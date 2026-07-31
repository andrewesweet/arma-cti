"""What one side has seen of the other, and how little that is allowed to say.

A Contact describes an observation, never the enemy behind it (`CONTEXT.md`).
Nothing here is keyed by, or can be traced to, an enemy Squad: a sighting names a
place and a perceived kind, and what comes out is a band. That is structural
rather than a rule to keep — there is no Squad id in this module to leak.

The world contributes the sightings, because the engine's knowledge model is the
one thing only it can see. Banding them is a rule, and rules live here where they
are testable (ADR-0012).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

# What an observed count is reported as. Bands rather than a number, so several
# of our Squads in one place read as a platoon without revealing which ones.
# Ascending, read as "this many or more".
ECHELONS: Final = ((25, "company"), (9, "platoon"), (4, "squad"), (1, "team"))

# What each perceived kind says about how a place moves. The kinds are
# `BIS_fnc_objectType`'s own vocabulary rather than a classification table of
# ours, and anything absent — every soldier type, a static gun, a thing nobody
# made out — leaves the place on foot.
#
# `docs/mvp-scope.md` puts armour and air out of MVP entirely, so only `foot`
# and `motorised` are reachable until Phase 4 adds vehicles. The rest is defined
# now so the schema #18's map UI renders does not churn when it arrives, and is
# unexercisable rather than untested.
POSTURES: Final = {
    "Motorcycle": "motorised",
    "Car": "motorised",
    "WheeledAPC": "mechanised",
    "TrackedAPC": "mechanised",
    "Tank": "armoured",
    "Helicopter": "air",
    "Plane": "air",
}
ON_FOOT: Final = "foot"

# Heaviest wins, because what a Commander needs of a place is what it can do
# rather than what most of it is. Ascending.
POSTURE_ORDER: Final = (ON_FOOT, "motorised", "mechanised", "armoured", "air")

# The things worth naming on their own, beyond how the place moves. Reported in
# this order rather than in sighting order, so two reports of the same place
# read the same. `AT` and `MG` are a weapons Squad's teams and are what MVP can
# produce; the rest waits on Phase 4 with the postures above.
ASSETS: Final = (
    ("AT", ("AT",)),
    ("MG", ("MG",)),
    ("static", ("StaticWeapon",)),
    ("IFV", ("WheeledAPC", "TrackedAPC")),
    ("MBT", ("Tank",)),
    ("air", ("Helicopter", "Plane")),
)


@dataclass(frozen=True, slots=True)
class Sighting:
    """One enemy thing one side's leaders currently know about."""

    # The place it was seen at: an Objective id or a Base id.
    at: str
    # What it appeared to be — `BIS_fnc_objectType` on the *perceived* type, so
    # an unrecognised contact is honestly unidentified rather than silently
    # exact.
    kind: str
    # Seconds since it was actually seen, as the engine's knowledge model has it.
    age: float


@dataclass(frozen=True, slots=True)
class Contact:
    """What one side has seen at one place, as its Commander receives it."""

    at: str
    echelon: str
    posture: str
    assets: tuple[str, ...]
    age: float


def echelon_of(count: int) -> str:
    """Band an observed count.

    The *observed* count, so seeing three of eight reports a team: a Commander
    is left under-informed rather than over-, which needs no extra machinery and
    is the right direction to be wrong in.
    """
    for floor, name in ECHELONS:
        if count >= floor:
            return name
    return ""


def posture_of(kinds: tuple[str, ...]) -> str:
    """Read how a place moves off the heaviest thing seen in it."""
    return max(
        (POSTURES.get(kind, ON_FOOT) for kind in kinds),
        key=POSTURE_ORDER.index,
        default=ON_FOOT,
    )


def assets_of(kinds: tuple[str, ...]) -> tuple[str, ...]:
    """Name the things at a place worth naming on their own."""
    seen = set(kinds)
    return tuple(asset for asset, kinds_named in ASSETS if seen.intersection(kinds_named))


@dataclass(slots=True)
class Contacts:
    """Every side's picture of the other, keyed by place.

    Bounded by the map rather than by enemy force size — ten places on Stratis —
    so a newer sighting supersedes an older one and no ageing rule is needed.
    """

    _seen: dict[tuple[str, str], _Record] = field(default_factory=dict)

    def report(
        self,
        side: str,
        at_time: float,
        seen: tuple[Sighting, ...],
        observed: tuple[str, ...],
    ) -> None:
        """Fold one side's sightings into its picture.

        `observed` is the places its leaders actually looked at, and it is the
        whole of the removal rule: absence of contact is not evidence, observed
        absence is. A place nobody looked at keeps the Contact it had, which is
        what carries a Commander's picture past the engine's 120 s decay.
        """
        by_place: dict[str, list[Sighting]] = {}
        for sighting in seen:
            by_place.setdefault(sighting.at, []).append(sighting)
        for place in observed:
            if place not in by_place:
                self._seen.pop((side, place), None)
        for place, sightings in by_place.items():
            kinds = tuple(sighting.kind for sighting in sightings)
            self._seen[side, place] = _Record(
                echelon=echelon_of(len(sightings)),
                posture=posture_of(kinds),
                assets=assets_of(kinds),
                # When it was actually seen, not when it was reported: that is
                # what lets a Contact outlive the engine forgetting it.
                seen_at=at_time - min(sighting.age for sighting in sightings),
            )

    def of(self, side: str, at_time: float) -> tuple[Contact, ...]:
        """One side's Contacts, aged to the moment it is asking."""
        return tuple(
            Contact(
                at=place,
                echelon=record.echelon,
                posture=record.posture,
                assets=record.assets,
                age=at_time - record.seen_at,
            )
            for (owner, place), record in self._seen.items()
            if owner == side
        )


@dataclass(slots=True)
class _Record:
    """One place's sighting, held in the terms it will be aged from."""

    echelon: str
    posture: str
    assets: tuple[str, ...]
    seen_at: float
