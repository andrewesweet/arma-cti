"""The push-path budget, read back off a run's telemetry (#17).

Two Commanders double the traffic on the path that carries work into the world,
and #17 asks for the headroom to be *measured and recorded* rather than
estimated. This is what turns a run's telemetry into those numbers, so the
measurement is reproducible from the evidence rather than from a session.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from types import ModuleType

# Loaded by path for the reason `test_check_sqf_bans.py` does: tools/ holds
# standalone scripts rather than an importable package.
_ROOT = Path(__file__).parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "push_path_report", _ROOT / "tools" / "push_path_report.py"
)
assert _SPEC is not None
assert _SPEC.loader is not None
push_path_report: ModuleType = importlib.util.module_from_spec(_SPEC)
sys.modules["push_path_report"] = push_path_report
_SPEC.loader.exec_module(push_path_report)


def telemetry(path: Path, *rows: dict[str, Any]) -> Path:
    """Write a telemetry log with the rows given, as the daemon writes it."""
    path.write_text(
        "".join(json.dumps({"at_ns": 1, **row}) + "\n" for row in rows), encoding="utf-8"
    )
    return path


def read(path: Path) -> dict[str, str]:
    """Run the report and return what it would append to results.env."""
    return dict(line.split("=", 1) for line in push_path_report.report(path))


def test_the_headroom_is_the_drain_cap_against_the_largest_drain(tmp_path: Path) -> None:
    # The number #17 asks for. The engine drains at most 100 callbacks per frame
    # (ADR-0004), so what matters is how close the biggest single handover came
    # to it — not the average, which a quiet minute flatters.
    log = telemetry(
        tmp_path / "telemetry.jsonl",
        {"event": "outbox_handed", "handed": 4, "through": 4},
        {"event": "outbox_handed", "handed": 25, "through": 29},
        {"event": "outbox_handed", "handed": 1, "through": 30},
    )
    numbers = read(log)

    assert numbers["outbox_drains"] == "3"
    assert numbers["outbox_max_handed"] == "25"
    assert numbers["push_path_headroom_x"] == "4.0"


def test_the_observe_call_is_measured_against_the_stall_cap(tmp_path: Path) -> None:
    # Both planners run inside the world's blocking `observe` call, so the
    # budget under load is that call against ADR-0005's 1000 ms stall cap. The
    # worst one is the one that would trip it.
    log = telemetry(
        tmp_path / "telemetry.jsonl",
        {"event": "request", "verb": "observe", "duration_us": 1_000},
        {"event": "request", "verb": "observe", "duration_us": 3_000},
        {"event": "request", "verb": "observe", "duration_us": 21_000},
        {"event": "request", "verb": "poll", "duration_us": 500_000},
    )
    numbers = read(log)

    assert numbers["observe_calls"] == "3"
    assert numbers["observe_max_us"] == "21000"
    assert numbers["observe_p50_us"] == "3000"
    # 21 ms of a 1000 ms cap, and the poll above is not an observe.
    assert numbers["observe_stall_budget_pct"] == "2.1"


def test_each_commander_is_counted_separately(tmp_path: Path) -> None:
    # Interleaved telemetry (#17): a run's numbers per side, because "the AI
    # decided 600 things" says nothing about whether both sides were playing.
    log = telemetry(
        tmp_path / "telemetry.jsonl",
        {"event": "decision", "side": "WEST"},
        {"event": "decision", "side": "EAST"},
        {"event": "decision", "side": "EAST"},
        {"event": "command_issued", "side": "WEST", "command": "purchase"},
        {"event": "plan_refused", "side": "EAST", "command": "order", "code": "unknown_squad"},
    )
    numbers = read(log)

    assert numbers["decisions_WEST"] == "1"
    assert numbers["decisions_EAST"] == "2"
    assert numbers["commands_WEST"] == "1"
    assert numbers["commands_EAST"] == "0"
    assert numbers["plan_refused"] == "1"


def test_a_run_that_pushed_nothing_says_so_rather_than_dividing_by_it(tmp_path: Path) -> None:
    # An empty log is a run that never got going, and reporting infinite
    # headroom off it would be the most flattering possible reading of a
    # Campaign that did nothing.
    numbers = read(telemetry(tmp_path / "telemetry.jsonl"))

    assert numbers["outbox_drains"] == "0"
    assert numbers["outbox_max_handed"] == "0"
    assert numbers["push_path_headroom_x"] == "unmeasured"
    assert numbers["observe_calls"] == "0"
