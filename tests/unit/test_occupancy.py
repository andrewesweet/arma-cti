"""Occupancy over a window of real dispatch records, in agent-minutes (#295)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from conftest import load_tool

if TYPE_CHECKING:
    from pathlib import Path


occupancy = load_tool("occupancy")


def write_dispatch(
    root: Path,
    dispatch_id: str,
    started: str,
    ended: str | None = None,
) -> None:
    """Write the two record files this program reads, using their live shape."""
    record = root / dispatch_id
    record.mkdir(parents=True)
    (record / "dispatch.json").write_text(
        json.dumps({"dispatch_id": dispatch_id, "planned_at": started}),
        encoding="utf-8",
    )
    if ended is not None:
        (record / "result.json").write_text(
            json.dumps({"dispatch_id": dispatch_id, "started_at": started, "ended_at": ended}),
            encoding="utf-8",
        )


def report(output: str) -> dict[str, str]:
    """Read the emitted `key=value` lines back as a mapping."""
    return dict(line.split("=", 1) for line in output.splitlines())


def test_a_dispatch_occupies_every_whole_minute_between_its_start_and_its_end(
    tmp_path: Path,
) -> None:
    write_dispatch(tmp_path, "d-1", "2026-08-09T07:02:00+00:00", "2026-08-09T07:05:00+00:00")
    spans = occupancy.read_spans(tmp_path)

    series = occupancy.occupancy_series(
        spans,
        datetime(2026, 8, 9, 7, 0, tzinfo=UTC),
        datetime(2026, 8, 9, 7, 8, tzinfo=UTC),
    )

    assert series == (0, 0, 1, 1, 1, 0, 0, 0)


def test_concurrent_dispatches_add_so_the_series_shows_the_sawtooth(
    tmp_path: Path,
) -> None:
    write_dispatch(tmp_path, "d-1", "2026-08-09T07:00:00+00:00", "2026-08-09T07:04:00+00:00")
    write_dispatch(tmp_path, "d-2", "2026-08-09T07:00:00+00:00", "2026-08-09T07:02:00+00:00")
    write_dispatch(tmp_path, "d-3", "2026-08-09T07:05:00+00:00", "2026-08-09T07:06:00+00:00")

    series = occupancy.occupancy_series(
        occupancy.read_spans(tmp_path),
        datetime(2026, 8, 9, 7, 0, tzinfo=UTC),
        datetime(2026, 8, 9, 7, 7, tzinfo=UTC),
    )

    assert series == (2, 2, 1, 1, 0, 1, 0)


def test_lost_agent_minutes_are_the_ruled_capacity_the_window_did_not_use(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_dispatch(tmp_path, "d-1", "2026-08-09T07:00:00+00:00", "2026-08-09T07:10:00+00:00")

    code = occupancy.main(
        [
            "--since",
            "2026-08-09T07:00:00Z",
            "--until",
            "2026-08-09T07:10:00Z",
            "--limit",
            "5",
            "--dispatch-dir",
            str(tmp_path),
        ]
    )

    assert code == 0
    lines = report(capsys.readouterr().out)
    assert lines["minutes"] == "10"
    assert lines["capacity"] == "50"
    assert lines["used"] == "10"
    assert lines["lost"] == "40"
    assert lines["mean_occupancy"] == "1.00"
    assert lines["series"] == "1111111111"


def test_an_unfinished_dispatch_is_counted_as_occupied_and_named_as_running(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_dispatch(tmp_path, "d-still-going", "2026-08-09T07:01:00+00:00")

    occupancy.main(
        [
            "--since",
            "2026-08-09T07:00:00Z",
            "--until",
            "2026-08-09T07:04:00Z",
            "--limit",
            "2",
            "--dispatch-dir",
            str(tmp_path),
        ]
    )

    lines = report(capsys.readouterr().out)
    assert lines["running"] == "d-still-going"
    assert lines["series"] == "0111"
    assert lines["used"] == "3"


def test_a_window_with_no_dispatch_reports_no_running_id_rather_than_an_empty_field(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    occupancy.main(
        [
            "--since",
            "2026-08-09T07:00:00Z",
            "--until",
            "2026-08-09T07:03:00Z",
            "--limit",
            "3",
            "--dispatch-dir",
            str(tmp_path),
        ]
    )

    lines = report(capsys.readouterr().out)
    assert lines["running"] == "none"
    assert lines["lost"] == "9"


def test_a_result_without_its_own_start_does_not_attest_an_open_span(
    tmp_path: Path,
) -> None:
    write_dispatch(tmp_path, "d-1", "2026-08-09T07:00:00+00:00")
    (tmp_path / "d-1" / "result.json").write_text(
        json.dumps(
            {
                "dispatch_id": "d-1",
                "stopped_by": "just dispatch --stop",
                "ended_at": "2026-08-09T07:04:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    assert occupancy.read_spans(tmp_path) == ()


def test_a_stop_swept_closeout_is_not_counted_as_live(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_dispatch(tmp_path, "d-swept", "2026-08-09T07:00:00+00:00")
    (tmp_path / "d-swept" / "result.json").write_text(
        json.dumps(
            {
                "dispatch_id": "d-swept",
                "stopped_by": "just dispatch --stop",
                "stopped_at": "2026-08-09T07:04:00+00:00",
                "killed": [],
                "terminal_state": {"state": "stopped"},
            }
        ),
        encoding="utf-8",
    )

    code = occupancy.main(
        [
            "--since",
            "2026-08-09T07:00:00Z",
            "--until",
            "2026-08-09T07:04:00Z",
            "--limit",
            "2",
            "--dispatch-dir",
            str(tmp_path),
        ]
    )

    assert code == 0
    lines = report(capsys.readouterr().out)
    assert lines["running"] == "none"
    assert lines["series"] == "0000"
    assert lines["used"] == "0"


def test_a_planned_but_unstarted_dispatch_falls_back_to_its_planned_time(
    tmp_path: Path,
) -> None:
    record = tmp_path / "d-planned"
    record.mkdir()
    (record / "dispatch.json").write_text(
        json.dumps({"dispatch_id": "d-planned", "planned_at": "2026-08-09T07:00:00+00:00"}),
        encoding="utf-8",
    )

    assert occupancy.read_spans(tmp_path)[0][0] == datetime(2026, 8, 9, 7, 0, tzinfo=UTC)


def test_a_record_with_no_time_at_all_is_skipped_rather_than_guessed(
    tmp_path: Path,
) -> None:
    record = tmp_path / "d-timeless"
    record.mkdir()
    (record / "dispatch.json").write_text(
        json.dumps({"dispatch_id": "d-timeless"}), encoding="utf-8"
    )

    assert occupancy.read_spans(tmp_path) == ()


@pytest.mark.parametrize(
    ("argv", "refusal"),
    [
        (
            ["--since", "2026-08-09T07:00:00Z", "--until", "2026-08-09T08:00:00Z", "--limit", "0"],
            "refusal=limit_not_positive",
        ),
        (
            ["--since", "not-a-time", "--until", "2026-08-09T08:00:00Z", "--limit", "5"],
            "refusal=window_unreadable",
        ),
        (
            ["--since", "2026-08-09T08:00:00Z", "--until", "2026-08-09T07:00:00Z", "--limit", "5"],
            "refusal=window_not_forward",
        ),
    ],
)
def test_a_window_it_cannot_read_is_refused_by_name_and_prints_no_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    refusal: str,
) -> None:
    code = occupancy.main([*argv, "--dispatch-dir", str(tmp_path)])

    captured = capsys.readouterr()
    assert code == occupancy.EXIT_REFUSED
    assert captured.err.splitlines()[0] == refusal
    assert captured.out == ""


def test_both_iso_spellings_of_the_same_instant_are_read_alike() -> None:
    assert occupancy.parse_moment("2026-08-09T07:00:00Z") == occupancy.parse_moment(
        "2026-08-09T07:00:00+00:00"
    )


def test_a_naive_instant_is_read_as_utc_rather_than_local_time() -> None:
    assert occupancy.parse_moment("2026-08-09T07:00:00") == datetime(2026, 8, 9, 7, 0, tzinfo=UTC)
