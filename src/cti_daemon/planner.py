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

    Two relations are load-bearing rather than tuning. `jitter` is smaller than
    `travel`, so the seed can only decide between options geography has already
    tied to within a third of a kilometre — it never sends a Squad the long way
    round. And `garrison` is smaller than `income`, so taking ground beats
    sitting on it while there is ground left to take.
    """

    # What an Objective's authored income is worth to take.
    income: float = 1.0
    # And to keep. Far lower, because `Campaign._advance` keeps ground taken
    # once taken: standing on quiet ground buys nothing the Campaign was not
    # already paying, and a Commander who garrisons everything never wins by
    # Domination. What makes a garrison worth it is the threat term below; this
    # only decides which of two threatened Objectives is worth more.
    garrison: float = 0.1
    # Ground half-taken is worth finishing.
    contested: float = 6.0
    # What a team of assumed enemy costs to attack, and is worth to garrison
    # against. Both in the units of ECHELON_THREAT.
    threat: float = 2.0
    defend: float = 3.0
    # Per kilometre of marching, measured along the adjacency graph.
    travel: float = 3.0
    # What a standing Order is worth on its own. The whole anti-thrash rule: a
    # Squad keeps going where it was sent unless something beats it by this much,
    # so scores that jitter around each other do not turn into countermarching.
    commitment: float = 5.0
    # A fixed per-place preference, so two identical Objectives at equal distance
    # are not decided by alphabetical order and a Campaign has a character.
    jitter: float = 1.0
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

    It plays for Domination and not for Decapitation, because an Order names an
    Objective and a Base is not one — the port has no way to say "go for the
    enemy HQ", so neither has this. That is the port's vocabulary to widen, not
    something for a scorer to route around.
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
            if (chosen.kind, chosen.place) == (squad.order, squad.objective):
                continue
            commands.append(
                Command(
                    name="order",
                    side=observation.for_side,
                    args={"squad": squad.id, "order": chosen.kind, "objective": chosen.place},
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
            terms["travel"] = -self.weights.travel * self._reach[origin][objective.id]
            # What the Squad is already doing, worth something on its own.
            standing = (kind, objective.id) == (squad.order, squad.objective)
            terms["commitment"] = self.weights.commitment if standing else 0.0
            terms["jitter"] = self.weights.jitter * self._jitter[objective.id]
            options.append(
                _Option(
                    squad=squad.id,
                    kind=kind,
                    place=objective.id,
                    score=sum(terms.values()),
                    terms=terms,
                )
            )
        return options

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
        if (chosen.kind, chosen.place) == (squad.order, squad.objective):
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
