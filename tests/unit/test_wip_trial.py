"""Prospective WIP-trial bar, immutable evidence, and decision table (#284)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from conftest import load_tool

if TYPE_CHECKING:
    from pathlib import Path
    from types import ModuleType

wip_trial: ModuleType = load_tool("wip_trial")

CREATED = 1_800_000_000.0
DAY = 24 * 60 * 60


def policy(limit: int = 3) -> dict[str, object]:
    """Build the queue-policy snapshot the stage cross-checks."""
    return {
        "version": 1,
        "freeze": {"state": "open", "since": "2026-08-08", "ruling": "human"},
        "wip_limit": {"value": limit, "since": "2026-08-08", "ruling": "human"},
        "packages": [],
    }


def routes(count: int = 2) -> list[dict[str, object]]:
    """Build independently named dispatchable lane/seat snapshots."""
    found: list[dict[str, object]] = [
        {
            "lane": "claude-native",
            "profile": "opus-high",
            "seat": "implementer",
            "dispatchable": True,
        },
        {"lane": "codex", "profile": "codex-sol-high", "seat": "implementer", "dispatchable": True},
    ]
    return found[:count]


def manifest(stage: int = 1) -> dict[str, Any]:
    """Create one valid pre-registration without touching the live store."""
    previous = None
    if stage > 1:
        previous = {"verdict": "pass", "candidate_limit": wip_trial.STAGES[stage][0]}
    found, refusal = wip_trial.make_manifest(
        stage=stage,
        source_sha="a" * 40,
        eligible_issues=tuple(range(1, 50)),
        policy=policy(wip_trial.STAGES[stage][0]),
        routes=routes(),
        created_at=CREATED,
        previous_result=previous,
    )
    assert refusal is None
    assert found is not None
    return found


def add(trial: dict[str, Any], rows: list[object], event: dict[str, object]) -> dict[str, Any]:
    """Append one event through the same validation and hash chain as the CLI."""
    row, refusal = wip_trial.append_event(trial, rows, event)
    assert refusal is None
    assert row is not None
    rows.append(row)
    return row


def drain(
    trial: dict[str, Any], rows: list[object], block: int, issues: list[int], at: float
) -> None:
    """Record the minimum complete occupancy series ending at zero."""
    for event_index, event_name in enumerate(("dispatch", "result", "close")):
        for issue_index, issue in enumerate(issues):
            add(
                trial,
                rows,
                {
                    "kind": "observation",
                    "at": at + event_index / 10 + issue_index / 1000,
                    "source": f"{event_name}-{issue}",
                    "block": block,
                    "issue": issue,
                    "event": event_name,
                    "occupancy": 0
                    if event_name == "close" and issue_index == len(issues) - 1
                    else int(trial["safe_limit"]),
                },
            )


def synthetic_stage(  # noqa: C901, PLR0913 -- fixture exposes each decision-table input
    *,
    candidate_occupancy: bool = True,
    candidate_hours: float = 15.0,
    safe_hours: float = 20.0,
    clean: bool = True,
    candidate_rework: int = 0,
    candidate_conflicts: int = 0,
    critical: str = "",
    concurrent_change: bool = False,
    non_result: bool = False,
) -> tuple[dict[str, Any], tuple[dict[str, object], ...], float]:
    """Generate four matured blocks with controllable treatment outcomes."""
    trial = manifest()
    rows: list[object] = []
    at = CREATED + 10
    order = trial["block_order"]
    assert isinstance(order, list)
    for number, arm in enumerate(order, start=1):
        limit = int(trial["safe_limit"] if arm == "safe" else trial["candidate_limit"])
        issues = list(range(number * 100, number * 100 + 10))
        add(
            trial,
            rows,
            {
                "kind": "block_start",
                "at": at,
                "source": f"queue-{number}",
                "block": number,
                "arm": arm,
                "limit": limit,
                "issues": issues,
                "eligible": [*issues, number * 100 + 10],
                "orchestration_trial": "cleared" if arm == "candidate" else "running",
            },
        )
        duration = candidate_hours if arm == "candidate" else safe_hours
        occupancy = limit
        if arm == "candidate" and not candidate_occupancy:
            occupancy = int(trial["safe_limit"])
        closes: dict[int, float] = {}
        for index, issue in enumerate(issues):
            add(
                trial,
                rows,
                {
                    "kind": "observation",
                    "at": at + index / 100,
                    "source": f"dispatch-{issue}",
                    "block": number,
                    "issue": issue,
                    "event": "dispatch",
                    "occupancy": occupancy,
                },
            )
            add(
                trial,
                rows,
                {
                    "kind": "ready",
                    "at": at + 1 + index / 100,
                    "source": f"ready-{issue}",
                    "block": number,
                    "issue": issue,
                    "corrective": False,
                },
            )
        if arm == "candidate":
            for issue in issues[:candidate_rework]:
                add(
                    trial,
                    rows,
                    {
                        "kind": "rework",
                        "at": at + 2,
                        "source": f"rework-{issue}",
                        "block": number,
                        "issue": issue,
                        "corrective": True,
                    },
                )
            for issue in issues[:candidate_conflicts]:
                add(
                    trial,
                    rows,
                    {
                        "kind": "conflict",
                        "at": at + 3,
                        "source": f"conflict-{issue}",
                        "block": number,
                        "issue": issue,
                        "conflict": "rebase_conflict",
                    },
                )
        if non_result:
            add(
                trial,
                rows,
                {
                    "kind": "non_result",
                    "at": at + 4,
                    "source": f"retry-{issues[0]}",
                    "block": number,
                    "issue": issues[0],
                    "failure_class": "quota_exhausted",
                },
            )
        for index, issue in enumerate(issues):
            add(
                trial,
                rows,
                {
                    "kind": "observation",
                    "at": at + duration / 2 + index / 100,
                    "source": f"result-{issue}",
                    "block": number,
                    "issue": issue,
                    "event": "result",
                    "occupancy": occupancy,
                },
            )
            closed = at + duration - 0.09 + index / 100
            closes[issue] = closed
            add(
                trial,
                rows,
                {
                    "kind": "observation",
                    "at": closed,
                    "source": f"close-{issue}",
                    "block": number,
                    "issue": issue,
                    "event": "close",
                    "occupancy": 0 if index == len(issues) - 1 else occupancy,
                },
            )
        if critical and arm == "candidate":
            add(
                trial,
                rows,
                {
                    "kind": "critical",
                    "at": at + duration,
                    "source": "incident",
                    "block": number,
                    "issue": issues[0],
                    "failure": critical,
                },
            )
        if arm == "candidate":
            add(
                trial,
                rows,
                {
                    "kind": "restore",
                    "at": at + duration + 0.1,
                    "source": f"queue-restore-{number}",
                    "block": number,
                    "limit": trial["safe_limit"],
                },
            )
        maturity_at = max(closes.values()) + 7 * DAY + 1
        for index, issue in enumerate(issues):
            add(
                trial,
                rows,
                {
                    "kind": "maturity",
                    "at": maturity_at + index / 100,
                    "source": f"admission-audit-{issue}",
                    "block": number,
                    "issue": issue,
                    "clean_close": clean or index > 0 or arm == "safe",
                    "unclean": False,
                    "unclean_reasons": [],
                    "gate_reds": 0,
                    "flake_reruns": 0,
                },
            )
        at = maturity_at + 10
    if concurrent_change:
        add(
            trial,
            rows,
            {
                "kind": "change",
                "at": at,
                "source": "issue-999",
                "description": "routing changed during the stage",
            },
        )
    events, refusal = wip_trial.validate_events(trial, rows)
    assert refusal is None
    return trial, events, at


def test_the_bar_is_fixed_before_any_observation() -> None:
    """Hold every human-chosen threshold and the never-above-ten bound still."""
    assert wip_trial.BAR_ID == "cti.wip-trial/284/v1"
    assert wip_trial.STAGES == {1: (3, 5), 2: (5, 7), 3: (7, 10)}
    assert wip_trial.ISSUES_PER_BLOCK == 10
    assert wip_trial.BLOCKS_PER_STAGE == 4
    assert wip_trial.MATERIAL_RATE_RATIO == 1.15
    assert wip_trial.MIN_HIGH_EXPOSURE == 0.50
    assert wip_trial.MAX_P90_RATIO == 1.25
    assert wip_trial.MATURITY_SECONDS == 7 * DAY
    assert max(candidate for _, candidate in wip_trial.STAGES.values()) == 10


def test_allocation_is_deterministic_and_balanced() -> None:
    first = manifest()
    second = manifest()
    assert first["block_order"] == second["block_order"]
    assert tuple(first["block_order"]) in wip_trial.ORDERS
    assert first["block_order"].count("safe") == 2
    assert first["block_order"].count("candidate") == 2


@pytest.mark.parametrize(
    ("overrides", "kind"),
    [
        ({"stage": 4}, "stage_invalid"),
        ({"eligible_issues": tuple(range(1, 10))}, "eligible_underfilled"),
        ({"routes": routes(1)}, "routes_underfilled"),
        ({"policy": policy(5)}, "safe_limit_mismatch"),
    ],
)
def test_start_refuses_an_uninterpretable_stage(overrides: dict[str, Any], kind: str) -> None:
    arguments: dict[str, Any] = {
        "stage": 1,
        "source_sha": "b" * 40,
        "eligible_issues": tuple(range(1, 30)),
        "policy": policy(),
        "routes": routes(),
        "created_at": CREATED,
    }
    arguments.update(overrides)
    found, refusal = wip_trial.make_manifest(**arguments)
    assert found is None
    assert refusal is not None
    assert refusal.kind == kind


def test_a_higher_stage_requires_the_adjacent_matured_pass() -> None:
    found, refusal = wip_trial.make_manifest(
        stage=2,
        source_sha="b" * 40,
        eligible_issues=tuple(range(1, 30)),
        policy=policy(5),
        routes=routes(),
        created_at=CREATED,
    )
    assert found is None
    assert refusal is not None
    assert refusal.kind == "previous_stage_not_cleared"


def test_a_started_manifest_is_immutable() -> None:
    trial = manifest()
    trial["thresholds"]["material_rate_ratio"] = 1.01
    found, refusal = wip_trial.validate_manifest(trial)
    assert found is None
    assert refusal is not None
    assert refusal.kind == "manifest_changed"


def test_an_absent_store_refuses_instead_of_becoming_an_empty_trial(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = wip_trial.main(["--trial-dir", str(tmp_path), "status"])
    assert code == 1
    assert "refusal=manifest_unreadable" in capsys.readouterr().err


def test_observation_before_the_bar_is_not_historical_control() -> None:
    trial = manifest()
    row, refusal = wip_trial.append_event(
        trial,
        [],
        {
            "kind": "change",
            "at": CREATED - 1,
            "source": "history",
            "description": "old close",
        },
    )
    assert row is None
    assert refusal is not None
    assert refusal.kind == "event_before_bar"


def test_candidate_block_waits_for_the_orchestration_trial() -> None:
    trial = manifest()
    order = trial["block_order"]
    assert isinstance(order, list)
    candidate_number = order.index("candidate") + 1
    rows: list[object] = []
    for number in range(1, candidate_number):
        arm = order[number - 1]
        issues = list(range(number * 100, number * 100 + 10))
        add(
            trial,
            rows,
            {
                "kind": "block_start",
                "at": CREATED + number,
                "source": "queue",
                "block": number,
                "arm": arm,
                "limit": trial["safe_limit"],
                "issues": issues,
                "eligible": issues,
                "orchestration_trial": "running",
            },
        )
        drain(trial, rows, number, issues, CREATED + number + 0.1)
    issues = list(range(candidate_number * 100, candidate_number * 100 + 10))
    row, refusal = wip_trial.append_event(
        trial,
        rows,
        {
            "kind": "block_start",
            "at": CREATED + candidate_number,
            "source": "queue",
            "block": candidate_number,
            "arm": "candidate",
            "limit": trial["candidate_limit"],
            "issues": issues,
            "eligible": issues,
            "orchestration_trial": "running",
        },
    )
    assert row is None
    assert refusal is not None
    assert refusal.kind == "orchestration_trial_running"


def test_an_issue_cannot_straddle_immutable_blocks() -> None:
    trial = manifest()
    order = trial["block_order"]
    assert isinstance(order, list)
    rows: list[object] = []
    first = list(range(100, 110))
    add(
        trial,
        rows,
        {
            "kind": "block_start",
            "at": CREATED + 1,
            "source": "queue-1",
            "block": 1,
            "arm": order[0],
            "limit": trial[f"{order[0]}_limit"],
            "issues": first,
            "eligible": first,
            "orchestration_trial": "cleared",
        },
    )
    drain(trial, rows, 1, first, CREATED + 1.1)
    second = [first[0], *range(201, 210)]
    row, refusal = wip_trial.append_event(
        trial,
        rows,
        {
            "kind": "block_start",
            "at": CREATED + 2,
            "source": "queue-2",
            "block": 2,
            "arm": order[1],
            "limit": trial[f"{order[1]}_limit"],
            "issues": second,
            "eligible": second,
            "orchestration_trial": "cleared",
        },
    )
    assert row is None
    assert refusal is not None
    assert refusal.kind == "issue_straddles_blocks"


def test_a_cohort_must_be_the_first_ten_queue_issues() -> None:
    trial = manifest()
    order = trial["block_order"]
    assert isinstance(order, list)
    eligible = list(range(100, 111))
    row, refusal = wip_trial.append_event(
        trial,
        [],
        {
            "kind": "block_start",
            "at": CREATED + 1,
            "source": "queue",
            "block": 1,
            "arm": order[0],
            "limit": trial[f"{order[0]}_limit"],
            "issues": eligible[1:],
            "eligible": eligible,
            "orchestration_trial": "cleared",
        },
    )
    assert row is None
    assert refusal is not None
    assert refusal.kind == "cohort_hand_picked"


def test_a_candidate_block_must_restore_safe_policy_before_the_next_block() -> None:
    trial = manifest()
    order = trial["block_order"]
    assert order == ["safe", "candidate", "candidate", "safe"]
    rows: list[object] = []
    for number in (1, 2):
        issues = list(range(number * 100, number * 100 + 10))
        add(
            trial,
            rows,
            {
                "kind": "block_start",
                "at": CREATED + number,
                "source": f"queue-{number}",
                "block": number,
                "arm": order[number - 1],
                "limit": trial[f"{order[number - 1]}_limit"],
                "issues": issues,
                "eligible": issues,
                "orchestration_trial": "cleared",
            },
        )
        drain(trial, rows, number, issues, CREATED + number + 0.1)
    issues = list(range(300, 310))
    row, refusal = wip_trial.append_event(
        trial,
        rows,
        {
            "kind": "block_start",
            "at": CREATED + 3,
            "source": "queue-3",
            "block": 3,
            "arm": order[2],
            "limit": trial["candidate_limit"],
            "issues": issues,
            "eligible": issues,
            "orchestration_trial": "cleared",
        },
    )
    assert row is None
    assert refusal is not None
    assert refusal.kind == "safe_limit_not_restored"


def test_the_event_chain_refuses_edits_and_reordering() -> None:
    trial = manifest()
    order = trial["block_order"]
    assert isinstance(order, list)
    issues = list(range(100, 110))
    rows: list[object] = []
    row = add(
        trial,
        rows,
        {
            "kind": "block_start",
            "at": CREATED + 1,
            "source": "queue",
            "block": 1,
            "arm": order[0],
            "limit": trial[f"{order[0]}_limit"],
            "issues": issues,
            "eligible": issues,
            "orchestration_trial": "cleared",
        },
    )
    row["source"] = "rewritten"
    events, refusal = wip_trial.validate_events(trial, rows)
    assert not events
    assert refusal is not None
    assert refusal.kind == "event_chain_broken"


def test_corrective_rework_requires_a_sourced_ready_point() -> None:
    trial = manifest()
    order = trial["block_order"]
    assert isinstance(order, list)
    issues = list(range(100, 110))
    rows: list[object] = []
    add(
        trial,
        rows,
        {
            "kind": "block_start",
            "at": CREATED + 1,
            "source": "queue",
            "block": 1,
            "arm": order[0],
            "limit": trial[f"{order[0]}_limit"],
            "issues": issues,
            "eligible": issues,
            "orchestration_trial": "cleared",
        },
    )
    row, refusal = wip_trial.append_event(
        trial,
        rows,
        {
            "kind": "rework",
            "at": CREATED + 2,
            "source": "correction",
            "block": 1,
            "issue": issues[0],
            "corrective": True,
        },
    )
    assert row is None
    assert refusal is not None
    assert refusal.kind == "rework_before_ready"


def test_unclean_reuses_admissions_vocabulary_without_a_default() -> None:
    trial = manifest()
    order = trial["block_order"]
    assert isinstance(order, list)
    issues = list(range(100, 110))
    rows: list[object] = []
    add(
        trial,
        rows,
        {
            "kind": "block_start",
            "at": CREATED + 1,
            "source": "queue",
            "block": 1,
            "arm": order[0],
            "limit": trial[f"{order[0]}_limit"],
            "issues": issues,
            "eligible": issues,
            "orchestration_trial": "cleared",
        },
    )
    row, refusal = wip_trial.append_event(
        trial,
        rows,
        {
            "kind": "maturity",
            "at": CREATED + 8 * DAY,
            "source": "audit",
            "block": 1,
            "issue": issues[0],
            "clean_close": True,
            "unclean": True,
            "unclean_reasons": ["invented"],
            "gate_reds": 0,
            "flake_reruns": 0,
        },
    )
    assert row is None
    assert refusal is not None
    assert refusal.kind == "unclean_reason_unknown"


def test_a_clean_matured_stage_passes_at_the_lowest_candidate() -> None:
    trial, events, now = synthetic_stage()
    result = wip_trial.analyse(trial, events, now)
    assert result.verdict == "pass"
    assert result.rate_ratio == pytest.approx(20 / 15)
    assert result.rate_ratio_interval is not None
    assert "candidate 5 clears" in result.recommendation
    assert "--limit 5" in result.recommendation


@pytest.mark.parametrize(
    ("arguments", "reason"),
    [
        ({"candidate_hours": 18.0}, "material_throughput_not_met"),
        ({"clean": False}, "clean_close_guardrail"),
        ({"candidate_rework": 1}, "candidate_rework_above_safe"),
        ({"candidate_conflicts": 1}, "candidate_conflicts_above_safe"),
        ({"critical": "red_landing"}, "critical_failure=red_landing"),
    ],
)
def test_each_failed_guardrail_retains_three(arguments: dict[str, Any], reason: str) -> None:
    trial, events, now = synthetic_stage(**arguments)
    result = wip_trial.analyse(trial, events, now)
    assert result.verdict == "fail"
    assert any(found.startswith(reason) for found in result.reasons)
    assert "retain 3" in result.recommendation
    assert "--limit 3" in result.recommendation


def test_under_exercised_candidate_is_inconclusive() -> None:
    trial, events, now = synthetic_stage(candidate_occupancy=False)
    result = wip_trial.analyse(trial, events, now)
    assert result.verdict == "inconclusive"
    assert any(reason.startswith("candidate_fidelity_failed=") for reason in result.reasons)
    assert "retain 3" in result.recommendation


def test_an_open_block_times_out_without_replacement_or_censoring() -> None:
    trial = manifest()
    order = trial["block_order"]
    assert isinstance(order, list)
    issues = list(range(100, 110))
    rows: list[object] = []
    add(
        trial,
        rows,
        {
            "kind": "block_start",
            "at": CREATED + 1,
            "source": "queue",
            "block": 1,
            "arm": order[0],
            "limit": trial[f"{order[0]}_limit"],
            "issues": issues,
            "eligible": issues,
            "orchestration_trial": "running",
        },
    )
    add(
        trial,
        rows,
        {
            "kind": "observation",
            "at": CREATED + 2,
            "source": "dispatch-100",
            "block": 1,
            "issue": issues[0],
            "event": "dispatch",
            "occupancy": 1,
        },
    )
    events, refusal = wip_trial.validate_events(trial, rows)
    assert refusal is None
    result = wip_trial.analyse(trial, events, CREATED + 2 + wip_trial.BLOCK_TIMEOUT_SECONDS + 1)
    assert result.verdict == "fail"
    assert "blocks_timed_out=1" in result.reasons


def test_a_concurrent_process_change_requires_a_new_bar() -> None:
    trial, events, now = synthetic_stage(concurrent_change=True)
    result = wip_trial.analyse(trial, events, now)
    assert result.verdict == "inconclusive"
    assert "concurrent_change_requires_new_bar" in result.reasons


def test_typed_non_results_remain_elapsed_but_are_not_rework() -> None:
    trial, events, now = synthetic_stage(non_result=True)
    result = wip_trial.analyse(trial, events, now)
    assert result.verdict == "pass"
    assert all(block.rework_issues == 0 for block in result.blocks)
    assert all(block.elapsed_hours is not None for block in result.blocks)
    assert all(block.non_results == ("quota_exhausted",) for block in result.blocks)


def test_poisson_interval_is_exactly_symmetric_for_equal_exposure() -> None:
    interval = wip_trial.poisson_rate_ratio_interval(20, 40.0, 20, 40.0)
    assert interval is not None
    assert interval[0] < 1 < interval[1]
    assert interval[0] == pytest.approx(1 / interval[1])


def test_report_contains_the_raw_cohorts_and_exact_verdict() -> None:
    trial, events, now = synthetic_stage()
    result = wip_trial.analyse(trial, events, now)
    report = wip_trial.markdown_report(trial, result)
    assert "**pass**" in report
    assert "exact conditional Poisson 90% interval" in report
    assert "100,101,102,103,104,105,106,107,108,109" in report
    assert "Codex" in report
