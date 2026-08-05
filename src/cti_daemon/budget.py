"""What a picture may cost on the wire, and how much of a map fits in one.

A boundary concern, not a picture one (#78). It measures the envelope-encoded
cost of an `Observation` against the engine's `callExtension` return cap, so it
knows about `protocol` and about a limit the engine imposes — neither of which
is anything `cti_daemon.observation` should have to know to say what a Commander
may see. This module imports `observation`; `observation` imports nothing from
here, and nothing from the transport layer at all.

The one number that has to reach SQF reaches it as generated data through
`addons/main/generated/command-schema.json` (ADR-0017), which is the seam that
exists for exactly this: `cti_fnc_daemonCall` reads the guard rather than
carrying a hand-copied literal held equal to this one by a source-grep test.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from cti_daemon import protocol
from cti_daemon.commands import OWNERS, SIDES
from cti_daemon.contacts import ASSETS, ECHELONS, POSTURE_ORDER, Contact
from cti_daemon.observation import DESTROYED, Observation, SquadView, serialise
from cti_daemon.squads import ORDERS

if TYPE_CHECKING:
    from cti_daemon.economy import EconomyTable
    from cti_daemon.manifest import MapManifest

# What a `callExtension` return may carry in one call (ADR-0004). An observation
# that does not fit is an observation to make smaller, never a reason to invent
# a chunking protocol in passing — Phase 2 decides chunking against the snapshot
# schema's size profile.
RETURN_CAP_BYTES: Final = 10_240

# Where the world refuses to go quietly: nine tenths of the cap, so a reply that
# is merely close to truncating fails a run rather than a Play Session. The
# guard that fires is `cti_fnc_daemonCall`'s, and since #78 it reads this number
# out of the exported schema rather than repeating it.
REPORT_GUARD_BYTES: Final = 9_216

# The worst case a map can put on the wire, term by term (#26). Each is the
# widest value its own vocabulary admits, taken from where that vocabulary is
# defined rather than restated here, so a new asset or a longer Order kind
# widens the budget by itself.
_WORST_ECHELON: Final = max((name for _, name in ECHELONS), key=len)
_WORST_POSTURE: Final = max(POSTURE_ORDER, key=len)
_WORST_ASSETS: Final = tuple(asset for asset, _ in ASSETS)
_WORST_ORDER: Final = max(ORDERS, key=len)
_WORST_OWNER: Final = max(OWNERS, key=len)
# The side whose name costs the most, like every other term here taken from
# where its vocabulary is defined rather than restated (#152): it is the
# observation's `for_side`, and Squad ids wear it as their stem.
_WORST_SIDE: Final = max(SIDES, key=len)
# A Campaign runs for hours rather than days, so this is the longest a clock
# reading gets said in.
_WORST_CLOCK: Final = 9_999.9
# An age is truncated to whole seconds (#134), so it is the same span said in
# four characters rather than six.
_WORST_AGE: Final = 9_999
# Squad ids number from the first ever bought, not from the ones still alive, so
# a long Campaign's live roster wears four-digit ordinals.
_WORST_ORDINAL: Final = 1_000
# The dearest map position a Squad can be standing at (#175). Not taken from the
# manifest, because a Squad may march anywhere on the terrain and the manifest
# only says where the Places are: this is the map's own extent, and Altis —
# 30,720 m on a side — is the largest terrain the engine ships. Five digits an
# axis, and every five-digit pair costs the wire the same, so a bigger world
# than Altis would have to arrive before this understates anything.
_WORST_POSITION: Final = (30_720, 30_720)
# `cti_fnc_commanderView` correlates on `view-<side>-<time>`.
_WORST_REQUEST_ID: Final = f"view-{_WORST_SIDE}-99999"


def worst_case(
    map_manifest: MapManifest, table: EconomyTable, *, squads_per_side: int
) -> Observation:
    """Build the largest Observation a map can produce at `squads_per_side` a side.

    Worst case in every term the schema admits rather than a plausible mid-game
    moment: every Objective owned, every Base's HQ destroyed, a Contact standing
    at every place at the heaviest echelon and posture with every asset named,
    and each Squad wearing the longest authored Squad type with the longest
    authored place id both in its Order and under its feet, standing at the
    dearest position the widest terrain admits. A real Campaign cannot exceed
    this, so a map that fits it fits.
    """
    places = tuple(objective.id for objective in map_manifest.objectives)
    places += tuple(base.id for base in map_manifest.bases)
    widest = max(places, key=len)
    return Observation(
        at_time=_WORST_CLOCK,
        owners={objective.id: _WORST_OWNER for objective in map_manifest.objectives},
        hq={base.id: DESTROYED for base in map_manifest.bases},
        for_side=_WORST_SIDE,
        funds=999_999,
        squads=tuple(
            SquadView(
                id=f"{_WORST_SIDE}-{_WORST_ORDINAL + index}",
                squad_type=max((squad.id for squad in table.squads), key=len),
                size=99,
                order=_WORST_ORDER,
                place=widest,
                at=widest,
                pos=_WORST_POSITION,
            )
            for index in range(squads_per_side)
        ),
        contacts=tuple(
            Contact(
                at=place,
                echelon=_WORST_ECHELON,
                posture=_WORST_POSTURE,
                assets=_WORST_ASSETS,
                age=_WORST_AGE,
            )
            for place in places
        ),
    )


def worst_case_bytes(
    map_manifest: MapManifest, table: EconomyTable, *, squads_per_side: int
) -> int:
    """Measure what that Observation costs on the wire, reply envelope included."""
    document = serialise(worst_case(map_manifest, table, squads_per_side=squads_per_side))
    return len(protocol.encode(protocol.accepted(_WORST_REQUEST_ID, document)))


def squad_ceiling(map_manifest: MapManifest, table: EconomyTable) -> int | None:
    """How many Squads a side a map may carry before the guard trips.

    `None` when the map does not fit even with no Squads at all — which is a
    different answer from nought, and the answer a big enough island gives once
    Contacts are counted, because they are keyed by place (#28) and so grow with
    the map rather than with either force.
    """
    if worst_case_bytes(map_manifest, table, squads_per_side=0) >= REPORT_GUARD_BYTES:
        return None
    low, high = 0, 1
    while worst_case_bytes(map_manifest, table, squads_per_side=high) < REPORT_GUARD_BYTES:
        low, high = high, high * 2
    while high - low > 1:
        middle = (low + high) // 2
        if worst_case_bytes(map_manifest, table, squads_per_side=middle) < REPORT_GUARD_BYTES:
            low = middle
        else:
            high = middle
    return low
