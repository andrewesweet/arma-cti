"""The gate-duration read, in its one home.

`tools/gate_clock.py` exists because the gate roughly doubled between
2026-08-05 and 2026-08-19 and nothing noticed for two weeks (#446): no commit
caused it, so only a standing measurement could catch it. What is pinned here
is the decision that module makes — *given these records and this anchor, is
the gate durably slower?* — by handing it records and reading its verdict, in
the `CTI_GATE_CLOCK_DIR` seam its five `just watch-report` siblings already
use (#249). Nothing runs a real gate: a test that measured this box would
assert whatever the box was doing that minute, which is the failure mode the
reporter itself exists to filter out.

The shapes asserted are the measured ones from the issue's own derivation:
against the 109 s post-#197 anchor, a 1.25× threshold fires on the 08-10 shape
(150 s, 1.37×) and stays silent on 08-06 (110 s) and 08-08 (124 s). That test
is what keeps the threshold honest if anyone tunes it later — it answers to
the history, not to the number as written.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from conftest import load_tool

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

gate_clock = load_tool("gate_clock")

# The post-#197 median the issue's day table is anchored to, and three of its
# days: the shapes the 1.25x threshold was derived to separate.
ANCHOR_SECONDS = 109.0
DAY_MEDIANS = {"08-06": 110.0, "08-08": 124.0, "08-10": 150.0}


def row(  # noqa: PLR0913, PLR0917 — the eight parameters are Record's own eight fields
    recipe: str = "unit",
    wall: float = ANCHOR_SECONDS,
    status: int = 0,
    at: str = "2026-08-05T12:00:00+00:00",
    head: str = "c0ffee" * 6,
    tests: int | None = 5022,
    load: float | None = 0.42,
    foreign: int | None = 0,
) -> gate_clock.Record:
    """Return one finished gate run, arranged."""
    return gate_clock.Record(
        at=at,
        recipe=recipe,
        wall_seconds=wall,
        status=status,
        head=head,
        tests_collected=tests,
        load_1m=load,
        foreign_gate_processes=foreign,
    )


def greens(walls: list[float], recipe: str = "unit") -> list[gate_clock.Record]:
    """Return green runs at the given walls, oldest first."""
    return [row(recipe=recipe, wall=wall) for wall in walls]


def unit_anchor() -> dict[str, float]:
    """Return the one anchor the derivation's table used."""
    return {"unit": ANCHOR_SECONDS}


def verdict_for(
    records: list[gate_clock.Record],
    anchors: dict[str, float],
    *,
    anchor_problem: str | None = None,
    arma_running: bool = False,
) -> gate_clock.Verdict:
    """Return the `unit` verdict of an assess call, so each test names only its subject."""
    unit, _fast = gate_clock.assess(
        tuple(records), anchors, anchor_problem=anchor_problem, arma_running=arma_running
    )
    return unit


def test_median_at_or_under_the_anchor_is_silent() -> None:
    """A healthy window says nothing — silence is the verdict that must mean something."""
    verdict = verdict_for(greens([ANCHOR_SECONDS] * gate_clock.MIN_SAMPLE), unit_anchor())
    assert verdict.reason == "healthy"
    assert verdict.line is None


def test_median_above_the_threshold_fires_exactly_one_line() -> None:
    """A durable slowdown is one line naming the recipe, anchor, median and multiple."""
    records = greens([150.0] * gate_clock.MIN_SAMPLE)
    lines = [v.line for v in gate_clock.assess(tuple(records), unit_anchor()) if v.line]
    assert len(lines) == 1
    line = lines[0]
    assert "unit" in line
    assert "109s anchor" in line
    assert "median 150s" in line
    assert "1.38×" in line  # 150/109, as the derivation's table spells it


def test_a_single_slow_run_among_healthy_ones_is_silent() -> None:
    """Box noise — the whole point of a median, and the reason a single run never speaks."""
    records = greens([ANCHOR_SECONDS] * (gate_clock.MIN_SAMPLE - 1) + [400.0])
    assert verdict_for(records, unit_anchor()).reason == "healthy"


def test_below_the_minimum_sample_is_silent_for_that_reason() -> None:
    """Fewer green runs than the floor is *not enough said*, not *healthy*."""
    verdict = verdict_for(greens([150.0] * (gate_clock.MIN_SAMPLE - 1)), unit_anchor())
    assert verdict.reason == "insufficient_sample"
    assert verdict.line is None


def test_an_unset_anchor_is_silent_for_that_reason() -> None:
    """A fresh clone reads as unknown, never as healthy — the anchor is the whole mechanism."""
    verdict = verdict_for(greens([150.0] * gate_clock.MIN_SAMPLE), {})
    assert verdict.reason == "anchor_unset"
    assert verdict.line is None


def test_an_unreadable_anchor_is_silent_under_its_own_name(tmp_path: Path) -> None:
    """A half-edited anchor file must not read as *no* anchor, which would be silence as health."""
    anchor_file = tmp_path / "broken.json"
    anchor_file.write_text("{not json", encoding="utf-8")
    broken, problem = gate_clock.load_anchors(anchor_file)
    assert broken == {}
    assert problem is not None
    verdict = verdict_for(greens([150.0] * 5), broken, anchor_problem=problem)
    assert verdict.reason == "anchor_unreadable"
    assert verdict.line is None


def test_red_runs_are_excluded_from_the_median() -> None:
    """A red run is faster (#446's own evidence), so admitting one flatters the median.

    Five green runs at the anchor and five red runs four times over it: excluded,
    the verdict is healthy; the same walls all green would fire. That flip is
    the exclusion doing its job.
    """
    reds = [one._replace(status=1) for one in greens([ANCHOR_SECONDS * 4] * 5)]
    recorded = greens([ANCHOR_SECONDS] * 5) + reds
    assert verdict_for(recorded, unit_anchor()).reason == "healthy"
    all_admitted = greens([ANCHOR_SECONDS] * 5 + [ANCHOR_SECONDS * 4] * 5)
    assert verdict_for(all_admitted, unit_anchor()).reason == "slower"


def test_the_threshold_fires_where_the_derivation_says_it_does() -> None:
    """The measured day shapes, against the measured anchor: fires on 08-10, not 08-06/08-08."""
    for day, median_wall in DAY_MEDIANS.items():
        verdict = verdict_for(greens([median_wall] * gate_clock.MIN_SAMPLE), unit_anchor())
        expected = "slower" if median_wall > ANCHOR_SECONDS * gate_clock.THRESHOLD else "healthy"
        assert verdict.reason == expected, f"the {day} shape ({median_wall:.0f}s)"
    assert DAY_MEDIANS["08-10"] > ANCHOR_SECONDS * gate_clock.THRESHOLD
    assert DAY_MEDIANS["08-08"] < ANCHOR_SECONDS * gate_clock.THRESHOLD


def test_only_the_recent_window_is_read() -> None:
    """A fix stops being reported once enough healthy runs exist to fill the window.

    Fifteen slow runs then ten healthy ones: the window holds only the healthy
    tail, so a gate that recovered goes quiet rather than dragging its past.
    """
    records = greens([400.0] * 15) + greens([ANCHOR_SECONDS] * gate_clock.REPORT_WINDOW)
    assert verdict_for(records, unit_anchor()).reason == "healthy"


def test_recipes_are_never_averaged_together() -> None:
    """A slow `fast` population says nothing about `unit`, which has its own anchor."""
    records = greens([400.0] * gate_clock.MIN_SAMPLE, recipe="fast")
    verdicts = gate_clock.assess(tuple(records), {"unit": ANCHOR_SECONDS, "fast": 100.0})
    unit, fast = verdicts
    assert unit.reason == "insufficient_sample"
    assert unit.line is None
    assert fast.reason == "slower"


def test_the_arma_tier_running_silences_every_recipe() -> None:
    """A gate slowed by the corpus or a play server is a busy box, not a regression."""
    records = greens([400.0] * gate_clock.MIN_SAMPLE)
    for verdict in gate_clock.assess(tuple(records), unit_anchor(), arma_running=True):
        assert verdict.reason == "arma_tier_running"
        assert verdict.line is None


def test_a_written_row_round_trips_every_field(tmp_path: Path) -> None:
    """Every field written is readable, so a later reader can tell a busy box from a regression."""
    written = (
        row(),
        row(recipe="fast", wall=271.5, status=0, at="2026-08-19T09:00:00+00:00"),
        row(recipe="unit", wall=221.0, status=1, tests=None, load=None, foreign=3),
    )
    for one in written:
        gate_clock.append_record(tmp_path, one)
    read_back = gate_clock.load_records(tmp_path)
    assert list(read_back) == list(written)


def test_malformed_lines_are_skipped_not_fatal(tmp_path: Path) -> None:
    """A box that died mid-append leaves a truncated line; the report must survive it."""
    gate_clock.append_record(tmp_path, row())
    path = gate_clock.records_path(tmp_path)
    path.write_text(path.read_text(encoding="utf-8") + '{"at": "half", "rec', encoding="utf-8")
    assert gate_clock.load_records(tmp_path) == (row(),)


def test_the_collected_count_reads_the_exported_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The recipe's temp file is the count's one source; unset or unreadable is None."""
    exported = tmp_path / "collected"
    monkeypatch.setenv("CTI_GATE_CLOCK_COLLECTED_FILE", str(exported))
    exported.write_text("5022\n", encoding="utf-8")
    assert gate_clock.read_collected_file() == 5022
    exported.write_text("not a count", encoding="utf-8")
    assert gate_clock.read_collected_file() is None
    monkeypatch.delenv("CTI_GATE_CLOCK_COLLECTED_FILE")
    assert gate_clock.read_collected_file() is None


def test_the_arma_scan_reads_proc_and_can_be_staged(tmp_path: Path) -> None:
    """The busy-box detector counts Arma servers by comm, without spawning anything."""
    (tmp_path / "1" / "comm").parent.mkdir()
    (tmp_path / "1" / "comm").write_text("arma3server\n", encoding="utf-8")
    (tmp_path / "2" / "comm").parent.mkdir()
    (tmp_path / "2" / "comm").write_text("arma3server_x64\n", encoding="utf-8")
    (tmp_path / "self").mkdir()
    (tmp_path / "self" / "comm").write_text("pytest\n", encoding="utf-8")
    assert gate_clock.arma_tier_processes(proc=tmp_path) == 2
    assert gate_clock.arma_tier_processes(proc=tmp_path / "nowhere") == 0


def test_the_anchor_loader_skips_provenance_and_non_entries(tmp_path: Path) -> None:
    """`_`-keys are prose, and a recipe's entry needs a positive number to count."""
    anchor_file = tmp_path / "gate-clock-anchor.json"
    anchor_file.write_text(
        json.dumps(
            {
                "_read_me": "raise these only by hand, in a diff",
                "unit": {"anchor_seconds": 190, "set": "2026-08-20"},
                "someday": {"anchor_seconds": 0},
            }
        ),
        encoding="utf-8",
    )
    anchors, problem = gate_clock.load_anchors(anchor_file)
    assert problem is None
    assert anchors == {"unit": 190.0}


def test_record_then_report_through_the_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The verbs the justfile drives, once each: a row lands, and a healthy window stays quiet."""
    exported = tmp_path / "collected"
    exported.write_text("5022\n", encoding="utf-8")
    monkeypatch.setenv("CTI_GATE_CLOCK_COLLECTED_FILE", str(exported))
    assert (
        gate_clock.main(
            [
                "--gate-clock-dir",
                str(tmp_path),
                "record",
                "--recipe",
                "unit",
                "--start-epoch-ns",
                "1000000000000000000",
                "--status",
                "0",
                "--load-1m",
                "0.5",
                "--foreign-gate",
                "2",
            ]
        )
        == 0
    )
    read_back = gate_clock.load_records(tmp_path)
    assert len(read_back) == 1
    assert read_back[0].tests_collected == 5022
    assert read_back[0].load_1m == 0.5
    assert read_back[0].foreign_gate_processes == 2
    assert read_back[0].head  # the tree's HEAD; provenance, not a pinned value


def test_report_through_the_cli_in_all_three_states(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The `report` verb #454 demonstrates: unset, anchored-healthy, and firing.

    The same ladder `just watch-report` drives, once each, with the anchor file
    pointed at a staged one so the shipped tree's anchor is never the input.
    """
    anchor_file = tmp_path / "anchor.json"
    monkeypatch.setattr(gate_clock, "ANCHOR_PATH", anchor_file)
    run = ["--gate-clock-dir", str(tmp_path), "report"]

    assert gate_clock.main(run) == 0  # no anchor set: a fresh clone reads as unknown
    assert capsys.readouterr().out == ""

    for wall in (ANCHOR_SECONDS,) * gate_clock.MIN_SAMPLE:
        gate_clock.append_record(tmp_path, row(wall=wall))
    anchor_file.write_text(
        json.dumps({"unit": {"anchor_seconds": ANCHOR_SECONDS}}), encoding="utf-8"
    )
    assert gate_clock.main(run) == 0  # anchored at the current median: healthy
    assert capsys.readouterr().out == ""

    for _ in range(gate_clock.MIN_SAMPLE):
        gate_clock.append_record(tmp_path, row(wall=ANCHOR_SECONDS * 2))
    assert gate_clock.main(run) == 0
    printed = capsys.readouterr().out
    assert printed.count("\n") == 1
    assert printed.startswith("gate-clock unit durably slower:")


def test_history_names_each_recipe_and_the_anchor(tmp_path: Path) -> None:
    """The retro's ask: what moving the anchor would be moving from."""
    for wall in (180.0, 200.0, 220.0):
        gate_clock.append_record(tmp_path, row(wall=wall))
        gate_clock.append_record(tmp_path, row(recipe="fast", wall=wall + 20))
    lines = gate_clock.history(tmp_path, {"unit": 200.0})
    assert len(lines) == len(gate_clock.RECIPES)
    assert lines[0].startswith("unit: ")
    assert "200s anchor" in lines[0]
    assert "no anchor set" in lines[1]
