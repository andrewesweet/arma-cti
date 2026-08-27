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
