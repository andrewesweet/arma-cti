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
from cti_daemon.loadouts import Catalogue, Chosen
from cti_daemon.observation import DESTROYED, INTACT, PUBLIC, Observation, SquadView
from cti_daemon.snapshot import Snapshot, SquadRecord
from cti_daemon.squads import Roster, Squad

if TYPE_CHECKING:
    from cti_daemon.squads import Held

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
    # The curated loadout menu this Campaign is played with (#172, ADR-0056),
    # and which kit each player has picked off it. The menu is authored data
    # like the price table; the picks are strategic state the snapshot carries,
    # which is what puts them here rather than in the world. Empty by default,
    # so a Campaign wired without an authored menu offers no kit rather than
    # every kit.
    catalogue: Catalogue = field(default_factory=Catalogue.empty)
    loadouts: Chosen = field(init=False)
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
        # The Ledger's seed is the table's to set (#152). Both arrive as parts
        # of one Campaign, and a Ledger opened at any other figure is two
        # answers to what a side starts with — a wiring bug, not a Campaign to
        # play, so it is refused where the two first meet.
        if self.ledger.starting_funds != self.table.starting_funds:
            message = (
                f"this Campaign's Ledger opened at {self.ledger.starting_funds} Funds "
                f"but its table authors starting_funds of {self.table.starting_funds}"
            )
            raise ValueError(message)
        self._states = {
            objective.id: ObjectiveState() for objective in self.map_manifest.objectives
        }
        self._hq = {base.id: INTACT for base in self.map_manifest.bases}
        # Built against this Campaign's own menu, which is what keeps the
        # persisted vocabulary closed: nothing can be recorded here that the
        # catalogue does not offer. A Phase-2 load replaces the whole record
        # (`Chosen.restore`) rather than filling this one in (#4).
        self.loadouts = Chosen(catalogue=self.catalogue)

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

    def squad(self, squad_id: str, side: str) -> Squad | None:
        """Return `side`'s Squad by that id, or None if it has no such Squad.

        The roster's forgiving read, offered by the root (#152): the port judges
        a Command against the Campaign, so what it may ask, it asks here rather
        than by reaching through to the aggregate's parts. Another side's Squad
        is not found rather than refused separately, for the roster's own
        reason — a Commander has no business learning the enemy's ids by
        guessing.
        """
        return self.roster.owned_by(squad_id, side)

    def squad_count(self, side: str) -> int:
        """How many Squads `side` holds, for rules that cap a force (#152).

        A count rather than the roll itself: the one rule that asks — the
        port's `force_limit` — needs the number, and a caller handed the tuple
        would be back to reading the roster through the root.
        """
        return len(self.roster.roll(side))

    def dress(self, uid: str, kit_id: str) -> bool:
        """Record which kit one player has chosen. False if the menu has no such kit.

        Offered by the root for the reason `squad` is (#152): what the report
        cycle may ask about a Campaign, it asks the Campaign, rather than
        reaching through to the record it holds.

        Not gated on the Campaign still being played, unlike every verb above
        it. A kit moves no ground and no Funds, so there is nothing here for a
        won Campaign to be protected from — and a won Campaign is archived as a
        record rather than resumed (ADR-0023), so nothing reads this afterwards
        either. Refusing it would only mean the world's last report before the
        end screen typed a mismatch that was not one.
        """
        return self.loadouts.choose(uid, kit_id)

    def dressed(self) -> dict[str, str]:
        """Which kit every player has chosen — the set a snapshot writes (#4)."""
        return self.loadouts.serialise()

    def to_snapshot(self) -> Snapshot:
        """Photograph the whole Campaign's strategic state, for both sides (#291).

        The inverse of `apply_snapshot`: every field ADR-0008 carries, read off
        the live object. A fresh `Snapshot` rather than the document a durable
        write would store, so the serialise boundary — not this aggregate — owns
        the on-disk shape, and a save path that goes `to_snapshot` then
        `serialise` is two steps a round-trip test can hold apart.
        """
        return Snapshot(
            clock=self.elapsed,
            owners=self.owners(),
            hq=self.headquarters(),
            funds=self.ledger.holdings(),
            squads=tuple(
                SquadRecord(
                    id=squad.id,
                    side=squad.side,
                    squad_type=squad.squad_type,
                    size=squad.size,
                    order=squad.order,
                    at=squad.at,
                )
                for squad in self.roster.all()
            ),
            loadouts=self.dressed(),
        )

    def apply_snapshot(self, snapshot: Snapshot) -> tuple[str, ...]:
        """Replace the live Campaign's state with a snapshot's (ADR-0003, #291).

        Validate-then-mutate: every fault raises before any field moves, so a
        refused load leaves the live Campaign exactly as it was — the
        load-bearing property ADR-0003 states and the issue's fifth criterion
        pins. A snapshot whose owner or HQ keys name ground this map has not
        authored, or whose Funds name a side this Campaign is not played by, is
        refused as a map mismatch rather than half-applied.

        Tactical state is regenerated, not restored (ADR-0008): every Squad's
        position and `fielded` flag come back blank for the first report after a
        resume to set, contacts are dropped, the Domination clock resets to
        boot, and a resumed Campaign is undecided again. Returns the UIDs whose
        saved kit the menu no longer offers — operational, surfaced so a resume
        names them rather than silently dressing a player back into a default.
        """
        # Map membership first, before anything moves: a snapshot written against
        # a different manifest names ground this one has not authored, and
        # applying half of it before noticing is the half-load durability
        # exists to prevent.
        unknown_owners = sorted(set(snapshot.owners) - set(self._states))
        if unknown_owners:
            message = f"a snapshot names objectives {unknown_owners} that this map has not authored"
            raise ValueError(message)
        unknown_hq = sorted(set(snapshot.hq) - set(self._hq))
        if unknown_hq:
            message = f"a snapshot names bases {unknown_hq} that this map has not authored"
            raise ValueError(message)

        # Raises on a side this Ledger does not play or a negative balance, and
        # is itself validate-before-mutate — so Funds move only once the whole
        # record passed, and nothing above this line has mutated, so this raise
        # leaves the live Campaign untouched too.
        self.ledger.restore(snapshot.funds)

        for name, state in self._states.items():
            state.owner = snapshot.owners.get(name, NEUTRAL)
            state.reset_hold()
        self._hq = {base: snapshot.hq.get(base, INTACT) for base in self._hq}
        self.roster.restore(
            tuple(
                Squad(
                    id=record.id,
                    side=record.side,
                    squad_type=record.squad_type,
                    size=record.size,
                    order=record.order,
                    at=record.at,
                )
                for record in snapshot.squads
            )
        )
        self.loadouts, dropped = Chosen.restore(self.catalogue, snapshot.loadouts)
        self.elapsed = snapshot.clock
        # Tactical, in-memory, regenerated at boot (ADR-0008, docs/mvp-scope.md):
        # a resumed Campaign has held no Objective long enough yet to have won,
        # has no Contacts until the first reports rebuild them, and is undecided.
        self._dominant = ""
        self._dominated_seconds = 0.0
        self._since_payout = 0.0
        self.contacts = Contacts()
        self.outcome = None
        return dropped

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

    def reinforce(self, squad_id: str, side: str) -> tuple[Squad, int, int]:
        """Spend a side's Funds to bring one of its Squads back to strength.

        The same single change `purchase` is (#60), for the same reason: Funds
        deducted, the roster's account of the Squad restored, and the world told
        to put the men there are one change rather than three a caller keeps in
        step — a Squad paid for and never refilled, or refilled and never paid
        for, is a Campaign disagreeing with itself. What it costs is
        the authored table's answer (`reinforce_cost`), so nothing outside can
        refill a Squad at a price of its own.

        Whether this Squad may be reinforced at all — whether it exists, whether
        it is standing at its own Base, whether anybody is missing — is the
        port's rule (ADR-0040) and is judged before this is called.

        Returns the Squad, what the side has left, and what it paid; the last
        two are advisory, like a Purchase's.
        """
        self._playing()
        squad = self.roster.owned_by(squad_id, side)
        if squad is None:
            message = f"{side} has no Squad {squad_id!r} to reinforce"
            raise KeyError(message)
        bought = self.table.sold(squad.squad_type)
        cost = self.table.reinforce_cost(squad.squad_type, self.missing(squad))
        if bought is None or cost is None:
            message = f"no Squad type {squad.squad_type!r} is sold"
            raise KeyError(message)

        remaining = self.ledger.spend(side, cost)
        # The daemon's account of the Squad is what it has paid for; the world's
        # is what is standing, and `reconcile` overwrites this with that on the
        # next report. Left at the old number in between, a Commander would read
        # a Squad he has just paid to refill as still under strength.
        squad.size = bought.size
        self.outbox.push(
            Effect(
                name="squad_reinforced",
                side=side,
                args={"squad": squad.id, "size": bought.size},
            )
        )
        return squad, remaining, cost

    def missing(self, squad: Squad) -> int:
        """How many men that Squad is short of what it was bought as.

        Zero for a Squad at strength, and for one the authored table no longer
        sells — the second is a fault the port reports rather than a Squad
        nobody may refill, and this is not the place that decides which.
        """
        bought = self.table.sold(squad.squad_type)
        if bought is None:
            return 0
        return max(0, bought.size - squad.size)

    def issue(self, squad_id: str, side: str, order: Order) -> Squad:
        """Give one of a side's Squads its standing Order, and tell the world.

        Whether the Order suits the Place it names is the port's rule (ADR-0020)
        and is judged before this is called, as is whether the side has such a
        Squad at all — `roster.owned_by` is the forgiving reading a Commander's
        mistake deserves, and by here the mistake has been made or ruled out.
        What is here is the part that must not come apart: recorded against the
        Squad and announced to the world in one step, so a Squad can never be
        carrying an Order the world was never told about.
        """
        self._playing()
        squad = self.roster.owned_by(squad_id, side)
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

    def reconcile(self, seen: dict[str, Held]) -> tuple[str, ...]:
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
                    pos=squad.pos,
                )
                for squad in self.roster.roll(for_side)
            ),
            # Aged to the moment this is being asked, so a Contact nobody has
            # looked at since grows older rather than vanishing when the
            # engine's own knowledge model forgets it.
            contacts=self.contacts.aged_to(for_side, self.elapsed),
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
            self._advance_capture(name, state, presence.get(name, []), interval)

        paid = self._accrue(interval)
        self._advance_domination(interval)
        return paid

    def _advance_domination(self, interval: float) -> None:
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

    def _advance_capture(
        self, name: str, state: ObjectiveState, sides: list[str], interval: float
    ) -> None:
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
