"""Fake capability adapters for the controller's external seams."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
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
    """A released run is terminal history; a live holder must still be counted.

    `quota_exhausted` with a published result is a release disjunct of
    `work_run_owns_slot`, so the run owns no slot and the holder's dispatch is
    appended rather than matched away — an unevidenced `landed` state would not
    do, because #671's capacity rule holds that slot (#690).
    """
    item = policy.WorkItemFact("item-7", "open", issue=7)
    terminal = policy.WorkRunFact(
        "old",
        "non_result",
        work_item_key="item-7",
        issue=7,
        failure_class="quota_exhausted",
        result_published=True,
    )
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


@pytest.mark.parametrize(
    ("state", "extra"),
    [
        ("possessed", {}),  # a state no vocabulary recognises holds the slot
        ("landed", {}),  # landed-stated without a landing SHA holds it too
        ("non_result", {"failure_class": "interrupted"}),  # live non-result
    ],
)
def test_runtime_collector_matches_a_holder_behind_any_live_run(
    monkeypatch: pytest.MonkeyPatch, state: str, extra: dict[str, object]
) -> None:
    """One liveness rule for capacity and holder matching alike (#690).

    Under the old second vocabulary these runs failed to match their holder, so
    a synthetic `running` run was appended beside them and one Work Item took
    two slots.
    """
    item = policy.WorkItemFact("item-7", "open", issue=7)
    run = policy.WorkRunFact("old", state, work_item_key="item-7", issue=7, **extra)  # type: ignore[arg-type]
    facts = policy.ControlFacts(None, (), (), (item,), (run,))
    active = ports.queue_policy.Holder(7, ("dispatch:d-7",), None)
    in_flight = ports.queue_policy.InFlight((active,), (), "read")
    monkeypatch.setattr(ports.queue_policy, "gather", lambda _root, _dispatch: in_flight)

    collected = ports.RuntimeFactCollector(
        ports.FakeFactCollector(facts), Path("/repo"), Path("/dispatches")
    ).collect()

    assert collected.work_runs == facts.work_runs
    assert len(policy.live_work_runs(collected)) == 1


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


def test_standalone_delivery_conflict_survives_landing_claim_clear(tmp_path: Path) -> None:
    """Compute identity conflicts before clearing standalone landing authority.

    The existing delivery tests use one SHA for every identity field, so they
    cannot observe the conflict disappearing when ``landed_sha`` is cleared.
    """
    record = tmp_path / "dispatches" / "d-1"
    record.mkdir(parents=True)
    candidate = "a" * 40
    delivery = {
        "schema": ports.DELIVERY_SCHEMA,
        "work_run": {
            "key": "run-1",
            "state": "landed",
            "work_item_key": "item-1",
            "dispatch_id": "d-1",
            "candidate_sha": candidate,
            "reviewed_sha": candidate,
            "review_status": "cleared",
            "review_dispatch_id": "review-1",
            "adjudication_sha": candidate,
            "adjudication_status": "cleared",
            "gate_sha": candidate,
            "gate_status": "passed",
            "landed_sha": "b" * 40,
            "close_evidence_sha": candidate,
        },
    }
    (record / "delivery.json").write_text(json.dumps(delivery) + "\n", encoding="utf-8")

    observed = ports.DispatchDeliveryFactCollector(tmp_path / "dispatches").collect(())

    assert observed[0].landed_sha is None
    assert observed[0].delivery_conflict is True


def test_standalone_delivery_cannot_publish_a_result_or_release_a_slot(tmp_path: Path) -> None:
    record = tmp_path / "dispatches" / "d-1"
    record.mkdir(parents=True)
    delivery = {
        "schema": ports.DELIVERY_SCHEMA,
        "work_run": {
            "key": "run-1",
            "state": "non_result",
            "work_item_key": "item-1",
            "dispatch_id": "d-1",
            "failure_class": "quota_exhausted",
            "result_published": True,
        },
    }
    (record / "delivery.json").write_text(json.dumps(delivery) + "\n", encoding="utf-8")

    observed = ports.DispatchDeliveryFactCollector(tmp_path / "dispatches").collect(())
    facts = policy.ControlFacts(None, (), (), (), observed, wip_limit=1)

    assert observed[0].result_published is False
    assert policy.live_work_runs(facts) == observed


@pytest.mark.parametrize("state", ["landed", "non_result", "unrecognized"])
def test_standalone_delivery_state_cannot_release_a_slot(tmp_path: Path, state: str) -> None:
    record = tmp_path / "dispatches" / "d-1"
    record.mkdir(parents=True)
    delivery = {
        "schema": ports.DELIVERY_SCHEMA,
        "work_run": {
            "key": "run-1",
            "state": state,
            "work_item_key": "item-1",
            "dispatch_id": "d-1",
        },
    }
    (record / "delivery.json").write_text(json.dumps(delivery) + "\n", encoding="utf-8")

    observed = ports.DispatchDeliveryFactCollector(tmp_path / "dispatches").collect(())
    facts = policy.ControlFacts(None, (), (), (), observed, wip_limit=1)

    assert observed[0].state == state
    assert observed[0].landed_sha is None
    assert observed[0].failure_class is None
    assert observed[0].recovery_kind is None
    assert policy.live_work_runs(facts) == observed


def test_standalone_delivery_recovery_claim_cannot_release_a_slot(tmp_path: Path) -> None:
    record = tmp_path / "dispatches" / "d-1"
    record.mkdir(parents=True)
    delivery = {
        "schema": ports.DELIVERY_SCHEMA,
        "work_run": {
            "key": "run-1",
            "state": "non_result",
            "work_item_key": "item-1",
            "dispatch_id": "d-1",
            "failure_class": "quota_exhausted",
            "recovery_kind": "lost_work",
        },
    }
    (record / "delivery.json").write_text(json.dumps(delivery) + "\n", encoding="utf-8")

    observed = ports.DispatchDeliveryFactCollector(tmp_path / "dispatches").collect(())
    facts = policy.ControlFacts(None, (), (), (), observed, wip_limit=1)

    assert observed[0].recovery_kind is None
    assert policy.live_work_runs(facts) == observed


def test_standalone_delivery_landing_claim_cannot_release_a_slot(tmp_path: Path) -> None:
    record = tmp_path / "dispatches" / "d-1"
    record.mkdir(parents=True)
    sha = "a" * 40
    delivery = {
        "schema": ports.DELIVERY_SCHEMA,
        "work_run": {
            "key": "run-1",
            "state": "running",
            "work_item_key": "item-1",
            "dispatch_id": "d-1",
            "issue": 1,
            "candidate_sha": sha,
            "reviewed_sha": sha,
            "review_status": "cleared",
            "review_dispatch_id": "review-1",
            "adjudication_sha": sha,
            "adjudication_status": "cleared",
            "gate_sha": sha,
            "gate_status": "passed",
            "landed_sha": sha,
            "close_evidence_sha": sha,
        },
    }
    (record / "delivery.json").write_text(json.dumps(delivery) + "\n", encoding="utf-8")

    observed = ports.DispatchDeliveryFactCollector(tmp_path / "dispatches").collect(())
    facts = policy.ControlFacts(None, (), (), (), observed, wip_limit=1)

    assert observed[0].landed_sha is None
    assert observed[0].state == "gated"
    assert policy.live_work_runs(facts) == observed


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


def test_dispatch_delivery_collector_releases_a_terminal_recovery_over_a_foreign_class(
    tmp_path: Path,
) -> None:
    """The #690 sequence end to end: a typed delivery class survives recovery's
    preserve-existing branch (`or "interrupted"` never fires), so the slot must
    release on the verdict alone — a class outside `NON_RESULT_CLASSES` is a
    record of what the delivery typed, not evidence the run is alive."""
    record = tmp_path / "dispatches" / "d-1"
    record.mkdir(parents=True)
    delivery = {
        "schema": ports.DELIVERY_SCHEMA,
        "work_run": {
            "key": "run-1",
            "state": "running",
            "dispatch_id": "d-1",
            "failure_class": "assertion_failed",
        },
    }
    (record / "delivery.json").write_text(json.dumps(delivery) + "\n", encoding="utf-8")

    class Recovery:
        def classify(self, _run: Any) -> str:  # noqa: ANN401 — dynamic policy module
            return "lost_work"

    observed = ports.DispatchDeliveryFactCollector(
        tmp_path / "dispatches", recovery=Recovery()
    ).collect(())

    assert observed[0].state == policy.NON_RESULT
    assert observed[0].failure_class == "assertion_failed"
    assert observed[0].recovery_kind == "lost_work"
    assert (
        ports.policy.live_work_runs(policy.ControlFacts(None, (), (), (), observed, wip_limit=1))
        == ()
    )


def _git(*argv: str, cwd: Path) -> None:
    subprocess.run(["git", *argv], cwd=cwd, check=True, capture_output=True)  # noqa: S603, S607 — fixed argv, PATH git as everywhere in tools/


def _dispatch_record(tmp_path: Path) -> None:
    """Stage one dispatch record over `d-1`, the shape a recovery look needs to find."""
    record = tmp_path / "dispatches" / "d-1"
    record.mkdir(parents=True)
    (record / "dispatch.json").write_text(
        json.dumps(
            {
                "dispatch_id": "d-1",
                "issue": 1,
                "planned_at": datetime.now(tz=UTC).isoformat(),
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _worktree_repo(tmp_path: Path) -> tuple[Path, Path]:
    """Stage a repository with one detached worktree under it, as every agent test does."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git("init", "-b", "main", cwd=repo)
    _git("config", "user.email", "test@example.com", cwd=repo)
    _git("config", "user.name", "Test", cwd=repo)
    _git("commit", "--allow-empty", "-m", "base", cwd=repo)
    _git("update-ref", "refs/remotes/origin/main", "HEAD", cwd=repo)
    _git("worktree", "add", "--detach", ".claude/worktrees/d-1", "HEAD", cwd=repo)
    return repo, repo / ".claude/worktrees/d-1"


def _controller_classifier(
    tmp_path: Path, repo: Path, machine: ports.dispatch_stop.Machine
) -> ports.DispatchDeliveryFactCollector:
    dispatches = tmp_path / "dispatches" / "d-1"
    dispatches.mkdir(parents=True, exist_ok=True)
    classifier = ports.ExistingRecoveryClassifier(
        repo, tmp_path / "watch", dispatches.parent, machine=machine
    )
    return ports.DispatchDeliveryFactCollector(dispatches.parent, recovery=classifier)


def _real_recovery_arrangement(
    tmp_path: Path,
) -> tuple[Path, Path, ports.DispatchDeliveryFactCollector, policy.WorkRunFact]:
    """Stage one real recovery arrangement shared by both process-backed tests."""
    repo, tree = _worktree_repo(tmp_path)
    _dispatch_record(tmp_path)
    classifier = ports.ExistingRecoveryClassifier(repo, tmp_path / "watch", tmp_path / "dispatches")
    collector = ports.DispatchDeliveryFactCollector(tmp_path / "dispatches", recovery=classifier)
    run = policy.WorkRunFact("run-1", "running", "item-1", "d-1", issue=1)
    return repo, tree, collector, run


def _start_real_agent(tree: Path) -> subprocess.Popen[bytes]:
    """Start a fixed-command process whose cwd is the staged worktree."""
    return subprocess.Popen(
        ["/bin/sleep", "30"],
        cwd=tree,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _plant(
    tmp_path: Path,
    pid: int,
    tree: Path,
    *,
    unreadable: bool = False,
    deleted: bool = False,
) -> ports.dispatch_stop.Machine:
    """Stage a fake `/proc` whose `pid` reports `tree` as its working directory.

    `unreadable` makes the `cwd` link a regular file, which is the stand-in for a
    `readlink` that fails for any reason other than a process already gone: the
    errno, not the empty result, is what the scan must carry (#625's cap ruling).
    """
    entry = tmp_path / "proc" / str(pid)
    entry.mkdir(parents=True)
    if unreadable:
        (entry / "cwd").write_text("", encoding="utf-8")
    elif deleted:
        (entry / "cwd").symlink_to(f"{tree.resolve()} (deleted)")
    else:
        (entry / "cwd").symlink_to(tree.resolve())
    return ports.dispatch_stop.Machine(procfs=tmp_path / "proc", self_pid=1)


# quarantined: #687
# Baseline 2026-09-03: target alone, serial (-n0), 200 runs, 0 reds; target module alone,
# xdist parallel (worksteal, -n auto), 50 runs, 0 reds; full `just unit`, xdist parallel
# (worksteal, -n auto) plus Rust, 10 runs, 0 reds. Box had 12 CPUs; load averages at
# block starts were 1.43/1.40/1.82, 2.09/1.64/1.85 and 20.71/10.18/5.08. Contention
# varied and was high during the full-tier block. Not reproduced; no cause demonstrated.
# Failure class: flake_quarantine.
def test_a_healthy_dispatch_that_dies_before_the_next_cycle_resolves(tmp_path: Path) -> None:
    """The #625 sequence, through the real classifier: healthy at cycle N, dead at N+1.

    The agent is a process working in the tree, so its death is an observed
    fact — the fake `/proc` entry is removed between the cycles — and not a
    story told about an unpushed commit.  The commit is staged too, because
    `lost_work` is the verdict that reads it; the empty scan is what carries
    the claim that nobody is coming back for it.
    """
    _, tree, collector, run = _real_recovery_arrangement(tmp_path)
    worker = _start_real_agent(tree)
    try:
        healthy = collector.collect((run,))[0]
        worker.kill()
        worker.wait()
        _git("commit", "--allow-empty", "-m", "unpushed", cwd=tree)
        resolved = collector.collect((healthy,))[0]
    finally:
        if worker.poll() is None:
            worker.kill()
        worker.wait()

    assert healthy.state == "running"
    assert healthy.recovery_kind == "still_live"
    assert resolved.state == policy.NON_RESULT
    assert resolved.failure_class == "interrupted"
    assert resolved.recovery_kind == "lost_work"
    assert (
        ports.policy.live_work_runs(policy.ControlFacts(None, (), (), (), (resolved,), wip_limit=1))
        == ()
    )


def test_a_live_agent_making_progress_is_never_concluded_lost(tmp_path: Path) -> None:
    """Unpushed commits are also what a live agent's ordinary progress looks like.

    Round two's High: `recovery.py` reads `tree.ahead` before anything else and
    says itself that it cannot tell whether the agent is alive, so concluding
    `lost_work` from the commit alone would release the slot under a running
    agent and invite a duplicate dispatch.  The process is still in the tree,
    so the look reads `still_live` and the run keeps everything it had.
    """
    _, tree, collector, run = _real_recovery_arrangement(tmp_path)
    worker = _start_real_agent(tree)
    try:
        healthy = collector.collect((run,))[0]
        _git("commit", "--allow-empty", "-m", "unpushed", cwd=tree)
        progressed = collector.collect((healthy,))[0]
    finally:
        if worker.poll() is None:
            worker.kill()
        worker.wait()

    assert healthy.recovery_kind == "still_live"
    assert progressed.state == "running"
    assert progressed.recovery_kind == "still_live"
    assert (
        len(
            ports.policy.live_work_runs(
                policy.ControlFacts(None, (), (), (), (progressed,), wip_limit=1)
            )
        )
        == 1
    )


def test_an_unreadable_cwd_of_our_own_keeps_the_verdict_from_concluding(
    tmp_path: Path,
) -> None:
    """A cwd the scan cannot read is not an empty tree (#625's cap ruling).

    Round two's High: an empty `matched` was read as proof the tree holds
    nobody, but a process of this user whose `readlink` fails for any reason
    but ENOENT is exactly the agent a terminal verdict would have to be sure
    about.  The could-not-look keeps the slot: failing closed costs a held
    slot until someone looks; failing open costs a duplicate dispatch onto
    live work.
    """
    repo, tree = _worktree_repo(tmp_path)
    _git("commit", "--allow-empty", "-m", "unpushed", cwd=tree)
    _dispatch_record(tmp_path)
    collector = _controller_classifier(
        tmp_path, repo, _plant(tmp_path, 4242, tree, unreadable=True)
    )
    run = policy.WorkRunFact("run-1", "running", "item-1", "d-1", issue=1)

    resolved = collector.collect((run,))[0]

    assert resolved.state == "running"
    assert resolved.recovery_kind == "still_live"
    assert (
        len(
            ports.policy.live_work_runs(
                policy.ControlFacts(None, (), (), (), (resolved,), wip_limit=1)
            )
        )
        == 1
    )


def test_a_cwd_unreadable_because_unowned_does_not_block_concluding(
    tmp_path: Path,
) -> None:
    """A different-uid process's unreadable cwd was never visible to this read anyway.

    The deliberate half of the unreadable-cwd placement: dispatches run as the
    controller's own user, so a process whose `status` names another owner is
    not one of this dispatch's and its unreadable directory is not evidence
    about the tree.  Only a same-uid could-not-look (or an unplaceable one)
    keeps the slot.
    """
    repo, tree = _worktree_repo(tmp_path)
    _git("commit", "--allow-empty", "-m", "unpushed", cwd=tree)
    _dispatch_record(tmp_path)
    machine = _plant(tmp_path, 4242, tree, unreadable=True)
    foreign = os.geteuid() + 1
    status = machine.procfs / "4242" / "status"
    status.write_text(
        f"Name:\tagent\nUid:\t{foreign}\t{foreign}\t{foreign}\t{foreign}\n", encoding="utf-8"
    )
    collector = _controller_classifier(tmp_path, repo, machine)
    run = policy.WorkRunFact("run-1", "running", "item-1", "d-1", issue=1)

    resolved = collector.collect((run,))[0]

    assert resolved.state == policy.NON_RESULT
    assert resolved.failure_class == "interrupted"
    assert resolved.recovery_kind == "lost_work"
    assert (
        ports.policy.live_work_runs(policy.ControlFacts(None, (), (), (), (resolved,), wip_limit=1))
        == ()
    )


def test_a_deleted_cwd_inside_the_tree_keeps_the_verdict_from_concluding(
    tmp_path: Path,
) -> None:
    """A live process the tree was removed under is somebody, not nobody.

    The kernel still names the old path with its ` (deleted)` marker, so the
    scan saw the pid and cannot prove it is gone — the same absence-of-evidence
    shape as round two's High, one door over.
    """
    repo, tree = _worktree_repo(tmp_path)
    _git("commit", "--allow-empty", "-m", "unpushed", cwd=tree)
    _dispatch_record(tmp_path)
    collector = _controller_classifier(tmp_path, repo, _plant(tmp_path, 4242, tree, deleted=True))
    run = policy.WorkRunFact("run-1", "running", "item-1", "d-1", issue=1)

    resolved = collector.collect((run,))[0]

    assert resolved.state == "running"
    assert resolved.recovery_kind == "still_live"
    assert (
        len(
            ports.policy.live_work_runs(
                policy.ControlFacts(None, (), (), (), (resolved,), wip_limit=1)
            )
        )
        == 1
    )


def test_an_unreadable_procfs_keeps_the_verdict_from_concluding(tmp_path: Path) -> None:
    """A `/proc` the scan cannot list is a look that never happened.

    `just dispatch --stop` refuses the same input by name (`procfs_unavailable`);
    the classifier has no refusal vocabulary, so it keeps the slot instead —
    which is the same fail-closed answer in the only shape it can say.
    """
    repo, tree = _worktree_repo(tmp_path)
    _git("commit", "--allow-empty", "-m", "unpushed", cwd=tree)
    _dispatch_record(tmp_path)
    classifier = ports.ExistingRecoveryClassifier(
        repo,
        tmp_path / "watch",
        tmp_path / "dispatches",
        machine=ports.dispatch_stop.Machine(procfs=tmp_path / "no-proc", self_pid=1),
    )
    collector = ports.DispatchDeliveryFactCollector(tmp_path / "dispatches", recovery=classifier)
    run = policy.WorkRunFact("run-1", "running", "item-1", "d-1", issue=1)

    resolved = collector.collect((run,))[0]

    assert resolved.state == "running"
    assert resolved.recovery_kind == "still_live"
    assert (
        len(
            ports.policy.live_work_runs(
                policy.ControlFacts(None, (), (), (), (resolved,), wip_limit=1)
            )
        )
        == 1
    )


def test_the_controllers_own_chain_does_not_block_a_conclusion(tmp_path: Path) -> None:
    """The controller's own chain is a reasoned exclusion, not a could-not-look.

    A process of this scan's own chain sits in the tree by construction and is
    never occupancy, so its presence must not hold the slot the way an
    unreadable cwd does.  Concluding past it is the scan working as designed.
    """
    repo, tree = _worktree_repo(tmp_path)
    _git("commit", "--allow-empty", "-m", "unpushed", cwd=tree)
    _dispatch_record(tmp_path)
    collector = _controller_classifier(tmp_path, repo, _plant(tmp_path, 1, tree))
    run = policy.WorkRunFact("run-1", "running", "item-1", "d-1", issue=1)

    resolved = collector.collect((run,))[0]

    assert resolved.state == policy.NON_RESULT
    assert resolved.failure_class == "interrupted"
    assert resolved.recovery_kind == "lost_work"
    assert (
        ports.policy.live_work_runs(policy.ControlFacts(None, (), (), (), (resolved,), wip_limit=1))
        == ()
    )


@pytest.mark.parametrize("kind", ["finished_and_cleaned", "lost_work"])
def test_a_terminal_verdict_is_never_re_derived(tmp_path: Path, kind: str) -> None:
    """`lost_work` and `finished_and_cleaned` conclude; a later cycle asks nothing."""
    _dispatch_record(tmp_path)
    calls: list[str] = []

    class Recovery:
        def classify(self, run: Any) -> str:  # noqa: ANN401 — dynamic policy module
            calls.append(run.dispatch_id)
            return kind

    collector = ports.DispatchDeliveryFactCollector(tmp_path / "dispatches", recovery=Recovery())
    run = policy.WorkRunFact("run-1", "running", "item-1", "d-1", issue=1)

    concluded = collector.collect((run,))[0]
    settled = collector.collect((concluded,))[0]

    assert calls == ["d-1"]
    assert settled == concluded
    assert settled.state == policy.NON_RESULT


def test_an_unproven_look_records_a_verdict_without_concluding(tmp_path: Path) -> None:
    """`unproven` says the look did not resolve, so it may not conclude the run either.

    recovery.py's own wording: clearing an unproven look here would be a guess.  The run
    keeps its state and slot, and stays open to the next cycle's classification.
    """
    _dispatch_record(tmp_path)

    class Recovery:
        def classify(self, _run: Any) -> str:  # noqa: ANN401 — dynamic policy module
            return "unproven"

    collector = ports.DispatchDeliveryFactCollector(tmp_path / "dispatches", recovery=Recovery())
    run = policy.WorkRunFact("run-1", "running", "item-1", "d-1", issue=1)

    observed = collector.collect((run,))

    assert observed[0].state == "running"
    assert observed[0].failure_class is None
    assert observed[0].recovery_kind == "unproven"
    assert (
        len(
            ports.policy.live_work_runs(
                policy.ControlFacts(None, (), (), (), observed, wip_limit=1)
            )
        )
        == 1
    )


def test_a_non_result_concluded_on_an_unresolved_look_is_re_derived(tmp_path: Path) -> None:
    """A `non_result` an earlier cycle stamped `unproven` is a guess, not a conclusion.

    Older cycles wrote exactly that state, so the run is built as they left it: a run
    whose next look resolves must not be held by the verdict it carries.
    """
    _dispatch_record(tmp_path)

    class Recovery:
        def classify(self, _run: Any) -> str:  # noqa: ANN401 — dynamic policy module
            return "lost_work"

    collector = ports.DispatchDeliveryFactCollector(tmp_path / "dispatches", recovery=Recovery())
    run = policy.WorkRunFact(
        "run-1",
        policy.NON_RESULT,
        "item-1",
        "d-1",
        issue=1,
        failure_class="interrupted",
        recovery_kind="unproven",
    )

    observed = collector.collect((run,))

    assert observed[0].state == policy.NON_RESULT
    assert observed[0].failure_class == "interrupted"
    assert observed[0].recovery_kind == "lost_work"


@pytest.mark.parametrize(
    "state",
    [
        "planned",
        "starting",
        "launching",
        "running",
        "stalled",
        "interrupted",
        "reviewed",
        "gated",
        "hypothesis-state",
    ],
)
def test_a_still_live_look_never_rewrites_the_workflow_state(tmp_path: Path, state: str) -> None:
    """`still_live` is a look at a tree, so it writes its verdict and nothing else.

    Every workflow state a run can carry survives the look — the delivery
    progression, the controller's own `launching`, and whatever arrives after
    this test was written, which no hand-kept precedence list can be trusted to
    remember.  The look says only that the tree reads; it is not evidence about
    the workflow, and a stalled or interrupted run is not thereby confirmed
    live.  Round two's Medium: the previous shape answered the precedence
    question with a second copy of the progression, and `stalled` still
    collapsed to `running`.
    """
    _dispatch_record(tmp_path)
    delivery = {
        "schema": ports.DELIVERY_SCHEMA,
        "work_run": {"key": "run-1", "state": state, "dispatch_id": "d-1"},
    }
    (tmp_path / "dispatches" / "d-1" / "delivery.json").write_text(
        json.dumps(delivery) + "\n", encoding="utf-8"
    )

    class Recovery:
        def classify(self, _run: Any) -> str:  # noqa: ANN401 — dynamic policy module
            return "still_live"

    collector = ports.DispatchDeliveryFactCollector(tmp_path / "dispatches", recovery=Recovery())

    observed = collector.collect(())

    assert observed[0].state == state
    assert observed[0].recovery_kind == "still_live"
    if state == "interrupted":
        assert (
            len(
                ports.policy.live_work_runs(
                    policy.ControlFacts(None, (), (), (), observed, wip_limit=1)
                )
            )
            == 1
        )
