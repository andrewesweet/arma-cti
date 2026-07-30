"""The Command Port: the one door into the campaign.

ADR-0012 makes the daemon the rules authority and this the sole mutator of
strategic state. The human UI reaches it through the SQF gateway and the
transport envelope; the AI planner builds the same Command objects and calls
`submit` in-process. Neither has a second path, which is what makes "one wire
format for human and AI" structural rather than conventional.

A judgement is never work. An accepted Command queues an Effect on the outbox
and returns only advisory data, so a human-issued effect and an AI-issued one
travel the same path and #19 has one path to audit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from cti_daemon.commands import Effect, serialise_effect
from cti_daemon.economy import InsufficientFundsError

if TYPE_CHECKING:
    from cti_daemon.commands import Command
    from cti_daemon.economy import EconomyTable, Ledger
    from cti_daemon.outbox import Outbox

# ADR-0012 fixes this set for #12. Adding a fifth is a schema change, and the
# SQF side is generated from the same source, so it cannot be done quietly.
REJECTION_CODES: Final = frozenset(
    {"insufficient_funds", "unknown_command", "malformed_command", "wrong_side"}
)


@dataclass(frozen=True, slots=True)
class Judgement:
    """What the rules made of a Command. Never an instruction to the world."""

    accepted: bool
    result: dict[str, Any]
    code: str = ""
    detail: str = ""


def _accept(result: dict[str, Any]) -> Judgement:
    return Judgement(accepted=True, result=result)


def _reject(code: str, detail: str) -> Judgement:
    if code not in REJECTION_CODES:
        message = f"{code!r} is not one of the port's rejection codes"
        raise ValueError(message)
    return Judgement(accepted=False, result={}, code=code, detail=detail)


@dataclass(slots=True)
class CommandPort:
    """Validates Commands against the campaign and records what they change."""

    table: EconomyTable
    ledger: Ledger
    outbox: Outbox

    def submit(self, command: Command, *, acting_side: str) -> Judgement:
        """Judge one Command. The only way strategic state ever moves."""
        # The gateway stamps the acting side server-side from its own commander
        # assignment; a Command naming another side is a caller reaching past
        # its authority, not a malformed one.
        if command.side != acting_side:
            return _reject(
                "wrong_side",
                f"{acting_side} may not command for {command.side}",
            )

        if command.name != "purchase":
            return _reject("unknown_command", f"no such Command: {command.name!r}")

        return self._purchase(command)

    def _purchase(self, command: Command) -> Judgement:
        """Spend Funds to put a new Squad at that side's Base."""
        squad_type = command.args.get("squad_type")
        if not isinstance(squad_type, str) or not squad_type:
            return _reject("malformed_command", "purchase needs a `squad_type`")

        price = self.table.price(squad_type)
        if price is None:
            return _reject("malformed_command", f"no Squad type {squad_type!r} is sold")

        try:
            remaining = self.ledger.spend(command.side, price)
        except InsufficientFundsError as exc:
            return _reject("insufficient_funds", str(exc))

        # The Base is not named here on purpose: the daemon owns the rules, the
        # game owns the geometry, and the manifest already tells it where each
        # side's Base is.
        squad = next(entry for entry in self.table.squads if entry.id == squad_type)
        self.outbox.push(
            serialise_effect(
                Effect(
                    name="squad_spawned",
                    side=command.side,
                    args={"squad_type": squad.id, "size": squad.size},
                )
            )
        )
        return _accept({"funds": remaining})
