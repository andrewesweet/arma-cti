"""Fake capability adapters for the controller's external seams."""

from __future__ import annotations

from typing import TYPE_CHECKING

from conftest import load_tool

if TYPE_CHECKING:
    from pathlib import Path


ports = load_tool("controller_ports")
policy = load_tool("controller_policy")


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
    port = ports.FakeDetachedWorkRunPort()

    port.start("run-1")

    assert port.started == ["run-1"]
    assert not (tmp_path / "scheduling.lock").exists()
