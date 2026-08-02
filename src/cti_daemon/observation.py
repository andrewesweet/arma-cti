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

What one of these costs on the wire, and how many Squads a map can carry before
that cost trips the engine's return cap, is `cti_daemon.budget` (#78). That is a
boundary question — it measures an envelope-encoded document against a limit the
engine imposes — and this module, which says what a Commander may know, should
not have to import the transport to answer it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final

from cti_daemon.contacts import Contact

# Each Base's HQ, as the wire says it. Here rather than beside the Campaign that
# razes one, because this is the vocabulary of the document.
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
