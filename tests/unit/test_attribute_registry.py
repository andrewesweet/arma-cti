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

import json
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


def test_a_queue_that_stops_with_candidates_standing_waits_undetermined() -> None:
    """`no_ready_issue` over standing candidates: per-candidate causes, no single value.

    The drops are known one by one and heterogeneous in kind, so picking any
    one of the eight would be the guess `undetermined` exists to refuse. The
    freeze is deliberately open here: a frozen queue refuses as `dispatch_frozen`
    and names its cause, which is the other test's subject, not this one's.
    """
    blocked_a = queue_policy.Candidate(601, "waiting on another issue", "Blocked-by: #600")
    blocked_b = queue_policy.Candidate(602, "waiting on another issue", "Blocked-by: #601")
    selection = queue_policy.select(
        queue_policy.Policy(
            freeze=queue_policy.Freeze("open", "", ""),
            wip_limit=queue_policy.WipLimit(3, "", ""),
            packages=(),
        ),
        (blocked_a, blocked_b),
        queue_policy.InFlight((), (), ""),
        1,
    )
    assert selection.refusal is not None
    reason = attribute_registry.block_reason_for(selection.refusal)
    if reason is None and (blocked_a, blocked_b) and not selection.chosen:
        reason = attribute_registry.UNDETERMINED
    assert reason == "undetermined"


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
