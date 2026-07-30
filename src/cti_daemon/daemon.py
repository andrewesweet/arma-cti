"""The Phase-1 daemon: one request line in, one reply line out."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cti_daemon import campaign, commands, economy, manifest, protocol
from cti_daemon.outbox import Outbox, UnknownSequenceError
from cti_daemon.port import CommandPort
from cti_daemon.telemetry import Telemetry

if TYPE_CHECKING:
    from collections.abc import Callable

DEFAULT_ECONOMY = Path(__file__).parents[2] / "config" / "economy.json"
DEFAULT_MANIFESTS = Path(__file__).parents[2] / "manifests"
DEFAULT_MAP = "stratis"


class Daemon:
    """Dispatches requests and owns the outbox the game reads from."""

    def __init__(
        self,
        *,
        telemetry_path: Path,
        economy_path: Path | None = None,
        manifests_path: Path | None = None,
        map_id: str = DEFAULT_MAP,
    ) -> None:
        """Wire the daemon to its telemetry sink, the economy and the map."""
        self.outbox = Outbox()
        self._telemetry = Telemetry(telemetry_path)
        table = economy.load(economy_path or DEFAULT_ECONOMY)
        ledger = economy.Ledger(table.starting_funds)
        self.port = CommandPort(table=table, ledger=ledger, outbox=self.outbox)
        # One ledger, shared: Funds spent through the port and Funds earned from
        # Objectives are the same Funds, and a second ledger would be a second
        # answer to how much a side has.
        self.campaign = campaign.Campaign(
            map_manifest=manifest.load_all(manifests_path or DEFAULT_MANIFESTS)[map_id],
            table=table,
            ledger=ledger,
            outbox=self.outbox,
        )

    def handle_line(self, line: str) -> str:
        """Answer one request line. Every path produces a reply."""
        started = time.perf_counter_ns()
        request_id: str | None = None
        verb: str | None = None
        try:
            request = protocol.decode(line)
            request_id, verb = request.id, request.verb
            reply = self._dispatch(request)
            encoded = protocol.encode(reply)
        except protocol.MalformedRequestError as exc:
            request_id = exc.request_id
            reply = protocol.failed(request_id, "malformed_request", exc.detail)
            encoded = protocol.encode(reply)
        except Exception as exc:  # noqa: BLE001 — a bug must answer, not hang the caller
            # The shim is blocked on a line. Anything that escapes a handler has
            # to come back as one, or SQF waits out its read timeout instead.
            reply = protocol.failed(request_id, "internal", f"{type(exc).__name__}: {exc}")
            encoded = protocol.encode(reply)
        # A refusal is recorded with its reason, not just its shape. Otherwise
        # every rejection looks identical on disk and the operator learns less
        # about a failure than the caller who caused it.
        refusal = reply.envelope.get("reason") or reply.envelope.get("error") or {}
        self._telemetry.record(
            "request",
            id=request_id,
            verb=verb,
            status=reply.envelope["status"],
            # `code` for a domain rejection, `class` for an error — one column
            # either way, because when reading a log the question is the same.
            reason_code=refusal.get("code") or refusal.get("class"),
            reason_detail=refusal.get("detail"),
            duration_us=(time.perf_counter_ns() - started) // 1_000,
        )
        return encoded

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
        }

    def _ping(self, request: protocol.Request) -> protocol.Reply:
        result: dict[str, Any] = {"pong": True}
        return protocol.accepted(request.id, result)

    def _observe(self, request: protocol.Request) -> protocol.Reply:
        """Take one report of what the world can see (ADR-0012's `observe`).

        A transport verb rather than a Command: nobody is instructing anything,
        the world is saying what is true. #15 grows this into the full
        observation feed; #13 needs only presence.
        """
        at_time = request.payload.get("time")
        if not isinstance(at_time, (int, float)) or isinstance(at_time, bool):
            detail = "`time` must be the in-game time in seconds"
            raise protocol.MalformedRequestError(detail, request.id)

        presence = request.payload.get("presence", {})
        if not isinstance(presence, dict):
            detail = "`presence` must map Objective ids to the sides present"
            raise protocol.MalformedRequestError(detail, request.id)

        paid = self.campaign.observe(float(at_time), presence)
        for payout in paid:
            self._telemetry.record("income", at=at_time, paid=payout)
        return protocol.accepted(
            request.id,
            {"owners": self.campaign.owners(), "funds": self.campaign.funds(), "paid": paid},
        )

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
        judgement = self.port.submit(command, acting_side=acting_side)
        if judgement.accepted:
            return protocol.accepted(request.id, judgement.result)
        return protocol.rejected(request.id, judgement.code, judgement.detail)

    def _poll(self, request: protocol.Request) -> protocol.Reply:
        """Hand over everything the game has not acknowledged yet."""
        messages = [
            {"sequence": entry.sequence, "message": entry.message}
            for entry in self.outbox.pending()
        ]
        return protocol.accepted(request.id, {"messages": messages})

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
