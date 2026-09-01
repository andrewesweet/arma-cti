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
    _write(
        directory / "result.json",
        {
            "started_at": _at(minute),
            "ended_at": _at(minute + 1),
            "outcome": "ok",
        },
    )
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
    assert "catch_fraction numerator=1 denominator=3" in joined
    assert "bound=upper_bound" in joined
    assert "dismissal_misses numerator=1 denominator=1" in joined
    assert "dismissal_matching=exact_nonempty_id_same_work_item_unique_independent_match" in joined
    assert "findings_per_independent_review reviews=2 findings=3" in joined
    assert "severity_mix severity=medium numerator=1 denominator=3" in joined
    assert "clean_round_distribution round=2 numerator=1 denominator=1" in joined
    assert "return_rate numerator=0 denominator=2" in joined
    assert "return_model lambda=0.000000" in joined
    assert "no_self_review_is_not_zero" in joined


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
    assert before == after
