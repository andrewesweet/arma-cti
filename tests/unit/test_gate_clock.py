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

The fix round's additions pin the instrument's own failure mode: a broken
anchor prints rather than reading as health, the window is bounded by the
anchor's `set` date so lowering it cannot false-fire at the old rows, and the
fired line carries its load context. Those three are the class #446 is about
turned on the fix itself.
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

# The default `at` of a arranged row, and the anchor set dates the window-bound
# tests place rows against. Dates, not datetimes, because the anchor file's
# `set` is a date and the bound is calendar-granular by design.
ROW_AT = "2026-08-20T12:00:00+00:00"
SET_ON = "2026-08-20"
SET_LATER = "2026-08-21"


def row(  # noqa: PLR0913, PLR0917 — the eight parameters are Record's own eight fields
    recipe: str = "unit",
    wall: float = ANCHOR_SECONDS,
    status: int = 0,
    at: str = ROW_AT,
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


def greens(walls: list[float], recipe: str = "unit", at: str = ROW_AT) -> list[gate_clock.Record]:
    """Return green runs at the given walls, oldest first."""
    return [row(recipe=recipe, wall=wall, at=at) for wall in walls]


def anchor_state(
    anchors: dict[str, float] | None = None,
    set_dates: dict[str, str] | None = None,
    problems: dict[str, str] | None = None,
) -> gate_clock.AnchorState:
    """Return an AnchorState, with `set` dates as the anchor file spells them."""
    return gate_clock.AnchorState(
        anchors or {},
        {recipe: gate_clock.date.fromisoformat(day) for recipe, day in (set_dates or {}).items()},
        problems or {},
    )


def unit_state(set_on: str = SET_ON) -> gate_clock.AnchorState:
    """Return the one anchored recipe the derivation's table used, set on the rows' day."""
    return anchor_state({"unit": ANCHOR_SECONDS}, {"unit": set_on})


def verdict_for(
    records: list[gate_clock.Record],
    state: gate_clock.AnchorState,
    *,
    arma_running: bool = False,
) -> gate_clock.Verdict:
    """Return the `unit` verdict of an assess call, so each test names only its subject."""
    unit, _fast = gate_clock.assess(tuple(records), state, arma_running=arma_running)
    return unit


def write_anchor(path: Path, entries: dict[str, object]) -> None:
    """Write an anchor file the way the tree ships one: `_read_me` plus entries."""
    path.write_text(json.dumps({"_read_me": "arranged", **entries}, indent=2), encoding="utf-8")


def test_median_at_or_under_the_anchor_is_silent() -> None:
    """A healthy window says nothing — silence is the verdict that must mean something."""
    verdict = verdict_for(greens([ANCHOR_SECONDS] * gate_clock.MIN_SAMPLE), unit_state())
    assert verdict.reason == "healthy"
    assert verdict.line is None


def test_median_above_the_threshold_fires_exactly_one_line() -> None:
    """A durable slowdown is one line naming the recipe, anchor, median and multiple."""
    records = greens([150.0] * gate_clock.MIN_SAMPLE)
    lines = [v.line for v in gate_clock.assess(tuple(records), unit_state()) if v.line]
    assert len(lines) == 1
    line = lines[0]
    assert "unit" in line
    assert "109s anchor" in line
    assert "median 150s" in line
    assert "1.38×" in line  # 150/109, as the derivation's table spells it


def test_the_fired_line_carries_the_windows_load_median() -> None:
    """A loaded stretch is not always visible at report time; the line must be self-diagnosing.

    The rows the loaded stretch leaves behind stay in the window after the load
    ends, so the one line that fires names the load it was measured under.
    """
    records = [
        row(wall=150.0, load=load)
        for load in (4.0, 4.2, 4.4, 4.6, 4.8)  # median 4.4
    ]
    verdict = verdict_for(records, unit_state())
    assert verdict.reason == "slower"
    assert verdict.line is not None
    assert "load-1m median 4.40" in verdict.line


def test_the_fired_line_omits_load_when_no_row_carries_it() -> None:
    """Rows recorded without a load average fire without the clause, not with a guess."""
    records = [row(wall=150.0, load=None) for _ in range(gate_clock.MIN_SAMPLE)]
    verdict = verdict_for(records, unit_state())
    assert verdict.reason == "slower"
    assert verdict.line is not None
    assert "load-1m" not in verdict.line


def test_a_single_slow_run_among_healthy_ones_is_silent() -> None:
    """Box noise — the whole point of a median, and the reason a single run never speaks."""
    records = greens([ANCHOR_SECONDS] * (gate_clock.MIN_SAMPLE - 1) + [400.0])
    assert verdict_for(records, unit_state()).reason == "healthy"


def test_below_the_minimum_sample_is_silent_for_that_reason() -> None:
    """Fewer green runs than the floor is *not enough said*, not *healthy*."""
    verdict = verdict_for(greens([150.0] * (gate_clock.MIN_SAMPLE - 1)), unit_state())
    assert verdict.reason == "insufficient_sample"
    assert verdict.line is None


def test_an_unset_anchor_is_silent_for_that_reason() -> None:
    """A recipe the valid file does not name reads as unknown, never as healthy."""
    verdict = verdict_for(greens([150.0] * gate_clock.MIN_SAMPLE), anchor_state())
    assert verdict.reason == "anchor_unset"
    assert verdict.line is None


def test_an_unreadable_anchor_prints_under_its_own_name(tmp_path: Path) -> None:
    """A half-edited anchor file must not read as *no* anchor, which would be silence as health.

    The fix round's blocking finding: the original verdict carried the reason
    and no line, so `report` printed nothing for the one state where noise is
    correct — a broken instrument, not a busy box.
    """
    anchor_file = tmp_path / "broken.json"
    anchor_file.write_text("{not json", encoding="utf-8")
    broken = gate_clock.load_anchors(anchor_file)
    for verdict in gate_clock.assess(greens([150.0] * 5), broken):
        assert verdict.reason == "anchor_unreadable"
        assert verdict.line is not None
        line: str = verdict.line
        assert verdict.recipe in line
        assert "not valid JSON" in line


def test_an_unreadable_anchor_prints_even_while_the_tier_runs(tmp_path: Path) -> None:
    """The busy-box suppression silences regression claims, not broken-instrument ones."""
    anchor_file = tmp_path / "broken.json"
    anchor_file.write_text("[]", encoding="utf-8")  # valid JSON, not an object
    broken = gate_clock.load_anchors(anchor_file)
    verdicts = gate_clock.assess(greens([150.0] * 5), broken, arma_running=True)
    assert all(v.reason == "anchor_unreadable" and v.line for v in verdicts)


def test_a_missing_anchor_file_is_unreadable_not_unset(tmp_path: Path) -> None:
    """The file ships in the tree; absence is damage, and must not read as the growth state."""
    state = gate_clock.load_anchors(tmp_path / "absent.json")
    assert state.anchors == {}
    assert set(state.problems) == set(gate_clock.RECIPES)


def test_half_edited_entries_are_problems_for_their_recipe_alone(tmp_path: Path) -> None:
    """A quoted number, a dropped key or a bad `set` date is a half-edit, not an unset recipe."""
    anchor_file = tmp_path / "anchor.json"
    write_anchor(
        anchor_file,
        {
            "unit": {"anchor_seconds": "110", "set": SET_ON},  # a string fails the read
            "fast": {"anchor_seconds": 195, "set": SET_ON},
        },
    )
    state = gate_clock.load_anchors(anchor_file)
    assert state.anchors == {"fast": 195.0}
    assert set(state.problems) == {"unit"}

    anchor_file.write_text(
        json.dumps({"unit": {"anchor_seconds": 110}}),
        encoding="utf-8",  # `set` dropped
    )
    assert set(gate_clock.load_anchors(anchor_file).problems) == {"unit"}

    anchor_file.write_text(
        json.dumps({"unit": 176}),
        encoding="utf-8",  # the entry itself is not an object
    )
    assert set(gate_clock.load_anchors(anchor_file).problems) == {"unit"}


def test_the_window_is_bounded_by_the_anchors_set_date() -> None:
    """Lowering the anchor cannot false-fire at the rows that predate it (#442's landing shape).

    Ten green runs at 176 s, then the anchor is re-derived to 109 s and `set`
    moved to the next day: the old rows leave the window and the recipe reads
    insufficient until five post-`set` greens exist — never `slower` at ~1.6×.
    """
    old_rows = greens([176.0] * gate_clock.REPORT_WINDOW, at="2026-08-20T09:00:00+00:00")
    lowered = unit_state(set_on=SET_LATER)
    assert verdict_for(old_rows, lowered).reason == "insufficient_sample"

    new_rows = greens([110.0] * gate_clock.MIN_SAMPLE, at=f"{SET_LATER}T09:00:00+00:00")
    assert verdict_for(old_rows + new_rows, lowered).reason == "healthy"


def test_rows_whose_at_will_not_parse_leave_a_bounded_window() -> None:
    """A row that cannot be placed in time is excluded, not guessed into the window."""
    placed = greens([110.0] * gate_clock.MIN_SAMPLE, at=f"{SET_LATER}T09:00:00+00:00")
    stray = [row(wall=176.0, at="not a timestamp")] * gate_clock.MIN_SAMPLE
    lowered = unit_state(set_on=SET_LATER)
    assert verdict_for(placed + stray, lowered).reason == "healthy"


def test_red_runs_are_excluded_from_the_median() -> None:
    """A red run is faster (#446's own evidence), so admitting one flatters the median.

    Five green runs at the anchor and five red runs four times over it: excluded,
    the verdict is healthy; the same walls all green would fire. That flip is
    the exclusion doing its job.
    """
    reds = [one._replace(status=1) for one in greens([ANCHOR_SECONDS * 4] * 5)]
    recorded = greens([ANCHOR_SECONDS] * 5) + reds
    assert verdict_for(recorded, unit_state()).reason == "healthy"
    all_admitted = greens([ANCHOR_SECONDS] * 5 + [ANCHOR_SECONDS * 4] * 5)
    assert verdict_for(all_admitted, unit_state()).reason == "slower"


def test_the_threshold_fires_where_the_derivation_says_it_does() -> None:
    """The measured day shapes, against the measured anchor: fires on 08-10, not 08-06/08-08."""
    for day, median_wall in DAY_MEDIANS.items():
        verdict = verdict_for(greens([median_wall] * gate_clock.MIN_SAMPLE), unit_state())
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
    assert verdict_for(records, unit_state()).reason == "healthy"


def test_recipes_are_never_averaged_together() -> None:
    """A slow `fast` population says nothing about `unit`, which has its own anchor."""
    records = greens([400.0] * gate_clock.MIN_SAMPLE, recipe="fast")
    verdicts = gate_clock.assess(
        tuple(records),
        anchor_state({"unit": ANCHOR_SECONDS, "fast": 100.0}, {"unit": SET_ON, "fast": SET_ON}),
    )
    unit, fast = verdicts
    assert unit.reason == "insufficient_sample"
    assert unit.line is None
    assert fast.reason == "slower"


def test_the_arma_tier_running_silences_the_comparison_not_the_instrument() -> None:
    """A gate slowed by the corpus or a play server is a busy box, not a regression."""
    records = greens([400.0] * gate_clock.MIN_SAMPLE)
    for verdict in gate_clock.assess(tuple(records), unit_state(), arma_running=True):
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


def test_proc_uptime_reads_the_monotonic_clock_and_can_be_staged(tmp_path: Path) -> None:
    """Both ends of a recorded wall read /proc/uptime; unreadable is None, never a guess."""
    staged = tmp_path / "uptime"
    staged.write_text("12345.67 23456.78\n", encoding="utf-8")
    assert gate_clock.proc_uptime(staged) == 12345.67
    assert gate_clock.proc_uptime(tmp_path / "absent") is None
    staged.write_text("not a number 1.00\n", encoding="utf-8")
    assert gate_clock.proc_uptime(staged) is None
    staged.write_text("\n", encoding="utf-8")
    assert gate_clock.proc_uptime(staged) is None


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


def test_the_anchor_loader_skips_provenance_and_unnamed_recipes(tmp_path: Path) -> None:
    """`_`-keys are prose; a recipe the file does not name is unset, not a problem."""
    anchor_file = tmp_path / "gate-clock-anchor.json"
    write_anchor(anchor_file, {"unit": {"anchor_seconds": 190, "set": SET_ON}})
    state = gate_clock.load_anchors(anchor_file)
    assert state.problems == {}
    assert state.anchors == {"unit": 190.0}
    assert state.set_dates == {"unit": gate_clock.date.fromisoformat(SET_ON)}


def test_record_then_report_through_the_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The verbs the justfile drives, once each: a row lands, and a healthy window stays quiet."""
    exported = tmp_path / "collected"
    exported.write_text("5022\n", encoding="utf-8")
    monkeypatch.setenv("CTI_GATE_CLOCK_COLLECTED_FILE", str(exported))
    staged = tmp_path / "uptime"
    staged.write_text("1000.50 2000.00\n", encoding="utf-8")
    monkeypatch.setattr(gate_clock, "PROC_UPTIME", staged)
    assert (
        gate_clock.main(
            [
                "--gate-clock-dir",
                str(tmp_path),
                "record",
                "--recipe",
                "unit",
                "--start-uptime",
                "1000.00",
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
    # The shell line states the count, so a null one is visible in the run's own
    # output rather than only in the row nobody reads.
    assert "recorded unit 0.5s green 5022 tests" in capsys.readouterr().out
    read_back = gate_clock.load_records(tmp_path)
    assert len(read_back) == 1
    assert read_back[0].wall_seconds == 0.5
    assert read_back[0].tests_collected == 5022
    assert read_back[0].load_1m == 0.5
    assert read_back[0].foreign_gate_processes == 2
    assert read_back[0].head  # the tree's HEAD; provenance, not a pinned value


def test_record_refuses_rather_than_fabricates_a_wall(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A recorder that cannot read /proc/uptime at its end skips the row loudly.

    A zero or realtime-derived wall would pollute the median the report fires
    on; no row is better than a row that lies.
    """
    monkeypatch.setattr(gate_clock, "PROC_UPTIME", tmp_path / "absent")
    assert (
        gate_clock.main(
            [
                "--gate-clock-dir",
                str(tmp_path),
                "record",
                "--recipe",
                "unit",
                "--start-uptime",
                "1000.00",
                "--status",
                "0",
            ]
        )
        == 0
    )
    assert gate_clock.load_records(tmp_path) == ()
    assert "recording failed" in capsys.readouterr().err


def test_report_through_the_cli_in_each_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The `report` verb #454 demonstrates, with the fix round's broken-anchor state first.

    The same ladder `just watch-report` drives, with the anchor file pointed at
    a staged one so the shipped tree's anchor is never the input: a missing file
    prints, a valid file naming no recipe stays silent, anchored-at-median stays
    silent, and drift fires once.
    """
    anchor_file = tmp_path / "anchor.json"
    monkeypatch.setattr(gate_clock, "ANCHOR_PATH", anchor_file)
    run = ["--gate-clock-dir", str(tmp_path), "report"]

    assert gate_clock.main(run) == 0  # the file ships in the tree: absence is a broken instrument
    printed = capsys.readouterr().out
    assert printed.count("\n") == len(gate_clock.RECIPES)
    assert "anchor unreadable" in printed

    for wall in (ANCHOR_SECONDS,) * gate_clock.MIN_SAMPLE:
        gate_clock.append_record(tmp_path, row(wall=wall))
    write_anchor(anchor_file, {})  # a valid file naming no recipe: the growth state
    assert gate_clock.main(run) == 0
    assert capsys.readouterr().out == ""

    write_anchor(anchor_file, {"unit": {"anchor_seconds": ANCHOR_SECONDS, "set": SET_ON}})
    assert gate_clock.main(run) == 0  # anchored at the current median: healthy
    assert capsys.readouterr().out == ""

    for _ in range(gate_clock.MIN_SAMPLE):
        gate_clock.append_record(tmp_path, row(wall=ANCHOR_SECONDS * 2))
    assert gate_clock.main(run) == 0
    printed = capsys.readouterr().out
    assert printed.count("\n") == 1
    assert printed.startswith("gate-clock unit durably slower:")


def test_the_check_verb_reds_a_broken_anchor_and_passes_a_good_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The `just check` leg: a malformed anchor is a red, not a line nobody must read."""
    anchor_file = tmp_path / "anchor.json"
    monkeypatch.setattr(gate_clock, "ANCHOR_PATH", anchor_file)

    anchor_file.write_text("{not json", encoding="utf-8")
    assert gate_clock.main(["check"]) == 1
    assert "anchor unreadable" in capsys.readouterr().out

    write_anchor(anchor_file, {"unit": {"anchor_seconds": 176, "set": SET_ON}})
    assert gate_clock.main(["check"]) == 0
    assert capsys.readouterr().out == ""


def test_history_names_each_recipe_the_anchor_and_its_set_date(tmp_path: Path) -> None:
    """The retro's ask: what moving the anchor would be moving from, and when it was set."""
    for wall in (180.0, 200.0, 220.0):
        gate_clock.append_record(tmp_path, row(wall=wall))
        gate_clock.append_record(tmp_path, row(recipe="fast", wall=wall + 20))
    lines = gate_clock.history(tmp_path, unit_state())
    assert len(lines) == len(gate_clock.RECIPES)
    assert lines[0].startswith("unit: ")
    assert "109s anchor set 2026-08-20" in lines[0]
    assert "no anchor set" in lines[1]
