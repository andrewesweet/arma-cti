"""The observe-report wire format: what the world says it can see.

ADR-0012 gives the Command Port one schema source for what goes *out* —
`cti_daemon.commands`, exported to the addon by `tools/export_command_schema.py`
and read there as JSON. This module is the same thing for what comes *in*. #74
found the inbound half living in two languages held together by convention: five
SQF samplers assemble the report, this daemon took it apart field by field, and
the only place a mismatch showed up was the Arma tier, one field at a time, at
run time.

So the document is declared once, as data (`SHAPES`), and both sides use that
declaration. The parsers below read a report *through* it, so the daemon
validates against the source it exports rather than against a second copy of the
same decision. The export writes the same shapes into
`addons/main/generated/command-schema.json`, where `cti_fnc_reportObject` builds
every named object in the report against them — a sampler that offers a field
this file does not declare, or omits one it does, is a typed `schema_stale`
failure in the world's own log rather than a field the daemon silently never
sees. `tests/unit/test_report_schema.py` holds the two sides together without
Arma: a field added or renamed on one side alone fails `just unit`.

What is *not* here is anything that needs the Campaign. Reading `hq.{base}`
against the map this Campaign is playing is a judgement about the world rather
than about the document, and it lives in `cti_daemon.report_cycle` with the rest
of the folding. This module turns a wire document into domain values and nothing
else, which is what makes it testable without a daemon.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, NoReturn, cast

from cti_daemon import commands, contacts, protocol

if TYPE_CHECKING:
    from collections.abc import Callable

# A position is three axes. Named because the check that a death carries one
# reads as arithmetic otherwise.
_POSITION_AXES: Final = 3

# The kinds a reported field can be. A kind is a name for a check and the
# conversion that follows it, so "what `age` must be" is stated once here rather
# than spelled out at each field.
NUMBER: Final = "number"
INTEGER: Final = "integer"
STRING: Final = "string"
BOOLEAN: Final = "boolean"
OBJECT: Final = "object"
LIST: Final = "list"
POSITION: Final = "position"

#: A field that must be there. Distinct from a field whose absence means
#: something (`""`, `0`, "the report said nothing about this"), because the two
#: are different answers and a schema that could not tell them apart would make
#: every field optional by accident.
REQUIRED: Final = object()


def _as_number(value: object) -> float | None:
    # `bool` is an `int` in Python and is never a reading of anything here.
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _as_integer(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _as_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _as_boolean(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _as_object(value: object) -> dict[str, Any] | None:
    return cast("dict[str, Any]", value) if isinstance(value, dict) else None


def _as_list(value: object) -> list[Any] | None:
    return cast("list[Any]", value) if isinstance(value, list) else None


def _as_position(value: object) -> list[float] | None:
    axes = _as_list(value)
    if axes is None or len(axes) != _POSITION_AXES:
        return None
    read = [_as_number(axis) for axis in axes]
    if any(axis is None for axis in read):
        return None
    return cast("list[float]", read)


#: How each kind is checked. A checker answers with the converted value or with
#: `None` for "not this kind" — no field in this document may legitimately be
#: null, so the one sentinel serves for every kind.
_CHECKERS: Final[dict[str, Callable[[object], object]]] = {
    NUMBER: _as_number,
    INTEGER: _as_integer,
    STRING: _as_string,
    BOOLEAN: _as_boolean,
    OBJECT: _as_object,
    LIST: _as_list,
    POSITION: _as_position,
}


@dataclass(frozen=True, slots=True)
class Field:
    """One named field of the report, and what it must be.

    `says` is the whole of the refusal prose: a report the daemon cannot read is
    answered with "`<path>` must be <says>", so the sentence an operator reads
    and the check that produced it are the same declaration.
    """

    name: str
    kind: str
    says: str
    absent: Any = REQUIRED


@dataclass(frozen=True, slots=True)
class Shape:
    """One named object in the report: what it is called, and its fields."""

    says: str
    fields: tuple[Field, ...]


#: What a death the world reports must say, beyond its own clock reading and
#: where it happened. All strings, all allowed to be empty: a garrison soldier
#: belongs to no Squad and a man drowned by nobody has no killer, and both of
#: those are answers rather than gaps.
_CASUALTY_NAMES: Final = (
    "unit",
    "type",
    "squad",
    "side",
    "place",
    "by_unit",
    "by_type",
    "by_squad",
    "by_side",
    "by_vehicle",
)

#: The observe report, shape by shape. This is the schema source #74 asked for:
#: the parsers below read through it and `tools/export_command_schema.py` writes
#: it out for the samplers, so there is one declaration of the document rather
#: than one per language.
SHAPES: Final[dict[str, Shape]] = {
    "payload": Shape(
        says="the report the world sends",
        fields=(
            Field("time", NUMBER, "the in-game time in seconds"),
            # Absent is not empty for the four below: a report that says nothing
            # about Squads leaves the roster alone, and one that says nothing
            # about sightings clears no Contact. Present but empty is the world
            # saying it holds none, which is a real answer and acted on.
            Field("presence", OBJECT, "a map of Objective ids to the sides present", absent={}),
            Field(
                "squads", OBJECT, "a map of Squad ids to what the world sees of them", absent=None
            ),
            Field("contacts", OBJECT, "a map of each side to what its leaders saw", absent=None),
            Field(
                "hq", OBJECT, "a map of Base ids to what the world sees of their HQ", absent=None
            ),
            Field("casualties", OBJECT, "the deaths since the last report", absent=None),
        ),
    ),
    "squad": Shape(
        says="an object",
        fields=(
            Field("size", INTEGER, "a whole number of men still standing"),
            # Open ground between places has no name, so an empty `at` is the
            # honest answer for a Squad that is marching rather than a gap.
            Field("at", STRING, "the place the Squad is standing in", absent=""),
        ),
    ),
    "contact": Shape(
        says="an object",
        fields=(
            Field("seen", LIST, "a list of sightings", absent=()),
            Field("observed", LIST, "a list of place names", absent=()),
        ),
    ),
    "sighting": Shape(
        says="a sighting",
        fields=(
            Field("at", STRING, "the place it was seen at"),
            Field("kind", STRING, "the perceived kind"),
            Field("age", NUMBER, "how many seconds ago it was seen"),
        ),
    ),
    "hq": Shape(
        says="an object",
        fields=(
            Field("destroyed", BOOLEAN, "true when the HQ has been brought down"),
            Field("by", STRING, "the side that brought it down", absent=""),
        ),
    ),
    "casualties": Shape(
        says="the deaths since the last report",
        fields=(
            Field("deaths", LIST, "a list of deaths", absent=()),
            Field("dropped", INTEGER, "a count of the deaths the buffer refused", absent=0),
        ),
    ),
    "death": Shape(
        says="a death",
        fields=(
            # The death's own clock reading, not the report's: a report is five
            # seconds of world and a firefight is not.
            Field("at", NUMBER, "the in-game time the death happened at"),
            # Metres as well as a place id, which ADR-0008 allows because no
            # Commander reads this: "3.8 km short of its target" is precisely
            # what a place id cannot say.
            Field("pos", POSITION, "a position of three coordinates"),
            *(Field(name, STRING, "a string", absent="") for name in _CASUALTY_NAMES),
        ),
    ),
}


@dataclass(frozen=True, slots=True)
class SideContacts:
    """What one side's leaders saw, and where they looked."""

    seen: tuple[contacts.Sighting, ...]
    observed: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HqSeen:
    """What the world says of one Base's HQ structure."""

    destroyed: bool
    by: str


@dataclass(frozen=True, slots=True)
class Casualties:
    """The deaths since the last report, and how many the buffer refused."""

    deaths: tuple[dict[str, Any], ...]
    dropped: int


@dataclass(frozen=True, slots=True)
class Report:
    """One report, read off the wire and ready to fold into a Campaign.

    `None` on the four optional members means the report said nothing about
    them, which is not the same as saying there are none — the distinction the
    Contacts removal rule turns on, and the reason it survives parsing rather
    than being flattened here.
    """

    at_time: float
    presence: dict[str, Any]
    squads: dict[str, tuple[int, str]] | None
    contacts: dict[str, SideContacts] | None
    hq: dict[str, HqSeen] | None
    casualties: Casualties | None


def _refuse(path: str, says: str, request_id: str | None) -> NoReturn:
    detail = f"`{path}` must be {says}"
    raise protocol.MalformedRequestError(detail, request_id)


def _checked(
    kind: str,
    says: str,
    value: object,
    path: str,
    request_id: str | None,
    # The declared kind is what decides the type at run time, so a narrower
    # return here would be a lie every caller had to cast away.
) -> Any:  # noqa: ANN401 — see above
    """Read one value as the kind the schema declares, or refuse the report."""
    read = _CHECKERS[kind](value)
    if read is None:
        _refuse(path, says, request_id)
    return read


def _object(shape: Shape, value: object, path: str, request_id: str | None) -> dict[str, Any]:
    """Read one named object through its shape, or refuse the report.

    Refusing rather than reading as far as it parses: a Commander cannot tell an
    empty picture from an unreadable one, and one of those is a reason to
    attack.
    """
    source = _as_object(value)
    if source is None:
        _refuse(path, shape.says, request_id)
    prefix = f"{path}." if path else ""
    return {
        field.name: (
            # A required field that is not there is read as absent and fails its
            # own check, so the refusal names the field rather than the object
            # holding it.
            _checked(
                field.kind,
                field.says,
                source.get(field.name),
                f"{prefix}{field.name}",
                request_id,
            )
            if field.name in source or field.absent is REQUIRED
            else field.absent
        )
        for field in shape.fields
    }


def _squads(reported: object, request_id: str | None) -> dict[str, tuple[int, str]] | None:
    """Read the world's account of its Squads."""
    if reported is None:
        return None
    seen: dict[str, tuple[int, str]] = {}
    for squad_id, said in cast("dict[str, Any]", reported).items():
        squad = _object(SHAPES["squad"], said, f"squads.{squad_id}", request_id)
        seen[squad_id] = (squad["size"], squad["at"])
    return seen


def _contacts(reported: object, request_id: str | None) -> dict[str, SideContacts] | None:
    """Read what each side's leaders saw, keyed by the side that did the seeing."""
    if reported is None:
        return None
    by_side: dict[str, SideContacts] = {}
    for side, said in cast("dict[str, Any]", reported).items():
        if side not in commands.SIDES:
            # `Contacts` keys on any string it is handed, so a mistyped side
            # would file a picture no observation ever reads and lose the
            # sighting without saying anything.
            detail = f"`contacts.{side}` names no side that is playing"
            raise protocol.MalformedRequestError(detail, request_id)
        report = _object(SHAPES["contact"], said, f"contacts.{side}", request_id)
        by_side[side] = SideContacts(
            seen=tuple(
                _sighting(sighting, f"contacts.{side}.seen[{index}]", request_id)
                for index, sighting in enumerate(report["seen"])
            ),
            observed=tuple(
                _checked(
                    STRING, "a place name", place, f"contacts.{side}.observed[{index}]", request_id
                )
                for index, place in enumerate(report["observed"])
            ),
        )
    return by_side


def _sighting(said: object, path: str, request_id: str | None) -> contacts.Sighting:
    """Read one sighting: a place, a perceived kind, and how old it is."""
    sighting = _object(SHAPES["sighting"], said, path, request_id)
    return contacts.Sighting(at=sighting["at"], kind=sighting["kind"], age=sighting["age"])


def _hq(reported: object, request_id: str | None) -> dict[str, HqSeen] | None:
    """Read what the world says of each Base's HQ structure."""
    if reported is None:
        return None
    return {
        base: HqSeen(**_object(SHAPES["hq"], said, f"hq.{base}", request_id))
        for base, said in cast("dict[str, Any]", reported).items()
    }


def _casualties(reported: object, request_id: str | None) -> Casualties | None:
    """Read the deaths the world saw since the last report."""
    if reported is None:
        return None
    batch = _object(SHAPES["casualties"], reported, "casualties", request_id)
    return Casualties(
        # Every row or none: a partly-read batch would leave a timeline that
        # looks complete and is not, and a black box nobody can trust is worse
        # than an obviously broken one.
        deaths=tuple(
            _object(SHAPES["death"], death, f"casualties.deaths[{index}]", request_id)
            for index, death in enumerate(batch["deaths"])
        ),
        dropped=batch["dropped"],
    )


def parse(payload: dict[str, Any], *, request_id: str | None = None) -> Report:
    """Read one observe report off the wire, or refuse it whole.

    Nothing is folded into anything here, so a report that fails half way
    through has changed nothing: what a malformed report leaves behind is the
    Campaign it arrived at.
    """
    told = _object(SHAPES["payload"], payload, "", request_id)
    return Report(
        at_time=told["time"],
        presence=dict(told["presence"]),
        squads=_squads(told["squads"], request_id),
        contacts=_contacts(told["contacts"], request_id),
        hq=_hq(told["hq"], request_id),
        casualties=_casualties(told["casualties"], request_id),
    )


def exported() -> dict[str, list[str]]:
    """Render the field names of each shape, as the addon reads them.

    Names only: what a field must *be* is judged here, where the rules are
    testable, and a copy of the type rules in SQF would be a second answer to
    the same question (ADR-0012).
    """
    return {name: [field.name for field in shape.fields] for name, shape in SHAPES.items()}
