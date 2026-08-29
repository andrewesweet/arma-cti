"""Journal, view, and scheduling-lock cases for the Controller slice."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

import pytest
from conftest import load_tool

if TYPE_CHECKING:
    from pathlib import Path


store = load_tool("controller_store")
policy = store.policy
ports = load_tool("controller_ports")


def empty_facts() -> object:
    """Return the normalized empty graph stored by the first slice."""
    return policy.ControlFacts(None, (), (), (), ())


def payload() -> dict[str, object]:
    """Return one complete stable journal payload."""
    return {
        "facts": policy.facts_document(empty_facts()),
        "lifecycle": {
            "state": policy.NO_ADMISSIBLE_INITIATIVE,
            "admitted_initiative": None,
            "reason": "no_product_curator_configured",
        },
        "actions": [],
    }


def write_journal(root: Path, content: str) -> None:
    """Write only the journal so incomplete-state tests cannot inherit a view."""
    root.mkdir(parents=True, exist_ok=True)
    (root / store.JOURNAL_NAME).write_text(content, encoding="utf-8")


def raw_record(**overrides: object) -> dict[str, object]:
    """Build one syntactically complete record for header-validation cases."""
    record: dict[str, object] = {
        "schema": store.JOURNAL_SCHEMA,
        "cycle_id": "cycle-1",
        "phase": "planned",
        "recorded_at": "now",
        "recorded_by": "test-controller",
        "payload": payload(),
    }
    record.update(overrides)
    return record


def test_complete_cycle_reloads_and_binds_view_to_exact_journal_bytes(tmp_path: Path) -> None:
    controller_store = store.ControllerStore(tmp_path / "controller")

    controller_store.write_cycle(
        "cycle-1",
        payload(),
        recorded_at="2026-08-27T12:00:00+00:00",
        recorded_by="test-controller",
    )

    loaded = controller_store.load()
    journal = controller_store.journal_path.read_bytes()
    view = json.loads(controller_store.view_path.read_text(encoding="utf-8"))
    assert loaded.last_cycle_id == "cycle-1"
    assert loaded.record_count == 3
    assert loaded.lifecycle.state == policy.NO_ADMISSIBLE_INITIATIVE
    assert loaded.actions == ()
    assert view["journal_sha256"] == hashlib.sha256(journal).hexdigest()
    assert view["confirmed"] == payload()
    assert not list(controller_store.root.glob(".view.json.*"))


def test_bootstrap_recovery_refuses_journal_even_without_a_view(tmp_path: Path) -> None:
    controller_store = store.ControllerStore(tmp_path / "controller")
    controller_store.mark_started()
    controller_store.root.mkdir()
    controller_store.journal_path.write_text("state needs review\n", encoding="utf-8")

    with pytest.raises(
        store.ControllerStateUnreadable,
        match="controller_bootstrap_recovery_requires_state_review",
    ):
        controller_store.recover_interrupted_bootstrap()

    assert controller_store.started_marker_path.exists()


def test_empty_desired_outcome_content_is_rejected_from_local_state(tmp_path: Path) -> None:
    controller_store = store.ControllerStore(tmp_path / "controller")
    invalid_facts = policy.facts_document(empty_facts())
    invalid_facts["desired_outcomes"] = [
        {
            "key": "outcome-1",
            "revision": 1,
            "content_digest": "digest",
            "content": "",
        }
    ]
    invalid_payload = payload()
    invalid_payload["facts"] = invalid_facts

    with pytest.raises(store.ControllerStateUnreadable, match="facts_invalid_content"):
        controller_store.append_phase(
            "cycle-1",
            "planned",
            invalid_payload,
            recorded_at="now",
            recorded_by="test-controller",
        )


def test_boolean_desired_outcome_revision_is_rejected_from_local_state(tmp_path: Path) -> None:
    controller_store = store.ControllerStore(tmp_path / "controller")
    invalid_facts = policy.facts_document(empty_facts())
    invalid_facts["desired_outcomes"] = [
        {
            "key": "outcome-1",
            "revision": True,
            "content_digest": "digest",
        }
    ]
    invalid_payload = payload()
    invalid_payload["facts"] = invalid_facts

    with pytest.raises(store.ControllerStateUnreadable, match="facts_desired_outcomes_revision"):
        controller_store.append_phase(
            "cycle-1",
            "planned",
            invalid_payload,
            recorded_at="now",
            recorded_by="test-controller",
        )


def test_partial_new_cycle_does_not_replay_previous_cycle_actions(tmp_path: Path) -> None:
    controller_store = store.ControllerStore(tmp_path / "controller")
    previous = payload()
    previous["actions"] = policy.actions_document(
        (policy.ControlAction("tracker.previous", "previous"),)
    )
    controller_store.write_cycle(
        "cycle-1",
        previous,
        recorded_at="now",
        recorded_by="test-controller",
    )

    current = payload()
    controller_store.append_phase(
        "cycle-2",
        "planned",
        current,
        recorded_at="now",
        recorded_by="test-controller",
    )

    recovered = controller_store.load_recoverable()

    assert recovered.phase == "planned"
    assert recovered.actions == ()


def test_append_phase_rejects_unknown_phase_before_writing(tmp_path: Path) -> None:
    controller_store = store.ControllerStore(tmp_path / "controller")

    with pytest.raises(ValueError, match=r"^planted$"):
        controller_store.append_phase(
            "cycle-1",
            "planted",
            payload(),
            recorded_at="now",
            recorded_by="test-controller",
        )

    assert not controller_store.journal_path.exists()


@pytest.mark.parametrize(
    "content",
    [
        "",
        '{"schema":"controller-journal/v1"',
        "not-json\n",
        json.dumps(
            {
                "schema": "controller-journal/v999",
                "cycle_id": "cycle-1",
                "phase": "planned",
                "recorded_at": "now",
                "recorded_by": "test-controller",
                "payload": payload(),
            }
        )
        + "\n",
        json.dumps(
            {
                "schema": store.JOURNAL_SCHEMA,
                "cycle_id": "cycle-1",
                "phase": "planned",
                "recorded_at": "now",
                "recorded_by": "test-controller",
                "payload": payload(),
            }
        )
        + "\n",
    ],
)
def test_local_journal_damage_is_one_typed_refusal(tmp_path: Path, content: str) -> None:
    root = tmp_path / "controller"
    write_journal(root, content)

    with pytest.raises(
        store.ControllerStateUnreadable, match=r"^refusal=controller_state_unreadable"
    ):
        store.ControllerStore(root).load()


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"schema": "controller-journal/v999"}, "journal_unknown_schema:1"),
        ({"recorded_at": ""}, "journal_invalid_recorded_at:1"),
    ],
)
def test_record_header_diagnostics_keep_the_first_line_number(
    tmp_path: Path, overrides: dict[str, object], expected: str
) -> None:
    root = tmp_path / "controller"
    write_journal(root, json.dumps(raw_record(**overrides)) + "\n")

    with pytest.raises(store.ControllerStateUnreadable, match=expected):
        store.ControllerStore(root).load()


def test_empty_configured_curator_is_not_treated_as_a_valid_fact(tmp_path: Path) -> None:
    root = tmp_path / "controller"
    invalid_payload = payload()
    invalid_facts = policy.facts_document(empty_facts())
    invalid_facts["configured_curator"] = ""
    invalid_payload["facts"] = invalid_facts
    record = raw_record(payload=invalid_payload)
    write_journal(root, json.dumps(record) + "\n")

    with pytest.raises(store.ControllerStateUnreadable, match="facts_configured_curator"):
        store.ControllerStore(root).load()


def test_view_disagreement_is_refused_even_when_the_journal_is_valid(tmp_path: Path) -> None:
    controller_store = store.ControllerStore(tmp_path / "controller")
    controller_store.write_cycle(
        "cycle-1",
        payload(),
        recorded_at="now",
        recorded_by="test-controller",
    )
    view = json.loads(controller_store.view_path.read_text(encoding="utf-8"))
    view["last_cycle_id"] = "cycle-2"
    controller_store.view_path.write_text(json.dumps(view) + "\n", encoding="utf-8")

    with pytest.raises(store.ControllerStateUnreadable, match="view_last_cycle_mismatch"):
        controller_store.load()


def test_scheduling_lock_is_nonblocking_and_releases_for_the_next_writer(tmp_path: Path) -> None:
    lock_path = tmp_path / "controller" / store.LOCK_NAME
    first = store.SchedulingLock(lock_path)
    second = store.SchedulingLock(lock_path)

    with first as acquired:
        pass
    assert acquired is first
    with first, pytest.raises(store.ControllerLockHeld, match=r"^refusal=controller_lock_held"):
        second.acquire()
    with second:
        assert lock_path.exists()


def test_started_marker_survives_missing_state_and_names_interrupted_bootstrap(
    tmp_path: Path,
) -> None:
    controller_store = store.ControllerStore(tmp_path / "controller")
    controller_store.mark_started()

    assert controller_store.started_marker_path.exists()
    with pytest.raises(store.ControllerStateUnreadable) as error:
        controller_store.load()

    assert error.value.reason == "controller_bootstrap_interrupted"


def test_named_bootstrap_recovery_clears_only_empty_interrupted_state(tmp_path: Path) -> None:
    controller_store = store.ControllerStore(tmp_path / "controller")
    controller_store.mark_started()
    controller_store.root.mkdir()
    controller_store.lock_path.touch()

    controller_store.recover_interrupted_bootstrap()

    assert not controller_store.started_marker_path.exists()
    assert controller_store.lock_path.exists()


def published_non_result_facts(*, result_published: bool) -> policy.ControlFacts:
    """Facts whose one run observed a quota non-result and holds item-1's slot."""
    run = policy.WorkRunFact(
        "d-1",
        "non_result",
        work_item_key="item-1",
        dispatch_id="d-1",
        failure_class="quota_exhausted",
        issue=1,
        result_published=result_published,
    )
    item = policy.WorkItemFact("item-1", "open", issue=1)
    return policy.ControlFacts(None, (), (), (item,), (run,), wip_limit=1)


def write_and_reload(root: Path, facts: policy.ControlFacts) -> store.LoadedControllerState:
    """Persist one cycle of facts and load it back through the journal."""
    controller_store = store.ControllerStore(root / "controller")
    document = payload()
    document["facts"] = policy.facts_document(facts)
    controller_store.write_cycle(
        "cycle-1",
        document,
        recorded_at="2026-08-29T12:00:00+00:00",
        recorded_by="test-controller",
    )
    return controller_store.load()


def recollect_over(loaded: store.LoadedControllerState, root: Path) -> policy.ControlFacts:
    """Re-read the run's published result and merge it over the reloaded fact."""
    (root / "dispatches" / "d-1").mkdir(parents=True)
    (root / "dispatches" / "d-1" / "result.json").write_text(
        json.dumps({"dispatch_id": "d-1", "status": "child_finished", "outcome": "quota_exhausted"})
        + "\n",
        encoding="utf-8",
    )
    observed = ports.DispatchDeliveryFactCollector(root / "dispatches").collect(
        loaded.facts.work_runs
    )
    merged = policy.merge_work_run_observations(loaded.facts.work_runs, observed)
    return policy.ControlFacts(None, (), (), loaded.facts.work_items, merged, wip_limit=1)


def test_a_published_non_result_survives_the_journal_boundary(tmp_path: Path) -> None:
    """A recorded publication serialises; a dropped stamp reloads as a held slot.

    The release is a recorded fact, so it has to outlive the cycle that
    recorded it: the journal is the only durable form the fact takes.
    """
    loaded = write_and_reload(tmp_path, published_non_result_facts(result_published=True))

    assert loaded.facts.work_runs[0].result_published is True
    assert policy.live_work_runs(loaded.facts) == ()


def test_recollection_after_reload_keeps_the_slot_released(tmp_path: Path) -> None:
    """Collector, journal, reload, recollection: the span a one-cycle test hides."""
    loaded = write_and_reload(tmp_path, published_non_result_facts(result_published=True))

    merged_facts = recollect_over(loaded, tmp_path)

    assert merged_facts.work_runs[0].result_published is True
    assert policy.live_work_runs(merged_facts) == ()
    assert policy.eligible_work_items(merged_facts) == loaded.facts.work_items


def landed_run_facts() -> policy.ControlFacts:
    """Facts whose one run has landed on item-1 and carries no publication yet."""
    run = policy.WorkRunFact(
        "d-1",
        "landed",
        work_item_key="item-1",
        dispatch_id="d-1",
        issue=1,
        landed_sha="a" * 40,
    )
    item = policy.WorkItemFact("item-1", "open", issue=1)
    return policy.ControlFacts(None, (), (), (item,), (run,), wip_limit=1)


def stage_published_result_with_delivery(root: Path) -> None:
    """Stage d-1's own result with the typed delivery block the collector reads."""
    record = root / "dispatches" / "d-1"
    record.mkdir(parents=True, exist_ok=True)
    (record / "result.json").write_text(
        json.dumps(
            {
                "dispatch_id": "d-1",
                "delivery": {
                    "key": "d-1",
                    "state": "gated",
                    "work_item_key": "item-1",
                    "dispatch_id": "d-1",
                    "issue": 1,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )


def run_published_cycle(
    loaded: store.LoadedControllerState, root: Path, cycle_id: str
) -> store.LoadedControllerState:
    """Collect, merge, journal, and reload — one cycle exactly as production runs it."""
    observed = ports.DispatchDeliveryFactCollector(root / "dispatches").collect(
        loaded.facts.work_runs
    )
    merged = policy.merge_work_run_observations(loaded.facts.work_runs, observed)
    merged_facts = policy.ControlFacts(None, (), (), loaded.facts.work_items, merged, wip_limit=1)
    controller_store = store.ControllerStore(root / "controller")
    document = payload()
    document["facts"] = policy.facts_document(merged_facts)
    controller_store.write_cycle(
        cycle_id,
        document,
        recorded_at="2026-08-29T12:00:00+00:00",
        recorded_by="test-controller",
    )
    return controller_store.load()


def test_a_collector_sourced_stamp_survives_two_journalled_cycles(tmp_path: Path) -> None:
    """The stamp is the collector's, and it must outlive every cycle after it.

    The journal starts unstamped, so the only source of the publication fact
    is the collection itself — no hand-written stamp exists anywhere in this
    sequence.  Each cycle persists what it merged and reloads it before
    collecting again, which is the span in which a branch that drops the fact
    loses it permanently rather than for one cycle.
    """
    stage_published_result_with_delivery(tmp_path)
    loaded = write_and_reload(tmp_path, landed_run_facts())
    assert loaded.facts.work_runs[0].result_published is False

    loaded = run_published_cycle(loaded, tmp_path, "cycle-2")
    assert loaded.facts.work_runs[0].result_published is True

    loaded = run_published_cycle(loaded, tmp_path, "cycle-3")
    assert loaded.facts.work_runs[0].result_published is True


def test_a_journal_written_before_the_stamp_self_heals_at_recollection(
    tmp_path: Path,
) -> None:
    """Stuck journals recover while their result is still published.

    A journal recorded before `result_published` existed carries no field, so
    reload cannot know the fact; the next cycle's collection re-reads the same
    result and the merge carries the fresh record instead of discarding it.
    A journal whose result has since been pruned has no such path (#625).
    """
    loaded = write_and_reload(tmp_path, published_non_result_facts(result_published=False))
    assert loaded.facts.work_runs[0].result_published is False
    assert policy.live_work_runs(loaded.facts) == loaded.facts.work_runs

    merged_facts = recollect_over(loaded, tmp_path)

    assert merged_facts.work_runs[0].result_published is True
    assert policy.live_work_runs(merged_facts) == ()
