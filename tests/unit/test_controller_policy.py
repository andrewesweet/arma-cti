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


def test_work_item_renderer_preserves_non_default_optional_fields() -> None:
    """Render non-default seat and recorded readiness without inventing defaults."""
    item = policy.WorkItemFact(
        "review-item",
        "open",
        issue=380,
        seat="review",
        ready_at="2026-08-27T12:00:00+00:00",
    )
    default_item = policy.WorkItemFact("default-item", "open")

    rendered = policy.facts_document(coordination_facts((item, default_item)))["work_items"]

    assert rendered == [
        {
            "key": "review-item",
            "state": "open",
            "issue": 380,
            "seat": "review",
            "ready_at": "2026-08-27T12:00:00+00:00",
        },
        {"key": "default-item", "state": "open"},
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


def test_worktree_debt_matches_resource_holder_by_issue_without_a_graph_key() -> None:
    """Debt without a Work Item key still holds its issue's exclusive resources."""
    holder = policy.WorkItemFact("holder", "complete", issue=1, exclusive_resources=("shared",))
    conflict = policy.WorkItemFact("conflict", "open", issue=2, exclusive_resources=("shared",))
    debt = policy.WorktreeDebtFact(1, "/trees/issue-1")
    current = coordination_facts((holder, conflict), debt=(debt,), limit=2)

    assert policy.eligible_work_items(current) == ()


def test_unlisted_work_items_use_explicit_nonnegative_priority() -> None:
    """An explicit priority orders items that configured priority leaves unlisted."""
    prioritized = policy.WorkItemFact("prioritized", "open", issue=1, priority=1)
    unprioritized = policy.WorkItemFact("unprioritized", "open", issue=2)
    current = coordination_facts((unprioritized, prioritized))

    assert policy.eligible_work_items(current) == (prioritized, unprioritized)


def test_unlisted_item_without_priority_stays_before_an_extremely_large_rank() -> None:
    """Missing priority remains below every accepted explicit nonnegative priority."""
    unprioritized = policy.WorkItemFact("unprioritized", "open", issue=1)
    large_rank = policy.WorkItemFact("large-rank", "open", issue=2, priority=2**31)
    current = coordination_facts((large_rank, unprioritized))

    assert policy.eligible_work_items(current) == (unprioritized, large_rank)


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


def test_new_work_run_replaces_a_live_issue_keyed_duplicate() -> None:
    item = policy.WorkItemFact("new-item", "open", issue=7)
    old_live = policy.WorkRunFact("old-live", "running", work_item_key="legacy-item", issue=7)
    current = coordination_facts((item,), runs=(old_live,), limit=3)

    updated = policy.with_work_run(
        current,
        policy.launch_action(current, item),
        run_key="new-run",
        dispatch_id="dispatch-1",
    )

    assert updated.work_runs == (
        policy.WorkRunFact(
            "new-run",
            "launching",
            work_item_key="new-item",
            dispatch_id="dispatch-1",
            worktree="issue-7",
            issue=7,
        ),
    )


@pytest.mark.parametrize(
    "failure_class",
    [
        "infra_unavailable",
        "quota_exhausted",
        "provider_refused",
        "untyped_harness_failure",
        "interrupted",
    ],
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


def _delivery_run(**overrides: object) -> object:
    """Build one fully evidenced candidate-bound Work Run for delivery cases."""
    values = {
        "key": "run-1",
        "state": "landed",
        "work_item_key": "item",
        "dispatch_id": "dispatch-1",
        "issue": 1,
        "candidate_sha": "a" * 40,
        "reviewed_sha": "a" * 40,
        "review_status": "cleared",
        "review_dispatch_id": "review-dispatch-1",
        "adjudication_sha": "a" * 40,
        "adjudication_status": "cleared",
        "gate_sha": "a" * 40,
        "gate_status": "passed",
        "landed_sha": "a" * 40,
        "close_evidence_sha": "a" * 40,
    }
    values.update(overrides)
    return policy.WorkRunFact(**values)


def test_exact_delivery_advances_one_item_and_frees_wip_for_the_next() -> None:
    completed = policy.WorkItemFact("item", "open", issue=1)
    next_item = policy.WorkItemFact("next", "open", issue=2, blocked_by=("item",))
    current = coordination_facts((completed, next_item), runs=(_delivery_run(),), limit=1)

    advanced = policy.advance_completed_work_items(current)

    assert advanced.work_items[0].state == "complete"
    assert policy.live_work_runs(advanced) == ()
    assert policy.derive(advanced).selected_work_item == advanced.work_items[1]


def test_incomplete_landing_evidence_keeps_the_work_run_slot() -> None:
    item = policy.WorkItemFact("item", "open", issue=1)
    facts = coordination_facts((item,), runs=(_delivery_run(close_evidence_sha=None),), limit=1)

    advanced = policy.advance_completed_work_items(facts)

    assert advanced.work_items[0].state == "open"
    assert policy.live_work_runs(advanced) == (advanced.work_runs[0],)
    assert policy.derive(advanced).selected_work_item is None


def test_a_candidate_arriving_after_a_live_observation_is_not_a_conflict() -> None:
    live = policy.WorkRunFact(
        "run-1",
        "running",
        work_item_key="item",
        dispatch_id="dispatch-1",
        issue=1,
    )

    merged = policy.merge_work_run_observations((live,), (_delivery_run(),))

    assert merged[0].candidate_sha == "a" * 40
    assert merged[0].delivery_conflict is False
    assert policy.completion_ready(merged[0]) is True


def test_considered_reason_reports_wip_at_exact_capacity() -> None:
    item = policy.WorkItemFact("item", "open", issue=1)
    debt = policy.WorktreeDebtFact(99, "/trees/issue-99")

    result = policy.derive(coordination_facts((item,), debt=(debt,), limit=1))

    assert result.considered == (("item", "wip_reached_by_live_runs_or_worktree_debt"),)


def test_issue_keyed_bar_does_not_match_a_work_item_without_an_issue() -> None:
    item = policy.WorkItemFact("item", "open")
    bar = policy.ExternalBarFact("None", "quota_exhausted")

    assert policy.eligible_work_items(coordination_facts((item,), bars=(bar,))) == (item,)


def test_issue_keyed_bar_matches_a_work_item_with_that_issue() -> None:
    item = policy.WorkItemFact("item", "open", issue=1)
    bar = policy.ExternalBarFact("1", "quota_exhausted")

    assert policy.eligible_work_items(coordination_facts((item,), bars=(bar,))) == ()


@pytest.mark.parametrize("overrides", [{"review_dispatch_id": "dispatch-1"}, {"dispatch_id": None}])
def test_controller_clearance_requires_a_distinct_independent_review_dispatch(
    overrides: dict[str, object],
) -> None:
    run = _delivery_run(**overrides)

    assert policy.candidate_cleared(run) is False
    assert (
        policy.advance_completed_work_items(
            coordination_facts((policy.WorkItemFact("item", "open", issue=1),), runs=(run,))
        )
        .work_items[0]
        .state
        == "open"
    )


def test_work_run_matching_requires_both_observations_to_share_dispatch_identity() -> None:
    left = policy.WorkRunFact("run-1", "running", dispatch_id="dispatch-1")
    same = policy.WorkRunFact("different-key", "landed", dispatch_id="dispatch-1")
    missing = policy.WorkRunFact("run-1", "running")

    assert policy.same_work_run(left, same) is True
    assert policy.same_work_run(left, missing) is False
    assert policy.same_work_run(missing, left) is False


def test_completion_requires_the_work_item_identity_not_only_a_shared_issue() -> None:
    wrong_key = _delivery_run(work_item_key="other")
    wrong_key_facts = coordination_facts(
        (policy.WorkItemFact("item", "open", issue=1),), runs=(wrong_key,)
    )
    assert policy.advance_completed_work_items(wrong_key_facts).work_items[0].state == "open"

    no_identity = _delivery_run(key="other", work_item_key=None, issue=1)
    no_identity_facts = coordination_facts(
        (policy.WorkItemFact("item", "open"),), runs=(no_identity,)
    )
    assert policy.advance_completed_work_items(no_identity_facts).work_items[0].state == "open"

    no_identity_without_issue = _delivery_run(key="other", work_item_key=None, issue=None)
    no_identity_without_issue_facts = coordination_facts(
        (policy.WorkItemFact("item", "open"),), runs=(no_identity_without_issue,)
    )
    assert (
        policy.advance_completed_work_items(no_identity_without_issue_facts).work_items[0].state
        == "open"
    )

    keyless_same_issue = _delivery_run(key="other", work_item_key=None, issue=1)
    keyless_same_issue_facts = coordination_facts(
        (policy.WorkItemFact("item", "open", issue=1),), runs=(keyless_same_issue,)
    )
    assert (
        policy.advance_completed_work_items(keyless_same_issue_facts).work_items[0].state
        == "complete"
    )

    same_key_wrong_issue = _delivery_run(issue=2)
    same_key_wrong_issue_facts = coordination_facts(
        (policy.WorkItemFact("item", "open", issue=1),), runs=(same_key_wrong_issue,)
    )
    assert (
        policy.advance_completed_work_items(same_key_wrong_issue_facts).work_items[0].state
        == "open"
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("reviewed_sha", "b" * 40),
        ("adjudication_sha", None),
        ("adjudication_status", "pending"),
        ("gate_sha", "b" * 40),
        ("gate_status", "failed"),
        ("landed_sha", "b" * 40),
        ("close_evidence_sha", None),
    ],
)
def test_incomplete_or_mismatched_delivery_evidence_leaves_item_unresolved(
    field: str, value: object
) -> None:
    run = _delivery_run(**{field: value})
    facts = coordination_facts(
        (policy.WorkItemFact("item", "open", issue=1),), runs=(run,), limit=1
    )

    advanced = policy.advance_completed_work_items(facts)

    assert advanced.work_items[0].state == "open"


@pytest.mark.parametrize(
    "failure_class",
    [
        "infra_unavailable",
        "quota_exhausted",
        "provider_refused",
        "untyped_harness_failure",
        "interrupted",
    ],
)
def test_every_published_non_result_releases_its_slot_and_reopens_its_item(
    failure_class: str,
) -> None:
    """The shape `_read_result_non_result` produces: a bound run, its result published.

    A non-result is never a completion, so the item stays open — but its slot
    must be released and the item must be eligible again for the re-dispatch
    the failure-class table requires.
    """
    run = policy.WorkRunFact(
        "run-1",
        "non_result",
        work_item_key="item",
        dispatch_id="dispatch-1",
        issue=1,
        failure_class=failure_class,
        result_published=True,
    )
    item = policy.WorkItemFact("item", "open", issue=1)
    facts = coordination_facts((item,), runs=(run,), limit=1)

    advanced = policy.advance_completed_work_items(facts)

    assert advanced.work_items[0].state == "open"
    assert policy.live_work_runs(advanced) == ()
    assert policy.eligible_work_items(advanced) == (item,)


def test_an_unpublished_unclassified_non_result_still_holds_its_slot() -> None:
    """Without a published result or a terminal recovery verdict, nothing releases.

    Reachable through the typed delivery boundary, whose envelope carries
    `failure_class` and which nothing yet writes (#629), and through journals
    written before `result_published` existed whose result has since been
    pruned; the hold is what the release fact is measured against.
    """
    run = policy.WorkRunFact(
        "run-1",
        "non_result",
        work_item_key="item",
        dispatch_id="dispatch-1",
        issue=1,
        failure_class="quota_exhausted",
    )
    facts = coordination_facts(
        (policy.WorkItemFact("item", "open", issue=1),), runs=(run,), limit=1
    )

    assert policy.live_work_runs(facts) == (run,)
    assert policy.eligible_work_items(facts) == ()


def test_non_result_cannot_be_replaced_by_later_completion() -> None:
    non_result = _delivery_run(
        state="non_result",
        failure_class="quota_exhausted",
        candidate_sha=None,
        reviewed_sha=None,
        review_status=None,
        review_dispatch_id=None,
        adjudication_sha=None,
        adjudication_status=None,
        gate_sha=None,
        gate_status=None,
        landed_sha=None,
        close_evidence_sha=None,
    )
    merged = policy.merge_work_run_observations((non_result,), (_delivery_run(),))

    assert merged[0].failure_class == "quota_exhausted"
    assert merged[0].delivery_conflict
    assert not policy.completion_ready(merged[0])


def test_a_result_non_result_keeps_the_binding_of_the_run_it_observes() -> None:
    """A controller-recorded run merged with the dispatcher's stripped result stays bound.

    `_read_result_non_result` carries only the dispatch identity, so the merge
    direction that production produces — bound prior, stripped observation —
    must keep the prior's Work Item binding rather than orphaning the slot.
    """
    recorded = policy.WorkRunFact(
        "test-controller:test-controller-cycle-1:item-1",
        policy.RECORDED_LAUNCH_STATE,
        work_item_key="item-1",
        dispatch_id="test-controller:test-controller-cycle-1:item-1",
        worktree="issue-1",
        issue=1,
    )
    stripped = policy.WorkRunFact(
        "test-controller:test-controller-cycle-1:item-1",
        policy.NON_RESULT,
        dispatch_id="test-controller:test-controller-cycle-1:item-1",
        failure_class="quota_exhausted",
    )

    merged = policy.merge_work_run_observation(recorded, stripped)

    assert merged.state == policy.NON_RESULT
    assert merged.failure_class == "quota_exhausted"
    assert merged.work_item_key == "item-1"
    assert merged.issue == 1
    assert merged.worktree == "issue-1"
    item = policy.WorkItemFact("item-1", "open", issue=1)
    facts = coordination_facts((item,), runs=(merged,), limit=1)

    assert policy.eligible_work_items(facts) == ()


def test_failure_evidence_blocks_completion_even_with_landing_fields() -> None:
    assert not policy.completion_ready(_delivery_run(failure_class="provider_refused"))


@pytest.mark.parametrize(
    ("previous", "current"),
    [
        # The identity-conflict branch.
        (
            _delivery_run(delivery_conflict=True, result_published=False),
            _delivery_run(result_published=True),
        ),
        # The branch whose fresh observation is a stripped typed non-result.
        (
            _delivery_run(result_published=True, close_evidence_sha=None),
            policy.WorkRunFact("run-1", "non_result", dispatch_id="dispatch-1"),
        ),
        # The landed branch, whose prior observation is unstamped.
        (
            _delivery_run(result_published=False, landed_sha="a" * 40),
            _delivery_run(result_published=True),
        ),
    ],
    ids=["identity_conflict", "fresh_non_result", "landed_prior"],
)
def test_no_merge_branch_clears_a_recorded_publication(
    previous: policy.WorkRunFact, current: policy.WorkRunFact
) -> None:
    """Publication is stamped once after the identity ladder, never per branch.

    ``result_published`` records where an observation was read from, so the
    union is applied by the merge's single preserve point; these are the
    branch shapes whose base observation carried no stamp and which round two
    found dropping it.
    """
    merged = policy.merge_work_run_observation(previous, current)

    assert merged.result_published is True


def test_delayed_landing_without_a_repeated_candidate_still_conflicts() -> None:
    delayed = _delivery_run(
        candidate_sha=None,
        reviewed_sha=None,
        review_status=None,
        review_dispatch_id=None,
        adjudication_sha=None,
        adjudication_status=None,
        gate_sha=None,
        gate_status=None,
        landed_sha="b" * 40,
        close_evidence_sha="b" * 40,
    )

    merged = policy.merge_work_run_observations((_delivery_run(),), (delayed,))

    assert merged[0].landed_sha == "a" * 40
    assert merged[0].delivery_conflict
    assert not policy.completion_ready(merged[0])


def test_delayed_conflict_after_completion_does_not_reoccupy_wip() -> None:
    run = _delivery_run(delivery_conflict=True)
    facts = coordination_facts(
        (
            policy.WorkItemFact("item", "complete", issue=1),
            policy.WorkItemFact("next", "open", issue=2),
        ),
        runs=(run,),
        limit=1,
    )

    assert policy.live_work_runs(facts) == ()
    assert policy.derive(facts).selected_work_item == facts.work_items[1]


def test_delayed_different_landing_cannot_rebind_a_completed_work_run() -> None:
    first = _delivery_run()
    delayed = _delivery_run(landed_sha="b" * 40, close_evidence_sha="b" * 40)
    merged = policy.merge_work_run_observations((first,), (delayed,))

    assert len(merged) == 1
    assert merged[0].landed_sha == "a" * 40
    assert merged[0].delivery_conflict is True
    assert policy.completion_ready(merged[0]) is False

    already_complete = coordination_facts(
        (policy.WorkItemFact("item", "complete", issue=1),), runs=merged, limit=1
    )
    assert policy.advance_completed_work_items(already_complete).work_items[0].state == "complete"


def test_delayed_candidate_change_cannot_rebind_a_work_run() -> None:
    delayed = _delivery_run(
        candidate_sha="b" * 40,
        reviewed_sha="b" * 40,
        adjudication_sha="b" * 40,
        gate_sha="b" * 40,
        landed_sha="b" * 40,
        close_evidence_sha="b" * 40,
    )

    merged = policy.merge_work_run_observations((_delivery_run(),), (delayed,))

    assert merged[0].candidate_sha == "a" * 40
    assert merged[0].delivery_conflict is True
    assert policy.completion_ready(merged[0]) is False
