"""The AI Commander's brain: what to Purchase, and where to send what it has.

ADR-0004 puts the planner in the daemon as a pure function of campaign state and
observations, so pytest and hypothesis exercise it at millisecond speed with no
Arma anywhere. Purity is meant literally: `plan` reads one Observation and the
authored data this object was built from, touches nothing else, and hands back
the Commands it would issue together with the trace explaining them. Writing that
trace is the daemon's job — a function that logs is no longer a pure one.

It plans under the same fog a human Commander does (ADR-0012). An Observation is
the only input there is, and no unprojected one exists to reach for, so this
cannot read the enemy's order of battle even by accident. What it knows of the
enemy is Contacts: banded, aged, and only where somebody looked.

**It does not read `SquadView.pos`, and that is decided rather than overlooked**
(#175 ruling 2, human, 2026-08-04; ADR-0058). The field carries a Squad's map
position in metres, so that a human Commander can see his own Squads while they
are on the march; this keeps reasoning in Places, because every term it has —
adjacency, Contacts, garrisons, the Assault mass table — is keyed on one.

`_options` is where the shape of the omission is visible: a Squad in open ground
has no Place, so its march is priced from the Base it was bought at rather than
from where it has actually got to. That understates a Squad half way to a town
and overstates one that has turned round, and correcting it is a real planner
change with consequences to weigh rather than a line to add here quietly — it
travels as post-MVP Commander work (#173, and the #177 prototype may pull it
in). Until then this reads `at` and ignores `pos`, deliberately.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from math import hypot
from typing import TYPE_CHECKING, Final, Protocol

import networkx as nx

from cti_daemon import budget
from cti_daemon.commands import CONTESTED, Command
from cti_daemon.observation import PUBLIC

if TYPE_CHECKING:
    from cti_daemon.contacts import Contact
    from cti_daemon.economy import EconomyTable
    from cti_daemon.manifest import MapManifest
    from cti_daemon.observation import Observation, SquadView

# How many candidates a decision carries into telemetry. The winner is first by
# construction, so what is dropped is also-rans — and `Decision.scored` says how
# many there were, because a silent cap reads as "everything was considered".
TRACE_CANDIDATES: Final = 5

# What a Contact's echelon band counts for, in teams. A band rather than a count
# is all a Commander gets (`CONTEXT.md`), so this is the whole of what the scorer
# can know about how hard a place will be.
ECHELON_THREAT: Final = {"team": 1.0, "squad": 2.0, "platoon": 4.0, "company": 8.0}

# What ground nobody is looking at is assumed to hold. Never zero, and that is
# the point: absence of a Contact is not absence of the enemy, so unknown ground
# is scored as a team standing on it rather than as empty. A stale Contact decays
# towards this floor rather than towards nothing, so old knowledge becomes
# ignorance instead of becoming good news.
UNKNOWN_THREAT: Final = 1.0

# How many Squads an Assault on a Base must bring, read off the Contact standing
# on it (#38, ADR-0027). This is the whole threat model, and it is a doctrine
# table keyed on the **band** rather than a force computed from a count: a
# Contact carries no count and #28 made sure none can be recovered, so a rule
# that divided men by eight would be inventing the one number the fog exists to
# withhold. A band in, a number of our own Squads out — nothing about the enemy
# is learned in between.
#
# It is deliberately not `ECHELON_THREAT`. That is a price in teams, paid by the
# `threat` weight and decayed by age; this is a size, and neither the weights nor
# the clock touch it. One term could not carry both, which is what ADR-0020 said
# the escalation would be.
#
# Playtest-tuned placeholders, flagged for gameplay-feel sign-off (#38). The
# bands' floors are 1, 4, 9 and 25 observed men (`contacts.ECHELONS`) and a
# Squad is eight, so these run from comfortable at a band's floor to thin at its
# top — on purpose. The map fields eight Squads (one per Objective), so a table
# that demanded parity with a company would spend the whole force on one raid
# and concede Domination to buy Decapitation. Measured on Stratis from a held
# island against a fresh company, 200 seeds: at nine the raid is never assembled
# at all and one sighting vetoes a win condition permanently; at eight it is
# assembled by emptying the island, no Objective garrisoned on any seed; at four
# half the force raids and half stays, on every seed. Below four it arrives at
# parity with the band's floor — twenty-four men against the twenty-five-plus
# that banded as a company, which is #35's eight into twenty-four at a larger
# scale, and the one end of this window that is extrapolated rather than
# measured. ADR-0027 carries the reasoning and the sign-off flag.
ASSAULT_MASS: Final = {"team": 1, "squad": 2, "platoon": 3, "company": 4}

# The heaviest a Contact can read, in the units of `ECHELON_THREAT`. It is the
# far bookend of both threat curves: a company is the most enemy the register
# can report, so it is what "as bad as it gets" means to this scorer.
WORST_THREAT: Final = ECHELON_THREAT["company"]

# Every consideration an option is scored on, in the order they are evaluated
# (ADR-0031). Cheap first, because the product early-outs on the first zero and
# `legal` is a dict lookup — half the option space dies on it every cycle.
#
# Lewis's three classes (Game AI Pro 3 ch.13), which is the vocabulary this
# scorer is now built in:
#
# - **mandatory** — a zero here vetoes the option outright. `legal` is the
#   port's refusal matrix (ADR-0020) scored rather than assumed. `worth` and
#   `proximity` reach zero too, at a Place that pays nothing and at a march
#   longer than `reach_km`; both are real vetoes rather than decoration, and
#   neither is reachable on Stratis.
# - **distinguishing** — separates options that are all viable. `worth`,
#   `proximity`, `hold` and `danger` are what actually decide a cycle.
# - **balance/feel** — small, shapes character without deciding. `momentum` and
#   `flavour`, and they are deliberately the only two: a scorer whose axes are
#   *all* balance/feel has nothing to gate with, which is the failure Lewis
#   names and the one #34's single stretched term was.
#
# The count is fixed, and that is load-bearing rather than tidy: every option
# carries every consideration, at 1.0 where the kind makes it inapplicable, so
# the compensation factor below is the same monotone map on all of them and
# cannot reorder anything.
CONSIDERATIONS: Final = (
    "legal",
    "worth",
    "unfinished",
    "momentum",
    "flavour",
    "proximity",
    "hold",
    "danger",
)


def _compensated(product: float) -> float:
    """Lift a product of many considerations back into a legible range.

    Lewis's compensation-factor problem: multiplying N normalised considerations
    drives every score toward zero, and eight of them put a good option at 0.3
    where an argument about it wants a number that reads like a preference. The
    fix that circulates is `final = s + (1 - s) * (1 - 1/N) * s`, and #48 could
    not trace it to a Mark or Lewis primary — so it is adopted on its algebra
    and on nothing else.

    The algebra is this: for a fixed `N` the map is strictly increasing on
    [0, 1], so it **cannot change which option wins**, only how far apart the
    scores read. That is the whole of what it is being used for here, and
    `test_the_compensation_factor_cannot_change_which_option_wins` is the proof
    rather than the claim. It stops being free the day the consideration set
    stops being fixed per option, because then two options are compensated by
    different amounts and the transform starts deciding things; the count is
    fixed above so that day is a deliberate change rather than a drift.
    """
    if product <= 0.0:
        return 0.0
    return product + (1.0 - product) * (1.0 - 1.0 / len(CONSIDERATIONS)) * product


@dataclass(frozen=True, slots=True)
class Considerations:
    """The bookends and response curves the scorer weighs an option through.

    ADR-0031 replaced ADR-0014's eight summed weights with this. What it keeps
    is every call ADR-0014 made; what it changes is the shape they are made in —
    each consideration is normalised to [0, 1] by a bookend, remapped by an
    authored curve, and multiplied, so a zero vetoes and a curve can be flat
    where a weight had to be linear.

    Tuned for a Commander that presses (human decision, 2026-07-31): two sides
    both sitting on what they hold is not a Campaign worth playing, so the
    default here advances by preference and consolidates only against a real
    massed incursion.

    Three relations are load-bearing rather than tuning, and they are ADR-0014's
    first call and its consequences restated in the new units. `flavour` spans
    less than `reach_km` gives back over three hundred metres, so the seed can
    only decide between options geography has already tied — it never sends a
    Squad the long way round. `momentum` is larger than the whole span of
    `flavour`, so the anti-thrash margin still covers what the seed can move.
    And `hold_floor` is below one, so taking ground beats sitting on it while
    there is ground left to take.
    """

    # How far a march has to be before distance alone has taken everything off
    # a Place. Linear, which is Lewis's published `(100 - d) / 100` in
    # kilometres, and the bookend is set so a kilometre costs a tenth of a
    # full-value Place — ADR-0014's `travel = 1.0` against `income = 10.0`,
    # exactly. This is still the main aggression dial: halve it and the far half
    # of the island stops being worth walking to.
    #
    # Stratis's graph diameter is about five kilometres, so the veto at the far
    # end is unreachable there. On an island wider than this it would fire, and
    # the fix is the bookend rather than a clamp somewhere else.
    reach_km: float = 10.0
    # What ground that is *not* half-taken is worth against ground that is. A
    # product can only discount, so ADR-0014's `contested = 6.0` bonus on an
    # income of 10 is expressed as its absence: 10/16 for everything else.
    unfinished_floor: float = 0.625
    # What standing on quiet ground is worth against taking it — ADR-0014's
    # `garrison = 0.1`, unmoved, and now the floor of a curve rather than a
    # multiplier of income. It is the whole value of a Defend nobody is coming
    # for, so what it actually sets is advance against consolidate: at 0.1 the
    # Squad that takes Agia Marina marches on to LZ Baldy and at 1.0 it stays.
    hold_floor: float = 0.1
    # And how fast a garrison becomes urgent as the Contact on it grows, from
    # that floor to the Place's whole value at a company. Squared rather than
    # linear so the fog floor barely registers and only a real massed incursion
    # turns a Squad round: the crossing point sits at about seven teams, which
    # is between a platoon and a company and nearer the company.
    hold_power: float = 2.0
    # What a company standing on ground takes off the value of attacking it —
    # ADR-0014's `threat = 0.5` per team, eight teams, against an income of 10.
    # Bounded below by construction at 1 - danger_bite, so heavy ground is
    # attacked later than light ground rather than never: this Commander presses.
    danger_bite: float = 0.4
    # And the shape of getting there. Squared, which is #48's "flat until a
    # platoon and collapses at a company": a team costs six thousandths and a
    # company costs the whole bite. A linear term had to charge for the fog
    # floor on every option on the map, which is a cost that decides nothing.
    danger_power: float = 2.0
    # What a standing Order is worth on its own. The whole anti-thrash rule: a
    # Squad keeps going where it was sent unless something beats it by this
    # much, so scores that drift around each other do not turn into
    # countermarching. ADR-0014's `commitment = 2.0` against an income of 10.
    #
    # It is a flat step rather than Lewis's `runtime` curve (`y = 1 - x⁶`,
    # decaying a decision the longer it has been running) because a runtime
    # curve needs the age of the standing Order and `SquadView` does not carry
    # one. That is the degenerate case of the curve, not a rejection of it, and
    # the field is where the curve would go.
    momentum: float = 0.2
    # A fixed per-place preference, so two identical Objectives at equal
    # distance are not decided by alphabetical order and a Campaign has a
    # character. The whole span of it, and `flavour * reach_km` is what it is
    # worth in kilometres of march: three hundred metres, ADR-0014's first call.
    flavour: float = 0.03
    # What taking the enemy's Base is worth, in the units every other value is
    # priced in — an Objective's authored income. ADR-0020's term, unmoved at
    # 8.0, and still a playtest-tuned placeholder flagged for feel sign-off.
    # A little under what an Objective pays, which is why the raid arrives late
    # without any rule saying so: what defers it is the 4.7 km between the Bases.
    decapitation: float = 8.0
    # And what keeping our own is worth. New in ADR-0031, and new because the
    # summed scorer had been getting it for free: what a Base was worth to hold
    # was `garrison * decapitation` — 0.8 — plus a `defend * threat` term of 8.0
    # that had nothing to do with the Base at all. A product cannot smuggle a
    # value in through a threat term, so the value has to be said out loud.
    #
    # Measured on Stratis over 200 seeds, where every Objective pays ten. Below
    # 9.087 a fresh company standing on our own Base no longer outbids marching
    # on, and the Commander walks away from its HQ at exactly the moment
    # somebody came for it. Above 27.959 a platoon is enough to stop the
    # advance, which is the Commander that turns round for every sighting.
    #
    # Ten sits near the low end on purpose rather than in the middle, and the
    # reason is a coupling worth knowing about: `worth` is normalised by the
    # richest thing on the map, so while `homeland` is at or under the best
    # Objective's income it raises the Base alone, and past that it is the
    # ceiling — every other Place's `worth` starts shrinking to make room. Above
    # ten this stops being a dial on the HQ and becomes a dial on everything
    # else wearing the HQ's name. Ten is the last value where it means what it
    # says.
    homeland: float = 10.0
    # How long a Contact takes to decay from what it said to knowing nothing.
    stale_seconds: float = 300.0


@dataclass(frozen=True, slots=True)
class _Option:
    """One thing one Squad could be doing, and what the scorer makes of it."""

    squad: str
    kind: str
    place: str
    score: float
    terms: dict[str, float]

    @property
    def choice(self) -> str:
        """The Order this option stands for, as the trace names it."""
        return f"{self.kind} {self.place}"


@dataclass(frozen=True, slots=True)
class _Prospect:
    """What one Place offers one Order kind, before the Squad going there."""

    # Whether the port would accept this kind of Order on this Place at all —
    # the mandatory consideration, and the only thing computed before the veto.
    legal: bool
    # What the Place is worth, in the units every value is priced in: an
    # Objective's authored income.
    value: float
    contested: bool
    # How much enemy it is assumed to hold, in teams.
    threat: float


@dataclass(frozen=True, slots=True)
class _Demand:
    """What one enemy Base's Assault must arrive with, and where the number came from.

    Two sources rather than one since #181, and kept apart because the trace
    has to say which one bound: what the Contact's band demands (ADR-0027), and
    what the Commander has already committed.
    """

    # What the band demands — the fog floor's one Squad when nothing is
    # reported. This half may move every cycle, because the picture does.
    banded: int
    # Our own Squads already standing under an Assault on this Base. The
    # commitment hysteresis (#181, human ruling on #177, 2026-08-04): a demand
    # re-derived from the picture alone shed a committed Squad twenty seconds
    # after ordering it, because the picture flickers and a commitment must not.
    committed: int

    @property
    def needed(self) -> int:
        """The force the Assault must arrive with — or, once sent, keep."""
        return max(self.banded, self.committed)


@dataclass(frozen=True, slots=True)
class _Refill:
    """One understrength Squad standing at its own Base, and what a refill costs.

    The port's Reinforce preconditions read forwards (#150, ADR-0040), the way
    `legal` reads the refusal matrix for Orders: a record exists only for a
    Squad the port would accept a Reinforce for right now.
    """

    squad: str
    # How many men short of the strength it was bought at — the port's own
    # `missing`, read from the same roster numbers the Observation carries.
    missing: int
    # The discounted pro-rata price (`EconomyTable.reinforce_cost`).
    cost: int


@dataclass(frozen=True, slots=True)
class _Fill:
    """One player-led shell standing at its own Base, and what filling it costs.

    The composition-carrying Reinforce's preconditions read forwards, the way
    `_Refill` beside it reads the ordinary Reinforce's (ADR-0070 ruling 2): a
    record exists only for a shell the port would accept a first fill for right
    now, at the composition named here.
    """

    squad: str
    # The composition the Commander's demand names — the one a Purchase would
    # have bought, on the same cheapest-affordable rule `_spend` applies to one.
    squad_type: str
    # What filling it costs: the missing fraction of that composition's price at
    # the ordinary Reinforce discount (ADR-0070 ruling 3), which is why
    # preferring a shell is the cheaper route as well as the ruled one.
    cost: int


@dataclass(frozen=True, slots=True)
class _Muster:
    """Who is going where this cycle, and what became of each Assault."""

    # Squad id to the option it was given.
    taken: dict[str, _Option]
    # Bases whose Assault was called off for want of mass, so no Squad may be
    # sent to one even as a fallback.
    declined: frozenset[str]
    # Base id to the number of Squads that could be found for it, whether or not
    # that was enough. Only for Bases whose Assault was sought at all.
    spared: dict[str, int]
    # Squad id to how many of its options a mandatory consideration refused
    # before anything weighed them (ADR-0031).
    vetoed: dict[str, int]


@dataclass(frozen=True, slots=True)
class Candidate:
    """One option the scorer weighed, and what it was worth."""

    choice: str
    score: float
    terms: dict[str, float]


@dataclass(frozen=True, slots=True)
class Decision:
    """One thing the planner decided, and enough of why to argue with it."""

    about: str
    chose: str
    because: str
    # How many candidates were scored, against the few `candidates` carries.
    scored: int
    candidates: tuple[Candidate, ...]
    # And how many never got that far, because a mandatory consideration vetoed
    # them (ADR-0031). Separate from `scored` because the two answer different
    # questions: `scored` is how much choice the Commander had, and this is how
    # much of the option space it was never allowed. Defaulted, so a planner
    # that is not this one — the daemon knows only the `Planner` protocol — does
    # not have to have an opinion about vetoes.
    vetoed: int = 0


@dataclass(frozen=True, slots=True)
class Plan:
    """What a Commander would do this cycle, and the trace of deciding it."""

    commands: tuple[Command, ...]
    decisions: tuple[Decision, ...]


class Planner(Protocol):
    """What the daemon asks of a Commander's brain, and all it asks.

    One Observation in, one Plan out. The scorer below is one implementation of
    it; ADR-0004 names HTN as the escalation path and an LLM Commander as a
    post-MVP experiment, and neither changes this signature, the Commands a Plan
    carries, or the shape of the trace beside them. The daemon knows this and
    nothing narrower, so swapping the brain touches no port and no trace reader.
    """

    def plan(self, observation: Observation) -> Plan:
        """Decide what this Commander does with the picture it has."""
        ...


@dataclass(slots=True)
class UtilityPlanner:
    """A seeded deterministic utility scorer over the Objective graph.

    Holds authored data and a seed, never campaign state: everything that moves
    arrives as the Observation argument, so two calls with the same Observation
    return the same Plan and `plan` is a pure function in the sense ADR-0004
    asks for.

    It plays for both win conditions. ADR-0020 widened an Order to name a Place,
    so both Bases are candidates here alongside the Objectives: the enemy's as
    an Assault worth `decapitation`, its own as a Defend under the same fog floor
    every other piece of held ground gets. No new geometry was needed for either
    — the adjacency graph already carried both Bases as nodes with authored
    distances — and no existing weight moved to make room (ADR-0014 stands).

    It also judges *how much* force a Base needs (ADR-0027). That judgement is
    an assignment rule rather than a score: what the Contact's band demands is a
    number of Squads (`ASSAULT_MASS`), the Assault gets all of them or none, and
    a Base that cannot be given its mass is one no Squad walks onto. Since #181
    that demand is floored by the force already standing under the Assault — a
    committed assault carries hysteresis (`_mass`), so a flickering picture may
    raise what an Assault brings and never shed what it sent. Deliberately
    not a weight — a term that made a defended Base merely expensive would still
    send the one Squad that could most afford the trip, which is exactly the
    Squad that dies there. It stays out of the scorer under ADR-0031 too: the
    obvious thing to do with a veto is to make an unmassable Base score zero,
    and that is the one thing ADR-0027 rules out, because a veto still only
    decides *whether* a Squad goes and never *how many*.

    Scoring is multiplicative (ADR-0031): every option is a product of the
    normalised considerations in `CONSIDERATIONS`, each remapped by an authored
    response curve, so a zero on a mandatory consideration vetoes the option
    outright and the cheap ones are evaluated first.

    It Reinforces as well as Purchases (#150, human ruling 2026-08-04; #191): an
    understrength Squad standing at its own Base is refilled when a fresh Squad
    is off the table — the wire's force limit, the map's one-Squad-per-Objective
    cap, or a purse no fresh Squad fits — or when the discounted pro-rata refill
    undercuts the fresh Squad the planner would otherwise buy. The choice lives
    in `_spend` beside the Purchase it competes with, deliberately not in
    `CONSIDERATIONS`: that tuple scores Orders, and its fixed count is what the
    compensation factor's rank-preservation proof rests on. If #136 grows a
    spending-consideration framework, this choice migrates into it (the ruling
    says so) rather than living beside it.

    And it prefers an eligible player-led shell to a net-new Purchase (ADR-0070
    ruling 2, #311). An allocation priority rather than a new economic axis: the
    strategic decision of *when* a composition is needed is the same decision a
    Purchase is and is unchanged, so the choice above is resolved first and the
    shell only takes the place of a Purchase that had already won. It lives in
    `_spend` for the reason the refill does, and the ADR names a shell
    preference that could only be written as a ninth consideration as one of the
    things that would reopen where the choice lives.
    """

    map_manifest: MapManifest
    table: EconomyTable
    # Fixed per Campaign, and an argument rather than a clock reading: the same
    # seed and the same observations must produce the same Orders. Phase 2 puts
    # it in the snapshot, so a resumed Campaign keeps its character.
    seed: int = 0
    considerations: Considerations = Considerations()
    _base_of: dict[str, str] = field(init=False, default_factory=dict)
    _reach: dict[str, dict[str, float]] = field(init=False, default_factory=dict)
    _jitter: dict[str, float] = field(init=False, default_factory=dict)
    _ceiling: float = field(init=False, default=1.0)
    # The wire's Squad ceiling, measured lazily like the port's own (#150): a
    # binary search over serialisations is not `__post_init__` money, and the
    # common boards never ask — the map's own cap is checked first and is
    # usually the one that binds.
    _force_limit: int | None = field(init=False, default=None)
    _force_limit_measured: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        """Derive what the authored data implies, once.

        Distances are kilometres along the adjacency graph rather than hops on
        it. Hops was the first reading of "over the Objective adjacency graph"
        and the world disagreed with it: both Objectives the WEST Base touches
        are one hop away and pay the same, so the seed picked between a 1,076 m
        march and a 2,065 m one and picked wrong — measured in
        `spike/probes/ai-commander.sqf`. Weighting the edges by the length the
        manifest already authored is still the same graph, and it is the
        difference between a Squad arriving in nine minutes and in seventeen.
        """
        self._base_of = {base.side: base.id for base in self.map_manifest.bases}
        where = {place.id: place.position for place in self.map_manifest.objectives}
        where |= {base.id: base.position for base in self.map_manifest.bases}

        graph = nx.Graph()
        for place, neighbours in self._adjacency().items():
            graph.add_node(place)
            for other in neighbours:
                (east, north), (other_east, other_north) = where[place], where[other]
                graph.add_edge(
                    place, other, km=hypot(east - other_east, north - other_north) / 1_000
                )
        # The manifest refuses a graph with a stranded Objective, so every pair
        # of places has a distance and none of this has to cope with infinity.
        self._reach = dict(nx.all_pairs_dijkstra_path_length(graph, weight="km"))
        self._jitter = {place: _stable_fraction(self.seed, place) for place in graph}
        # The near bookend of `worth`: the most anything on this map is worth,
        # so the richest Place scores 1.0 and everything else is a fraction of
        # it. Derived rather than authored, because it has to move with the
        # manifest — a map whose Objectives paid a hundred would otherwise score
        # every Place at the ceiling and the value axis would stop deciding.
        self._ceiling = max(
            [objective.income for objective in self.map_manifest.objectives]
            + [self.considerations.decapitation, self.considerations.homeland]
        )

    def _adjacency(self) -> dict[str, tuple[str, ...]]:
        """Return what each authored place touches.

        A Base names its neighbouring Objectives and an Objective does not name
        the Base back, so the graph is built from both sides of that and comes
        out undirected either way.
        """
        edges: dict[str, tuple[str, ...]] = {
            objective.id: objective.adjacent for objective in self.map_manifest.objectives
        }
        edges |= {base.id: base.adjacent for base in self.map_manifest.bases}
        return edges

    def plan(self, observation: Observation) -> Plan:
        """Decide what this Commander does with the picture it has."""
        if observation.for_side == PUBLIC:
            message = "a planner needs a Commander's picture, not the public one"
            raise ValueError(message)
        if observation.for_side not in self._base_of:
            message = f"no side named {observation.for_side!r} has a Base to command from"
            raise ValueError(message)

        spending, spent_because = self._spend(observation)
        deploying, deployed_because = self._deploy(observation)
        return Plan(
            commands=(*spending, *deploying),
            decisions=(*spent_because, *deployed_because),
        )

    def _deploy(self, observation: Observation) -> tuple[list[Command], list[Decision]]:
        """Give every Squad the best thing left for it to be doing.

        Returns what it decided rather than appending into lists the caller
        passed down (#90): output arguments were the one Clean Code smell in
        this module, and `plan` concatenating two answers says the same thing
        with nothing to keep in step.
        """
        commands: list[Command] = []
        decisions: list[Decision] = []
        # Every Squad is scored against the whole option space — both kinds at
        # every Place — and the vetoed half is dropped here rather than never
        # generated (ADR-0031). What it is dropped *by* is the port's own
        # refusal matrix read as a mandatory consideration, so the scorer states
        # the rule it used to obey silently. The count survives into the trace.
        weighed = {squad.id: self._options(observation, squad) for squad in observation.squads}
        vetoed = {
            squad: sum(1 for option in options if option.score <= 0.0)
            for squad, options in weighed.items()
        }
        options = sorted(
            (option for options in weighed.values() for option in options if option.score > 0.0),
            key=lambda option: (-option.score, option.squad, option.place),
        )
        wanted = self._mass(observation)
        muster = self._muster(options, wanted, vetoed)
        declined = muster.declined
        decisions.extend(self._mustered(observation, wanted, muster))

        for squad in observation.squads:
            mine = [option for option in options if option.squad == squad.id]
            if not mine:
                continue
            # Every Squad gets its own place while there are places, and the
            # scorer Purchases up to one per Objective so there normally are. A
            # Squad past that — one a human has also been Purchasing for — takes its own
            # best option and shares the ground. Never a declined Assault: the
            # whole point of declining is that no Squad walks onto that Base, and
            # a fallback that ignored it would send the loneliest one of all.
            chosen = muster.taken.get(squad.id) or next(
                option for option in mine if option.place not in declined
            )
            decisions.append(self._why(squad, chosen, mine, muster))
            if (chosen.kind, chosen.place) == (squad.order, squad.place):
                continue
            commands.append(
                Command(
                    name="order",
                    side=observation.for_side,
                    args={"squad": squad.id, "order": chosen.kind, "place": chosen.place},
                )
            )
        return commands, decisions

    def _options(self, observation: Observation, squad: SquadView) -> list[_Option]:
        """Score everything this one Squad could be sent to do.

        Both kinds at every Place, and the illegal one is scored to zero rather
        than left ungenerated (ADR-0031). Which kind a Place takes is the port's
        refusal matrix read forwards (ADR-0020) — Capture for ground the side
        does not hold, Defend for ground it does, Assault for the enemy's Base —
        and making the scorer say so out loud is what gives the mandatory class
        something to do: half the space dies on `legal` every cycle, and the
        never-rejected property run through the real `CommandPort` is the
        evidence that the rule the scorer states is the rule the port enforces.
        """
        side = observation.for_side
        # A Squad in open ground is between places and has no distance of its
        # own, so it is measured from the Base it was bought at.
        origin = squad.at if squad.at in self._reach else self._base_of[side]
        watched = {other.at for other in observation.squads if other.at}
        contacts = {contact.at: contact for contact in observation.contacts}

        options = []
        for objective in self.map_manifest.objectives:
            owner = observation.owners.get(objective.id, "")
            threat = self._threat(contacts.get(objective.id), watched=objective.id in watched)
            for kind, legal in (("capture", owner != side), ("defend", owner == side)):
                offer = _Prospect(
                    legal=legal,
                    value=float(objective.income),
                    contested=owner == CONTESTED,
                    threat=threat,
                )
                options.append(self._weigh(squad, kind, objective.id, origin, offer))

        for base in self.map_manifest.bases:
            # The one place whose loss ends the Campaign, on either side of it.
            # Taking the enemy's is worth `decapitation`; keeping ours is worth
            # `homeland`, which the summed scorer never had to name because a
            # threat term was quietly carrying it (ADR-0031).
            threat = self._threat(contacts.get(base.id), watched=base.id in watched)
            ours = base.side == side
            for kind, legal, value in (
                ("assault", not ours, self.considerations.decapitation),
                ("defend", ours, self.considerations.homeland),
            ):
                offer = _Prospect(legal=legal, value=value, contested=False, threat=threat)
                options.append(self._weigh(squad, kind, base.id, origin, offer))
        return options

    def _weigh(
        self, squad: SquadView, kind: str, place: str, origin: str, offer: _Prospect
    ) -> _Option:
        """Run one option through every consideration and multiply them out."""
        shape = self.considerations
        factors: dict[str, float] = {"legal": 1.0 if offer.legal else 0.0}
        if offer.legal:
            factors["worth"] = min(1.0, offer.value / self._ceiling)
            # A product can only discount, so "ground half-taken is worth
            # finishing" is expressed as the discount everything else takes.
            factors["unfinished"] = 1.0 if offer.contested else shape.unfinished_floor
            standing = (kind, place) == (squad.order, squad.place)
            factors["momentum"] = 1.0 if standing else 1.0 - shape.momentum
            factors["flavour"] = 1.0 - shape.flavour * self._jitter[place]
            factors["proximity"] = max(0.0, 1.0 - self._reach[origin][place] / shape.reach_km)
            # The same Contact, read the two opposite ways it has always been
            # read: a reason to stand on ground you hold, a reason to stay off
            # ground you do not. One curve each rather than one signed weight,
            # which is what lets the two have different shapes.
            factors["hold"] = self._hold(offer.threat) if kind == "defend" else 1.0
            factors["danger"] = self._danger(offer.threat) if kind != "defend" else 1.0

        product = 1.0
        for factor in factors.values():
            product *= factor
            if product == 0.0:
                break
        return _Option(
            squad=squad.id, kind=kind, place=place, score=_compensated(product), terms=factors
        )

    def _hold(self, threat: float) -> float:
        """Return what standing on ground we hold is worth, against taking it.

        `hold_floor` when nobody is coming — ADR-0014's `garrison`, which is
        what made quiet held ground worth a tenth of fresh ground — rising to
        the Place's whole value at a company. Squared, so the fog floor barely
        registers and a Commander told to press does not turn round for a team.
        """
        shape = self.considerations
        return shape.hold_floor + (1.0 - shape.hold_floor) * (threat / WORST_THREAT) ** (
            shape.hold_power
        )

    def _danger(self, threat: float) -> float:
        """Return what a Contact takes off the value of going at the ground it stands on.

        Never to zero: `1 - danger_bite` is the floor, so heavy ground is
        attacked later than light ground rather than never. That is ADR-0014's
        `threat` weight's whole point kept intact — the thing that would make a
        company ground this Commander will not go near is `danger_bite` at 1.0,
        and it is at 0.4.
        """
        shape = self.considerations
        return 1.0 - shape.danger_bite * (threat / WORST_THREAT) ** shape.danger_power

    def _threat(self, contact: Contact | None, *, watched: bool) -> float:
        """How much enemy a place is assumed to hold, in teams."""
        # Ground one of ours is standing on is ground being looked at, so no
        # Contact there means empty. Anywhere else, no Contact means unknown.
        floor = 0.0 if watched else UNKNOWN_THREAT
        if contact is None:
            return floor
        freshness = max(0.0, 1.0 - contact.age / self.considerations.stale_seconds)
        return max(floor, ECHELON_THREAT.get(contact.echelon, UNKNOWN_THREAT) * freshness)

    def _mass(self, observation: Observation) -> dict[str, _Demand]:
        """How many Squads an Assault on each enemy Base has to arrive with.

        The threat model (ADR-0027), floored by the commitment (#181). The
        banded half reads the band and only the band: `ASSAULT_MASS` is a
        doctrine table, so nothing here divides, multiplies or otherwise
        reconstructs the count #28 withheld.

        Age is read nowhere in this method, and that is the decision rather than
        an omission. A Contact's age already discounts what the place *costs*
        (`_threat`), because a ten-minute-old company may well have marched off.
        It must not discount what an Assault *brings*, because the two errors are
        not the same size: sending four Squads at an empty Base wastes a march,
        and sending one at a company that is still there is #35's five dead in
        twenty-five seconds. Only somebody looking lowers this number — a place
        observed empty loses its Contact outright (#28's removal rule), which is
        the honest way to find out and the only one.

        Honest, and still not steady enough to unmake a commitment on (#181):
        in-world, "observed empty" is the engine's knowledge model, and a leader
        standing on the Base can lose sight of a garrison 25 m away for one
        sample. The red run's Decision rows show exactly that — "squad reported;
        2 wanted" one cycle, "nothing reported; 1 wanted" the next — and the
        demand shedding a Squad whose own top-scored option was still the
        assault. So a committed assault carries hysteresis (human ruling on
        #177, 2026-08-04): the Squads already standing under the Assault floor
        the demand, and the picture may raise what an Assault brings but never
        shed force the Commander has committed. The ruling's three releases all
        stay open, none of them through this floor: the objective falling ends
        the Campaign and the planning with it; a force that breaks leaves the
        Observation and takes the floor down with it, and a band the remainder
        cannot mass for is declined all-or-nothing as ever, retreat included;
        and a plan that clears the standing-Order margin (`momentum`, the
        stated threshold) moves the bid off the Base, the Assault is not
        sought, and every committed Squad is released to it.
        """
        seen = {contact.at: contact for contact in observation.contacts}
        committed: dict[str, int] = {}
        for squad in observation.squads:
            if squad.order == "assault":
                committed[squad.place] = committed.get(squad.place, 0) + 1
        return {
            base.id: _Demand(
                banded=self._demanded(seen.get(base.id)),
                committed=committed.get(base.id, 0),
            )
            for base in self.map_manifest.bases
            if base.side != observation.for_side
        }

    def _demanded(self, contact: Contact | None) -> int:
        """Read one Contact's band as a number of our own Squads."""
        if contact is None:
            # No Contact is not "empty" anywhere else in this scorer, and it is
            # not here either — it is the fog floor, which `_threat` already
            # prices at a team. A team is one Squad's worth, so an unreported
            # Base is assaulted by one Squad exactly as it was before #38.
            return ASSAULT_MASS["team"]
        # A band this table has never heard of is treated as the heaviest there
        # is. `contacts.ECHELONS` and this table are asserted in step, so the
        # fallback should be unreachable — but the direction to be wrong in is
        # the one that brings too many men rather than too few.
        return ASSAULT_MASS.get(contact.echelon, max(ASSAULT_MASS.values()))

    def _muster(
        self, options: list[_Option], wanted: dict[str, _Demand], vetoed: dict[str, int]
    ) -> _Muster:
        """Assign Squads to places, and say which Assaults were called off.

        Two stages, and the second one is the whole of #38. Everything a
        Commander does is decided by Squads bidding for places, one each — but
        a bid is exactly the wrong shape for massing. A Squad garrisoning quiet
        ground would rather stay there than march four kilometres at a company,
        so every Squad but the keenest bids the Assault down, and what arrives
        is the one Squad that could most afford the trip: precisely the Squad
        that dies there (#35).

        So the Assault is decided once, at the Commander's level, and the force
        is then **detailed** to it. Stage one is the ordinary bid, and its only
        job here is the question *is this Assault worth doing at all* — if no
        Squad ranked the Base first, nothing is sought and the Campaign goes on.
        Stage two takes that Squad and tops it up to the mass its Contact
        demands, cheapest trip first, from Squads that would rather be elsewhere.
        Ground already taken stays taken (`Campaign._advance_capture`), so what
        concentration costs is the advance and not the island.

        All-or-nothing: a Base that cannot be given its mass is one no Squad
        walks onto, so it is called off and the whole thing run again with it
        barred. Each pass either bars one of `wanted`'s Bases or settles, and
        `wanted` holds the enemy's Bases — one, on a two-sided map.
        """
        declined: set[str] = set()
        spared: dict[str, int] = {}
        while True:
            bid = self._assign(options, declined, detailed={})
            detailed: dict[str, _Option] = {}
            short = set()
            for place, demand in sorted(wanted.items()):
                if place in declined or _sent(bid, place) == 0:
                    # Not sought this cycle: nothing outbid the ground still
                    # worth taking, which is #34's arc and not a refusal — and
                    # the one way a committed Assault dissolves whole (#181),
                    # because a bid only leaves a standing Order past the
                    # `momentum` margin.
                    continue
                crew = self._detail(options, bid, place, demand.needed, detailed)
                spared[place] = len(crew)
                if len(crew) < demand.needed:
                    short.add(place)
                else:
                    detailed |= crew
            if not short:
                chosen = self._assign(options, declined, detailed)
                return _Muster(
                    taken=chosen,
                    declined=frozenset(declined),
                    spared=spared,
                    vetoed=vetoed,
                )
            declined |= short

    def _detail(
        self,
        options: list[_Option],
        bid: dict[str, _Option],
        place: str,
        needed: int,
        spoken_for: dict[str, _Option],
    ) -> dict[str, _Option]:
        """Name the Squads that go, starting with the one that asked to.

        The Squad the bid gave the Base to is kept rather than recomputed, so an
        Assault that needs one Squad details exactly the Squad it always did and
        an undefended Base behaves as it did before #38 — the change is only ever
        the Squads *added* to it. The rest are taken cheapest trip first, which
        on this scorer means the highest-scoring Assault option going: `options`
        is already in that order.
        """
        crew = {squad: option for squad, option in bid.items() if option.place == place}
        for option in options:
            if len(crew) >= needed:
                break
            if option.place != place or option.squad in crew or option.squad in spoken_for:
                continue
            crew[option.squad] = option
        return crew

    def _assign(
        self, options: list[_Option], declined: set[str], detailed: dict[str, _Option]
    ) -> dict[str, _Option]:
        """Give each Squad the best free place, best-scoring option first.

        One Squad per place: eight Squads all converging on the same Objective
        would take it eight times over and leave the rest of the island alone.
        `detailed` is the one exception and arrives already decided — the crew
        massed on a Base, whose place is closed to everyone else on arrival.
        """
        chosen: dict[str, _Option] = dict(detailed)
        held = {option.place for option in detailed.values()}
        for option in options:
            if option.squad in chosen or option.place in held or option.place in declined:
                continue
            chosen[option.squad] = option
            held.add(option.place)
        return chosen

    def _mustered(
        self, observation: Observation, wanted: dict[str, _Demand], muster: _Muster
    ) -> list[Decision]:
        """Say, per enemy Base, what force its Assault asked for and got.

        A row of its own rather than a phrase inside a Squad's, because "no
        Squad was sent to Kamino" is otherwise a silence, and three quite
        different things wear it: an Assault massed, an Assault called off for
        want of force, and an Assault nothing outbid. `scored` is the force the
        Commander had to draw on. When the commitment floor is what held the
        number up (#181), the row says so — "1 wanted, 2 committed" is the
        hysteresis operating, and a trace that read "1 wanted" over a mass of
        two would be an argument the reader could not follow.
        """
        seen = {contact.at: contact for contact in observation.contacts}
        rows = []
        for place, demand in sorted(wanted.items()):
            contact = seen.get(place)
            reported = f"{contact.echelon} reported" if contact else "nothing reported"
            asked = f"{demand.needed} wanted"
            if demand.committed > demand.banded:
                asked = f"{demand.banded} wanted, {demand.committed} committed"
            sent = _sent(muster.taken, place)
            if place in muster.declined:
                found = muster.spared.get(place, 0)
                chose, because = "declined", f"{reported}; {asked}, {found} could be spared"
            elif sent:
                chose, because = f"massed {sent}", f"{reported}; {asked}"
            else:
                chose, because = "not sought", f"{reported}; ground still worth taking outbid it"
            rows.append(
                Decision(
                    about=f"assault {place}",
                    chose=chose,
                    because=because,
                    scored=len(observation.squads),
                    candidates=(),
                )
            )
        return rows

    def _why(
        self,
        squad: SquadView,
        chosen: _Option,
        mine: list[_Option],
        muster: _Muster,
    ) -> Decision:
        """Say what this Squad was told and what it was chosen over."""
        best = mine[0]
        if chosen.choice == best.choice:
            if len(mine) > 1:
                # Three decimals since ADR-0031: a score is a compensated
                # product in [0, 1] rather than a sum of income-like terms, so
                # one decimal would round most real margins to nothing.
                because = f"{best.score - mine[1].score:.3f} ahead of {mine[1].choice}"
            else:
                because = "the only ground on the map"
        elif best.place in muster.declined:
            # The one reason a Squad is turned away from its best option that is
            # not another Squad having got there first (#38).
            because = f"{best.choice} was called off for want of mass"
        else:
            rivals = sorted(
                other.squad for other in muster.taken.values() if other.place == best.place
            )
            # Plural since #38: a Base is the one Place several Squads may share,
            # and "went to WEST-1" about a crew of four is a true sentence that
            # reads as a false one.
            if len(rivals) > 1:
                because = f"{best.choice} went to {len(rivals)} others"
            else:
                because = f"{best.choice} went to {rivals[0] if rivals else 'another'}"
        if (chosen.kind, chosen.place) == (squad.order, squad.place):
            because = f"already under this Order; {because}"
        return Decision(
            about=squad.id,
            chose=chosen.choice,
            because=because,
            scored=len(mine),
            candidates=tuple(
                Candidate(choice=option.choice, score=option.score, terms=option.terms)
                for option in mine[:TRACE_CANDIDATES]
            ),
            vetoed=muster.vetoed[squad.id],
        )

    def _spend(self, observation: Observation) -> tuple[list[Command], list[Decision]]:
        """Decide whether to spend, and on what: a fresh Squad, or a refill (#150).

        One spend per cycle, chosen among the ways the economy offers to add
        men. A fresh Squad is on the table while one may actually be added —
        under the map's cap and under the wire's force limit (`_fresh_barred`)
        — and the cheapest affordable one is the fresh candidate, because
        ground is taken by standing in a capture radius and every Squad stands
        in exactly one; Funds spent on a costlier Squad buy firepower this
        scorer has no threat model to value (#136). A refill is on the table
        for any Squad the port would accept a Reinforce for (`_refills`).

        The refill wins under the #150 ruling's two triggers: when no fresh
        Squad is on the table — at the force limit a Purchase is refused and
        Reinforce is the only way to add men, and the map's cap and an empty
        purse bar the fresh Squad the same way — or when its discounted
        pro-rata cost strictly beats the fresh Squad the planner would
        otherwise buy. A tie goes to the fresh Squad, which adds a whole Squad
        for the same Funds.

        And a player-led shell is preferred to a net-new Purchase (ADR-0070
        ruling 2, #311). That is an **allocation priority rather than a fourth
        way to spend**: the #150 choice above is resolved first, and only where
        it landed on a Purchase does an eligible shell take that Purchase's
        place, carrying the very composition it would have bought. A refill that
        has already won is not displaced, because the ruling substitutes for a
        Purchase and for nothing else.

        The map's cap and the wire's force limit bar a Purchase and do not bar
        this: filling a shell adds no Squad to the roster, so the Commander that
        would otherwise have spent nothing at its ceiling fills instead. Which
        is why the fill is reached from two branches — where a Purchase was
        chosen, and where no Purchase was available at all.

        It is deliberately absent from `candidates`. That tuple is the one price
        axis the fresh Squads and the refills are ranked on, winner first; a fill
        is not ranked against them but substituted after they have been, and
        listing it would assert a four-way comparison that was never made — and,
        where a refill won, would put a cheaper also-ran above the winner.
        """
        commands: list[Command] = []
        funds = observation.funds or 0
        refills = self._refills(observation)
        affordable = [refill for refill in refills if refill.cost <= funds]
        barred = self._fresh_barred(observation)
        priced = (
            ()
            if barred
            else tuple(
                squad
                for squad in sorted(self.table.squads, key=lambda squad: (squad.price, squad.id))
                if squad.price <= funds
            )
        )
        # How much choice there was: every fresh Squad weighed — none, when a
        # cap barred them all — plus every refillable Squad.
        scored = (0 if barred else len(self.table.squads)) + len(refills)

        # Winner first, as every Decision row promises. Cheapest way to add men
        # first, and where a refill ties a fresh Squad the fresh Squad leads,
        # because that is the way the tie is decided below.
        weighed = [
            ((float(squad.price), 0, squad.id), _priced_candidate(squad.id, squad.price))
            for squad in priced
        ]
        weighed += [((float(one.cost), 1, one.squad), _refill_candidate(one)) for one in affordable]
        candidates = tuple(candidate for _, candidate in sorted(weighed, key=lambda pair: pair[0]))

        fresh = priced[0] if priced else None
        refill = affordable[0] if affordable else None
        fill = next(iter(self._fills(observation, funds)), None)
        fielded = len(observation.squads)

        if refill is not None and (fresh is None or refill.cost < fresh.price):
            if barred:
                because = f"{refill.missing} men short at Base; {barred}"
            elif fresh is None:
                because = f"{refill.missing} men short at Base; {funds} Funds buy no fresh Squad"
            else:
                because = (
                    f"{refill.missing} men short at Base; "
                    f"{refill.cost} beats {fresh.id} at {fresh.price}"
                )
            commands.append(
                Command(name="reinforce", side=observation.for_side, args={"squad": refill.squad})
            )
            decision = Decision(
                about="funds",
                chose=f"reinforce {refill.squad}",
                because=because,
                scored=scored,
                candidates=candidates[:TRACE_CANDIDATES],
            )
        elif fresh is not None and fill is not None:
            commands.append(_fill_command(observation.for_side, fill))
            decision = Decision(
                about="funds",
                chose=_fill_choice(fill),
                because=_stood_in(fill, fresh.id, fresh.price, refill, fielded),
                scored=scored,
                candidates=candidates[:TRACE_CANDIDATES],
            )
        elif fresh is not None:
            because = f"{fielded} Squads fielded"
            if refill is not None:
                # A live refill lost the comparison, and the row says to what:
                # a trace that went quiet about the runner-up would read as the
                # refill never having been weighed (#150).
                because = (
                    f"{fielded} Squads fielded; {fresh.id} at {fresh.price} adds a whole "
                    f"Squad against refilling {refill.squad} at {refill.cost}"
                )
            commands.append(
                Command(name="purchase", side=observation.for_side, args={"squad_type": fresh.id})
            )
            decision = Decision(
                about="funds",
                chose=f"purchase {fresh.id}",
                because=because,
                scored=scored,
                candidates=candidates[:TRACE_CANDIDATES],
            )
        elif fill is not None:
            # No Purchase was on the table at all, and the shell is filled
            # anyway: neither ceiling bars a Command that adds no Squad, and a
            # purse that cannot reach a fresh Squad can still reach a discounted
            # fill. The register the silence would have used is kept and the
            # substitution said after it, so the row still explains itself.
            commands.append(_fill_command(observation.for_side, fill))
            decision = Decision(
                about="funds",
                chose=_fill_choice(fill),
                because=_fill_alone(self._spent_nothing(barred, funds, refills), fill, barred),
                scored=scored,
                candidates=candidates[:TRACE_CANDIDATES],
            )
        else:
            decision = Decision(
                about="funds",
                chose="nothing",
                because=self._spent_nothing(barred, funds, refills),
                scored=scored,
                candidates=(),
            )
        return commands, [decision]

    def _fresh_barred(self, observation: Observation) -> str:
        """Why no fresh Squad may be added this cycle, or "" while one may.

        Two ceilings, one sentence each. The map's: ground is taken by standing
        in a capture radius, the map has only so many radii, and a Squad past
        that has nowhere of its own to be. The wire's: past `force_limit` the
        port refuses the Purchase outright (#101), and the number here is the
        port's own measurement (`budget.squad_ceiling`) over the same manifest
        and table — so the planner declines exactly where the port would
        refuse, rather than issuing a Command whose refusal it cannot read.
        On the authored map the wire's ceiling (71) sits far behind the map's
        cap (8), so the map's sentence is the one Stratis ever says.
        """
        fielded = len(observation.squads)
        wanted = len(self.map_manifest.objectives)
        if fielded >= wanted:
            return f"{fielded} Squads fielded of {wanted} the map holds"
        if fielded >= self._force_ceiling():
            return f"{fielded} Squads fielded of {self._force_ceiling()} the wire carries"
        return ""

    def _force_ceiling(self) -> int:
        """How many Squads the wire lets this side field, measured once.

        The port's measurement reused rather than restated (#150): a Purchase
        past it is refused `force_limit`, which under the ruling is the one
        place a Reinforce is the only way to add men. Lazy like the port's own
        `squad_ceiling`, because it costs a binary search over serialisations.
        None — a map whose Observation fits no reply at all — reads as zero:
        no Purchase is ever legal there.
        """
        if not self._force_limit_measured:
            self._force_limit = budget.squad_ceiling(self.map_manifest, self.table)
            self._force_limit_measured = True
        return self._force_limit or 0

    def _refills(self, observation: Observation) -> list[_Refill]:
        """Every Squad a Reinforce would be accepted for, cheapest refill first.

        The port's refusal matrix read forwards, exactly as `legal` reads it
        for Orders (ADR-0031): bought as a type the table still sells, short of
        the strength it was bought at, and standing at its own Base — which is
        where CONTEXT.md puts Reinforce and what `_refill_refusal` holds it to.
        The planner and the port read the same roster numbers (the
        Observation's `size` is the roster's own), so a candidate here is never
        `already_held` there.
        """
        base = self._base_of[observation.for_side]
        found = []
        for squad in observation.squads:
            if squad.at != base:
                continue
            sold = self.table.sold(squad.squad_type)
            if sold is None:
                # A type the table no longer sells cannot be priced. The port
                # reports that as a fault in the table (`malformed_command`),
                # and a fault in the table is not this cycle's to spend on.
                continue
            missing = sold.size - squad.size
            cost = self.table.reinforce_cost(squad.squad_type, missing)
            if missing <= 0 or cost is None:
                continue
            found.append(_Refill(squad=squad.id, missing=missing, cost=cost))
        return sorted(found, key=lambda refill: (refill.cost, refill.squad))

    def _fills(self, observation: Observation, funds: int) -> list[_Fill]:
        """Every shell a composition-carrying Reinforce would be accepted for.

        The port's refusal matrix read forwards, exactly as `_refills` reads it
        for the ordinary Reinforce (ADR-0031, ADR-0070): not suspended, still
        composition-unassigned, standing at its own Base, and priced at a
        composition this side can pay to fill. So a candidate here is never one
        `_fill_refusal` would refuse `squad_suspended`, `composition_fixed` or
        `wrong_ground`, nor one `first_fill` would refuse for want of Funds.

        A composition-unassigned Squad is one carrying no composition type,
        which is the representation CONTEXT.md's amended **Observation**
        ratified; `suspended` beside it is what says whether it may be filled
        *yet*, and the two are read together because a suspended shell carries
        no type either.

        Cheapest fill first, like `_refills`, so a Commander with one spend to
        make reaches for the shell it can most afford.
        """
        base = self._base_of[observation.for_side]
        found = []
        for squad in observation.squads:
            if squad.squad_type or squad.suspended or squad.at != base:
                continue
            demanded = self._composition(squad.size, funds)
            if demanded is None:
                continue
            squad_type, cost = demanded
            found.append(_Fill(squad=squad.id, squad_type=squad_type, cost=cost))
        return sorted(found, key=lambda fill: (fill.cost, fill.squad))

    def _composition(self, standing: int, funds: int) -> tuple[str, int] | None:
        """Return the composition a Purchase would have bought, and the fill's price.

        The same cheapest-affordable rule `_spend` applies to a Purchase — the
        table in price order, the first entry the side can pay for — read
        against what this route actually pays rather than against the full
        price. Wherever a Purchase is on the table the two agree exactly, and
        provably so: a fill is a discounted fraction of the composition's price,
        so the Purchase's own choice is always affordable here, and anything
        cheaper by price would have been the Purchase. They part only where the
        purse reaches a fill and no Purchase at all, which is a case a Purchase
        has no opinion about.
        """
        for squad in sorted(self.table.squads, key=lambda squad: (squad.price, squad.id)):
            cost = self.table.reinforce_cost(squad.id, max(0, squad.size - standing))
            if cost is not None and cost <= funds:
                return squad.id, cost
        return None

    def _spent_nothing(self, barred: str, funds: int, refills: list[_Refill]) -> str:
        """Say why no Funds moved, distinguishing every silence (#150).

        Four of them now: barred from buying with nothing to refill, barred
        with refills the Funds cannot pay for, free to buy but too poor for
        anything, and too poor for a Squad with the refill also out of reach.
        """
        if barred and not refills:
            return barred
        if barred:
            return f"{barred}; {funds} Funds refill none"
        if not refills:
            return f"{funds} Funds purchase no Squad this map sells"
        return f"{funds} Funds purchase no Squad this map sells and refill none"


def _priced_candidate(squad_type: str, price: int) -> Candidate:
    """Render one fresh Squad as the funds row carries it, unchanged since #16."""
    return Candidate(choice=squad_type, score=float(-price), terms={"price": -price})


def _refill_candidate(refill: _Refill) -> Candidate:
    """Render one refill as the funds row carries it (#150).

    The same price axis the fresh Squads score on, so the row is one argument —
    the cheapest way to add men wins — plus the `missing` the cost was priced
    off, because a refill's price means nothing without it.
    """
    return Candidate(
        choice=f"reinforce {refill.squad}",
        score=float(-refill.cost),
        terms={"price": -refill.cost, "missing": refill.missing},
    )


def _fill_command(side: str, fill: _Fill) -> Command:
    """Build the composition-carrying Reinforce that fills one shell (ADR-0070).

    Its own Command name rather than an optional argument on `reinforce`, which
    is the ADR's call and not this module's: the catalogue's fixed argument
    lists are what SQF cannot build wrong.
    """
    return Command(
        name="reinforce_composition",
        side=side,
        args={"squad": fill.squad, "squad_type": fill.squad_type},
    )


def _fill_choice(fill: _Fill) -> str:
    """Render a chosen fill as the funds row names it: the shell and its composition."""
    return f"fill {fill.squad} as {fill.squad_type}"


def _stood_in(fill: _Fill, bought: str, price: int, refill: _Refill | None, fielded: int) -> str:
    """Say which Purchase the shell stood in for, and what that Purchase beat.

    Both halves, because they are two different arguments and dropping either
    leaves a row that reads as an omission. A fill that went quiet about the
    Purchase would read as the shell never having been weighed against one —
    which is #150's own "a live refill lost the comparison, and the row says to
    what", one substitution further along — and a fill that swallowed #150's
    sentence would lose the refill that had already lost.
    """
    stood = f"filling the shell {fill.squad} at {fill.cost} stands in for"
    if refill is None:
        return f"{fielded} Squads fielded; {stood} purchasing {bought} at {price}"
    return (
        f"{fielded} Squads fielded; {bought} at {price} adds a whole Squad against "
        f"refilling {refill.squad} at {refill.cost}, and {stood} that Purchase"
    )


def _fill_alone(stood: str, fill: _Fill, barred: str) -> str:
    """Say why the shell was filled where no Purchase was on the table at all.

    `stood` is the silence this row would otherwise have carried, kept verbatim
    so the reader still learns what could not be bought; what follows says why
    the fill was not barred with it. Two reasons, because the two ceilings and
    an empty purse stop a Purchase for quite different causes: a ceiling counts
    Squads and a fill adds none, while a purse is simply reached by the
    discounted price and not by the full one.
    """
    why = "adds no Squad to the roster" if barred else "is what the purse reaches"
    return f"{stood}; filling the shell {fill.squad} at {fill.cost} {why}"


def _sent(chosen: dict[str, _Option], place: str) -> int:
    """How many Squads an assignment put on one Place."""
    return sum(1 for option in chosen.values() if option.place == place)


def _stable_fraction(seed: int, of: str) -> float:
    """Return a number in [0, 1) fixed by the seed and the name.

    Seeded from a string rather than through `hash`, which is randomised per
    process, and keyed on the name rather than drawn per call: a Campaign has to
    play the same way twice, and an Objective's small preference has to stay put
    between cycles or it is one more thing for a Squad to countermarch over.
    """
    return random.Random(f"{seed}:{of}").random()  # noqa: S311 — tie-breaks, not secrets
