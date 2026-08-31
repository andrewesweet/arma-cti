"""Capability ports and deterministic fakes for the System-of-Work Controller."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, NoReturn, Protocol, cast, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Callable

    from controller_store import SchedulingLock

sys.path.insert(0, str(Path(__file__).parent))

import controller_policy as policy
import dispatch_stop
import queue_policy
import recovery

CONTROL_FACTS_SCHEMA: Final = "control-facts/v1"
CONTROL_FACTS_FIELDS: Final = frozenset(
    {"schema", "configured_curator", "desired_outcomes", "initiatives", "work_items", "work_runs"}
)
CONTROL_FACTS_OPTIONAL_FIELDS: Final = frozenset(
    {"worktree_debt", "wip_limit", "external_bars", "priority_order", "ready_transitions"}
)
DELIVERY_SCHEMA: Final = "work-run-delivery/v1"
DELIVERY_FIELDS: Final = frozenset({"schema", "work_run"})
RESULT_HARNESS_FAILURE_STATUSES: Final = frozenset(
    {"harness_failed_after_child", "child_state_unknown"}
)
RESULT_NON_RESULT_STATUS: Final = "child_not_launched"
RESULT_STOPPED_STATE: Final = "stopped"
RESULT_OUTCOME_CLASSES: Final[dict[str, str]] = {
    "quota_exhausted": "quota_exhausted",
    "provider_error": "infra_unavailable",
    "provider_refused": "provider_refused",
}
FACT_FIELDS: Final = frozenset({"key", "state"})
WORK_ITEM_OPTIONAL_FIELDS: Final = frozenset(
    {"issue", "blocked_by", "priority", "exclusive_resources", "seat", "profile", "ready_at"}
)
WORK_RUN_OPTIONAL_FIELDS: Final = frozenset(
    {
        "work_item_key",
        "dispatch_id",
        "failure_class",
        "worktree",
        "issue",
        "candidate_sha",
        "reviewed_sha",
        "review_status",
        "review_dispatch_id",
        "adjudication_sha",
        "adjudication_status",
        "gate_sha",
        "gate_status",
        "landed_sha",
        "close_evidence_sha",
        "recovery_kind",
        "result_published",
        "delivery_conflict",
    }
)
DEBT_FIELDS: Final = frozenset({"issue", "path"})
DEBT_OPTIONAL_FIELDS: Final = frozenset({"work_item_key"})
BAR_FIELDS: Final = frozenset({"key", "kind"})
BAR_OPTIONAL_FIELDS: Final = frozenset({"detail"})
READY_TRANSITION_FIELDS: Final = frozenset({"key", "recorded_at"})
OUTCOME_FIELDS: Final = frozenset({"key", "revision", "content_digest"})
OUTCOME_OPTIONAL_FIELDS: Final = frozenset({"content", "parent_issue"})


class FactCollectionError(RuntimeError):
    """A configured Control Fact source could not be normalized."""

    code: Final = "control_facts_unreadable"

    def __init__(self, reason: str) -> None:
        """Expose the exact source failure without inventing facts."""
        self.reason = reason
        super().__init__(f"refusal={self.code} reason={reason}")


def _fact_fail(reason: str) -> NoReturn:
    """Raise the fact-source refusal after attaching its source detail."""
    raise FactCollectionError(reason)


class Clock(Protocol):
    """The only source of controller timestamps."""

    def now(self) -> str:
        """Return an RFC 3339 timestamp."""


class IdentitySource(Protocol):
    """The only source of controller and cycle identity."""

    def identity(self) -> str:
        """Return the stable identity of this controller process."""


class FactCollector(Protocol):
    """Read and normalize current Control Facts."""

    def collect(self) -> policy.ControlFacts:
        """Collect one point-in-time fact set."""


@runtime_checkable
class HistoricalFactCollector(Protocol):
    """Read current facts while giving delivery recovery the prior run set."""

    def collect_with_previous(
        self, previous_work_runs: tuple[policy.WorkRunFact, ...]
    ) -> policy.ControlFacts:
        """Collect facts after classifying prior runs that ended without a result."""


class DeliveryFactSource(Protocol):
    """Read structured delivery evidence for the current Work Runs."""

    def collect(self, existing: tuple[policy.WorkRunFact, ...]) -> tuple[policy.WorkRunFact, ...]:
        """Return current runs, replacing only matching dispatch identities."""


class RecoveryClassifier(Protocol):
    """Use the existing recovery procedure to classify a no-result run."""

    def classify(self, run: policy.WorkRunFact) -> str | None:
        """Return the recovery verdict kind, or no computable verdict."""


class ActionPort(Protocol):
    """Apply one already-derived Control Action."""

    def apply(self, action: policy.ControlAction) -> object | None:
        """Apply an action through the port's external capability."""


@dataclass(frozen=True, slots=True)
class ActionPorts:
    """The four mutation ports owned by one Controller application instance."""

    tracker: ActionPort
    worktree: ActionPort
    dispatch: ActionPort
    evidence: ActionPort


class DetachedWorkRunPort(Protocol):
    """Start a detached Work Run without taking the scheduling writer lock."""

    def start(self, run_key: str) -> None:
        """Start one detached Work Run."""


@dataclass(frozen=True, slots=True)
class SystemClock:
    """Production clock adapter; policy never sees this implementation."""

    def now(self) -> str:
        """Return current UTC time for a journal record."""
        return datetime.now(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class SystemIdentity:
    """Production identity adapter with an intentionally stable local name."""

    value: str = "local-controller"

    def identity(self) -> str:
        """Return the configured controller identity."""
        return self.value


@dataclass
class FakeClock:
    """Deterministic clock fake for controller and journal tests."""

    value: str

    def now(self) -> str:
        """Return the arranged timestamp."""
        return self.value


@dataclass
class FakeIdentity:
    """Deterministic identity fake for controller and journal tests."""

    value: str

    def identity(self) -> str:
        """Return the arranged identity."""
        return self.value


@dataclass
class FakeFactCollector:
    """Fact collector fake that exposes every read to its test."""

    facts: policy.ControlFacts
    collect_calls: int = 0

    def collect(self) -> policy.ControlFacts:
        """Return the same arranged normalized facts."""
        self.collect_calls += 1
        return self.facts


@dataclass
class DefaultFactCollector:
    """Conservative first-slice collector before tracker adapters are admitted."""

    def collect(self) -> policy.ControlFacts:
        """Read configured facts or report the empty graph rather than inventing an Initiative."""
        source = os.environ.get("CTI_CONTROL_FACTS_FILE")
        if source:
            return FileFactCollector(Path(source)).collect()
        return policy.ControlFacts(
            configured_curator=None,
            desired_outcomes=(),
            initiatives=(),
            work_items=(),
            work_runs=(),
        )


@dataclass(frozen=True)
class RuntimeFactCollector:
    """Enrich a normalized graph with the queue's live capacity evidence.

    The queue remains the authority for worktree registrations, dispatch records,
    and its ruled WIP limit.  This adapter only translates that existing view into
    Controller facts; it does not reimplement queue selection or refusal ladders.
    """

    base: FactCollector
    root: Path
    dispatch_dir: Path
    queue_dir: Path | None = None
    delivery: DeliveryFactSource | None = None

    def collect(self) -> policy.ControlFacts:
        """Collect graph facts, then add live runs and owed worktree debt."""
        return self.collect_with_previous(())

    def collect_with_previous(
        self, previous_work_runs: tuple[policy.WorkRunFact, ...]
    ) -> policy.ControlFacts:
        """Collect facts and classify prior runs before the controller plans a launch."""
        facts = self.base.collect()
        in_flight = queue_policy.gather(self.root, self.dispatch_dir)
        limit = facts.wip_limit
        if self.queue_dir is not None:
            queue_store = queue_policy.Store(self.queue_dir)
            configured, refusal = queue_policy.read_policy(queue_store)
            if refusal is not None or configured is None:
                _fact_fail(f"queue_policy={refusal.kind if refusal is not None else 'unreadable'}")
            limit = configured.wip_limit.value

        debts = tuple(
            policy.WorktreeDebtFact(
                issue=holder.issue,
                path=str(holder.worktree),
                work_item_key=next(
                    (item.key for item in facts.work_items if item.issue == holder.issue),
                    None,
                ),
            )
            for holder in in_flight.owed
            if holder.worktree is not None
        )
        runs = list(policy.merge_work_run_observations(previous_work_runs, facts.work_runs))
        if self.delivery is not None:
            runs = list(self.delivery.collect(tuple(runs)))
        bars = list(facts.external_bars)
        if in_flight.github.startswith("unreadable"):
            bars.extend(
                policy.ExternalBarFact(item.key, "infra_unavailable", in_flight.github)
                for item in facts.work_items
                if item.state in policy.OPEN_WORK_ITEM_STATES
                and not any(bar.key == item.key for bar in bars)
            )
        for holder in in_flight.holders:
            item_key = next(
                (item.key for item in facts.work_items if item.issue == holder.issue),
                str(holder.issue),
            )
            dispatch_id = next(
                (
                    source.removeprefix("dispatch:")
                    for source in holder.sources
                    if source.startswith("dispatch:")
                ),
                None,
            )
            if any(_run_matches_holder(run, item_key, holder.issue, dispatch_id) for run in runs):
                continue
            runs.append(
                policy.WorkRunFact(
                    key=dispatch_id or f"issue-{holder.issue}",
                    state="running",
                    work_item_key=item_key,
                    dispatch_id=dispatch_id,
                    worktree=str(holder.worktree) if holder.worktree is not None else None,
                    issue=holder.issue,
                )
            )
        return replace(
            facts,
            work_runs=tuple(runs),
            worktree_debt=debts,
            wip_limit=limit,
            external_bars=tuple(bars),
        )


def _run_matches_holder(
    run: policy.WorkRunFact,
    item_key: str,
    issue: int,
    dispatch_id: str | None,
) -> bool:
    """Avoid duplicating a queue holder while retaining distinct terminal history."""
    same_item = run.item_key == item_key or run.issue == issue
    if dispatch_id is not None:
        if run.dispatch_id == dispatch_id:
            return True
        return (
            run.dispatch_id is None
            and same_item
            and (
                run.state in policy.LIVE_WORK_RUN_STATES
                or run.failure_class in policy.NON_RESULT_CLASSES
            )
        )
    return same_item and (
        run.state in policy.LIVE_WORK_RUN_STATES or run.failure_class in policy.NON_RESULT_CLASSES
    )


# The recovery verdicts that conclude rather than observe.  `lost_work` and
# `finished_and_cleaned` cannot be un-concluded by a later look, so they are
# the only kinds the terminal branch of `_with_recovery` stamps and the only
# ones a later cycle leaves alone.  `still_live` and `unproven` are
# observations — true when taken, silent about now — so they keep the run's
# slot and stay open to re-classification, which is what lets a dispatch
# classified healthy at one cycle resolve once its agent has died (#625).  A
# kind missing from this set defaults to observed, never concluded: an
# unknown verdict must not release a slot by accident.
#
# A terminal verdict also claims the agent is gone, and `recovery.py` says
# itself that it cannot read that: unpushed commits are equally what a live
# agent's ordinary progress looks like.  The occupancy scan is what carries
# the claim, and #625's cap ruling is what bounds it: a terminal kind
# concludes only where the scan *positively* found nobody — no matched
# process, no deleted cwd inside the tree, no unreadable cwd on a process of
# this user's, and a `/proc` it could list.  Every could-not-look reads
# `still_live`, because failing closed here costs a held slot until someone
# looks while failing open costs a duplicate dispatch onto live work.
# The human's cap ruling deliberately accepts one limit: a same-uid unreadable-cwd process born
# after `planned_at` can keep this dispatch indeterminate for its lifetime, because only a process
# proven older than the dispatch can be excluded.
TERMINAL_RECOVERY_KINDS: Final = frozenset({"lost_work", "finished_and_cleaned"})
# This intentionally remains a byte-identical twin of `controller_policy.RECOVERY_RELAUNCH_KINDS`
# while #630 keeps the ports adapter and pure policy boundaries separate.


@dataclass(frozen=True)
class ExistingRecoveryClassifier:
    """Adapter around ``tools/recovery.py``'s existing read-only classification.

    `recovery.py` declines to judge whether a worktree's agent is alive, and a
    terminal verdict needs exactly that judgement, so this adapter answers it
    with the project's own authority for the question — ``dispatch_stop.scan``,
    the `/proc` read #105 built to answer whether anyone is still working in a
    tree.  A terminal verdict concludes only where the scan *positively* found
    nobody; any look that could not be made — an unreadable cwd, a deleted cwd
    inside the tree, a `/proc` that could not be listed — keeps the slot and
    reads `still_live` (#625's cap ruling), because an absence of evidence is
    not evidence of absence.
    """

    repository: Path
    watch_dir: Path
    dispatch_dir: Path
    now: Callable[[], int] | None = None
    machine: dispatch_stop.Machine = field(default_factory=dispatch_stop.Machine)

    def classify(self, run: policy.WorkRunFact) -> str | None:
        """Ask recovery only for a dispatch with no published result."""
        if not run.dispatch_id:
            return None
        record = self.dispatch_dir / run.dispatch_id
        if not record.is_dir() or (record / "result.json").is_file():
            return None
        try:
            evidence = recovery.gather_check(
                run.dispatch_id,
                repo=self.repository,
                watch_dir=self.watch_dir,
                dispatch_dir=self.dispatch_dir,
                now=(self.now or (lambda: int(datetime.now(UTC).timestamp())))(),
            )
        except Exception:  # noqa: BLE001 — an unavailable recovery read is not a result
            return None
        if evidence is None:
            return None
        verdict = recovery.decide(evidence)
        if verdict.kind in TERMINAL_RECOVERY_KINDS and not self._proven_empty(
            evidence.tree.path, record
        ):
            return recovery.LIVE
        return verdict.kind

    def _proven_empty(self, tree: Path, dispatch_record: Path) -> bool:
        """Whether the scan positively found nobody working in `tree`.

        Only a positive empty may conclude a terminal verdict (#625's cap ruling),
        and each of these says the scan cannot support the claim that the agent is
        gone: a matched process, a live process the tree was removed under, or a pid
        of this user's whose cwd could not be read and whose start time could not
        prove it predates the dispatch, or a `/proc` it could not list.  A
        different-uid unreadable cwd is excluded by `scan` itself — that read was
        never visible to it — and a known controller-chain cwd failure is a reasoned
        identity exclusion rather than a failure to look, so neither holds the slot.
        """
        found = dispatch_stop.scan(
            tree,
            self.machine,
            dispatch_created_at=dispatch_stop.record_created_at(dispatch_record),
        )
        return found.proven_empty


@dataclass(frozen=True)
class DispatchDeliveryFactCollector:
    """Read structured Work Run delivery records beside dispatch records.

    ``delivery.json`` is the adapter's typed boundary.  Dispatch logs and
    command output are deliberately never read here; a human-oriented line
    cannot clear a candidate or close a Work Item.
    """

    dispatch_dir: Path
    recovery: RecoveryClassifier | None = None

    def collect(self, existing: tuple[policy.WorkRunFact, ...]) -> tuple[policy.WorkRunFact, ...]:
        """Merge delivery records, then classify no-result runs before scheduling."""
        runs = list(existing)
        if self.dispatch_dir.is_dir():
            for record in sorted(self.dispatch_dir.iterdir(), key=lambda path: path.name):
                delivery = record / "delivery.json"
                if delivery.is_file():
                    self._merge(runs, _read_delivery(delivery))
                result_delivery = _read_result_delivery(record / "result.json")
                if result_delivery is not None:
                    self._merge(runs, result_delivery)
        if self.recovery is not None:
            runs = [self._with_recovery(run) for run in runs]
        return tuple(runs)

    def _merge(self, runs: list[policy.WorkRunFact], observed: policy.WorkRunFact) -> None:
        """Replace one exact dispatch observation without appending a duplicate."""
        match = next(
            (
                index
                for index, current in enumerate(runs)
                if policy.same_work_run(current, observed)
            ),
            None,
        )
        if match is None:
            runs.append(observed)
        else:
            runs[match] = policy.merge_work_run_observation(runs[match], observed)

    def _with_recovery(self, run: policy.WorkRunFact) -> policy.WorkRunFact:
        """Attach an existing recovery verdict while preserving non-result semantics.

        Stickiness is carried by the state, never by the verdict: the terminal
        branch below is the only writer of ``non_result``, so a concluded run
        is skipped by its state and an observed one — `still_live`, `unproven`
        — falls through and is re-derived every cycle.  A `non_result` run
        carrying a non-terminal verdict is one an earlier cycle concluded as a
        guess, so it too is re-derived rather than trusted.

        An observation writes its verdict and nothing else.  `still_live` is a
        look at a tree, not a workflow fact: whether a run is reviewed, gated,
        stalled or anything else belongs to the delivery facts that moved it
        there, so the progression is never restated here for a look to walk
        back over.
        """
        if run.landed_sha is not None:
            return run
        if run.state == policy.NON_RESULT and (
            run.recovery_kind is None or run.recovery_kind in TERMINAL_RECOVERY_KINDS
        ):
            return run
        kind = self.recovery.classify(run) if self.recovery is not None else None
        if kind is None:
            return run
        if kind in TERMINAL_RECOVERY_KINDS:
            return replace(
                run,
                state=policy.NON_RESULT,
                failure_class=run.failure_class or "interrupted",
                recovery_kind=kind,
            )
        return replace(run, recovery_kind=kind)


def _read_delivery(path: Path) -> policy.WorkRunFact:
    """Read one strict typed delivery envelope."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        _fact_fail(f"source={path}: {error}")
    if (
        not isinstance(raw, dict)
        or set(raw) != DELIVERY_FIELDS
        or raw.get("schema") != DELIVERY_SCHEMA
    ):
        _fact_fail(f"source={path}: delivery envelope")
    value = raw.get("work_run")
    if not isinstance(value, dict):
        _fact_fail(f"source={path}: delivery work_run")
    run = _fact(value, "work_runs", path)
    if run.dispatch_id is None or run.dispatch_id != path.parent.name:
        _fact_fail(f"source={path}: delivery dispatch_id")
    return replace(
        run,
        state=policy.derived_work_run_state(run),
        delivery_conflict=run.delivery_conflict or policy.delivery_identity_conflict(run),
    )


def _read_result_delivery(path: Path) -> policy.WorkRunFact | None:
    """Read structured delivery or typed non-result evidence from a result."""
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        _fact_fail(f"source={path}: {error}")
    if not isinstance(raw, dict):
        return None
    result_dispatch_id = _result_dispatch_id(raw, path)
    if "delivery" not in raw:
        return _read_result_non_result(raw, path)
    value = raw["delivery"]
    if not isinstance(value, dict):
        _fact_fail(f"source={path}: delivery")
    run = _fact(value, "work_runs", path)
    if run.dispatch_id is None or run.dispatch_id != result_dispatch_id:
        _fact_fail(f"source={path}: delivery dispatch_id")
    return replace(
        run,
        state=policy.derived_work_run_state(run),
        result_published=True,
        delivery_conflict=run.delivery_conflict or policy.delivery_identity_conflict(run),
    )


def _read_result_non_result(raw: dict[str, object], path: Path) -> policy.WorkRunFact | None:
    """Translate only the dispatcher's typed terminal fields, never its prose."""
    status = _result_text(raw, "status", path)
    outcome = _result_text(raw, "outcome", path)
    failure_class = _result_text(raw, "failure_class", path)
    refusal = _result_text(raw, "refusal", path)
    typed_class = _result_non_result_class(
        status,
        outcome,
        failure_class,
        refusal,
        {"state": RESULT_STOPPED_STATE}
        if dispatch_stop.is_stop_closeout(raw)
        else raw.get("terminal_state"),
    )
    if typed_class is None:
        return None
    dispatch_id = _result_dispatch_id(raw, path)
    return policy.WorkRunFact(
        key=dispatch_id,
        state=policy.NON_RESULT,
        dispatch_id=dispatch_id,
        failure_class=typed_class,
        result_published=True,
    )


def _result_dispatch_id(raw: dict[str, object], path: Path) -> str:
    """Require a result's optional top-level identity to match its directory."""
    dispatch_id = raw.get("dispatch_id", path.parent.name)
    if not isinstance(dispatch_id, str) or not dispatch_id or dispatch_id != path.parent.name:
        _fact_fail(f"source={path}: result dispatch_id")
    return dispatch_id


def _result_text(raw: dict[str, object], name: str, path: Path) -> str | None:
    """Read one optional typed result field without accepting coercion.

    The dispatcher writes an optional field it has no value for as an empty
    string (``Refusal.failure_class`` defaults to ``""``), so an empty string
    reads as absent rather than malformed: a record the dispatcher itself
    writes must stay readable.
    """
    if name not in raw:
        return None
    value = raw[name]
    if not isinstance(value, str):
        _fact_fail(f"source={path}: result {name}")
    return value or None


def _result_non_result_class(
    status: str | None,
    outcome: str | None,
    failure_class: str | None,
    refusal: str | None,
    terminal: object,
) -> str | None:
    """Map the dispatcher's closed result vocabulary to controller non-results."""
    if refusal is not None:
        return failure_class if failure_class in policy.NON_RESULT_CLASSES else "infra_unavailable"
    if isinstance(terminal, dict) and terminal == {"state": RESULT_STOPPED_STATE}:
        return "interrupted"
    if status in RESULT_HARNESS_FAILURE_STATUSES:
        return "untyped_harness_failure"
    if status == RESULT_NON_RESULT_STATUS:
        return "infra_unavailable"
    if failure_class in policy.NON_RESULT_CLASSES:
        return failure_class
    return RESULT_OUTCOME_CLASSES.get(outcome) if outcome is not None else None


@dataclass(frozen=True)
class FileFactCollector:
    """Normalize one strict local Control Fact snapshot for a controller cycle."""

    path: Path

    def collect(self) -> policy.ControlFacts:
        """Read one versioned fact envelope and fail closed on every malformed shape."""
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            _fact_fail(f"source={self.path}: {error}")
        if not isinstance(raw, dict) or not (
            set(raw) >= CONTROL_FACTS_FIELDS
            and set(raw) <= CONTROL_FACTS_FIELDS | CONTROL_FACTS_OPTIONAL_FIELDS
        ):
            _fact_fail(f"source={self.path}: fields")
        if raw.get("schema") != CONTROL_FACTS_SCHEMA:
            _fact_fail(f"source={self.path}: schema")
        curator = raw.get("configured_curator")
        if curator is not None and (not isinstance(curator, str) or not curator.strip()):
            _fact_fail(f"source={self.path}: configured_curator")
        return policy.ControlFacts(
            cast("str | None", curator),
            tuple(_outcome(item, self.path) for item in _list(raw, "desired_outcomes", self.path)),
            tuple(
                _fact(item, "initiatives", self.path)
                for item in _list(raw, "initiatives", self.path)
            ),
            tuple(
                _fact(item, "work_items", self.path) for item in _list(raw, "work_items", self.path)
            ),
            tuple(
                _fact(item, "work_runs", self.path) for item in _list(raw, "work_runs", self.path)
            ),
            tuple(
                _debt(item, self.path) for item in _list_optional(raw, "worktree_debt", self.path)
            ),
            _optional_limit(raw, self.path),
            tuple(
                _bar(item, self.path) for item in _list_optional(raw, "external_bars", self.path)
            ),
            tuple(
                _priority(item, self.path)
                for item in _list_optional(raw, "priority_order", self.path)
            ),
            tuple(
                _ready_transition(item, self.path)
                for item in _list_optional(raw, "ready_transitions", self.path)
            ),
        )


def _list(document: dict[str, object], name: str, source: Path) -> list[object]:
    """Read one required list from a fact envelope."""
    value = document.get(name)
    if not isinstance(value, list):
        _fact_fail(f"source={source}: {name}")
    return value


def _list_optional(document: dict[str, object], name: str, source: Path) -> list[object]:
    """Read an optional list, treating its absence as an empty collection."""
    if name not in document:
        return []
    return _list(document, name, source)


def _fact(
    value: object, name: str, source: Path
) -> policy.InitiativeFact | policy.WorkItemFact | policy.WorkRunFact:
    """Normalize one lifecycle fact with its collection name retained in errors."""
    if not isinstance(value, dict):
        _fact_fail(f"source={source}: {name} entry")
    optional = (
        WORK_ITEM_OPTIONAL_FIELDS
        if name == "work_items"
        else (WORK_RUN_OPTIONAL_FIELDS if name == "work_runs" else frozenset())
    )
    if set(value) != FACT_FIELDS and not (
        set(value).issubset(FACT_FIELDS | optional) and FACT_FIELDS.issubset(value)
    ):
        _fact_fail(f"source={source}: {name} entry")
    key = value.get("key")
    state = value.get("state")
    if not isinstance(key, str) or not key or not isinstance(state, str) or not state:
        _fact_fail(f"source={source}: {name} value")
    if name == "initiatives":
        return policy.InitiativeFact(key, state)
    if name == "work_items":
        return policy.WorkItemFact(
            key,
            state,
            _optional_positive_int(value, "issue", source, name),
            _string_list_optional(value, "blocked_by", source, name),
            _optional_nonnegative_int(value, "priority", source, name),
            _string_list_optional(value, "exclusive_resources", source, name),
            _optional_nonempty_text(value, "seat", source, name) or "implementer",
            _optional_nonempty_text(value, "profile", source, name),
            _optional_nonempty_text(value, "ready_at", source, name),
        )
    run = policy.WorkRunFact(
        key,
        state,
        _optional_nonempty_text(value, "work_item_key", source, name),
        _optional_nonempty_text(value, "dispatch_id", source, name),
        _optional_nonempty_text(value, "failure_class", source, name),
        _optional_nonempty_text(value, "worktree", source, name),
        _optional_positive_int(value, "issue", source, name),
        _optional_nonempty_text(value, "candidate_sha", source, name),
        _optional_nonempty_text(value, "reviewed_sha", source, name),
        _optional_nonempty_text(value, "review_status", source, name),
        _optional_nonempty_text(value, "review_dispatch_id", source, name),
        _optional_nonempty_text(value, "adjudication_sha", source, name),
        _optional_nonempty_text(value, "adjudication_status", source, name),
        _optional_nonempty_text(value, "gate_sha", source, name),
        _optional_nonempty_text(value, "gate_status", source, name),
        _optional_nonempty_text(value, "landed_sha", source, name),
        _optional_nonempty_text(value, "close_evidence_sha", source, name),
        _optional_nonempty_text(value, "recovery_kind", source, name),
        _optional_bool(value, "result_published", source, name),
        _optional_bool(value, "delivery_conflict", source, name),
    )
    return replace(run, state=policy.derived_work_run_state(run))


def _optional_nonempty_text(
    value: dict[str, object], field_name: str, source: Path, collection: str
) -> str | None:
    """Read an optional non-empty string from an extended fact."""
    if field_name not in value:
        return None
    item = value[field_name]
    if not isinstance(item, str) or not item:
        _fact_fail(f"source={source}: {collection} {field_name}")
    return item


def _optional_positive_int(
    value: dict[str, object], field_name: str, source: Path, collection: str
) -> int | None:
    """Read an optional positive integer from an extended fact."""
    if field_name not in value:
        return None
    item = value[field_name]
    if isinstance(item, bool) or not isinstance(item, int) or item < 1:
        _fact_fail(f"source={source}: {collection} {field_name}")
    return item


def _optional_nonnegative_int(
    value: dict[str, object], field_name: str, source: Path, collection: str
) -> int | None:
    """Read an optional non-negative integer from an extended fact."""
    if field_name not in value:
        return None
    item = value[field_name]
    if isinstance(item, bool) or not isinstance(item, int) or item < 0:
        _fact_fail(f"source={source}: {collection} {field_name}")
    return item


def _optional_bool(
    value: dict[str, object], field_name: str, source: Path, collection: str
) -> bool:
    """Read an optional boolean marker without accepting integer coercion."""
    if field_name not in value:
        return False
    item = value[field_name]
    if not isinstance(item, bool):
        _fact_fail(f"source={source}: {collection} {field_name}")
    return item


def _string_list_optional(
    value: dict[str, object], field_name: str, source: Path, collection: str
) -> tuple[str, ...]:
    """Read an optional list of non-empty strings."""
    if field_name not in value:
        return ()
    item = value[field_name]
    if not isinstance(item, list) or not all(isinstance(entry, str) and entry for entry in item):
        _fact_fail(f"source={source}: {collection} {field_name}")
    return tuple(cast("list[str]", item))


def _debt(value: object, source: Path) -> policy.WorktreeDebtFact:
    """Normalize one first-class worktree debt fact."""
    if not isinstance(value, dict) or not set(value).issubset(DEBT_FIELDS | DEBT_OPTIONAL_FIELDS):
        _fact_fail(f"source={source}: worktree_debt entry")
    if not DEBT_FIELDS.issubset(value):
        _fact_fail(f"source={source}: worktree_debt entry")
    issue = value.get("issue")
    path = value.get("path")
    if isinstance(issue, bool) or not isinstance(issue, int) or issue < 1:
        _fact_fail(f"source={source}: worktree_debt issue")
    if not isinstance(path, str) or not path:
        _fact_fail(f"source={source}: worktree_debt path")
    work_item_key = value.get("work_item_key")
    if work_item_key is not None and (not isinstance(work_item_key, str) or not work_item_key):
        _fact_fail(f"source={source}: worktree_debt work_item_key")
    return policy.WorktreeDebtFact(issue, path, cast("str | None", work_item_key))


def _bar(value: object, source: Path) -> policy.ExternalBarFact:
    """Normalize one typed external launch bar."""
    if not isinstance(value, dict) or not set(value).issubset(BAR_FIELDS | BAR_OPTIONAL_FIELDS):
        _fact_fail(f"source={source}: external_bars entry")
    if not BAR_FIELDS.issubset(value):
        _fact_fail(f"source={source}: external_bars entry")
    key = value.get("key")
    kind = value.get("kind")
    detail = value.get("detail", "")
    if not isinstance(key, str) or not key or not isinstance(kind, str) or not kind:
        _fact_fail(f"source={source}: external_bars value")
    if not isinstance(detail, str):
        _fact_fail(f"source={source}: external_bars detail")
    return policy.ExternalBarFact(key, kind, detail)


def _priority(value: object, source: Path) -> str:
    """Normalize one configured priority key."""
    if not isinstance(value, str) or not value:
        _fact_fail(f"source={source}: priority_order value")
    return value


def _ready_transition(value: object, source: Path) -> policy.ReadyTransitionFact:
    """Normalize one recorded ready transition."""
    if not isinstance(value, dict) or set(value) != READY_TRANSITION_FIELDS:
        _fact_fail(f"source={source}: ready_transitions entry")
    key = value.get("key")
    recorded_at = value.get("recorded_at")
    if not isinstance(key, str) or not key or not isinstance(recorded_at, str) or not recorded_at:
        _fact_fail(f"source={source}: ready_transitions value")
    return policy.ReadyTransitionFact(key, recorded_at)


def _optional_limit(document: dict[str, object], source: Path) -> int | None:
    """Read the optional configured WIP limit."""
    if "wip_limit" not in document:
        return None
    value = document["wip_limit"]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fact_fail(f"source={source}: wip_limit")
    return value


def _outcome(value: object, source: Path) -> policy.DesiredOutcomeFact:
    """Normalize one versioned Desired Outcome with optional exact content."""
    if not isinstance(value, dict):
        _fact_fail(f"source={source}: desired_outcomes entry")
    actual = set(value)
    if not OUTCOME_FIELDS.issubset(actual) or not actual.issubset(
        OUTCOME_FIELDS | OUTCOME_OPTIONAL_FIELDS
    ):
        _fact_fail(f"source={source}: desired_outcomes fields")
    key = value.get("key")
    revision = value.get("revision")
    digest = value.get("content_digest")
    if (
        not isinstance(key, str)
        or not key
        or isinstance(revision, bool)
        or not isinstance(revision, int)
        or revision < 1
    ):
        _fact_fail(f"source={source}: desired_outcomes identity")
    if not isinstance(digest, str) or not digest:
        _fact_fail(f"source={source}: desired_outcomes digest")
    content = value.get("content")
    if content is not None and (not isinstance(content, str) or not content):
        _fact_fail(f"source={source}: desired_outcomes content")
    parent_issue = value.get("parent_issue")
    if parent_issue is not None and (
        isinstance(parent_issue, bool) or not isinstance(parent_issue, int) or parent_issue < 1
    ):
        _fact_fail(f"source={source}: desired_outcomes parent_issue")
    return policy.DesiredOutcomeFact(key, revision, digest, content, parent_issue)


@dataclass
class RecordingActionPort:
    """Fake mutation port whose writes are observable and never external."""

    applied: list[policy.ControlAction] = field(default_factory=list)

    def apply(self, action: policy.ControlAction) -> None:
        """Record an applied action."""
        self.applied.append(action)


@dataclass
class FakeDetachedWorkRunPort:
    """Detached Work Run fake proving scheduling-lock scope stays narrow."""

    scheduling_lock: SchedulingLock
    started: list[str] = field(default_factory=list)

    def start(self, run_key: str) -> None:
        """Record a detached run without consulting a scheduler lock."""
        self.started.append(run_key)
