"""Behavioural seams for the first System-of-Work Controller slice."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from conftest import load_tool

if TYPE_CHECKING:
    from collections.abc import Callable

controller = load_tool("controller")
policy = load_tool("controller_policy")
ports = load_tool("controller_ports")
store_module = load_tool("controller_store")

REPO = Path(__file__).resolve().parents[2]


def empty_facts() -> Any:  # noqa: ANN401 — tools are loaded dynamically by the test harness
    """Return the conservative current picture used by the first slice."""
    return policy.ControlFacts(
        configured_curator=None,
        desired_outcomes=(),
        initiatives=(),
        work_items=(),
        work_runs=(),
    )


def make_controller(
    root: Path,
    *,
    facts: Any | None = None,  # noqa: ANN401 — tools are loaded dynamically by the test harness
    clock_value: str = "2026-08-27T12:00:00+00:00",
    identity_value: str = "test-controller",
) -> tuple[Any, Any, Any, tuple[Any, ...]]:
    """Assemble one controller with deterministic capabilities and recording ports."""
    collector = ports.FakeFactCollector(facts or empty_facts())
    clock = ports.FakeClock(clock_value)
    identity = ports.FakeIdentity(identity_value)
    store = store_module.ControllerStore(root)
    mutation_ports = tuple(ports.RecordingActionPort() for _ in range(4))
    instance = controller.Controller(
        fact_collector=collector,
        clock=clock,
        identity=identity,
        store=store,
        action_ports=ports.ActionPorts(*mutation_ports),
    )
    return instance, store, collector, mutation_ports


def test_one_cycle_reports_facts_state_and_an_explicit_empty_action_list(tmp_path: Path) -> None:
    instance, _store, collector, _mutation_ports = make_controller(tmp_path / "controller")

    report = instance.run_cycle(dry_run=True)

    assert collector.collect_calls == 1
    document = report.to_document()
    assert document["control_facts"] == {
        "configured_curator": None,
        "desired_outcomes": [],
        "initiatives": [],
        "work_items": [],
        "work_runs": [],
    }
    assert document["lifecycle"] == {
        "state": "no_admissible_initiative",
        "admitted_initiative": None,
        "reason": "no_product_curator_configured",
    }
    assert document["control_actions"] == []
    assert document["dry_run"] is True


def test_controller_slice_stays_outside_the_campaign_commander_runtime() -> None:
    """The first controller slice is tooling, not an in-game runtime feature."""
    tooling_modules = {path.name for path in (REPO / "tools").glob("controller*.py")}
    assert tooling_modules == {
        "controller.py",
        "controller_policy.py",
        "controller_ports.py",
        "controller_store.py",
    }
    assert not list((REPO / "src" / "cti_daemon").glob("controller*.py"))


def test_dry_run_writes_no_controller_or_external_state(tmp_path: Path) -> None:
    root = tmp_path / "controller"
    instance, store, _collector, mutation_ports = make_controller(root)

    report = instance.run_cycle(dry_run=True)

    assert report.journal_written is False
    assert not root.exists()
    assert not store.journal_path.exists()
    assert not store.view_path.exists()
    assert not store.started_marker_path.exists()
    assert all(port.applied == [] for port in mutation_ports)


def test_default_controller_refuses_unimplemented_actions_before_claiming_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    action = controller.policy.ControlAction("tracker.record", "outcome-1")
    lifecycle = controller.policy.LifecycleState(policy.NO_ADMISSIBLE_INITIATIVE, None, "reason")
    plan = controller.policy.Reconciliation(lifecycle=lifecycle, actions=(action,))
    monkeypatch.setattr(controller.policy, "derive", lambda _facts, _previous=None: plan)

    root = tmp_path / "controller"
    instance = controller.default_controller(root)

    with pytest.raises(
        controller.store_module.ControllerActionUnsupportedError,
        match=r"^refusal=controller_action_unsupported action=tracker\.record$",
    ):
        instance.run_cycle(dry_run=False)

    rows = [
        json.loads(line)
        for line in instance.store.journal_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [row["phase"] for row in rows] == ["planned"]


def test_confirmed_phase_attests_applied_plan_without_recollecting_or_rederiving(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    action = controller.policy.ControlAction("tracker.record", "outcome-1")
    lifecycle = controller.policy.LifecycleState(policy.NO_ADMISSIBLE_INITIATIVE, None, "reason")
    plan = controller.policy.Reconciliation(lifecycle=lifecycle, actions=(action,))
    derive_calls: list[tuple[Any, Any]] = []

    def derive(facts: Any, previous: Any = None) -> Any:  # noqa: ANN401 — dynamically loaded policy
        derive_calls.append((facts, previous))
        return plan

    monkeypatch.setattr(controller.policy, "derive", derive)
    instance, store, collector, mutation_ports = make_controller(tmp_path / "controller")

    report = instance.run_cycle(dry_run=False)
    rows = [
        json.loads(line) for line in store.journal_path.read_text(encoding="utf-8").splitlines()
    ]

    assert report.actions == (action,)
    assert collector.collect_calls == 1
    assert len(derive_calls) == 1
    assert [row["payload"] for row in rows] == [rows[0]["payload"]] * 3
    assert mutation_ports[0].applied == [action]


def test_report_marks_all_external_mutations_only_for_a_real_action_plan() -> None:
    """A dry run stays non-mutating even when a future policy supplies actions."""
    action = controller.policy.ControlAction("tracker.record.detail", "outcome-1")
    lifecycle = controller.policy.LifecycleState(policy.NO_ADMISSIBLE_INITIATIVE, None, "reason")

    dry_report = controller.CycleReport(
        cycle_id="cycle-1",
        facts=empty_facts(),
        lifecycle=lifecycle,
        actions=(action,),
        dry_run=True,
        journal_written=False,
        state_source="bootstrap",
    )
    real_report = controller.CycleReport(
        cycle_id="cycle-1",
        facts=empty_facts(),
        lifecycle=lifecycle,
        actions=(action,),
        dry_run=False,
        journal_written=True,
        state_source="bootstrap",
    )

    assert dry_report.to_document()["mutations"] == {
        "tracker": False,
        "worktree": False,
        "dispatch": False,
        "journal": False,
        "evidence": False,
    }
    assert real_report.to_document()["mutations"] == {
        "tracker": True,
        "worktree": False,
        "dispatch": False,
        "journal": True,
        "evidence": False,
    }


def test_dry_run_does_not_bypass_an_existing_but_unreadable_state_root(tmp_path: Path) -> None:
    root = tmp_path / "controller"
    root.mkdir()
    store_module.ControllerStore(root).mark_started()
    instance, _store, _collector, _mutation_ports = make_controller(root)

    with pytest.raises(store_module.ControllerStateUnreadable) as error:
        instance.run_cycle(dry_run=True)
    assert error.value.reason == "controller_bootstrap_interrupted"


def test_cli_reconcile_dry_run_is_one_cycle_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "controller"
    monkeypatch.setenv("CTI_CONTROLLER_DIR", str(root))

    assert controller.main(["reconcile", "--dry-run"]) == 0

    output = json.loads(capfd.readouterr().out)
    assert output["control_actions"] == []
    assert output["dry_run"] is True
    assert output["journal_written"] is False
    assert not root.exists()


def test_cli_recover_names_empty_interrupted_bootstrap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "controller"
    store_module.ControllerStore(root).mark_started()
    monkeypatch.setenv("CTI_CONTROLLER_DIR", str(root))

    assert controller.main(["recover"]) == 0

    assert json.loads(capfd.readouterr().out) == {"recovered": "controller_bootstrap_interrupted"}
    assert not store_module.ControllerStore(root).started_marker_path.exists()


def test_real_cycle_records_three_phases_and_replays_without_new_actions(tmp_path: Path) -> None:
    instance, store, collector, _mutation_ports = make_controller(tmp_path / "controller")

    first = instance.run_cycle(dry_run=False)
    second = instance.run_cycle(dry_run=False)

    assert first.journal_written is True
    assert first.cycle_id == "test-controller-cycle-1"
    assert second.cycle_id == "test-controller-cycle-2"
    assert second.to_document()["control_actions"] == []
    assert collector.collect_calls == 2
    rows = [
        json.loads(line) for line in store.journal_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [row["phase"] for row in rows] == [
        "planned",
        "applied",
        "confirmed",
        "planned",
        "applied",
        "confirmed",
    ]
    loaded = store.load()
    assert loaded.confirmed["lifecycle"]["state"] == "no_admissible_initiative"
    assert loaded.confirmed["actions"] == []
    assert store.view_path.exists()
    assert store.started_marker_path.exists()
    assert not list(store.root.glob("*.tmp"))


def test_same_facts_and_valid_journal_have_same_derived_state_and_no_extra_action(
    tmp_path: Path,
) -> None:
    instance, store, _collector, _mutation_ports = make_controller(tmp_path / "controller")
    first = instance.run_cycle(dry_run=False)
    first_rows = [
        json.loads(line) for line in store.journal_path.read_text(encoding="utf-8").splitlines()
    ]

    second = instance.run_cycle(dry_run=False)
    second_rows = [
        json.loads(line) for line in store.journal_path.read_text(encoding="utf-8").splitlines()
    ]

    def logical_actions(rows: list[Any]) -> list[tuple[str, str]]:
        return [
            (action["kind"], action["logical_key"])
            for row in rows
            for action in row["payload"]["actions"]
        ]

    assert second.lifecycle == first.lifecycle
    assert second.actions == first.actions == ()
    assert len(second_rows) == len(first_rows) + len(store_module.PHASES)
    assert logical_actions(second_rows) == logical_actions(first_rows) == []


def test_second_scheduling_writer_is_refused_but_detached_work_run_is_unaffected(
    tmp_path: Path,
) -> None:
    lock_path = tmp_path / "controller" / "scheduling.lock"
    first = store_module.SchedulingLock(lock_path)
    second = store_module.SchedulingLock(lock_path)
    detached = ports.FakeDetachedWorkRunPort(first)

    first.acquire()
    try:
        with pytest.raises(store_module.ControllerLockHeld, match="refusal=controller_lock_held"):
            second.acquire()
        detached.start("work-run-1")
    finally:
        first.release()

    assert detached.started == ["work-run-1"]


@pytest.mark.parametrize(
    ("name", "arrange", "expected_reason"),
    [
        ("absent journal", lambda root: root.mkdir(), "journal_unreadable:"),
        ("empty journal", lambda root: _write(root, ""), "journal_empty"),
        (
            "truncated final record",
            lambda root: _write(root, '{"schema":"controller-journal/v1"'),
            "journal_final_record_truncated",
        ),
        ("damaged JSON", lambda root: _write(root, "not-json\n"), "journal_invalid_json:1:"),
        (
            "unknown schema",
            lambda root: _write(
                root,
                json.dumps({**_record("c", "planned"), "schema": "controller-journal/v999"}) + "\n",
            ),
            "journal_unknown_schema:1",
        ),
        (
            "planned but not applied",
            lambda root: _write(root, json.dumps(_record("c", "planned")) + "\n"),
            "journal_incomplete_cycle",
        ),
        (
            "wrong phase sequence",
            lambda root: _write(
                root,
                "".join(
                    json.dumps(_record("c", phase)) + "\n"
                    for phase in ("planned", "confirmed", "applied")
                ),
            ),
            "journal_phase_sequence:1",
        ),
        (
            "duplicate cycle",
            lambda root: _write(
                root,
                "".join(
                    json.dumps(_record("c", phase)) + "\n"
                    for phase in ("planned", "applied", "confirmed") * 2
                ),
            ),
            "journal_duplicate_cycle",
        ),
        (
            "last transition unconfirmed",
            lambda root: _write(
                root,
                "".join(
                    json.dumps(_record("c", phase)) + "\n"
                    for phase in ("planned", "applied", "applied")
                ),
            ),
            "journal_last_transition_unconfirmed",
        ),
    ],
)
def test_every_incomplete_or_damaged_local_shape_refuses_by_name(
    tmp_path: Path,
    name: str,
    arrange: Callable[[Path], None],
    expected_reason: str,
) -> None:
    root = tmp_path / "controller"
    arrange(root)

    with pytest.raises(store_module.ControllerStateUnreadable) as error:
        store_module.ControllerStore(root).load()

    assert error.value.reason.startswith(expected_reason), name


def test_materialized_view_disagreement_refuses_instead_of_trusting_either_side(
    tmp_path: Path,
) -> None:
    root = tmp_path / "controller"
    store = store_module.ControllerStore(root)
    payload = {
        "facts": policy.facts_document(empty_facts()),
        "lifecycle": {
            "state": "no_admissible_initiative",
            "admitted_initiative": None,
            "reason": "no_product_curator_configured",
        },
        "actions": [],
    }
    store.write_cycle(
        "cycle-1",
        payload,
        recorded_at="2026-08-27T12:00:00+00:00",
        recorded_by="test-controller",
    )
    view = json.loads(store.view_path.read_text(encoding="utf-8"))
    view["confirmed"]["actions"] = [{"kind": "unexpected"}]
    store.view_path.write_text(json.dumps(view) + "\n", encoding="utf-8")

    with pytest.raises(
        store_module.ControllerStateUnreadable, match="refusal=controller_state_unreadable"
    ):
        store.load()


def _write(root: Path, content: str) -> None:
    """Arrange raw local state without hiding the damaged bytes behind a helper."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "journal.jsonl").write_text(content, encoding="utf-8")


def _record(cycle_id: str, phase: str) -> dict[str, object]:
    """Build one valid journal record for sequence-only refusal cases."""
    return {
        "schema": store_module.JOURNAL_SCHEMA,
        "cycle_id": cycle_id,
        "phase": phase,
        "recorded_at": "2026-08-27T12:00:00+00:00",
        "recorded_by": "test-controller",
        "payload": {
            "facts": policy.facts_document(empty_facts()),
            "lifecycle": {
                "state": policy.NO_ADMISSIBLE_INITIATIVE,
                "admitted_initiative": None,
                "reason": "no_product_curator_configured",
            },
            "actions": [],
        },
    }
