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
anchor's `set` so lowering it cannot false-fire at the old rows, and the fired
line carries its load context. Those three are the class #446 is about turned
on the fix itself. Round 3 extends the same discipline to the sibling shapes:
a deleted or misspelled recipe key is damage the file ships against, not an
unset recipe, and a `set` timestamp bounds the window to the moment it names
so a same-day re-set excludes the same morning's rows.

#466's round pins the record's blind spot: a run that gave `just mutation`
nothing to work on skipped the one leg of either recipe whose cost the diff
moves, and the row now carries that tier's own target count — read by calling
the tier's selection against a staged tree — rather than a docs label that
would have had to call a product edit with no test module beside it a code run.
What is asserted is the decision that count feeds: the cheap kind cannot hide a
slowdown in `fast`'s median (the false-negative direction the issue is about),
`unit`'s window reads every kind because its legs price the whole tree, and the
rows written before the count read as unclassified rather than guessed at.

Round 2 of that pins the narrower form of the same bias: a target on
`mutation_smoke.NO_MUTABLE_SUBJECT` is skipped before `smoke` is called, so it
plants nothing and costs nothing, and counting it would have let a floor-priced
run into `fast`'s window carrying a code run's count. The count is of targets
the tier does work on, and the exempt case is asserted directly rather than
assumed — the sibling divergences (a target that reaches `measure` and finds
nothing to plant on, and one whose `measure` refuses) are paid for and red
respectively, so neither reaches a green row cheaply.
"""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

from conftest import load_tool

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

gate_clock = load_tool("gate_clock")
# The exempt list is read from the tier rather than restated here, so an entry
# added or removed there moves the target count's test with it (#466 round 2).
mutation_smoke = load_tool("mutation_smoke")

# The post-#197 median the issue's day table is anchored to, and three of its
# days: the shapes the 1.25x threshold was derived to separate.
ANCHOR_SECONDS = 109.0
DAY_MEDIANS = {"08-06": 110.0, "08-08": 124.0, "08-10": 150.0}

# The default `at` of an arranged row, and the anchor set values the
# window-bound tests place rows against: `set` takes a date (bounding from that
# day's start) or a full timestamp (bounding from the moment it names).
ROW_AT = "2026-08-20T12:00:00+00:00"
SET_ON = "2026-08-20"
SET_LATER = "2026-08-21"
MORNING = "2026-08-20T09:00:00+00:00"
SET_MOMENT = "2026-08-20T14:30:00+00:00"
EVENING = "2026-08-20T15:00:00+00:00"


def row(  # noqa: PLR0913, PLR0917 — the nine parameters are Record's own nine fields
    recipe: str = "unit",
    wall: float = ANCHOR_SECONDS,
    status: int = 0,
    at: str = ROW_AT,
    head: str = "c0ffee" * 6,
    tests: int | None = 5022,
    load: float | None = 0.42,
    foreign: int | None = 0,
    targets: int | None = 2,
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
        mutation_targets=targets,
    )


def greens(walls: list[float], recipe: str = "unit", at: str = ROW_AT) -> list[gate_clock.Record]:
    """Return green runs at the given walls, oldest first."""
    return [row(recipe=recipe, wall=wall, at=at) for wall in walls]


def anchor_state(
    anchors: dict[str, float] | None = None,
    set_dates: dict[str, str] | None = None,
    problems: dict[str, str] | None = None,
) -> gate_clock.AnchorState:
    """Return an AnchorState, with `set` values as the anchor file spells them."""
    return gate_clock.AnchorState(
        anchors or {},
        {
            recipe: gate_clock.as_utc(gate_clock.datetime.fromisoformat(when))
            for recipe, when in (set_dates or {}).items()
        },
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


def stage_repo(tmp_path: Path, name: str = "repo") -> Path:
    """Return an empty git repo, so the subject count reads git's own report of a tree.

    No commits and no `origin/main`: `changed`'s porcelain half alone finds the
    untracked files the arrangements below lay down, which is also how #450's
    one-untracked-markdown-file landing presented.
    """
    repo = tmp_path / name
    repo.mkdir(parents=True)
    subprocess.run(  # noqa: S603 — argv is this constant, as everywhere in tools/
        ["git", "init", "--quiet", str(repo)],  # noqa: S607 — git resolves off PATH, same as there
        check=True,
        capture_output=True,
    )
    return repo


def lay_down(repo: Path, *names: str) -> None:
    """Write each named file into a staged tree, parent directories and all."""
    for name in names:
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("arranged\n", encoding="utf-8")


def fast_state(set_on: str = SET_ON) -> gate_clock.AnchorState:
    """Return the `fast` recipe anchored on the rows' day — the recipe that reads the kind."""
    return anchor_state({"fast": ANCHOR_SECONDS}, {"fast": set_on})


def fast_rows(walls: list[float], targets: int | None) -> list[gate_clock.Record]:
    """Return green `fast` runs at those walls, each carrying that target count."""
    return [row(recipe="fast", wall=wall, targets=targets) for wall in walls]


def fast_verdict_for(
    records: list[gate_clock.Record], state: gate_clock.AnchorState
) -> gate_clock.Verdict:
    """Return the `fast` verdict of an assess call, so each test names only its subject."""
    _unit, fast = gate_clock.assess(tuple(records), state)
    return fast


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
    """The `anchor_unset` backstop: unknown, never healthy.

    The loader no longer produces this state — a recipe the file fails to name
    is a problem, pinned below — so this rung exists for a hand-built state and
    must not fall through to a comparison against no anchor.
    """
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
    """A quoted number, a dropped key or a bad `set` is a half-edit, not a missing recipe."""
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

    good_fast = {"fast": {"anchor_seconds": 195, "set": SET_ON}}
    anchor_file.write_text(
        json.dumps({"unit": {"anchor_seconds": 110}, **good_fast}),
        encoding="utf-8",  # `set` dropped
    )
    assert set(gate_clock.load_anchors(anchor_file).problems) == {"unit"}

    anchor_file.write_text(
        json.dumps({"unit": 176, **good_fast}),
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


def test_a_timestamp_set_bounds_the_window_to_the_moment_it_names() -> None:
    """A same-day re-set must exclude the same morning's rows (round 3's second finding).

    An implementer who improves the gate on a day they have already run it
    leaves that morning's slower rows on disk: ten greens at 176 s from 09:00,
    the anchor lowered to 109 s at 14:30. A day-granular `set` keeps those rows
    in the window and false-fires at 1.61×; `set` as a timestamp bounds from
    the moment, and the recipe reads insufficient until five post-moment greens
    exist.
    """
    morning = greens([176.0] * gate_clock.REPORT_WINDOW, at=MORNING)
    lowered = anchor_state({"unit": ANCHOR_SECONDS}, {"unit": SET_MOMENT})
    assert verdict_for(morning, lowered).reason == "insufficient_sample"

    evening = greens([ANCHOR_SECONDS] * gate_clock.MIN_SAMPLE, at=EVENING)
    assert verdict_for(morning + evening, lowered).reason == "healthy"


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


def test_the_anchor_loader_skips_provenance_only(tmp_path: Path) -> None:
    """`_`-keys are prose; a file naming every recipe reads clean, `set` date or timestamp."""
    anchor_file = tmp_path / "gate-clock-anchor.json"
    write_anchor(
        anchor_file,
        {
            "unit": {"anchor_seconds": 190, "set": SET_ON},
            "fast": {"anchor_seconds": 195, "set": SET_MOMENT},
        },
    )
    state = gate_clock.load_anchors(anchor_file)
    assert state.problems == {}
    assert state.anchors == {"unit": 190.0, "fast": 195.0}
    assert state.set_dates == {
        "unit": gate_clock.as_utc(gate_clock.datetime.fromisoformat(SET_ON)),
        "fast": gate_clock.datetime.fromisoformat(SET_MOMENT),
    }


def test_a_recipe_the_file_does_not_name_is_a_problem(tmp_path: Path) -> None:
    """The file ships naming every recipe, so a deleted key is damage, not the growth state.

    The round-3 finding: a recipe missing from the file used to read as
    `anchor_unset` — silence — where a deleted block is exactly the half-edit
    the broken-anchor rule exists to catch.
    """
    anchor_file = tmp_path / "gate-clock-anchor.json"
    write_anchor(anchor_file, {"unit": {"anchor_seconds": 190, "set": SET_ON}})  # `fast` deleted
    state = gate_clock.load_anchors(anchor_file)
    assert state.anchors == {"unit": 190.0}
    assert set(state.problems) == {"fast"}
    assert "missing" in state.problems["fast"]


def test_a_misspelled_key_is_flagged_where_it_sits(tmp_path: Path) -> None:
    """A typo in a key is as likely as a trailing comma, and presents twice.

    `unti` leaves `unit` missing (a problem in its own right, above) *and*
    loads a well-formed entry nothing reads; the loader names the stray key so
    the red tells the editor where their entry went.
    """
    anchor_file = tmp_path / "gate-clock-anchor.json"
    write_anchor(
        anchor_file,
        {
            "unti": {"anchor_seconds": 190, "set": SET_ON},
            "fast": {"anchor_seconds": 195, "set": SET_ON},
        },
    )
    state = gate_clock.load_anchors(anchor_file)
    assert state.anchors == {"fast": 195.0}  # the misspelling loads nowhere
    assert state.set_dates == {"fast": gate_clock.as_utc(gate_clock.datetime.fromisoformat(SET_ON))}
    assert set(state.problems) == {"unti", "unit"}
    assert "not a recipe" in state.problems["unti"]
    assert "missing" in state.problems["unit"]


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


def test_read_only_canonical_path_queues_the_row_for_the_dispatch_harness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The live sandbox failure stays non-gating and leaves a row the host can collect."""
    canonical = tmp_path / "read-only"
    canonical.mkdir()
    canonical.chmod(0o500)
    outbox = tmp_path / "outbox"
    staged = tmp_path / "uptime"
    staged.write_text("1000.50 2000.00\n", encoding="utf-8")
    monkeypatch.setattr(gate_clock, "PROC_UPTIME", staged)
    monkeypatch.setenv("CTI_GATE_CLOCK_CANONICAL_DIR", str(canonical))
    monkeypatch.setenv("CTI_GATE_CLOCK_OUTBOX_DIR", str(outbox))

    assert (
        gate_clock.main(
            [
                "--gate-clock-dir",
                str(canonical),
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

    assert gate_clock.load_records(canonical) == ()
    assert len(gate_clock.load_records(outbox)) == 1
    error = capsys.readouterr().err
    assert error.count("\n") == 1
    assert "gate-clock unit canonical write failed" in error
    assert "Permission denied" in error
    assert "queued for dispatch harness" in error


def test_a_dispatched_noncanonical_destination_also_queues_the_canonical_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The #470 workaround may keep its copy, but cannot fork dispatched history."""
    canonical = tmp_path / "canonical"
    selected = tmp_path / "selected"
    outbox = tmp_path / "outbox"
    staged = tmp_path / "uptime"
    staged.write_text("1000.50 2000.00\n", encoding="utf-8")
    monkeypatch.setattr(gate_clock, "PROC_UPTIME", staged)
    monkeypatch.setenv("CTI_GATE_CLOCK_CANONICAL_DIR", str(canonical))
    monkeypatch.setenv("CTI_GATE_CLOCK_OUTBOX_DIR", str(outbox))

    assert (
        gate_clock.main(
            [
                "--gate-clock-dir",
                str(selected),
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

    assert len(gate_clock.load_records(selected)) == 1
    assert len(gate_clock.load_records(outbox)) == 1
    assert gate_clock.load_records(canonical) == ()
    assert "queued for canonical collection" in capsys.readouterr().out


def test_report_through_the_cli_in_each_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The `report` verb #454 demonstrates, with the fix round's broken-anchor state first.

    The same ladder `just watch-report` drives, with the anchor file pointed at
    a staged one so the shipped tree's anchor is never the input: a missing file
    prints, a file naming no recipe prints (the file ships naming every recipe,
    so every key missing is damage), anchored-at-median stays silent, and drift
    fires once.
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
    write_anchor(anchor_file, {})  # valid JSON, no recipe named: every key missing
    assert gate_clock.main(run) == 0
    printed = capsys.readouterr().out
    assert printed.count("\n") == len(gate_clock.RECIPES)
    assert "missing from the anchor file" in printed

    write_anchor(
        anchor_file,
        {
            "unit": {"anchor_seconds": ANCHOR_SECONDS, "set": SET_ON},
            "fast": {"anchor_seconds": ANCHOR_SECONDS, "set": SET_ON},
        },
    )
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
    """The `just check` leg: a malformed anchor is a red, not a line nobody must read.

    Round 3's first finding: the passing arm used to name only `unit`, pinning
    a file missing `fast` green — the guard reached the malformation it was
    shown and not its sibling. A deleted key and a misspelled one both red now.
    """
    anchor_file = tmp_path / "anchor.json"
    monkeypatch.setattr(gate_clock, "ANCHOR_PATH", anchor_file)
    good: dict[str, object] = {
        "unit": {"anchor_seconds": 176, "set": SET_ON},
        "fast": {"anchor_seconds": 195, "set": SET_ON},
    }

    anchor_file.write_text("{not json", encoding="utf-8")
    assert gate_clock.main(["check"]) == 1
    assert "anchor unreadable" in capsys.readouterr().out

    write_anchor(anchor_file, {"unit": good["unit"]})  # the `fast` block deleted
    assert gate_clock.main(["check"]) == 1
    printed = capsys.readouterr().out
    assert "fast entry is missing" in printed

    write_anchor(anchor_file, {"unti": good["unit"], "fast": good["fast"]})  # the key misspelled
    assert gate_clock.main(["check"]) == 1
    printed = capsys.readouterr().out
    assert "unit entry is missing" in printed
    assert "unti is not a recipe" in printed

    write_anchor(anchor_file, good)
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
    assert all("coverage unknowable" in line for line in lines)


def test_the_target_count_is_the_tiers_own_selection_of_a_staged_tree(tmp_path: Path) -> None:
    """What `just mutation` would do work on, asked of the tier rather than re-derived.

    The fourth arrangement is the case a docs-only flag would have had to
    guess at: product code with no test module beside it. It counts zero
    because the tier plants nothing against it either — the run costs what a
    docs-only run costs, and the cost is what the record is measuring.
    """
    repo = stage_repo(tmp_path)
    lay_down(repo, "docs/note.md", "changelog.d/466-note.md")
    assert gate_clock.read_mutation_targets(repo) == 0

    lay_down(repo, "tests/unit/test_thing.py")
    assert gate_clock.read_mutation_targets(repo) == 1

    lay_down(repo, "extension/src/lib.rs")  # the shim arm, counted as one target
    assert gate_clock.read_mutation_targets(repo) == 2

    product_only = stage_repo(tmp_path, "product-only")
    lay_down(product_only, "src/cti_daemon/thing.py")
    assert gate_clock.read_mutation_targets(product_only) == 0


def test_an_exempt_target_plants_nothing_and_so_counts_as_nothing(tmp_path: Path) -> None:
    """The narrower form of #466's bias: a floor-priced run wearing a code run's count.

    `_judge` skips a `NO_MUTABLE_SUBJECT` target before calling `smoke`, so
    that run plants nothing and pays nothing — two of the list's entries are
    on it precisely because measuring them costs minutes. The exempt name is
    taken from the tier rather than written here, so removing an entry there
    moves this count with it.
    """
    exempt = next(iter(mutation_smoke.NO_MUTABLE_SUBJECT))
    repo = stage_repo(tmp_path)
    lay_down(repo, exempt)
    assert gate_clock.read_mutation_targets(repo) == 0

    lay_down(repo, "tests/unit/test_thing.py")
    assert gate_clock.read_mutation_targets(repo) == 1


def test_a_tree_git_cannot_be_asked_about_is_unclassified_not_zero(tmp_path: Path) -> None:
    """Zero would claim the tier had no work; only a run that was read can claim that."""
    assert gate_clock.read_mutation_targets(tmp_path / "nowhere") is None


def test_cheap_rows_cannot_hide_a_slowdown_in_the_fast_median() -> None:
    """#466's defect, arranged: floor-priced runs turning a fired line back into silence.

    The third assertion is what makes the first two mean something — the
    unfiltered median of the same ten rows sits under the threshold, so
    without the filter this window reads healthy while five real runs are at
    1.38x the anchor.
    """
    slow = fast_rows([ANCHOR_SECONDS * 1.38] * gate_clock.MIN_SAMPLE, targets=2)
    cheap = fast_rows([ANCHOR_SECONDS * 0.75] * gate_clock.MIN_SAMPLE, targets=0)
    assert fast_verdict_for(slow, fast_state()).reason == "slower"
    assert fast_verdict_for([*slow, *cheap], fast_state()).reason == "slower"
    unfiltered = gate_clock.median([one.wall_seconds for one in [*slow, *cheap]])
    assert unfiltered <= ANCHOR_SECONDS * gate_clock.THRESHOLD


def test_a_fast_window_of_only_cheap_rows_is_insufficient_not_healthy() -> None:
    """No comparable run is an unknown, and an unknown must not read as health."""
    cheap = fast_rows([ANCHOR_SECONDS * 0.75] * gate_clock.MIN_SAMPLE, targets=0)
    assert fast_verdict_for(cheap, fast_state()).reason == "insufficient_sample"


def test_the_unit_window_reads_every_kind() -> None:
    """`unit` carries no diff-scoped leg, so a zero-target row is the same measurement."""
    rows = [row(wall=ANCHOR_SECONDS, targets=0) for _ in range(gate_clock.MIN_SAMPLE)]
    assert verdict_for(rows, unit_state()).reason == "healthy"


def test_rows_written_before_the_count_stay_readable_and_leave_the_fast_window(
    tmp_path: Path,
) -> None:
    """The constraint the existing records impose: readable, and never guessed a kind for."""
    legacy = {
        "at": ROW_AT,
        "recipe": "fast",
        "wall_seconds": 81.49,
        "status": 0,
        "head": "c0ffee" * 6,
        "tests_collected": 5188,
        "load_1m": 0.42,
        "foreign_gate_processes": 0,
    }
    path = gate_clock.records_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(legacy) + "\n" for _ in range(gate_clock.MIN_SAMPLE)), encoding="utf-8"
    )
    read_back = gate_clock.load_records(tmp_path)
    assert len(read_back) == gate_clock.MIN_SAMPLE
    assert all(one.mutation_targets is None for one in read_back)
    assert all(one.wall_seconds == 81.49 for one in read_back)
    assert gate_clock.assess(read_back, fast_state())[1].reason == "insufficient_sample"


def test_history_counts_the_kinds_and_medians_only_the_comparable_rows(tmp_path: Path) -> None:
    """The retro's read shows what the window declined, not only a median that shrank."""
    for wall in (150.0, 160.0, 170.0):
        gate_clock.append_record(tmp_path, row(recipe="fast", wall=wall, targets=2))
    for _ in range(2):
        gate_clock.append_record(tmp_path, row(recipe="fast", wall=81.0, targets=0))
    gate_clock.append_record(tmp_path, row(recipe="fast", wall=81.0, targets=None))
    _unit_line, fast_line = gate_clock.history(tmp_path, fast_state())
    assert "6 green" in fast_line
    assert "2 with no mutation target" in fast_line
    assert "1 predating the target count" in fast_line
    assert "median(last 3 green) 160s" in fast_line
    assert "span 150s to 170s" in fast_line


def test_a_run_over_docs_and_a_run_over_code_land_as_different_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """#466's acceptance: two recorded runs, one diff kind each, told apart from the rows alone.

    Both runs are `fast` at the same staged wall, so nothing but the tree they
    were recorded against differs — and the shell line says which, so a zero is
    visible in the run's own output rather than only in a row nobody opens.
    """
    repo = stage_repo(tmp_path)
    staged = tmp_path / "uptime"
    staged.write_text("1000.50 2000.00\n", encoding="utf-8")
    monkeypatch.setattr(gate_clock, "PROC_UPTIME", staged)
    monkeypatch.setattr(gate_clock, "REPO_ROOT", repo)
    monkeypatch.delenv("CTI_GATE_CLOCK_COLLECTED_FILE", raising=False)
    run = [
        "--gate-clock-dir",
        str(tmp_path),
        "record",
        "--recipe",
        "fast",
        "--start-uptime",
        "1000.00",
        "--status",
        "0",
    ]

    lay_down(repo, "docs/note.md")
    assert gate_clock.main(run) == 0
    assert "0 mutation target(s)" in capsys.readouterr().out

    lay_down(repo, "tests/unit/test_thing.py")
    assert gate_clock.main(run) == 0
    assert "1 mutation target(s)" in capsys.readouterr().out

    docs_row, code_row = gate_clock.load_records(tmp_path)
    assert docs_row.mutation_targets == 0
    assert code_row.mutation_targets == 1
    assert docs_row.wall_seconds == code_row.wall_seconds
