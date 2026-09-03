"""Read loop metrics from the dispatch and review records (#602).

This is an on-demand report, not a controller capability.  It reads the durable
dispatch records, per-issue review loops, materialised ledger rows and queue-depth
samples.  It never opens a dispatch, writes a projection, contacts MLflow, or
changes the records it reads.  A missing or damaged input is named as unknown and
never quietly converted to zero.

The self-review block is the provisional version-2 shape proposed by #589.  No
producer for that shape has landed on current main, so the v2 branch below is
unexercised by current durable records; its fixture tests pin the expected
boundary until #589 lands and owns the protocol.  Version-1 loop files remain
valid input and explicitly contribute no self-review observations.
Dismissal matching is deliberately conservative: an independent finding matches a
dismissed self-review finding only when the two records carry the same non-empty
finding id for the same issue, and exactly one independent finding carries it.
The reader cannot infer that two differently named findings describe the same diff;
those cases stay unmatched and are shown in the denominator's uncertainty range.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from statistics import pvariance
from typing import Final, NamedTuple

# ``tools/`` is a collection of standalone scripts.  Keep the existing queue and
# acceptance readers available without turning the directory into a package.
sys.path.insert(0, str(Path(__file__).parent))

import acceptance
import observatory

REPO: Final = Path(__file__).resolve().parents[1]
STATE_ROOT: Final = Path.home() / ".arma-cti"
DEFAULT_DISPATCH_ROOT: Final = STATE_ROOT / "dispatches"
DEFAULT_REVIEW_ROOT: Final = STATE_ROOT / "review"
DEFAULT_QUEUE_ROOT: Final = STATE_ROOT / "queue"

IMPLEMENTER: Final = "implementer"
REVIEW: Final = "review"
LOOP_SEATS: Final = frozenset({IMPLEMENTER, REVIEW})
LOOP_VERSIONS: Final = frozenset({1, 2})
SELF_REVIEW_VERSION: Final = 2
# Provisional until #589 lands its producer and protocol constants.  The parser's
# fixture tests exercise this expectation; current main's durable records do not.
SELF_REVIEW_ROUND_BUDGET: Final = 5
WORTH_ADDRESSING: Final = "worth_addressing"
NOT_WORTH_ADDRESSING: Final = "not_worth_addressing"
SELF_CATEGORIES: Final = frozenset({WORTH_ADDRESSING, NOT_WORTH_ADDRESSING})
PRE_EXISTING: Final = "pre_existing"
INTRODUCED: Final = "introduced"
SELF_ORIGINS: Final = frozenset({PRE_EXISTING, INTRODUCED})
SEVERITIES: Final = ("critical", "high", "medium", "low")
# Deliberate reporting floor: one observation is reportable, and its wide Wilson
# interval carries the uncertainty rather than hiding the observation as absent.
MIN_OBSERVATIONS: Final = 1
WILSON_Z: Final = 1.959963984540054
EXCLUDED_WORK_ITEM_LIMIT: Final = 20

# These are the setpoints recorded in the frozen baseline and in fb42e18.  The
# reader reports a setpoint only where the project has actually ruled one; it
# does not invent targets for the other stocks.
READY_SETPOINT: Final = 3
WORKTREES_SETPOINT: Final = 0
NO_LEDGER_SETPOINT: Final = 0
UNRATIFIED_SETPOINT: Final = 0
OPEN_FINDINGS_SETPOINT: Final = 2

# Worktree names that carry an issue number: `issue-672`, the review seat's
# `review-672`, its `review-672-r2` and bare-letter `review-672b` variants, the
# suffixed `review-672-N-note` shape, and hand-named audit trees `audit-672`.
# Everything else on the registration table cannot be joined to a landing and
# is excluded by name instead.
ISSUE_WORKTREE_NAME: Final = re.compile(
    r"^(?:issue|review|audit)-(\d+)(?:-[a-z0-9][a-z0-9-]*|[a-z][a-z0-9-]*)?$"
)


class DispatchRecord(NamedTuple):
    """The durable fields needed from one dispatch directory."""

    dispatch_id: str
    issue: int
    seat: str
    planned_at: float
    result_state: str
    result_started_at: float | None
    result_ended_at: float | None
    ledger_row: bool
    ledger_materialised_at: float | None
    landed_sha: str | None
    landed_at: float | None
    path: Path


class IndependentFinding(NamedTuple):
    """One finding from the never-alone review loop."""

    identifier: str
    severity: str
    round_raised: int
    is_open: bool = True


class SelfFinding(NamedTuple):
    """One #589 self-review finding, including dismissed findings."""

    identifier: str
    category: str
    origin: str
    round_raised: int


class SelfRound(NamedTuple):
    """One numbered self-review round."""

    number: int
    findings: tuple[SelfFinding, ...]


class SelfReviewData(NamedTuple):
    """The validated fields the provisional self-review extension contributes."""

    rounds: tuple[SelfRound, ...]
    converged_on: str
    failure: str


class LoopRecord(NamedTuple):
    """The independent findings and optional separate self-review block."""

    issue: int
    review_rounds: int
    independent_findings: tuple[IndependentFinding, ...]
    self_rounds: tuple[SelfRound, ...]
    self_review_present: bool
    self_converged_on: str = ""
    self_failure: str = ""
    independent_present: bool = True


class Window(NamedTuple):
    """An inclusive epoch window; ``None`` means the source has no boundary."""

    start: float | None
    end: float | None
    explicit: bool

    def contains(self, value: float) -> bool:
        """Answer whether a timestamp is inside this inclusive window."""
        return (self.start is None or value >= self.start) and (
            self.end is None or value <= self.end
        )


class Inputs(NamedTuple):
    """All source reads, kept in memory so reporting performs no second read."""

    dispatches: tuple[DispatchRecord, ...]
    loops: tuple[LoopRecord, ...]
    queue_rows: tuple[dict[str, object], ...]
    diagnostics: tuple[str, ...]


class Proportion(NamedTuple):
    """A ratio and its 95% Wilson interval."""

    numerator: int
    denominator: int
    value: float
    lower: float
    upper: float


class StockReading(NamedTuple):
    """One stock level with its paired flows, trend and evidence reason."""

    level: int | None
    flow_creation: str
    flow_clearing: str
    trend: str
    reason: str


class DispatchLevel(NamedTuple):
    """One in-flight level plus dispatches excluded from its evidence."""

    level: int | None
    excluded: int


class WorktreeStock(NamedTuple):
    """One joined worktree level with the registration evidence behind it."""

    reading: StockReading
    registrations: int
    unjoinable: int


def _is_number(value: object) -> bool:
    """Accept finite JSON numbers but not booleans."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _read_object(path: Path, diagnostics: list[str], label: str) -> dict[str, object] | None:
    """Read one JSON object and name damage without turning it into a zero."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        diagnostics.append(f"{label} status=absent path={path}")
        return None
    except (OSError, json.JSONDecodeError) as error:
        diagnostics.append(f"{label} status=unreadable path={path} reason={error}")
        return None
    if not isinstance(raw, dict):
        diagnostics.append(f"{label} status=unreadable path={path} reason=not_an_object")
        return None
    return raw


def parse_timestamp(value: object) -> float | None:
    """Parse an epoch or timezone-aware ISO timestamp without guessing a zone."""
    if _is_number(value):
        return float(value)
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.timestamp()


def format_timestamp(value: float | None) -> str:
    """Render a source boundary in a stable UTC representation."""
    if value is None:
        return "unrecorded"
    return datetime.fromtimestamp(value, UTC).isoformat().replace("+00:00", "Z")


def _positive_int(value: object) -> int | None:
    """Read a positive integer field without coercing malformed data."""
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        return None
    return value


def _nonnegative_int(value: object) -> int | None:
    """Read a non-negative integer field without coercing malformed data."""
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        return None
    return value


def _read_result(
    dispatch_dir: Path, diagnostics: list[str], dispatch_id: str
) -> tuple[str, float | None, float | None]:
    """Read a result closeout, preserving missing and damaged as different states."""
    path = dispatch_dir / "result.json"
    if not path.exists():
        return "absent", None, None
    document = _read_object(path, diagnostics, f"result dispatch={dispatch_id}")
    if document is None:
        return "unreadable", None, None
    started = parse_timestamp(document.get("started_at"))
    ended = parse_timestamp(document.get("ended_at"))
    if document.get("started_at") is not None and started is None:
        diagnostics.append(f"result dispatch={dispatch_id} field=started_at status=unreadable")
    if document.get("ended_at") is not None and ended is None:
        diagnostics.append(f"result dispatch={dispatch_id} field=ended_at status=unreadable")
    return "readable", started, ended


def _ledger_fields(  # noqa: PLR0911 — each typed absence is a distinct durable fact
    dispatch_dir: Path, diagnostics: list[str], dispatch_id: str, issue: int
) -> tuple[bool, float | None, str | None, float | None]:
    """Read the optional materialised row and its landing join."""
    path = dispatch_dir / "ledger.json"
    if not path.exists():
        return False, None, None, None
    document = _read_object(path, diagnostics, f"ledger dispatch={dispatch_id}")
    if document is None:
        return False, None, None, None
    stored_id = document.get("dispatch_id")
    if stored_id is not None and stored_id != dispatch_id:
        diagnostics.append(
            f"ledger dispatch={dispatch_id} status=unreadable reason=dispatch_id_mismatch"
        )
        return False, None, None, None
    stored_issue = document.get("issue")
    if stored_issue is not None and stored_issue != issue:
        diagnostics.append(f"ledger dispatch={dispatch_id} status=unreadable reason=issue_mismatch")
        return False, None, None, None
    materialised = parse_timestamp(document.get("materialised_at"))
    if document.get("materialised_at") is not None and materialised is None:
        diagnostics.append(f"ledger dispatch={dispatch_id} field=materialised_at status=unreadable")

    gate = document.get("gate")
    if not isinstance(gate, dict) or gate.get("outcome") != "landed":
        return True, materialised, None, None
    landed = gate.get("landed")
    if not isinstance(landed, dict):
        diagnostics.append(f"ledger dispatch={dispatch_id} status=unreadable reason=landed_shape")
        return True, materialised, None, None
    sha = landed.get("sha")
    if not isinstance(sha, str) or not sha:
        diagnostics.append(f"ledger dispatch={dispatch_id} status=unreadable reason=landed_sha")
        return True, materialised, None, None
    landed_at = parse_timestamp(landed.get("landed_at"))
    if landed_at is None:
        landed_at = parse_timestamp(gate.get("landed_at"))
    return True, materialised, sha, landed_at


def read_dispatches(root: Path, diagnostics: list[str]) -> tuple[DispatchRecord, ...]:
    """Read all dispatch plans and their local result/ledger companions."""
    if not root.exists():
        diagnostics.append(f"dispatch_source status=absent path={root}")
        return ()
    try:
        entries = tuple(sorted(root.iterdir(), key=lambda path: path.name))
    except OSError as error:
        diagnostics.append(f"dispatch_source status=unreadable path={root} reason={error}")
        return ()
    records: list[DispatchRecord] = []
    for dispatch_dir in entries:
        if not dispatch_dir.is_dir():
            continue
        plan_path = dispatch_dir / "dispatch.json"
        document = _read_object(plan_path, diagnostics, f"dispatch path={plan_path}")
        if document is None:
            continue
        dispatch_id = document.get("dispatch_id")
        issue = _positive_int(document.get("issue"))
        seat = document.get("seat")
        planned_at = parse_timestamp(document.get("planned_at"))
        if not isinstance(dispatch_id, str) or not dispatch_id:
            diagnostics.append(f"dispatch path={plan_path} status=unreadable reason=dispatch_id")
            continue
        if issue is None:
            diagnostics.append(f"dispatch={dispatch_id} status=unreadable reason=issue")
            continue
        if not isinstance(seat, str) or not seat:
            diagnostics.append(f"dispatch={dispatch_id} status=unreadable reason=seat")
            continue
        if planned_at is None:
            diagnostics.append(f"dispatch={dispatch_id} status=unreadable reason=planned_at")
            continue
        result_state, started, ended = _read_result(dispatch_dir, diagnostics, dispatch_id)
        ledger, materialised, landed_sha, landed_at = _ledger_fields(
            dispatch_dir, diagnostics, dispatch_id, issue
        )
        records.append(
            DispatchRecord(
                dispatch_id,
                issue,
                seat,
                planned_at,
                result_state,
                started,
                ended,
                ledger,
                materialised,
                landed_sha,
                landed_at,
                dispatch_dir,
            )
        )
    records.sort(key=lambda record: (record.planned_at, record.dispatch_id))
    diagnostics.append(f"dispatch_source status=readable path={root} records={len(records)}")
    return tuple(records)


def _parse_independent_findings(
    raw: object, issue: int, diagnostics: list[str]
) -> tuple[IndependentFinding, ...] | None:
    """Read the v1/v2 independent finding list."""
    if not isinstance(raw, list):
        diagnostics.append(f"review issue={issue} status=unreadable reason=findings")
        return None
    findings: list[IndependentFinding] = []
    seen: set[str] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            diagnostics.append(f"review issue={issue} status=unreadable reason=finding_shape")
            return None
        identifier = entry.get("id")
        severity = entry.get("severity")
        round_raised = entry.get("round_raised")
        if (
            not isinstance(identifier, str)
            or not identifier
            or not isinstance(severity, str)
            or severity not in SEVERITIES
            or _nonnegative_int(round_raised) is None
        ):
            diagnostics.append(f"review issue={issue} status=unreadable reason=finding_fields")
            return None
        if identifier in seen:
            diagnostics.append(f"review issue={issue} status=ambiguous reason=duplicate_finding_id")
        else:
            seen.add(identifier)
        findings.append(
            IndependentFinding(
                identifier,
                severity,
                int(round_raised),
                entry.get("adjudication") is None,
            )
        )
    return tuple(findings)


def _parse_self_rounds(  # noqa: C901, PLR0911 — one fail-closed ladder for the stored schema
    raw: object, issue: int, diagnostics: list[str]
) -> tuple[SelfRound, ...] | None:
    """Read the exact #589 nested rounds, including only actual findings."""
    if not isinstance(raw, list) or len(raw) > SELF_REVIEW_ROUND_BUDGET:
        diagnostics.append(f"review issue={issue} status=unreadable reason=self_rounds")
        return None
    rounds: list[SelfRound] = []
    seen: set[str] = set()
    for expected, raw_round in enumerate(raw, start=1):
        if not isinstance(raw_round, dict) or raw_round.get("number") != expected:
            diagnostics.append(f"review issue={issue} status=unreadable reason=self_round_number")
            return None
        raw_findings = raw_round.get("findings", [])
        raw_refutations = raw_round.get("refutations", [])
        if not isinstance(raw_findings, list) or not isinstance(raw_refutations, list):
            diagnostics.append(f"review issue={issue} status=unreadable reason=self_round_lists")
            return None
        findings: list[SelfFinding] = []
        for entry in raw_findings:
            if not isinstance(entry, dict):
                diagnostics.append(
                    f"review issue={issue} status=unreadable reason=self_finding_shape"
                )
                return None
            identifier = entry.get("id")
            category = entry.get("category")
            origin = entry.get("origin")
            round_raised = entry.get("round_raised")
            if (
                not isinstance(identifier, str)
                or not identifier
                or not isinstance(category, str)
                or category not in SELF_CATEGORIES
                or not isinstance(origin, str)
                or origin not in SELF_ORIGINS
                or not isinstance(entry.get("reason"), str)
                or not entry["reason"]
                or _nonnegative_int(round_raised) != expected
            ):
                diagnostics.append(
                    f"review issue={issue} status=unreadable reason=self_finding_fields"
                )
                return None
            if identifier in seen:
                diagnostics.append(
                    f"review issue={issue} status=unreadable reason=self_duplicate_id"
                )
                return None
            seen.add(identifier)
            findings.append(SelfFinding(identifier, category, origin, expected))
        # Refutations are evidence, not findings.  Validate their stable identity
        # and stamp so malformed refutations cannot quietly become findings.
        for entry in raw_refutations:
            if not isinstance(entry, dict):
                diagnostics.append(
                    f"review issue={issue} status=unreadable reason=refutation_shape"
                )
                return None
            identifier = entry.get("id")
            if (
                not isinstance(identifier, str)
                or not identifier
                or not isinstance(entry.get("reason"), str)
                or not entry["reason"]
                or _nonnegative_int(entry.get("round_raised")) != expected
            ):
                diagnostics.append(
                    f"review issue={issue} status=unreadable reason=refutation_fields"
                )
                return None
            if identifier in seen:
                diagnostics.append(
                    f"review issue={issue} status=unreadable reason=self_duplicate_id"
                )
                return None
            seen.add(identifier)
        rounds.append(SelfRound(expected, tuple(findings)))
    return tuple(rounds)


def _parse_self_review(  # noqa: C901, PLR0911 — the provisional schema's fail-closed ladder stays together
    raw: object, issue: int, diagnostics: list[str]
) -> SelfReviewData | None:
    """Read the provisional #589 self-review block without affecting independent findings."""
    if not isinstance(raw, dict):
        diagnostics.append(f"review issue={issue} status=unreadable reason=self_review_shape")
        return None
    parsed_rounds = _parse_self_rounds(raw.get("rounds"), issue, diagnostics)
    if parsed_rounds is None:
        return None
    converged_on = raw.get("converged_on", "")
    failure = raw.get("failure", "")
    if (
        not isinstance(converged_on, str)
        or not isinstance(failure, str)
        or (converged_on and failure)
    ):
        diagnostics.append(f"review issue={issue} status=unreadable reason=self_closed_state")
        return None
    if failure and failure not in {"discovery-dominated", "injection-dominated"}:
        diagnostics.append(f"review issue={issue} status=unreadable reason=self_failure")
        return None
    if failure and (
        len(parsed_rounds) != SELF_REVIEW_ROUND_BUDGET
        or any(
            not any(f.category == WORTH_ADDRESSING for f in attempt.findings)
            for attempt in parsed_rounds
        )
    ):
        diagnostics.append(f"review issue={issue} status=unreadable reason=self_failure_state")
        return None
    if converged_on and (
        not parsed_rounds or any(f.category == WORTH_ADDRESSING for f in parsed_rounds[-1].findings)
    ):
        diagnostics.append(f"review issue={issue} status=unreadable reason=self_convergence")
        return None
    raw_gate_fixes = raw.get("gate_fixes", [])
    if not isinstance(raw_gate_fixes, list):
        diagnostics.append(f"review issue={issue} status=unreadable reason=self_gate_fixes")
        return None
    covered = {converged_on} if converged_on else set()
    for entry in raw_gate_fixes:
        if not isinstance(entry, dict):
            diagnostics.append(
                f"review issue={issue} status=unreadable reason=self_gate_fix_fields"
            )
            return None
        sha = entry.get("sha")
        reason = entry.get("reason")
        if (
            not isinstance(sha, str)
            or not sha
            or not isinstance(reason, str)
            or not reason
            or sha in covered
        ):
            diagnostics.append(
                f"review issue={issue} status=unreadable reason=self_gate_fix_fields"
            )
            return None
        covered.add(sha)
    if raw_gate_fixes and not converged_on:
        diagnostics.append(f"review issue={issue} status=unreadable reason=self_gate_fix_state")
        return None
    return SelfReviewData(parsed_rounds, converged_on, failure)


def _parse_loop(path: Path, diagnostics: list[str]) -> LoopRecord | None:
    """Read one review loop, preserving each independently readable sub-block."""
    document = _read_object(path, diagnostics, f"review path={path}")
    if document is None:
        return None
    issue = _positive_int(document.get("issue"))
    version = document.get("version")
    rounds = _nonnegative_int(document.get("review_rounds"))
    if issue is None or version not in LOOP_VERSIONS or rounds is None:
        diagnostics.append(f"review path={path} status=unreadable reason=loop_header")
        return None

    parsed_findings = _parse_independent_findings(document.get("findings"), issue, diagnostics)
    independent_present = parsed_findings is not None
    findings = parsed_findings or ()
    if parsed_findings is not None and any(finding.round_raised > rounds for finding in findings):
        diagnostics.append(f"review issue={issue} status=unreadable reason=round_out_of_range")
        independent_present = False
        findings = ()

    self_rounds: tuple[SelfRound, ...] = ()
    self_present = False
    converged_on = ""
    failure = ""
    # Version 1 predates the block.  A stray key on a v1 record is ignored by
    # the #589 reader too; it cannot be evidence of a block that version never wrote.
    if version == SELF_REVIEW_VERSION and "self_review" in document:
        parsed_self = _parse_self_review(document["self_review"], issue, diagnostics)
        if parsed_self is not None:
            self_present = True
            self_rounds = parsed_self.rounds
            converged_on = parsed_self.converged_on
            failure = parsed_self.failure
    return LoopRecord(
        issue,
        rounds,
        findings,
        self_rounds,
        self_present,
        converged_on,
        failure,
        independent_present,
    )


def read_loops(root: Path, diagnostics: list[str]) -> tuple[LoopRecord, ...]:
    """Read all per-issue loop files and count absent roots as an empty view."""
    if not root.exists():
        diagnostics.append(f"review_source status=absent path={root}")
        return ()
    try:
        paths = tuple(sorted(root.glob("*/loop.json")))
    except OSError as error:
        diagnostics.append(f"review_source status=unreadable path={root} reason={error}")
        return ()
    records: list[LoopRecord] = []
    for path in paths:
        record = _parse_loop(path, diagnostics)
        if record is not None:
            records.append(record)
    records.sort(key=lambda record: record.issue)
    diagnostics.append(f"review_source status=readable path={root} records={len(records)}")
    return tuple(records)


def read_queue_rows(root: Path, diagnostics: list[str]) -> tuple[dict[str, object], ...]:
    """Reuse the canonical queue-depth reader without rebuilding its store."""
    if not root.exists():
        diagnostics.append(f"queue_source status=absent path={root}")
        return ()
    try:
        rows, malformed = observatory.read_queue_depths(root)
    except OSError as error:
        diagnostics.append(f"queue_source status=unreadable path={root} reason={error}")
        return ()
    for source, count in sorted(malformed.items()):
        diagnostics.append(f"queue_source status=unreadable source={source} records={count}")
    diagnostics.append(f"queue_source status=readable path={root} records={len(rows)}")
    return tuple(dict(row) for row in rows)


def read_inputs(dispatch_root: Path, review_root: Path, queue_root: Path) -> Inputs:
    """Read every source once; all later calculations consume this snapshot."""
    diagnostics: list[str] = []
    dispatches = read_dispatches(dispatch_root, diagnostics)
    loops = read_loops(review_root, diagnostics)
    queue_rows = read_queue_rows(queue_root, diagnostics)
    return Inputs(dispatches, loops, queue_rows, tuple(diagnostics))


def observed_times(inputs: Inputs) -> tuple[float, ...]:
    """Collect timestamps present in the snapshot for the default window."""
    times: list[float] = []
    for dispatch in inputs.dispatches:
        times.append(dispatch.planned_at)
        times.extend(
            value
            for value in (dispatch.result_started_at, dispatch.result_ended_at)
            if value is not None
        )
        times.extend(
            value
            for value in (dispatch.ledger_materialised_at, dispatch.landed_at)
            if value is not None
        )
    for row in inputs.queue_rows:
        value = row.get("sampled_at")
        if _is_number(value):
            times.append(float(value))
    return tuple(times)


def resolve_window(
    inputs: Inputs, start: float | None, end: float | None, *, explicit: bool
) -> Window:
    """Resolve an explicit boundary or the reproducible min/max source window."""
    times = observed_times(inputs)
    low = start if start is not None else min(times, default=None)
    high = end if end is not None else max(times, default=None)
    return Window(low, high, explicit)


def _proportion_failure(numerator: int, denominator: int) -> str | None:
    """Name why a proportion cannot be calculated, keeping invalid counts distinct."""
    if numerator < 0 or numerator > denominator:
        return "inconsistent"
    if denominator < MIN_OBSERVATIONS:
        return "too_few"
    return None


def wilson_interval(numerator: int, denominator: int) -> Proportion | None:
    """Return a two-sided 95% Wilson interval, or no ratio for invalid evidence."""
    if _proportion_failure(numerator, denominator) is not None:
        return None
    n = float(denominator)
    p = numerator / n
    z2 = WILSON_Z * WILSON_Z
    centre = (p + z2 / (2 * n)) / (1 + z2 / n)
    half = WILSON_Z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / (1 + z2 / n)
    return Proportion(numerator, denominator, p, max(0.0, centre - half), min(1.0, centre + half))


def _proportion_text(name: str, numerator: int, denominator: int, *, extras: str = "") -> str:
    """Render every ratio with numerator, denominator and an interval."""
    ratio = wilson_interval(numerator, denominator)
    if ratio is None:
        failure = _proportion_failure(numerator, denominator)
        if failure == "inconsistent":
            return (
                f"{name} status=inconsistent reason=numerator_out_of_range "
                f"numerator={numerator} denominator={denominator}"
                f"{f' {extras}' if extras else ''}"
            )
        return (
            f"{name} status=too_few observed={denominator} needed={MIN_OBSERVATIONS} "
            f"numerator={numerator} denominator={denominator}"
            f"{f' {extras}' if extras else ''}"
        )
    suffix = f" {extras}" if extras else ""
    return (
        f"{name} numerator={numerator} denominator={denominator} ratio={ratio.value:.6f} "
        f"interval=[{ratio.lower:.6f},{ratio.upper:.6f}] confidence=95%{suffix}"
    )


def _mean_text(name: str, values: list[float], *, extras: str = "") -> str:
    """Render a mean and population variance, naming an empty observation set."""
    if not values:
        suffix = f" {extras}" if extras else ""
        return f"{name} status=too_few observed=0 needed={MIN_OBSERVATIONS}{suffix}"
    suffix = f" {extras}" if extras else ""
    return (
        f"{name} observations={len(values)} mean={sum(values) / len(values):.6f} "
        f"variance={pvariance(values):.6f} variance_basis=population{suffix}"
    )


def _self_review_exclusion_text(loops: tuple[LoopRecord, ...]) -> str:
    """Name every absent self-review count, bounding the displayed issue list."""
    excluded = tuple(
        f"issue:{record.issue}"
        for record in sorted(loops, key=lambda record: record.issue)
        if not record.self_review_present
    )
    visible = excluded[:EXCLUDED_WORK_ITEM_LIMIT]
    omitted = len(excluded) - len(visible)
    names = ",".join(visible) if visible else "none"
    omitted_text = f" excluded_work_items_omitted={omitted}" if omitted else ""
    return f"excluded_without_self_review={len(excluded)} excluded_work_items={names}{omitted_text}"


def _selected_loops(inputs: Inputs, window: Window) -> tuple[LoopRecord, ...]:
    """Select loops by issue dispatch time because loop files carry no timestamp."""
    if not window.explicit:
        return inputs.loops
    issues = {
        dispatch.issue for dispatch in inputs.dispatches if window.contains(dispatch.planned_at)
    }
    return tuple(record for record in inputs.loops if record.issue in issues)


def _selected_dispatches(inputs: Inputs, window: Window) -> tuple[DispatchRecord, ...]:
    """Select dispatch events whose own plan timestamp is in the window."""
    return tuple(dispatch for dispatch in inputs.dispatches if window.contains(dispatch.planned_at))


def _loop_sequences(
    dispatches: tuple[DispatchRecord, ...], window: Window
) -> dict[int, tuple[str, ...]]:
    """Reduce implementer/review dispatches to seat transitions per issue."""
    grouped: defaultdict[int, list[str]] = defaultdict(list)
    for dispatch in dispatches:
        if dispatch.seat in LOOP_SEATS and window.contains(dispatch.planned_at):
            grouped[dispatch.issue].append(dispatch.seat)
    sequences: dict[int, tuple[str, ...]] = {}
    for issue, seats in grouped.items():
        reduced: list[str] = []
        for seat in seats:
            if not reduced or reduced[-1] != seat:
                reduced.append(seat)
        sequences[issue] = tuple(reduced)
    return sequences


def injection_lines(loops: tuple[LoopRecord, ...]) -> list[str]:
    """Report introduced versus pre-existing self findings per round and aggregate."""
    per_round: defaultdict[int, Counter[str]] = defaultdict(Counter)
    aggregate: Counter[str] = Counter()
    self_records = 0
    for record in loops:
        if not record.self_review_present:
            continue
        self_records += 1
        for attempt in record.self_rounds:
            per_round.setdefault(attempt.number, Counter())
            for finding in attempt.findings:
                per_round[attempt.number][finding.origin] += 1
                aggregate[finding.origin] += 1
    exclusions = _self_review_exclusion_text(loops)
    if self_records == 0:
        return [
            (
                "injection_rate status=too_few observed=0 needed=1 "
                f"self_review_records=0 {exclusions}"
            )
        ]
    lines = []
    for number in sorted(per_round):
        tally = per_round[number]
        lines.append(
            _proportion_text(
                f"injection_rate round={number}",
                tally[INTRODUCED],
                tally[INTRODUCED] + tally[PRE_EXISTING],
                extras="origin=introduced_vs_pre_existing",
            )
        )
    lines.append(
        _proportion_text(
            "injection_rate aggregate",
            aggregate[INTRODUCED],
            aggregate[INTRODUCED] + aggregate[PRE_EXISTING],
            extras=f"self_review_records={self_records} {exclusions}",
        )
    )
    return lines


def catch_fraction(loops: tuple[LoopRecord, ...]) -> tuple[Proportion | None, int, int]:
    """Compute self worth-addressing over self worth-addressing plus independent findings."""
    self_worth = 0
    independent = 0
    for record in loops:
        if not record.self_review_present or not record.independent_present:
            continue
        self_worth += sum(
            finding.category == WORTH_ADDRESSING
            for attempt in record.self_rounds
            for finding in attempt.findings
        )
        independent += len(record.independent_findings)
    denominator = self_worth + independent
    return wilson_interval(self_worth, denominator), self_worth, denominator


def dismissal_match_counts(
    loops: tuple[LoopRecord, ...],
) -> tuple[int, int, int, int, tuple[str, ...]]:
    """Match dismissed self findings by exact unique id within the same issue.

    A different id is not a match, even when its reason or severity looks similar:
    the records do not carry a safe line-level or semantic fingerprint.  Duplicate
    independent ids are ambiguous and remain outside the decidable denominator.
    """
    misses = 0
    dismissed = 0
    unmatched = 0
    ambiguous = 0
    unmatched_ids: list[str] = []
    for record in loops:
        if not record.self_review_present or not record.independent_present:
            continue
        independent_by_id: defaultdict[str, list[IndependentFinding]] = defaultdict(list)
        for finding in record.independent_findings:
            independent_by_id[finding.identifier].append(finding)
        for attempt in record.self_rounds:
            for finding in attempt.findings:
                if finding.category != NOT_WORTH_ADDRESSING:
                    continue
                dismissed += 1
                matches = independent_by_id[finding.identifier]
                if len(matches) == 1:
                    misses += 1
                elif len(matches) > 1:
                    ambiguous += 1
                    unmatched_ids.append(f"{record.issue}:{finding.identifier}:ambiguous")
                else:
                    unmatched += 1
                    unmatched_ids.append(f"{record.issue}:{finding.identifier}")
    return misses, dismissed, unmatched, ambiguous, tuple(unmatched_ids)


def _catch_text(loops: tuple[LoopRecord, ...]) -> tuple[str, str]:
    """Return the catch line and a compact copy for the findings line beside it."""
    ratio, numerator, denominator = catch_fraction(loops)
    exclusions = _self_review_exclusion_text(loops)
    if ratio is None:
        text = _proportion_text(
            "catch_fraction",
            numerator,
            denominator,
            extras=f"bound=upper_bound reason=no_self_review_or_findings {exclusions}",
        )
        return text, "catch_fraction_status=too_few"
    text = _proportion_text(
        "catch_fraction",
        numerator,
        denominator,
        extras=(
            "bound=upper_bound caveat=self_review_may_raise_a_class_the_reviewer_would_not "
            f"matching=not_used {exclusions}"
        ),
    )
    return text, (
        f"catch_fraction_ratio={ratio.value:.6f} "
        f"catch_fraction_interval=[{ratio.lower:.6f},{ratio.upper:.6f}] "
        "catch_fraction_bound=upper_bound"
    )


def dismissal_lines(loops: tuple[LoopRecord, ...]) -> list[str]:
    """Render dismissal misses, decidability and the matching limitation."""
    misses, dismissed, unmatched, ambiguous, unmatched_ids = dismissal_match_counts(loops)
    decidable = misses
    exclusions = _self_review_exclusion_text(loops)
    # A unique exact match is the only decidable dismissal.  Ambiguous entries are
    # kept out of the ratio just like unmatched entries, and both bounds remain visible.
    lines = [
        (
            "dismissal_matching=exact_nonempty_id_same_work_item_unique_independent_match "
            "different_ids=unmatched semantic_or_line_inference=not_available "
            "duplicate_ids=ambiguous"
        ),
        _proportion_text(
            "dismissal_misses",
            misses,
            dismissed,
            extras=(
                f"bound=lower_bound dismissed={dismissed} decidable={decidable} "
                f"unmatched={unmatched} "
                f"ambiguous={ambiguous} possible_range="
                f"[{(misses / dismissed if dismissed else 0.0):.6f},"
                f"{((misses + unmatched + ambiguous) / dismissed if dismissed else 0.0):.6f}] "
                f"{exclusions}"
            ),
        ),
    ]
    if unmatched_ids:
        lines.append("dismissal_unmatched=" + ",".join(unmatched_ids))
    return lines


def findings_lines(
    loops: tuple[LoopRecord, ...], dispatches: tuple[DispatchRecord, ...], window: Window
) -> list[str]:
    """Report findings per independent review and severity mix beside catch fraction."""
    catch_line, catch_copy = _catch_text(loops)
    reviews_by_issue: Counter[int] = Counter(
        dispatch.issue
        for dispatch in dispatches
        if dispatch.seat == REVIEW and window.contains(dispatch.planned_at)
    )
    findings_by_issue: Counter[int] = Counter(
        record.issue
        for record in loops
        if record.independent_present and record.issue in reviews_by_issue
        for _ in record.independent_findings
    )
    reviewed_issues = set(findings_by_issue) | {
        record.issue
        for record in loops
        if record.independent_present and record.issue in reviews_by_issue
    }
    reviews = sum(reviews_by_issue[issue] for issue in reviewed_issues)
    findings = sum(findings_by_issue.values())
    per_issue = [findings_by_issue[issue] / reviews_by_issue[issue] for issue in reviewed_issues]
    excluded_without_loop = sum(
        count for issue, count in reviews_by_issue.items() if issue not in reviewed_issues
    )
    lines = [catch_line]
    if reviews:
        lines.append(
            f"findings_per_independent_review reviews={reviews} findings={findings} "
            f"mean={findings / reviews:.6f} variance={pvariance(per_issue):.6f} "
            f"variance_basis=population reviewed_issues={len(reviewed_issues)} "
            f"excluded_without_loop_record={excluded_without_loop} {catch_copy}"
        )
    else:
        lines.append(
            f"findings_per_independent_review status=too_few observed={reviews} "
            f"needed={MIN_OBSERVATIONS} findings={findings} "
            f"excluded_without_loop_record={excluded_without_loop} {catch_copy}"
        )
    counts = Counter(
        finding.severity
        for record in loops
        if record.independent_present and record.issue in reviewed_issues
        for finding in record.independent_findings
    )
    total = sum(counts.values())
    lines.extend(
        _proportion_text(
            f"severity_mix severity={severity}",
            counts[severity],
            total,
            extras="findings=independent",
        )
        for severity in SEVERITIES
    )
    return lines


def clean_round_lines(loops: tuple[LoopRecord, ...]) -> list[str]:
    """Report the first clean self-review round distribution."""
    clean_rounds: list[int] = []
    exclusions = _self_review_exclusion_text(loops)
    for record in loops:
        if not record.self_review_present or not record.self_converged_on:
            continue
        if record.self_rounds and not any(
            finding.category == WORTH_ADDRESSING for finding in record.self_rounds[-1].findings
        ):
            clean_rounds.append(record.self_rounds[-1].number)
    if not clean_rounds:
        return [
            (
                "clean_round_distribution status=too_few observed=0 needed=1 "
                f"self_review_records=0_or_no_clean_round {exclusions}"
            )
        ]
    counts = Counter(clean_rounds)
    denominator = len(clean_rounds)
    return [
        _proportion_text(
            f"clean_round_distribution round={number}",
            counts[number],
            denominator,
            extras=f"clean_observations={denominator} {exclusions}",
        )
        for number in sorted(counts)
    ]


class Landing(NamedTuple):
    """One ledger-attested landing for an issue, and the basis of its timestamp.

    ``attested`` is False where the time is the landing commit's own timestamp
    because no ledger row recorded one — the canonical schema has no
    ``landed_at`` (docs/telemetry-ledger.md), so this is the normal path and
    never a rare fallback.
    """

    at: float
    attested: bool


def _landing_times(
    dispatches: tuple[DispatchRecord, ...], repo: Path, diagnostics: list[str]
) -> dict[int, tuple[Landing, ...]]:
    """Join landed ledger SHAs to commit timestamps, caching each SHA read.

    Every attested landing is kept, not just the latest: the worktree stock
    asks whether *any* landing occurred by a window boundary, and an issue can
    land twice (#486 carries two distinct landed SHAs).  Keeping the latest
    alone made such an issue read as never having landed whenever its later
    landing fell past the boundary.
    """
    cache: dict[str, float | None] = {}
    times: dict[int, list[Landing]] = {}
    for dispatch in dispatches:
        if dispatch.landed_sha is None:
            continue
        landed_at = dispatch.landed_at
        attested = landed_at is not None
        if landed_at is None:
            if dispatch.landed_sha not in cache:
                cache[dispatch.landed_sha] = _commit_timestamp(repo, dispatch.landed_sha)
            landed_at = cache[dispatch.landed_sha]
            if landed_at is None:
                diagnostics.append(
                    f"landing issue={dispatch.issue} sha={dispatch.landed_sha} status=unrecorded"
                )
        if landed_at is not None:
            times.setdefault(dispatch.issue, []).append(Landing(landed_at, attested))
    return {issue: tuple(landings) for issue, landings in times.items()}


def _git_text(repo: Path, args: list[str]) -> str | None:
    """Run one fixed git query and return its stdout, or None when git cannot answer."""
    try:
        completed = subprocess.run(  # noqa: S603 — fixed git argv; operands are data words
            ["git", *args],  # noqa: S607 — git resolves off PATH by design
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
            timeout=5.0,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout


def _commit_timestamp(repo: Path, sha: str) -> float | None:
    """Read a commit date without changing the repository."""
    stdout = _git_text(repo, ["show", "-s", "--format=%cI", sha])
    return parse_timestamp(stdout.strip()) if stdout is not None else None


def cycle_lines(
    dispatches: tuple[DispatchRecord, ...], repo: Path, window: Window, diagnostics: list[str]
) -> list[str]:
    """Report dispatch-to-landed time per issue, with no timestamp fabrication."""
    starts: dict[int, float] = {}
    for dispatch in dispatches:
        if window.contains(dispatch.planned_at):
            starts[dispatch.issue] = min(
                starts.get(dispatch.issue, dispatch.planned_at), dispatch.planned_at
            )
    landings = _landing_times(dispatches, repo, diagnostics)
    values: list[float] = []
    for issue, issue_landings in landings.items():
        if issue not in starts:
            continue
        landed = max(landing.at for landing in issue_landings)
        if landed >= starts[issue] and (not window.explicit or window.contains(landed)):
            values.append(landed - starts[issue])
    return [_mean_text("cycle_time_per_work_item", values, extras="unit=seconds")]


def return_lines(dispatches: tuple[DispatchRecord, ...], window: Window) -> list[str]:
    """Report handover return probability, lambda and the geometric residual."""
    sequences = _loop_sequences(dispatches, window)
    handovers = 0
    returns = 0
    review_counts: list[float] = []
    for sequence in sequences.values():
        handovers += sum(a == IMPLEMENTER and b == REVIEW for a, b in pairwise(sequence))
        returns += sum(a == REVIEW and b == IMPLEMENTER for a, b in pairwise(sequence))
        count = sequence.count(REVIEW)
        if count:
            review_counts.append(float(count))
    ratio = wilson_interval(returns, handovers)
    if ratio is None:
        failure = _proportion_failure(returns, handovers)
        if failure == "inconsistent":
            reason = "returns_exceed_handovers" if returns > handovers else "counts_out_of_range"
            rate_line = (
                f"return_rate status=inconsistent reason={reason} "
                f"returns={returns} handovers={handovers}"
            )
        else:
            rate_line = (
                f"return_rate status=too_few observed={handovers} needed={MIN_OBSERVATIONS} "
                f"returns={returns} handovers={handovers}"
            )
        probability = returns / handovers if handovers > 0 and 0 <= returns <= handovers else None
        return [
            rate_line,
            _return_model_line(review_counts, probability),
        ]

    return [
        _proportion_text(
            "return_rate",
            returns,
            handovers,
            extras=f"returns={returns} handovers={handovers}",
        ),
        _return_model_line(review_counts, ratio.value),
    ]


def _return_model_line(review_counts: list[float], probability: float | None) -> str:
    """Render the geometric model, retaining its computable terms on rate failure."""
    if probability is None:
        return _mean_text(
            "return_model", review_counts, extras="lambda=unrecorded residual=unrecorded"
        )
    p = probability
    lam = math.inf if p >= 1.0 else -math.log1p(-p)
    expected = math.inf if p >= 1.0 else 1.0 / (1.0 - p)
    observed = sum(review_counts) / len(review_counts) if review_counts else math.nan
    residual = (
        observed - expected if math.isfinite(observed) and math.isfinite(expected) else math.nan
    )
    return (
        f"return_model lambda={lam:.6f} expected_reviews_geometric={expected:.6f} "
        f"observed_reviews_mean={observed:.6f} residual={residual:.6f} "
        f"observed_reviews_variance={pvariance(review_counts):.6f} "
        f"observations={len(review_counts)} residual_basis=observed_minus_geometric"
    )


def _open_findings_level(
    loops: tuple[LoopRecord, ...],
) -> tuple[int | None, int, int]:
    """Return the maximum open-finding level and readable/excluded Work Item counts."""
    readable = tuple(record for record in loops if record.independent_present)
    excluded = len(loops) - len(readable)
    if not readable:
        return (0 if not loops else None), 0, excluded
    levels = (
        sum(finding.is_open for finding in record.independent_findings) for record in readable
    )
    return max(levels, default=0), len(readable), excluded


def _reason_token(value: object) -> str:
    """Make a durable reason safe as one value in the report's key/value lines."""
    if not isinstance(value, str) or not value:
        return "unrecorded"
    value = value.removeprefix("basis=")
    token = "".join(
        character if character.isalnum() or character in "._-" else "_" for character in value
    )
    return token.strip("_") or "unrecorded"


def _queue_stock(rows: tuple[dict[str, object], ...], queue: str, window: Window) -> StockReading:
    """Return the sampled end level, paired flows, trend and evidence reason."""
    dated = sorted(
        (
            (float(row["sampled_at"]), row)
            for row in rows
            if row.get("queue") == queue and _is_number(row.get("sampled_at"))
        ),
        key=lambda item: item[0],
    )
    if not dated:
        return StockReading(None, "unrecorded", "unrecorded", "unrecorded", "no_durable_sample")
    end = [item for item in dated if window.end is None or item[0] <= window.end]
    if not end:
        return StockReading(
            None, "unrecorded", "unrecorded", "unrecorded", "no_sample_at_window_end"
        )
    end_at, end_row = end[-1]
    count = end_row.get("count") if end_row.get("state") == "counted" else None
    if not isinstance(count, int) or isinstance(count, bool):
        return StockReading(
            None,
            "unrecorded",
            "unrecorded",
            "unrecorded",
            _reason_token(end_row.get("count_reason", "unrecorded")),
        )
    before = [item for item in dated if window.start is None or item[0] <= window.start]
    baseline = before[-1] if before else end[0]
    samples = [
        item
        for item in dated
        if (window.start is None or item[0] >= window.start) and item[0] <= end_at
    ]
    baseline_count = baseline[1].get("count") if baseline[1].get("state") == "counted" else None
    if not isinstance(baseline_count, int) or isinstance(baseline_count, bool):
        baseline_count = None
    counts: list[int] = []
    if baseline_count is not None:
        counts.append(baseline_count)
    counts.extend(
        int(item[1]["count"])
        for item in samples
        if item[1].get("state") == "counted"
        and isinstance(item[1].get("count"), int)
        and not isinstance(item[1].get("count"), bool)
        and item != baseline
    )
    if not counts:
        return StockReading(
            count, "unrecorded", "unrecorded", "unrecorded", "no_counted_sample_in_window"
        )
    increases = sum(max(after - before_count, 0) for before_count, after in pairwise(counts))
    decreases = sum(max(before_count - after, 0) for before_count, after in pairwise(counts))
    trend = count - baseline_count if baseline_count is not None else "unrecorded"
    return StockReading(count, str(increases), str(decreases), str(trend), "queue_depth_deltas")


def _dispatch_active_at(
    dispatch: DispatchRecord, boundary: float | None, *, historical: bool
) -> bool | None:
    """Read whether a dispatch was in flight at a boundary, or now."""
    if dispatch.result_state == "unreadable":
        return None
    if not historical:
        return dispatch.result_state == "absent"
    if dispatch.result_state == "absent":
        return True
    if dispatch.result_ended_at is None or boundary is None:
        return None
    return dispatch.result_ended_at > boundary


def _dispatch_level_evidence(
    dispatches: tuple[DispatchRecord, ...], boundary: float | None, *, historical: bool
) -> DispatchLevel:
    """Count known in-flight states while naming excluded incomplete evidence."""
    candidates = tuple(
        dispatch for dispatch in dispatches if boundary is None or dispatch.planned_at <= boundary
    )
    states = tuple(
        _dispatch_active_at(dispatch, boundary, historical=historical) for dispatch in candidates
    )
    known = tuple(state for state in states if state is not None)
    if not states:
        level = 0
    elif not known:
        level = None
    else:
        level = sum(state is True for state in known)
    return DispatchLevel(level, len(states) - len(known))


def _dispatch_level_at(
    dispatches: tuple[DispatchRecord, ...], boundary: float | None, *, historical: bool
) -> int | None:
    """Count known in-flight states without discarding a partial level."""
    return _dispatch_level_evidence(dispatches, boundary, historical=historical).level


def _dispatch_stock(
    dispatches: tuple[DispatchRecord, ...], window: Window
) -> tuple[StockReading, int]:
    """Read in-flight dispatches at the window end and their event flows."""
    # A resolved end is an as-of boundary even when the caller omitted ``--end``;
    # using the current result-file state would make ``--start`` non-reproducible.
    historical_end = window.end is not None
    end_level = _dispatch_level_evidence(dispatches, window.end, historical=historical_end)
    level = end_level.level
    reason = (
        "derived_from_result_end_timestamps"
        if historical_end
        else "derived_from_result_file_presence"
    )
    created = sum(window.contains(dispatch.planned_at) for dispatch in dispatches)
    cleared = sum(
        dispatch.result_ended_at is not None and window.contains(dispatch.result_ended_at)
        for dispatch in dispatches
    )
    start = window.start
    historical_start = window.start is not None
    start_level = _dispatch_level_at(dispatches, start, historical=historical_start)
    if level is None or start is None or start_level is None:
        trend = "unrecorded"
    else:
        trend = str(level - start_level)
    return StockReading(level, str(created), str(cleared), trend, reason), end_level.excluded


def _ledger_present_at(
    dispatch: DispatchRecord, boundary: float | None, *, historical: bool
) -> bool | None:
    """Read whether a ledger row existed at a boundary, or in the current snapshot."""
    if not historical:
        return dispatch.ledger_row
    if not dispatch.ledger_row:
        return False
    if dispatch.ledger_materialised_at is None or boundary is None:
        return None
    return dispatch.ledger_materialised_at <= boundary


def _ledger_stock(
    dispatches: tuple[DispatchRecord, ...], window: Window
) -> tuple[StockReading, int]:
    """Read missing ledger rows at the window end and their materialisation flows."""
    # Match dispatch stock: a derived window end is still the report's snapshot.
    historical_end = window.end is not None
    candidates = tuple(
        dispatch
        for dispatch in dispatches
        if window.end is None or dispatch.planned_at <= window.end
    )
    presence = tuple(
        _ledger_present_at(dispatch, window.end, historical=historical_end)
        for dispatch in candidates
    )
    known = tuple(value for value in presence if value is not None)
    if not presence:
        level = 0
    elif not known:
        level = None
    else:
        level = sum(value is False for value in known)
    excluded = len(presence) - len(known)
    reason = (
        "derived_from_ledger_materialisation_timestamps"
        if historical_end
        else "derived_from_ledger_row_presence"
    )
    created = sum(window.contains(dispatch.planned_at) for dispatch in dispatches)
    cleared = sum(
        dispatch.ledger_materialised_at is not None
        and window.contains(dispatch.ledger_materialised_at)
        for dispatch in dispatches
    )
    start = window.start
    historical_start = window.start is not None
    start_candidates = tuple(
        dispatch for dispatch in dispatches if start is not None and dispatch.planned_at <= start
    )
    start_presence = tuple(
        _ledger_present_at(dispatch, start, historical=historical_start)
        for dispatch in start_candidates
    )
    known_at_start = tuple(value for value in start_presence if value is not None)
    if not start_presence:
        start_level = 0
    elif not known_at_start:
        start_level = None
    else:
        start_level = sum(value is False for value in known_at_start)
    if level is None or start is None or start_level is None:
        trend = "unrecorded"
    else:
        trend = str(level - start_level)
    return StockReading(level, str(created), str(cleared), trend, reason), excluded


def _parse_issue_registrations(porcelain: str) -> tuple[tuple[Path, int | None], ...]:
    """Read ``git worktree list --porcelain`` into (path, issue) pairs."""
    registrations: list[tuple[Path, int | None]] = []
    seen = 0
    for line in porcelain.splitlines():
        if not line.startswith("worktree "):
            continue
        seen += 1
        if seen == 1:
            continue  # git lists the main checkout first; it never owes `done`
        path = Path(line[len("worktree ") :])
        match = ISSUE_WORKTREE_NAME.match(path.name)
        registrations.append((path, int(match.group(1)) if match else None))
    return tuple(registrations)


def _issue_registrations(repo: Path) -> tuple[tuple[Path, int | None], ...] | None:
    """Sweep the registration table locally; None means git could not answer."""
    stdout = _git_text(repo, ["worktree", "list", "--porcelain"])
    if stdout is None:
        return None
    return _parse_issue_registrations(stdout)


def _worktree_stock(
    dispatches: tuple[DispatchRecord, ...], repo: Path, window: Window
) -> WorktreeStock:
    """Join current registrations to ledger-attested landings at the window end.

    A registration counts when its issue name matches a ledger row attesting
    ``gate=landed`` with **any** landing at or before the window's end — an
    issue that landed inside the window and again after it has landed, so it
    still counts.  The tracker's own closure is deliberately unseen — the
    reader makes no network call.

    The level is a **proxy** for the tracker's answer and the reason says so
    rather than picking one error direction.  Under-counting paths: a landing
    whose ledger row was never materialised is invisible here (195 such rows
    at #602's review), an issue closed with no landing at all is never joined,
    and for a past window a tree unregistered since the boundary is already
    gone from the sweep.  Over-counting paths: an issue landed but still open
    — including the `just land` exit-2 state before its own close step — still
    holds a counted registration, an issue reopened after its landing does
    too, the commit timestamp proxy reads no later than the true landing so
    near a boundary it can pull a landing inside it, and for a past window a
    tree registered since the boundary counts although it did not exist at
    it.  Because the magnitudes of those paths are unknowable from these
    records, no net direction is claimed.

    The basis the landing timestamps were read on is reported per level, not
    assumed: a ledger-recorded landing time, a commit-timestamp stand-in, a
    mix of the two, or none at all when no landing participated.

    The registration table is a current snapshot no durable record replays
    historically, like the acceptance lint's repository read, so a window
    with a boundary in the past is **not** an as-of answer: the landing half
    is read at the boundary and the registration half is read now.  That
    split is emitted as its own field rather than folded into the preceding
    one, so a machine reader can parse the caveat instead of swallowing it
    into the basis value (runs_in_flight's split between
    derived_from_result_end_timestamps and _file_presence).
    """
    registrations = _issue_registrations(repo)
    if registrations is None:
        return WorktreeStock(
            StockReading(
                None, "unrecorded", "unrecorded", "unrecorded", "worktree_registrations_unreadable"
            ),
            0,
            0,
        )
    landings = _landing_times(dispatches, repo, [])
    end = window.end
    owing = 0
    unjoinable = 0
    proxied = 0
    attested = 0
    for _, issue in registrations:
        if issue is None:
            unjoinable += 1
            continue
        qualifying = tuple(
            landing for landing in landings.get(issue, ()) if end is None or landing.at <= end
        )
        if qualifying:
            owing += 1
            proxied += sum(not landing.attested for landing in qualifying)
            attested += sum(landing.attested for landing in qualifying)
    # A level no landing participated in must not borrow the attested label:
    # no landing timestamp was read at all.  A mix of the two bases is its
    # own value, not the louder of its halves.
    if not proxied and not attested:
        basis = " landing_basis=none_no_qualifying_landing"
    elif proxied and attested:
        basis = " landing_basis=mixed_commit_timestamp_and_ledger_landed_at"
    elif proxied:
        basis = " landing_basis=commit_timestamp"
    else:
        basis = " landing_basis=ledger_landed_at"
    if proxied:
        basis += " proxy_bias=reads_early_over_counts_near_boundary"
    # The landing half honours the boundary; the registration half cannot — the
    # table is read live and nothing replays it — so a past boundary makes the
    # level a mixed-time read.  Emitted as its own key=value field: appended
    # straight onto the basis value it would be unparsable, and a caveat no
    # field boundary marks is one a machine reader silently swallows.
    temporal = (
        " temporal=live_registration_sweep_not_as_of_window_end" if window.end is not None else ""
    )
    return WorktreeStock(
        StockReading(
            owing,
            "unrecorded",
            "unrecorded",
            "unrecorded",
            "registered_issue_worktrees_joined_to_ledger_attested_landings"
            f"_tracker_closure_unseen{basis}{temporal}",
        ),
        len(registrations),
        unjoinable,
    )


def _worktree_bias_text(window: Window) -> str:
    """Name the level's error paths and refuse a single net direction.

    One token per path with the direction it pushes, because a bare
    ``bias=under_counts`` would be false for the paths that over-count and a
    reader leaning on it would misread a disagreeing number.  Four
    magnitudes-unknown paths are always in play — the two unmaterialisation
    and closure-mismatch paths, since a landing is only ever a proxy for the
    tracker's own closure — and the sweep-liveness pair joins them only where
    the window ends in the past, when the registration half is read after its
    own boundary.
    """
    paths = [
        "unmaterialised_ledger_landings:under_counts",
        "closed_issue_without_landing:under_counts",
        "issue_reopened_after_landing:over_counts",
        "landed_issue_still_open:over_counts",
    ]
    if window.end is not None:
        paths += [
            "registrations_removed_since_boundary:under_counts",
            "registrations_added_since_boundary:over_counts",
        ]
    return (
        " registration_basis=current_snapshot bias=mixed net_direction=undetermined"
        f" bias_paths={','.join(paths)}"
    )


def _provisional_stock(repo: Path) -> tuple[int | None, str]:
    """Count unique unratified provisional terms through the canonical acceptance linter."""
    try:
        lint = acceptance.lint_repository(repo)
    except (OSError, ValueError, TypeError):
        return None, "acceptance_source_unreadable"
    terms = {term for report in lint.reports for term in report.unratified}
    return len(terms), "current_repository_snapshot_acceptance_lint"


def _minimum_alarm_status(level: int | None, threshold: int) -> str:
    """Evaluate a ruled lower-bound alarm without turning unknown into zero."""
    if level is None:
        return "unrecorded"
    return "below_alarm" if level < threshold else "observed"


def _maximum_setpoint_status(level: int | None, threshold: int) -> str:
    """Evaluate a ruled upper-bound setpoint without turning unknown into zero."""
    if level is None:
        return "unrecorded"
    return "above_setpoint" if level > threshold else "at_setpoint"


def _level_text(level: int | None) -> str:
    """Render a stock level while preserving an unknown level as unknown."""
    return str(level) if level is not None else "unrecorded"


def stock_lines(inputs: Inputs, repo: Path, window: Window) -> list[str]:
    """Render end-window stock levels separately from their flows."""
    ready = _queue_stock(inputs.queue_rows, "ready_work", window)
    blocked = _queue_stock(inputs.queue_rows, "dispatch_slot", window)
    runs, runs_excluded = _dispatch_stock(inputs.dispatches, window)
    ledger, ledger_excluded = _ledger_stock(inputs.dispatches, window)
    provisional, provisional_reason = _provisional_stock(repo)
    worktrees = _worktree_stock(inputs.dispatches, repo, window)
    open_findings, open_work_items, findings_excluded = _open_findings_level(
        _selected_loops(inputs, window)
    )
    return [
        (
            f"stock ready_work level={_level_text(ready.level)} setpoint=>={READY_SETPOINT} "
            f"status={_minimum_alarm_status(ready.level, READY_SETPOINT)} "
            f"alarm=below_{READY_SETPOINT} flow_creation={ready.flow_creation} "
            f"flow_clearing={ready.flow_clearing} trend={ready.trend} reason={ready.reason}"
        ),
        (
            f"stock blocked_work level={_level_text(blocked.level)} setpoint=unruled "
            f"status=unruled source=dispatch_slot flow_creation={blocked.flow_creation} "
            f"flow_clearing={blocked.flow_clearing} trend={blocked.trend} reason={blocked.reason}"
        ),
        (
            f"stock runs_in_flight level={_level_text(runs.level)} "
            f"excluded_without_ended_at={runs_excluded} setpoint=unruled "
            f"status=unruled flow_creation={runs.flow_creation} "
            f"flow_clearing={runs.flow_clearing} trend={runs.trend} reason={runs.reason}"
        ),
        (
            f"stock open_findings_per_work_item level={_level_text(open_findings)} "
            f"setpoint=at_most_{OPEN_FINDINGS_SETPOINT} "
            f"status={_maximum_setpoint_status(open_findings, OPEN_FINDINGS_SETPOINT)} "
            f"aggregation=max_per_work_item work_items={open_work_items} "
            f"excluded_without_independent_record={findings_excluded} "
            "flow_creation=unrecorded flow_clearing=unrecorded trend=unrecorded "
            "reason=review_loop_open_findings"
        ),
        (
            f"stock worktrees_owing_done level={_level_text(worktrees.reading.level)} "
            f"setpoint=at_most_{WORKTREES_SETPOINT} "
            f"status={_maximum_setpoint_status(worktrees.reading.level, WORKTREES_SETPOINT)} "
            "alarm=3 "
            f"registrations={worktrees.registrations} "
            f"excluded_without_issue_name={worktrees.unjoinable} "
            "flow_creation=unrecorded flow_clearing=unrecorded trend=unrecorded "
            f"reason={worktrees.reading.reason}"
            + (_worktree_bias_text(window) if worktrees.reading.level is not None else "")
        ),
        (
            f"stock dispatches_without_ledger level={_level_text(ledger.level)} "
            f"excluded_without_materialised_at={ledger_excluded} "
            f"status={_maximum_setpoint_status(ledger.level, NO_LEDGER_SETPOINT)} "
            f"setpoint=at_most_{NO_LEDGER_SETPOINT} alarm=20 "
            f"flow_creation={ledger.flow_creation} flow_clearing={ledger.flow_clearing} "
            f"trend={ledger.trend} reason={ledger.reason}"
        ),
        (
            "stock unratified_provisional_terms "
            f"level={provisional if provisional is not None else 'unrecorded'} "
            f"status={_maximum_setpoint_status(provisional, UNRATIFIED_SETPOINT)} "
            f"setpoint=at_most_{UNRATIFIED_SETPOINT} alarm=5 flow_creation=unrecorded "
            f"flow_clearing=unrecorded trend=unrecorded reason={provisional_reason}"
        ),
    ]


def delivery_gap_lines() -> list[str]:
    """State the two quality measures that current canonical records cannot answer."""
    return [
        (
            "delivery_gap_quality scope=audit status=unrecorded "
            "reason=durable_audit_gap_field_not_present outside_loop_metrics=yes"
        ),
        (
            "delivery_gap_quality scope=post_landing_review status=unrecorded "
            "reason=durable_post_landing_gap_field_not_present outside_loop_metrics=yes"
        ),
    ]


def report_lines(inputs: Inputs, repo: Path, window: Window) -> tuple[str, ...]:
    """Build the complete report without mutating any source."""
    selected_loops = _selected_loops(inputs, window)
    selected_dispatches = _selected_dispatches(inputs, window)
    boundary = (
        f"start={format_timestamp(window.start)} end={format_timestamp(window.end)} "
        f"basis={'explicit' if window.explicit else 'all_durable_source_timestamps'}"
    )
    diagnostics = list(inputs.diagnostics)
    lines = [
        "loop_metrics schema=cti.loop-metrics/1 read_only=yes gates=no controller=no mlflow=no",
        f"window {boundary}",
        "loop_time=review_loop_files_have_no_timestamps; explicit_windows_select_by_issue_dispatch",
        f"observations dispatches={len(selected_dispatches)} review_loops={len(selected_loops)}",
        *injection_lines(selected_loops),
        *dismissal_lines(selected_loops),
        *findings_lines(selected_loops, selected_dispatches, window),
        *clean_round_lines(selected_loops),
        *cycle_lines(inputs.dispatches, repo, window, diagnostics),
        *return_lines(inputs.dispatches, window),
        *stock_lines(inputs, repo, window),
        *delivery_gap_lines(),
        (
            "metric_scope self_review=injection,catch,dismissal,clean_round; "
            "independent_review=findings,severity,return; no_self_review_is_not_zero"
        ),
    ]
    lines.extend(diagnostics)
    return tuple(lines)


def _cli_timestamp(value: str) -> float:
    """Argparse converter for an epoch or timezone-aware ISO boundary."""
    parsed = parse_timestamp(value)
    if parsed is None:
        message = "use a finite epoch or timezone-aware ISO-8601 timestamp"
        raise argparse.ArgumentTypeError(message)
    return parsed


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse the read-only command's optional source roots and window."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--start", type=_cli_timestamp, default=None, help="inclusive ISO-8601 or epoch boundary"
    )
    parser.add_argument(
        "--end", type=_cli_timestamp, default=None, help="inclusive ISO-8601 or epoch boundary"
    )
    parser.add_argument(
        "--dispatch-root",
        type=Path,
        default=Path(os.environ.get("CTI_DISPATCH_DIR", str(DEFAULT_DISPATCH_ROOT))),
    )
    parser.add_argument(
        "--review-root",
        type=Path,
        default=Path(os.environ.get("CTI_REVIEW_DIR", str(DEFAULT_REVIEW_ROOT))),
    )
    parser.add_argument(
        "--queue-root",
        type=Path,
        default=Path(os.environ.get("CTI_QUEUE_DIR", str(DEFAULT_QUEUE_ROOT))),
    )
    parser.add_argument("--repo", type=Path, default=REPO)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Print the report and exit zero; metric values never gate a caller."""
    args = parse_args(argv)
    inputs = read_inputs(args.dispatch_root, args.review_root, args.queue_root)
    if args.start is not None and args.end is not None and args.start > args.end:
        print("window status=unreadable reason=start_after_end")  # noqa: T201 — command output
        return 0
    window = resolve_window(
        inputs,
        args.start,
        args.end,
        explicit=args.start is not None or args.end is not None,
    )
    for line in report_lines(inputs, args.repo, window):
        print(line)  # noqa: T201 — command output
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
