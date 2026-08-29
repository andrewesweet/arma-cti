"""Fake capability adapters for the controller's external seams."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from conftest import load_tool

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


def test_dispatch_delivery_collector_reads_typed_candidate_evidence(tmp_path: Path) -> None:
    record = tmp_path / "dispatches" / "d-1"
    record.mkdir(parents=True)
    delivery = {
        "schema": ports.DELIVERY_SCHEMA,
        "work_run": {
            "key": "run-1",
            "state": "gated",
            "work_item_key": "item-1",
            "dispatch_id": "d-1",
            "issue": 1,
            "candidate_sha": "a" * 40,
            "reviewed_sha": "a" * 40,
            "review_status": "cleared",
            "review_dispatch_id": "review-1",
            "adjudication_status": "cleared",
            "gate_sha": "a" * 40,
            "gate_status": "passed",
        },
    }
    (record / "delivery.json").write_text(json.dumps(delivery) + "\n", encoding="utf-8")

    observed = ports.DispatchDeliveryFactCollector(tmp_path / "dispatches").collect(())

    assert observed[0].state == "gated"
    assert observed[0].candidate_sha == "a" * 40
    assert observed[0].issue == 1
    assert observed[0].reviewed_sha == observed[0].gate_sha
    assert observed[0].result_published is False
    assert observed[0].delivery_conflict is False


def test_dispatch_delivery_collector_rejects_delivery_bound_to_another_dispatch(
    tmp_path: Path,
) -> None:
    record = tmp_path / "dispatches" / "d-1"
    record.mkdir(parents=True)
    delivery = {
        "schema": ports.DELIVERY_SCHEMA,
        "work_run": {"key": "run-1", "state": "running", "dispatch_id": "d-2"},
    }
    (record / "delivery.json").write_text(json.dumps(delivery) + "\n", encoding="utf-8")

    with pytest.raises(ports.FactCollectionError, match="delivery dispatch_id"):
        ports.DispatchDeliveryFactCollector(tmp_path / "dispatches").collect(())


def test_dispatch_delivery_collector_ignores_human_output_without_typed_delivery(
    tmp_path: Path,
) -> None:
    record = tmp_path / "dispatches" / "d-1"
    record.mkdir(parents=True)
    (record / "result.json").write_text(
        json.dumps({"stdout": "issue_closed=yes issue=1 sha=" + "a" * 40}) + "\n",
        encoding="utf-8",
    )
    run = policy.WorkRunFact("run-1", "running", "item-1", "d-1", issue=1)

    observed = ports.DispatchDeliveryFactCollector(tmp_path / "dispatches").collect((run,))

    assert observed == (run,)
    assert observed[0].landed_sha is None


@pytest.mark.parametrize(
    ("result", "failure_class"),
    [
        ({"dispatch_id": "d-1", "status": "child_not_launched"}, "infra_unavailable"),
        (
            {
                "dispatch_id": "d-1",
                "status": "harness_failed_after_child",
                "failure_class": "infra_unavailable",
            },
            "untyped_harness_failure",
        ),
        ({"dispatch_id": "d-1", "status": "child_state_unknown"}, "untyped_harness_failure"),
        (
            {"dispatch_id": "d-1", "status": "harness_failed_after_child"},
            "untyped_harness_failure",
        ),
        (
            {"dispatch_id": "d-1", "status": "child_finished", "outcome": "quota_exhausted"},
            "quota_exhausted",
        ),
        (
            {"dispatch_id": "d-1", "status": "child_finished", "outcome": "provider_error"},
            "infra_unavailable",
        ),
        (
            {"dispatch_id": "d-1", "status": "child_finished", "outcome": "provider_refused"},
            "provider_refused",
        ),
        (
            {"dispatch_id": "d-1", "terminal_state": {"state": "stopped"}},
            "interrupted",
        ),
    ],
)
def test_dispatch_delivery_collector_normalizes_typed_result_non_results(
    tmp_path: Path, result: dict[str, object], failure_class: str
) -> None:
    record = tmp_path / "dispatches" / "d-1"
    record.mkdir(parents=True)
    (record / "result.json").write_text(json.dumps(result) + "\n", encoding="utf-8")
    run = policy.WorkRunFact("run-1", "running", "item-1", "d-1", issue=1)

    observed = ports.DispatchDeliveryFactCollector(tmp_path / "dispatches").collect((run,))

    assert observed[0].state == "non_result"
    assert observed[0].failure_class == failure_class
    assert observed[0].result_published is True


def test_a_published_non_result_keeps_the_binding_it_merged_over(tmp_path: Path) -> None:
    """The bound prior run's identity survives the merge with the stripped result.

    The slot the run holds is released only through that binding: `issue` and
    `work_item_key` stay, `result_published` records the terminal outcome, and
    no recovery verdict is invented for a run that already published one.
    """
    record = tmp_path / "dispatches" / "d-1"
    record.mkdir(parents=True)
    (record / "result.json").write_text(
        json.dumps({"dispatch_id": "d-1", "status": "child_finished", "outcome": "quota_exhausted"})
        + "\n",
        encoding="utf-8",
    )
    bound = policy.WorkRunFact("run-1", "running", "item-1", "d-1", issue=1)

    observed = ports.DispatchDeliveryFactCollector(tmp_path / "dispatches").collect((bound,))

    assert observed[0].state == "non_result"
    assert observed[0].failure_class == "quota_exhausted"
    assert observed[0].work_item_key == "item-1"
    assert observed[0].issue == 1
    assert observed[0].result_published is True
    assert observed[0].recovery_kind is None


def test_dispatch_delivery_collector_rejects_malformed_typed_result_fields(tmp_path: Path) -> None:
    record = tmp_path / "dispatches" / "d-1"
    record.mkdir(parents=True)
    (record / "result.json").write_text(
        json.dumps({"dispatch_id": "d-1", "status": 1}) + "\n", encoding="utf-8"
    )

    with pytest.raises(ports.FactCollectionError, match="result status"):
        ports.DispatchDeliveryFactCollector(tmp_path / "dispatches").collect(())


def test_dispatch_delivery_collector_reads_the_dispatcher_s_empty_failure_class(
    tmp_path: Path,
) -> None:
    """`Refusal.failure_class` defaults to "" for a dirty-tree style refusal."""
    record = tmp_path / "dispatches" / "d-1"
    record.mkdir(parents=True)
    (record / "result.json").write_text(
        json.dumps(
            {
                "dispatch_id": "d-1",
                "status": "child_not_launched",
                "refusal": "dirty_tree",
                "failure_class": "",
                "ended_at": "2026-08-28T12:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    observed = ports.DispatchDeliveryFactCollector(tmp_path / "dispatches").collect(())

    assert observed[0].state == policy.NON_RESULT
    assert observed[0].failure_class == "infra_unavailable"


def test_dispatch_delivery_collector_rejects_a_result_bound_to_another_dispatch(
    tmp_path: Path,
) -> None:
    record = tmp_path / "dispatches" / "d-1"
    record.mkdir(parents=True)
    (record / "result.json").write_text(
        json.dumps({"dispatch_id": "d-2", "status": "child_not_launched"}) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ports.FactCollectionError, match="result dispatch_id"):
        ports.DispatchDeliveryFactCollector(tmp_path / "dispatches").collect(())


def test_dispatch_delivery_collector_does_not_treat_another_terminal_state_as_stop(
    tmp_path: Path,
) -> None:
    record = tmp_path / "dispatches" / "d-1"
    record.mkdir(parents=True)
    (record / "result.json").write_text(
        json.dumps({"dispatch_id": "d-1", "terminal_state": {"state": "running"}}) + "\n",
        encoding="utf-8",
    )
    run = policy.WorkRunFact("run-1", "running", "item-1", "d-1", issue=1)

    assert ports.DispatchDeliveryFactCollector(tmp_path / "dispatches").collect((run,)) == (run,)


def test_dispatch_delivery_collector_rejects_nested_delivery_bound_to_another_dispatch(
    tmp_path: Path,
) -> None:
    record = tmp_path / "dispatches" / "d-1"
    record.mkdir(parents=True)
    (record / "result.json").write_text(
        json.dumps(
            {
                "dispatch_id": "d-1",
                "delivery": {"key": "run-1", "state": "running", "dispatch_id": "d-2"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ports.FactCollectionError, match="delivery dispatch_id"):
        ports.DispatchDeliveryFactCollector(tmp_path / "dispatches").collect(())


def test_dispatch_delivery_collector_rejects_nested_delivery_with_result_identity_mismatch(
    tmp_path: Path,
) -> None:
    record = tmp_path / "dispatches" / "d-1"
    record.mkdir(parents=True)
    (record / "result.json").write_text(
        json.dumps(
            {
                "dispatch_id": "d-2",
                "delivery": {"key": "run-1", "state": "running", "dispatch_id": "d-1"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ports.FactCollectionError, match="result dispatch_id"):
        ports.DispatchDeliveryFactCollector(tmp_path / "dispatches").collect(())


def test_dispatch_delivery_collector_rejects_unknown_fact_fields(tmp_path: Path) -> None:
    record = tmp_path / "dispatches" / "d-1"
    record.mkdir(parents=True)
    delivery = {
        "schema": ports.DELIVERY_SCHEMA,
        "work_run": {"key": "run-1", "state": "running", "dispatch_id": "d-1", "extra": True},
    }
    (record / "delivery.json").write_text(json.dumps(delivery) + "\n", encoding="utf-8")

    with pytest.raises(ports.FactCollectionError, match="work_runs entry"):
        ports.DispatchDeliveryFactCollector(tmp_path / "dispatches").collect(())


@pytest.mark.parametrize(
    "field_value", [{"key": 1, "state": "running"}, {"key": "run-1", "state": 1}]
)
def test_dispatch_delivery_collector_rejects_non_text_fact_identity(
    tmp_path: Path, field_value: dict[str, object]
) -> None:
    record = tmp_path / "dispatches" / "d-1"
    record.mkdir(parents=True)
    delivery = {
        "schema": ports.DELIVERY_SCHEMA,
        "work_run": {**field_value, "dispatch_id": "d-1"},
    }
    (record / "delivery.json").write_text(json.dumps(delivery) + "\n", encoding="utf-8")

    with pytest.raises(ports.FactCollectionError, match="work_runs value"):
        ports.DispatchDeliveryFactCollector(tmp_path / "dispatches").collect(())


def test_dispatch_delivery_collector_uses_stop_closeout_shape_for_legacy_records(
    tmp_path: Path,
) -> None:
    record = tmp_path / "dispatches" / "d-1"
    record.mkdir(parents=True)
    (record / "result.json").write_text(
        json.dumps({"dispatch_id": "d-1", "stopped_by": "just dispatch --stop"}) + "\n",
        encoding="utf-8",
    )

    observed = ports.DispatchDeliveryFactCollector(tmp_path / "dispatches").collect(())

    assert observed[0].state == "non_result"
    assert observed[0].failure_class == "interrupted"


def test_dispatch_delivery_collector_composes_recovery_before_relaunch(
    tmp_path: Path,
) -> None:
    record = tmp_path / "dispatches" / "d-1"
    record.mkdir(parents=True)
    (record / "dispatch.json").write_text('{"dispatch_id":"d-1","issue":1}\n', encoding="utf-8")
    calls: list[str] = []

    class Recovery:
        def classify(self, run: Any) -> str:  # noqa: ANN401 — dynamic policy module
            calls.append(run.dispatch_id)
            return "lost_work"

    run = policy.WorkRunFact("run-1", "running", "item-1", "d-1", issue=1)
    observed = ports.DispatchDeliveryFactCollector(
        tmp_path / "dispatches", recovery=Recovery()
    ).collect((run,))

    assert calls == ["d-1"]
    assert observed[0].state == "non_result"
    assert observed[0].failure_class == "interrupted"
    assert observed[0].recovery_kind == "lost_work"
    assert (
        ports.policy.live_work_runs(policy.ControlFacts(None, (), (), (), observed, wip_limit=1))
        == ()
    )
