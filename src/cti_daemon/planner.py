"""The AI Commander's brain: what to buy, and where to send what it has.

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

from cti_daemon.campaign import CONTESTED
from cti_daemon.commands import Command
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


@dataclass(frozen=True, slots=True)
class Weights:
    """What the scorer values. Playtest-tuned placeholders; the terms are the contract.

    Tuned for a Commander that presses (human decision, 2026-07-31): two sides
    both sitting on what they hold is not a Campaign worth playing, so the
    default here advances by preference and consolidates only against a real
    massed incursion. Measured on Stratis with a Squad on the line and the
    enemy fresh across it, it attacks a Contact of every echelon up to a
    company, and pulls back only when a company is standing on ground behind
    it. What the first set of these weights did in the same picture was hold,
    at every echelon, even with `threat` and `defend` set to zero — because the
    turtle was never the threat terms. It was `travel` and `commitment`.

    Three relations are load-bearing rather than tuning. `jitter` is smaller
    than `travel`, so the seed can only decide between options geography has
    already tied to within three hundred metres — it never sends a Squad the
    long way round. `commitment` is larger than the whole spread of `jitter`,
    so the anti-thrash margin still covers what the seed can move. And
    `garrison` is smaller than `income`, so taking ground beats sitting on it
    while there is ground left to take.
    """

    # What an Objective's authored income is worth to take.
    income: float = 1.0
    # And to keep. This is the whole value of standing on quiet ground, so what
    # it actually sets is advance against consolidate: whether a Squad that has
    # just taken an Objective holds it or moves on. Measured on Stratis, at 0.1
    # the Squad that takes Agia Marina marches on to LZ Baldy and at 1.0 it
    # stays. Low because `Campaign._advance` keeps ground taken once taken, so a
    # garrison on quiet ground guards income the Campaign was already paying.
    #
    # It multiplies the Objective's authored income, so on a map where every
    # Objective pays the same — Stratis does — it is a constant across every
    # Defend option and cannot choose between them. Deciding which garrison is
    # the urgent one is the threat term below, and always was.
    garrison: float = 0.1
    # Ground half-taken is worth finishing.
    contested: float = 6.0
    # What a team of assumed enemy costs to attack, and is worth to garrison
    # against. Both in the units of ECHELON_THREAT. Small against `income`
    # deliberately: at 0.5 a fresh company on an Objective costs 4 against the
    # 10 that taking it pays, so heavy ground is attacked later than light
    # ground rather than never. Raising it past `income / 8` is the point where
    # a company becomes ground this Commander will not go near.
    threat: float = 0.5
    # And what the same Contact is worth to garrison against on our own side of
    # it. Sized so a company — and only a company — behind the line outbids
    # marching on: a Commander that turned round for every team sighting would
    # never finish anything it started.
    defend: float = 1.0
    # Per kilometre of marching, measured along the adjacency graph. This is the
    # main aggression dial, not `garrison` and not `threat`: at the original 3.0
    # a four-kilometre march cost 12 against an Objective worth 10, so the far
    # half of the island was never worth walking to and a Squad that reached the
    # line stopped there. At 1.0 the whole of Stratis stays worth crossing while
    # the near Objective is still preferred to the far one.
    travel: float = 1.0
    # What a standing Order is worth on its own. The whole anti-thrash rule: a
    # Squad keeps going where it was sent unless something beats it by this much,
    # so scores that jitter around each other do not turn into countermarching.
    # It has to stay above the spread of `jitter` and below what a better
    # Objective is worth — at 5.0 it was half an Objective's income and a Squad
    # that had once been told to hold would not be told anything else.
    commitment: float = 2.0
    # What a Base is worth, in the units every other value term is priced in —
    # an Objective's authored income. ADR-0020's one new term, and it needs to
    # be new because every existing value term prices income and a Base pays
    # none: what a Base is worth is the Campaign, the enemy's to end and ours to
    # keep. Playtest-tuned placeholder, flagged for feel sign-off (#34).
    #
    # A little under what an Objective pays, and the window either side of it is
    # narrow enough that both ends are behaviours rather than tastes. Measured
    # on Stratis, where every Objective pays ten:
    #
    # Above 8.87 a Squad standing on Agia Marina turns for the WEST Base 1.1 km
    # away instead of taking LZ Baldy 1.9 km away, and does it with seven
    # Objectives still unheld — a base rush rather than a Campaign, and the
    # thing ADR-0020 said to tune first if raids outrun fronts. Below 7.27 a
    # fresh company standing on our own Base no longer outbids marching on: a
    # Base's value to hold is this term through `garrison`, so a tenth of too
    # little is nothing and the Commander walks away from its own HQ at exactly
    # the moment somebody came for it.
    #
    # Eight sits between them. It makes the Assault the third option at the
    # opening and the first for a Squad that has run out of ground worth taking
    # — which is the arc, and which is why the raid arrives late without any
    # rule saying so: what defers it is the 4.7 km between the two Bases.
    decapitation: float = 8.0
    # A fixed per-place preference, so two identical Objectives at equal distance
    # are not decided by alphabetical order and a Campaign has a character.
    # Three hundred metres of march, in the units of `travel`.
    jitter: float = 0.3
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
    """

    map_manifest: MapManifest
    table: EconomyTable
    # Fixed per Campaign, and an argument rather than a clock reading: the same
    # seed and the same observations must produce the same Orders. Phase 2 puts
    # it in the snapshot, so a resumed Campaign keeps its character.
    seed: int = 0
    weights: Weights = Weights()
    _base_of: dict[str, str] = field(init=False, default_factory=dict)
    _reach: dict[str, dict[str, float]] = field(init=False, default_factory=dict)
    _jitter: dict[str, float] = field(init=False, default_factory=dict)

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

        commands: list[Command] = []
        decisions: list[Decision] = []
        self._buy(observation, commands, decisions)
        self._deploy(observation, commands, decisions)
        return Plan(commands=tuple(commands), decisions=tuple(decisions))

    def _deploy(
        self, observation: Observation, commands: list[Command], decisions: list[Decision]
    ) -> None:
        """Give every Squad the best thing left for it to be doing."""
        options = sorted(
            (
                option
                for squad in observation.squads
                for option in self._options(observation, squad)
            ),
            key=lambda option: (-option.score, option.squad, option.place),
        )
        taken = self._assign(options)

        for squad in observation.squads:
            mine = [option for option in options if option.squad == squad.id]
            if not mine:
                continue
            # Every Squad gets its own place while there are places, and the
            # scorer buys up to one per Objective so there normally are. A Squad
            # past that — a side a human has also been buying for — takes its own
            # best option and shares the ground.
            chosen = taken.get(squad.id, mine[0])
            decisions.append(self._why(squad, chosen, mine, taken))
            if (chosen.kind, chosen.place) == (squad.order, squad.place):
                continue
            commands.append(
                Command(
                    name="order",
                    side=observation.for_side,
                    args={"squad": squad.id, "order": chosen.kind, "place": chosen.place},
                )
            )

    def _options(self, observation: Observation, squad: SquadView) -> list[_Option]:
        """Score everything this one Squad could be sent to do."""
        side = observation.for_side
        # A Squad in open ground is between places and has no distance of its
        # own, so it is measured from the Base it was bought at.
        origin = squad.at if squad.at in self._reach else self._base_of[side]
        watched = {other.at for other in observation.squads if other.at}
        contacts = {contact.at: contact for contact in observation.contacts}

        options = []
        for objective in self.map_manifest.objectives:
            owner = observation.owners.get(objective.id, "")
            # One kind per place, because the other is an Order the port would
            # refuse or a nonsense: Capture is for ground the side does not hold
            # and Defend is for ground it does.
            kind = "defend" if owner == side else "capture"
            terms = self._terms(
                kind=kind,
                income=objective.income,
                contested=owner == CONTESTED,
                threat=self._threat(contacts.get(objective.id), watched=objective.id in watched),
            )
            options.append(self._weigh(squad, kind, objective.id, terms, origin))

        for base in self.map_manifest.bases:
            # The one place whose loss ends the Campaign, on either side of it.
            # Which kind a Base takes is the port's refusal matrix read forwards
            # (ADR-0020): Assault names the enemy's and Defend names our own,
            # and there is no third thing to say about either.
            kind = "defend" if base.side == side else "assault"
            terms = self._base_terms(
                kind=kind,
                threat=self._threat(contacts.get(base.id), watched=base.id in watched),
            )
            options.append(self._weigh(squad, kind, base.id, terms, origin))
        return options

    def _weigh(
        self, squad: SquadView, kind: str, place: str, terms: dict[str, float], origin: str
    ) -> _Option:
        """Add what this Squad's own position makes of a place, and total it up."""
        terms["travel"] = -self.weights.travel * self._reach[origin][place]
        # What the Squad is already doing, worth something on its own.
        standing = (kind, place) == (squad.order, squad.place)
        terms["commitment"] = self.weights.commitment if standing else 0.0
        terms["jitter"] = self.weights.jitter * self._jitter[place]
        return _Option(
            squad=squad.id, kind=kind, place=place, score=sum(terms.values()), terms=terms
        )

    def _terms(self, *, kind: str, income: int, contested: bool, threat: float) -> dict[str, float]:
        """Value one place, before anything about the Squad going to it."""
        if kind == "capture":
            return {
                "income": self.weights.income * income,
                "contested": self.weights.contested if contested else 0.0,
                "threat": -self.weights.threat * threat,
            }
        return {
            "income": self.weights.garrison * income,
            # Threat is a reason to garrison rather than a reason to stay away:
            # the same Contact reads opposite ways depending on who holds it.
            "threat": self.weights.defend * threat,
        }

    def _base_terms(self, *, kind: str, threat: float) -> dict[str, float]:
        """Value a Base, whose worth is not income but the Campaign ending on it.

        The same two-sided reading the Objective terms have, one step further
        along: an Objective changes hands and a Base dies, so what the enemy's
        is worth is the whole of `decapitation`, and what ours is worth to stand
        on goes through the same `garrison` multiplier an Objective's income
        does. That keeps ADR-0014's relation intact — holding is worth a tenth
        of taking, so a Squad garrisons the Base against something rather than
        instead of the war — while making the thing it is holding the Campaign
        rather than ten Funds a tick.
        """
        if kind == "assault":
            return {
                "decapitation": self.weights.decapitation,
                "threat": -self.weights.threat * threat,
            }
        return {
            "decapitation": self.weights.garrison * self.weights.decapitation,
            # Read the same way as on any held ground, floor and all: nobody
            # standing at the Base means possibly-threatened, never safe.
            "threat": self.weights.defend * threat,
        }

    def _threat(self, contact: Contact | None, *, watched: bool) -> float:
        """How much enemy a place is assumed to hold, in teams."""
        # Ground one of ours is standing on is ground being looked at, so no
        # Contact there means empty. Anywhere else, no Contact means unknown.
        floor = 0.0 if watched else UNKNOWN_THREAT
        if contact is None:
            return floor
        freshness = max(0.0, 1.0 - contact.age / self.weights.stale_seconds)
        return max(floor, ECHELON_THREAT.get(contact.echelon, UNKNOWN_THREAT) * freshness)

    def _assign(self, options: list[_Option]) -> dict[str, _Option]:
        """Give each Squad the best free place, best-scoring option first.

        One Squad per place: eight Squads all converging on the same Objective
        would take it eight times over and leave the rest of the island alone.
        """
        chosen: dict[str, _Option] = {}
        held: set[str] = set()
        for option in options:
            if option.squad in chosen or option.place in held:
                continue
            chosen[option.squad] = option
            held.add(option.place)
        return chosen

    def _why(
        self,
        squad: SquadView,
        chosen: _Option,
        mine: list[_Option],
        taken: dict[str, _Option],
    ) -> Decision:
        """Say what this Squad was told and what it was chosen over."""
        best = mine[0]
        if chosen.choice == best.choice:
            if len(mine) > 1:
                because = f"{best.score - mine[1].score:.1f} ahead of {mine[1].choice}"
            else:
                because = "the only ground on the map"
        else:
            rival = next(
                (other.squad for other in taken.values() if other.place == best.place), "another"
            )
            because = f"{best.choice} went to {rival}"
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
        )

    def _buy(
        self, observation: Observation, commands: list[Command], decisions: list[Decision]
    ) -> None:
        """Decide whether to spend, and on what."""
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
            return

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
                    because=f"{funds} Funds buys no Squad this map sells",
                    scored=len(self.table.squads),
                    candidates=(),
                )
            )
            return

        # Cheapest, because ground is taken by standing in a capture radius and
        # every Squad stands in exactly one. Funds spent on a costlier Squad buy
        # firepower this scorer has no threat model to value.
        bought = candidates[0]
        commands.append(
            Command(name="purchase", side=observation.for_side, args={"squad_type": bought.choice})
        )
        decisions.append(
            Decision(
                about="funds",
                chose=f"buy {bought.choice}",
                because=f"{len(observation.squads)} Squads fielded",
                scored=len(self.table.squads),
                candidates=candidates[:TRACE_CANDIDATES],
            )
        )


def _stable_fraction(seed: int, of: str) -> float:
    """Return a number in [0, 1) fixed by the seed and the name.

    Seeded from a string rather than through `hash`, which is randomised per
    process, and keyed on the name rather than drawn per call: a Campaign has to
    play the same way twice, and an Objective's small preference has to stay put
    between cycles or it is one more thing for a Squad to countermarch over.
    """
    return random.Random(f"{seed}:{of}").random()  # noqa: S311 — tie-breaks, not secrets
