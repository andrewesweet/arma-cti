"""The Phase-1 daemon: one request line in, one reply line out.

Transport and dispatch only. What a request *means* to the Campaign lives one
module along in `cti_daemon.report_cycle`, and what the observe report is made
of lives in `cti_daemon.report` — so this class decodes, delegates, replies and
writes down who asked, and a Phase-2 snapshot verb is a handler here plus a
method there rather than another job in one class (#75).
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from cti_daemon import (
    campaign,
    commands,
    economy,
    observation,
    protocol,
    report,
    report_cycle,
)
from cti_daemon.dedupe import Answered
from cti_daemon.outbox import Entry, Outbox, UnknownSequenceError
from cti_daemon.port import CommandPort
from cti_daemon.telemetry import Telemetry

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from cti_daemon import planner
    from cti_daemon.economy import EconomyTable
    from cti_daemon.manifest import MapManifest

# What one poll reply may hand the world in one go. A `callExtension` return is
# capped at `observation.RETURN_CAP_BYTES` and truncated in silence (ADR-0004),
# and a truncated poll reply is broken JSON mid-message: the effects past the
# cut are lost with nothing said, which is the false-green shape ADR-0028 warns
# about arriving on the push path (#67).
#
# Nine tenths of the cap, the same figure and the same ratio the observation
# path guards itself at (`observation.REPORT_GUARD_BYTES`), so that a reply
# merely close to truncating fails a run rather than a Play Session. A test
# holds the two together. Where the observation path's fix is a smaller picture,
# this one's is a shorter drain: the outbox already numbers its entries and
# retires an acknowledged prefix (ADR-0018), so a poll hands over as much as
# fits and the ack cursor brings the rest on the next one.
POLL_GUARD_BYTES: Final = 9_216


class Daemon:
    """Dispatches requests and owns the outbox the game reads from."""

    def __init__(
        self,
        *,
        telemetry_path: Path,
        table: EconomyTable,
        map_manifest: MapManifest,
        archive_path: Path | None = None,
        epoch: str | None = None,
    ) -> None:
        """Wire the daemon to its telemetry sink, the economy and the map.

        Handed the authored economy and the map it is playing rather than told
        where the repo keeps them (#76). Resolving `config/` and `addons/` from
        `__file__` made this module a composition root as well as an adapter,
        and bound a daemon to a source checkout: an installed or relocated
        package resolved those paths into nothing. Where the authored files live
        is `cti_daemon.transport`'s, which is Main.
        """
        # One request at a time, whoever is asking (#98). The transport serves
        # every connection on its own thread, and none of the state below —
        # ownership, the Ledger, the Roster, Contacts, the outbox — is written
        # under any other lock. Two connections is not a hypothetical: the
        # shim's resend arrives on a fresh connection while the request it is
        # resending may still be in flight on the old one (#69, ADR-0034), and
        # that is precisely the moment a duplicate must meet the record rather
        # than race it.
        #
        # A lock rather than a single-threaded server: a serial server would
        # accept the resend's connection only after the stuck one closed, which
        # is the hang the resend exists to escape, and `serve_in_thread` plus
        # any diagnostic connection would queue behind the game's. A lock rather
        # than finer-grained locking: a request is 746 µs at p50 and 8.69 ms at
        # its worst with both planners inside it
        # (docs/spikes/0002-two-commanders.md), so serialising whole requests
        # costs nothing measurable and buys an invariant that needs no proof per
        # field. Non-reentrant on purpose: nothing under `_answer` re-enters the
        # daemon, and if something ever does it should stop rather than quietly
        # interleave with itself.
        self._lock = threading.Lock()
        # Who is answering (#96, ADR-0036). Every reply carries it, and the
        # world latches the first one it sees: this daemon's whole strategic
        # state is in memory, so a restart is a factory-fresh Campaign wearing
        # the old world's clothes, and the shim's silent reconnect (ADR-0005)
        # makes it indistinguishable from a hiccup on the transport alone.
        # Minted here rather than passed in, because a daemon that could be
        # handed its predecessor's identity could claim to be it.
        self.epoch = epoch or protocol.mint_epoch()
        self.outbox = Outbox()
        # What the wire has already been told (#69, ADR-0034). The shim resends
        # a request whose exchange failed on its cached connection, and a write
        # that succeeded before the read failed has already been carried out
        # here — so an identical line gets the answer it got, not a second
        # Purchase. Here rather than in the port, because every verb this
        # answers changes something: `observe` folds a report and lets each
        # Commander play on it, and a replayed one is a Commander taking two
        # turns.
        self.answered = Answered()
        self._telemetry = Telemetry(telemetry_path)
        # One campaign object holds ownership, Funds and Squads, and the port
        # judges against it. Two of anything here would be two answers to how
        # much a side has or what it owns.
        self.campaign = campaign.Campaign(
            map_manifest=map_manifest,
            table=table,
            ledger=economy.Ledger(table.starting_funds),
            outbox=self.outbox,
        )
        self.port = CommandPort(campaign=self.campaign)
        # The Campaign in play, and everything one report does to it (#75). The
        # daemon holds it rather than is it: this object answers a socket, that
        # one plays a Campaign, and Phase 2's `save` lands there because what it
        # persists is what that object holds (ADR-0008).
        self.cycle = report_cycle.ReportCycle(
            campaign=self.campaign,
            port=self.port,
            telemetry=self._telemetry,
            telemetry_path=telemetry_path,
            # Where a won Campaign's record lands, and where its summary is read
            # from (#35, ADR-0023). Beside the telemetry by default, because the
            # two are one run's evidence and separating them would be one more
            # path for a session to get wrong.
            archive_path=archive_path or telemetry_path.parent / "campaigns",
        )

    @property
    def commanders(self) -> tuple[str, ...]:
        """The sides under AI command, in the order they play."""
        return self.cycle.commanders

    def commanded_by(self, side: str, brain: planner.Planner) -> None:
        """Put one side under an AI Commander for the rest of the session.

        Set at bring-up rather than passed to the constructor, because a planner
        is built from the manifest and the economy table this object has just
        loaded, and there is no sense in loading them twice to hand them back.
        Named here as well as on the cycle because bring-up talks to the daemon:
        `transport.build` has one object to hand a brain to.
        """
        self.cycle.commanded_by(side, brain)

    def handle_line(self, line: str) -> str:
        """Answer one request line, and only one at a time (#98).

        The lock is the whole of the daemon's concurrency model: every mutation
        of the Campaign happens inside it, so a second connection's request
        waits rather than interleaving. It also makes the replay window in
        `_answer` mean what it says — a resend cannot overtake the request it
        duplicates, because the answer is recorded before the lock is released.
        """
        with self._lock:
            return self._answer(line)

    def _answer(self, line: str) -> str:
        """Carry out one request line. Every path produces a reply.

        A line identical to one already answered is answered from that answer
        rather than carried out again (#69, ADR-0034). Nothing downstream sees
        it: the shim's resend after a failed exchange is indistinguishable from
        the first attempt at this end, so the receiver is the only place the
        duplicate can be stopped.
        """
        started = time.perf_counter_ns()
        remembered = self.answered.recall(line)
        if remembered is not None:
            self._telemetry.record(
                "request_replayed",
                id=remembered.id,
                epoch=self.epoch,
                verb=remembered.verb,
                duration_us=(time.perf_counter_ns() - started) // 1_000,
                reply_bytes=len(remembered.reply),
            )
            return remembered.reply
        request_id: str | None = None
        verb: str | None = None
        # Who the caller was acting for, when the request says. A human-issued
        # Command is then attributable in the same column an AI-issued one is
        # (#17), and #19 has one attribution to audit rather than two.
        acting: str | None = None
        try:
            request = protocol.decode(line)
            request_id, verb = request.id, request.verb
            acting = self._acting_side(request)
            reply = self._dispatch(request)
        except protocol.MalformedRequestError as exc:
            request_id = exc.request_id
            reply = protocol.failed(request_id, "malformed_request", exc.detail)
        except Exception as exc:  # noqa: BLE001 — a bug must answer, not hang the caller
            # The shim is blocked on a line. Anything that escapes a handler has
            # to come back as one, or SQF waits out its read timeout instead.
            reply = protocol.failed(request_id, "internal", f"{type(exc).__name__}: {exc}")
        # Stamped once, on every path out — a malformed line and an internal
        # bug are exactly the moments the world most needs to know who answered
        # (#96, ADR-0036), and a branch that could forget the epoch is a branch
        # through which a restart stays invisible.
        encoded = protocol.encode(protocol.stamped(reply, self.epoch))
        # A refusal is recorded with its reason, not just its shape. Otherwise
        # every rejection looks identical on disk and the operator learns less
        # about a failure than the caller who caused it.
        refusal = reply.envelope.get("reason") or reply.envelope.get("error") or {}
        self._telemetry.record(
            "request",
            id=request_id,
            # One run's telemetry is appended to across a daemon restart, so
            # this is what tells two daemons' records apart in one file (#96).
            epoch=self.epoch,
            verb=verb,
            side=acting,
            status=reply.envelope["status"],
            # `code` for a domain rejection, `class` for an error — one column
            # either way, because when reading a log the question is the same.
            reason_code=refusal.get("code") or refusal.get("class"),
            reason_detail=refusal.get("detail"),
            duration_us=(time.perf_counter_ns() - started) // 1_000,
            # A `callExtension` return caps at 10,240 bytes and truncates in
            # silence (ADR-0004), so how close a reply runs to it is a number
            # worth having on disk rather than a thing to find out in a session.
            reply_bytes=len(encoded),
        )
        self.answered.remember(line, request_id=request_id, verb=verb, reply=encoded)
        return encoded

    @staticmethod
    def _acting_side(request: protocol.Request) -> str | None:
        """Which side a request was issued for, or None when it is nobody's.

        The gateway stamps `acting_side` server-side from its own Commander
        assignment, so that is the honest answer where it exists; `side` is what
        the caller claimed. A transport verb belongs to no side and says so by
        leaving the column empty rather than by guessing.
        """
        for key in ("acting_side", "side"):
            claimed = request.payload.get(key)
            if isinstance(claimed, str) and claimed:
                return claimed
        return None

    def _dispatch(self, request: protocol.Request) -> protocol.Reply:
        handler = self._handlers().get(request.verb)
        if handler is None:
            return protocol.failed(request.id, "unknown_verb", f"no handler for {request.verb!r}")
        return handler(request)

    def _handlers(self) -> dict[str, Callable[[protocol.Request], protocol.Reply]]:
        return {
            "ping": self._ping,
            "poll": self._poll,
            "ack": self._ack,
            "command": self._command,
            "observe": self._observe,
            "view": self._view,
        }

    def _ping(self, request: protocol.Request) -> protocol.Reply:
        result: dict[str, Any] = {"pong": True}
        return protocol.accepted(request.id, result)

    def _view(self, request: protocol.Request) -> protocol.Reply:
        """Hand one Commander the picture it may see (#18).

        A transport verb beside `observe` rather than a Command: nobody is
        instructing anything, and ADR-0012 keeps domain Commands and transport
        verbs out of one namespace. `observe` is the world reporting and gets the
        public picture back (#27) because the server is not a Commander; this is
        the server asking, on behalf of a Commander it has assigned, for the one
        view that Commander is entitled to — and the server forwards it to that
        client alone rather than reading it.

        It is `Campaign.observation(side)` and there is nothing else to serve: the
        projection is the only thing that exists (#27), so the human Commander and
        the in-process planner are reading the same call as well as commanding
        through the same port. That is what makes Commander symmetry cover knowing
        as well as commanding without a second assembly step to keep honest.

        A side under an AI Commander has no view to hand out. Not a technicality:
        that side's Funds, roster and standing Orders are the enemy's secrets to
        whoever asked, and the one door that could leak them is this one.
        """
        side = request.payload.get("side")
        if not isinstance(side, str) or side not in commands.SIDES:
            detail = f"`side` must name a side that is playing, got {side!r}"
            raise protocol.MalformedRequestError(detail, request.id)
        if self.cycle.commanded(side):
            return protocol.rejected(
                request.id,
                "wrong_side",
                f"{side} is under an AI Commander and has no human view to hand out",
            )
        return protocol.accepted(request.id, observation.serialise(self.campaign.observation(side)))

    def _observe(self, request: protocol.Request) -> protocol.Reply:
        """Take one report of what the world can see (ADR-0012's `observe`).

        A transport verb rather than a Command: nobody is instructing anything,
        the world is saying what is true. The reply is the whole strategic
        picture (#15), which is what makes this the return leg — a planner has
        something to plan against without a second channel or a second cadence.

        Decode and delegate, and nothing else (#75). What the report is made of
        is `cti_daemon.report`, which is also what the samplers are built from;
        what one report does to the Campaign, and in what order, is the cycle's.
        The picture that comes back is the public one (#27), which is what the
        server repaints its markers from and all it is entitled to.
        """
        told = report.parse(request.payload, request_id=request.id)
        try:
            picture = self.cycle.fold(told)
        except report_cycle.UnknownPlaceError as exc:
            # Ground this map does not have is a report the daemon cannot read,
            # and it is refused in the wire's language here rather than in the
            # Campaign's language there.
            raise protocol.MalformedRequestError(str(exc), request.id) from exc
        return protocol.accepted(request.id, observation.serialise(picture))

    def _command(self, request: protocol.Request) -> protocol.Reply:
        """Carry one Command to the port and return its judgement (ADR-0012)."""
        try:
            command = commands.parse(request.payload)
        except commands.MalformedCommandError as exc:
            return protocol.rejected(request.id, "malformed_command", str(exc))

        # The SQF gateway stamps the acting side server-side and overwrites the
        # client's, so the two normally agree and `wrong_side` is unreachable
        # through the front door. It stays reachable for an in-process planner
        # bug and for anything that reached the daemon without the gateway —
        # which is the path #19's audit exists to find.
        acting_side = request.payload.get("acting_side", command.side)
        # One Commander per side, whichever kind it is (#18). `commanded_by`
        # already refuses a second AI brain on a side, for the reason ADR-0015
        # gives: two brains on one side are two answers to what that side is
        # doing and both spend the same Funds. A human reaching the wire while an
        # AI plays that side is the same thing arriving through the other door,
        # so it gets the same answer. Checked here rather than in the port
        # because the port is what the in-process planner calls, and a planner
        # refused for being under a Commander would be refused for existing.
        if self.cycle.commanded(acting_side):
            return protocol.rejected(
                request.id,
                "wrong_side",
                f"{acting_side} is under an AI Commander: a side has one Commander, "
                f"so bring the world up without an AI on the side you mean to play",
            )
        judgement = self.port.submit(command, acting_side=acting_side)
        if judgement.accepted:
            return protocol.accepted(request.id, judgement.result)
        return protocol.rejected(request.id, judgement.code, judgement.detail)

    def _poll(self, request: protocol.Request) -> protocol.Reply:
        """Hand over as much of the unacknowledged outbox as one reply carries.

        A prefix, oldest first, bounded by `POLL_GUARD_BYTES` (#67). Nothing is
        lost by stopping short: the game acknowledges through a high-water mark
        and polls again, so the ack cursor delivers the remainder on the next
        turn of the pump (ADR-0018). Stopping at the first entry that does not
        fit rather than skipping it is what keeps the order the outbox issued.
        """
        pending = self.outbox.pending()
        messages: list[dict[str, Any]] = []
        for entry in pending:
            candidate = [*messages, {"sequence": entry.sequence, "message": entry.message}]
            if len(protocol.encode(self._drain(request, candidate))) >= POLL_GUARD_BYTES:
                break
            messages = candidate

        if pending and not messages:
            return self._oversized(request, pending[0])

        if messages:
            # How much work one drain hands the world in one go, and how much
            # was held back. ADR-0004 has the engine draining at most 100
            # callbacks per frame, and two Commanders double what arrives at
            # this path (#17) — so the size of a drain is a number to have on
            # disk rather than to estimate, and a backlog that stops draining
            # inside one poll has to be visible before it is a Play Session's
            # problem. Written only when there is something to hand over: a poll
            # that found nothing is the ordinary case and would bury the rest.
            self._telemetry.record(
                "outbox_handed",
                handed=len(messages),
                through=messages[-1]["sequence"],
                deferred=len(pending) - len(messages),
            )
        return self._drain(request, messages)

    @staticmethod
    def _drain(request: protocol.Request, messages: list[dict[str, Any]]) -> protocol.Reply:
        """Build the reply one drain goes back in. Measured before it is sent."""
        return protocol.accepted(request.id, {"messages": messages})

    def _oversized(self, request: protocol.Request, entry: Entry) -> protocol.Reply:
        """Refuse a drain whose oldest entry cannot cross the wire at all.

        Loud rather than truncated, matching the observation path's refusal: an
        effect that does not fit one return is an effect to make smaller, never
        a reason to hand the transport something it will cut in half. The entry
        stays on the outbox and every poll fails the same way until it is fixed
        — a stalled pump that says so beats a pump that quietly loses the work
        behind it.
        """
        alone = [{"sequence": entry.sequence, "message": entry.message}]
        size = len(protocol.encode(self._drain(request, alone)))
        self._telemetry.record(
            "outbox_oversized", sequence=entry.sequence, reply_bytes=size, guard=POLL_GUARD_BYTES
        )
        detail = (
            f"outbox entry {entry.sequence} needs {size} bytes of a {POLL_GUARD_BYTES}-byte "
            f"reply guard: it cannot cross one callExtension return and will not be truncated"
        )
        return protocol.failed(request.id, "oversized_message", detail)

    def _ack(self, request: protocol.Request) -> protocol.Reply:
        """Retire everything up to the sequence the game says it received."""
        through = request.payload.get("through")
        if not isinstance(through, int) or isinstance(through, bool):
            return protocol.failed(
                request.id, "malformed_request", "`through` must be an integer sequence"
            )
        try:
            cleared = self.outbox.ack(through=through)
        except UnknownSequenceError as exc:
            return protocol.rejected(request.id, "unknown_sequence", str(exc))
        return protocol.accepted(request.id, {"cleared": cleared})
