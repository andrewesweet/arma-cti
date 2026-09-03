"""Tests for the read-only loop metrics reader (#602)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from conftest import load_tool

METRICS = load_tool("loop_metrics")


def _at(minutes: int) -> str:
    """Return a stable timezone-aware fixture timestamp."""
    return (datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=minutes)).isoformat()


def _write(path: Path, document: dict[str, object]) -> None:
    """Write one fixture document."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")


def _dispatch(  # noqa: PLR0913 — fixture fields mirror the durable dispatch shape
    root: Path,
    identifier: str,
    issue: int,
    seat: str,
    minute: int,
    *,
    ledger: dict[str, object] | None = None,
    ended_minute: int | None = None,
    omit_ended_at: bool = False,
    worktree: str | None = None,
) -> None:
    """Arrange a dispatch plan, a completed result and an optional ledger row."""
    directory = root / identifier
    resolved = worktree if worktree is not None else f"/repo/.claude/worktrees/issue-{issue}"
    _write(
        directory / "dispatch.json",
        {
            "dispatch_id": identifier,
            "issue": issue,
            "seat": seat,
            "planned_at": _at(minute),
            "worktree": resolved,
        },
    )
    result: dict[str, object] = {"started_at": _at(minute), "outcome": "ok"}
    if not omit_ended_at:
        result["ended_at"] = _at(minute + 1 if ended_minute is None else ended_minute)
    _write(directory / "result.json", result)
    if ledger is not None:
        _write(directory / "ledger.json", ledger)


def _loop_v2(root: Path, issue: int) -> None:
    """Arrange one v2 loop with a dismissal, a worth finding and a clean round."""
    _write(
        root / str(issue) / "loop.json",
        {
            "version": 2,
            "issue": issue,
            "review_rounds": 1,
            "findings": [
                {"id": "same-diff", "severity": "high", "round_raised": 0},
                {"id": "independent", "severity": "low", "round_raised": 1},
            ],
            "self_review": {
                "rounds": [
                    {
                        "number": 1,
                        "findings": [
                            {
                                "id": "same-diff",
                                "category": "not_worth_addressing",
                                "origin": "pre_existing",
                                "reason": "dismissed in the self pass",
                                "round_raised": 1,
                            },
                            {
                                "id": "own-fix",
                                "category": "worth_addressing",
                                "origin": "introduced",
                                "reason": "the local fix exposed it",
                                "round_raised": 1,
                            },
                        ],
                        "refutations": [
                            {"id": "refuted", "reason": "replayed the assertion", "round_raised": 1}
                        ],
                    },
                    {"number": 2, "findings": [], "refutations": []},
                ],
                "converged_on": "a" * 40,
            },
        },
    )


def test_v2_metrics_keep_self_and_independent_loops_separate(tmp_path: Path) -> None:
    """The v2 block drives self metrics while v1 remains valid non-self evidence."""
    dispatch_root = tmp_path / "dispatches"
    review_root = tmp_path / "review"
    queue_root = tmp_path / "queue"
    _dispatch(dispatch_root, "i10", 10, "implementer", 0)
    _dispatch(dispatch_root, "r10", 10, "review", 2)
    _dispatch(dispatch_root, "i11", 11, "implementer", 4)
    _dispatch(dispatch_root, "r11", 11, "review", 6)
    _loop_v2(review_root, 10)
    _write(
        review_root / "11" / "loop.json",
        {
            "version": 1,
            "issue": 11,
            "review_rounds": 0,
            "findings": [{"id": "v1", "severity": "medium", "round_raised": 0}],
        },
    )
    inputs = METRICS.read_inputs(dispatch_root, review_root, queue_root)
    window = METRICS.resolve_window(inputs, None, None, explicit=False)
    lines = METRICS.report_lines(inputs, tmp_path, window)
    joined = "\n".join(lines)

    assert "injection_rate aggregate numerator=1 denominator=2" in joined
    injection = next(line for line in lines if line.startswith("injection_rate aggregate"))
    assert "self_review_records=1 excluded_without_self_review=1" in injection
    assert "excluded_work_items=issue:11" in injection
    assert "catch_fraction numerator=1 denominator=3" in joined
    assert "bound=upper_bound" in joined
    catch = next(line for line in lines if line.startswith("catch_fraction "))
    assert "excluded_without_self_review=1 excluded_work_items=issue:11" in catch
    assert "dismissal_misses numerator=1 denominator=1" in joined
    dismissal = next(line for line in lines if line.startswith("dismissal_misses "))
    assert "excluded_without_self_review=1 excluded_work_items=issue:11" in dismissal
    assert "dismissal_matching=exact_nonempty_id_same_work_item_unique_independent_match" in joined
    assert "findings_per_independent_review reviews=2 findings=3" in joined
    assert "severity_mix severity=medium numerator=1 denominator=3" in joined
    assert "clean_round_distribution round=2 numerator=1 denominator=1" in joined
    clean = next(line for line in lines if line.startswith("clean_round_distribution "))
    assert "excluded_without_self_review=1 excluded_work_items=issue:11" in clean
    assert "return_rate numerator=0 denominator=2" in joined
    assert "return_model lambda=0.000000" in joined
    assert "no_self_review_is_not_zero" in joined


def test_malformed_self_review_keeps_independent_metrics(tmp_path: Path) -> None:
    """An unreadable self block does not erase the independent half of a loop."""
    dispatch_root = tmp_path / "dispatches"
    review_root = tmp_path / "review"
    _dispatch(dispatch_root, "i20", 20, "implementer", 0)
    _dispatch(dispatch_root, "r20", 20, "review", 2)
    _write(
        review_root / "20" / "loop.json",
        {
            "version": 2,
            "issue": 20,
            "review_rounds": 0,
            "findings": [{"id": "independent", "severity": "high", "round_raised": 0}],
            "self_review": {"rounds": "not-a-list"},
        },
    )

    inputs = METRICS.read_inputs(dispatch_root, review_root, tmp_path / "queue")
    lines = METRICS.report_lines(
        inputs, tmp_path, METRICS.resolve_window(inputs, None, None, explicit=False)
    )
    joined = "\n".join(lines)

    assert len(inputs.loops) == 1
    assert inputs.loops[0].independent_present is True
    assert inputs.loops[0].self_review_present is False
    assert "findings_per_independent_review reviews=1 findings=1" in joined
    assert "severity_mix severity=high numerator=1 denominator=1" in joined
    assert "excluded_without_self_review=1 excluded_work_items=issue:20" in next(
        line for line in lines if line.startswith("injection_rate ")
    )
    assert "excluded_without_self_review=1 excluded_work_items=issue:20" in next(
        line for line in lines if line.startswith("catch_fraction ")
    )
    assert "excluded_without_self_review=1 excluded_work_items=issue:20" in next(
        line for line in lines if line.startswith("dismissal_misses ")
    )
    assert "excluded_without_self_review=1 excluded_work_items=issue:20" in next(
        line for line in lines if line.startswith("clean_round_distribution ")
    )
    assert "review issue=20 status=unreadable reason=self_rounds" in joined


def test_self_review_exclusion_names_are_bounded() -> None:
    """A complete exclusion count stays readable when many Work Items lack self-review."""
    loops = tuple(
        METRICS.LoopRecord(issue, 0, (), (), self_review_present=False) for issue in range(1, 26)
    )

    line = METRICS.injection_lines(loops)[0]

    assert "excluded_without_self_review=25" in line
    assert "excluded_work_items=issue:1,issue:2,issue:3" in line
    assert "excluded_work_items_omitted=5" in line
    assert "issue:21" not in line


def test_malformed_independent_findings_keeps_self_metrics(tmp_path: Path) -> None:
    """An unreadable independent block does not erase the self-review half."""
    review_root = tmp_path / "review"
    _write(
        review_root / "22" / "loop.json",
        {
            "version": 2,
            "issue": 22,
            "review_rounds": 0,
            "findings": "not-a-list",
            "self_review": {
                "rounds": [
                    {
                        "number": 1,
                        "findings": [
                            {
                                "id": "own-fix",
                                "category": "worth_addressing",
                                "origin": "introduced",
                                "reason": "the local fix exposed it",
                                "round_raised": 1,
                            }
                        ],
                        "refutations": [],
                    }
                ]
            },
        },
    )

    inputs = METRICS.read_inputs(tmp_path / "dispatches", review_root, tmp_path / "queue")
    lines = METRICS.report_lines(
        inputs, tmp_path, METRICS.resolve_window(inputs, None, None, explicit=False)
    )
    joined = "\n".join(lines)

    assert len(inputs.loops) == 1
    assert inputs.loops[0].independent_present is False
    assert inputs.loops[0].self_review_present is True
    assert "injection_rate aggregate numerator=1 denominator=1" in joined
    assert "findings_per_independent_review status=too_few" in joined
    assert "review issue=22 status=unreadable reason=findings" in joined


def test_duplicate_independent_ids_are_reported_as_ambiguous(tmp_path: Path) -> None:
    """Duplicate independent identities remain evidence and make matching ambiguous."""
    review_root = tmp_path / "review"
    _write(
        review_root / "21" / "loop.json",
        {
            "version": 2,
            "issue": 21,
            "review_rounds": 0,
            "findings": [
                {"id": "same", "severity": "high", "round_raised": 0},
                {"id": "same", "severity": "low", "round_raised": 0},
            ],
            "self_review": {
                "rounds": [
                    {
                        "number": 1,
                        "findings": [
                            {
                                "id": "same",
                                "category": "not_worth_addressing",
                                "origin": "pre_existing",
                                "reason": "dismissed",
                                "round_raised": 1,
                            }
                        ],
                        "refutations": [],
                    }
                ]
            },
        },
    )

    inputs = METRICS.read_inputs(tmp_path / "dispatches", review_root, tmp_path / "queue")
    record = inputs.loops[0]

    assert len(record.independent_findings) == 2
    assert METRICS.dismissal_match_counts((record,)) == (0, 1, 0, 1, ("21:same:ambiguous",))
    assert "duplicate_ids=ambiguous" in "\n".join(METRICS.dismissal_lines((record,)))
    assert any("duplicate_finding_id" in diagnostic for diagnostic in inputs.diagnostics)


def test_findings_population_uses_reviews_inside_the_window() -> None:
    """A loop outside the selected review population cannot inflate its mean or mix."""
    loops = tuple(
        METRICS.LoopRecord(
            issue,
            0,
            (METRICS.IndependentFinding(f"finding-{issue}", severity, 0),),
            (),
            self_review_present=False,
        )
        for issue, severity in ((30, "high"), (31, "low"))
    )
    dispatches = tuple(
        METRICS.DispatchRecord(
            dispatch_id=f"review-{issue}",
            issue=issue,
            seat="review",
            planned_at=planned_at,
            result_state="readable",
            result_started_at=None,
            result_ended_at=None,
            ledger_row=True,
            ledger_materialised_at=None,
            landed_sha=None,
            landed_at=None,
            path=Path(),
        )
        for issue, planned_at in ((30, 5.0), (31, 15.0))
    )

    lines = METRICS.findings_lines(loops, dispatches, METRICS.Window(0.0, 10.0, explicit=True))
    joined = "\n".join(lines)

    assert "findings_per_independent_review reviews=1 findings=1" in joined
    assert "severity_mix severity=high numerator=1 denominator=1" in joined
    assert "severity_mix severity=low numerator=0 denominator=1" in joined


def test_historic_stock_levels_use_end_timestamps_and_are_reproducible(tmp_path: Path) -> None:
    """A historic end reads active and materialised state at that boundary."""
    dispatch_root = tmp_path / "dispatches"
    _dispatch(
        dispatch_root,
        "late-close",
        40,
        "implementer",
        0,
        ended_minute=10,
        ledger={"materialised_at": _at(10)},
    )
    _dispatch(dispatch_root, "early-close", 41, "review", 2, ended_minute=3)
    inputs = METRICS.read_inputs(dispatch_root, tmp_path / "review", tmp_path / "queue")
    window = METRICS.Window(0.0, METRICS.parse_timestamp(_at(5)), explicit=True)

    first = METRICS.report_lines(inputs, tmp_path, window)
    second = METRICS.report_lines(inputs, tmp_path, window)
    joined = "\n".join(first)

    assert "stock runs_in_flight level=1" in joined
    assert "stock dispatches_without_ledger level=2" in joined
    assert first == second


def test_runs_in_flight_counts_known_endings_and_names_missing_ones(tmp_path: Path) -> None:
    """An incomplete result does not erase the stock level computed from known endings."""
    dispatch_root = tmp_path / "dispatches"
    _dispatch(dispatch_root, "known", 42, "implementer", 0, ended_minute=3)
    _dispatch(dispatch_root, "missing-end", 43, "review", 1, omit_ended_at=True)
    inputs = METRICS.read_inputs(dispatch_root, tmp_path / "review", tmp_path / "queue")
    window = METRICS.Window(0.0, METRICS.parse_timestamp(_at(2)), explicit=True)

    line = next(
        line
        for line in METRICS.stock_lines(inputs, tmp_path, window)
        if line.startswith("stock runs_in_flight")
    )

    assert "level=1" in line
    assert "excluded_without_ended_at=1" in line


def test_empty_dispatch_source_reports_zero_stock_levels(tmp_path: Path) -> None:
    """An empty dispatch source has known zero levels and no excluded evidence."""
    inputs = METRICS.Inputs(dispatches=(), loops=(), queue_rows=(), diagnostics=())
    lines = METRICS.stock_lines(inputs, tmp_path, METRICS.Window(0.0, 2.0, explicit=True))

    runs = next(line for line in lines if line.startswith("stock runs_in_flight"))
    ledger = next(line for line in lines if line.startswith("stock dispatches_without_ledger"))

    assert "level=0 excluded_without_ended_at=0" in runs
    assert "level=0 excluded_without_materialised_at=0" in ledger


def test_dispatches_without_ledger_counts_known_rows_and_names_missing_timestamps(
    tmp_path: Path,
) -> None:
    """An incomplete ledger timestamp does not erase known missing-row evidence."""
    dispatch_root = tmp_path / "dispatches"
    _dispatch(dispatch_root, "missing-row", 44, "implementer", 0)
    _dispatch(dispatch_root, "missing-materialised", 45, "review", 1, ledger={})
    inputs = METRICS.read_inputs(dispatch_root, tmp_path / "review", tmp_path / "queue")
    window = METRICS.Window(0.0, METRICS.parse_timestamp(_at(2)), explicit=True)

    line = next(
        line
        for line in METRICS.stock_lines(inputs, tmp_path, window)
        if line.startswith("stock dispatches_without_ledger")
    )

    assert "level=1" in line
    assert "excluded_without_materialised_at=1" in line


def _landed_ledger(minute: int) -> dict[str, object]:
    """Arrange one ledger row whose gate attests a landing with a timestamp."""
    return {
        "materialised_at": _at(minute - 1),
        "gate": {
            "outcome": "landed",
            "landed_at": _at(minute),
            "landed": {"sha": "a" * 40, "landed_at": _at(minute)},
        },
    }


def _worktree_line(
    inputs: METRICS.Inputs,
    repo: Path,
    window: METRICS.Window,
    diagnostics: list[str] | None = None,
) -> str:
    """Select the worktree stock line — the one selection every worktree test repeats."""
    return next(
        line
        for line in METRICS.stock_lines(inputs, repo, window, diagnostics)
        if line.startswith("stock worktrees_owing_done")
    )


def test_worktree_owing_done_joins_registrations_to_attested_landings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A registration counts when its issue has any landing attested by the end."""
    dispatch_root = tmp_path / "dispatches"
    _dispatch(
        dispatch_root,
        "i50",
        50,
        "implementer",
        0,
        ledger=_landed_ledger(11),
        worktree="/repo/.claude/worktrees/issue-50",
    )
    _dispatch(
        dispatch_root,
        "i51",
        51,
        "implementer",
        0,
        worktree="/repo/.claude/worktrees/issue-51",
    )
    _dispatch(
        dispatch_root,
        "i53",
        53,
        "implementer",
        0,
        ledger=_landed_ledger(20),
        worktree="/repo/.claude/worktrees/issue-53",
    )
    # Issue 54 landed inside the window and again after it; either landing settles it.
    _dispatch(
        dispatch_root,
        "i54",
        54,
        "implementer",
        0,
        ledger=_landed_ledger(9),
        worktree="/repo/.claude/worktrees/issue-54",
    )
    _dispatch(
        dispatch_root,
        "i54-r2",
        54,
        "review",
        0,
        ledger=_landed_ledger(25),
        worktree="/repo/.claude/worktrees/review-54-r2",
    )
    # An unnamed tree registers but cannot join to a landing.
    _dispatch(
        dispatch_root,
        "u1",
        55,
        "implementer",
        0,
        worktree="/repo/.claude/worktrees/dispatch-d-20260827-103751-65cbec",
    )
    inputs = METRICS.read_inputs(dispatch_root, tmp_path / "review", tmp_path / "queue")
    monkeypatch.setattr(
        METRICS,
        "_issue_registrations",
        # the live sweep is never consulted on a bounded window; pin that
        lambda _repo: pytest.fail("live sweep must not run for a bounded window"),
    )

    window = METRICS.Window(0.0, METRICS.parse_timestamp(_at(15)), explicit=True)
    line = _worktree_line(inputs, tmp_path, window)

    assert "level=3 " in line  # 50, review-54-r2, and 54; 53 landed after the end
    assert "registrations=6 excluded_without_issue_name=1" in line
    assert "setpoint=at_most_0 status=above_setpoint alarm=3" in line
    assert "registration_basis=dispatch_records_through_boundary" in line
    assert (
        "bias_paths=unmaterialised_ledger_landings:under_counts,"
        "closed_issue_without_landing:under_counts,"
        "issue_reopened_after_landing:over_counts,"
        "landed_issue_still_open:over_counts,"
        "landing_time_unreadable:under_counts,"
        "hand_made_registrations_without_dispatch:under_counts,"
        "tree_created_before_first_dispatch:under_counts,"
        "worktrees_removed_before_boundary:over_counts,"
        "unreadable_worktree_field:under_counts"
    ) in line
    # The temporal caveat is its own field, not a suffix of the basis value:
    # assert the field boundary, not merely the token.
    assert " temporal=hand_made_registrations_absent_from_dispatch_records" in line
    assert "landing_basis=ledger_landed_at " in line
    assert "tracker_closure_unseen " in line
    assert "bias=under_counts" not in line


def test_worktree_stock_registration_after_boundary_leaves_the_past_level_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Adding a registration after a bounded window cannot move that window's level."""
    dispatch_root = tmp_path / "dispatches"
    _dispatch(
        dispatch_root,
        "early",
        60,
        "implementer",
        0,
        ledger=_landed_ledger(5),
        worktree="/repo/.claude/worktrees/issue-60",
    )
    # Planned after the boundary: no registration may be reconstructed from it.
    _dispatch(
        dispatch_root,
        "late",
        61,
        "implementer",
        40,
        worktree="/repo/.claude/worktrees/issue-61",
    )
    inputs = METRICS.read_inputs(dispatch_root, tmp_path / "review", tmp_path / "queue")
    monkeypatch.setattr(
        METRICS,
        "_issue_registrations",
        # the live sweep is never consulted on a bounded window; pin that
        lambda _repo: pytest.fail("live sweep must not run for a bounded window"),
    )

    window = METRICS.Window(0.0, METRICS.parse_timestamp(_at(15)), explicit=True)
    line = _worktree_line(inputs, tmp_path, window)

    assert "level=1" in line  # the late tree is invisible as of minute 15
    assert "registrations=1 excluded_without_issue_name=0" in line
    assert "registration_basis=dispatch_records_through_boundary" in line
    assert " temporal=hand_made_registrations_absent_from_dispatch_records," in line
    assert "trees_created_before_their_first_dispatch" in line


def test_worktree_stock_names_the_planned_at_undercount(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tree created before its first dispatch is a second under-counted path."""
    dispatch_root = tmp_path / "dispatches"
    # The tree is created at minute 10 (`just worktree add`), its first dispatch
    # is planned at minute 20, and the boundary sits at minute 15: the tree
    # existed at the boundary but no record places it there yet, because
    # `planned_at` bounds existence from below rather than dating creation.
    _dispatch(
        dispatch_root,
        "late",
        61,
        "implementer",
        20,
        worktree="/repo/.claude/worktrees/issue-61",
    )
    inputs = METRICS.read_inputs(dispatch_root, tmp_path / "review", tmp_path / "queue")
    monkeypatch.setattr(
        METRICS,
        "_issue_registrations",
        # the live sweep is never consulted on a bounded window; pin that
        lambda _repo: pytest.fail("live sweep must not run for a bounded window"),
    )

    window = METRICS.Window(0.0, METRICS.parse_timestamp(_at(15)), explicit=True)
    line = _worktree_line(inputs, tmp_path, window)

    assert "level=0" in line  # the reconstruction cannot see the tree; the bias fields say so
    assert "tree_created_before_first_dispatch:under_counts" in line
    assert " temporal=hand_made_registrations_absent_from_dispatch_records," in line
    assert "trees_created_before_their_first_dispatch" in line


def test_worktree_stock_unreadable_landing_is_excluded_and_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A landed SHA whose time cannot be read is excluded and named, not a stock-wide unknown."""
    dispatch_root = tmp_path / "dispatches"
    # The canonical schema has no `landed_at`: `gate=landed` with a SHA and no
    # time is well-formed input, and the commit lookup failing must not read as
    # an absent landing.
    _dispatch(
        dispatch_root,
        "opaque",
        61,
        "implementer",
        0,
        ledger={
            "materialised_at": _at(4),
            "gate": {"outcome": "landed", "landed": {"sha": "d" * 40}},
        },
        worktree="/repo/.claude/worktrees/issue-61",
    )
    monkeypatch.setattr(METRICS, "_commit_timestamp", lambda _repo, _sha: None)
    inputs = METRICS.read_inputs(dispatch_root, tmp_path / "review", tmp_path / "queue")
    diagnostics: list[str] = []

    window = METRICS.Window(0.0, METRICS.parse_timestamp(_at(15)), explicit=True)
    line = _worktree_line(inputs, tmp_path, window, diagnostics)

    # The one tree's settlement is unknown, so the level of 0 is a bound the
    # excluded tree could still break: named beside the level, never claimed
    # at_setpoint.
    assert "level=0 " in line
    assert "registrations=1 excluded_without_issue_name=0 excluded_without_landing_time=1" in line
    assert "setpoint=at_most_0 status=unresolved" in line
    assert "status=at_setpoint" not in line
    assert "landing_basis=none_no_qualifying_landing" in line
    assert "landing_time_unreadable:under_counts" in line
    assert any(
        diagnostic.startswith("landing issue=61 sha=") and diagnostic.endswith("status=unrecorded")
        for diagnostic in diagnostics
    )


def test_worktree_stock_resolved_landing_settles_its_tree_despite_an_unresolved_sibling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A resolved landing settles its tree; the unresolved sibling is excluded and named."""
    dispatch_root = tmp_path / "dispatches"
    _dispatch(
        dispatch_root,
        "readable",
        62,
        "implementer",
        0,
        ledger=_landed_ledger(5),
        worktree="/repo/.claude/worktrees/issue-62",
    )
    _dispatch(
        dispatch_root,
        "opaque",
        63,
        "implementer",
        0,
        ledger={
            "materialised_at": _at(4),
            "gate": {"outcome": "landed", "landed": {"sha": "e" * 40}},
        },
        worktree="/repo/.claude/worktrees/issue-63",
    )
    monkeypatch.setattr(METRICS, "_commit_timestamp", lambda _repo, _sha: None)
    inputs = METRICS.read_inputs(dispatch_root, tmp_path / "review", tmp_path / "queue")

    window = METRICS.Window(0.0, METRICS.parse_timestamp(_at(15)), explicit=True)
    line = _worktree_line(inputs, tmp_path, window)

    # Issue 62's landing resolved, so its tree is counted; issue 63's tree has
    # no readable landing, so it is excluded and named rather than dropping the
    # whole stock to unknown.
    assert "level=1 " in line
    assert "registrations=2 excluded_without_issue_name=0 excluded_without_landing_time=1" in line
    assert "status=above_setpoint" in line
    assert "landing_basis=ledger_landed_at " in line
    assert "landing_time_unreadable:under_counts" in line


def test_worktree_stock_damages_are_named_once_per_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`report_lines` derives the landing evidence twice; one damage is named once."""
    dispatch_root = tmp_path / "dispatches"
    _dispatch(
        dispatch_root,
        "opaque",
        64,
        "implementer",
        0,
        ledger={
            "materialised_at": _at(4),
            "gate": {"outcome": "landed", "landed": {"sha": "f" * 40}},
        },
        worktree="/repo/.claude/worktrees/issue-64",
    )
    monkeypatch.setattr(METRICS, "_commit_timestamp", lambda _repo, _sha: None)
    inputs = METRICS.read_inputs(dispatch_root, tmp_path / "review", tmp_path / "queue")

    window = METRICS.Window(0.0, METRICS.parse_timestamp(_at(15)), explicit=True)
    lines = METRICS.report_lines(inputs, tmp_path, window)

    landing_lines = [line for line in lines if line.startswith("landing issue=64 sha=")]
    assert len(landing_lines) == 1
    assert landing_lines[0].endswith("status=unrecorded")


def test_issue_registrations_skip_main_checkout_and_name_unjoinable() -> None:
    """The main checkout never owes done and unnamed registrations stay visible."""
    porcelain = (
        "worktree /repo\n"
        "branch refs/heads/main\n"
        "\n"
        "worktree /repo/.claude/worktrees/issue-672\n"
        "detached\n"
        "\n"
        "worktree /repo/.claude/worktrees/review-525-r2\n"
        "detached\n"
        "\n"
        "worktree /repo/.claude/worktrees/review-328b\n"
        "detached\n"
        "\n"
        "worktree /repo/.claude/worktrees/review-497-guidance\n"
        "detached\n"
        "\n"
        "worktree /repo/.claude/worktrees/audit-319\n"
        "detached\n"
        "\n"
        "worktree /repo/.claude/worktrees/dispatch-d-20260827-103751-65cbec\n"
        "detached\n"
        "\n"
        "worktree /home/andre/.codex/9f2/arma-cti\n"
        "detached"
    )

    assert METRICS._parse_issue_registrations(porcelain) == (  # noqa: SLF001 — pin the parser
        (Path("/repo/.claude/worktrees/issue-672"), 672),
        (Path("/repo/.claude/worktrees/review-525-r2"), 525),
        (Path("/repo/.claude/worktrees/review-328b"), 328),
        (Path("/repo/.claude/worktrees/review-497-guidance"), 497),
        (Path("/repo/.claude/worktrees/audit-319"), 319),
        (Path("/repo/.claude/worktrees/dispatch-d-20260827-103751-65cbec"), None),
        (Path("/home/andre/.codex/9f2/arma-cti"), None),
    )


def test_worktree_stock_names_the_commit_timestamp_proxy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A landing time read from the commit itself is labelled with its bias."""
    dispatch_root = tmp_path / "dispatches"
    _dispatch(
        dispatch_root,
        "proxy",
        60,
        "implementer",
        0,
        ledger={
            "materialised_at": _at(4),
            "gate": {"outcome": "landed", "landed": {"sha": "b" * 40}},
        },
        worktree="/repo/.claude/worktrees/review-60b",
    )
    monkeypatch.setattr(
        METRICS, "_commit_timestamp", lambda _repo, _sha: METRICS.parse_timestamp(_at(9))
    )
    inputs = METRICS.read_inputs(dispatch_root, tmp_path / "review", tmp_path / "queue")
    monkeypatch.setattr(
        METRICS,
        "_issue_registrations",
        # the live sweep is never consulted on a bounded window; pin that
        lambda _repo: pytest.fail("live sweep must not run for a bounded window"),
    )

    window = METRICS.Window(0.0, METRICS.parse_timestamp(_at(15)), explicit=True)
    line = _worktree_line(inputs, tmp_path, window)

    assert "level=1" in line
    assert "landing_basis=commit_timestamp" in line
    assert "proxy_bias=reads_early_over_counts_near_boundary" in line


def test_worktree_stock_names_a_mixed_landing_basis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Attested and proxy landings together report the mix, not the louder half."""
    dispatch_root = tmp_path / "dispatches"
    _dispatch(dispatch_root, "att", 80, "implementer", 0, ledger=_landed_ledger(5))
    _dispatch(
        dispatch_root,
        "mix",
        81,
        "implementer",
        0,
        ledger={
            "materialised_at": _at(4),
            "gate": {"outcome": "landed", "landed": {"sha": "c" * 40}},
        },
    )
    monkeypatch.setattr(
        METRICS, "_commit_timestamp", lambda _repo, _sha: METRICS.parse_timestamp(_at(9))
    )
    inputs = METRICS.read_inputs(dispatch_root, tmp_path / "review", tmp_path / "queue")
    porcelain = "\n".join(
        [
            "worktree /repo",
            f"HEAD {'0' * 40}",
            "branch refs/heads/main",
            "",
            "worktree /repo/.claude/worktrees/issue-80",
            f"HEAD {'9' * 40}",
            "detached",
            "",
            "worktree /repo/.claude/worktrees/issue-81",
            f"HEAD {'a' * 40}",
            "detached",
        ]
    )
    monkeypatch.setattr(
        METRICS,
        "_issue_registrations",
        lambda _repo: METRICS._parse_issue_registrations(porcelain),  # noqa: SLF001
    )

    line = _worktree_line(inputs, tmp_path, METRICS.Window(0.0, None, explicit=False))

    assert "level=2" in line
    assert "landing_basis=mixed_commit_timestamp_and_ledger_landed_at" in line
    assert "proxy_bias=reads_early_over_counts_near_boundary" in line
    assert "landing_basis=ledger_landed_at" not in line.replace(
        "mixed_commit_timestamp_and_ledger_landed_at", ""
    )
    assert "temporal=" not in line


def test_worktree_stock_without_a_qualifying_landing_names_no_basis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A level no landing participated in borrows neither basis label."""
    dispatch_root = tmp_path / "dispatches"
    # Issue 90 has a registration but its dispatch never landed.
    _dispatch(dispatch_root, "nope", 90, "implementer", 0)
    inputs = METRICS.read_inputs(dispatch_root, tmp_path / "review", tmp_path / "queue")
    porcelain = "\n".join(
        [
            "worktree /repo",
            f"HEAD {'0' * 40}",
            "branch refs/heads/main",
            "",
            "worktree /repo/.claude/worktrees/issue-90",
            f"HEAD {'b' * 40}",
            "detached",
        ]
    )
    monkeypatch.setattr(
        METRICS,
        "_issue_registrations",
        lambda _repo: METRICS._parse_issue_registrations(porcelain),  # noqa: SLF001
    )

    line = _worktree_line(inputs, tmp_path, METRICS.Window(0.0, None, explicit=False))

    assert "level=0" in line
    assert "landing_basis=none_no_qualifying_landing" in line
    assert "ledger_landed_at" not in line
    assert "commit_timestamp" not in line
    assert "proxy_bias" not in line


def test_worktree_stock_current_window_states_its_bias_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without a boundary the sweep is the answer: the standing paths, no as-of caveat."""
    dispatch_root = tmp_path / "dispatches"
    _dispatch(dispatch_root, "cur", 70, "implementer", 0, ledger=_landed_ledger(3))
    inputs = METRICS.read_inputs(dispatch_root, tmp_path / "review", tmp_path / "queue")
    porcelain = "\n".join(
        [
            "worktree /repo",
            f"HEAD {'0' * 40}",
            "branch refs/heads/main",
            "",
            "worktree /repo/.claude/worktrees/issue-70",
            f"HEAD {'8' * 40}",
            "detached",
        ]
    )
    monkeypatch.setattr(
        METRICS,
        "_issue_registrations",
        lambda _repo: METRICS._parse_issue_registrations(porcelain),  # noqa: SLF001
    )

    line = _worktree_line(inputs, tmp_path, METRICS.Window(0.0, None, explicit=False))

    assert "level=1" in line
    assert (
        "bias_paths=unmaterialised_ledger_landings:under_counts,"
        "closed_issue_without_landing:under_counts,"
        "issue_reopened_after_landing:over_counts,"
        "landed_issue_still_open:over_counts,"
        "landing_time_unreadable:under_counts"
    ) in line
    assert "bias=mixed net_direction=undetermined" in line
    assert "not_as_of_window_end" not in line
    assert "registrations_removed_since_boundary" not in line
    assert "landing_basis=ledger_landed_at " in line
    assert "temporal=" not in line
    assert "excluded_without_readable_worktree=0" in line


def test_worktree_stock_names_unreadable_registrations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A sweep that cannot answer stays unrecorded and never becomes zero."""
    monkeypatch.setattr(METRICS, "_issue_registrations", lambda _repo: None)
    inputs = METRICS.Inputs(dispatches=(), loops=(), queue_rows=(), diagnostics=())

    line = _worktree_line(inputs, tmp_path, METRICS.Window(0.0, None, explicit=True))

    assert "level=unrecorded setpoint=at_most_0 status=unrecorded" in line
    assert "reason=worktree_registrations_unreadable" in line
    assert "bias=under_counts" not in line


def test_worktree_stock_diagnoses_a_damaged_worktree_field(
    tmp_path: Path,
) -> None:
    """A record whose worktree field is damaged is diagnosed, never a tree."""
    dispatch_root = tmp_path / "dispatches"
    _dispatch(
        dispatch_root,
        "placed",
        90,
        "implementer",
        0,
        ledger=_landed_ledger(5),
        worktree="/repo/.claude/worktrees/issue-90",
    )
    directory = dispatch_root / "damaged"
    _write(
        directory / "dispatch.json",
        {
            "dispatch_id": "damaged",
            "issue": 93,
            "seat": "implementer",
            "planned_at": _at(1),
            "worktree": 7,
        },
    )
    _write(directory / "result.json", {"started_at": _at(1), "outcome": "ok", "ended_at": _at(2)})
    inputs = METRICS.read_inputs(dispatch_root, tmp_path / "review", tmp_path / "queue")

    window = METRICS.Window(0.0, METRICS.parse_timestamp(_at(15)), explicit=True)
    line = _worktree_line(inputs, tmp_path, window)

    assert "level=1" in line  # only the record that placed a tree joins
    assert "registrations=1" in line
    assert "excluded_without_readable_worktree=1" in line
    assert any(
        "dispatch=damaged field=worktree status=unreadable reason=not_a_string" in diagnostic
        for diagnostic in inputs.diagnostics
    )


def test_unreadable_worktree_field_keeps_the_setpoint_unclaimed(tmp_path: Path) -> None:
    """A record that cannot place a tree is an exclusion the level could still feel."""
    dispatch_root = tmp_path / "dispatches"
    directory = dispatch_root / "damaged"
    _write(
        directory / "dispatch.json",
        {
            "dispatch_id": "damaged",
            "issue": 73,
            "seat": "implementer",
            "planned_at": _at(1),
            "worktree": 7,
        },
    )
    _write(directory / "result.json", {"started_at": _at(1), "outcome": "ok", "ended_at": _at(2)})
    inputs = METRICS.read_inputs(dispatch_root, tmp_path / "review", tmp_path / "queue")

    window = METRICS.Window(0.0, METRICS.parse_timestamp(_at(15)), explicit=True)
    line = _worktree_line(inputs, tmp_path, window)

    # The reconstruction cannot prove the tree absent: a zero that claimed the
    # setpoint would be the damaged record reading as health.
    assert "level=0 " in line
    assert "registrations=0" in line
    assert "excluded_without_readable_worktree=1" in line
    assert "status=unresolved" in line
    assert "status=at_setpoint" not in line


def test_setpoint_status_derives_from_its_exclusions() -> None:
    """Exclusions hold ``at_setpoint`` back; a level already above still reads."""
    assert METRICS._maximum_setpoint_status(0, 0, 0) == "at_setpoint"  # noqa: SLF001
    assert METRICS._maximum_setpoint_status(0, 0, 1) == "unresolved"  # noqa: SLF001
    assert METRICS._maximum_setpoint_status(1, 0, 1) == "above_setpoint"  # noqa: SLF001
    assert METRICS._maximum_setpoint_status(None, 0, 0) == "unrecorded"  # noqa: SLF001


def test_landed_sha_is_validated_before_it_reaches_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An option-shaped ledger SHA is refused at read, never handed to git."""
    dispatch_root = tmp_path / "dispatches"
    _dispatch(
        dispatch_root,
        "tampered",
        71,
        "implementer",
        0,
        ledger={
            "materialised_at": _at(4),
            "gate": {"outcome": "landed", "landed": {"sha": "--output=/tmp/arma-cti-pwn"}},
        },
        worktree="/repo/.claude/worktrees/issue-71",
    )
    monkeypatch.setattr(
        METRICS,
        "_git_text",
        lambda _repo, _args: pytest.fail("git must not be consulted for an unvalidated SHA"),
    )
    inputs = METRICS.read_inputs(dispatch_root, tmp_path / "review", tmp_path / "queue")

    window = METRICS.Window(0.0, METRICS.parse_timestamp(_at(15)), explicit=True)
    line = _worktree_line(inputs, tmp_path, window)

    # The row attests a landing its SHA cannot support: excluded and named,
    # never a healthy zero, and git never ran.
    assert "level=0 " in line
    assert "excluded_without_landing_time=1" in line
    assert "status=unresolved" in line
    assert "status=at_setpoint" not in line
    assert any("reason=landed_sha" in diagnostic for diagnostic in inputs.diagnostics)


def test_commit_timestamp_separates_the_revision_from_its_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The SHA rides behind `--end-of-options`, so it cannot parse as an option."""
    captured: list[list[str]] = []

    def fake_git_text(_repo: Path, args: list[str]) -> str:
        captured.append(args)
        return "2026-01-01T00:00:00+00:00\n"

    monkeypatch.setattr(METRICS, "_git_text", fake_git_text)

    timestamp = METRICS._commit_timestamp(Path("/repo"), "a" * 40)  # noqa: SLF001

    assert timestamp == METRICS.parse_timestamp("2026-01-01T00:00:00+00:00")
    assert captured == [["show", "-s", "--format=%cI", "--end-of-options", "a" * 40]]


@pytest.mark.parametrize(
    "gate",
    [
        {"outcome": "landed"},
        {"outcome": "landed", "landed": "not-a-mapping"},
        {"outcome": "landed", "landed": {"sha": ""}},
        {"outcome": "landed", "landed": {"sha": "not-hex"}},
        {"outcome": "landed", "landed": {"sha": "A" * 40}},
        {"outcome": "landed", "landed": {"sha": "a" * 64 + "extra"}},
    ],
)
def test_damaged_landed_evidence_is_unresolved_never_a_healthy_zero(
    tmp_path: Path, gate: dict[str, object]
) -> None:
    """A landing the row attests but cannot read is an exclusion, never a zero."""
    dispatch_root = tmp_path / "dispatches"
    _dispatch(
        dispatch_root,
        "damaged",
        72,
        "implementer",
        0,
        ledger={"materialised_at": _at(4), "gate": gate},
        worktree="/repo/.claude/worktrees/issue-72",
    )
    inputs = METRICS.read_inputs(dispatch_root, tmp_path / "review", tmp_path / "queue")

    window = METRICS.Window(0.0, METRICS.parse_timestamp(_at(15)), explicit=True)
    line = _worktree_line(inputs, tmp_path, window)

    assert "level=0 " in line
    assert "excluded_without_landing_time=1" in line
    assert "status=unresolved" in line
    assert "status=at_setpoint" not in line


def test_queue_stock_requires_a_counted_non_boolean_baseline() -> None:
    """Uncounted and boolean baseline values cannot create queue flow or trend."""
    reading = METRICS._queue_stock(  # noqa: SLF001 — pin the baseline evidence guard
        (
            {"sampled_at": 1.0, "queue": "ready_work", "state": "uncounted", "count": 99},
            {"sampled_at": 1.5, "queue": "ready_work", "state": "counted", "count": True},
            {"sampled_at": 2.0, "queue": "ready_work", "state": "counted", "count": 2},
        ),
        "ready_work",
        METRICS.Window(0.0, 2.0, explicit=True),
    )

    assert reading.level == 2
    assert reading.flow_creation == "0"
    assert reading.flow_clearing == "0"
    assert reading.trend == "unrecorded"


def test_stock_lines_report_blocked_queue_and_ruled_alarm_statuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stock output names the canonical blocked queue and evaluates every alarm."""
    monkeypatch.setattr(METRICS, "_issue_registrations", lambda _repo: None)
    inputs = METRICS.Inputs(
        dispatches=(),
        loops=(),
        queue_rows=(
            {"sampled_at": 1.0, "queue": "ready_work", "state": "counted", "count": 2},
            {"sampled_at": 1.0, "queue": "dispatch_slot", "state": "counted", "count": 4},
        ),
        diagnostics=(),
    )

    lines = METRICS.stock_lines(inputs, tmp_path, METRICS.Window(0.0, None, explicit=True))
    joined = "\n".join(lines)

    assert "stock ready_work level=2 setpoint=>=3 status=below_alarm" in joined
    assert (
        "stock blocked_work level=4 setpoint=unruled status=unruled source=dispatch_slot" in joined
    )
    assert (
        "stock worktrees_owing_done level=unrecorded setpoint=at_most_0 status=unrecorded" in joined
    )
    assert "reason=worktree_registrations_unreadable" in next(
        line for line in lines if "worktrees_owing_done" in line
    )
    assert "stock dispatches_without_ledger level=0" in joined
    assert "status=at_setpoint" in next(
        line for line in lines if "dispatches_without_ledger" in line
    )
    assert "status=at_setpoint" in next(
        line for line in lines if "unratified_provisional_terms" in line
    )
    assert "reason=basis=" not in joined


def test_stock_status_uses_setpoint_and_retains_alarm(tmp_path: Path) -> None:
    """An above-setpoint stock names the setpoint status despite a higher alarm."""
    inputs = METRICS.Inputs(
        dispatches=(
            METRICS.DispatchRecord(
                dispatch_id="without-ledger",
                issue=50,
                seat="implementer",
                planned_at=1.0,
                result_state="readable",
                result_started_at=None,
                result_ended_at=2.0,
                ledger_row=False,
                ledger_materialised_at=None,
                landed_sha=None,
                landed_at=None,
                path=Path(),
            ),
        ),
        loops=(),
        queue_rows=(),
        diagnostics=(),
    )

    line = next(
        line
        for line in METRICS.stock_lines(inputs, tmp_path, METRICS.Window(0.0, 2.0, explicit=True))
        if line.startswith("stock dispatches_without_ledger")
    )

    assert "level=1" in line
    assert "status=above_setpoint" in line
    assert "setpoint=at_most_0 alarm=20" in line


def test_open_findings_stock_reports_maximum_against_its_setpoint(tmp_path: Path) -> None:
    """The open-finding stock uses the highest readable Work Item level."""
    loops = (
        METRICS.LoopRecord(
            1,
            0,
            (
                METRICS.IndependentFinding("open-1", "low", 0),
                METRICS.IndependentFinding("open-2", "low", 0),
                METRICS.IndependentFinding("open-3", "low", 0),
            ),
            (),
            self_review_present=False,
        ),
        METRICS.LoopRecord(
            2,
            0,
            (
                METRICS.IndependentFinding("open-4", "low", 0),
                METRICS.IndependentFinding("closed", "low", 0, is_open=False),
            ),
            (),
            self_review_present=False,
        ),
    )
    inputs = METRICS.Inputs(dispatches=(), loops=loops, queue_rows=(), diagnostics=())

    line = next(
        line
        for line in METRICS.stock_lines(
            inputs, tmp_path, METRICS.Window(None, None, explicit=False)
        )
        if line.startswith("stock open_findings_per_work_item")
    )

    assert "level=3" in line
    assert "setpoint=at_most_2 status=above_setpoint" in line
    assert "aggregation=max_per_work_item work_items=2" in line


def test_dismissal_matching_leaves_different_ids_unmatched() -> None:
    """A plausible reason cannot substitute for an identity the records do not carry."""
    record = METRICS.LoopRecord(
        7,
        0,
        (METRICS.IndependentFinding("review-id", "low", 0),),
        (
            METRICS.SelfRound(
                1,
                (
                    METRICS.SelfFinding(
                        "self-id", METRICS.NOT_WORTH_ADDRESSING, METRICS.PRE_EXISTING, 1
                    ),
                ),
            ),
        ),
        self_review_present=True,
    )

    assert METRICS.dismissal_match_counts((record,)) == (0, 1, 1, 0, ("7:self-id",))
    output = "\n".join(METRICS.dismissal_lines((record,)))
    assert "possible_range=[0.000000,1.000000]" in output
    assert "semantic_or_line_inference=not_available" in output


def test_wilson_interval_is_bounded_and_reports_no_zero_sample() -> None:
    """Ratios carry a bounded interval and no observations remain explicitly absent."""
    interval = METRICS.wilson_interval(1, 2)

    assert interval is not None
    assert 0.0 <= interval.lower <= interval.value <= interval.upper <= 1.0
    assert METRICS.wilson_interval(0, 0) is None


def test_return_model_counts_transitions_and_geometric_residual() -> None:
    """The return model uses collapsed seat transitions, not raw adjacent duplicates."""
    dispatches = (
        METRICS.DispatchRecord(
            dispatch_id="i",
            issue=1,
            seat="implementer",
            planned_at=1.0,
            result_state="readable",
            result_started_at=None,
            result_ended_at=2.0,
            ledger_row=True,
            ledger_materialised_at=None,
            landed_sha=None,
            landed_at=None,
            path=Path(),
        ),
        METRICS.DispatchRecord(
            dispatch_id="r",
            issue=1,
            seat="review",
            planned_at=3.0,
            result_state="readable",
            result_started_at=None,
            result_ended_at=4.0,
            ledger_row=True,
            ledger_materialised_at=None,
            landed_sha=None,
            landed_at=None,
            path=Path(),
        ),
        METRICS.DispatchRecord(
            dispatch_id="i2",
            issue=1,
            seat="implementer",
            planned_at=5.0,
            result_state="readable",
            result_started_at=None,
            result_ended_at=6.0,
            ledger_row=True,
            ledger_materialised_at=None,
            landed_sha=None,
            landed_at=None,
            path=Path(),
        ),
        METRICS.DispatchRecord(
            dispatch_id="r2",
            issue=1,
            seat="review",
            planned_at=7.0,
            result_state="readable",
            result_started_at=None,
            result_ended_at=8.0,
            ledger_row=True,
            ledger_materialised_at=None,
            landed_sha=None,
            landed_at=None,
            path=Path(),
        ),
        METRICS.DispatchRecord(
            dispatch_id="r3",
            issue=1,
            seat="review",
            planned_at=9.0,
            result_state="readable",
            result_started_at=None,
            result_ended_at=10.0,
            ledger_row=True,
            ledger_materialised_at=None,
            landed_sha=None,
            landed_at=None,
            path=Path(),
        ),
    )

    lines = METRICS.return_lines(dispatches, METRICS.Window(0.0, 20.0, explicit=True))

    assert "return_rate numerator=1 denominator=2" in lines[0]
    assert "expected_reviews_geometric=2.000000" in lines[1]
    assert "observed_reviews_mean=2.000000" in lines[1]
    assert "residual=0.000000" in lines[1]


def test_return_rate_names_inconsistent_window_counts() -> None:
    """A window-truncated loop is inconsistent, not a too-few observation."""
    dispatch_root = Path("dispatches")
    records = (
        ("i1", "implementer", 10),
        ("r1", "review", 20),
        ("i2", "implementer", 30),
        ("r2", "review", 40),
        ("i3", "implementer", 50),
    )
    dispatches = tuple(
        METRICS.DispatchRecord(
            dispatch_id=identifier,
            issue=1,
            seat=seat,
            planned_at=float(minute),
            result_state="readable",
            result_started_at=None,
            result_ended_at=None,
            ledger_row=True,
            ledger_materialised_at=None,
            landed_sha=None,
            landed_at=None,
            path=dispatch_root / identifier,
        )
        for identifier, seat, minute in records
    )

    lines = METRICS.return_lines(dispatches, METRICS.Window(15.0, 60.0, explicit=True))

    assert lines[0] == (
        "return_rate status=inconsistent reason=returns_exceed_handovers returns=2 handovers=1"
    )
    assert "status=too_few" not in lines[0]
    assert "return_model observations=1 mean=2.000000" in lines[1]
    assert "lambda=unrecorded residual=unrecorded" in lines[1]


def test_cli_is_read_only_and_exits_zero_for_empty_sources(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A report with no evidence still prints every family and writes no state."""
    dispatch_root = tmp_path / "dispatches"
    review_root = tmp_path / "review"
    queue_root = tmp_path / "queue"
    for root in (dispatch_root, review_root, queue_root):
        root.mkdir()
    before = tuple(sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*")))

    result = METRICS.main(
        [
            "--dispatch-root",
            str(dispatch_root),
            "--review-root",
            str(review_root),
            "--queue-root",
            str(queue_root),
            "--repo",
            str(tmp_path),
        ]
    )
    captured = capsys.readouterr()
    after = tuple(sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*")))

    assert result == 0
    assert "injection_rate status=too_few" in captured.out
    assert "delivery_gap_quality scope=audit" in captured.out
    assert "stock ready_work" in captured.out
    assert (
        "cycle_time_per_work_item status=too_few observed=0 needed=1 unit=seconds" in captured.out
    )
    assert (
        "return_model status=too_few observed=0 needed=1 lambda=unrecorded residual=unrecorded"
    ) in captured.out
    assert before == after
