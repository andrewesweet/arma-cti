"""One-shot System-of-Work Controller command."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

sys.path.insert(0, str(Path(__file__).parent))

import controller_planning as planning
import controller_policy as policy
import controller_ports as ports
import controller_store as store_module

DEFAULT_ROOT: Final = Path.home() / ".arma-cti" / "controller"


@dataclass(frozen=True, slots=True)
class CycleReport:
    """Observable result of exactly one reconciliation cycle."""

    cycle_id: str
    facts: policy.ControlFacts
    lifecycle: policy.LifecycleState
    actions: tuple[policy.ControlAction, ...]
    dry_run: bool
    journal_written: bool
    state_source: str
    planning_status: str | None = None
    plan_revision: str | None = None
    product_question: dict[str, object] | None = None
    selected_work_item: str | None = None
    launch_snapshot: policy.CoordinationSnapshot | None = None
    considered: tuple[tuple[str, str], ...] = ()

    def to_document(self) -> dict[str, object]:
        """Render the stable command result and its explicit empty collections."""
        external_mutations = {
            port_name: (
                not self.dry_run
                and any(action.kind.split(".", 1)[0] == port_name for action in self.actions)
            )
            for port_name in ("tracker", "worktree", "dispatch", "evidence")
        }
        document: dict[str, object] = {
            "cycle_id": self.cycle_id,
            "control_facts": policy.facts_document(self.facts),
            "lifecycle": policy.lifecycle_document(self.lifecycle),
            "control_actions": policy.actions_document(self.actions),
            "dry_run": self.dry_run,
            "journal_written": self.journal_written,
            "state_source": self.state_source,
            "mutations": {
                **external_mutations,
                "journal": self.journal_written,
            },
        }
        planning_document: dict[str, object] = {}
        if self.planning_status is not None:
            planning_document["status"] = self.planning_status
        if self.plan_revision is not None:
            planning_document["plan_revision"] = self.plan_revision
        if self.product_question is not None:
            planning_document["question"] = self.product_question
        if planning_document:
            document["planning"] = planning_document
        if self.launch_snapshot is not None:
            document["coordination"] = {
                "selected_work_item": self.selected_work_item,
                "considered": [{"key": key, "reason": reason} for key, reason in self.considered],
                "launch_preconditions": policy.snapshot_document(self.launch_snapshot),
            }
        return document


@dataclass(frozen=True, slots=True)
class UnsupportedActionPort:
    """Conservative production adapter until an external action is implemented."""

    def apply(self, action: policy.ControlAction) -> None:
        """Refuse instead of pretending an external mutation happened."""
        raise store_module.ControllerActionUnsupportedError(action.kind)


class Controller:
    """Coordinate capability ports around the pure reconciliation policy."""

    def __init__(  # noqa: PLR0913 — each injected capability is an independent application seam
        self,
        *,
        fact_collector: ports.FactCollector,
        clock: ports.Clock,
        identity: ports.IdentitySource,
        store: store_module.ControllerStore,
        action_ports: ports.ActionPorts,
        stage_gateway: planning.SemanticStageGateway | None = None,
        repository_context: planning.RepositoryContextSource | None = None,
        repository_root: Path | None = None,
        plan_store: planning.ValidatedPlanStore | None = None,
    ) -> None:
        """Inject every external capability at the application seam."""
        self.fact_collector = fact_collector
        self.clock = clock
        self.identity = identity
        self.store = store
        self._ports = action_ports
        self.stage_gateway = stage_gateway
        self.repository_root = repository_root or planning.acceptance.REPO
        self.repository_context = repository_context or planning.FileRepositoryContext(
            self.repository_root / "CONTEXT.md"
        )
        self.plan_store = plan_store or planning.ValidatedPlanStore(
            store.plans_root,
            repository_root=self.repository_root,
        )

    def run_cycle(self, *, dry_run: bool) -> CycleReport:
        """Collect, reduce, and optionally execute exactly one cycle."""
        fresh_root = self.store.is_fresh()
        if dry_run:
            previous = None if fresh_root else self.store.load_recoverable()
            return self._cycle(previous, dry_run=True, fresh_root=fresh_root)
        self.store.mark_started()
        with self.store.scheduling_lock():
            previous = None if fresh_root else self.store.load_recoverable()
            return self._cycle(previous, dry_run=False, fresh_root=fresh_root)

    def _cycle(
        self,
        previous: store_module.LoadedControllerState | None,
        *,
        dry_run: bool,
        fresh_root: bool,
    ) -> CycleReport:
        """Run the policy and, for a real cycle, persist each transition phase."""
        if previous is not None and previous.phase != "confirmed":
            return self._resume(previous, dry_run=dry_run)
        facts = self._merge_local_facts(self._collect_facts(previous), previous)
        facts = policy.advance_completed_work_items(facts)
        ready_keys = policy.newly_ready_keys(
            previous.facts if previous is not None else None, facts
        )
        if ready_keys:
            facts = policy.with_ready_transitions(facts, ready_keys, self.clock.now())
        prior_lifecycle = previous.lifecycle if previous is not None else None
        plan = policy.derive(facts, prior_lifecycle)
        planning_result = self._planning_result(facts, previous)
        if planning_result is not None:
            lifecycle, actions, status, revision, question, stored_plan = planning_result
            plan = policy.Reconciliation(lifecycle=lifecycle, actions=actions)
        else:
            status = None
            revision = None
            question = None
            stored_plan = None
        cycle_id = self._cycle_id(previous, fresh_start=fresh_root)
        if dry_run and plan.launch_snapshot is not None and plan.actions:
            cycle_action = self._bind_launch_action(plan.actions[0], cycle_id)
            plan = policy.Reconciliation(
                lifecycle=plan.lifecycle,
                actions=(cycle_action,),
                selected_work_item=plan.selected_work_item,
                launch_snapshot=plan.launch_snapshot,
                considered=plan.considered,
            )
        if dry_run:
            return CycleReport(
                cycle_id=cycle_id,
                facts=facts,
                lifecycle=plan.lifecycle,
                actions=plan.actions,
                dry_run=True,
                journal_written=False,
                state_source="bootstrap" if fresh_root else "replayed",
                planning_status=status,
                plan_revision=revision,
                product_question=question,
                selected_work_item=(
                    plan.selected_work_item.key if plan.selected_work_item is not None else None
                ),
                launch_snapshot=plan.launch_snapshot,
                considered=plan.considered,
            )

        if plan.launch_snapshot is not None and plan.actions:
            refreshed = self._merge_local_facts(self._collect_facts(previous), previous)
            refreshed = policy.advance_completed_work_items(refreshed)
            if policy.coordination_snapshot(refreshed) != plan.launch_snapshot:
                selected_key = plan.selected_work_item.key if plan.selected_work_item else "unknown"
                raise store_module.ControllerLaunchStale(selected_key)
            cycle_action = self._bind_launch_action(plan.actions[0], cycle_id)
            plan = policy.Reconciliation(
                lifecycle=plan.lifecycle,
                actions=(cycle_action,),
                selected_work_item=plan.selected_work_item,
                launch_snapshot=plan.launch_snapshot,
                considered=plan.considered,
            )
            run_key = str(dict(cycle_action.payload)["run_key"])
            facts = policy.with_work_run(
                facts,
                cycle_action,
                run_key=run_key,
                dispatch_id=str(dict(cycle_action.payload)["dispatch_id"]),
            )

        payload = self._payload(facts, plan, stored_plan)
        self._record(cycle_id, "planned", payload)
        for action in plan.actions:
            self._apply(action)
        self._record(cycle_id, "applied", payload)
        self._record(cycle_id, "confirmed", payload)
        self.store.materialize_view()
        return CycleReport(
            cycle_id=cycle_id,
            facts=facts,
            lifecycle=plan.lifecycle,
            actions=plan.actions,
            dry_run=False,
            journal_written=True,
            state_source="bootstrap" if fresh_root else "replayed",
            planning_status=status,
            plan_revision=revision,
            product_question=question,
            selected_work_item=(
                plan.selected_work_item.key if plan.selected_work_item is not None else None
            ),
            launch_snapshot=plan.launch_snapshot,
            considered=plan.considered,
        )

    def _resume(
        self,
        previous: store_module.LoadedControllerState,
        *,
        dry_run: bool,
    ) -> CycleReport:
        """Finish one journaled plan without recollecting facts or re-deriving actions."""
        facts = previous.facts
        if facts is None:
            reason = "resume_facts_missing"
            raise store_module.ControllerStateUnreadable(reason)
        actions = previous.actions
        if dry_run:
            return CycleReport(
                cycle_id=previous.last_cycle_id,
                facts=facts,
                lifecycle=previous.lifecycle,
                actions=actions,
                dry_run=True,
                journal_written=False,
                state_source="resumed",
                planning_status=planning.VALID if previous.plan is not None else None,
                plan_revision=(
                    str(previous.plan["revision_id"]) if previous.plan is not None else None
                ),
            )
        payload = previous.confirmed
        if previous.phase == "planned":
            unobserved = self._unobserved_launch_run_keys(previous, actions)
            for action in actions:
                if self._is_launch_action(action):
                    current = self._collect_facts(previous, unobserved_run_keys=unobserved)
                    if not self._has_live_run_for_action(current, action):
                        self._assert_resume_fresh(current, action)
                        self._apply(action)
                else:
                    self._apply(action)
            self._record(previous.last_cycle_id, "applied", payload)
        self._record(previous.last_cycle_id, "confirmed", payload)
        self.store.materialize_view()
        return CycleReport(
            cycle_id=previous.last_cycle_id,
            facts=facts,
            lifecycle=previous.lifecycle,
            actions=actions,
            dry_run=False,
            journal_written=True,
            state_source="resumed",
            planning_status=planning.VALID if previous.plan is not None else None,
            plan_revision=(
                str(previous.plan["revision_id"]) if previous.plan is not None else None
            ),
            selected_work_item=self._selected_from_actions(actions),
        )

    def _collect_facts(
        self,
        previous: store_module.LoadedControllerState | None,
        *,
        unobserved_run_keys: frozenset[str] = frozenset(),
    ) -> policy.ControlFacts:
        """Collect delivery facts with recovery history before planning or relaunching."""
        if previous is not None and previous.facts is not None:
            collector = self.fact_collector
            if isinstance(collector, ports.HistoricalFactCollector):
                runs = previous.facts.work_runs
                if unobserved_run_keys:
                    runs = tuple(run for run in runs if run.key not in unobserved_run_keys)
                return collector.collect_with_previous(runs)
        return self.fact_collector.collect()

    def _planning_result(  # noqa: C901, PLR0911, PLR0912 — typed stage outcomes form one ordered gate
        self,
        facts: policy.ControlFacts,
        previous: store_module.LoadedControllerState | None,
    ) -> (
        tuple[
            policy.LifecycleState,
            tuple[policy.ControlAction, ...],
            str,
            str | None,
            dict[str, object] | None,
            planning.ValidatedPlan | None,
        ]
        | None
    ):
        """Run or resume Initiative Planning only when exactly one outcome is eligible."""
        if self.stage_gateway is None:
            return None
        if facts.configured_curator is None or len(facts.desired_outcomes) != 1:
            return None
        if facts.initiatives:
            return None
        outcome = facts.desired_outcomes[0]
        if outcome.content is None:
            return self._planning_refusal(
                planning.INFRA_UNAVAILABLE,
                "desired_outcome_content_absent",
            )
        if hashlib.sha256(outcome.content.encode("utf-8")).hexdigest() != outcome.content_digest:
            return self._planning_refusal(planning.INVALID, "desired_outcome_digest_mismatch")
        if previous is not None and previous.plan is not None:
            try:
                stored = self.plan_store.load(str(previous.plan["revision_id"]))
            except planning.PlanStorageError as error:
                return self._planning_refusal(planning.INFRA_UNAVAILABLE, error.code)
            if self._same_outcome(stored.plan, outcome):
                return (
                    policy.LifecycleState("operative", stored.plan.initiative_key, "plan_replayed"),
                    (),
                    planning.VALID,
                    stored.revision_id,
                    None,
                    stored.plan,
                )
        try:
            request = planning.StageRequest(
                stage=planning.INITIATIVE_PLANNING,
                input_revision=f"{outcome.key}@{outcome.revision}",
                desired_outcome=planning.DesiredOutcomeSnapshot(
                    outcome.key,
                    outcome.revision,
                    outcome.content,
                    outcome.content_digest,
                ),
                repository_context=self.repository_context.read(),
            )
            raw_verdict = self.stage_gateway.run(request)
            verdict = planning.validate_stage_verdict(raw_verdict, request)
        except planning.StageValidationError as error:
            return self._planning_refusal(planning.INVALID, error.code)
        except planning.PlanValidationError as error:
            return self._planning_refusal(planning.INVALID, error.code)
        except planning.TrackerError as error:
            return self._planning_refusal(planning.INFRA_UNAVAILABLE, error.code)
        if verdict.status == planning.PRODUCT_QUESTION:
            return (
                policy.LifecycleState("needs_product_input", outcome.key, verdict.reason),
                (),
                verdict.status,
                None,
                dict(verdict.question) if verdict.question is not None else None,
                None,
            )
        if not verdict.publication_allowed:
            return self._planning_refusal(verdict.status, verdict.reason)
        try:
            submitted = planning.PlanningSubmission(
                self.plan_store,
                repository_root=self.repository_root,
            ).submit(verdict.plan)
            self._require_same_outcome(submitted.plan, outcome)
            actions = planning.publication_actions(
                submitted.plan,
                str(outcome.parent_issue or outcome.key),
            )
        except planning.PlanValidationError as error:
            return self._planning_refusal(planning.INVALID, error.code)
        except planning.PlanStorageError as error:
            return self._planning_refusal(planning.INFRA_UNAVAILABLE, error.code)
        return (
            policy.LifecycleState("operative", submitted.plan.initiative_key, "validated_plan"),
            actions,
            planning.VALID,
            submitted.revision_id,
            None,
            submitted.plan,
        )

    @staticmethod
    def _same_outcome(plan: planning.ValidatedPlan, outcome: policy.DesiredOutcomeFact) -> bool:
        """Require exact key, version, content, and digest identity."""
        return (
            plan.desired_outcome.key == outcome.key
            and plan.desired_outcome.revision == outcome.revision
            and plan.desired_outcome.content == outcome.content
            and plan.desired_outcome.content_digest == outcome.content_digest
        )

    @staticmethod
    def _require_same_outcome(
        plan: planning.ValidatedPlan,
        outcome: policy.DesiredOutcomeFact,
    ) -> None:
        """Reject a package that changed the exact Desired Outcome being planned."""
        if not Controller._same_outcome(plan, outcome):
            code = "desired_outcome_mismatch"
            detail = "plan does not preserve frozen outcome"
            raise planning.PlanValidationError(code, detail)

    @staticmethod
    def _planning_refusal(
        status: str,
        reason: str,
    ) -> tuple[
        policy.LifecycleState,
        tuple[policy.ControlAction, ...],
        str,
        str | None,
        dict[str, object] | None,
        planning.ValidatedPlan | None,
    ]:
        """Return a typed no-mutation planning result."""
        return (
            policy.LifecycleState("planning_suspended", None, reason),
            (),
            status,
            None,
            None,
            None,
        )

    def _record(self, cycle_id: str, phase: str, payload: dict[str, object]) -> None:
        """Record a phase with injected deterministic time and identity."""
        self.store.append_phase(
            cycle_id,
            phase,
            payload,
            recorded_at=self.clock.now(),
            recorded_by=self.identity.identity(),
        )

    def _apply(self, action: policy.ControlAction) -> object | None:
        """Route a derived action to its narrow external port."""
        port_name = action.kind.split(".", 1)[0]
        try:
            port = getattr(self._ports, port_name)
        except AttributeError as error:
            raise store_module.ControllerActionUnsupported(action.kind) from error
        try:
            return port.apply(action)
        except planning.TrackerError as error:
            if error.code == "unsupported_action":
                raise store_module.ControllerActionUnsupported(action.kind) from error
            raise

    def _merge_local_facts(
        self,
        facts: policy.ControlFacts,
        previous: store_module.LoadedControllerState | None,
    ) -> policy.ControlFacts:
        """Retain only confirmed local live-run/readiness facts until delivery observes them."""
        if previous is None or previous.facts is None:
            return facts
        current_runs = list(facts.work_runs)
        for prior in previous.facts.work_runs:
            match = next(
                (
                    index
                    for index, current in enumerate(current_runs)
                    if self._run_matches(prior, current)
                ),
                None,
            )
            if match is None:
                current_runs.append(prior)
            else:
                current_runs[match] = policy.merge_work_run_observation(prior, current_runs[match])
        current_transitions = list(facts.ready_transitions)
        known_transitions = {transition.key for transition in current_transitions}
        current_transitions.extend(
            transition
            for transition in previous.facts.ready_transitions
            if transition.key not in known_transitions
        )
        merged = policy.ControlFacts(
            facts.configured_curator,
            facts.desired_outcomes,
            facts.initiatives,
            facts.work_items,
            tuple(current_runs),
            facts.worktree_debt,
            facts.wip_limit,
            facts.external_bars,
            facts.priority_order,
            tuple(current_transitions),
        )
        return policy.retain_completed_work_items(previous.facts, merged)

    @staticmethod
    def _run_matches(left: policy.WorkRunFact, right: policy.WorkRunFact) -> bool:
        """Match a local run to a fresh delivery fact by exact dispatch identity."""
        return policy.same_work_run(left, right)

    @staticmethod
    def _is_launch_action(action: policy.ControlAction) -> bool:
        """Identify the one action whose preconditions are checked at launch."""
        return action.kind == "dispatch.start_work_run"

    @staticmethod
    def _has_live_run_for_action(facts: policy.ControlFacts, action: policy.ControlAction) -> bool:
        """Avoid a duplicate after a crash between the real launch and journal confirmation."""
        payload = dict(action.payload)
        key = str(payload.get("work_item_key", action.logical_key))
        issue = payload.get("issue")
        return any(
            run.item_key == key or (isinstance(issue, int) and run.issue == issue)
            for run in policy.live_work_runs(facts)
        )

    @staticmethod
    def _is_unobserved_recorded_run(run: policy.WorkRunFact) -> bool:
        """Return whether a run is still exactly the launch record ``with_work_run`` wrote.

        A planned-phase journal cannot distinguish crash-before-apply from
        crash-after-apply, so its own launch record is intent and never
        evidence.  Any field an external observation writes — the dispatcher's
        own running state, a recovery verdict, or a delivery identity — turns
        the run into evidence that the apply did happen.
        """
        return (
            run.state == policy.RECORDED_LAUNCH_STATE
            and run.recovery_kind is None
            and not run.delivery_conflict
            and not any(getattr(run, name) for name in policy.DELIVERY_IDENTITY_FIELDS)
        )

    @classmethod
    def _unobserved_launch_run_keys(
        cls,
        previous: store_module.LoadedControllerState,
        actions: tuple[policy.ControlAction, ...],
    ) -> frozenset[str]:
        """Return the run keys this planned phase recorded and nothing has observed."""
        if previous.facts is None:
            return frozenset()
        recorded = {run.key: run for run in previous.facts.work_runs}
        keys = set()
        for action in actions:
            if not cls._is_launch_action(action):
                continue
            run_key = dict(action.payload).get("run_key")
            run = recorded.get(str(run_key)) if run_key is not None else None
            if run is not None and cls._is_unobserved_recorded_run(run):
                keys.add(run.key)
        return frozenset(keys)

    @staticmethod
    def _assert_resume_fresh(facts: policy.ControlFacts, action: policy.ControlAction) -> None:
        """Apply the same launch snapshot guard when resuming a planned cycle."""
        expected = dict(action.payload).get("preconditions")
        actual = policy.snapshot_document(policy.coordination_snapshot(facts))
        if expected != actual:
            raise store_module.ControllerLaunchStale(action.logical_key)

    def _bind_launch_action(
        self, action: policy.ControlAction, cycle_id: str
    ) -> policy.ControlAction:
        """Bind one stable Work Run and dispatch identity after the cycle is named."""
        run_key = f"{self.identity.identity()}:{cycle_id}:{action.logical_key}"
        payload = dict(action.payload)
        payload["run_key"] = run_key
        payload["dispatch_id"] = run_key
        return policy.ControlAction(action.kind, action.logical_key, tuple(payload.items()))

    @staticmethod
    def _selected_from_actions(actions: tuple[policy.ControlAction, ...]) -> str | None:
        """Recover a selected Work Item key from a resumed launch action."""
        action = next((item for item in actions if item.kind == "dispatch.start_work_run"), None)
        return action.logical_key if action is not None else None

    def _cycle_id(
        self,
        previous: store_module.LoadedControllerState | None,
        *,
        fresh_start: bool,
    ) -> str:
        """Build a unique cycle identity without a direct clock or random call."""
        ordinal = self.store.next_cycle_number(previous, fresh_start=fresh_start)
        return f"{self.identity.identity()}-cycle-{ordinal}"

    @staticmethod
    def _payload(
        facts: policy.ControlFacts,
        plan: policy.Reconciliation,
        validated_plan: planning.ValidatedPlan | None = None,
    ) -> dict[str, object]:
        """Build the persistence payload from independent pure renderers."""
        payload: dict[str, object] = {
            "facts": policy.facts_document(facts),
            "lifecycle": policy.lifecycle_document(plan.lifecycle),
            "actions": policy.actions_document(plan.actions),
        }
        if validated_plan is not None:
            payload["plan"] = {
                "revision_id": validated_plan.revision_id,
                "initiative_key": validated_plan.initiative_key,
                "desired_outcome_key": validated_plan.desired_outcome.key,
                "desired_outcome_revision": validated_plan.desired_outcome.revision,
                "content_digest": validated_plan.content_digest,
            }
        return payload


def default_controller(root: Path | None = None) -> Controller:
    """Build the runnable first-slice controller with conservative adapters."""
    state_root = root or Path(os.environ.get("CTI_CONTROLLER_DIR", DEFAULT_ROOT))
    repository = os.environ.get("CTI_GITHUB_REPOSITORY", "andrewesweet/arma-cti")
    tracker = planning.PlanPublisher(planning.GitHubTracker(repository))
    queue_directory = os.environ.get("CTI_QUEUE_DIR", str(ports.queue_policy.DEFAULT_QUEUE_DIR))
    dispatch_directory = Path(
        os.environ.get("CTI_DISPATCH_DIR", str(Path.home() / ".arma-cti" / "dispatches"))
    )
    delivery = ports.DispatchDeliveryFactCollector(
        dispatch_directory,
        recovery=ports.ExistingRecoveryClassifier(
            Path.cwd(),
            Path.home() / ".arma-cti" / "watch",
            dispatch_directory,
        ),
    )
    facts: ports.FactCollector = ports.RuntimeFactCollector(
        ports.DefaultFactCollector(),
        Path.cwd(),
        dispatch_directory,
        Path(queue_directory) if queue_directory else None,
        delivery,
    )
    return Controller(
        fact_collector=facts,
        clock=ports.SystemClock(),
        identity=ports.SystemIdentity(),
        store=store_module.ControllerStore(state_root),
        action_ports=ports.ActionPorts(
            tracker,
            UnsupportedActionPort(),
            UnsupportedActionPort(),
            UnsupportedActionPort(),
        ),
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the stable `controller reconcile` command surface."""
    parser = argparse.ArgumentParser(prog="controller")
    commands = parser.add_subparsers(dest="command", required=True)
    reconcile = commands.add_parser("reconcile", help="run exactly one reconciliation cycle")
    reconcile.add_argument("--dry-run", action="store_true", help="perform no mutation")
    commands.add_parser("recover", help="recover an empty interrupted bootstrap")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run one requested Controller command and emit its typed result."""
    args = parse_args(argv)
    try:
        instance = default_controller()
        if args.command == "recover":
            instance.store.recover_interrupted_bootstrap()
            print(json.dumps({"recovered": "controller_bootstrap_interrupted"}))  # noqa: T201
            return 0
        report = instance.run_cycle(dry_run=args.dry_run)
    except (
        store_module.ControllerActionUnsupported,
        store_module.ControllerLaunchStale,
        store_module.ControllerLockHeld,
        store_module.ControllerStateUnreadable,
        ports.FactCollectionError,
        planning.TrackerError,
    ) as error:
        print(str(error), file=sys.stderr)  # noqa: T201 — CLI refusal is the public interface
        return 2
    print(json.dumps(report.to_document(), indent=2, sort_keys=True))  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
