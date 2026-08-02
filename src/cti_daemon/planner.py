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
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from math import hypot
from typing import TYPE_CHECKING, Final, Protocol

import networkx as nx

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
    a Base that cannot be given its mass is one no Squad walks onto. Deliberately
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

        spending, spent_because = self._purchase(observation)
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

    def _mass(self, observation: Observation) -> dict[str, int]:
        """How many Squads an Assault on each enemy Base has to arrive with.

        The threat model, and all of it (ADR-0027). It reads the band and only
        the band: `ASSAULT_MASS` is a doctrine table, so nothing here divides,
        multiplies or otherwise reconstructs the count #28 withheld.

        Age is read nowhere in this method, and that is the decision rather than
        an omission. A Contact's age already discounts what the place *costs*
        (`_threat`), because a ten-minute-old company may well have marched off.
        It must not discount what an Assault *brings*, because the two errors are
        not the same size: sending four Squads at an empty Base wastes a march,
        and sending one at a company that is still there is #35's five dead in
        twenty-five seconds. Only somebody looking lowers this number — a place
        observed empty loses its Contact outright (#28's removal rule), which is
        the honest way to find out and the only one.
        """
        seen = {contact.at: contact for contact in observation.contacts}
        return {
            base.id: self._demanded(seen.get(base.id))
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
        self, options: list[_Option], wanted: dict[str, int], vetoed: dict[str, int]
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
        Ground already taken stays taken (`Campaign._advance`), so what
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
            for place, needed in sorted(wanted.items()):
                if place in declined or _sent(bid, place) == 0:
                    # Not sought this cycle: nothing outbid the ground still
                    # worth taking, which is #34's arc and not a refusal.
                    continue
                crew = self._detail(options, bid, place, needed, detailed)
                spared[place] = len(crew)
                if len(crew) < needed:
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
        self, observation: Observation, wanted: dict[str, int], muster: _Muster
    ) -> list[Decision]:
        """Say, per enemy Base, what force its Assault asked for and got.

        A row of its own rather than a phrase inside a Squad's, because "no
        Squad was sent to Kamino" is otherwise a silence, and three quite
        different things wear it: an Assault massed, an Assault called off for
        want of force, and an Assault nothing outbid. `scored` is the force the
        Commander had to draw on.
        """
        seen = {contact.at: contact for contact in observation.contacts}
        rows = []
        for place, needed in sorted(wanted.items()):
            contact = seen.get(place)
            reported = f"{contact.echelon} reported" if contact else "nothing reported"
            sent = _sent(muster.taken, place)
            if place in muster.declined:
                found = muster.spared.get(place, 0)
                chose, because = "declined", f"{reported}; {needed} wanted, {found} could be spared"
            elif sent:
                chose, because = f"massed {sent}", f"{reported}; {needed} wanted"
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

    def _purchase(self, observation: Observation) -> tuple[list[Command], list[Decision]]:
        """Decide whether to spend, and on what. Returns what it decided."""
        commands: list[Command] = []
        decisions: list[Decision] = []
        funds = observation.funds or 0
        # Ground is taken by standing in a capture radius, and the map has only
        # so many radii. A Squad past that has nowhere of its own to be, and a
        # force that grows without a ceiling is what runs an Observation into
        # #26's 10,240-byte return cap.
        wanted = len(self.map_manifest.objectives)
        if len(observation.squads) >= wanted:
            decisions.append(
                Decision(
                    about="funds",
                    chose="nothing",
                    because=f"{len(observation.squads)} Squads fielded of {wanted} the map holds",
                    scored=0,
                    candidates=(),
                )
            )
            return commands, decisions

        affordable = tuple(squad for squad in self.table.squads if squad.price <= funds)
        candidates = tuple(
            Candidate(choice=squad.id, score=float(-squad.price), terms={"price": -squad.price})
            for squad in sorted(affordable, key=lambda squad: (squad.price, squad.id))
        )
        if not affordable:
            decisions.append(
                Decision(
                    about="funds",
                    chose="nothing",
                    because=f"{funds} Funds purchase no Squad this map sells",
                    scored=len(self.table.squads),
                    candidates=(),
                )
            )
            return commands, decisions

        # Cheapest, because ground is taken by standing in a capture radius and
        # every Squad stands in exactly one. Funds spent on a costlier Squad get
        # firepower this scorer has no threat model to value.
        bought = candidates[0]
        commands.append(
            Command(name="purchase", side=observation.for_side, args={"squad_type": bought.choice})
        )
        decisions.append(
            Decision(
                about="funds",
                chose=f"purchase {bought.choice}",
                because=f"{len(observation.squads)} Squads fielded",
                scored=len(self.table.squads),
                candidates=candidates[:TRACE_CANDIDATES],
            )
        )
        return commands, decisions


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
