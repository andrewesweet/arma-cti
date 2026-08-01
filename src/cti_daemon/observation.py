"""The strategic picture a Commander plans against — and only its own.

An observation is what **one** Commander may know at one moment: which side
holds each Objective, what that Commander has to spend, and where its own Squads
are and what they were told to do. It is deliberately the same set ADR-0008
persists — strategic state, nothing tactical — so the Phase-2 snapshot schema is
this shape rather than a second one, and a planner tested against a closed schema
is tested against the one that survives a resume.

Excluded on purpose, not for want of a field: exact positions, health, ammo,
vehicle damage and AI knowledge. A Squad's position is the Place it is standing
on, because that is the resolution a Commander reasons at (ADR-0020).

Excluded on purpose for a second reason (#27): the enemy. ADR-0012's Commander
symmetry covers knowing as well as commanding, so there is no observation
carrying both sides for anything to obtain — not even by accident, which matters
because the planner reads campaign state in-process rather than over the wire,
and a projection applied at the wire is one it walks straight past. Funds are
therefore a number rather than a table, and a `SquadView` carries no side: an
enemy Squad and enemy Funds have nowhere in this schema to live. What a
Commander learns of the enemy arrives as **Contacts** (`CONTEXT.md`), which is
#28's shape, not this one.

The one enemy-shaped fact that does cross is the enemy Base's HQ, and it was
decided with #27 rather than carved out afterwards (ADR-0012's amendment, and
`docs/mvp-scope.md`): the two win conditions are the scoreboard rather than
intelligence. Ownership and HQ status are therefore public in every view, the
one belonging to nobody included.

Assembled here rather than reported wholesale by the world: ownership, Funds and
Orders are the daemon's own (ADR-0012), and only the head count and the ground
underfoot are facts the world alone can see.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

from cti_daemon import protocol
from cti_daemon.commands import OWNERS
from cti_daemon.contacts import ASSETS, ECHELONS, POSTURE_ORDER, Contact
from cti_daemon.squads import ORDERS

if TYPE_CHECKING:
    from cti_daemon.economy import EconomyTable
    from cti_daemon.manifest import MapManifest

# What a `callExtension` return may carry in one call (ADR-0004). An observation
# that does not fit is an observation to make smaller, never a reason to invent
# a chunking protocol in passing — Phase 2 decides chunking against the snapshot
# schema's size profile.
RETURN_CAP_BYTES = 10_240

# Where `cti_fnc_commanderView` refuses to go quietly: nine tenths of the cap,
# so a view that is merely close to truncating fails a run rather than a Play
# Session. The SQF literal is the one that fires; this one is what the budget
# below is measured against, and a test holds the two together.
REPORT_GUARD_BYTES = 9_216

# Each Base's HQ, as the wire says it. Here rather than beside the Campaign that
# razes one, because this is the vocabulary of the document — and the budget
# below has to know how wide the widest word is.
INTACT: Final = "intact"
DESTROYED: Final = "destroyed"

# The view that belongs to no side: the public facts alone. It is what the server
# receives, because the server needs ownership to paint markers and nothing else
# — and handing it a Commander's view would put an unprojected picture back on
# the wire for #19's audit to find.
PUBLIC: Final = ""


@dataclass(frozen=True, slots=True)
class SquadView:
    """One of the observing Commander's own Squads, as it sees it."""

    id: str
    squad_type: str
    size: int
    order: str
    # The Place its Order names: an Objective id, a Base id, or empty.
    place: str
    # Where it is, to the nearest authored place: an Objective id, a Base id, or
    # empty for open ground between them.
    at: str


@dataclass(frozen=True, slots=True)
class Observation:
    """Everything one Commander may know, at one in-game moment."""

    at_time: float
    # Public to both sides: the win conditions are the scoreboard rather than
    # intelligence, and a Campaign whose score nobody can read is unplayable.
    owners: dict[str, str]
    # The other half of that scoreboard (#35): each Base's HQ, intact or
    # destroyed. Public for the same reason and in the same shape — a place
    # mapped to a status — because Domination and Decapitation are the two
    # conditions and neither is a secret. It grows with the map rather than with
    # the Campaign, and the map has one Base per side, so this is fifty-odd
    # bytes and stays fifty-odd bytes.
    hq: dict[str, str] = field(default_factory=dict)
    # Whose view this is, or PUBLIC for the view that is nobody's.
    for_side: str = PUBLIC
    # That side's own Funds. None in the public view — absent because there is
    # no side whose Funds these would be, not because they are zero.
    funds: int | None = None
    # That side's own Squads.
    squads: tuple[SquadView, ...] = ()
    # What that side has seen of the other (#28). There is no `ContactView`
    # beside `SquadView` because there is nothing for one to strip: a
    # `SquadView` exists to drop a Squad's side, and a Contact is assembled
    # already carrying no enemy identity at all. A field-for-field copy would
    # be a second definition of the same thing and a translation step whose
    # only job is to be the identity.
    contacts: tuple[Contact, ...] = ()

    def __post_init__(self) -> None:
        """Refuse a picture belonging to nobody that carries somebody's secrets.

        The projection is the point of this type (#27), so a mismatch is a bug
        to raise on rather than a field to leave empty and hope about.
        """
        if self.for_side == PUBLIC and (self.funds is not None or self.squads or self.contacts):
            message = "the public picture carries no side's Funds, Squads or Contacts"
            raise ValueError(message)
        if self.for_side != PUBLIC and self.funds is None:
            message = f"{self.for_side}'s picture must carry its own Funds"
            raise ValueError(message)


def serialise(observation: Observation) -> dict[str, Any]:
    """Render an observation as the document that crosses the wire."""
    document: dict[str, Any] = {
        "at": observation.at_time,
        "owners": observation.owners,
        "hq": observation.hq,
    }
    if observation.for_side == PUBLIC:
        return document
    document["side"] = observation.for_side
    document["funds"] = observation.funds
    document["squads"] = [
        {
            "id": squad.id,
            "type": squad.squad_type,
            "size": squad.size,
            "order": squad.order,
            "place": squad.place,
            "at": squad.at,
        }
        for squad in observation.squads
    ]
    document["contacts"] = [
        {
            "at": contact.at,
            "echelon": contact.echelon,
            "posture": contact.posture,
            "assets": list(contact.assets),
            "age": contact.age,
        }
        for contact in observation.contacts
    ]
    return document


# The worst case a map can put on the wire, term by term (#26). Each is the
# widest value its own vocabulary admits, taken from where that vocabulary is
# defined rather than restated here, so a new asset or a longer Order kind
# widens the budget by itself.
_WORST_ECHELON: Final = max((name for _, name in ECHELONS), key=len)
_WORST_POSTURE: Final = max(POSTURE_ORDER, key=len)
_WORST_ASSETS: Final = tuple(asset for asset, _ in ASSETS)
_WORST_ORDER: Final = max(ORDERS, key=len)
_WORST_OWNER: Final = max(OWNERS, key=len)
# A Campaign runs for hours rather than days and an age is rounded to a tenth
# (`contacts.AGE_PLACES`), so this is the longest a clock reading gets said in.
_WORST_CLOCK: Final = 9_999.9
# Squad ids number from the first ever bought, not from the ones still alive, so
# a long Campaign's live roster wears four-digit ordinals.
_WORST_ORDINAL: Final = 1_000
# `cti_fnc_commanderView` correlates on `view-<side>-<time>`.
_WORST_REQUEST_ID: Final = "view-WEST-99999"


def worst_case(map_manifest: MapManifest, table: EconomyTable, squads: int) -> Observation:
    """Build the largest Observation a map can produce at `squads` Squads a side.

    Worst case in every term the schema admits rather than a plausible mid-game
    moment: every Objective owned, every Base's HQ destroyed, a Contact standing
    at every place at the heaviest echelon and posture with every asset named,
    and each Squad wearing the longest authored Squad type with the longest
    authored place id both in its Order and under its feet. A real Campaign
    cannot exceed this, so a map that fits it fits.
    """
    places = tuple(objective.id for objective in map_manifest.objectives)
    places += tuple(base.id for base in map_manifest.bases)
    widest = max(places, key=len)
    return Observation(
        at_time=_WORST_CLOCK,
        owners={objective.id: _WORST_OWNER for objective in map_manifest.objectives},
        hq={base.id: DESTROYED for base in map_manifest.bases},
        for_side="WEST",
        funds=999_999,
        squads=tuple(
            SquadView(
                id=f"WEST-{_WORST_ORDINAL + index}",
                squad_type=max((squad.id for squad in table.squads), key=len),
                size=99,
                order=_WORST_ORDER,
                place=widest,
                at=widest,
            )
            for index in range(squads)
        ),
        contacts=tuple(
            Contact(
                at=place,
                echelon=_WORST_ECHELON,
                posture=_WORST_POSTURE,
                assets=_WORST_ASSETS,
                age=_WORST_CLOCK,
            )
            for place in places
        ),
    )


def worst_case_bytes(map_manifest: MapManifest, table: EconomyTable, squads: int) -> int:
    """Measure what that Observation costs on the wire, reply envelope included."""
    document = serialise(worst_case(map_manifest, table, squads))
    return len(protocol.encode(protocol.accepted(_WORST_REQUEST_ID, document)))


def squad_ceiling(map_manifest: MapManifest, table: EconomyTable) -> int | None:
    """How many Squads a side a map may carry before the guard trips.

    `None` when the map does not fit even with no Squads at all — which is a
    different answer from nought, and the answer a big enough island gives once
    Contacts are counted, because they are keyed by place (#28) and so grow with
    the map rather than with either force.
    """
    if worst_case_bytes(map_manifest, table, 0) >= REPORT_GUARD_BYTES:
        return None
    low, high = 0, 1
    while worst_case_bytes(map_manifest, table, high) < REPORT_GUARD_BYTES:
        low, high = high, high * 2
    while high - low > 1:
        middle = (low + high) // 2
        if worst_case_bytes(map_manifest, table, middle) < REPORT_GUARD_BYTES:
            low = middle
        else:
            high = middle
    return low


def parse(document: dict[str, Any]) -> Observation:
    """Rebuild an observation from its wire document."""
    at_time = document["at"]
    owners = dict(document["owners"])
    hq = dict(document.get("hq", {}))
    for_side = document.get("side", PUBLIC)
    if for_side == PUBLIC:
        return Observation(at_time=at_time, owners=owners, hq=hq)
    return Observation(
        at_time=at_time,
        owners=owners,
        hq=hq,
        for_side=for_side,
        funds=document["funds"],
        squads=tuple(
            SquadView(
                id=squad["id"],
                squad_type=squad["type"],
                size=squad["size"],
                order=squad["order"],
                place=squad["place"],
                at=squad["at"],
            )
            for squad in document["squads"]
        ),
        contacts=tuple(
            Contact(
                at=contact["at"],
                echelon=contact["echelon"],
                posture=contact["posture"],
                assets=tuple(contact["assets"]),
                age=contact["age"],
            )
            for contact in document["contacts"]
        ),
    )
