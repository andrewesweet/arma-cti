"""Who owns what, and what that pays.

The world reports who is standing where; this decides what it means. The split
follows ADR-0012 — presence is a fact only the game can observe, ownership and
Funds are rules, and rules live in the daemon where they are testable.

Time is an argument rather than a clock reading. The unit is in-game seconds,
which stop when the Play Session does, so income accrues only while a session is
live without anything here having to know what a session is.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from cti_daemon.commands import CONTESTED, NEUTRAL, SIDES, Effect
from cti_daemon.contacts import Contacts
from cti_daemon.observation import DESTROYED, INTACT, PUBLIC, Observation, SquadView
from cti_daemon.squads import Roster, Squad

if TYPE_CHECKING:
    from cti_daemon.contacts import Sighting
    from cti_daemon.economy import EconomyTable, Ledger
    from cti_daemon.manifest import MapManifest
    from cti_daemon.outbox import Outbox
    from cti_daemon.squads import Order


class CampaignOverError(Exception):
    """Something tried to change a Campaign that has already been won.

    Raised rather than returned because it is a caller's mistake rather than a
    Commander's: `complete` is public, the port asks it before it judges
    anything and answers `campaign_over` on the wire, so anything reaching this
    has changed strategic state without asking whether there was still a
    Campaign to change.
    """


# Owner vocabulary and side names come from `commands`, which is where the wire
# schema defines them (#65) — restating them here as fresh literals made the
# rules and the wire two lists nothing held together.

# The two ways a Campaign ends (docs/mvp-scope.md, decided 2026-07-30). There is
# no third, and no draw.
DOMINATION: Final = "domination"
DECAPITATION: Final = "decapitation"


@dataclass(slots=True)
class ObjectiveState:
    """One Objective's owner, and any capture in progress on it."""

    owner: str = NEUTRAL
    # The side currently accumulating a hold, and how long it has held. Reset
    # whenever the ground changes hands or is contested.
    holder: str = ""
    held_seconds: float = 0.0

    def reset_hold(self) -> None:
        """Forget any capture in progress. The two fields always move together."""
        self.holder = ""
        self.held_seconds = 0.0


@dataclass(frozen=True, slots=True)
class Outcome:
    """How a Campaign ended: who won, by which condition, and when."""

    winner: str
    condition: str
    # In-game seconds, the unit every other clock in here is written in.
    at_time: float
    # The Base that fell, for a Decapitation. Empty for a Domination, which is
    # won on ground rather than on a building.
    base: str = ""


@dataclass(slots=True)
class Campaign:
    """The strategic state of one playthrough: ownership and Funds."""

    map_manifest: MapManifest
    table: EconomyTable
    ledger: Ledger
    outbox: Outbox
    # The Squads each side has bought and what each has been told to do (#14).
    # Ownership, Funds and Squads are one playthrough's strategic state, so they
    # sit behind one object rather than three the caller has to keep in step.
    roster: Roster = field(default_factory=Roster)
    # What each side has seen of the other (#28), for the same reason: it is
    # one playthrough's strategic state, and a Commander's picture of the enemy
    # has to be as private as its own roster.
    contacts: Contacts = field(default_factory=Contacts)
    elapsed: float = 0.0
    # How this Campaign ended, or None while it is still being played. Set once
    # and never revised: `docs/mvp-scope.md` resolves a mutual Decapitation by
    # whichever destruction came first, so the first outcome to be reached is
    # the outcome, and a second one arriving in the same report is too late.
    outcome: Outcome | None = None
    _states: dict[str, ObjectiveState] = field(default_factory=dict)
    _hq: dict[str, str] = field(default_factory=dict)
    # The side that currently owns every Objective, and for how long it has. The
    # Domination clock, and it is in memory only on purpose: the timer is not
    # persisted and resets on boot (docs/mvp-scope.md), which a Campaign built
    # rather than loaded gets for nothing.
    _dominant: str = ""
    _dominated_seconds: float = 0.0
    _since_payout: float = 0.0

    def __post_init__(self) -> None:
        """Start every Objective Neutral and every HQ standing, as authored."""
        self._states = {
            objective.id: ObjectiveState() for objective in self.map_manifest.objectives
        }
        self._hq = {base.id: INTACT for base in self.map_manifest.bases}

    def owner(self, objective: str) -> str:
        """Who holds `objective` — a side, Neutral, or Contested."""
        return self._states[objective].owner

    def holds(self, objective: str) -> str | None:
        """Who holds `objective`, or None when this map has no such Objective.

        The forgiving reading of `owner`, for validating a Command that names
        ground: an Objective nobody authored is a Commander's mistake to be
        told about, not an exception to escape the port.
        """
        state = self._states.get(objective)
        return None if state is None else state.owner

    def based(self, place: str) -> str | None:
        """Whose Base `place` is, or None when this map has no such Base.

        The Base-shaped half of `holds`, for the same reason: an Order may now
        name either kind of Place (ADR-0020), so the port has to be able to ask
        which kind it was handed without reaching into the manifest itself.
        """
        for base in self.map_manifest.bases:
            if base.id == place:
                return base.side
        return None

    def owners(self) -> dict[str, str]:
        """Every Objective's owner, for a Commander to reason over."""
        return {name: state.owner for name, state in self._states.items()}

    def headquarters(self) -> dict[str, str]:
        """Every Base's HQ, intact or destroyed.

        Public to both sides like ownership is, and for the same reason: the two
        win conditions are the scoreboard rather than intelligence
        (`docs/mvp-scope.md`), so a side must be able to read that its own HQ has
        fallen and that the enemy's has not.
        """
        return dict(self._hq)

    @property
    def complete(self) -> bool:
        """Whether this Campaign has been won and is no longer being played."""
        return self.outcome is not None

    def raze(self, base: str, *, at_time: float) -> bool:
        """Record that a Base's HQ has been destroyed. True if that is news.

        The world says a building fell; what it costs is decided here, because
        that is a rule (ADR-0012). The side that loses is the side whose Base it
        was, and who brought it down is not asked for: an HQ destroyed by its
        own side's ordnance is still that side's Base gone. Attribution is real
        and the world reports it, but it belongs to the log rather than to this,
        and a rule that took it as an argument would invite somebody to use it.

        Returns False for a Base already down, which is the whole of the
        once-only rule — the world reports rubble as rubble on every report, and
        the *first* report is what settles a mutual Decapitation.
        """
        side = self.based(base)
        if side is None:
            message = f"{base!r} is no Base this map has"
            raise KeyError(message)
        if self._hq[base] == DESTROYED:
            return False
        self._hq[base] = DESTROYED
        loser = side
        winner = next(other for other in SIDES if other != loser)
        self._won(Outcome(winner=winner, condition=DECAPITATION, at_time=at_time, base=base))
        return True

    def _won(self, outcome: Outcome) -> None:
        """Declare an outcome, unless this Campaign already has one.

        Recorded rather than announced, which is the one place this object stops
        short of `objective_captured` beside it. The `campaign_won` effect
        carries the end screen's summary, that summary is read back off
        telemetry (`docs/mvp-scope.md`), and telemetry belongs to the daemon —
        so the daemon pushes it on seeing this appear. A capture has nothing
        outside these rules to add, which is why that one is pushed here.
        """
        if self.complete:
            return
        self.outcome = outcome

    def _playing(self) -> None:
        """Refuse to change a Campaign that has already been won (#60).

        The invariant every mutating verb below shares, stated once. A Command
        arriving after the end screen is refused at the port with a code the
        game knows; anything that got past that and reached the state itself is
        a bug, and this is where it stops rather than where it is discovered.
        """
        # `self.outcome` rather than `complete`, which is the same question:
        # having the Outcome in hand is what lets the refusal say who won.
        if self.outcome is not None:
            message = (
                f"this Campaign was won by {self.outcome.winner} "
                f"by {self.outcome.condition} and takes no further change"
            )
            raise CampaignOverError(message)

    def purchase(self, side: str, squad_type: str) -> tuple[Squad, int]:
        """Spend a side's Funds to put a new Squad in its roster (#60).

        Funds, roster and the world being told are one change rather than three
        a caller keeps in step: a Squad that was paid for and never minted, or
        minted and never announced, is a Campaign disagreeing with itself. What
        it costs and how many men it is are the authored table's answer, so
        nothing outside can buy a Squad at a price of its own.

        The Base is not named on purpose: the daemon owns the rules, the game
        owns the geometry, and the manifest already tells it where each side's
        Base is. Returns the Squad and what the side has left, both advisory.
        """
        self._playing()
        bought = self.table.sold(squad_type)
        if bought is None:
            message = f"no Squad type {squad_type!r} is sold"
            raise KeyError(message)
        # Raises `InsufficientFundsError` on an overdraft, which is the Ledger's
        # own invariant and is left to it.
        remaining = self.ledger.spend(side, bought.price)
        squad = self.roster.add(side, bought.id, bought.size)
        self.outbox.push(
            Effect(
                name="squad_spawned",
                side=side,
                args={"squad": squad.id, "squad_type": bought.id, "size": bought.size},
            )
        )
        return squad, remaining

    def issue(self, squad_id: str, side: str, order: Order) -> Squad:
        """Give one of a side's Squads its standing Order, and tell the world.

        Whether the Order suits the Place it names is the port's rule (ADR-0020)
        and is judged before this is called, as is whether the side has such a
        Squad at all — `roster.of` is the forgiving reading a Commander's
        mistake deserves, and by here the mistake has been made or ruled out.
        What is here is the part that must not come apart: recorded against the
        Squad and announced to the world in one step, so a Squad can never be
        carrying an Order the world was never told about.
        """
        self._playing()
        squad = self.roster.of(squad_id, side)
        if squad is None:
            message = f"{side} has no Squad {squad_id!r} to order"
            raise KeyError(message)
        squad.order = order
        self.outbox.push(
            Effect(
                name="order_issued",
                side=side,
                args={"squad": squad.id, "order": order.kind, "place": order.place},
            )
        )
        return squad

    def reconcile(self, seen: dict[str, tuple[int, str]]) -> tuple[str, ...]:
        """Take the world's account of which Squads exist, and where.

        Ignored rather than refused once the Campaign is won, for the reason
        `observe` ignores a report: the world does not know it is over until the
        effect reaches it, and it goes on saying what it sees in the meantime.
        Returns the Squad ids the world has lost, so a caller can record them.
        """
        if self.complete:
            return ()
        return self.roster.reconcile(seen)

    def sight(
        self,
        side: str,
        *,
        at_time: float,
        seen: tuple[Sighting, ...],
        observed: tuple[str, ...],
    ) -> None:
        """Fold what one side's leaders saw into that side's Contacts (#28).

        Ignored after the end screen for the same reason `reconcile` is: nobody
        is planning off this picture any more, and a Campaign that went on
        rebuilding one would be keeping state past the state it archived.
        """
        if self.complete:
            return
        self.contacts.report(side, at_time=at_time, seen=seen, observed=observed)

    def observation(self, for_side: str = PUBLIC) -> Observation:
        """Assemble the strategic picture `for_side` may know (#15, #27).

        Assembled rather than reported: ownership, Funds and Orders are the
        daemon's own, and only the head count and the ground underfoot came
        from the world. Held nowhere but in memory — persistence is Phase 2.

        Projected rather than filtered on the way out: ADR-0012 runs the planner
        in-process, so a projection applied at the wire is one it never meets.
        This is the only way to obtain an observation, and it never assembles
        one carrying both sides. `PUBLIC` — the default, so the safe answer is
        also the easy one — is ownership alone, which is what the server gets.
        """
        if for_side == PUBLIC:
            return Observation(at_time=self.elapsed, owners=self.owners(), hq=self.headquarters())
        if for_side not in SIDES:
            # In this module's own language rather than the Ledger's: what is
            # missing is a Commander to hand a picture to, and the Ledger's
            # refusal (#66) is about Funds.
            message = f"no side named {for_side!r} has an observation to take"
            raise ValueError(message)
        return Observation(
            at_time=self.elapsed,
            owners=self.owners(),
            hq=self.headquarters(),
            for_side=for_side,
            funds=self.ledger.balance(for_side),
            squads=tuple(
                SquadView(
                    id=squad.id,
                    squad_type=squad.squad_type,
                    size=squad.size,
                    order=squad.order.kind,
                    place=squad.order.place,
                    at=squad.at,
                )
                for squad in self.roster.roll(for_side)
            ),
            # Aged to the moment this is being asked, so a Contact nobody has
            # looked at since grows older rather than vanishing when the
            # engine's own knowledge model forgets it.
            contacts=self.contacts.of(for_side, self.elapsed),
        )

    def observe(self, at_time: float, presence: dict[str, list[str]]) -> list[dict[str, int]]:
        """Take one report of who is standing where, at an in-game time.

        `presence` maps Objective id to the sides inside its capture radius.
        An Objective the report omits is treated as empty, which is what an
        empty radius looks like from the world.

        Returns one entry per income tick the elapsed time covered, so a caller
        can record that Funds moved. Paying in silence would leave the economy
        the one part of the campaign nobody can watch.

        A won Campaign takes no more reports. The world keeps sending them —
        nothing in it knows the Campaign is over until the effect arrives, and
        the reply is still owed — but ground stops changing hands and Funds stop
        moving, because a Campaign that kept playing past its end screen would
        archive a state nobody played to.
        """
        if self.complete:
            return []

        # In-game time restarts at zero when the mission does. A negative
        # interval would claw back Funds already paid, so a step backwards is a
        # new session rather than a refund.
        interval = at_time - self.elapsed
        if interval < 0:
            interval = 0.0
        self.elapsed = at_time

        for name, state in self._states.items():
            self._advance(name, state, presence.get(name, []), interval)

        paid = self._accrue(interval)
        self._dominion(interval)
        return paid

    def _dominion(self, interval: float) -> None:
        """Move the Domination clock on by `interval` seconds.

        One side owning every Objective *simultaneously*, sustained ten in-game
        minutes within one Play Session (`docs/mvp-scope.md`). Sustained is the
        load-bearing word: losing one Objective does not pause the clock, it
        starts it again, or a Campaign could bank nine minutes and cash them a
        quarter of an hour later.

        The interval in which totality was reached is not credited. The moment
        the last Objective changed hands falls somewhere inside it, and crediting
        the whole of it would be counting time the side did not hold the island.
        """
        if not self._states:
            return

        held = {state.owner for state in self._states.values()}
        holder = held.pop() if len(held) == 1 else ""
        if holder not in SIDES:
            holder = ""

        if holder != self._dominant:
            self._dominant = holder
            self._dominated_seconds = 0.0
            return
        if not holder:
            return

        self._dominated_seconds += interval
        if self._dominated_seconds >= self.table.domination_seconds:
            self._won(Outcome(winner=holder, condition=DOMINATION, at_time=self.elapsed))

    def _advance(self, name: str, state: ObjectiveState, sides: list[str], interval: float) -> None:
        """Move one Objective's capture on by `interval` seconds."""
        present = sorted({side for side in sides if side in SIDES})

        if len(present) > 1:
            # Contested is a state, not a moment: it persists until somebody is
            # alone in the radius again, and it pays nobody while it lasts.
            self._set_owner(name, state, CONTESTED)
            state.reset_hold()
            return

        if not present:
            # Ground already taken stays taken; holding it should not require
            # standing on it forever.
            state.reset_hold()
            return

        side = present[0]
        if state.owner == side:
            state.reset_hold()
            return

        if state.holder != side:
            state.holder = side
            state.held_seconds = 0.0
        state.held_seconds += interval

        if state.held_seconds >= self.table.capture_seconds:
            self._set_owner(name, state, side)
            state.reset_hold()

    def _set_owner(self, name: str, state: ObjectiveState, owner: str) -> None:
        """Record a change of hands and tell the world about it."""
        if state.owner == owner:
            return
        state.owner = owner
        self.outbox.push(Effect(name="objective_captured", side=owner, args={"objective": name}))

    def _accrue(self, interval: float) -> list[dict[str, int]]:
        """Pay every income tick the elapsed time covers."""
        paid: list[dict[str, int]] = []
        self._since_payout += interval
        tick = self.table.income_tick_seconds
        while self._since_payout >= tick:
            self._since_payout -= tick
            paid.append(self._pay())
        return paid

    def _pay(self) -> dict[str, int]:
        """One tick: the sum over owned Objectives, plus the flat stipend."""
        income = dict.fromkeys(SIDES, self.table.stipend)
        for objective in self.map_manifest.objectives:
            owner = self._states[objective.id].owner
            # Neutral and Contested Objectives pay nobody.
            if owner in income:
                income[owner] += objective.income
        for side, amount in income.items():
            self.ledger.deposit(side, amount)
        return income
