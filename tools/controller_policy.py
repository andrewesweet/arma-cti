"""Pure System-of-Work reconciliation policy.

This module is deliberately a facts-to-actions kernel.  It owns no capability
that can observe or mutate the host; adapters and the command coordinator keep
those concerns outside the policy seam.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Final

NO_ADMISSIBLE_INITIATIVE: Final = "no_admissible_initiative"
DELIVERING: Final = "delivering"
BLOCKED_EXTERNAL: Final = "blocked_external"
NO_ELIGIBLE_WORK_ITEM: Final = "no_eligible_work_item"

# These vocabularies are intentionally local to the pure reducer.  The delivery
# protocol may add richer states later, but a state outside the live set is not
# silently treated as a live process by this scheduling slice.
OPEN_WORK_ITEM_STATES: Final = frozenset({"open", "ready"})
COMPLETE_WORK_ITEM_STATES: Final = frozenset(
    {"complete", "completed", "closed", "done", "landed", "satisfied"}
)
LIVE_WORK_RUN_STATES: Final = frozenset(
    {"planned", "starting", "launching", "running", "stalled", "interrupted", "reviewed", "gated"}
)
NON_RESULT_CLASSES: Final = frozenset(
    {
        "infra_unavailable",
        "quota_exhausted",
        "provider_refused",
        "untyped_harness_failure",
        "interrupted",
    }
)
RECOVERY_RELAUNCH_KINDS: Final = frozenset({"lost_work", "finished_and_cleaned"})
REVIEW_CLEARED: Final = "cleared"
GATE_PASSED: Final = "passed"
LANDED: Final = "landed"
NON_RESULT: Final = "non_result"
# The state `with_work_run` records for a launch the controller has bound but no
# external observation has yet corroborated.  It is inside the live set: the
# record itself occupies the item's slot until a delivery or recovery fact
# resolves it, because the journal cannot distinguish crash-before-apply from
# crash-after-apply.  Resume therefore refuses a planned cycle holding a launch
# (`controller_resume_indeterminate`) instead of judging the record; #631
# carries making such a cycle resolvable.
RECORDED_LAUNCH_STATE: Final = "launching"
SAME_RUN_ERROR: Final = "work run identity mismatch"
DELIVERY_IDENTITY_FIELDS: Final = (
    "candidate_sha",
    "reviewed_sha",
    "adjudication_sha",
    "gate_sha",
    "landed_sha",
    "close_evidence_sha",
)


@dataclass(frozen=True, slots=True)
class DesiredOutcomeFact:
    """One normalized Product Curator input."""

    key: str
    revision: int
    content_digest: str
    content: str | None = None
    parent_issue: int | None = None


@dataclass(frozen=True, slots=True)
class InitiativeFact:
    """The visible lifecycle fact for one Initiative."""

    key: str
    state: str


@dataclass(frozen=True, slots=True)
class WorkItemFact:
    """The visible lifecycle and scheduling facts for one Work Item."""

    key: str
    state: str
    issue: int | None = None
    blocked_by: tuple[str, ...] = ()
    priority: int | None = None
    exclusive_resources: tuple[str, ...] = ()
    seat: str = "implementer"
    profile: str | None = None
    ready_at: str | None = None


@dataclass(frozen=True, slots=True)
class WorkRunFact:
    """The visible lifecycle and delivery facts for one detached Work Run.

    The fields after ``issue`` are observations made by delivery adapters.  The
    controller may record a launch, but it cannot manufacture any of these
    clearance or landing fields.  Keeping them on the normalized fact makes the
    candidate identity travel with every later state transition.
    """

    key: str
    state: str
    work_item_key: str | None = None
    dispatch_id: str | None = None
    failure_class: str | None = None
    worktree: str | None = None
    issue: int | None = None
    candidate_sha: str | None = None
    reviewed_sha: str | None = None
    review_status: str | None = None
    review_dispatch_id: str | None = None
    adjudication_sha: str | None = None
    adjudication_status: str | None = None
    gate_sha: str | None = None
    gate_status: str | None = None
    landed_sha: str | None = None
    close_evidence_sha: str | None = None
    recovery_kind: str | None = None
    result_published: bool = False
    delivery_conflict: bool = False

    @property
    def item_key(self) -> str:
        """Return the Work Item key this run excludes, with legacy-key fallback."""
        return self.work_item_key or self.key

    @property
    def review_sha(self) -> str | None:
        """Retain the short internal alias for callers of the first draft."""
        return self.reviewed_sha

    @property
    def close_sha(self) -> str | None:
        """Expose the exact SHA cited by close evidence."""
        return self.close_evidence_sha


@dataclass(frozen=True, slots=True)
class WorktreeDebtFact:
    """A closed Work Item whose persistent tree still owes ``worktree done``."""

    issue: int
    path: str
    work_item_key: str | None = None


@dataclass(frozen=True, slots=True)
class ExternalBarFact:
    """A typed non-result that prevents a Work Item launch without failing it."""

    key: str
    kind: str
    detail: str = ""


@dataclass(frozen=True, slots=True)
class ReadyTransitionFact:
    """One durable observation that a Work Item's blockers have cleared."""

    key: str
    recorded_at: str


@dataclass(frozen=True, slots=True)
class ControlFacts:
    """Normalized facts supplied to one reconciliation cycle."""

    configured_curator: str | None
    desired_outcomes: tuple[DesiredOutcomeFact, ...]
    initiatives: tuple[InitiativeFact, ...]
    work_items: tuple[WorkItemFact, ...]
    work_runs: tuple[WorkRunFact, ...]
    worktree_debt: tuple[WorktreeDebtFact, ...] = ()
    wip_limit: int | None = None
    external_bars: tuple[ExternalBarFact, ...] = ()
    priority_order: tuple[str, ...] = ()
    ready_transitions: tuple[ReadyTransitionFact, ...] = ()


@dataclass(frozen=True, slots=True)
class LifecycleState:
    """Derived lifecycle state; never a second mutable source of truth."""

    state: str
    admitted_initiative: str | None
    reason: str


@dataclass(frozen=True, slots=True)
class ControlAction:
    """One ordered, idempotent request to an external port."""

    kind: str
    logical_key: str
    payload: tuple[tuple[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class Reconciliation:
    """The complete pure result of reducing one fact set."""

    lifecycle: LifecycleState
    actions: tuple[ControlAction, ...]
    selected_work_item: WorkItemFact | None = None
    launch_snapshot: CoordinationSnapshot | None = None
    considered: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class CoordinationSnapshot:
    """The launch-time facts that must still hold after a plan was derived."""

    work_items: tuple[WorkItemFact, ...]
    work_runs: tuple[WorkRunFact, ...]
    worktree_debt: tuple[WorktreeDebtFact, ...]
    wip_limit: int | None
    external_bars: tuple[ExternalBarFact, ...]
    priority_order: tuple[str, ...]


def coordination_snapshot(facts: ControlFacts) -> CoordinationSnapshot:
    """Project facts that can invalidate a pending Work Run launch."""
    return CoordinationSnapshot(
        facts.work_items,
        live_work_runs(facts),
        facts.worktree_debt,
        facts.wip_limit,
        facts.external_bars,
        facts.priority_order,
    )


def snapshot_document(snapshot: CoordinationSnapshot) -> dict[str, object]:
    """Render launch preconditions for dry-run output and journal actions."""
    return {
        "work_items": [_work_item_document(item) for item in snapshot.work_items],
        "work_runs": [_work_run_document(run) for run in snapshot.work_runs],
        "worktree_debt": [_worktree_debt_document(debt) for debt in snapshot.worktree_debt],
        "wip_limit": snapshot.wip_limit,
        "external_bars": [_external_bar_document(bar) for bar in snapshot.external_bars],
        "priority_order": list(snapshot.priority_order),
    }


def live_work_runs(facts: ControlFacts) -> tuple[WorkRunFact, ...]:
    """Return every run that still owns a Work Item scheduling slot."""
    return tuple(
        run
        for run in facts.work_runs
        if (
            (
                run.state in LIVE_WORK_RUN_STATES
                and not (
                    run.state == "interrupted"
                    and run.recovery_kind is not None
                    and run.recovery_kind not in {"still_live", "unproven"}
                )
            )
            or (
                run.state == LANDED
                and run.landed_sha is not None
                and not completion_ready(run)
                and not _completed_item_owns_no_slot(run, facts.work_items)
            )
            # A published result is the dispatcher's own terminal record:
            # recovery never classifies such a run (the ports adapter
            # refuses it), so only that recorded fact releases its slot.
            # The fact is read from the result itself and carried forward by
            # the merge; it is never inferred from state or failure class.
            or (
                run.failure_class in NON_RESULT_CLASSES
                and run.recovery_kind not in RECOVERY_RELAUNCH_KINDS
                and not run.result_published
            )
        )
    )


def occupied_capacity(facts: ControlFacts) -> int:
    """Count live runs plus worktree debt, the two independent capacity stocks."""
    return len(live_work_runs(facts)) + len(facts.worktree_debt)


def eligible_work_items(facts: ControlFacts) -> tuple[WorkItemFact, ...]:
    """Return Work Items that pass dependency, run, bar, resource, and WIP checks."""
    live = live_work_runs(facts)
    held_resources = _held_resources(facts, live)
    capacity_available = facts.wip_limit is not None and occupied_capacity(facts) < facts.wip_limit

    candidates = [
        item
        for item in facts.work_items
        if _is_eligible(
            item,
            facts=facts,
            live=live,
            held_resources=held_resources,
            capacity_available=capacity_available,
        )
    ]
    return tuple(sorted(candidates, key=lambda item: _priority_key(item, facts)))


def next_work_item(facts: ControlFacts) -> WorkItemFact | None:
    """Choose one Work Item by configured priority and stable key order."""
    eligible = eligible_work_items(facts)
    return eligible[0] if eligible else None


def launch_action(facts: ControlFacts, item: WorkItemFact) -> ControlAction:
    """Build the one detached-launch action owned by Work Coordination."""
    run_key = f"work-run:{item.key}"
    return ControlAction(
        "dispatch.start_work_run",
        item.key,
        (
            ("work_item_key", item.key),
            ("issue", item.issue),
            ("seat", item.seat),
            ("profile", item.profile),
            ("worktree", f"issue-{item.issue}" if item.issue is not None else item.key),
            ("run_key", run_key),
            ("preconditions", snapshot_document(coordination_snapshot(facts))),
            ("priority_source", "configured_work_item_policy"),
        ),
    )


def with_work_run(
    facts: ControlFacts,
    action: ControlAction,
    *,
    run_key: str,
    dispatch_id: str,
    state: str = RECORDED_LAUNCH_STATE,
) -> ControlFacts:
    """Return facts with the one controller-owned live run recorded."""
    payload = dict(action.payload)
    item_key = str(payload.get("work_item_key", action.logical_key))
    worktree = payload.get("worktree")
    issue = payload.get("issue")
    issue_value = issue if isinstance(issue, int) and not isinstance(issue, bool) else None
    run = WorkRunFact(
        key=run_key,
        state=state,
        work_item_key=item_key,
        dispatch_id=dispatch_id,
        worktree=str(worktree) if worktree else None,
        issue=issue_value,
    )
    live = live_work_runs(facts)
    existing = tuple(
        run
        for run in facts.work_runs
        if run.key != run_key
        and not (
            run in live
            and (run.item_key == item_key or (issue_value is not None and run.issue == issue_value))
        )
    )
    return ControlFacts(
        facts.configured_curator,
        facts.desired_outcomes,
        facts.initiatives,
        facts.work_items,
        (*existing, run),
        facts.worktree_debt,
        facts.wip_limit,
        facts.external_bars,
        facts.priority_order,
        facts.ready_transitions,
    )


def derived_work_run_state(run: WorkRunFact) -> str:
    """Derive the observable Work Run state from typed delivery facts.

    A child return code or a line in a dispatch log is deliberately absent from
    this reducer.  Only exact, structured delivery fields can move a run through
    review, gate, and landing states.  A typed non-result remains explicit even
    after recovery has made a relaunch safe.
    """
    if run.failure_class in NON_RESULT_CLASSES:
        return NON_RESULT
    if run.landed_sha is not None:
        return LANDED
    if run.candidate_sha and run.gate_status == GATE_PASSED and run.gate_sha == run.candidate_sha:
        return "gated"
    if (
        run.candidate_sha
        and run.review_status == REVIEW_CLEARED
        and run.reviewed_sha == run.candidate_sha
        and run.adjudication_status == REVIEW_CLEARED
        and run.adjudication_sha == run.candidate_sha
    ):
        return "reviewed"
    return run.state


def same_work_run(left: WorkRunFact, right: WorkRunFact) -> bool:
    """Match observations by dispatch identity, with a legacy key-only fallback."""
    if left.dispatch_id is not None or right.dispatch_id is not None:
        return left.dispatch_id is not None and left.dispatch_id == right.dispatch_id
    return left.key == right.key


def merge_work_run_observation(previous: WorkRunFact, current: WorkRunFact) -> WorkRunFact:
    """Merge one fresh observation without allowing a second landing identity.

    A terminal landing is write-once per Work Run.  A repeated signal may add
    close evidence for the same SHA; a different SHA becomes a visible conflict
    and can never satisfy completion.
    """
    if not same_work_run(previous, current):
        raise ValueError(SAME_RUN_ERROR)
    previous_ids = _delivery_identities(previous)
    current_ids = _delivery_identities(current)
    different_identity = len(set(previous_ids + current_ids)) > 1
    if different_identity or previous.delivery_conflict or current.delivery_conflict:
        # The conflict marks the landing identity; a recorded publication is a
        # separate fact about the result, so it survives the conflict rather
        # than being dropped with it.
        return replace(
            previous,
            delivery_conflict=True,
            result_published=previous.result_published or current.result_published,
        )
    previous_non_result = previous.failure_class in NON_RESULT_CLASSES
    current_non_result = current.failure_class in NON_RESULT_CLASSES
    if previous_non_result:
        # A later delivery record cannot turn a typed non-result into success.
        # A recorded publication is still a recorded fact: carrying it lets a
        # journal written before the field existed recover at the next cycle's
        # collection instead of holding its slot forever.
        return replace(
            previous,
            delivery_conflict=True,
            result_published=previous.result_published or current.result_published,
        )
    if current_non_result:
        # The typed non-result is terminal for the run's outcome, but a result
        # record carries no Work Item binding: keep the prior observation's
        # structural fields so the run stays bound to the item, issue and
        # worktree whose slot it holds rather than orphaning them.
        return replace(
            current,
            work_item_key=current.work_item_key or previous.work_item_key,
            issue=current.issue or previous.issue,
            worktree=current.worktree or previous.worktree,
            delivery_conflict=previous.delivery_conflict or current.delivery_conflict,
        )
    if previous.landed_sha is not None:
        return replace(
            previous,
            close_evidence_sha=current.close_evidence_sha or previous.close_evidence_sha,
            delivery_conflict=previous.delivery_conflict or current.delivery_conflict,
        )
    fields = {
        field_name: getattr(current, field_name) or getattr(previous, field_name)
        for field_name in (
            "candidate_sha",
            "reviewed_sha",
            "review_status",
            "review_dispatch_id",
            "adjudication_sha",
            "adjudication_status",
            "gate_sha",
            "gate_status",
            "landed_sha",
            "close_evidence_sha",
            "recovery_kind",
            "result_published",
        )
    }
    return replace(
        current,
        **fields,
        delivery_conflict=previous.delivery_conflict or current.delivery_conflict,
    )


def merge_work_run_observations(
    previous: tuple[WorkRunFact, ...], current: tuple[WorkRunFact, ...]
) -> tuple[WorkRunFact, ...]:
    """Merge current observations with durable history in stable order."""
    merged = list(current)
    for prior in previous:
        match = next(
            (index for index, observed in enumerate(merged) if same_work_run(prior, observed)),
            None,
        )
        if match is None:
            merged.append(prior)
        else:
            merged[match] = merge_work_run_observation(prior, merged[match])
    return tuple(merged)


def candidate_cleared(run: WorkRunFact) -> bool:
    """Require independent review, adjudication, and a candidate-bound gate.

    ``with_work_run`` never writes these fields, and the reviewer dispatch must
    have a distinct identity.  That makes controller self-clearance impossible
    by construction rather than by relying on a caller remembering not to set a
    flag.
    """
    if run.delivery_conflict or not run.candidate_sha:
        return False
    candidate = run.candidate_sha
    return (
        bool(run.dispatch_id)
        and run.dispatch_id != run.review_dispatch_id
        and run.review_status == REVIEW_CLEARED
        and run.reviewed_sha == candidate
        and bool(run.review_dispatch_id)
        and run.adjudication_status == REVIEW_CLEARED
        and run.adjudication_sha == candidate
        and run.gate_status == GATE_PASSED
        and run.gate_sha == candidate
    )


def delivery_identity_conflict(run: WorkRunFact) -> bool:
    """Return whether one delivery observation names more than one candidate."""
    return len(set(_delivery_identities(run))) > 1


def _delivery_identities(run: WorkRunFact) -> tuple[str, ...]:
    """Collect the identity-bearing fields used by the completion proof."""
    return tuple(
        value
        for field_name in DELIVERY_IDENTITY_FIELDS
        if (value := getattr(run, field_name)) is not None
    )


def completion_ready(run: WorkRunFact) -> bool:
    """Require clearance, exact landing, and close evidence for the same SHA."""
    candidate = run.candidate_sha
    return bool(
        run.state == LANDED
        and run.failure_class not in NON_RESULT_CLASSES
        and candidate
        and candidate_cleared(run)
        and run.landed_sha == candidate
        and run.close_evidence_sha == candidate
    )


def _run_belongs_to_item(run: WorkRunFact, item: WorkItemFact) -> bool:
    """Bind a completion to one Work Item's key and, where present, issue."""
    if run.work_item_key is not None and run.work_item_key != item.key:
        return False
    if (
        run.work_item_key is None
        and run.item_key != item.key
        and (run.issue is None or item.issue is None or run.issue != item.issue)
    ):
        return False
    return not (run.issue is not None and item.issue is not None and run.issue != item.issue)


def _completed_item_owns_no_slot(run: WorkRunFact, items: tuple[WorkItemFact, ...]) -> bool:
    """Keep a delayed terminal signal from reacquiring capacity after completion."""
    return any(
        item.state in COMPLETE_WORK_ITEM_STATES and _run_belongs_to_item(run, item)
        for item in items
    )


def advance_completed_work_items(facts: ControlFacts) -> ControlFacts:
    """Advance only Work Items with one exact, fully evidenced completion.

    This is idempotent: an already complete item is left unchanged, and a
    delayed or conflicting landing signal cannot create another completion.
    """
    completed = {
        item.key
        for item in facts.work_items
        if any(_run_belongs_to_item(run, item) and completion_ready(run) for run in facts.work_runs)
    }
    if not completed:
        return facts
    items = tuple(
        replace(item, state="complete") if item.key in completed else item
        for item in facts.work_items
    )
    return replace(facts, work_items=items)


def retain_completed_work_items(previous: ControlFacts, current: ControlFacts) -> ControlFacts:
    """Carry a controller-observed completion across a stale tracker read."""
    prior = {
        item.key: item for item in previous.work_items if item.state in COMPLETE_WORK_ITEM_STATES
    }
    if not prior:
        return current
    items = tuple(
        replace(prior[item.key], state="complete")
        if item.key in prior and item.state not in COMPLETE_WORK_ITEM_STATES
        else item
        for item in current.work_items
    )
    return replace(current, work_items=items)


def newly_ready_keys(previous: ControlFacts | None, current: ControlFacts) -> tuple[str, ...]:
    """Find Work Items whose dependency predicate changed from blocked to ready."""
    if previous is None:
        return ()
    previous_items = {item.key: item for item in previous.work_items}
    current_items = {item.key: item for item in current.work_items}
    result: list[str] = []
    for item in current.work_items:
        old = previous_items.get(item.key)
        if old is None:
            continue
        if _is_ready(item, current_items) and not _is_ready(old, previous_items):
            result.append(item.key)
    return tuple(result)


def with_ready_transitions(
    facts: ControlFacts, keys: tuple[str, ...], recorded_at: str
) -> ControlFacts:
    """Persist newly observed readiness transitions without duplicating them."""
    existing = {transition.key for transition in facts.ready_transitions}
    additions = tuple(ReadyTransitionFact(key, recorded_at) for key in keys if key not in existing)
    if not additions:
        return facts
    return ControlFacts(
        facts.configured_curator,
        facts.desired_outcomes,
        facts.initiatives,
        facts.work_items,
        facts.work_runs,
        facts.worktree_debt,
        facts.wip_limit,
        facts.external_bars,
        facts.priority_order,
        facts.ready_transitions + additions,
    )


def derive(
    facts: ControlFacts,
    previously_confirmed: LifecycleState | None = None,
) -> Reconciliation:
    """Derive lifecycle and, when possible, one deterministic Work Run launch.

    The previous state is accepted so replay callers can pass the confirmed
    journal state explicitly.  It is intentionally not trusted as authority:
    the lifecycle is derived from the newly collected facts every time.
    """
    del previously_confirmed
    if facts.configured_curator is None:
        reason = "no_product_curator_configured"
    elif not facts.desired_outcomes:
        reason = "no_desired_outcome"
    elif len(facts.desired_outcomes) != 1:
        reason = "desired_outcome_cardinality_not_one"
    elif facts.initiatives and facts.work_items:
        return _derive_coordination(facts)
    elif facts.initiatives:
        reason = "active_initiative_present"
    else:
        reason = "initiative_admission_not_implemented"
    return Reconciliation(
        lifecycle=LifecycleState(NO_ADMISSIBLE_INITIATIVE, None, reason),
        actions=(),
    )


def _derive_coordination(facts: ControlFacts) -> Reconciliation:
    """Reduce the published Work Graph without consulting any capability."""
    initiative = facts.initiatives[0]
    selected = next_work_item(facts)
    considered = tuple((item.key, _eligibility_reason(item, facts)) for item in facts.work_items)
    if selected is None:
        reason = _coordination_reason(facts)
        state = (
            BLOCKED_EXTERNAL
            if any(
                _bar_matches_item(bar, item)
                for item in facts.work_items
                for bar in facts.external_bars
            )
            else DELIVERING
        )
        return Reconciliation(
            LifecycleState(state, initiative.key, reason),
            (),
            None,
            coordination_snapshot(facts),
            considered,
        )
    return Reconciliation(
        LifecycleState(DELIVERING, initiative.key, "eligible_work_item"),
        (launch_action(facts, selected),),
        selected,
        coordination_snapshot(facts),
        considered,
    )


def _coordination_reason(facts: ControlFacts) -> str:
    """Give a stable reason for an empty eligible set, in policy order."""
    bar = next(
        (
            bar
            for item in facts.work_items
            for bar in facts.external_bars
            if _bar_matches_item(bar, item)
        ),
        None,
    )
    if bar is not None:
        return f"external_bar:{bar.kind}"
    if facts.wip_limit is None:
        return "wip_limit_unconfigured"
    if occupied_capacity(facts) >= facts.wip_limit:
        return "wip_reached_by_live_runs_or_worktree_debt"
    return NO_ELIGIBLE_WORK_ITEM


def _eligibility_reason(item: WorkItemFact, facts: ControlFacts) -> str:
    """Explain one candidate's first failed scheduling predicate."""
    item_by_key = {candidate.key: candidate for candidate in facts.work_items}
    live = live_work_runs(facts)
    held_resources = _held_resources(facts, live)
    reason = "eligible"
    if item.state not in OPEN_WORK_ITEM_STATES:
        reason = f"state:{item.state}"
    elif any(blocker not in item_by_key for blocker in item.blocked_by):
        reason = "blocked_by_unknown"
    else:
        blocked = next(
            (
                blocker
                for blocker in item.blocked_by
                if item_by_key[blocker].state not in COMPLETE_WORK_ITEM_STATES
            ),
            None,
        )
        if blocked is not None:
            reason = f"blocked_by:{blocked}"
        elif any(_run_matches_item(run, item) for run in live):
            reason = "live_work_run"
        else:
            bar = _external_bar_for_item(item, facts.external_bars)
            if bar is not None:
                reason = f"external_bar:{bar.kind}"
            elif any(resource in held_resources for resource in item.exclusive_resources):
                reason = "exclusive_resource_held"
            elif facts.wip_limit is None:
                reason = "wip_limit_unconfigured"
            elif occupied_capacity(facts) >= facts.wip_limit:
                reason = "wip_reached_by_live_runs_or_worktree_debt"
    return reason


def _run_matches_item(run: WorkRunFact, item: WorkItemFact) -> bool:
    """Match a live run by stable Work Item key or its tracker issue identity."""
    return run.item_key == item.key or (
        run.issue is not None and item.issue is not None and run.issue == item.issue
    )


def _item_for_run(run: WorkRunFact, items: tuple[WorkItemFact, ...]) -> WorkItemFact | None:
    """Find a live run's graph node even when its adapter only knows the issue number."""
    return next((item for item in items if _run_matches_item(run, item)), None)


def _item_for_debt(debt: WorktreeDebtFact, items: tuple[WorkItemFact, ...]) -> WorkItemFact | None:
    """Find a debt holder's graph node by stable key or tracker issue identity."""
    if debt.work_item_key is not None:
        found = next((item for item in items if item.key == debt.work_item_key), None)
        if found is not None:
            return found
    return next((item for item in items if item.issue == debt.issue), None)


def _bar_matches_item(bar: ExternalBarFact, item: WorkItemFact) -> bool:
    """Match a launch bar by stable Work Item key or tracker issue identity."""
    return bar.key == item.key or (item.issue is not None and bar.key == str(item.issue))


def _external_bar_for_item(
    item: WorkItemFact, bars: tuple[ExternalBarFact, ...]
) -> ExternalBarFact | None:
    """Return the first typed launch bar for one Work Item."""
    return next((bar for bar in bars if _bar_matches_item(bar, item)), None)


def _held_resources(
    facts: ControlFacts, live: tuple[WorkRunFact, ...] | None = None
) -> frozenset[str]:
    """Return resources held by live runs and worktree debt."""
    active_runs = live if live is not None else live_work_runs(facts)
    resources: set[str] = set()
    for run in active_runs:
        holder = _item_for_run(run, facts.work_items)
        if holder is not None:
            resources.update(holder.exclusive_resources)
    for debt in facts.worktree_debt:
        holder = _item_for_debt(debt, facts.work_items)
        if holder is not None:
            resources.update(holder.exclusive_resources)
    return frozenset(resources)


def _is_eligible(
    item: WorkItemFact,
    *,
    facts: ControlFacts,
    live: tuple[WorkRunFact, ...],
    held_resources: frozenset[str],
    capacity_available: bool,
) -> bool:
    """Evaluate every scheduling predicate for one Work Item."""
    item_by_key = {candidate.key: candidate for candidate in facts.work_items}
    if item.state not in OPEN_WORK_ITEM_STATES:
        return False
    if (
        any(_run_matches_item(run, item) for run in live)
        or _external_bar_for_item(item, facts.external_bars) is not None
    ):
        return False
    if any(
        item_by_key.get(blocker) is None
        or item_by_key[blocker].state not in COMPLETE_WORK_ITEM_STATES
        for blocker in item.blocked_by
    ):
        return False
    if any(resource in held_resources for resource in item.exclusive_resources):
        return False
    return capacity_available


def _is_ready(item: WorkItemFact, items: dict[str, WorkItemFact]) -> bool:
    """Evaluate the dependency predicate used by both selection and transition tracking."""
    return item.state in OPEN_WORK_ITEM_STATES and all(
        blocker in items and items[blocker].state in COMPLETE_WORK_ITEM_STATES
        for blocker in item.blocked_by
    )


def _priority_key(item: WorkItemFact, facts: ControlFacts) -> tuple[int, int, str]:
    """Order by configured list first, then an explicit configured rank, then key."""
    try:
        configured = facts.priority_order.index(item.key)
    except ValueError:
        configured = 2**31 - 1
    explicit = item.priority if item.priority is not None else 2**31 - 1
    return configured, explicit, item.key


def _work_item_document(item: WorkItemFact) -> dict[str, object]:
    """Render one Work Item without emitting default compatibility fields."""
    document: dict[str, object] = {"key": item.key, "state": item.state}
    if item.issue is not None:
        document["issue"] = item.issue
    if item.blocked_by:
        document["blocked_by"] = list(item.blocked_by)
    if item.priority is not None:
        document["priority"] = item.priority
    if item.exclusive_resources:
        document["exclusive_resources"] = list(item.exclusive_resources)
    if item.seat != "implementer":
        document["seat"] = item.seat
    if item.profile is not None:
        document["profile"] = item.profile
    if item.ready_at is not None:
        document["ready_at"] = item.ready_at
    return document


def _work_run_document(run: WorkRunFact) -> dict[str, object]:
    """Render one Work Run without emitting default compatibility fields."""
    document: dict[str, object] = {"key": run.key, "state": run.state}
    if run.work_item_key is not None:
        document["work_item_key"] = run.work_item_key
    if run.dispatch_id is not None:
        document["dispatch_id"] = run.dispatch_id
    if run.failure_class is not None:
        document["failure_class"] = run.failure_class
    if run.worktree is not None:
        document["worktree"] = run.worktree
    if run.issue is not None:
        document["issue"] = run.issue
    for field_name in (
        "candidate_sha",
        "reviewed_sha",
        "review_status",
        "review_dispatch_id",
        "adjudication_sha",
        "adjudication_status",
        "gate_sha",
        "gate_status",
        "landed_sha",
        "close_evidence_sha",
        "recovery_kind",
    ):
        value = getattr(run, field_name)
        if value is not None:
            document[field_name] = value
    # Recorded facts survive the journal boundary: a stamp dropped here would
    # reload as False and put a released run's slot back on the next cycle.
    if run.result_published:
        document["result_published"] = True
    if run.delivery_conflict:
        document["delivery_conflict"] = True
    return document


def _worktree_debt_document(debt: WorktreeDebtFact) -> dict[str, object]:
    """Render one worktree debt fact."""
    document: dict[str, object] = {"issue": debt.issue, "path": debt.path}
    if debt.work_item_key is not None:
        document["work_item_key"] = debt.work_item_key
    return document


def _external_bar_document(bar: ExternalBarFact) -> dict[str, object]:
    """Render one typed launch bar."""
    document: dict[str, object] = {"key": bar.key, "kind": bar.kind}
    if bar.detail:
        document["detail"] = bar.detail
    return document


def facts_document(facts: ControlFacts) -> dict[str, object]:
    """Render normalized facts without introducing an I/O dependency."""
    desired_outcomes = []
    for outcome in facts.desired_outcomes:
        document: dict[str, object] = {
            "key": outcome.key,
            "revision": outcome.revision,
            "content_digest": outcome.content_digest,
        }
        if outcome.content is not None:
            document["content"] = outcome.content
        if outcome.parent_issue is not None:
            document["parent_issue"] = outcome.parent_issue
        desired_outcomes.append(document)
    document: dict[str, object] = {
        "configured_curator": facts.configured_curator,
        "desired_outcomes": desired_outcomes,
        "initiatives": [asdict(item) for item in facts.initiatives],
        "work_items": [_work_item_document(item) for item in facts.work_items],
        "work_runs": [_work_run_document(run) for run in facts.work_runs],
    }
    if facts.worktree_debt:
        document["worktree_debt"] = [_worktree_debt_document(item) for item in facts.worktree_debt]
    if facts.wip_limit is not None:
        document["wip_limit"] = facts.wip_limit
    if facts.external_bars:
        document["external_bars"] = [_external_bar_document(item) for item in facts.external_bars]
    if facts.priority_order:
        document["priority_order"] = list(facts.priority_order)
    if facts.ready_transitions:
        document["ready_transitions"] = [asdict(item) for item in facts.ready_transitions]
    return document


def lifecycle_document(lifecycle: LifecycleState) -> dict[str, object]:
    """Render derived lifecycle state as a stable value document."""
    return asdict(lifecycle)


def actions_document(actions: tuple[ControlAction, ...]) -> list[dict[str, object]]:
    """Render the ordered action plan, preserving its sequence."""
    return [
        {
            "order": index,
            "kind": action.kind,
            "logical_key": action.logical_key,
            "payload": dict(action.payload),
        }
        for index, action in enumerate(actions, start=1)
    ]
