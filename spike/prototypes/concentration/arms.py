"""PROTOTYPE — throwaway. The four planner variants under comparison (#187).

Arm (a) is the shipped `UtilityPlanner`, imported and unmodified. The other
three subclass it and change one thing each, so what a measurement attributes to
an arm is the change and not a reimplementation. None of this is production
code; the diff between an arm and its base is the *complexity* half of the
comparison and is counted as such.

The issue names three arms. There are four here because arm (b) has two readings
and they behave differently:

- **b-term** takes the acceptance criteria literally — the veto deleted and
  replaced by a consideration that scores two-on-one. It is what "a term that
  can score two-on-one" means if the term lives where terms live.
- **b-muster** puts the same capability where ADR-0027 already put the identical
  problem for Bases: in the assignment rule, not the score. It is the smaller
  change of the two, and it inherits #181's commitment hysteresis for nothing.

Both are reported. Which one "arm (b)" means turns out to matter more than the
gap between arm (b) and arm (c).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import SQUAD_MEN, rally_point

from cti_daemon import planner
from cti_daemon.commands import Command
from cti_daemon.observation import Observation, SquadView

if TYPE_CHECKING:
    from cti_daemon.contacts import Contact

# The Order kinds that send a Squad at ground somebody else holds. Defend is not
# one: two Squads standing on the same held Objective is a garrison doubling up,
# which is the waste the veto was built for and is not what anyone means by
# concentration.
OFFENSIVE = ("capture", "assault")


def demanded(contact: Contact | None) -> int:
    """How many Squads doctrine wants against one place, band in and number out.

    `planner.ASSAULT_MASS` read as what it is — a doctrine table from an echelon
    band to a number of our own Squads — and applied to any place rather than to
    enemy Bases alone. Nothing new is invented and nothing about the enemy is
    reconstructed: the same band, the same table, the same arithmetic ADR-0027
    signed off, asked about an Objective.
    """
    if contact is None:
        return planner.ASSAULT_MASS["team"]
    return planner.ASSAULT_MASS.get(contact.echelon, max(planner.ASSAULT_MASS.values()))


def contested(observation: Observation, manifest_places: set[str]) -> dict[str, Contact | None]:
    """Every place this side does not hold, with whatever is reported on it."""
    seen = {contact.at: contact for contact in observation.contacts}
    return {
        place: seen.get(place)
        for place in sorted(manifest_places)
        if observation.owners.get(place, "") != observation.for_side
    }


# --------------------------------------------------------------------- arm (a)

Baseline = planner.UtilityPlanner
"""Arm (a): the status quo, imported. One Squad per Place, no exceptions but the
Base mass ADR-0027 already carved out."""


# ------------------------------------------------------------------- arm (b-term)


@dataclass(slots=True)
class ConcentrationTerm(Baseline):
    """Arm (b-term): the veto deleted, a concentration consideration in its place.

    `_assign`'s one-per-place rule goes. What replaces it is a factor on the
    score — a place already carrying `k` of our Squads discounts the next one by
    how little it is still short of the force doctrine wants there. Under-matched
    ground barely discounts, matched ground discounts to `waste_floor`, so the
    veto's legitimate job (the whole force does not pile onto one town) survives
    as a steep preference rather than as a prohibition.

    Because the factor depends on who has already been assigned, the greedy
    single pass `_assign` does cannot carry it: the term re-ranks the option list
    as the list is consumed. So the assignment becomes an iterative best-first
    pick. That is the shape cost of putting concentration in the score, and it
    is the first thing the complexity count charges this arm for.

    The shortfall is read off `ASSAULT_MASS`, not off `ECHELON_THREAT`. The
    first draft here did the latter — a Squad priced at two teams, matched
    against the Contact's threat in teams — and it never sent a second Squad
    anywhere, because on that arithmetic one Squad answers a squad band exactly.
    That is ADR-0027's rejected reading rediscovered from the other end: the
    threat curve is a price and the doctrine table is a size, and only the size
    can say how many. Correcting it makes this arm ask doctrine's question and
    lose on the answer's shape rather than on a mis-tuned constant.
    """

    # What a Squad added to ground already answered is worth against the first
    # one there. Not zero: two-on-one at a place we have already matched is
    # waste, never illegal, and a scorer that forbade it would be the veto again
    # wearing a curve.
    waste_floor: float = 0.05
    # How fast the discount lifts as the shortfall grows. Squared by default,
    # matching the `danger` and `hold` curves' shape. Swept in `compare.py`,
    # because what this exponent turns out to decide is not how eagerly the arm
    # concentrates but whether it ever does.
    shortfall_power: float = 2.0

    def _concentration(self, already: int, want: int) -> float:
        """What the next Squad onto a place is worth, given who is already going."""
        if already == 0:
            return 1.0
        shortfall = max(0, want - already) / want
        if self.shortfall_power == 0.0:
            # The degenerate curve: full value while short, `waste_floor` once
            # matched. A step rather than a slope — which is a capacity rule
            # wearing a factor's clothes, and the point of measuring it.
            return 1.0 if shortfall > 0.0 else self.waste_floor
        return self.waste_floor + (1.0 - self.waste_floor) * shortfall**self.shortfall_power

    def _assign(
        self,
        options: list[planner._Option],
        declined: set[str],
        detailed: dict[str, planner._Option],
    ) -> dict[str, planner._Option]:
        """Best-first, with the concentration term re-ranking as places fill up."""
        chosen: dict[str, planner._Option] = dict(detailed)
        crowd: dict[str, int] = {}
        for option in detailed.values():
            crowd[option.place] = crowd.get(option.place, 0) + 1
        free = [option for option in options if option.squad not in chosen]
        while free:
            best = max(
                free,
                key=lambda option: (
                    option.score
                    * (
                        1.0
                        if option.kind not in OFFENSIVE
                        else self._concentration(
                            crowd.get(option.place, 0), self._wants[option.place]
                        )
                    ),
                    -crowd.get(option.place, 0),
                    option.squad,
                ),
            )
            if best.place in declined:
                free = [option for option in free if option is not best]
                continue
            chosen[best.squad] = best
            crowd[best.place] = crowd.get(best.place, 0) + 1
            free = [option for option in free if option.squad != best.squad]
        return chosen

    # The term reads a doctrine demand per place, which `_assign` has no argument
    # for. Stashed on the instance for the duration of a plan rather than
    # threaded through four signatures — a prototype's shortcut, and the second
    # thing the complexity count charges: in production this is a parameter
    # change down `_muster`, `_assign` and `_detail`.
    _wants: dict[str, int] = field(init=False, default_factory=dict)

    def plan(self, observation: Observation) -> planner.Plan:
        """Read the doctrine demand once, then plan as the base class does."""
        seen = {contact.at: contact for contact in observation.contacts}
        places = [objective.id for objective in self.map_manifest.objectives]
        places += [base.id for base in self.map_manifest.bases]
        self._wants = {place: demanded(seen.get(place)) for place in places}
        return super().plan(observation)


# ----------------------------------------------------------------- arm (b-muster)


@dataclass(slots=True)
class ConcentrationMuster(Baseline):
    """Arm (b-muster): ADR-0027's Base mass, asked about Objectives too.

    `_mass` returns a demand per enemy Base. This returns one per *contested
    place* — every Objective the side does not hold, and the enemy's Base as
    before — read off the same `ASSAULT_MASS` table from the same Contact band.
    Everything downstream is the shipped code: `_muster` details the crew,
    `_detail` tops it up cheapest trip first, `_assign` keeps its veto for every
    place that is not being massed for, and `_Demand.committed` floors the
    demand by what is already going.

    That last clause is why this arm is here. #181's hysteresis is a property of
    `_Demand`, so extending `_mass` extends the hysteresis with it — an Objective
    concentration cannot be shed by a flickering Contact, for free and without a
    line of new anti-thrash machinery.

    It is not the one-method change it looks like, and `_detail` is why. The
    shipped `_muster` details each wanted place in turn and merges the crews with
    `detailed |= crew`, which is safe while `wanted` holds one enemy Base and
    unsafe the moment it holds two places: `_detail` seeds its crew from the bid
    without consulting `spoken_for`, so the second place's seed silently
    overwrites a Squad the first place had already been given. Measured on Board
    A before the override below — the Objective massed two, then the Base's turn
    reclaimed one of them and the plan issued one Squad while its own trace said
    "massed 1, 2 wanted". The override is the second half of this arm's cost.
    """

    def _mass(self, observation: Observation) -> dict[str, planner._Demand]:
        """What every contested place's attack must arrive with."""
        seen = {contact.at: contact for contact in observation.contacts}
        committed: dict[str, int] = {}
        for squad in observation.squads:
            if squad.order in OFFENSIVE:
                committed[squad.place] = committed.get(squad.place, 0) + 1
        places = [
            base.id for base in self.map_manifest.bases if base.side != observation.for_side
        ] + [
            objective.id
            for objective in self.map_manifest.objectives
            if observation.owners.get(objective.id, "") != observation.for_side
        ]
        return {
            place: planner._Demand(  # noqa: SLF001
                banded=self._demanded(seen.get(place)),
                committed=committed.get(place, 0),
            )
            for place in sorted(places)
        }

    def _detail(
        self,
        options: list[planner._Option],
        bid: dict[str, planner._Option],
        place: str,
        needed: int,
        spoken_for: dict[str, planner._Option],
    ) -> dict[str, planner._Option]:
        """The shipped `_detail`, with the bid's seed held to `spoken_for` too.

        One line changed — the seed comprehension gains `and squad not in
        spoken_for` — and it is the line that makes a second massed place safe.
        """
        crew = {
            squad: option
            for squad, option in bid.items()
            if option.place == place and squad not in spoken_for
        }
        for option in options:
            if len(crew) >= needed:
                break
            if option.place != place or option.squad in crew or option.squad in spoken_for:
                continue
            crew[option.squad] = option
        return crew


# --------------------------------------------------------------------- arm (c)


@dataclass(frozen=True, slots=True)
class Detachment:
    """A scratch grouping of owned Squads the Commander orders as one thing.

    Working label only. "Platoon" is not available: CONTEXT.md's **Contact**
    entry already spends the word as an echelon *band* and says in terms that a
    band "is a size estimate, never a unit of command", and `ECHELON_THREAT` and
    `ASSAULT_MASS` are both keyed on it. Naming the new object Platoon would make
    `ASSAULT_MASS["platoon"] == 3` read as "a Platoon is three Squads", which is
    not what it says. The real term is the human's to pick.
    """

    id: str
    members: frozenset[str]
    # Where the Commander told it to go, or ("", "") before it has been told.
    kind: str = ""
    place: str = ""


@dataclass(slots=True)
class EchelonScorer(Baseline):
    """The shipped scorer with ADR-0027's mass switched off, for arm (c) to run.

    One Detachment per Place, always — which is #177's own claim about what
    moving the Commander up a level does to the veto, made true rather than
    argued. The Detachment is composed to the size doctrine wants, so a demand of
    two *Detachments* on top of that would send twice the force: measured before
    this class existed, arm (c) put three Squads on a Base a squad band wants two
    for, and the extra Squad was ADR-0027's mass double-counting the composition.

    `_muster`, `_detail` and `_Demand` all become dead weight at this level. That
    is a subtraction, and the complexity count records it as one.
    """

    def _demanded(self, contact: object) -> int:
        """One of whatever is being commanded, whatever the band says."""
        return 1


@dataclass(slots=True)
class DetachmentLayer:
    """Arm (c): the planner commands Detachments, and Squads only through them.

    Not a subclass. The shipped scorer runs unmodified *inside* this, over an
    Observation whose `squads` are Detachments: a composed Detachment appears as
    one entry, sized at its members' men and standing at the place it musters
    on. So the one-per-Place veto is untouched and becomes correct — one
    Detachment per Objective is the rule it was always reaching for — and
    concentration stops being a planner question at all. It is a composition
    question, answered before the scorer runs.

    What the layer owns is the composition and the lifetime, and both are state:
    this object is not a pure function of an Observation the way `UtilityPlanner`
    is, which is ADR-0004's purity claim broken and the largest single entry in
    this arm's complexity column.

    Composition: for each contested place doctrine wants more than one Squad for,
    the nearest free Squads are grouped. Dissolution: membership below two, or
    the place changing hands. Once formed, membership does not move — which is
    the whole of this arm's anti-thrash property, and it is structural rather
    than a margin anyone tuned.
    """

    inner: Baseline
    _formed: dict[str, Detachment] = field(default_factory=dict)
    _minted: int = 0

    @property
    def map_manifest(self) -> object:
        """The authored map, for callers that reach through to the geometry."""
        return self.inner.map_manifest

    def _places(self, side: str) -> set[str]:
        """Every place a Detachment could be formed against — never our own Base."""
        return {objective.id for objective in self.inner.map_manifest.objectives} | {
            base.id for base in self.inner.map_manifest.bases if base.side != side
        }

    def _compose(self, observation: Observation) -> None:
        """Form what doctrine wants, dissolve what no longer holds together."""
        alive = {squad.id for squad in observation.squads}
        # Dissolution, first: a Detachment whose Objective we now hold has done
        # what it was formed for, and one reduced to a single Squad is a Squad.
        for one in list(self._formed.values()):
            members = one.members & alive
            taken = observation.owners.get(one.place, "") == observation.for_side
            if len(members) < 2 or taken:
                del self._formed[one.id]
            elif members != one.members:
                self._formed[one.id] = replace(one, members=members)

        spoken_for = {squad for one in self._formed.values() for squad in one.members}
        standing = {squad.id: squad for squad in observation.squads}
        wanted = {
            place: demanded(contact)
            for place, contact in contested(observation, self._places(observation.for_side)).items()
            if demanded(contact) > 1
        }
        already = {one.place for one in self._formed.values()}
        for place, want in sorted(wanted.items(), key=lambda pair: (-pair[1], pair[0])):
            if place in already:
                continue
            free = sorted(
                (squad for squad in observation.squads if squad.id not in spoken_for),
                key=lambda squad: (self._km(standing[squad.id].at, place), squad.id),
            )
            if len(free) < want:
                continue
            self._minted += 1
            crew = frozenset(squad.id for squad in free[:want])
            self._formed[f"{observation.for_side}-D{self._minted}"] = Detachment(
                id=f"{observation.for_side}-D{self._minted}", members=crew, place=place
            )
            spoken_for |= crew

    def _km(self, origin: str, target: str) -> float:
        reach = self.inner._reach  # noqa: SLF001
        start = origin if origin in reach else target
        return reach[start][target]

    def _muster_place(self, observation: Observation, one: Detachment) -> str:
        """Where a Detachment stands, as one thing: the rally its members form on."""
        where = {
            squad.id: squad.at
            for squad in observation.squads
            if squad.id in one.members and squad.at
        }
        if not where:
            return ""
        if len(where) == 1 or one.place == "":
            return next(iter(where.values()))
        return rally_point(self.inner, where, one.place)

    def _echelon_view(self, observation: Observation) -> Observation:
        """The same picture, with Detachments where the Squads were."""
        grouped = {squad for one in self._formed.values() for squad in one.members}
        views = [
            SquadView(
                id=one.id,
                squad_type="rifle",
                size=SQUAD_MEN * len(one.members),
                order=one.kind,
                place=one.place,
                at=self._muster_place(observation, one),
            )
            for one in sorted(self._formed.values(), key=lambda one: one.id)
        ]
        views += [squad for squad in observation.squads if squad.id not in grouped]
        return replace(observation, squads=tuple(views))

    def plan(self, observation: Observation) -> planner.Plan:
        """Compose, plan at the echelon, then say it in Squads."""
        self._compose(observation)
        echelon = self._echelon_view(observation)
        upstairs = self.inner.plan(echelon)

        commands: list[Command] = []
        for command in upstairs.commands:
            if command.name != "order":
                commands.append(command)
                continue
            one = self._formed.get(command.args["squad"])
            if one is None:
                commands.append(command)
                continue
            self._formed[one.id] = replace(
                one, kind=command.args["order"], place=command.args["place"]
            )
            # What the wire carries. Squad-grained today, so one Detachment Order
            # becomes N Commands; with a Detachment verb on the port it is one.
            commands += [
                Command(
                    name="order",
                    side=command.side,
                    args={
                        "squad": squad,
                        "order": command.args["order"],
                        "place": command.args["place"],
                    },
                )
                for squad in sorted(one.members)
            ]
        return planner.Plan(commands=tuple(commands), decisions=upstairs.decisions)

    def detachment_of(self, squad: str) -> Detachment | None:
        """Which Detachment a Squad belongs to, or None while it is on its own."""
        return next((one for one in self._formed.values() if squad in one.members), None)
