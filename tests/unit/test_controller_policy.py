"""Pure policy cases for the first System-of-Work Controller slice."""

from __future__ import annotations

import pytest
from conftest import load_tool

policy = load_tool("controller_policy")


def facts(
    *,
    curator: str | None = None,
    outcomes: tuple[object, ...] = (),
    initiatives: tuple[object, ...] = (),
) -> policy.ControlFacts:
    """Build a fact set while keeping the branch cases easy to read."""
    return policy.ControlFacts(
        configured_curator=curator,
        desired_outcomes=outcomes,
        initiatives=initiatives,
        work_items=(),
        work_runs=(),
    )


OUTCOME = policy.DesiredOutcomeFact("outcome-1", 1, "digest-1")
ACTIVE = policy.InitiativeFact("initiative-1", "active")


@pytest.mark.parametrize(
    ("arrangement", "expected_reason"),
    [
        (facts(), "no_product_curator_configured"),
        (facts(curator="curator-1"), "no_desired_outcome"),
        (
            facts(curator="curator-1", outcomes=(OUTCOME, OUTCOME)),
            "desired_outcome_cardinality_not_one",
        ),
        (
            facts(curator="curator-1", outcomes=(OUTCOME,), initiatives=(ACTIVE,)),
            "active_initiative_present",
        ),
        (facts(curator="curator-1", outcomes=(OUTCOME,)), "initiative_admission_not_implemented"),
    ],
)
def test_first_slice_always_explains_why_no_initiative_is_admissible(
    arrangement: object, expected_reason: str
) -> None:
    """Every conservative no-admission branch is explicit and action-free."""
    result = policy.derive(arrangement)

    assert result.lifecycle == policy.LifecycleState(
        policy.NO_ADMISSIBLE_INITIATIVE, None, expected_reason
    )
    assert result.actions == ()


def test_previous_confirmed_state_is_not_an_authority_for_replay() -> None:
    """The same current facts derive the same result regardless of prior state."""
    current = facts(curator="curator-1", outcomes=(OUTCOME,))
    previous = policy.LifecycleState("unexpected", "initiative-9", "old")

    assert policy.derive(current) == policy.derive(current, previous)


def test_renderers_preserve_normalized_facts_and_action_order() -> None:
    """Stable documents expose all fields, including an ordered action payload."""
    current = facts(curator="curator-1", outcomes=(OUTCOME,))
    actions = (
        policy.ControlAction("tracker.record", "outcome-1", (("revision", 1),)),
        policy.ControlAction("evidence.write", "cycle-1"),
    )

    assert policy.facts_document(current) == {
        "configured_curator": "curator-1",
        "desired_outcomes": [{"key": "outcome-1", "revision": 1, "content_digest": "digest-1"}],
        "initiatives": [],
        "work_items": [],
        "work_runs": [],
    }
    lifecycle = policy.LifecycleState(policy.NO_ADMISSIBLE_INITIATIVE, None, "reason")
    assert policy.lifecycle_document(lifecycle) == {
        "state": policy.NO_ADMISSIBLE_INITIATIVE,
        "admitted_initiative": None,
        "reason": "reason",
    }
    assert policy.actions_document(actions) == [
        {
            "order": 1,
            "kind": "tracker.record",
            "logical_key": "outcome-1",
            "payload": {"revision": 1},
        },
        {"order": 2, "kind": "evidence.write", "logical_key": "cycle-1", "payload": {}},
    ]


def test_fact_renderer_returns_a_new_document() -> None:
    """Rendering cannot mutate the immutable fact input through its result."""
    current = facts(curator="curator-1", outcomes=(OUTCOME,))

    rendered = policy.facts_document(current)
    rendered["desired_outcomes"].clear()  # type: ignore[union-attr]

    assert current.desired_outcomes == (OUTCOME,)


def coordination_facts(  # noqa: PLR0913 — each fact collection is an independent test seam
    items: tuple[object, ...],
    *,
    runs: tuple[object, ...] = (),
    debt: tuple[object, ...] = (),
    limit: int | None = 3,
    bars: tuple[object, ...] = (),
    priority_order: tuple[str, ...] = (),
) -> policy.ControlFacts:
    """Build one published graph with its scheduling facts."""
    return policy.ControlFacts(
        configured_curator="curator-1",
        desired_outcomes=(OUTCOME,),
        initiatives=(ACTIVE,),
        work_items=items,
        work_runs=runs,
        worktree_debt=debt,
        wip_limit=limit,
        external_bars=bars,
        priority_order=priority_order,
    )


def test_coordination_selects_one_ready_item_by_configured_priority() -> None:
    blocked = policy.WorkItemFact("blocked", "blocked", issue=1)
    lower = policy.WorkItemFact("lower", "open", issue=3)
    higher = policy.WorkItemFact("higher", "open", issue=4)
    current = coordination_facts(
        (lower, blocked, higher),
        priority_order=("higher", "lower"),
    )

    assert policy.eligible_work_items(current) == (higher, lower)
    result = policy.derive(current)

    assert result.selected_work_item == higher
    assert len(result.actions) == 1
    action = result.actions[0]
    assert action.kind == "dispatch.start_work_run"
    assert dict(action.payload)["priority_source"] == "configured_work_item_policy"
    assert dict(action.payload)["preconditions"] == policy.snapshot_document(
        policy.coordination_snapshot(current)
    )


def test_worktree_debt_is_first_class_wip_capacity() -> None:
    item = policy.WorkItemFact("item-1", "open", issue=1)
    debt = policy.WorktreeDebtFact(99, "/trees/issue-99")
    current = coordination_facts((item,), debt=(debt,), limit=1)

    assert policy.occupied_capacity(current) == 1
    assert policy.eligible_work_items(current) == ()
    result = policy.derive(current)
    assert result.actions == ()
    assert result.lifecycle.reason == "wip_reached_by_live_runs_or_worktree_debt"
    assert policy.facts_document(current)["worktree_debt"] == [
        {"issue": 99, "path": "/trees/issue-99"}
    ]


def test_live_run_claims_its_work_item_resources() -> None:
    holder = policy.WorkItemFact("holder", "open", issue=1, exclusive_resources=("shared-slot",))
    conflict = policy.WorkItemFact(
        "conflict", "open", issue=2, exclusive_resources=("shared-slot",)
    )
    independent = policy.WorkItemFact("independent", "open", issue=3)
    run = policy.WorkRunFact("run-1", "running", work_item_key="legacy-key", issue=1)
    current = coordination_facts((holder, conflict, independent), runs=(run,), limit=3)

    assert policy.eligible_work_items(current) == (independent,)


def test_worktree_debt_keeps_its_exclusive_resources_held() -> None:
    holder = policy.WorkItemFact("holder", "complete", issue=1, exclusive_resources=("shared",))
    conflict = policy.WorkItemFact("conflict", "open", issue=2, exclusive_resources=("shared",))
    debt = policy.WorktreeDebtFact(1, "/trees/issue-1", work_item_key="holder")
    current = coordination_facts((holder, conflict), debt=(debt,), limit=2)

    assert policy.eligible_work_items(current) == ()


def test_new_work_run_keeps_terminal_history_but_replaces_a_live_duplicate() -> None:
    item = policy.WorkItemFact("item", "open", issue=1)
    old_terminal = policy.WorkRunFact("old-terminal", "landed", work_item_key="item", issue=1)
    old_live = policy.WorkRunFact("old-live", "running", work_item_key="item", issue=1)
    current = coordination_facts((item,), runs=(old_terminal, old_live), limit=3)
    action = policy.launch_action(current, item)

    updated = policy.with_work_run(
        current,
        action,
        run_key="new-run",
        dispatch_id="dispatch-1",
    )

    assert updated.work_runs == (
        old_terminal,
        policy.WorkRunFact(
            "new-run",
            "launching",
            work_item_key="item",
            dispatch_id="dispatch-1",
            worktree="issue-1",
            issue=1,
        ),
    )


@pytest.mark.parametrize(
    "failure_class",
    ["infra_unavailable", "quota_exhausted", "provider_refused", "interrupted"],
)
def test_external_bars_and_non_results_leave_work_item_open(
    failure_class: str,
) -> None:
    item = policy.WorkItemFact("item-1", "open", issue=1)
    bar = policy.ExternalBarFact("item-1", failure_class, "provider said no")
    current = coordination_facts((item,), bars=(bar,), limit=3)
    current = policy.ControlFacts(
        current.configured_curator,
        current.desired_outcomes,
        current.initiatives,
        current.work_items,
        (policy.WorkRunFact("run-1", "failed", failure_class=failure_class),),
        current.worktree_debt,
        current.wip_limit,
        current.external_bars,
        current.priority_order,
        current.ready_transitions,
    )

    result = policy.derive(current)

    assert result.actions == ()
    assert result.lifecycle.state == policy.BLOCKED_EXTERNAL
    assert result.lifecycle.reason == f"external_bar:{failure_class}"
    assert item.state == "open"
    assert policy.live_work_runs(current)[0].failure_class == failure_class


def test_ready_transition_records_when_the_last_blocker_completes() -> None:
    previous = coordination_facts(
        (
            policy.WorkItemFact("blocker", "open", issue=1),
            policy.WorkItemFact("item", "open", issue=2, blocked_by=("blocker",)),
        )
    )
    current = coordination_facts(
        (
            policy.WorkItemFact("blocker", "complete", issue=1),
            policy.WorkItemFact("item", "open", issue=2, blocked_by=("blocker",)),
        )
    )

    keys = policy.newly_ready_keys(previous, current)
    with_transition = policy.with_ready_transitions(current, keys, "2026-08-27T12:00:00+00:00")

    assert keys == ("item",)
    assert with_transition.ready_transitions == (
        policy.ReadyTransitionFact("item", "2026-08-27T12:00:00+00:00"),
    )
