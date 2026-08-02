"""Deaths the world reports become rows an operator can reconstruct a run from.

#35's demo ended with a Squad at three of eight and no record of the other five.
These are the daemon's half of the fix (#39): what a death must carry to be
worth having, and what the daemon does with a report that cannot be trusted.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from cti_daemon.daemon import Daemon

if TYPE_CHECKING:
    from pathlib import Path


def reply_to(daemon: Daemon, **envelope: object) -> dict[str, Any]:
    """Send one request and return its decoded reply."""
    return json.loads(daemon.handle_line(json.dumps(envelope)))


def rows(log: Path, event: str) -> list[dict[str, Any]]:
    """Every row of one kind the daemon wrote down."""
    written = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    return [row for row in written if row["event"] == event]


def death(**fields: object) -> dict[str, Any]:
    """One death in the shape the world reports it, with the fields under test."""
    return {
        "at": 431.5,
        "unit": "2:14",
        "type": "B_Soldier_F",
        "squad": "WEST-1",
        "side": "WEST",
        "place": "agia_marina",
        "pos": [3421, 5122, 0],
        "by_unit": "3:2",
        "by_type": "O_Soldier_F",
        "by_squad": "EAST-2",
        "by_side": "EAST",
        "by_vehicle": "",
        **fields,
    }


def report(daemon: Daemon, request_id: str, **casualties: object) -> dict[str, Any]:
    """Report one batch of deaths, on a report that carries nothing else."""
    return reply_to(
        daemon,
        id=request_id,
        verb="observe",
        payload={"time": 440, "casualties": casualties},
    )


def test_a_death_is_written_down_with_who_where_when_and_by_whom(tmp_path: Path) -> None:
    # The whole point of the row: a timeline needs an identity a person
    # recognises (Squad and side, not the engine's netId), the ground it
    # happened on *and* the metre it happened at, the death's own clock reading
    # rather than the report's, and who did it.
    log = tmp_path / "telemetry.jsonl"
    report(Daemon(telemetry_path=log), "c-1", deaths=[death()])

    (row,) = rows(log, "casualty")
    assert row["squad"] == "WEST-1"
    assert row["side"] == "WEST"
    assert row["type"] == "B_Soldier_F"
    assert row["place"] == "agia_marina"
    assert row["pos"] == [3421, 5122, 0]
    # The death's clock, not the 440 the report was sent under: a report is five
    # seconds of world and a firefight is not.
    assert row["at"] == 431.5
    assert (row["by_squad"], row["by_side"], row["by_type"]) == ("EAST-2", "EAST", "O_Soldier_F")
    assert row["unit"] == "2:14"


def test_a_death_belonging_to_no_squad_is_still_written_down(tmp_path: Path) -> None:
    # A Base garrison, an editor-placed unit, a civilian: none of them is on any
    # roster, and dropping them would leave holes exactly where an unexplained
    # firefight happened.
    log = tmp_path / "telemetry.jsonl"
    report(
        Daemon(telemetry_path=log),
        "c-2",
        deaths=[death(squad="", side="EAST", type="O_Soldier_F", place="csat_kamino")],
    )

    (row,) = rows(log, "casualty")
    assert (row["squad"], row["side"], row["place"]) == ("", "EAST", "csat_kamino")


def test_a_death_nobody_can_be_blamed_for_is_still_written_down(tmp_path: Path) -> None:
    # Drowning, a fall, friendly artillery with the instigator lost: the engine
    # hands objNull and the row says so rather than being withheld.
    log = tmp_path / "telemetry.jsonl"
    report(
        Daemon(telemetry_path=log),
        "c-3",
        deaths=[death(by_unit="", by_type="", by_squad="", by_side="")],
    )

    (row,) = rows(log, "casualty")
    assert (row["by_squad"], row["by_side"], row["by_unit"]) == ("", "", "")


def test_the_vehicle_that_did_it_is_recorded_beside_the_man_who_did(tmp_path: Path) -> None:
    log = tmp_path / "telemetry.jsonl"
    report(Daemon(telemetry_path=log), "c-4", deaths=[death(by_vehicle="B_MBT_01_cannon_F")])

    assert rows(log, "casualty")[0]["by_vehicle"] == "B_MBT_01_cannon_F"


def test_deaths_are_written_in_the_order_the_world_reported_them(tmp_path: Path) -> None:
    log = tmp_path / "telemetry.jsonl"
    report(
        Daemon(telemetry_path=log),
        "c-5",
        deaths=[death(at=1.0, unit="a"), death(at=2.0, unit="b"), death(at=3.0, unit="c")],
    )

    assert [row["unit"] for row in rows(log, "casualty")] == ["a", "b", "c"]


def test_a_report_carrying_no_casualties_writes_nothing(tmp_path: Path) -> None:
    # Every report from a world older than this change, and every quiet minute
    # in a world that is not: silence is not a malformed report.
    log = tmp_path / "telemetry.jsonl"
    reply = reply_to(Daemon(telemetry_path=log), id="c-6", verb="observe", payload={"time": 1})

    assert reply["status"] == "ok"
    assert rows(log, "casualty") == []


def test_deaths_the_world_had_to_drop_are_recorded_as_a_gap(tmp_path: Path) -> None:
    # The world's buffer is bounded, so it can refuse. A hole in the timeline
    # must announce itself, or it reads as a quiet stretch of the run.
    log = tmp_path / "telemetry.jsonl"
    report(Daemon(telemetry_path=log), "c-7", deaths=[death()], dropped=4)

    assert rows(log, "casualties_dropped")[0]["count"] == 4


def test_a_report_that_dropped_nothing_says_nothing(tmp_path: Path) -> None:
    log = tmp_path / "telemetry.jsonl"
    report(Daemon(telemetry_path=log), "c-8", deaths=[death()], dropped=0)

    assert rows(log, "casualties_dropped") == []


def test_a_death_without_a_clock_reading_is_refused(tmp_path: Path) -> None:
    # An undated death cannot be put in a sequence, which is the only thing the
    # row is for.
    daemon = Daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    reply = report(daemon, "c-9", deaths=[death(at="soon")])

    assert reply["error"]["class"] == "malformed_request"


def test_a_death_without_a_position_is_refused(tmp_path: Path) -> None:
    daemon = Daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    assert report(daemon, "c-10", deaths=[death(pos=[1, 2])])["error"]["class"] == (
        "malformed_request"
    )
    assert report(daemon, "c-11", deaths=[death(pos=["x", 2, 0])])["error"]["class"] == (
        "malformed_request"
    )


def test_a_death_whose_identity_is_not_a_name_is_refused(tmp_path: Path) -> None:
    daemon = Daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    reply = report(daemon, "c-12", deaths=[death(squad=7)])

    assert reply["error"]["class"] == "malformed_request"


def test_one_unreadable_death_refuses_the_whole_batch(tmp_path: Path) -> None:
    # Not a partial read: a batch half-written is a timeline that looks complete
    # and is not, and a record nobody can trust is worse than a refusal.
    #
    # It used to be a partial read, and this test asserted the half — the rows
    # ahead of the bad one were already on disk when the refusal was raised,
    # which is exactly what the paragraph above says must not happen. #74 made
    # the whole report parse before any of it is folded, so a refusal now leaves
    # the record it arrived at.
    log = tmp_path / "telemetry.jsonl"
    daemon = Daemon(telemetry_path=log)
    reply = report(daemon, "c-13", deaths=[death(unit="first"), "not a death"])

    assert reply["error"]["class"] == "malformed_request"
    assert [row["unit"] for row in rows(log, "casualty")] == []


def test_a_casualties_field_that_is_not_a_batch_is_refused(tmp_path: Path) -> None:
    daemon = Daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    reply = reply_to(
        daemon,
        id="c-14",
        verb="observe",
        payload={"time": 1, "casualties": ["a death"]},
    )

    assert reply["error"]["class"] == "malformed_request"


def test_a_drop_count_that_is_not_a_count_is_refused(tmp_path: Path) -> None:
    daemon = Daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    reply = report(daemon, "c-15", deaths=[], dropped="lots")

    assert reply["error"]["class"] == "malformed_request"


def test_recording_a_death_does_not_touch_the_observation(tmp_path: Path) -> None:
    # Telemetry, not intelligence (ADR-0020): neither Commander learns anything
    # from a casualty, and #26's return cap stays the Observation's problem
    # alone. The reply to a report carrying five deaths is the reply to one
    # carrying none.
    daemon = Daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    quiet = reply_to(daemon, id="c-16", verb="observe", payload={"time": 50})["result"]
    bloody = report(daemon, "c-17", deaths=[death(at=51.0) for _ in range(5)])["result"]

    assert bloody | {"at": 0} == quiet | {"at": 0}
