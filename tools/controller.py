"""One-shot System-of-Work Controller command."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

sys.path.insert(0, str(Path(__file__).parent))

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

    def to_document(self) -> dict[str, object]:
        """Render the stable command result and its explicit empty collections."""
        external_mutations = {
            port_name: (
                not self.dry_run
                and any(action.kind.split(".", 1)[0] == port_name for action in self.actions)
            )
            for port_name in ("tracker", "worktree", "dispatch", "evidence")
        }
        return {
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


@dataclass(frozen=True, slots=True)
class UnsupportedActionPort:
    """Conservative production adapter until an external action is implemented."""

    def apply(self, action: policy.ControlAction) -> None:
        """Refuse instead of pretending an external mutation happened."""
        raise store_module.ControllerActionUnsupportedError(action.kind)


class Controller:
    """Coordinate capability ports around the pure reconciliation policy."""

    def __init__(
        self,
        *,
        fact_collector: ports.FactCollector,
        clock: ports.Clock,
        identity: ports.IdentitySource,
        store: store_module.ControllerStore,
        action_ports: ports.ActionPorts,
    ) -> None:
        """Inject every external capability at the application seam."""
        self.fact_collector = fact_collector
        self.clock = clock
        self.identity = identity
        self.store = store
        self._ports = action_ports

    def run_cycle(self, *, dry_run: bool) -> CycleReport:
        """Collect, reduce, and optionally execute exactly one cycle."""
        fresh_root = self.store.is_fresh()
        if dry_run:
            previous = None if fresh_root else self.store.load()
            return self._cycle(previous, dry_run=True, fresh_root=fresh_root)
        self.store.mark_started()
        with self.store.scheduling_lock():
            previous = None if fresh_root else self.store.load()
            return self._cycle(previous, dry_run=False, fresh_root=fresh_root)

    def _cycle(
        self,
        previous: store_module.LoadedControllerState | None,
        *,
        dry_run: bool,
        fresh_root: bool,
    ) -> CycleReport:
        """Run the policy and, for a real cycle, persist each transition phase."""
        facts = self.fact_collector.collect()
        prior_lifecycle = previous.lifecycle if previous is not None else None
        plan = policy.derive(facts, prior_lifecycle)
        cycle_id = self._cycle_id(previous, fresh_start=fresh_root)
        if dry_run:
            return CycleReport(
                cycle_id=cycle_id,
                facts=facts,
                lifecycle=plan.lifecycle,
                actions=plan.actions,
                dry_run=True,
                journal_written=False,
                state_source="bootstrap" if fresh_root else "replayed",
            )

        payload = self._payload(facts, plan)
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

    def _apply(self, action: policy.ControlAction) -> None:
        """Route a derived action to its narrow external port."""
        port_name = action.kind.split(".", 1)[0]
        try:
            port = getattr(self._ports, port_name)
        except AttributeError as error:
            raise store_module.ControllerActionUnsupported(action.kind) from error
        port.apply(action)

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
    def _payload(facts: policy.ControlFacts, plan: policy.Reconciliation) -> dict[str, object]:
        """Build the persistence payload from independent pure renderers."""
        return {
            "facts": policy.facts_document(facts),
            "lifecycle": policy.lifecycle_document(plan.lifecycle),
            "actions": policy.actions_document(plan.actions),
        }


def default_controller(root: Path | None = None) -> Controller:
    """Build the runnable first-slice controller with conservative adapters."""
    state_root = root or Path(os.environ.get("CTI_CONTROLLER_DIR", DEFAULT_ROOT))
    mutation_ports = tuple(UnsupportedActionPort() for _ in range(4))
    return Controller(
        fact_collector=ports.DefaultFactCollector(),
        clock=ports.SystemClock(),
        identity=ports.SystemIdentity(),
        store=store_module.ControllerStore(state_root),
        action_ports=ports.ActionPorts(*mutation_ports),
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
        store_module.ControllerLockHeld,
        store_module.ControllerStateUnreadable,
    ) as error:
        print(str(error), file=sys.stderr)  # noqa: T201 — CLI refusal is the public interface
        return 2
    print(json.dumps(report.to_document(), indent=2, sort_keys=True))  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
