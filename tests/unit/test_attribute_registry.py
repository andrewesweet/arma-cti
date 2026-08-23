"""The attribute registry and `block_reason` on waits (#484).

Every assertion here reads what a reader would find — the journal line, the
rendered OTLP document — never the internals of a helper, which is #480's
Testing Decisions line: a test that a helper produced a particular attribute
list passes while the posted body is wrong. The check leg's own tests, over
real sources, live in `tests/unit/test_check_attributes.py`.

Prior art: `tests/unit/test_breaker.py` covers one family's emission end to end
including the journal's `exported` flag.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import TYPE_CHECKING, Any, Final

import pytest
from conftest import load_tool

if TYPE_CHECKING:
    from pathlib import Path
    from types import ModuleType

attribute_registry: ModuleType = load_tool("attribute_registry")
dispatch: ModuleType = load_tool("dispatch")
otel_event: ModuleType = load_tool("otel_event")
queue_policy: ModuleType = load_tool("queue_policy")

DEAD_ENDPOINT: Final = "http://127.0.0.1:2999/v1/logs"
NOW: Final = 1_772_000_000.0


# ------------------------------------------------------------------- the registry


def test_the_block_reason_vocabulary_is_the_nine_and_nothing_else() -> None:
    """Closed means closed: a new value is an explicit edit beside this lock.

    #480's Implementation Decisions name the nine; a value arriving any other
    way is a fourth spelling of a rule, which is the drift the registry exists
    to end.
    """
    assert set(attribute_registry.BLOCK_REASONS) == {
        "waiting_human",
        "lane_peak_band",
        "quota_exhausted",
        "breaker_open",
        "waiting_reviewer",
        "worktree_occupied",
        "wip_limit",
        "slot_unavailable",
        "undetermined",
    }


def test_every_reason_row_is_a_sentence_not_a_blank() -> None:
    """A row without its reason is a name that arrived without its justification."""
    for name, reason in attribute_registry.BLOCK_REASONS.items():
        assert len(reason) > 20, f"{name} carries its reason beside it"


# --------------------------------------------------- the terminal state (#489)


def test_the_not_a_result_vocabulary_is_the_four_and_nothing_else() -> None:
    """Closed means closed here too: CLAUDE.md's not-a-result rows, all four.

    The fourth is the one `gate_outcome`'s old tuple omitted — `untyped_harness_failure`,
    which the table says outranks everything, `infra_unavailable` included (#184) — and
    a class arriving any other way than an edit beside this lock is the parallel table
    criterion four forbids.
    """
    assert set(attribute_registry.NOT_A_RESULT_CLASSES) == {
        "infra_unavailable",
        "quota_exhausted",
        "provider_refused",
        "untyped_harness_failure",
    }
    for name, reason in attribute_registry.NOT_A_RESULT_CLASSES.items():
        assert len(reason) > 20, f"{name} carries its reason beside it"


def test_a_terminal_event_journals_fail_open_with_its_export_outcome(tmp_path: Path) -> None:
    """One abandonment, one journal line beside the record it names, export outcome kept."""
    exported = attribute_registry.emit_terminal(
        attribute_registry.terminal_event(
            "abandoned",
            "quota_exhausted",
            NOW,
            dispatch_id="d-20260823-112611-917c38",
            identity={
                "lane": "codex",
                "profile": "codex-luna-max",
                "seat": "implementer",
                "issue": 486,
            },
        ),
        journal=tmp_path / "terminal.jsonl",
        endpoint=DEAD_ENDPOINT,
    )
    assert exported is False, "the dead endpoint is the arrangement, not a surprise"
    (row,) = journal_rows(tmp_path / "terminal.jsonl")
    assert row["event"] == "cti.terminal.state"
    assert row["exported"] is False
    assert row["export_detail"]
    assert row["attributes"]["cti.dispatch_id"] == "d-20260823-112611-917c38"
    assert row["attributes"]["cti.terminal.state"] == "abandoned"
    assert row["attributes"]["cti.terminal.class"] == "quota_exhausted"
    assert row["attributes"]["cti.lane"] == "codex"
    assert row["attributes"]["cti.issue"] == 486


def test_a_terminal_class_outside_the_vocabulary_is_refused_not_journalled(
    tmp_path: Path,
) -> None:
    """The spelling is a programming error, never a transport failure to swallow."""
    with pytest.raises(ValueError, match="closed vocabulary"):
        attribute_registry.terminal_event("abandoned", "timed_out", NOW, dispatch_id="d")
    with pytest.raises(ValueError, match="closed vocabulary"):
        attribute_registry.terminal_event("vanished", "quota_exhausted", NOW, dispatch_id="d")
    assert not (tmp_path / "terminal.jsonl").exists(), "and nothing was journalled for it"


# ------------------------------------------------------------- wait emission


def journal_rows(path: Path) -> list[dict[str, Any]]:
    """Read a wait journal as its reader finds it, one object per line."""
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_a_wait_journals_fail_open_with_its_export_outcome(tmp_path: Path) -> None:
    """A collector that refuses is a recorded fact, never a lost event (#496)."""
    exported = attribute_registry.emit_wait(
        attribute_registry.wait_event("wip_limit", "queue", NOW, refusal="wip_reached"),
        journal=tmp_path / "waits.jsonl",
        endpoint=DEAD_ENDPOINT,
    )
    assert exported is False, "the dead endpoint is the arrangement, not a surprise"
    (row,) = journal_rows(tmp_path / "waits.jsonl")
    assert row["event"] == "cti.wait.blocked"
    assert row["exported"] is False
    assert row["export_detail"]
    assert row["attributes"]["cti.wait.block_reason"] == "wip_limit"
    assert row["attributes"]["cti.wait.surface"] == "queue"
    assert row["attributes"]["cti.wait.refusal"] == "wip_reached"


def test_a_value_outside_the_closed_vocabulary_is_refused_not_journalled(
    tmp_path: Path,
) -> None:
    """The vocabulary is enforced at the builder, which is a code bug's loud failure.

    Fail-open governs the emission — transport, journal — and never the
    spelling: a misspelt cause journalled quietly would be the fourth spelling
    arriving through the side door.
    """
    with pytest.raises(ValueError, match="closed vocabulary"):
        attribute_registry.wait_event("waiting_on_human", "queue", NOW)

    assert not (tmp_path / "waits.jsonl").exists(), "and nothing was journalled for it"


def test_the_breaker_refusal_maps_its_class_to_two_different_remedies() -> None:
    """`lane_breaker_open` is one refusal kind with two causes and two remedies."""
    quota = dispatch.Refusal("lane_breaker_open", (), "", failure_class="quota_exhausted")
    assert attribute_registry.block_reason_for(quota) == "quota_exhausted"
    quality = dispatch.Refusal("lane_breaker_open", (), "", failure_class="provider_refused")
    assert attribute_registry.block_reason_for(quality) == "breaker_open"


def test_a_wait_whose_cause_cannot_be_determined_says_so(tmp_path: Path) -> None:
    """A breaker trip on an unnamed class is a real wait with an unreadable cause.

    `undetermined` is the stated absence — never an omitted field, never a
    picked value — which is the criterion that decides this issue's review.
    """
    odd = dispatch.Refusal("lane_breaker_open", (), "", failure_class="something_new")
    assert attribute_registry.block_reason_for(odd) == "undetermined"

    attribute_registry.emit_wait(
        attribute_registry.wait_event(
            attribute_registry.block_reason_for(odd), "dispatch", NOW, refusal="lane_breaker_open"
        ),
        journal=tmp_path / "waits.jsonl",
        endpoint=DEAD_ENDPOINT,
    )
    (row,) = journal_rows(tmp_path / "waits.jsonl")
    assert row["attributes"]["cti.wait.block_reason"] == "undetermined"
    assert row["attributes"]["cti.wait.refusal"] == "lane_breaker_open"


def test_a_refusal_that_names_no_wait_emits_nothing() -> None:
    """A bad argument was never going to happen, so it is no queue's wait."""
    missing = dispatch.Refusal("incomplete_request", (), "")
    assert attribute_registry.block_reason_for(missing) is None


def _next_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    policy: queue_policy.Policy,
    candidates: tuple[queue_policy.Candidate, ...],
) -> tuple[tuple[str, ...], int]:
    """Drive the queue's `next` seam over staged candidates and return its verdict.

    The seam, not a re-statement of it (#484 round 2, finding 4): `_candidate_read`
    is where a blocked selection decides its cause and calls `note_wait`, so the
    assertion below reads the journal the seam wrote rather than re-deriving the
    branch beside it. `ready_candidates` is staged because the real one reads the
    tracker live, which would make the arrangement somebody else's issue list.
    """
    monkeypatch.setattr(
        queue_policy,
        "ready_candidates",
        lambda: (candidates, None),
    )
    args = argparse.Namespace(verb="next", count=1)
    store = queue_policy.Store(directory=tmp_path)
    return queue_policy._candidate_read(  # noqa: SLF001 — the seam's own branch is the subject
        args, store, policy, queue_policy.InFlight((), (), "read")
    )


def _open_policy() -> queue_policy.Policy:
    return queue_policy.Policy(
        freeze=queue_policy.Freeze("open", "", ""),
        wip_limit=queue_policy.WipLimit(3, "", ""),
        packages=(),
    )


def test_a_queue_that_stops_with_candidates_standing_journals_undetermined(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`no_ready_issue` over standing candidates: per-candidate causes, no single value.

    The drops are known one by one and heterogeneous in kind, so picking any one of
    the eight would be the guess `undetermined` exists to refuse — and the decision
    is the seam's own, read back from the journal it wrote rather than re-stated
    here. The freeze is deliberately open: a frozen queue names its cause, which is
    the next test's subject, not this one's.
    """
    blocked_a = queue_policy.Candidate(601, "waiting on another issue", "Blocked-by: #600")
    blocked_b = queue_policy.Candidate(602, "waiting on another issue", "Blocked-by: #601")
    lines, code = _next_read(tmp_path, monkeypatch, _open_policy(), (blocked_a, blocked_b))
    assert code != 0
    assert any("no_ready_issue" in line for line in lines)
    (row,) = journal_rows(tmp_path / "waits.jsonl")
    assert row["event"] == "cti.wait.blocked"
    assert row["attributes"]["cti.wait.block_reason"] == "undetermined"
    assert row["attributes"]["cti.wait.surface"] == "queue"
    assert row["attributes"]["cti.wait.refusal"] == "no_ready_issue"


def test_a_frozen_queue_journals_the_human_it_waits_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The queue seam's named cause: a freeze is a wait on the human's own hand."""
    standing = (queue_policy.Candidate(601, "anything", ""),)
    frozen = queue_policy.Policy(
        freeze=queue_policy.Freeze("frozen", "", "a ruling"),
        wip_limit=queue_policy.WipLimit(3, "", ""),
        packages=(),
    )
    lines, code = _next_read(tmp_path, monkeypatch, frozen, standing)
    assert code != 0
    assert any("dispatch_frozen" in line for line in lines)
    (row,) = journal_rows(tmp_path / "waits.jsonl")
    assert row["attributes"]["cti.wait.block_reason"] == "waiting_human"
    assert row["attributes"]["cti.wait.refusal"] == "dispatch_frozen"


def test_an_empty_ready_queue_is_not_a_wait() -> None:
    """Nothing standing means nothing waiting: absence, not `undetermined`."""
    selection = queue_policy.select(
        queue_policy.Policy(
            freeze=queue_policy.Freeze("open", "", ""),
            wip_limit=queue_policy.WipLimit(3, "", ""),
            packages=(),
        ),
        (),
        queue_policy.InFlight((), (), ""),
        1,
    )
    assert selection.refusal is not None
    reason = attribute_registry.block_reason_for(selection.refusal)
    assert reason is None, "no candidates stood, so no wait is recorded"


# --------------------------------------------------------------- hermeticity


def test_the_suite_resolves_every_default_emission_to_the_dead_port() -> None:
    """No emission this suite makes can reach the box's real collector (#484 round 2).

    `conftest` forces `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT`, which is the structural
    closure: an emission that forgot to point anywhere exported for real while the
    collector was up, and did — wait records for live issues in the JSONL
    `just ledger-sync` materialises. This pins the line's presence, so removing it
    reddens the suite on any box, including one where nothing listens on 4318 and
    the leak would otherwise hide.
    """
    assert os.environ.get("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT") == DEAD_ENDPOINT
    assert otel_event.endpoint_from_environment() == DEAD_ENDPOINT


def test_an_emission_with_no_endpoint_named_is_refused_not_exported(tmp_path: Path) -> None:
    """The leak's own shape, run through the fix: unset endpoint, live collector, no write.

    On this box the collector is up, so before the fix this returned `True` and the
    record reached `http://127.0.0.1:4318`; after it the resolution lands on the dead
    port and the journal carries the refusal as the export's outcome.
    """
    exported = attribute_registry.emit_wait(
        attribute_registry.wait_event("wip_limit", "queue", NOW, refusal="wip_reached"),
        journal=tmp_path / "waits.jsonl",
    )
    assert exported is False
    (row,) = journal_rows(tmp_path / "waits.jsonl")
    assert row["exported"] is False
    assert row["export_detail"].startswith("unreachable:"), row["export_detail"]


# --------------------------------------------------------- reading the journal


def test_a_historical_journal_line_without_the_new_field_still_parses() -> None:
    """Optional on read: the six families' lines predate the wait fields (#480 story 19)."""
    old = otel_event.journal_line(
        otel_event.Event("cti.breaker.transition", NOW, {"cti.lane": "zai"}, {}),
        exported=False,
        detail="unreachable:ConnectionRefusedError",
    )
    row = json.loads(old)
    assert row["event"] == "cti.breaker.transition"
    assert "cti.wait.block_reason" not in row["attributes"], "absent is a fact, not a default"

    new = otel_event.journal_line(
        attribute_registry.wait_event("waiting_reviewer", "review", NOW, issue=332),
        exported=False,
        detail="unreachable:ConnectionRefusedError",
    )
    later = json.loads(new)
    assert later["attributes"]["cti.wait.block_reason"] == "waiting_reviewer"
    # And the old reader's view of the new line keeps every old key intact.
    assert later["event"] == "cti.wait.blocked"
    assert later["exported"] is False


def test_the_rendered_document_carries_the_reason_where_a_reader_looks() -> None:
    """The OTLP body, not a helper's list: `event.name` and the attribute pair."""
    document = otel_event.log_record(
        attribute_registry.wait_event("lane_peak_band", "dispatch", NOW, refusal="lane_peak_hours")
    )
    record = document["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]
    assert record["body"] == {"stringValue": "cti.wait.blocked"}
    pairs = {entry["key"]: entry["value"] for entry in record["attributes"]}
    assert pairs["event.name"] == {"stringValue": "cti.wait.blocked"}
    assert pairs["cti.wait.block_reason"] == {"stringValue": "lane_peak_band"}
    assert pairs["cti.wait.refusal"] == {"stringValue": "lane_peak_hours"}
