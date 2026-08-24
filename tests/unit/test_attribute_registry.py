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


def test_a_queue_depth_count_rejects_bool_even_though_bool_is_an_int() -> None:
    with pytest.raises(ValueError, match="counted sample carries its count"):
        attribute_registry.queue_depth_event(
            "ready_work", "counted", NOW, count=True, oldest="none"
        )


# --------------------------------------------------- the stage family and its journal (#490)


def stage_rows(journal: Path) -> list[dict[str, Any]]:
    """Read a stage journal as its reader finds it, one object per line."""
    return [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]


def test_the_stage_set_is_the_six_in_pipeline_order() -> None:
    """Closed and ordered: the order is data, because first-pass status is decided by it."""
    assert list(attribute_registry.STAGES) == [
        "brief",
        "implementation",
        "own_gate",
        "exchange",
        "review",
        "land",
    ]


def test_the_first_pass_vocabulary_is_the_three_states() -> None:
    """`undetermined` is a state, not a soft true — yield multiplies the per-stage rates."""
    assert list(attribute_registry.FIRST_PASS) == ["first_time", "after_rework", "undetermined"]


def test_every_stage_reason_is_a_sentence_not_a_blank() -> None:
    for vocabulary in (attribute_registry.STAGES, attribute_registry.FIRST_PASS):
        for reason in vocabulary.values():
            assert reason
            assert reason.strip()


def test_every_seat_the_seams_map_is_a_stage_the_registry_holds() -> None:
    """The seat map derives its values from STAGES; a value it does not hold is a typo."""
    for stage in attribute_registry.STAGE_OF_SEAT.values():
        assert stage in attribute_registry.STAGES


def test_a_stage_event_carries_the_stage_its_status_and_the_item() -> None:
    event = attribute_registry.stage_event(
        "implementation", "first_time", NOW, issue=490, dispatch_id="d-1"
    )
    assert event.name == "cti.stage.transition"
    assert dict(event.attributes) == {
        "cti.stage.name": "implementation",
        "cti.stage.first_pass": "first_time",
        "cti.issue": 490,
        "cti.dispatch_id": "d-1",
    }


def test_a_stage_or_status_outside_the_vocabularies_is_refused_not_journalled(
    tmp_path: Path,
) -> None:
    journal = attribute_registry.stage_journal(490, tmp_path)
    for bad in (
        lambda: attribute_registry.stage_event("dispatch", "first_time", NOW, issue=490),
        lambda: attribute_registry.stage_event("brief", "probably", NOW, issue=490),
    ):
        with pytest.raises(ValueError, match="closed"):
            bad()
    assert not journal.exists(), "and nothing was journalled for either"


def test_a_stage_arrival_journals_fail_open_with_its_export_outcome(tmp_path: Path) -> None:
    """A collector that refuses is a recorded fact, never a lost arrival (#496's shape)."""
    status = attribute_registry.record_stage_arrival("brief", 490, tmp_path, NOW)
    assert status == "first_time"
    (row,) = stage_rows(attribute_registry.stage_journal(490, tmp_path))
    assert row["event"] == "cti.stage.transition"
    assert row["attributes"]["cti.stage.first_pass"] == "first_time"  # noqa: S105 — the attribute's own name carries "pass"; a stage status, never a credential
    assert row["exported"] is False, "the dead port refuses, and the journal says so"


def test_a_clean_forward_pass_reaches_every_stage_first_time(tmp_path: Path) -> None:
    statuses = [
        attribute_registry.record_stage_arrival(stage, 490, tmp_path, NOW, dispatch_id="d-1")
        for stage in attribute_registry.STAGES
    ]
    assert statuses == ["first_time"] * 6


def test_rework_upstream_makes_a_downstream_first_arrival_not_first_pass(
    tmp_path: Path,
) -> None:
    """The rolled-throughput-yield reading: rework anywhere before a stage counts there."""
    for stage in attribute_registry.STAGES:
        attribute_registry.record_stage_arrival(stage, 490, tmp_path, NOW, dispatch_id="d-1")
    # The fix round: a second brief, a second implementation and own gate — each a
    # re-arrival — and the exchange that follows them is the item's first arrival at
    # exchange but not on its first pass.
    assert attribute_registry.record_stage_arrival("brief", 490, tmp_path, NOW) == "after_rework"
    assert (
        attribute_registry.record_stage_arrival(
            "implementation", 490, tmp_path, NOW, dispatch_id="d-2"
        )
        == "after_rework"
    )
    assert (
        attribute_registry.record_stage_arrival("own_gate", 490, tmp_path, NOW, dispatch_id="d-2")
        == "after_rework"
    )
    assert attribute_registry.record_stage_arrival("exchange", 490, tmp_path, NOW) == "after_rework"
    assert (
        attribute_registry.record_stage_arrival("review", 490, tmp_path, NOW, dispatch_id="d-3")
        == "after_rework"
    )
    assert attribute_registry.record_stage_arrival("land", 490, tmp_path, NOW) == "after_rework"


def test_one_dispatch_reaching_a_stage_twice_is_one_arrival(tmp_path: Path) -> None:
    """The own gate's shape: `just fast` re-runs inside one dispatched session."""
    attribute_registry.record_stage_arrival("brief", 490, tmp_path, NOW)
    attribute_registry.record_stage_arrival("implementation", 490, tmp_path, NOW, dispatch_id="d-1")
    assert (
        attribute_registry.record_stage_arrival("own_gate", 490, tmp_path, NOW, dispatch_id="d-1")
        == "first_time"
    )
    again = attribute_registry.record_stage_arrival(
        "own_gate", 490, tmp_path, NOW, dispatch_id="d-1"
    )
    assert again == attribute_registry.STAGE_ALREADY_REACHED
    journal = stage_rows(attribute_registry.stage_journal(490, tmp_path))
    assert [row["attributes"]["cti.stage.name"] for row in journal] == [
        "brief",
        "implementation",
        "own_gate",
    ], "the re-run journalled nothing"


def test_an_idempotent_arrival_collapses_with_no_dispatch_id_to_dedupe_on(
    tmp_path: Path,
) -> None:
    """The hand landing's shape (#552): the exit-2 re-run carries no dispatch id.

    The dispatch deduplication keys on the id, and a hand landing has none — so
    the land seam asks for idempotence over the stage instead, and the re-run
    that takes `_push`'s nothing-to-push branch is the same arrival.
    """
    for stage in ("brief", "implementation", "own_gate", "exchange", "review"):
        attribute_registry.record_stage_arrival(stage, 552, tmp_path, NOW)
    assert (
        attribute_registry.record_stage_arrival("land", 552, tmp_path, NOW, idempotent=True)
        == "first_time"
    )
    again = attribute_registry.record_stage_arrival("land", 552, tmp_path, NOW, idempotent=True)
    assert again == attribute_registry.STAGE_ALREADY_REACHED
    journal = stage_rows(attribute_registry.stage_journal(552, tmp_path))
    assert [row["attributes"]["cti.stage.name"] for row in journal][-1] == "land", (
        "the re-run journalled nothing"
    )
    assert len(journal) == 6


def test_a_non_idempotent_arrival_still_counts_every_time_by_default(tmp_path: Path) -> None:
    """Only the land seam opts in (#552): a re-brief is a second brief, honestly."""
    attribute_registry.record_stage_arrival("brief", 552, tmp_path, NOW)
    assert attribute_registry.record_stage_arrival("brief", 552, tmp_path, NOW) == "after_rework"
    journal = stage_rows(attribute_registry.stage_journal(552, tmp_path))
    assert [row["attributes"]["cti.stage.name"] for row in journal] == ["brief", "brief"]


def test_an_unreadable_journal_records_undetermined_never_true(tmp_path: Path) -> None:
    """#490's central criterion: the hole is stated, never padded with a clean past."""
    journal = attribute_registry.stage_journal(490, tmp_path)
    journal.parent.mkdir(parents=True)
    journal.write_text("{not json\n", encoding="utf-8")
    assert attribute_registry.record_stage_arrival("brief", 490, tmp_path, NOW) == "undetermined"
    # The arrival is appended to the damaged journal; the last line is the new one.
    row = json.loads(journal.read_text(encoding="utf-8").splitlines()[-1])
    assert row["attributes"]["cti.stage.first_pass"] == "undetermined"  # noqa: S105 — a stage status, never a credential
    assert row["attributes"]["cti.stage.first_pass"] != "first_time"  # noqa: S105 — a stage status, never a credential


def test_a_journal_line_without_the_stage_field_parses_and_undetermines_the_next_arrival(
    tmp_path: Path,
) -> None:
    """The historical shape (#490 criterion 5): a line the field predates still parses."""
    journal = attribute_registry.stage_journal(490, tmp_path)
    journal.parent.mkdir(parents=True)
    # The journal_line shape as a line written before the stage name existed on it.
    journal.write_text(
        json.dumps(
            {
                "event": "cti.stage.transition",
                "at": NOW - 10,
                "attributes": {"cti.issue": 490},
                "resource": {"service.name": "arma-cti-stage"},
                "exported": False,
                "export_detail": "unreachable:ConnectionRefusedError",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    # The read did not crash, and the arrival the hole precedes says undetermined.
    assert attribute_registry.record_stage_arrival("brief", 490, tmp_path, NOW) == "undetermined"


# ------------------- the absent journal, and the record outside it (#490 round 2, finding 1)


def _dispatch_record(root: Path, dispatch_id: str, issue: int, seat: str) -> None:
    """Lay down one dispatch record as `tools/dispatch.py`'s `write_record` does."""
    directory = root / dispatch_id
    directory.mkdir(parents=True)
    (directory / "dispatch.json").write_text(
        json.dumps(
            {"dispatch_id": dispatch_id, "seat": seat, "issue": issue, "lane": "claude-native"}
        ),
        encoding="utf-8",
    )


def test_an_absent_journal_with_no_history_is_first_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A genuinely new issue has no journal yet, and that one is first time."""
    monkeypatch.setenv("CTI_DISPATCH_DIR", str(tmp_path / "no-records"))
    assert attribute_registry.record_stage_arrival("brief", 511, tmp_path, NOW) == "first_time"


def test_an_absent_journal_with_a_prior_loop_is_undetermined_not_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The transition window's shape: the issue predates the recorder and has a past."""
    monkeypatch.setenv("CTI_DISPATCH_DIR", str(tmp_path / "no-records"))
    (tmp_path / "512").mkdir()
    (tmp_path / "512" / "loop.json").write_text("{}", encoding="utf-8")
    assert attribute_registry.record_stage_arrival("brief", 512, tmp_path, NOW) == "undetermined"
    # The undetermined arrival founds the journal, so the question does not recur.
    assert attribute_registry.record_stage_arrival("implementation", 512, tmp_path, NOW) == (
        "first_time"
    )


def test_an_absent_journal_with_a_pipeline_dispatch_on_the_issue_is_undetermined(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An implementer dispatch predating the recorder says the item moved."""
    records = tmp_path / "records"
    monkeypatch.setenv("CTI_DISPATCH_DIR", str(records))
    _dispatch_record(records, "d-old", 513, "implementer")
    assert attribute_registry.record_stage_arrival("brief", 513, tmp_path, NOW) == "undetermined"


def test_a_recon_dispatch_is_not_pipeline_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Triage names the issue without moving it through the pipeline."""
    records = tmp_path / "records"
    monkeypatch.setenv("CTI_DISPATCH_DIR", str(records))
    _dispatch_record(records, "d-recon", 514, "recon")
    assert attribute_registry.record_stage_arrival("brief", 514, tmp_path, NOW) == "first_time"


def test_this_arrivals_own_dispatch_record_is_not_prior_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`write_record` lays the dispatch down before it records the arrival (#490).

    The record for the dispatch arriving now is passed over, so it is not read
    as prior history: the answer is the pessimistic `after_rework` an empty
    prefix earns (no brief line — its emission failed open), never the
    `undetermined` the scan would grant if its own record counted as evidence.
    """
    records = tmp_path / "records"
    monkeypatch.setenv("CTI_DISPATCH_DIR", str(records))
    _dispatch_record(records, "d-now", 515, "implementer")
    assert (
        attribute_registry.record_stage_arrival(
            "implementation", 515, tmp_path, NOW, dispatch_id="d-now"
        )
        == "after_rework"
    )


def test_a_dispatch_record_that_will_not_read_undetermines_rather_than_cleans(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The seat inside an unreadable record cannot be known, so no clean past."""
    records = tmp_path / "records" / "d-broken"
    records.mkdir(parents=True)
    (records / "dispatch.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("CTI_DISPATCH_DIR", str(tmp_path / "records"))
    assert attribute_registry.record_stage_arrival("brief", 516, tmp_path, NOW) == "undetermined"


# ------------------------- per-stage equality, not a sum (#490 round 2, finding 3)


def test_a_skipped_stage_and_a_doubled_one_do_not_compensate(tmp_path: Path) -> None:
    """Two briefs beside a missing implementation line is rework, not a first pass."""
    journal = attribute_registry.stage_journal(490, tmp_path)
    journal.parent.mkdir(parents=True)
    # Two brief arrivals, but the implementation line never landed between them —
    # the fail-open emission a sum over the prefix would read as one brief's
    # worth of history (2 == the own gate's position, so the sum says first_time).
    brief = (
        json.dumps(
            {
                "event": "cti.stage.transition",
                "at": NOW,
                "attributes": {
                    "cti.stage.name": "brief",
                    "cti.stage.first_pass": "after_rework",
                    "cti.issue": 490,
                },
                "resource": {"service.name": "arma-cti-stage"},
                "exported": False,
                "export_detail": "unreachable:ConnectionRefusedError",
            }
        )
        + "\n"
    )
    journal.write_text(brief + brief, encoding="utf-8")
    assert attribute_registry.record_stage_arrival("own_gate", 490, tmp_path, NOW) == (
        "after_rework"
    ), "brief=2 with no implementation is not brief=1 with one"
