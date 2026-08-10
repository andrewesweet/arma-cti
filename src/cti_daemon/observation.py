"""The strategic picture a Commander plans against — and only its own.

An observation is what **one** Commander may know at one moment: which side
holds each Objective, what that Commander has to spend, and where its own Squads
are and what they were told to do. It is deliberately the same set ADR-0008
persists — strategic state, nothing tactical — so the Phase-2 snapshot schema is
this shape rather than a second one, and a planner tested against a closed schema
is tested against the one that survives a resume.

Excluded on purpose, not for want of a field: health, ammo, vehicle damage and
AI knowledge. A Squad's position is the Place it is standing on, because that is
the resolution a Commander *reasons* at (ADR-0020).

With one exception, and it is about seeing rather than reasoning (#175,
ADR-0058, human ruling of 2026-08-04). A `SquadView` carries `pos` beside `at`:
the map position of the Commander's **own** Squad, in whole metres. `at` is
Place-grained and stays so, and every reader of it — the planner, the port's
rules, the Contacts the fog rule is actually about — is untouched. The reason is
that a Place-grained `at` is empty for the whole march between two Places, so a
marching Squad, a pinned Squad and a Squad wiped to the last man were the same
picture on the Commander's map: absent. Knowing where his own Squads are is not
enemy intelligence, and both Commanders receive the same field, so ADR-0012's
symmetry is unmoved. There is deliberately no such field on a `Contact`.

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
Orders are the daemon's own (ADR-0012). The facts the world alone can see are
the head count, the ground underfoot, the sightings its leaders report (#28)
and an HQ falling (#33).

What one of these costs on the wire, and how many Squads a map can carry before
that cost trips the engine's return cap, is `cti_daemon.budget` (#78). That is a
boundary question — it measures an envelope-encoded document against a limit the
engine imposes — and this module, which says what a Commander may know, should
not have to import the transport to answer it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

from cti_daemon.contacts import Contact

if TYPE_CHECKING:
    from collections.abc import Callable

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
    # Empty for a composition-unassigned player-led Squad, and that absence is
    # the representation CONTEXT.md's amended **Observation** ratified: "one
    # that is composition-unassigned carries no composition type — an absence
    # the Commander reads as the shell it may fill" (ADR-0070). It is
    # unambiguous in a view because every *bought* Squad names the type it was
    # bought as; the flag that keeps the two states apart in the rules lives on
    # `squads.Squad`, where the ambiguity would otherwise have been.
    squad_type: str
    size: int
    order: str
    # The Place its Order names: an Objective id, a Base id, or empty.
    place: str
    # Where it is, to the nearest authored place: an Objective id, a Base id, or
    # empty for open ground between them.
    at: str
    # And where it is on the map, as `[east, north]` in whole metres (#175,
    # ADR-0058) — `()` for a Squad the world has not yet reported standing, so
    # a Commander is shown nothing rather than a coordinate nobody has observed.
    # It is up to one report — five seconds — behind, which at infantry pace is
    # a marker trailing its Squad by tens of metres on a strategic map:
    # `cti_fnc_commanderView` sets the rate and states the consequence.
    pos: tuple[int, ...] = ()
    # Whether this is a shell whose player has disconnected before its first
    # fill (ADR-0070 ruling 7). Beside the absent composition type rather than
    # folded into it, because the two answer different questions: the empty
    # type says the Squad may be filled, and this says it may not be filled
    # *yet*. Without it a Commander — the AI one included — cannot tell an
    # eligible shell from an ineligible one, and ruling 2's preference for
    # filling an active shell over a net-new Purchase is unstateable. False for
    # every other Squad, which is what it has always been.
    suspended: bool = False


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


# The document's own keys, declared once for the same reason the records below
# are (#163). `serialise` wrote them and `parse` read them as literals, which is
# two copies of a wire contract agreeing by eye; a Commander's view splits into
# the part every picture carries and the part only a side's does, because that
# split *is* the projection `__post_init__` enforces.
AT_KEY: Final = "at"
OWNERS_KEY: Final = "owners"
HQ_KEY: Final = "hq"
SIDE_KEY: Final = "side"
FUNDS_KEY: Final = "funds"
SQUADS_KEY: Final = "squads"
CONTACTS_KEY: Final = "contacts"

PUBLIC_FIELDS: Final[tuple[str, ...]] = (AT_KEY, OWNERS_KEY, HQ_KEY)
SIDE_FIELDS: Final[tuple[str, ...]] = (SIDE_KEY, FUNDS_KEY, SQUADS_KEY, CONTACTS_KEY)
DOCUMENT_FIELDS: Final[tuple[str, ...]] = PUBLIC_FIELDS + SIDE_FIELDS

# The wire names of the two repeated records, declared once (#87). `serialise`
# and `parse` both read this, so a rename is one edit rather than two held in
# step by a round-trip test noticing afterwards. Wire name first because that is
# the side that is fixed: the attribute is ours to rename, the key is not.
SQUAD_FIELDS: Final[tuple[tuple[str, str], ...]] = (
    ("id", "id"),
    ("type", "squad_type"),
    ("size", "size"),
    ("order", "order"),
    ("place", "place"),
    ("at", "at"),
    # Last because it arrived last, and because the map reads by name: the
    # order here is the document's order and nothing depends on it but the
    # export's own test.
    ("pos", "pos"),
    ("suspended", "suspended"),
)
CONTACT_FIELDS: Final[tuple[tuple[str, str], ...]] = (
    ("at", "at"),
    ("echelon", "echelon"),
    ("posture", "posture"),
    # A tuple in the record and a list on the wire: JSON has one sequence.
    ("assets", "assets"),
    ("age", "age"),
)


def _rendered(record: object, fields: tuple[tuple[str, str], ...]) -> dict[str, Any]:
    """Render one record as its wire object.

    A tuple field becomes a list because JSON has one sequence; `_built` puts it
    back. The pair is the whole translation, which is why neither of them names
    a field.
    """
    rendered: dict[str, Any] = {}
    for key, attribute in fields:
        value = getattr(record, attribute)
        rendered[key] = list(value) if isinstance(value, tuple) else value
    return rendered


def _built[T](
    record: Callable[..., T], document: dict[str, Any], fields: tuple[tuple[str, str], ...]
) -> T:
    """Rebuild one record from its wire object."""
    values: dict[str, Any] = {}
    for key, attribute in fields:
        value = document[key]
        values[attribute] = tuple(value) if isinstance(value, list) else value
    return record(**values)


def exported() -> dict[str, list[str]]:
    """Render the document's field names, as the map UI reads them.

    Names only, for the reason `cti_daemon.report.exported` gives on the inbound
    half: what a field must *be* is judged in Python, and a copy of those rules
    in SQF would be a second answer to the same question (ADR-0012). This is the
    outbound half of that seam (#163) — the map UI reads these keys by literal,
    and `tests/unit/test_observation_schema.py` holds its literals to this list.
    """
    return {
        "document": list(DOCUMENT_FIELDS),
        "squad": [key for key, _ in SQUAD_FIELDS],
        "contact": [key for key, _ in CONTACT_FIELDS],
    }


def serialise(observation: Observation) -> dict[str, Any]:
    """Render an observation as the document that crosses the wire."""
    document: dict[str, Any] = {
        AT_KEY: observation.at_time,
        OWNERS_KEY: observation.owners,
        HQ_KEY: observation.hq,
    }
    if observation.for_side == PUBLIC:
        return document
    document[SIDE_KEY] = observation.for_side
    document[FUNDS_KEY] = observation.funds
    document[SQUADS_KEY] = [_rendered(squad, SQUAD_FIELDS) for squad in observation.squads]
    document[CONTACTS_KEY] = [
        _rendered(contact, CONTACT_FIELDS) for contact in observation.contacts
    ]
    return document


def parse(document: dict[str, Any]) -> Observation:
    """Rebuild an observation from its wire document.

    It reads our own wire and nothing else: the only writer is `serialise` above
    and the only readers are this project's tests and tools, so a missing key is
    a broken build rather than untrusted input. Anything arriving from the world
    is validated in `cti_daemon.report`, which is the module that exists for it.
    """
    at_time = document[AT_KEY]
    owners = dict(document[OWNERS_KEY])
    hq = dict(document.get(HQ_KEY, {}))
    for_side = document.get(SIDE_KEY, PUBLIC)
    if for_side == PUBLIC:
        return Observation(at_time=at_time, owners=owners, hq=hq)
    return Observation(
        at_time=at_time,
        owners=owners,
        hq=hq,
        for_side=for_side,
        funds=document[FUNDS_KEY],
        squads=tuple(_built(SquadView, squad, SQUAD_FIELDS) for squad in document[SQUADS_KEY]),
        contacts=tuple(
            _built(Contact, contact, CONTACT_FIELDS) for contact in document[CONTACTS_KEY]
        ),
    )
