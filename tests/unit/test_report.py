"""Reading the observe report off the wire, without a daemon to read it into.

#74's point: the report's shape is one declaration, and the thing that reads it
is a function over a document rather than a method on a socket. So these are
tests of the wire format itself — what a field means when it is absent, what a
report that cannot be read is answered with, and that the answer names the field
that was wrong.
"""

from __future__ import annotations

from typing import Any

import pytest

from cti_daemon import report


def _payload(**named: Any) -> dict[str, Any]:  # noqa: ANN401 — a wire document is
    # exactly a dictionary of anything, which is what these tests are about.
    return {"time": 12, **named}


def test_a_report_of_nothing_but_the_clock_says_nothing_about_anything() -> None:
    # Absent is not empty. A report that carries no `squads` leaves the roster
    # alone, and one that carries no `contacts` clears no Contact — the removal
    # rule turns on that distinction, so it survives parsing rather than being
    # flattened into an empty collection here.
    told = report.parse(_payload())

    assert told.at_time == 12
    assert told.presence == {}
    assert told.squads is None
    assert told.contacts is None
    assert told.hq is None
    assert told.casualties is None


def test_an_empty_squad_report_is_the_world_saying_it_holds_none() -> None:
    told = report.parse(_payload(squads={}))

    assert told.squads == {}


def test_a_squad_is_read_as_its_strength_and_its_place() -> None:
    told = report.parse(_payload(squads={"w-1": {"size": 6, "at": "girna"}}))

    assert told.squads == {"w-1": (6, "girna")}


def test_a_marching_squad_is_in_no_place_rather_than_in_a_missing_one() -> None:
    told = report.parse(_payload(squads={"w-1": {"size": 6}}))

    assert told.squads == {"w-1": (6, "")}


def test_a_sighting_carries_a_place_a_kind_and_an_age() -> None:
    told = report.parse(
        _payload(
            contacts={
                "WEST": {
                    "seen": [{"at": "girna", "kind": "Infantry", "age": 4}],
                    "observed": ["girna"],
                }
            }
        )
    )

    assert told.contacts is not None
    seen = told.contacts["WEST"]
    assert [(sighting.at, sighting.kind, sighting.age) for sighting in seen.seen] == [
        ("girna", "Infantry", 4.0)
    ]
    assert seen.observed == ("girna",)


def test_a_side_nobody_is_playing_has_no_contacts_to_report() -> None:
    with pytest.raises(report.MalformedReportError) as refusal:
        report.parse(_payload(contacts={"west": {"seen": [], "observed": []}}))

    assert refusal.value.path == "contacts.west"
    assert refusal.value.detail == "`contacts.west` names no side that is playing"


def test_an_hq_is_read_as_standing_or_down_and_by_whom() -> None:
    told = report.parse(_payload(hq={"air_base": {"destroyed": True, "by": "EAST"}}))

    assert told.hq == {"air_base": report.HqSeen(destroyed=True, by="EAST")}


def test_a_death_carries_its_own_clock_reading_and_ten_names() -> None:
    told = report.parse(
        _payload(casualties={"deaths": [{"at": 9, "pos": [1, 2, 3], "unit": "u-1"}], "dropped": 2})
    )

    assert told.casualties is not None
    (death,) = told.casualties.deaths
    assert death["at"] == 9.0
    assert death["pos"] == [1.0, 2.0, 3.0]
    assert death["unit"] == "u-1"
    # A garrison soldier belongs to no Squad and a man drowned by nobody has no
    # killer: both are answers rather than gaps.
    assert death["by_squad"] == ""
    assert told.casualties.dropped == 2


@pytest.mark.parametrize(
    ("payload", "path"),
    [
        ({}, "time"),
        ({"time": "soon"}, "time"),
        ({"time": 1, "presence": []}, "presence"),
        ({"time": 1, "squads": {"w-1": {"size": "six"}}}, "squads.w-1.size"),
        ({"time": 1, "squads": {"w-1": 6}}, "squads.w-1"),
        (
            {"time": 1, "contacts": {"WEST": {"seen": [{"at": "girna"}]}}},
            "contacts.WEST.seen[0].kind",
        ),
        ({"time": 1, "contacts": {"WEST": {"observed": [7]}}}, "contacts.WEST.observed[0]"),
        ({"time": 1, "hq": {"air_base": {"destroyed": "yes"}}}, "hq.air_base.destroyed"),
        ({"time": 1, "casualties": ["a death"]}, "casualties"),
        ({"time": 1, "casualties": {"deaths": [{"pos": [1, 2, 3]}]}}, "casualties.deaths[0].at"),
        (
            {"time": 1, "casualties": {"deaths": [{"at": 1, "pos": [1, 2]}]}},
            "casualties.deaths[0].pos",
        ),
        (
            {"time": 1, "casualties": {"deaths": [{"at": 1, "pos": [1, 2, 3], "squad": 7}]}},
            "casualties.deaths[0].squad",
        ),
        ({"time": 1, "casualties": {"dropped": "lots"}}, "casualties.dropped"),
    ],
)
def test_a_refusal_names_the_field_that_was_wrong(payload: dict[str, Any], path: str) -> None:
    # A report the daemon cannot read is refused whole, and the refusal says
    # where: one field per message, by its path in the document, so an operator
    # reading the log is told what to fix rather than that something was wrong.
    # The refusal is this module's own and carries no request id (#164): what a
    # document is wrong about is not a fact about the envelope it arrived in,
    # and `Daemon._observe` is the one place the two are put together.
    with pytest.raises(report.MalformedReportError) as refusal:
        report.parse(payload)

    assert refusal.value.path == path
    assert refusal.value.detail.startswith(f"`{path}` must be ")


def test_the_refusal_prose_is_the_schemas_own() -> None:
    # The sentence and the check are one declaration: `says` is what the field
    # must be, and it is both what is enforced and what is said.
    with pytest.raises(report.MalformedReportError) as refusal:
        report.parse({"time": True})

    assert refusal.value.detail == "`time` must be the in-game time in seconds"


def test_a_boolean_is_never_a_number_however_python_feels_about_it() -> None:
    # `bool` is an `int` in Python, and `true` seconds is not a clock reading.
    with pytest.raises(report.MalformedReportError):
        report.parse(_payload(squads={"w-1": {"size": True}}))


def test_the_export_is_the_field_names_of_every_shape() -> None:
    exported = report.exported()

    assert set(exported) == set(report.SHAPES)
    assert exported["squad"] == ["size", "at"]
    assert exported["payload"] == ["time", "presence", "squads", "contacts", "hq", "casualties"]
