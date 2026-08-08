"""Prospective, lane-blind WIP experiment instrumentation for issue #284.

The bar is fixed before observation. Events are append-only and hash-chained. This tool
cannot dispatch work or edit queue policy; adoption remains a human act.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import admission
import queue_policy

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence

VERSION: Final = 1
BAR_ID: Final = "cti.wip-trial/284/v1"
ISSUES_PER_BLOCK: Final = 10
BLOCKS_PER_STAGE: Final = 4
MATERIAL_RATE_RATIO: Final = 1.15
MAX_P90_RATIO: Final = 1.25
MIN_HIGH_EXPOSURE: Final = 0.50
MATURITY_SECONDS: Final = 7 * 24 * 60 * 60
BLOCK_TIMEOUT_SECONDS: Final = 72 * 60 * 60
ALPHA: Final = 0.10
STAGES: Final[dict[int, tuple[int, int]]] = {1: (3, 5), 2: (5, 7), 3: (7, 10)}
ORDERS: Final = (
    ("safe", "candidate", "candidate", "safe"),
    ("candidate", "safe", "safe", "candidate"),
)
OBSERVATION_KINDS: Final = frozenset({"dispatch", "result", "close", "watch_report"})
NON_RESULTS: Final = frozenset(
    {"quota_exhausted", "infra_unavailable", "provider_refused", "untyped_harness_failure"}
)
CONFLICT_KINDS: Final = frozenset({"rebase_conflict", "surface_conflict", "not_fast_forward"})
CRITICAL_KINDS: Final = frozenset(
    {
        "red_landing",
        "non_result_as_result",
        "wrong_issue",
        "semantic_gate_bypass",
        "duplicate_work",
        "lost_work",
    }
)
EVENT_KINDS: Final = frozenset(
    {
        "block_start",
        "observation",
        "ready",
        "rework",
        "conflict",
        "maturity",
        "critical",
        "non_result",
        "change",
        "restore",
    }
)
DEFAULT_TRIAL_DIR: Final = Path.home() / ".arma-cti" / "wip-trial"
MANIFEST_FILE: Final = "manifest.json"
EVENTS_FILE: Final = "events.jsonl"
RESULT_FILE: Final = "result.json"
EXIT_REFUSED: Final = 1


class Refusal(NamedTuple):
    """A named fail-closed refusal with evidence and a remedy."""

    kind: str
    found: tuple[str, ...]
    action: str

    def lines(self) -> tuple[str, ...]:
        """Render the typed refusal for a caller."""
        return (f"refusal={self.kind}", *self.found, f"action={self.action}")


class InvalidDocumentError(TypeError):
    """A validated document did not retain its promised type."""


class BlockResult(NamedTuple):
    """All derived measurements for one immutable ten-issue block."""

    number: int
    arm: str
    limit: int
    issues: tuple[int, ...]
    started_at: float | None
    closed_at: float | None
    elapsed_hours: float | None
    clean_closures: int
    fidelity_reached: bool
    high_exposure: float | None
    occupancy_complete: bool
    rework_issues: int
    conflicts: int
    unclean_issues: int
    mature_issues: int
    critical_failures: tuple[str, ...]
    flow_hours: tuple[float, ...]
    gate_reds: int
    flake_reruns: int
    non_results: tuple[str, ...]
    changes: tuple[str, ...]


class Analysis(NamedTuple):
    """The stage verdict and the evidence from which it was obtained."""

    verdict: str
    reasons: tuple[str, ...]
    blocks: tuple[BlockResult, ...]
    safe_rate: float | None
    candidate_rate: float | None
    rate_ratio: float | None
    rate_ratio_interval: tuple[float, float] | None
    safe_p90: float | None
    candidate_p90: float | None
    recommendation: str


def canonical(document: Mapping[str, object]) -> str:
    """Stable bytes for hashing manifests and journal entries."""
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _mapping(value: object) -> dict[str, object]:
    """Narrow a decoded JSON object to string keys."""
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _integer(document: Mapping[str, object], key: str) -> int:
    """Read an integer already validated by the event or manifest parser."""
    return _as_int(document[key])


def _as_int(value: object) -> int:
    """Narrow one decoded JSON value to an integer."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise InvalidDocumentError
    return value


def _number(document: Mapping[str, object], key: str) -> float:
    """Read a number already validated by the event or manifest parser."""
    return _as_float(document[key])


def _as_float(value: object) -> float:
    """Narrow one decoded JSON value to a floating-point number."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise InvalidDocumentError
    return float(value)


def _list(document: Mapping[str, object], key: str) -> list[object]:
    """Read a list already validated by the event or manifest parser."""
    value = document[key]
    if not isinstance(value, list):
        raise InvalidDocumentError
    found: list[object] = []
    found.extend(value)
    return found


def digest(document: Mapping[str, object]) -> str:
    """Hash one canonical document."""
    return hashlib.sha256(canonical(document).encode()).hexdigest()


def block_order(source_sha: str) -> tuple[str, ...]:
    """Choose ABBA or BAAB without operator discretion."""
    return ORDERS[int(hashlib.sha256(source_sha.encode()).hexdigest(), 16) % len(ORDERS)]


def thresholds() -> dict[str, object]:
    """Return the pre-registered bar copied into every manifest."""
    return {
        "issues_per_block": ISSUES_PER_BLOCK,
        "blocks_per_stage": BLOCKS_PER_STAGE,
        "material_rate_ratio": MATERIAL_RATE_RATIO,
        "max_p90_ratio": MAX_P90_RATIO,
        "minimum_high_exposure": MIN_HIGH_EXPOSURE,
        "maturity_seconds": MATURITY_SECONDS,
        "block_timeout_seconds": BLOCK_TIMEOUT_SECONDS,
        "throughput_interval": "exact conditional Poisson 90%",
        "clean_close_per_block": ISSUES_PER_BLOCK,
        "critical_failures": 0,
        "unclean_per_block": 1,
        "candidate_unclean_not_above_safe": True,
        "candidate_rework_not_above_safe": True,
        "candidate_conflicts_not_above_safe": True,
        "candidate_faster_in_each_adjacent_pair": True,
        "admission_bar_id": admission.BAR_ID,
        "admission_part_a": list(admission.PART_A_KEYS),
        "unclean_reasons": list(admission.UNCLEAN_REASONS),
        "orchestration_trial_bar_id": admission.TRIAL_BAR_ID,
        "orchestration_trial_criteria": list(admission.TRIAL_CRITERION_KEYS),
    }


def make_manifest(  # noqa: PLR0911, PLR0913 -- each pre-start refusal is a registered guard
    *,
    stage: int,
    source_sha: str,
    eligible_issues: Sequence[int],
    policy: Mapping[str, object],
    routes: Sequence[Mapping[str, object]],
    created_at: float,
    previous_result: Mapping[str, object] | None = None,
) -> tuple[dict[str, object] | None, Refusal | None]:
    """Pre-register a stage from snapshots taken before its first observation."""
    if stage not in STAGES:
        return None, Refusal(
            "stage_invalid",
            (f"stage={stage}", "known=1 2 3"),
            "Test only the adjacent 3→5, 5→7, and 7→10 stages ruled on #284.",
        )
    safe, candidate = STAGES[stage]
    if stage > 1 and (
        previous_result is None
        or previous_result.get("verdict") != "pass"
        or previous_result.get("candidate_limit") != safe
    ):
        return None, Refusal(
            "previous_stage_not_cleared",
            (f"stage={stage}", f"required_safe={safe}"),
            "A higher candidate is tested only after the adjacent lower level matures and passes.",
        )
    unique = tuple(dict.fromkeys(int(issue) for issue in eligible_issues))
    if len(unique) != len(eligible_issues) or any(issue <= 0 for issue in unique):
        return None, Refusal(
            "eligible_invalid",
            (f"eligible={','.join(map(str, eligible_issues))}",),
            "Record each positive eligible issue once, in `just queue next` order.",
        )
    if len(unique) < 2 * candidate:
        return None, Refusal(
            "eligible_underfilled",
            (f"eligible={len(unique)}", f"required={2 * candidate}"),
            "Retain the safe limit until at least twice the candidate WIP is eligible.",
        )
    dispatchable = [route for route in routes if route.get("dispatchable") is True]
    route_keys = {
        (str(route.get("lane", "")), str(route.get("seat", ""))) for route in dispatchable
    }
    if len(route_keys) < len(ORDERS):
        return None, Refusal(
            "routes_underfilled",
            (f"dispatchable_lane_seats={len(route_keys)}", "required=2"),
            "Do not start while one lane/seat configuration is carrying the system.",
        )
    wip = policy.get("wip_limit")
    policy_limit = wip.get("value") if isinstance(wip, dict) else None
    if policy_limit != safe:
        return None, Refusal(
            "safe_limit_mismatch",
            (f"policy_limit={policy_limit}", f"stage_safe={safe}"),
            "Restore the preceding safe limit before pre-registering the stage.",
        )
    core: dict[str, object] = {
        "version": VERSION,
        "bar_id": f"{BAR_ID}/stage-{stage}/{source_sha[:12]}",
        "issue": 284,
        "created_at": created_at,
        "source_sha": source_sha,
        "stage": stage,
        "safe_limit": safe,
        "candidate_limit": candidate,
        "block_order": list(block_order(source_sha)),
        "eligible_issues": list(unique),
        "selection": "next eligible issues in `just queue next` order; never hand-picked",
        "policy_snapshot": dict(policy),
        "route_snapshot": [dict(route) for route in routes],
        "previous_result": dict(previous_result) if previous_result is not None else None,
        "thresholds": thresholds(),
        "historical_closes": "context_only",
        "elapsed_time": "first dispatch through tenth close; no pauses or exclusions",
        "mix_diagnostics": ["gate", "lane", "profile", "seat", "landed_change_size"],
        "confounders": [
            "dispatch-follow and underfill reporting changed throughput at every limit",
            "orchestrator hand-finishes every Codex landing under #265",
            "z.ai weekly quota outage leaves one foreign lane through 2026-08-12T18:31:37Z",
            "in-world work is bounded by the three-slot corpus tier",
        ],
    }
    core["manifest_sha256"] = digest(core)
    return core, None


def validate_manifest(document: object) -> tuple[dict[str, object] | None, Refusal | None]:
    """Refuse a manifest whose schema, bar, or hash differs from the pre-registration."""
    if not isinstance(document, dict):
        return None, Refusal(
            "manifest_invalid", ("type=not-object",), "Start a new bar; do not repair history."
        )
    document = _mapping(document)
    expected = document.get("manifest_sha256")
    body = {key: value for key, value in document.items() if key != "manifest_sha256"}
    if expected != digest(body):
        return None, Refusal(
            "manifest_changed",
            (f"bar_id={document.get('bar_id', '')}",),
            "Start a new bar id. A started bar is immutable.",
        )
    stage = document.get("stage")
    if not isinstance(stage, int) or stage not in STAGES:
        return None, Refusal("manifest_invalid", (f"stage={stage}",), "Start a valid bar.")
    safe, candidate = STAGES[stage]
    if (
        document.get("safe_limit") != safe
        or document.get("candidate_limit") != candidate
        or document.get("thresholds") != thresholds()
    ):
        return None, Refusal(
            "bar_amended",
            (f"bar_id={document.get('bar_id', '')}",),
            "Start a new bar id; never move criteria after observation.",
        )
    return document, None


def event_hash(previous_hash: str, event: Mapping[str, object]) -> str:
    """Hash an event against the preceding journal link."""
    return digest({"previous_hash": previous_hash, "event": dict(event)})


def append_event(
    manifest: Mapping[str, object], existing: Sequence[object], event: Mapping[str, object]
) -> tuple[dict[str, object] | None, Refusal | None]:
    """Validate then extend the journal by one event."""
    _, refusal = validate_events(manifest, existing)
    if refusal is not None:
        return None, refusal
    previous = str(manifest["manifest_sha256"])
    if existing and isinstance(existing[-1], dict):
        previous = str(existing[-1].get("event_sha256", ""))
    body = {"bar_id": manifest["bar_id"], **dict(event)}
    row = {
        **body,
        "previous_hash": previous,
        "event_sha256": event_hash(previous, body),
    }
    _, refusal = validate_events(manifest, [*existing, row])
    return (row, None) if refusal is None else (None, refusal)


def validate_events(  # noqa: C901, PLR0911, PLR0912 -- malformed history has typed refusals
    manifest: Mapping[str, object], rows: Sequence[object]
) -> tuple[tuple[dict[str, object], ...], Refusal | None]:
    """Validate the journal chain and every cross-event invariant."""
    previous = str(manifest["manifest_sha256"])
    events: list[dict[str, object]] = []
    blocks: dict[int, tuple[int, ...]] = {}
    issue_blocks: dict[int, int] = {}
    ready_issues: set[int] = set()
    closed_issues: set[int] = set()
    last_occupancy: int | None = None
    restored_blocks: set[int] = set()
    for index, raw in enumerate(rows, start=1):
        if not isinstance(raw, dict):
            return (), Refusal(
                "event_invalid",
                (f"line={index}", "type=not-object"),
                "Do not edit the journal; start a new bar if history is damaged.",
            )
        normalized = _mapping(raw)
        recorded_previous = normalized.get("previous_hash")
        recorded_hash = normalized.get("event_sha256")
        event: dict[str, object] = {
            key: value
            for key, value in normalized.items()
            if key not in {"previous_hash", "event_sha256"}
        }
        if recorded_previous != previous or recorded_hash != event_hash(previous, event):
            return (), Refusal(
                "event_chain_broken",
                (f"line={index}",),
                "Do not edit or reorder observations; start a new bar.",
            )
        if event.get("bar_id") != manifest.get("bar_id"):
            return (), Refusal(
                "event_wrong_bar",
                (f"line={index}",),
                "Record observations under the bar that pre-registered them.",
            )
        at = event.get("at")
        if (
            not isinstance(at, (int, float))
            or isinstance(at, bool)
            or at < _number(manifest, "created_at")
        ):
            return (), Refusal(
                "event_before_bar",
                (f"line={index}", f"at={at}"),
                "Historical observations are context only; record prospectively.",
            )
        kind = event.get("kind")
        if kind not in EVENT_KINDS:
            return (), Refusal(
                "event_kind_unknown",
                (f"line={index}", f"kind={kind}"),
                "Unknown data is never zero; use a documented event kind.",
            )
        if kind == "block_start":
            if blocks:
                previous_block = blocks[len(blocks)]
                if not set(previous_block) <= closed_issues or last_occupancy != 0:
                    return (), Refusal(
                        "previous_block_not_drained",
                        (f"block={len(blocks)}", f"last_occupancy={last_occupancy}"),
                        "Close the whole cohort and drain WIP to zero before assigning the next.",
                    )
                previous_arm = _list(manifest, "block_order")[len(blocks) - 1]
                if previous_arm == "candidate" and len(blocks) not in restored_blocks:
                    return (), Refusal(
                        "safe_limit_not_restored",
                        (f"block={len(blocks)}",),
                        "Record the ruled safe-limit restore before assigning another block.",
                    )
            refusal = _validate_block_start(manifest, event, blocks, issue_blocks)
            if refusal is not None:
                return (), refusal
            number = _integer(event, "block")
            issues = tuple(_as_int(issue) for issue in _list(event, "issues"))
            blocks[number] = issues
            issue_blocks.update(dict.fromkeys(issues, number))
        elif kind == "restore":
            refusal = _validate_restore(manifest, event, blocks)
            if refusal is not None:
                return (), refusal
            restored_blocks.add(_integer(event, "block"))
        else:
            refusal = _validate_detail_event(event, issue_blocks, ready_issues)
            if refusal is not None:
                return (), refusal
            if kind == "ready":
                ready_issues.add(_integer(event, "issue"))
            if kind == "observation":
                last_occupancy = _integer(event, "occupancy")
                if event.get("event") == "close":
                    closed_issues.add(_integer(event, "issue"))
        events.append(event)
        previous = str(recorded_hash)
    return tuple(events), None


def _validate_restore(
    manifest: Mapping[str, object],
    event: Mapping[str, object],
    blocks: Mapping[int, tuple[int, ...]],
) -> Refusal | None:
    """Validate evidence that the orchestrator restored the safe policy."""
    block = event.get("block")
    if not isinstance(block, int) or block not in blocks:
        return Refusal(
            "restore_without_block",
            (f"block={block}",),
            "A restore records the candidate block it followed.",
        )
    arm = _list(manifest, "block_order")[block - 1]
    if arm != "candidate" or event.get("limit") != manifest.get("safe_limit"):
        return Refusal(
            "restore_mismatch",
            (f"block={block}", f"arm={arm}", f"limit={event.get('limit')}"),
            "After a candidate block, record the preceding safe limit exactly.",
        )
    if not str(event.get("source", "")).strip():
        return Refusal(
            "provenance_missing",
            ("kind=restore",),
            "Link the `just queue wip` ruling output that restored the safe limit.",
        )
    return None


def _validate_block_start(  # noqa: PLR0911 -- immutable cohort guards fail separately
    manifest: Mapping[str, object],
    event: Mapping[str, object],
    blocks: Mapping[int, tuple[int, ...]],
    issue_blocks: Mapping[int, int],
) -> Refusal | None:
    number = event.get("block")
    expected = len(blocks) + 1
    if number != expected or not isinstance(number, int) or number > BLOCKS_PER_STAGE:
        return Refusal(
            "block_out_of_order",
            (f"block={number}", f"expected={expected}"),
            "Drain and finish each block before assigning the next.",
        )
    issues = event.get("issues")
    eligible = event.get("eligible")
    size = len(issues) if isinstance(issues, list) else "invalid"
    if (
        not isinstance(issues, list)
        or len(issues) != ISSUES_PER_BLOCK
        or len(set(issues)) != ISSUES_PER_BLOCK
        or any(
            not isinstance(issue, int) or isinstance(issue, bool) or issue <= 0 for issue in issues
        )
    ):
        return Refusal(
            "cohort_invalid",
            (f"block={number}", f"size={size}"),
            f"Assign exactly {ISSUES_PER_BLOCK} distinct positive issue numbers.",
        )
    issue_numbers = tuple(_as_int(issue) for issue in issues)
    repeated = sorted(set(issue_numbers) & set(issue_blocks))
    if repeated:
        return Refusal(
            "issue_straddles_blocks",
            (f"issues={','.join(map(str, repeated))}",),
            "Every issue belongs to exactly one immutable block.",
        )
    if not isinstance(eligible, list) or issues != eligible[:ISSUES_PER_BLOCK]:
        return Refusal(
            "cohort_hand_picked",
            (f"block={number}",),
            "Use the first ten issues in the recorded `just queue next` order.",
        )
    order = manifest["block_order"]
    arm = order[number - 1] if isinstance(order, list) else ""
    expected_limit = manifest["safe_limit"] if arm == "safe" else manifest["candidate_limit"]
    if event.get("arm") != arm or event.get("limit") != expected_limit:
        return Refusal(
            "block_treatment_mismatch",
            (f"block={number}", f"expected_arm={arm}", f"expected_limit={expected_limit}"),
            "Restore the pre-registered order and limit before the first dispatch.",
        )
    if event.get("orchestration_trial") not in {
        "not_started",
        "running",
        "cleared",
        "failed",
    }:
        return Refusal(
            "orchestration_trial_unreadable",
            (f"block={number}",),
            "Record #242's observed trial standing; there is no default.",
        )
    if arm == "candidate" and event.get("orchestration_trial") != "cleared":
        return Refusal(
            "orchestration_trial_running",
            (f"block={number}", f"state={event.get('orchestration_trial')}"),
            "Candidate blocks wait until #242's orchestration-seat trial has cleared.",
        )
    if not str(event.get("source", "")).strip():
        return Refusal(
            "provenance_missing",
            (f"block={number}",),
            "Every cohort links to the queue selection that produced it.",
        )
    return None


def _validate_detail_event(  # noqa: C901, PLR0911, PLR0912 -- one branch per event schema
    event: Mapping[str, object],
    issue_blocks: Mapping[int, int],
    ready_issues: set[int],
) -> Refusal | None:
    kind = str(event.get("kind", ""))
    source = event.get("source")
    if not isinstance(source, str) or not source.strip():
        return Refusal(
            "provenance_missing",
            (f"kind={kind}",),
            "Supply the source record or explicit judgement supporting this event.",
        )
    issue = event.get("issue")
    if kind != "change":
        if not isinstance(issue, int) or issue not in issue_blocks:
            return Refusal(
                "issue_outside_cohort",
                (f"kind={kind}", f"issue={issue}"),
                "Record only issues assigned to this bar's immutable blocks.",
            )
        if event.get("block") != issue_blocks[issue]:
            return Refusal(
                "event_wrong_block",
                (f"issue={issue}", f"block={event.get('block')}"),
                "An issue cannot straddle blocks.",
            )
    if kind == "observation":
        if event.get("event") not in OBSERVATION_KINDS:
            return Refusal(
                "observation_invalid",
                (f"event={event.get('event')}",),
                "Sample occupancy at dispatch, result, close, and watch-report reads.",
            )
        occupancy = event.get("occupancy")
        if (
            not isinstance(occupancy, int)
            or isinstance(occupancy, bool)
            or occupancy < 0
            or occupancy > max(candidate for _, candidate in STAGES.values())
        ):
            return Refusal(
                "occupancy_invalid",
                (f"occupancy={occupancy}",),
                "Record the in-flight floor from 0 through 10; unknown is not zero.",
            )
    elif kind == "ready" and event.get("corrective") is not False:
        return Refusal(
            "ready_invalid",
            (f"issue={issue}",),
            "The first ready point is not itself corrective rework.",
        )
    elif kind == "rework" and event.get("corrective") is not True:
        return Refusal(
            "rework_unclassified",
            (f"issue={issue}",),
            "Explicitly classify corrective rework; there is no default.",
        )
    elif kind == "rework" and issue not in ready_issues:
        return Refusal(
            "rework_before_ready",
            (f"issue={issue}",),
            "Corrective rework begins only after the first sourced ready point.",
        )
    elif kind == "conflict" and event.get("conflict") not in CONFLICT_KINDS:
        return Refusal(
            "conflict_unknown",
            (f"conflict={event.get('conflict')}",),
            "Use the pre-registered conflict vocabulary.",
        )
    elif kind == "maturity":
        refusal = _validate_maturity(event)
        if refusal is not None:
            return refusal
    elif kind == "critical" and event.get("failure") not in CRITICAL_KINDS:
        return Refusal(
            "critical_unknown",
            (f"failure={event.get('failure')}",),
            "Use the pre-registered critical-failure vocabulary.",
        )
    elif kind == "non_result" and event.get("failure_class") not in NON_RESULTS:
        return Refusal(
            "non_result_unknown",
            (f"class={event.get('failure_class')}",),
            "Typed non-results remain elapsed time and do not default to rework.",
        )
    elif kind == "change" and not str(event.get("description", "")).strip():
        return Refusal(
            "change_unclassified",
            (),
            "Record unavoidable concurrent process or lane changes explicitly.",
        )
    return None


def _validate_maturity(event: Mapping[str, object]) -> Refusal | None:
    """Reuse admission's outcome vocabulary and refuse unobserved counts."""
    issue = event.get("issue")
    if event.get("clean_close") not in (True, False) or event.get("unclean") not in (
        True,
        False,
    ):
        return Refusal(
            "maturity_unclassified",
            (f"issue={issue}",),
            "Audit clean close and seven-day unclean explicitly; absence is not a pass.",
        )
    reasons = event.get("unclean_reasons", [])
    if not isinstance(reasons, list) or any(
        reason not in admission.UNCLEAN_REASONS for reason in reasons
    ):
        return Refusal(
            "unclean_reason_unknown",
            (f"issue={issue}",),
            f"Reuse admission's vocabulary: {' '.join(admission.UNCLEAN_REASONS)}.",
        )
    if bool(reasons) != bool(event.get("unclean")):
        return Refusal(
            "unclean_reason_mismatch",
            (f"issue={issue}",),
            "An unclean issue names a reason; a clean one names none.",
        )
    for count in ("gate_reds", "flake_reruns"):
        value = event.get(count)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            return Refusal(
                "maturity_count_invalid",
                (f"issue={issue}", f"field={count}"),
                "Record a non-negative observed count; unknown is not zero.",
            )
    return None


def _for_block(
    events: Sequence[Mapping[str, object]], block: int, kind: str = ""
) -> list[Mapping[str, object]]:
    return [
        event
        for event in events
        if event.get("block") == block and (not kind or event.get("kind") == kind)
    ]


def _percentile(values: Sequence[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(probability * len(ordered)) - 1)]


def _empty_block(manifest: Mapping[str, object], number: int) -> BlockResult:
    order = manifest["block_order"]
    arm = str(order[number - 1]) if isinstance(order, list) else ""
    limit = _as_int(manifest["safe_limit"] if arm == "safe" else manifest["candidate_limit"])
    return BlockResult(
        number=number,
        arm=arm,
        limit=limit,
        issues=(),
        started_at=None,
        closed_at=None,
        elapsed_hours=None,
        clean_closures=0,
        fidelity_reached=False,
        high_exposure=None,
        occupancy_complete=False,
        rework_issues=0,
        conflicts=0,
        unclean_issues=0,
        mature_issues=0,
        critical_failures=(),
        flow_hours=(),
        gate_reds=0,
        flake_reruns=0,
        non_results=(),
        changes=(),
    )


def _block_result(
    manifest: Mapping[str, object], events: Sequence[Mapping[str, object]], number: int
) -> BlockResult:
    starts = [
        event
        for event in events
        if event.get("kind") == "block_start" and event.get("block") == number
    ]
    if not starts:
        return _empty_block(manifest, number)
    start = starts[0]
    issues = tuple(_as_int(issue) for issue in _list(start, "issues"))
    observations = _for_block(events, number, "observation")
    dispatches: dict[int, float] = {}
    closes: dict[int, float] = {}
    observed_kinds: dict[int, set[str]] = {issue: set() for issue in issues}
    for event in observations:
        issue = _integer(event, "issue")
        observed_kinds[issue].add(str(event["event"]))
        if event.get("event") == "dispatch":
            dispatches.setdefault(issue, _number(event, "at"))
        elif event.get("event") == "close":
            closes[issue] = _number(event, "at")
    first_dispatch = min(dispatches.values()) if dispatches else None
    last_close = max(closes.values()) if len(closes) == ISSUES_PER_BLOCK else None
    elapsed = (
        (last_close - first_dispatch) / 3600
        if first_dispatch is not None and last_close is not None
        else None
    )

    maturity = {_integer(event, "issue"): event for event in _for_block(events, number, "maturity")}
    clean = sum(1 for event in maturity.values() if event.get("clean_close") is True)
    mature = sum(
        1
        for issue, event in maturity.items()
        if issue in closes and _number(event, "at") >= closes[issue] + MATURITY_SECONDS
    )
    unclean = sum(
        1
        for issue, event in maturity.items()
        if issue in closes
        and event.get("unclean") is True
        and _number(event, "at") >= closes[issue] + MATURITY_SECONDS
    )
    flows = tuple(
        (closes[issue] - dispatched) / 3600
        for issue, dispatched in dispatches.items()
        if issue in closes
    )

    required = {"dispatch", "result", "close"}
    occupancy_complete = all(required <= observed_kinds[issue] for issue in issues)
    reached = any(
        _integer(event, "occupancy") >= _integer(start, "limit") for event in observations
    )
    high_exposure: float | None = None
    if first_dispatch is not None and last_close is not None:
        timeline = sorted(
            (_number(event, "at"), _integer(event, "occupancy"))
            for event in observations
            if first_dispatch <= _number(event, "at") <= last_close
        )
        if timeline and timeline[0][0] == first_dispatch and last_close > first_dispatch:
            high_seconds = 0.0
            for index, (at, occupancy) in enumerate(timeline):
                next_at = timeline[index + 1][0] if index + 1 < len(timeline) else last_close
                if occupancy > _integer(manifest, "safe_limit"):
                    high_seconds += max(0.0, next_at - at)
            high_exposure = high_seconds / (last_close - first_dispatch)

    critical = tuple(str(event["failure"]) for event in _for_block(events, number, "critical"))
    non_results = tuple(
        str(event["failure_class"]) for event in _for_block(events, number, "non_result")
    )
    changes = tuple(str(event["description"]) for event in _for_block(events, number, "change"))
    return BlockResult(
        number=number,
        arm=str(start["arm"]),
        limit=_integer(start, "limit"),
        issues=issues,
        started_at=first_dispatch,
        closed_at=last_close,
        elapsed_hours=elapsed,
        clean_closures=clean,
        fidelity_reached=reached,
        high_exposure=high_exposure,
        occupancy_complete=occupancy_complete,
        rework_issues=len(
            {_integer(event, "issue") for event in _for_block(events, number, "rework")}
        ),
        conflicts=len(_for_block(events, number, "conflict")),
        unclean_issues=unclean,
        mature_issues=mature,
        critical_failures=critical,
        flow_hours=flows,
        gate_reds=sum(_integer(event, "gate_reds") for event in maturity.values()),
        flake_reruns=sum(_integer(event, "flake_reruns") for event in maturity.values()),
        non_results=non_results,
        changes=changes,
    )


def _binomial_cdf(k: int, n: int, probability: float) -> float:
    return sum(
        math.comb(n, index) * probability**index * (1 - probability) ** (n - index)
        for index in range(k + 1)
    )


def _solve_probability(
    function: Callable[[float], float], target: float, *, increasing: bool
) -> float:
    low, high = 0.0, 1.0
    for _ in range(100):
        middle = (low + high) / 2
        value = function(middle)
        if increasing:
            low, high = (middle, high) if value < target else (low, middle)
        else:
            low, high = (middle, high) if value > target else (low, middle)
    return (low + high) / 2


def poisson_rate_ratio_interval(
    candidate_events: int,
    candidate_time: float,
    safe_events: int,
    safe_time: float,
) -> tuple[float, float] | None:
    """Exact conditional Poisson interval via Clopper-Pearson's event split."""
    total = candidate_events + safe_events
    if total == 0 or candidate_time <= 0 or safe_time <= 0:
        return None
    tail = ALPHA / 2
    lower_p = (
        0.0
        if candidate_events == 0
        else _solve_probability(
            lambda probability: 1 - _binomial_cdf(candidate_events - 1, total, probability),
            tail,
            increasing=True,
        )
    )
    upper_p = (
        1.0
        if candidate_events == total
        else _solve_probability(
            lambda probability: _binomial_cdf(candidate_events, total, probability),
            tail,
            increasing=False,
        )
    )
    scale = safe_time / candidate_time
    lower = 0.0 if lower_p == 0 else lower_p / (1 - lower_p) * scale
    upper = math.inf if upper_p == 1 else upper_p / (1 - upper_p) * scale
    return lower, upper


def analyse(  # noqa: C901, PLR0912, PLR0915 -- implements the registered decision table
    manifest: Mapping[str, object], events: Sequence[Mapping[str, object]], now: float
) -> Analysis:
    """Apply the registered stopping and promotion rules without exclusions."""
    blocks = tuple(
        _block_result(manifest, events, number) for number in range(1, BLOCKS_PER_STAGE + 1)
    )
    safe = tuple(block for block in blocks if block.arm == "safe")
    candidate = tuple(block for block in blocks if block.arm == "candidate")
    reasons: list[str] = []

    critical = [failure for block in blocks for failure in block.critical_failures]
    if critical:
        reasons.append("critical_failure=" + ",".join(critical))
    if any(event.get("kind") == "change" for event in events):
        reasons.append("concurrent_change_requires_new_bar")
    restored = {_integer(event, "block") for event in events if event.get("kind") == "restore"}
    missing_restores = [
        block.number
        for block in candidate
        if block.closed_at is not None and block.number not in restored
    ]
    if missing_restores:
        reasons.append("safe_limit_restore_unrecorded=" + ",".join(map(str, missing_restores)))
    incomplete = [block.number for block in blocks if block.elapsed_hours is None]
    if incomplete:
        reasons.append("blocks_incomplete=" + ",".join(map(str, incomplete)))
    timed_out = [
        block.number
        for block in blocks
        if block.started_at is not None
        and block.closed_at is None
        and now - block.started_at > BLOCK_TIMEOUT_SECONDS
    ]
    if timed_out:
        reasons.append("blocks_timed_out=" + ",".join(map(str, timed_out)))
    all_mature = all(block.mature_issues == ISSUES_PER_BLOCK for block in blocks)
    if all_mature and any(block.clean_closures != ISSUES_PER_BLOCK for block in blocks):
        reasons.append("clean_close_guardrail")
    if not all_mature:
        reasons.append("seven_day_outcomes_immature")
    if all_mature and any(block.unclean_issues > 1 for block in blocks):
        reasons.append("unclean_block_guardrail")
    if all_mature and sum(block.unclean_issues for block in candidate) > sum(
        block.unclean_issues for block in safe
    ):
        reasons.append("candidate_unclean_above_safe")
    if sum(block.rework_issues for block in candidate) > sum(block.rework_issues for block in safe):
        reasons.append("candidate_rework_above_safe")
    if sum(block.conflicts for block in candidate) > sum(block.conflicts for block in safe):
        reasons.append("candidate_conflicts_above_safe")
    fidelity_misses = [
        block.number
        for block in candidate
        if not block.fidelity_reached
        or not block.occupancy_complete
        or block.high_exposure is None
        or block.high_exposure < MIN_HIGH_EXPOSURE
    ]
    if fidelity_misses:
        reasons.append("candidate_fidelity_failed=" + ",".join(map(str, fidelity_misses)))

    safe_hours = sum(block.elapsed_hours or 0 for block in safe)
    candidate_hours = sum(block.elapsed_hours or 0 for block in candidate)
    safe_clean = sum(block.clean_closures for block in safe)
    candidate_clean = sum(block.clean_closures for block in candidate)
    safe_rate = safe_clean / safe_hours if safe_hours else None
    candidate_rate = candidate_clean / candidate_hours if candidate_hours else None
    ratio = candidate_rate / safe_rate if safe_rate and candidate_rate is not None else None
    interval = poisson_rate_ratio_interval(candidate_clean, candidate_hours, safe_clean, safe_hours)
    if interval is not None and interval[0] <= 1.0 <= interval[1]:
        reasons.append("rate_interval_crosses_1_adoption_is_provisional")
    all_closed = all(block.elapsed_hours is not None for block in blocks)
    if not all_closed:
        reasons.append("throughput_unavailable")
    elif ratio is None or ratio < MATERIAL_RATE_RATIO:
        reasons.append("material_throughput_not_met")

    paired_faster = True
    for left, right in ((blocks[0], blocks[1]), (blocks[2], blocks[3])):
        candidate_block = left if left.arm == "candidate" else right
        safe_block = right if left.arm == "candidate" else left
        if (
            candidate_block.elapsed_hours is None
            or safe_block.elapsed_hours is None
            or candidate_block.elapsed_hours >= safe_block.elapsed_hours
        ):
            paired_faster = False
    if all_closed and not paired_faster:
        reasons.append("candidate_not_faster_in_both_pairs")

    safe_p90 = _percentile(tuple(flow for block in safe for flow in block.flow_hours), 0.90)
    candidate_p90 = _percentile(
        tuple(flow for block in candidate for flow in block.flow_hours), 0.90
    )
    if safe_p90 is None or candidate_p90 is None:
        reasons.append("p90_unavailable")
    elif candidate_p90 > MAX_P90_RATIO * safe_p90:
        reasons.append("p90_guardrail")

    failures = {
        "critical_failure",
        "blocks_timed_out",
        "clean_close_guardrail",
        "unclean_block_guardrail",
        "candidate_unclean_above_safe",
        "candidate_rework_above_safe",
        "candidate_conflicts_above_safe",
        "material_throughput_not_met",
        "candidate_not_faster_in_both_pairs",
        "p90_guardrail",
        "safe_limit_restore_unrecorded",
    }
    inconclusive = {
        "concurrent_change_requires_new_bar",
        "blocks_incomplete",
        "seven_day_outcomes_immature",
        "candidate_fidelity_failed",
        "throughput_unavailable",
        "p90_unavailable",
    }
    reason_kinds = {reason.split("=", 1)[0] for reason in reasons}
    if reason_kinds & failures:
        verdict = "fail"
    elif reason_kinds & inconclusive:
        verdict = "inconclusive"
    else:
        verdict = "pass"

    safe_limit = _integer(manifest, "safe_limit")
    candidate_limit = _integer(manifest, "candidate_limit")
    if verdict == "pass":
        recommendation = (
            f"candidate {candidate_limit} clears as the lowest tested passing level. "
            f"Human adoption, if chosen: `just queue wip --limit {candidate_limit} "
            f'--ruling "WIP experiment #284 matured pass"`'
        )
    else:
        recommendation = (
            f"retain {safe_limit}. Restore/confirm it with `just queue wip --limit "
            f'{safe_limit} --ruling "WIP experiment #284 {verdict}"`'
        )
    return Analysis(
        verdict,
        tuple(dict.fromkeys(reasons)),
        blocks,
        safe_rate,
        candidate_rate,
        ratio,
        interval,
        safe_p90,
        candidate_p90,
        recommendation,
    )


def result_document(
    manifest: Mapping[str, object], result: Analysis, generated_at: float
) -> dict[str, object]:
    """Machine-readable result whose summary derives from the raw block rows."""
    return {
        "version": VERSION,
        "bar_id": manifest["bar_id"],
        "safe_limit": manifest["safe_limit"],
        "candidate_limit": manifest["candidate_limit"],
        "generated_at": generated_at,
        "verdict": result.verdict,
        "reasons": list(result.reasons),
        "safe_rate": result.safe_rate,
        "candidate_rate": result.candidate_rate,
        "rate_ratio": result.rate_ratio,
        "rate_ratio_interval_90": (
            list(result.rate_ratio_interval) if result.rate_ratio_interval else None
        ),
        "safe_p90_hours": result.safe_p90,
        "candidate_p90_hours": result.candidate_p90,
        "recommendation": result.recommendation,
        "blocks": [block._asdict() for block in result.blocks],
    }


def markdown_report(manifest: Mapping[str, object], result: Analysis) -> str:
    """Paste-ready result with raw cohorts below the decision."""
    ratio = "unknown" if result.rate_ratio is None else f"{result.rate_ratio:.3f}"
    interval = "unknown"
    if result.rate_ratio_interval is not None:
        interval = f"{result.rate_ratio_interval[0]:.3f}-{result.rate_ratio_interval[1]:.3f}"
    lines = [
        f"## WIP trial `{manifest['bar_id']}` — **{result.verdict}**",
        "",
        (
            "| Block | Arm / limit | Cohort | Elapsed h | High exposure | Clean | "
            "Rework | Conflicts | 7-day unclean |"
        ),
        "|---:|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for block in result.blocks:
        elapsed = "—" if block.elapsed_hours is None else f"{block.elapsed_hours:.2f}"
        exposure = "—" if block.high_exposure is None else f"{block.high_exposure:.1%}"
        lines.append(
            f"| {block.number} | {block.arm} / {block.limit} | "
            f"{','.join(map(str, block.issues)) or '—'} | {elapsed} | {exposure} | "
            f"{block.clean_closures}/10 | {block.rework_issues} | {block.conflicts} | "
            f"{block.unclean_issues} |"
        )
    lines += [
        "",
        (
            f"Throughput rate ratio candidate/safe: **{ratio}** "
            f"(exact conditional Poisson 90% interval {interval})."
        ),
        f"Reasons: {', '.join(result.reasons) if result.reasons else 'all criteria cleared'}.",
        f"Recommendation: {result.recommendation}",
        "",
        "Concurrent changes/confounders: "
        + "; ".join(str(item) for item in _list(manifest, "confounders"))
        + ".",
    ]
    return "\n".join(lines) + "\n"


def read_json(path: Path) -> object:
    """Read one JSON document."""
    return json.loads(path.read_text(encoding="utf-8"))


def read_rows(path: Path) -> list[object]:
    """Read the append-only JSON-lines journal."""
    if not path.exists():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def write_new(path: Path, document: Mapping[str, object]) -> None:
    """Create a file without an overwrite path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(document, indent=2) + "\n")


def append_row(path: Path, document: Mapping[str, object]) -> None:
    """Append one canonical row to a journal."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(canonical(document) + "\n")


def _git_sha(root: Path) -> str:
    done = subprocess.run(
        ["git", "rev-parse", "origin/main"],  # noqa: S607 -- git is repo authority
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return done.stdout.strip() if done.returncode == 0 else ""


def _live_inputs(
    args: argparse.Namespace,
) -> tuple[
    tuple[int, ...],
    dict[str, object],
    tuple[dict[str, object], ...],
    dict[str, object] | None,
    Refusal | None,
]:
    """Read queue candidates/policy and the dispatch dry-run route snapshot."""
    policy, refusal = queue_policy.read_policy(
        queue_policy.Store(Path(args.queue_dir).expanduser())
    )
    if refusal is not None or policy is None:
        found = refusal.lines() if refusal else ()
        return (
            (),
            {},
            (),
            None,
            Refusal("policy_unreadable", found, "Restore the queue policy read before starting."),
        )
    candidates, refusal = queue_policy.ready_candidates()
    if refusal is not None:
        return (
            (),
            {},
            (),
            None,
            Refusal(
                "candidates_unreadable",
                refusal.lines(),
                "Restore the tracker read before starting.",
            ),
        )
    in_flight = queue_policy.gather(Path(args.root), Path(args.dispatch_dir).expanduser())
    selection = queue_policy.select(policy, candidates, in_flight, 200)
    eligible = tuple(candidate.issue for candidate in selection.eligible)
    try:
        routes_raw = read_json(Path(args.routes_file))
        routes = tuple(routes_raw) if isinstance(routes_raw, list) else ()
    except (OSError, json.JSONDecodeError, ValueError):
        routes = ()
    if not routes or any(not isinstance(route, dict) for route in routes):
        return (
            (),
            {},
            (),
            None,
            Refusal(
                "routes_snapshot_missing",
                ("routes=unreadable",),
                "Record at least two `just dispatch --dry-run` lane/seat verdicts "
                "in --routes-file.",
            ),
        )
    previous: dict[str, object] | None = None
    if args.previous_result:
        try:
            raw = read_json(Path(args.previous_result))
            previous = _mapping(raw) if isinstance(raw, dict) else None
        except (OSError, json.JSONDecodeError, ValueError):
            previous = None
    return (
        eligible,
        policy.document(),
        tuple(_mapping(route) for route in routes),
        previous,
        None,
    )


def _emit(lines: Iterable[str], code: int = 0) -> int:
    stream = sys.stdout if code == 0 else sys.stderr
    for line in lines:
        print(line, file=stream)
    return code


def _manifest(args: argparse.Namespace) -> tuple[dict[str, object] | None, Refusal | None]:
    path = Path(args.trial_dir).expanduser() / MANIFEST_FILE
    try:
        return validate_manifest(read_json(path))
    except (OSError, json.JSONDecodeError, ValueError) as failure:
        return None, Refusal(
            "manifest_unreadable",
            (f"path={path}", f"detail={failure}"),
            "Run `just wip-trial start` before recording or analysing.",
        )


def _read_trial(
    args: argparse.Namespace,
) -> tuple[dict[str, object] | None, tuple[dict[str, object], ...], Refusal | None]:
    manifest, refusal = _manifest(args)
    if refusal is not None or manifest is None:
        return None, (), refusal
    try:
        rows = read_rows(Path(args.trial_dir).expanduser() / EVENTS_FILE)
    except (OSError, json.JSONDecodeError, ValueError) as failure:
        return (
            None,
            (),
            Refusal(
                "journal_unreadable",
                (f"detail={failure}",),
                "Start a new bar; do not silently drop unreadable observations.",
            ),
        )
    events, refusal = validate_events(manifest, rows)
    return manifest, events, refusal


def bar_lines() -> tuple[str, ...]:
    """Render the bar before any live stage starts."""
    stages = " ".join(f"{safe}->{candidate}" for safe, candidate in STAGES.values())
    return (
        f"bar_id={BAR_ID}",
        f"stages={stages}",
        "maximum_wip=10",
        f"block={ISSUES_PER_BLOCK} issues",
        "stage=two safe blocks and two candidate blocks; SHA-derived ABBA or BAAB",
        f"material_throughput={MATERIAL_RATE_RATIO:.0%} of safe rate",
        f"candidate_high_exposure={MIN_HIGH_EXPOSURE:.0%} of unfinished-cohort time",
        f"maturity={MATURITY_SECONDS // 86400} days",
        "quality=10/10 clean, zero critical failures, at most 1/10 unclean per block",
        f"quality_sources={admission.BAR_ID} {admission.TRIAL_BAR_ID}",
        "rework=candidate issue and conflict counts cannot exceed the safe control",
        "selection=lowest passing limit; a higher stage follows only a matured pass",
        "authority=reports only; never dispatches and never edits queue policy",
    )


def manifest_lines(manifest: Mapping[str, object]) -> tuple[str, ...]:
    """Render the immutable stage identity and allocation."""
    return (
        f"source_sha={manifest['source_sha']}",
        f"stage={manifest['safe_limit']}->{manifest['candidate_limit']}",
        f"order={'-'.join(str(item) for item in _list(manifest, 'block_order'))}",
        f"eligible={len(_list(manifest, 'eligible_issues'))}",
        "criteria=immutable-before-first-observation",
    )


def run_bar(_args: argparse.Namespace) -> int:
    """Print the pre-registered bar without reading observations."""
    return _emit(bar_lines())


def run_start(args: argparse.Namespace) -> int:
    """Snapshot inputs and create an immutable manifest."""
    trial_dir = Path(args.trial_dir).expanduser()
    path = trial_dir / MANIFEST_FILE
    if path.exists():
        return _emit(
            Refusal(
                "bar_already_started",
                (f"path={path}",),
                "Archive the completed bar directory and start a new immutable bar.",
            ).lines(),
            EXIT_REFUSED,
        )
    eligible, policy, routes, previous, refusal = _live_inputs(args)
    if refusal is not None:
        return _emit(refusal.lines(), EXIT_REFUSED)
    source_sha = args.source_sha or _git_sha(Path(args.root))
    if not source_sha:
        return _emit(
            Refusal(
                "source_sha_unreadable",
                (),
                "Restore the origin/main read before starting.",
            ).lines(),
            EXIT_REFUSED,
        )
    manifest, refusal = make_manifest(
        stage=args.stage,
        source_sha=source_sha,
        eligible_issues=eligible,
        policy=policy,
        routes=routes,
        created_at=args.now or time.time(),
        previous_result=previous,
    )
    if refusal is not None or manifest is None:
        return _emit(refusal.lines() if refusal else (), EXIT_REFUSED)
    if args.dry_run:
        return _emit((json.dumps(manifest, indent=2), "dry_run=true written=false"))
    write_new(path, manifest)
    return _emit((f"started={manifest['bar_id']}", f"manifest={path}", *manifest_lines(manifest)))


def _issues(text: str, label: str) -> tuple[tuple[int, ...], Refusal | None]:
    issues, refusal = queue_policy.parse_issues(text)
    if refusal is None:
        return issues, None
    return (), Refusal(
        f"{label}_invalid",
        refusal.lines(),
        f"Record the {label.replace('_', ' ')} in ascending queue order.",
    )


def _event_from_args(  # noqa: C901 -- construction mirrors the finite event vocabulary
    args: argparse.Namespace,
) -> tuple[dict[str, object] | None, Refusal | None]:
    common: dict[str, object] = {
        "kind": args.kind,
        "at": args.at or time.time(),
        "source": args.source,
    }
    if args.kind == "block_start":
        issues, refusal = _issues(args.issues, "cohort")
        if refusal is not None:
            return None, refusal
        eligible, refusal = _issues(args.eligible, "eligible")
        if refusal is not None:
            return None, refusal
        return {
            **common,
            "block": args.block,
            "arm": args.arm,
            "limit": args.limit,
            "issues": list(issues),
            "eligible": list(eligible),
            "orchestration_trial": args.orchestration_trial,
        }, None
    if args.kind == "change":
        return {**common, "description": args.description}, None
    if args.kind == "restore":
        return {**common, "block": args.block, "limit": args.limit}, None
    common.update({"block": args.block, "issue": args.issue})
    details: dict[str, object] = {}
    if args.kind == "observation":
        details = {
            "event": args.event,
            "occupancy": args.occupancy,
            "lane": args.lane,
            "profile": args.profile,
            "seat": args.seat,
            "gate": args.gate,
            "change_size": args.change_size,
        }
    elif args.kind == "ready":
        details = {"corrective": False}
    elif args.kind == "rework":
        details = {"corrective": True}
    elif args.kind == "conflict":
        details = {"conflict": args.conflict}
    elif args.kind == "maturity":
        details = {
            "clean_close": None if not args.clean_close else args.clean_close == "yes",
            "unclean": None if not args.unclean else args.unclean == "yes",
            "unclean_reasons": [item for item in args.unclean_reasons.split(",") if item],
            "gate_reds": args.gate_reds,
            "flake_reruns": args.flake_reruns,
        }
    elif args.kind == "critical":
        details = {"failure": args.failure}
    elif args.kind == "non_result":
        details = {"failure_class": args.failure_class}
    return {**common, **details}, None


def run_record(args: argparse.Namespace) -> int:
    """Append one classified and sourced observation."""
    manifest, refusal = _manifest(args)
    if refusal is not None or manifest is None:
        return _emit(refusal.lines() if refusal else (), EXIT_REFUSED)
    path = Path(args.trial_dir).expanduser() / EVENTS_FILE
    try:
        rows = read_rows(path)
    except (OSError, json.JSONDecodeError, ValueError) as failure:
        return _emit(
            Refusal(
                "journal_unreadable",
                (f"detail={failure}",),
                "Do not repair observed history in place; start a new bar.",
            ).lines(),
            EXIT_REFUSED,
        )
    event, refusal = _event_from_args(args)
    if refusal is not None or event is None:
        return _emit(refusal.lines() if refusal else (), EXIT_REFUSED)
    row, refusal = append_event(manifest, rows, event)
    if refusal is not None or row is None:
        return _emit(refusal.lines() if refusal else (), EXIT_REFUSED)
    append_row(path, row)
    return _emit((f"recorded={row['kind']}", f"event_sha256={row['event_sha256']}"))


def run_status(args: argparse.Namespace) -> int:
    """Print the current stage state and recommendation."""
    manifest, events, refusal = _read_trial(args)
    if refusal is not None or manifest is None:
        return _emit(refusal.lines() if refusal else (), EXIT_REFUSED)
    result = analyse(manifest, events, args.now or time.time())
    return _emit(
        (
            *manifest_lines(manifest),
            f"events={len(events)}",
            f"verdict={result.verdict}",
            *(f"reason={reason}" for reason in result.reasons),
            f"recommendation={result.recommendation}",
        )
    )


def run_audit(args: argparse.Namespace) -> int:
    """Print block completeness and every current decision reason."""
    manifest, events, refusal = _read_trial(args)
    if refusal is not None or manifest is None:
        return _emit(refusal.lines() if refusal else (), EXIT_REFUSED)
    result = analyse(manifest, events, args.now or time.time())
    lines = [
        "audit=complete",
        f"bar_id={manifest['bar_id']}",
        *(
            f"block={block.number} arm={block.arm} issues={len(block.issues)}/10 "
            f"elapsed_hours={block.elapsed_hours} "
            f"occupancy_complete={str(block.occupancy_complete).lower()} "
            f"fidelity_reached={str(block.fidelity_reached).lower()} "
            f"high_exposure={block.high_exposure} mature={block.mature_issues}/10"
            for block in result.blocks
        ),
    ]
    return _emit((*lines, f"verdict={result.verdict}", *(f"reason={r}" for r in result.reasons)))


def run_analyse(args: argparse.Namespace) -> int:
    """Write and print the reproducible machine-readable result."""
    manifest, events, refusal = _read_trial(args)
    if refusal is not None or manifest is None:
        return _emit(refusal.lines() if refusal else (), EXIT_REFUSED)
    now = args.now or time.time()
    result = analyse(manifest, events, now)
    document = result_document(manifest, result, now)
    path = Path(args.trial_dir).expanduser() / RESULT_FILE
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return _emit((json.dumps(document, indent=2), f"result={path}"))


def run_report(args: argparse.Namespace) -> int:
    """Print the paste-ready Markdown result."""
    manifest, events, refusal = _read_trial(args)
    if refusal is not None or manifest is None:
        return _emit(refusal.lines() if refusal else (), EXIT_REFUSED)
    sys.stdout.write(markdown_report(manifest, analyse(manifest, events, args.now or time.time())))
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the read-only and append-only command surface."""
    parser = argparse.ArgumentParser(prog="just wip-trial", description=__doc__)
    parser.add_argument(
        "--trial-dir",
        default=os.environ.get("CTI_WIP_TRIAL_DIR", str(DEFAULT_TRIAL_DIR)),
    )
    parser.add_argument("--now", type=float, default=0.0)
    verbs = parser.add_subparsers(dest="verb", required=True)
    verbs.add_parser("bar")

    start = verbs.add_parser("start")
    start.add_argument("--stage", type=int, required=True)
    start.add_argument("--source-sha", default="")
    start.add_argument("--root", default=".")
    start.add_argument(
        "--queue-dir",
        default=os.environ.get("CTI_QUEUE_DIR", str(queue_policy.DEFAULT_QUEUE_DIR)),
    )
    start.add_argument(
        "--dispatch-dir",
        default=os.environ.get("CTI_DISPATCH_DIR", str(Path.home() / ".arma-cti" / "dispatches")),
    )
    start.add_argument("--routes-file", required=True)
    start.add_argument("--previous-result", default="")
    start.add_argument("--dry-run", action="store_true")

    for name in ("status", "audit", "analyse", "report"):
        verbs.add_parser(name)

    record = verbs.add_parser("record")
    record.add_argument("--kind", choices=tuple(sorted(EVENT_KINDS)), required=True)
    record.add_argument("--at", type=float, default=0.0)
    record.add_argument("--source", required=True)
    record.add_argument("--block", type=int, default=0)
    record.add_argument("--issue", type=int, default=0)
    record.add_argument("--issues", default="")
    record.add_argument("--eligible", default="")
    record.add_argument("--arm", choices=("safe", "candidate"), default="")
    record.add_argument("--limit", type=int, default=0)
    record.add_argument(
        "--orchestration-trial",
        choices=("not_started", "running", "cleared", "failed"),
        default="",
    )
    record.add_argument("--event", choices=tuple(sorted(OBSERVATION_KINDS)), default="")
    record.add_argument("--occupancy", type=int, default=-1)
    record.add_argument("--lane", default="")
    record.add_argument("--profile", default="")
    record.add_argument("--seat", default="")
    record.add_argument("--gate", choices=("fast", "corpus", ""), default="")
    record.add_argument("--change-size", type=int, default=0)
    record.add_argument("--conflict", choices=tuple(sorted(CONFLICT_KINDS)), default="")
    record.add_argument("--clean-close", choices=("yes", "no"), default="")
    record.add_argument("--unclean", choices=("yes", "no"), default="")
    record.add_argument("--unclean-reasons", default="")
    record.add_argument("--gate-reds", type=int, default=-1)
    record.add_argument("--flake-reruns", type=int, default=-1)
    record.add_argument("--failure", choices=tuple(sorted(CRITICAL_KINDS)), default="")
    record.add_argument("--failure-class", choices=tuple(sorted(NON_RESULTS)), default="")
    record.add_argument("--description", default="")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Dispatch one WIP trial command."""
    args = parse_args(argv)
    return {
        "bar": run_bar,
        "start": run_start,
        "status": run_status,
        "audit": run_audit,
        "record": run_record,
        "analyse": run_analyse,
        "report": run_report,
    }[args.verb](args)


if __name__ == "__main__":
    sys.exit(main())
