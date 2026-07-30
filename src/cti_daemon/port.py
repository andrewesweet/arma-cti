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

from cti_daemon import squads
from cti_daemon.commands import Effect, serialise_effect
from cti_daemon.economy import InsufficientFundsError

if TYPE_CHECKING:
    from collections.abc import Callable

    from cti_daemon.campaign import Campaign
    from cti_daemon.commands import Command
    from cti_daemon.economy import EconomyTable, Ledger
    from cti_daemon.outbox import Outbox

# ADR-0012 fixed the first four for #12; #14's Order adds the last two, and the
# ADR's own consequences anticipate that ("new port verbs are schema
# additions"). The SQF side is generated from this set, so a code can never be
# added quietly — but it can be added.
REJECTION_CODES: Final = frozenset(
    {
        "insufficient_funds",
        "unknown_command",
        "malformed_command",
        "wrong_side",
        "unknown_squad",
        "already_held",
    }
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

    campaign: Campaign

    @property
    def table(self) -> EconomyTable:
        """The authored prices and timings the rules are judged against."""
        return self.campaign.table

    @property
    def ledger(self) -> Ledger:
        """The Funds each side holds. One ledger: spending and income are one."""
        return self.campaign.ledger

    @property
    def outbox(self) -> Outbox:
        """The one path every world effect takes, whoever issued it."""
        return self.campaign.outbox

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

        handlers: dict[str, Callable[[Command], Judgement]] = {
            "purchase": self._purchase,
            "order": self._order,
        }
        handler = handlers.get(command.name)
        if handler is None:
            return _reject("unknown_command", f"no such Command: {command.name!r}")

        return handler(command)

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
        bought = next(entry for entry in self.table.squads if entry.id == squad_type)
        squad = self.campaign.roster.add(command.side, bought.id, bought.size)
        self.outbox.push(
            serialise_effect(
                Effect(
                    name="squad_spawned",
                    side=command.side,
                    args={"squad": squad.id, "squad_type": bought.id, "size": bought.size},
                )
            )
        )
        # The id is advisory like the balance, but it is what a Commander needs
        # to order what it has just bought without waiting for an observation.
        return _accept({"squad": squad.id, "funds": remaining})

    def _order(self, command: Command) -> Judgement:
        """Give one Squad a standing Order (#14).

        Standing, not a waypoint: the Order is recorded against the Squad here
        and the world is told to act on it, so it outlives the leader who was
        carrying it when it arrives.
        """
        kind = command.args.get("order")
        if kind not in squads.ORDERS:
            return _reject(
                "malformed_command",
                f"no such Order: {kind!r}; expected one of {list(squads.ORDERS)}",
            )

        squad_id = command.args.get("squad")
        if not isinstance(squad_id, str) or not squad_id:
            return _reject("malformed_command", "order needs a `squad`")
        squad = self.campaign.roster.of(squad_id, command.side)
        if squad is None:
            return _reject("unknown_squad", f"{command.side} has no Squad {squad_id!r}")

        objective = command.args.get("objective", "")
        refusal = self._check_ground(command.side, str(kind), objective)
        if refusal is not None:
            return refusal

        squad.order = squads.Order(kind=str(kind), objective=str(objective))
        result = {"squad": squad.id, "order": squad.order.kind, "objective": squad.order.objective}
        self.outbox.push(
            serialise_effect(Effect(name="order_issued", side=command.side, args=dict(result)))
        )
        return _accept(result)

    def _check_ground(self, side: str, kind: str, objective: object) -> Judgement | None:
        """Judge the ground an Order names, or None if it names it correctly."""
        if kind not in squads.NEEDS_OBJECTIVE:
            # Silently dropping a stray Objective would hide a UI bug behind an
            # Order that looked accepted and went somewhere else.
            if objective:
                return _reject("malformed_command", f"{kind} takes no Objective, got {objective!r}")
            return None

        owner = self.campaign.holds(objective) if isinstance(objective, str) else None
        if owner is None:
            return _reject(
                "malformed_command", f"{kind} needs an Objective this map has, got {objective!r}"
            )

        # A Capture on ground the side already holds is a nonsensical Order, and
        # accepting it as a no-op would leave a Commander waiting on a Squad
        # that was never going anywhere. The detail says what to do instead.
        if kind == "capture" and owner == side:
            return _reject(
                "already_held",
                f"{side} already holds {objective}: Capture is for ground you do not hold, "
                f"so order Defend to garrison it instead",
            )
        return None
