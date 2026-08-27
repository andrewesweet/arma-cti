"""Fake capability adapters for the controller's external seams."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from conftest import load_tool

if TYPE_CHECKING:
    import pytest

ports = load_tool("controller_ports")
policy = load_tool("controller_policy")
store = load_tool("controller_store")


def test_fake_clock_and_identity_are_deterministic() -> None:
    clock = ports.FakeClock("2026-08-27T12:00:00+00:00")
    identity = ports.FakeIdentity("controller-test")

    assert clock.now() == "2026-08-27T12:00:00+00:00"
    assert clock.now() == clock.now()
    assert identity.identity() == "controller-test"
    assert identity.identity() == identity.identity()


def test_fake_fact_collector_returns_normalized_facts_without_io() -> None:
    facts = policy.ControlFacts(
        configured_curator="curator-1",
        desired_outcomes=(policy.DesiredOutcomeFact("outcome-1", 1, "digest"),),
        initiatives=(),
        work_items=(),
        work_runs=(),
    )
    collector = ports.FakeFactCollector(facts)

    assert collector.collect() == facts
    collector.collect()
    assert collector.collect_calls == 2


def test_recording_ports_expose_writes_as_facts_for_dry_run_assertions() -> None:
    action = policy.ControlAction("publish_initiative", "initiative-1")
    port = ports.RecordingActionPort()

    port.apply(action)

    assert port.applied == [action]


def test_default_fact_collector_explicitly_reports_no_admissible_initiative() -> None:
    facts = ports.DefaultFactCollector().collect()

    assert facts.configured_curator is None
    assert facts.desired_outcomes == ()
    assert facts.initiatives == ()
    assert facts.work_items == ()
    assert facts.work_runs == ()


def test_detached_work_run_port_does_not_use_the_scheduling_lock(tmp_path: Path) -> None:
    lock = store.SchedulingLock(tmp_path / "scheduling.lock")
    port = ports.FakeDetachedWorkRunPort(lock)

    with lock:
        port.start("run-1")

    assert port.started == ["run-1"]
    assert port.scheduling_lock is lock


def test_runtime_collector_translates_queue_holders_and_worktree_debt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base_facts = policy.ControlFacts(
        configured_curator="curator-1",
        desired_outcomes=(policy.DesiredOutcomeFact("outcome-1", 1, "digest"),),
        initiatives=(policy.InitiativeFact("initiative-1", "active"),),
        work_items=(policy.WorkItemFact("item-7", "open", issue=7),),
        work_runs=(policy.WorkRunFact("run-7", "running", work_item_key="item-7", issue=7),),
        wip_limit=3,
    )
    active = ports.queue_policy.Holder(7, ("dispatch:d-7",), tmp_path / "issue-7")
    owed = ports.queue_policy.Holder(
        8, ("worktree:/trees/issue-8",), tmp_path / "issue-8", closed=True
    )
    in_flight = ports.queue_policy.InFlight((active,), (owed,), "read")
    monkeypatch.setattr(ports.queue_policy, "gather", lambda _root, _dispatch: in_flight)

    collected = ports.RuntimeFactCollector(
        ports.FakeFactCollector(base_facts), tmp_path, tmp_path / "dispatches"
    ).collect()

    assert collected.work_runs == base_facts.work_runs
    assert collected.worktree_debt == (
        ports.policy.WorktreeDebtFact(8, str(tmp_path / "issue-8"), work_item_key=None),
    )
    assert collected.wip_limit == 3


def test_runtime_collector_preserves_a_new_dispatch_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facts = policy.ControlFacts(None, (), (), (), (), wip_limit=2)
    active = ports.queue_policy.Holder(7, ("dispatch:d-7",), None)
    in_flight = ports.queue_policy.InFlight((active,), (), "read")
    monkeypatch.setattr(ports.queue_policy, "gather", lambda _root, _dispatch: in_flight)

    collected = ports.RuntimeFactCollector(
        ports.FakeFactCollector(facts), Path("/repo"), Path("/dispatches")
    ).collect()

    assert collected.work_runs == (
        ports.policy.WorkRunFact("d-7", "running", "7", "d-7", None, None, 7),
    )


def test_runtime_collector_exhaustively_matches_a_graph_keyed_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = policy.WorkItemFact("item-7", "open", issue=7)
    facts = policy.ControlFacts(
        None,
        (),
        (),
        (item,),
        (policy.WorkRunFact("old", "running", "item-7"),),
    )
    active = ports.queue_policy.Holder(7, ("dispatch:d-7",), None)
    in_flight = ports.queue_policy.InFlight((active,), (), "read")
    monkeypatch.setattr(ports.queue_policy, "gather", lambda _root, _dispatch: in_flight)

    collected = ports.RuntimeFactCollector(
        ports.FakeFactCollector(facts), Path("/repo"), Path("/dispatches")
    ).collect()

    assert collected.work_runs == facts.work_runs


def test_runtime_collector_exhaustively_matches_an_issue_keyed_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = policy.WorkItemFact("item-7", "open", issue=7)
    run = policy.WorkRunFact("old", "running", issue=7)
    facts = policy.ControlFacts(None, (), (), (item,), (run,))
    active = ports.queue_policy.Holder(7, ("dispatch:d-7",), None)
    in_flight = ports.queue_policy.InFlight((active,), (), "read")
    monkeypatch.setattr(ports.queue_policy, "gather", lambda _root, _dispatch: in_flight)

    collected = ports.RuntimeFactCollector(
        ports.FakeFactCollector(facts), Path("/repo"), Path("/dispatches")
    ).collect()

    assert collected.work_runs == facts.work_runs


def test_runtime_collector_does_not_let_terminal_history_hide_a_live_holder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = policy.WorkItemFact("item-7", "open", issue=7)
    terminal = policy.WorkRunFact("old", "landed", work_item_key="item-7", issue=7)
    facts = policy.ControlFacts(None, (), (), (item,), (terminal,))
    active = ports.queue_policy.Holder(7, ("dispatch:d-7",), None)
    in_flight = ports.queue_policy.InFlight((active,), (), "read")
    monkeypatch.setattr(ports.queue_policy, "gather", lambda _root, _dispatch: in_flight)

    collected = ports.RuntimeFactCollector(
        ports.FakeFactCollector(facts), Path("/repo"), Path("/dispatches")
    ).collect()

    assert collected.work_runs == (
        terminal,
        ports.policy.WorkRunFact("d-7", "running", "item-7", "d-7", None, None, 7),
    )
