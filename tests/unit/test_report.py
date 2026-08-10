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
    assert told.loadouts is None
    assert told.squad_leaders is None


def test_an_empty_squad_report_is_the_world_saying_it_holds_none() -> None:
    told = report.parse(_payload(squads={}))

    assert told.squads == {}


def test_a_squad_is_read_as_its_strength_its_place_and_its_position() -> None:
    told = report.parse(
        _payload(squads={"w-1": {"size": 6, "at": "girna", "pos": [1234.5, 5678.4, 12.0]}})
    )

    assert told.squads == {"w-1": (6, "girna", (1234, 5678))}


def test_a_marching_squad_is_in_no_place_rather_than_in_a_missing_one() -> None:
    # And is still somewhere: the Place is empty because open ground has no
    # name, which is exactly the case #175 exists for.
    told = report.parse(_payload(squads={"w-1": {"size": 6, "pos": [400.0, 900.0, 0.0]}}))

    assert told.squads == {"w-1": (6, "", (400, 900))}


def test_a_squad_the_world_cannot_place_in_metres_refuses_the_report() -> None:
    # Unlike `at`, whose emptiness is an answer, there is no honest absence for
    # a position: a Squad the world is holding has a leader standing somewhere.
    # So the report is refused whole rather than read as far as it parses, which
    # is what every required field here does.
    with pytest.raises(report.MalformedReportError) as refusal:
        report.parse(_payload(squads={"w-1": {"size": 6, "at": "girna"}}))

    assert refusal.value.path == "squads.w-1.pos"


def test_a_position_is_carried_as_the_two_axes_a_map_can_draw() -> None:
    # The world states a position the way it states a death's, three axes and
    # unrounded; a Commander is shown the two of them a map has, in whole
    # metres (ADR-0058). Rounded rather than truncated, because a marker that
    # is half a metre out is not wrong in a direction anybody can act on.
    told = report.parse(_payload(squads={"w-1": {"size": 6, "pos": [10.6, -3.4, 55.9]}}))

    assert told.squads == {"w-1": (6, "", (11, -3))}


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


def test_an_empty_loadout_report_is_the_world_saying_nobody_has_chosen() -> None:
    # Distinct from absent, like every other optional member: absent leaves the
    # record alone, empty is a world with nobody in it saying so (#172).
    assert report.parse(_payload(loadouts={})).loadouts == {}


def test_a_players_chosen_kit_is_read_as_an_id_against_his_uid() -> None:
    told = report.parse(_payload(loadouts={"76561198000000000": "medic"}))

    assert told.loadouts == {"76561198000000000": "medic"}


def test_a_kit_that_is_not_a_string_is_refused_and_the_uid_is_named() -> None:
    with pytest.raises(report.MalformedReportError, match=r"loadouts\.7656") as refused:
        report.parse(_payload(loadouts={"76561198000000000": 4}))

    assert refused.value.path == "loadouts.76561198000000000"


def test_a_loadout_report_that_is_not_an_object_is_refused() -> None:
    with pytest.raises(report.MalformedReportError, match="loadouts"):
        report.parse(_payload(loadouts=["medic"]))


def test_whether_a_kit_is_on_the_menu_is_not_this_documents_question() -> None:
    # The catalogue is the Campaign's, and `report_cycle` judges against it. A
    # document module that knew the menu would be a second copy of it.
    assert report.parse(_payload(loadouts={"uid-1": "jetpack"})).loadouts == {"uid-1": "jetpack"}


def test_an_empty_squad_leader_report_is_the_world_saying_nobody_leads_one() -> None:
    # `loadouts`' distinction on the field ADR-0070 added: absent leaves the
    # roster's account of who leads what alone, empty is a world in which nobody
    # has taken the squad-leader role saying so.
    assert report.parse(_payload(squad_leaders={})).squad_leaders == {}


def test_a_squad_leaders_claim_is_read_as_a_side_against_his_uid() -> None:
    told = report.parse(_payload(squad_leaders={"76561198000000000": "WEST"}))

    assert told.squad_leaders == {"76561198000000000": "WEST"}


def test_a_squad_leader_claiming_a_side_nobody_is_playing_refuses_the_report() -> None:
    # `contacts`' rule rather than `loadouts`', and the difference is where the
    # vocabulary comes from: a kit id is authored data a shipped PBO can drift
    # on, while a side is `commands.SIDES` travelling through the same generated
    # export the sampler reads. Minting a shell on a side nothing commands would
    # put a Squad in the roster that no Observation ever carries.
    with pytest.raises(report.MalformedReportError) as refusal:
        report.parse(_payload(squad_leaders={"uid-1": "west"}))

    assert refusal.value.path == "squad_leaders.uid-1"
    assert refusal.value.detail == "`squad_leaders.uid-1` names no side that is playing"


def test_a_squad_leader_claim_that_is_not_a_string_is_refused_and_the_uid_is_named() -> None:
    with pytest.raises(report.MalformedReportError) as refusal:
        report.parse(_payload(squad_leaders={"uid-1": 7}))

    assert refusal.value.path == "squad_leaders.uid-1"
    assert refusal.value.detail.startswith("`squad_leaders.uid-1` must be ")


def test_the_export_is_the_field_names_of_every_shape() -> None:
    exported = report.exported()

    assert set(exported) == set(report.SHAPES)
    assert exported["squad"] == ["size", "at", "pos"]
    assert exported["payload"] == [
        "time",
        "presence",
        "squads",
        "contacts",
        "hq",
        "casualties",
        "loadouts",
        "squad_leaders",
    ]
