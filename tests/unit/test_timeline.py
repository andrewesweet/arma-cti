"""Reading a run back out of its telemetry (#39).

The tool is what turns an in-world casualty test into an assertion: the world
says what it staged, and the daemon's file has to account for it independently.
So the check that matters here is that it fails when the record is short.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from types import ModuleType

# Loaded by path for the reason `test_push_path_report.py` does: tools/ holds
# standalone scripts rather than an importable package.
_ROOT = Path(__file__).parents[2]
_SPEC = importlib.util.spec_from_file_location("timeline", _ROOT / "tools" / "timeline.py")
assert _SPEC is not None
assert _SPEC.loader is not None
_TIMELINE: ModuleType = importlib.util.module_from_spec(_SPEC)
sys.modules["timeline"] = _TIMELINE
_SPEC.loader.exec_module(_TIMELINE)

main = _TIMELINE.main
staged = _TIMELINE.staged
timeline = _TIMELINE.timeline
unmatched = _TIMELINE.unmatched


def death(**fields: object) -> dict[str, Any]:
    """One recorded death, in the shape the daemon writes it."""
    return {
        "at_ns": 1,
        "event": "casualty",
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


def written(tmp_path: Path, *records: dict[str, Any]) -> Path:
    """Write a telemetry file holding these rows."""
    log = tmp_path / "telemetry.jsonl"
    log.write_text("".join(json.dumps(row) + "\n" for row in records), encoding="utf-8")
    return log


def test_a_death_reads_as_a_sentence_naming_squad_place_and_killer() -> None:
    (line,) = timeline([death()])

    assert "431.5" in line
    assert "WEST-1" in line
    assert "agia_marina" in line
    assert "3421,5122,0" in line
    assert "EAST-2" in line


def test_the_run_s_breathing_is_left_out_of_the_story() -> None:
    # Five deaths under nine hundred heartbeats is the state this tool exists to
    # leave behind, so observations, requests and income are not narrated.
    noise = [
        {"event": "observation", "at": 1, "side": "WEST"},
        {"event": "request", "at": 1, "verb": "observe"},
        {"event": "income", "at": 1, "paid": 30},
    ]

    assert timeline([*noise, death()]) != []
    assert len(timeline([*noise, death()])) == 1


def test_a_gap_in_the_record_is_narrated_rather_than_left_quiet() -> None:
    (line,) = timeline([{"event": "casualties_dropped", "at": 0, "count": 4}])

    assert "4" in line
    assert "never recorded" in line


def test_a_truncated_last_line_does_not_stop_the_read(tmp_path: Path) -> None:
    log = written(tmp_path, death())
    with log.open("a", encoding="utf-8") as sink:
        sink.write('{"event": "casu')

    assert main([str(log)]) == 0


def test_a_staged_death_the_record_holds_is_accounted_for(tmp_path: Path) -> None:
    log = written(tmp_path, death())
    claims = tmp_path / "spike-lines.txt"
    claims.write_text(
        "casualty_staged squad=WEST-1 side=WEST place=agia_marina by_side=EAST\n",
        encoding="utf-8",
    )

    assert main([str(log), "--expect", str(claims)]) == 0


def test_a_staged_death_the_record_lacks_fails(tmp_path: Path) -> None:
    # The assertion the in-world probe rests on. A world that says it killed a
    # man of WEST-1 and a telemetry file with no such row is exactly the bug
    # this whole surface exists to catch.
    log = written(tmp_path, death(squad="WEST-2"))
    claims = tmp_path / "spike-lines.txt"
    claims.write_text("casualty_staged squad=WEST-1\n", encoding="utf-8")

    assert main([str(log), "--expect", str(claims)]) == 1


def test_a_claim_matching_the_wrong_field_is_not_accounted_for() -> None:
    # Right Squad, wrong killer: attribution is half the value of the row, so a
    # near miss must not pass as a hit.
    records = [death()]
    assert unmatched(records, [{"squad": "WEST-1", "by_side": "WEST"}]) == [
        {"squad": "WEST-1", "by_side": "WEST"}
    ]


def test_two_staged_deaths_cannot_be_met_by_one_recorded_one() -> None:
    claims = [{"squad": "WEST-1"}, {"squad": "WEST-1"}]

    assert unmatched([death()], claims) == [{"squad": "WEST-1"}]
    assert unmatched([death(), death(unit="other")], claims) == []


def test_a_probe_that_staged_nothing_does_not_pass_by_default(tmp_path: Path) -> None:
    # Nothing claimed is not the same as everything found: a probe whose staging
    # silently failed would otherwise be indistinguishable from one that worked.
    log = written(tmp_path, death())
    claims = tmp_path / "spike-lines.txt"
    claims.write_text("nothing to see here\n", encoding="utf-8")

    assert main([str(log), "--expect", str(claims)]) == 1


def test_staged_lines_are_read_off_a_log_that_carries_other_lines(tmp_path: Path) -> None:
    log = tmp_path / "spike-lines.txt"
    log.write_text(
        "world_built map=stratis\n"
        "casualty_staged squad=WEST-1 place=agia_marina\n"
        "presence_report_started interval=5\n",
        encoding="utf-8",
    )

    assert staged(log) == [{"squad": "WEST-1", "place": "agia_marina"}]


def test_a_missing_telemetry_file_is_an_error_not_an_empty_timeline(tmp_path: Path) -> None:
    assert main([str(tmp_path / "never-written.jsonl")]) == 1
