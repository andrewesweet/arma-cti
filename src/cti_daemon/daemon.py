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
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from cti_daemon import (
    budget,
    commands,
    observation,
    protocol,
    report,
    report_cycle,
)
from cti_daemon.dedupe import Answered
from cti_daemon.outbox import UnknownSequenceError

if TYPE_CHECKING:
    from collections.abc import Callable

    from cti_daemon import campaign as campaign_module
    from cti_daemon import planner
    from cti_daemon.outbox import Entry, Outbox
    from cti_daemon.port import CommandPort
    from cti_daemon.telemetry import Telemetry

# How long a request waits for the daemon's one lock before it is refused (#142).
#
# Not a synchronisation wait dressed up as a timeout: nothing here becomes true
# by waiting, and this never lengthens to make anything pass. It is a bound on
# how much self-inflicted load a wedged handler may collect. The transport gives
# every connection a thread and the shim abandons a call at 500 ms and reopens
# on the next one, so a handler stuck on anything — a filesystem stall in
# `archive.write`, a planner bug — used to gather one more thread blocked here
# every couple of seconds, for as long as the session lasted, with nothing shed
# and nothing said. A refused request returns its thread to the read loop, where
# an abandoned connection is already at EOF and the thread ends.
#
# 250 ms: comfortably inside the shim's 500 ms budget, so the refusal arrives as
# a typed reply rather than as the shim's own transport failure — the world can
# tell "the daemon said no" from "the daemon is gone" (#97) only if the daemon
# gets a word in. And twenty-eight times the worst request ever measured, both
# planners inside it (8.69 ms, docs/spikes/0002-two-commanders.md), so a healthy
# daemon under two Commanders never comes near it.
LOCK_WAIT_SECONDS: Final = 0.25

# How many unacknowledged Effects the outbox grows by between depth rows (#142).
#
# ADR-0004 has the engine draining at most 100 callbacks per frame, so a quarter
# of that is still one handover's worth of work and a poor thing to shout about,
# while the second row — 50 — is a backlog that several polls in a row have
# failed to clear. Coarse on purpose: a row per request would bury the log it is
# written to, and what is being watched for is a trend, not a value.
OUTBOX_DEPTH_STEP: Final = 25


@dataclass(frozen=True, slots=True)
class Wiring:
    """Everything a daemon answers requests with, assembled by Main.

    Declared here, where the adapter says what it needs, and filled in
    `cti_daemon.transport.wire`, which is the composition root and decides what
    those things are made of (#164).

    One record rather than four parameters, and deliberately unlike the authored
    inputs `build_daemon` keeps as separate arguments: those are knobs a caller
    varies one at a time, these four are one object graph. The port judges
    against the Campaign the cycle plays and both write to the telemetry the
    daemon writes to, so a caller free to mix collaborators from two wirings
    could build a daemon whose port and cycle disagree about which Campaign is
    being played.
    """

    campaign: campaign_module.Campaign
    port: CommandPort
    cycle: report_cycle.ReportCycle
    telemetry: Telemetry


class Daemon:
    """Dispatches requests and drains the outbox the game reads from."""

    def __init__(self, *, wiring: Wiring, epoch: str | None = None) -> None:
        """Take the collaborators Main built, and mint this daemon's identity.

        Handed its object graph rather than building one (#164). #76 moved the
        authored *paths* out — resolving `config/` and `addons/` from `__file__`
        made this module a composition root as well as an adapter, and bound a
        daemon to a source checkout — but the graph itself was still assembled
        here, so an adapter still decided what a Campaign in play is made of.
        `cti_daemon.transport.build_daemon` is Main and decides that now: it
        loads the authored files, wires the Campaign, the port and the cycle,
        and hands them over. What is left here is the wire: a lock, a dedupe
        window, an epoch, and a verb table.
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
        # Which `OUTBOX_DEPTH_STEP` band the outbox depth was last announced at,
        # so that a row is written when it changes and not once per request.
        # Zero is the honest starting value: an empty outbox is band zero, and a
        # daemon that announced it at bring-up would be announcing nothing.
        self._depth_band = 0
        # What the wire has already been told (#69, ADR-0034). The shim resends
        # a request whose exchange failed on its cached connection, and a write
        # that succeeded before the read failed has already been carried out
        # here — so an identical line gets the answer it got, not a second
        # Purchase. Here rather than in the port, because every verb this
        # answers changes something: `observe` folds a report and lets each
        # Commander play on it, and a replayed one is a Commander taking two
        # turns.
        self.answered = Answered()
        self._telemetry = wiring.telemetry
        # One campaign object holds ownership, Funds and Squads, and the port
        # judges against it. Two of anything here would be two answers to how
        # much a side has or what it owns — which is why these arrive together
        # as one wiring rather than being built here from parts.
        self.campaign = wiring.campaign
        self.port = wiring.port
        # The Campaign in play, and everything one report does to it (#75). The
        # daemon holds it rather than is it: this object answers a socket, that
        # one plays a Campaign, and Phase 2's `save` lands there because what it
        # persists is what that object holds (ADR-0008).
        self.cycle = wiring.cycle

    @property
    def outbox(self) -> Outbox:
        """The queue of Effects the world has not acknowledged yet.

        The Campaign's, read through here rather than held twice: the outbox is
        where the domain puts an Effect and where `poll` takes one from, and a
        daemon holding its own reference to the same object would be a second
        answer to which queue is the queue the moment Main wired one of them to
        something else.
        """
        return self.campaign.outbox

    @property
    def commanders(self) -> tuple[str, ...]:
        """The sides under AI command, in the order they play."""
        return self.cycle.commanders

    def commanded_by(self, side: str, brain: planner.Planner) -> None:
        """Put one side under an AI Commander for the rest of the session.

        Set at bring-up rather than passed to the constructor, because a planner
        is built from the manifest and the economy table Main has just loaded,
        and `transport.build` reads them back off the Campaign it wired rather
        than loading them a second time. Named here as well as on the cycle
        because bring-up talks to the daemon: `transport.build` has one object
        to hand a brain to.
        """
        self.cycle.commanded_by(side, brain)

    def handle_line(self, line: str) -> str:
        """Answer one request line, and only one at a time (#98).

        The lock is the whole of the daemon's concurrency model: every mutation
        of the Campaign happens inside it, so a second connection's request
        waits rather than interleaving. It also makes the replay window in
        `_answer` mean what it says — a resend cannot overtake the request it
        duplicates, because the answer is recorded before the lock is released.

        The wait for it is bounded (#142). Waiting forever was the whole of the
        old shed policy, and against a wedged handler it is not one: the caller
        has already given up at 500 ms and the thread stays parked regardless,
        so the queue behind a stuck request grew without bound on the process
        whose single lock *is* the concurrency model. Past `LOCK_WAIT_SECONDS`
        the request is refused instead — fail fast, in the wire's own language,
        which costs a healthy daemon nothing because it never waits that long.
        """
        if not self._lock.acquire(timeout=LOCK_WAIT_SECONDS):
            return self._shed(line)
        try:
            return self._answer(line)
        finally:
            self._lock.release()

    def _shed(self, line: str) -> str:
        """Refuse a request the daemon could not get to in time (#142).

        `busy` rather than a rejection code: nothing was judged, so this is not
        the port's vocabulary (`port.REJECTION_CODES`, and unlike those it never
        crosses into the exported schema) — it is the daemon saying it could not
        answer the request as asked, which is what an `error` reply is for. The
        world already branches on `status` alone and reads the class as text, so
        a healthy daemon's wire is untouched by this class existing.

        Deliberately *not* remembered by `Answered`: the request was never
        carried out, so the shim's resend must be carried out rather than
        answered from a refusal (#69, ADR-0034). A shed Purchase costs its
        Commander a round trip and nothing else.

        Decoding outside the lock is safe because `protocol.decode` is a pure
        function of the line, and it is worth doing: a refusal the caller cannot
        match to its request is barely better than no reply at all.
        """
        request_id, verb = self._identify(line)
        detail = (
            f"the daemon answers one request at a time (#98) and did not reach this one "
            f"within {LOCK_WAIT_SECONDS * 1000:.0f} ms: a request already in flight is "
            f"holding the lock. Nothing was judged and nothing was spent; ask again"
        )
        encoded = protocol.encode(
            protocol.stamped(protocol.failed(request_id, "busy", detail), self.epoch)
        )
        # Its own event rather than a `request` row: no request was served, and
        # a zero-duration `observe` in that column would flatter every
        # percentile `tools/push_path_report.py` reads out of it. A shed request
        # is a fact about the daemon's load, and the operator asking why a
        # session felt unresponsive wants to count these.
        self._telemetry.record(
            "request_shed",
            id=request_id,
            epoch=self.epoch,
            verb=verb,
            waited_ms=round(LOCK_WAIT_SECONDS * 1000),
        )
        return encoded

    @staticmethod
    def _identify(line: str) -> tuple[str | None, str | None]:
        """Read the id and verb off a line without acting on it."""
        try:
            request = protocol.decode(line)
        except protocol.MalformedRequestError as exc:
            return exc.request_id, None
        return request.id, request.verb

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
        self._gauge_outbox()
        return encoded

    def _gauge_outbox(self) -> None:
        """Say how deep the outbox is when it crosses a band, polled or not (#142).

        `outbox_handed` is written on a successful drain only, which leaves the
        one shape that matters unrecorded: the effect pump dies while
        `presence_report` lives (#102), income keeps paying, both Commanders
        keep buying, and the undelivered Effects accumulate in memory for a
        whole session with nothing on disk saying so. #125's starvation had to
        be diagnosed from outside the daemon for exactly this reason. A poll is
        the wrong place to look from, because the failure *is* the absence of
        polls.

        The request path is the right one: every Effect enters the outbox under
        a request, so this is called wherever the depth can have changed, and it
        needs no timer thread on a process whose concurrency model is one lock
        (#98). Bands rather than values, and on the way down as well as up — a
        backlog that cleared is as much of an event as one that formed.
        """
        band = self.outbox.depth // OUTBOX_DEPTH_STEP
        if band == self._depth_band:
            return
        self._depth_band = band
        self._telemetry.record(
            "outbox_depth", depth=self.outbox.depth, step=OUTBOX_DEPTH_STEP, epoch=self.epoch
        )

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
        handler = HANDLERS.get(request.verb)
        if handler is None:
            return protocol.failed(request.id, "unknown_verb", f"no handler for {request.verb!r}")
        return handler(self, request)

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
        try:
            picture = self.cycle.fold(report.parse(request.payload))
        except (report.MalformedReportError, report_cycle.UnknownPlaceError) as exc:
            # The one place a refusal from either side of the observe path
            # crosses into the wire's language (#164). A document the schema
            # cannot read and ground this map does not have are the same kind of
            # answer — the daemon cannot read this report — and neither module
            # has to know what a request id is to say so.
            raise protocol.MalformedRequestError(str(exc), request.id) from exc
        return protocol.accepted(request.id, observation.serialise(picture))

    def _command(self, request: protocol.Request) -> protocol.Reply:
        """Carry one Command to the port and return its judgement (ADR-0012)."""
        try:
            command = commands.parse_command(request.payload)
        except commands.MalformedCommandError as exc:
            return protocol.rejected(request.id, "malformed_command", str(exc))

        # Who the server resolved this caller to be (ADR-0044). The gateway
        # stamps it from its own state — a Commander's assignment or a squad
        # leader's slot — and a Command that carries no stamp is a caller nobody
        # vouched for. It used to default to the side named in the payload,
        # which made "who is acting" a claim the caller could write: #19's audit
        # found it, and the fix is that the field is required rather than
        # defaulted. `wrong_side` below stays for the resolved caller who
        # reaches past his own side; this is the caller who was never resolved.
        stamped_side = request.payload.get("acting_side")
        if not isinstance(stamped_side, str) or stamped_side not in commands.SIDES:
            return protocol.rejected(
                request.id,
                "unknown_caller",
                "this Command carries no server-side `acting_side` stamp, so the daemon "
                "cannot tell who is acting: a Command reaches the port through the gateway, "
                "which stamps the caller from the server's own state",
            )
        acting_side = stamped_side
        # Which principal is at the door (ADR-0040). Empty is a Commander; a
        # Squad id is the squad leader the gateway resolved from the caller's
        # own slot, and the port holds him to that Squad. Read here rather than
        # off the Command because it is a stamp, not an argument: a client that
        # could write it would be a client that could command any Squad.
        stamped = request.payload.get("acting_squad", "")
        acting_squad = stamped if isinstance(stamped, str) else ""
        # One Commander per side, whichever kind it is (#18). `commanded_by`
        # already refuses a second AI brain on a side, for the reason ADR-0015
        # gives: two brains on one side are two answers to what that side is
        # doing and both spend the same Funds. A human reaching the wire while an
        # AI plays that side is the same thing arriving through the other door,
        # so it gets the same answer. Checked here rather than in the port
        # because the port is what the in-process planner calls, and a planner
        # refused for being under a Commander would be refused for existing.
        #
        # A squad leader is not a second Commander and is not refused by this:
        # the MVP's second mode is a person leading a Squad while both sides are
        # AI-commanded (CONTEXT.md), and a check that took his Reinforce away
        # for the presence of the AI playing his own side would refuse that mode
        # entirely. He is held to his own Squad at the port instead (ADR-0040).
        if not acting_squad and self.cycle.commanded(acting_side):
            return protocol.rejected(
                request.id,
                "wrong_side",
                f"{acting_side} is under an AI Commander: a side has one Commander, "
                f"so bring the world up without an AI on the side you mean to play",
            )
        judgement = self.port.submit(command, acting_side=acting_side, acting_squad=acting_squad)
        if judgement.accepted:
            return protocol.accepted(request.id, judgement.result)
        return protocol.rejected(request.id, judgement.code, judgement.detail)

    def _poll(self, request: protocol.Request) -> protocol.Reply:
        """Hand over as much of the unacknowledged outbox as one reply carries.

        A prefix, oldest first, bounded by `budget.REPORT_GUARD_BYTES` (#67). A
        `callExtension` return is capped at `budget.RETURN_CAP_BYTES` and
        truncated in silence (ADR-0004), and a truncated poll reply is broken
        JSON mid-message: the effects past the cut are lost with nothing said,
        which is the false-green shape ADR-0028 warns about arriving on the push
        path. One figure guards both directions of that one cap, and it lives in
        `cti_daemon.budget`, which owns the wire-cap numbers — a second literal
        here held equal by a test was the shape #78 removed from SQF (#164).

        Nothing is lost by stopping short: the game acknowledges through a
        high-water mark and polls again, so the ack cursor delivers the
        remainder on the next turn of the pump (ADR-0018). Where the observation
        path's answer to the guard is a smaller picture, this one's is a shorter
        drain. Stopping at the first entry that does not fit rather than
        skipping it is what keeps the order the outbox issued.
        """
        pending = self.outbox.pending()
        messages: list[dict[str, Any]] = []
        # Priced incrementally rather than by re-encoding the whole candidate
        # reply once per entry, which read the backlog quadratically (#156).
        # Exact, not an estimate: `protocol.measure` shares `encode`'s fixed
        # rendering, under which a document encodes the same alone as nested —
        # so a longer drain costs the empty drain plus each message plus one
        # comma between neighbours, to the byte.
        size = len(protocol.encode(self._drain(request, messages)))
        for entry in pending:
            message = self._addressed(entry)
            grown = size + protocol.measure(message) + (1 if messages else 0)
            if grown >= budget.REPORT_GUARD_BYTES:
                break
            messages.append(message)
            size = grown

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
    def _addressed(entry: Entry) -> dict[str, Any]:
        """Render one outbox entry as the wire message the game receives.

        The single boundary point (#77). The outbox holds `Effect` objects and
        the domain never constructs a wire document, so a change to the effect
        rendering is a change here and nowhere else.
        """
        return {"sequence": entry.sequence, "message": commands.serialise_effect(entry.effect)}

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
        alone = [self._addressed(entry)]
        size = len(protocol.encode(self._drain(request, alone)))
        guard = budget.REPORT_GUARD_BYTES
        self._telemetry.record(
            "outbox_oversized", sequence=entry.sequence, reply_bytes=size, guard=guard
        )
        detail = (
            f"outbox entry {entry.sequence} needs {size} bytes of a {guard}-byte reply guard: "
            f"it cannot cross one callExtension return and will not be truncated"
        )
        return protocol.failed(request.id, "oversized_message", detail)

    def _ack(self, request: protocol.Request) -> protocol.Reply:
        """Retire everything up to the sequence the game says it received.

        An acknowledgement may say that some of what it retired was refused for
        good rather than carried out (#100). The world dead-letters an effect it
        can never apply so the queue behind it moves; the row lands here, because
        an effect the Campaign paid for and never got is part of the Campaign's
        record and the server's log is not that record.

        A malformed payload is raised rather than returned, which is what `_view`
        and `_observe` already do (#88): one convention across the handlers, and
        `_answer` turns it into the same `malformed_request` reply this built by
        hand.
        """
        through = request.payload.get("through")
        # `bool` is an `int` in Python and is never a sequence number.
        if not isinstance(through, int) or isinstance(through, bool):
            detail = f"`through` must be an integer sequence, got {through!r}"
            raise protocol.MalformedRequestError(detail, request.id)
        dead = request.payload.get("dead", [])
        if not isinstance(dead, list) or not all(isinstance(row, dict) for row in dead):
            detail = f"`dead` must be a list of dead-letter rows, got {dead!r}"
            raise protocol.MalformedRequestError(detail, request.id)
        for row in dead:
            self._telemetry.record(
                "effect_dead_letter",
                sequence=row.get("sequence"),
                effect=row.get("effect"),
                reason=row.get("reason"),
            )
        try:
            cleared = self.outbox.ack(through=through)
        except UnknownSequenceError as exc:
            return protocol.rejected(request.id, "unknown_sequence", str(exc))
        return protocol.accepted(request.id, {"cleared": cleared})


# One table rather than a dictionary rebuilt on every request (#156) — the fix
# #90 already applied to the port's Command dispatch, one module along. Below
# the class because it names its methods; unbound, so `_dispatch` passes the
# daemon. These are ADR-0012's transport verbs, not Commands: the catalogue
# binds one level down, at `port.HANDLERS`.
HANDLERS: Final[dict[str, Callable[[Daemon, protocol.Request], protocol.Reply]]] = {
    "ping": Daemon._ping,  # noqa: SLF001 — the class's own dispatch table
    "poll": Daemon._poll,  # noqa: SLF001 — ditto
    "ack": Daemon._ack,  # noqa: SLF001 — ditto
    "command": Daemon._command,  # noqa: SLF001 — ditto
    "observe": Daemon._observe,  # noqa: SLF001 — ditto
    "view": Daemon._view,  # noqa: SLF001 — ditto
}
