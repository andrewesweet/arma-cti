"""Tests for the read-only loop metrics reader (#602)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from conftest import load_tool

if TYPE_CHECKING:
    import pytest

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
) -> None:
    """Arrange a dispatch plan, a completed result and an optional ledger row."""
    directory = root / identifier
    _write(
        directory / "dispatch.json",
        {
            "dispatch_id": identifier,
            "issue": issue,
            "seat": seat,
            "planned_at": _at(minute),
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


def test_worktree_owing_done_joins_registrations_to_attested_landings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A registration counts only when its issue has a landing attested by the end."""
    dispatch_root = tmp_path / "dispatches"
    _dispatch(dispatch_root, "i50", 50, "implementer", 0, ledger=_landed_ledger(11))
    _dispatch(dispatch_root, "i51", 51, "implementer", 0)
    _dispatch(dispatch_root, "i53", 53, "implementer", 0, ledger=_landed_ledger(20))
    inputs = METRICS.read_inputs(dispatch_root, tmp_path / "review", tmp_path / "queue")
    porcelain = "\n".join(
        [
            "worktree /repo",
            f"HEAD {'0' * 40}",
            "branch refs/heads/main",
            "",
            "worktree /repo/.claude/worktrees/issue-50",
            f"HEAD {'1' * 40}",
            "detached",
            "",
            "worktree /repo/.claude/worktrees/review-50-r2",
            f"HEAD {'2' * 40}",
            "detached",
            "",
            "worktree /repo/.claude/worktrees/issue-51",
            f"HEAD {'3' * 40}",
            "detached",
            "",
            "worktree /repo/.claude/worktrees/issue-53",
            f"HEAD {'4' * 40}",
            "detached",
            "",
            "worktree /repo/.codex/9f2/arma-cti",
            f"HEAD {'5' * 40}",
            "detached",
        ]
    )
    monkeypatch.setattr(
        METRICS,
        "_issue_registrations",
        lambda _repo: METRICS._parse_issue_registrations(porcelain),
    )

    window = METRICS.Window(0.0, METRICS.parse_timestamp(_at(15)), explicit=True)
    line = next(
        line
        for line in METRICS.stock_lines(inputs, tmp_path, window)
        if line.startswith("stock worktrees_owing_done")
    )

    assert "level=2 " in line  # issue-50 and review-50-r2; 53 landed after the end
    assert "registrations=5 excluded_without_issue_name=1" in line
    assert "setpoint=at_most_0 status=above_setpoint alarm=3" in line
    assert "registration_basis=current_snapshot bias=under_counts" in line
    assert "tracker_closure_unseen" in line


def test_issue_registrations_skip_main_checkout_and_name_unjoinable() -> None:
    """The main checkout never owes done and unnamed registrations stay visible."""
    porcelain = "\n".join(
        [
            "worktree /repo",
            "branch refs/heads/main",
            "",
            "worktree /repo/.claude/worktrees/issue-672",
            "detached",
            "",
            "worktree /repo/.claude/worktrees/review-525-r2",
            "detached",
            "",
            "worktree /home/andre/.codex/9f2/arma-cti",
            "detached",
        ]
    )

    assert METRICS._parse_issue_registrations(porcelain) == (
        (Path("/repo/.claude/worktrees/issue-672"), 672),
        (Path("/repo/.claude/worktrees/review-525-r2"), 525),
        (Path("/home/andre/.codex/9f2/arma-cti"), None),
    )


def test_worktree_stock_names_unreadable_registrations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A sweep that cannot answer stays unrecorded and never becomes zero."""
    monkeypatch.setattr(METRICS, "_issue_registrations", lambda _repo: None)
    inputs = METRICS.Inputs(dispatches=(), loops=(), queue_rows=(), diagnostics=())

    line = next(
        line
        for line in METRICS.stock_lines(inputs, tmp_path, METRICS.Window(0.0, 2.0, explicit=True))
        if line.startswith("stock worktrees_owing_done")
    )

    assert "level=unrecorded setpoint=at_most_0 status=unrecorded" in line
    assert "reason=worktree_registrations_unreadable" in line
    assert "bias=under_counts" not in line


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

    lines = METRICS.stock_lines(inputs, tmp_path, METRICS.Window(0.0, 2.0, explicit=True))
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
