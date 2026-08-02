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

from cti_daemon import budget, squads
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
        # Ground the map has, that this Order may not name (ADR-0020): Capture
        # never names a Base, Assault only the enemy Base, Defend never the
        # enemy Base. Ground the map lacks stays `malformed_command`.
        "wrong_ground",
        # A Campaign that has been won takes no more Commands (#59). The world
        # keeps a map screen open until the end screen reaches it, so this is a
        # judgement a Commander can be shown rather than an error.
        "campaign_over",
        # The roster has a ceiling and it is the wire's, not a balance decision
        # (#101): past the point where a side's Observation stops fitting one
        # `callExtension` return, the engine truncates in silence and the
        # Commander's view stops arriving. A Purchase that would cross it is
        # refused in the port's own vocabulary rather than accepted into a
        # session that then degrades every cycle.
        "force_limit",
        # Minted by the gateway rather than by this module, like `wrong_side`:
        # the daemon was not reached at all, so nothing was judged and nothing
        # was spent (#97). It lives in the one vocabulary because a Commander
        # reads it in the same place as every other refusal, and because the
        # exported schema is what tells the world which codes exist.
        "port_unavailable",
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
    # How many Squads a side this map's Observation can carry before it stops
    # fitting one `callExtension` return (#101), measured once on first use. A
    # property of the map and the economy, both fixed for a Campaign's life, and
    # the measurement is a binary search over serialisations — so it is measured
    # when the first Purchase asks and not on every one. Held here rather than on
    # the Campaign because it is a fact about the wire, and #78 keeps those out
    # of the aggregate.
    _ceiling: int | None = None
    _ceiling_measured: bool = False

    @property
    def squad_ceiling(self) -> int | None:
        """The measured Squad ceiling for the map this Campaign is played on.

        Not a balance number and nobody's judgement: it is the point at which
        this map's worst-case Observation stops fitting one reply. `None` means
        the map does not fit even with no Squads at all, which `just unit`
        refuses when a map is authored.
        """
        if not self._ceiling_measured:
            self._ceiling = budget.squad_ceiling(self.campaign.map_manifest, self.table)
            self._ceiling_measured = True
        return self._ceiling

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
        # Before anything else, including whose Command this is: a won Campaign
        # is over for both sides, and there is nothing left for a Command to be
        # right or wrong about (#59). The AI Commanders are already stood down;
        # a human still has a map screen up and can still click, so the refusal
        # is typed and says so rather than being an error or a silent no-op.
        if self.campaign.complete:
            return _reject(
                "campaign_over",
                "this Campaign has been won: no further Command is judged against it",
            )

        # The gateway stamps the acting side server-side from its own commander
        # assignment; a Command naming another side is a caller reaching past
        # its authority, not a malformed one.
        if command.side != acting_side:
            return _reject(
                "wrong_side",
                f"{acting_side} may not command for {command.side}",
            )

        handler = HANDLERS.get(command.name)
        if handler is None:
            return _reject("unknown_command", f"no such Command: {command.name!r}")

        return handler(self, command)

    def _purchase(self, command: Command) -> Judgement:
        """Spend Funds to put a new Squad at that side's Base."""
        squad_type = command.args.get("squad_type")
        if not isinstance(squad_type, str) or not squad_type:
            return _reject("malformed_command", "purchase needs a `squad_type`")

        if self.table.sold(squad_type) is None:
            return _reject("malformed_command", f"no Squad type {squad_type!r} is sold")

        refusal = self._check_force(command.side)
        if refusal is not None:
            return refusal

        # Spending the Funds, minting the Squad and telling the world are the
        # campaign's own single change (#60): this decides whether the Command
        # is one the rules will take, and the Campaign decides what happens to
        # itself when it is.
        try:
            squad, remaining = self.campaign.purchase(command.side, squad_type)
        except InsufficientFundsError as exc:
            return _reject("insufficient_funds", str(exc))

        # The id is advisory like the balance, but it is what a Commander needs
        # to order what it has just bought without waiting for an observation.
        return _accept({"squad": squad.id, "funds": remaining})

    def _check_force(self, side: str) -> Judgement | None:
        """Refuse a Purchase that would take a side past what the wire carries.

        ADR-0005 measured the Observation's ceiling and the SQF side logs when a
        reply comes within a tenth of the cap, but nothing stopped a side
        reaching it: Funds were the only question a Purchase was judged on, and a
        long Campaign with hoarded income buys past the ceiling legally. Past it
        the engine truncates the return in silence, `fromJSON` fails, and the
        session degrades every cycle with the cause four hours behind it (#101).

        ADR-0030's budget is checked per map at `just unit` time, and cannot see
        this: Contacts are keyed by place and so grow with the map, while Squads
        grow with play. So the rule lives where the growing happens.

        The number is measured rather than chosen — how many Squads this map's
        worst-case Observation fits — so it is not a balance decision, and a map
        that pays for its own size in Contacts gets a smaller one for free.
        """
        ceiling = self.squad_ceiling
        if ceiling is None:
            return _reject(
                "force_limit",
                f"this map's Observation does not fit one reply even with no Squads: "
                f"{side} cannot buy on it at all",
            )
        held = len(self.campaign.roster.roll(side))
        if held >= ceiling:
            return _reject(
                "force_limit",
                f"{side} has {held} Squads and this map's Observation carries {ceiling}: "
                f"your force is at the limit this wire can carry, so order what you have "
                f"or wait until you have lost a Squad",
            )
        return None

    def _order(self, command: Command) -> Judgement:
        """Give one Squad a standing Order (#14).

        Standing, not a waypoint: the Order is recorded against the Squad and
        the world is told to act on it, so it outlives the leader who was
        carrying it when it arrives. Which ground each kind may name is judged
        here (ADR-0020); recording and announcing it is the Campaign's, so the
        two cannot come apart.
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
        # A read, not a reach: the Squad has to exist before the ground it is
        # being sent to is worth judging, and `issue` below is what changes it.
        if self.campaign.roster.owned_by(squad_id, command.side) is None:
            return _reject("unknown_squad", f"{command.side} has no Squad {squad_id!r}")

        place = command.args.get("place", "")
        refusal = self._ground_refusal(command.side, str(kind), place)
        if refusal is not None:
            return refusal

        order = squads.Order(kind=str(kind), place=str(place))
        squad = self.campaign.issue(squad_id, command.side, order)
        return _accept({"squad": squad.id, "order": order.kind, "place": order.place})

    def _ground_refusal(self, side: str, kind: str, place: object) -> Judgement | None:
        """Return the refusal the Place an Order names earns, or None if it earns none.

        Named for what it returns rather than for the check it performs (#88).
        The family used to be `_check_*` returning `Judgement | None` where None
        meant success, which is an inverted null every docstring had to
        re-explain; a refusal that is absent is the same sentence read forwards.

        An Order names a Place — an Objective or a Base (ADR-0020) — and which
        of the two each kind may name is a rule, so the refusals are typed
        rather than left to the world to discover: `wrong_ground` for ground
        this map has that this Order may not name, `malformed_command` for a
        Place this map does not have at all.
        """
        if kind not in squads.NEEDS_PLACE:
            # Silently dropping a stray Place would hide a UI bug behind an
            # Order that looked accepted and went somewhere else.
            if place:
                return _reject("malformed_command", f"{kind} takes no Place, got {place!r}")
            return None

        named = place if isinstance(place, str) else ""
        owner = self.campaign.holds(named)
        base_side = self.campaign.based(named)
        if owner is None and base_side is None:
            return _reject("malformed_command", f"{kind} needs a Place this map has, got {place!r}")

        if kind == "capture":
            return self._capture_refusal(side, named, owner, base_side)
        if kind == "assault":
            return self._assault_refusal(side, named, owner, base_side)
        return self._defend_refusal(side, named, base_side)

    def _capture_refusal(
        self, side: str, place: str, owner: str | None, base_side: str | None
    ) -> Judgement | None:
        """Capture takes an Objective the side does not hold, and nothing else."""
        if base_side is not None:
            return _reject(
                "wrong_ground",
                f"{place} is a Base, and a Base is never captured: it has no owner by "
                f"presence and dies rather than changing hands, so order Assault to "
                f"destroy the enemy's or Defend to garrison your own",
            )

        # A Capture on ground the side already holds is a nonsensical Order, and
        # accepting it as a no-op would leave a Commander waiting on a Squad
        # that was never going anywhere. The detail says what to do instead.
        if owner == side:
            return _reject(
                "already_held",
                f"{side} already holds {place}: Capture is for ground you do not hold, "
                f"so order Defend to garrison it instead",
            )
        return None

    def _assault_refusal(
        self, side: str, place: str, owner: str | None, base_side: str | None
    ) -> Judgement | None:
        """Assault takes the enemy Base, and nothing else."""
        if owner is not None:
            return _reject(
                "wrong_ground",
                f"{place} is an Objective, and an Objective is captured rather than "
                f"assaulted: order Capture instead",
            )
        if base_side == side:
            return _reject(
                "wrong_ground",
                f"{place} is {side}'s own Base: Assault is for the enemy's, "
                f"so order Defend to garrison your own",
            )
        return None

    def _defend_refusal(self, side: str, place: str, base_side: str | None) -> Judgement | None:
        """Defend takes any Objective, or the side's own Base."""
        if base_side is not None and base_side != side:
            return _reject(
                "wrong_ground",
                f"{place} is {base_side}'s Base, not {side}'s: order Assault to destroy it",
            )
        return None


# One table rather than a dictionary rebuilt on every Command (#90). Below the
# class because it names its methods; unbound, so `submit` passes itself.
HANDLERS: Final[dict[str, Callable[[CommandPort, Command], Judgement]]] = {
    "purchase": CommandPort._purchase,  # noqa: SLF001 — the class's own dispatch table
    "order": CommandPort._order,  # noqa: SLF001 — ditto
}
