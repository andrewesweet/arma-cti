"""Capability ports and deterministic fakes for the System-of-Work Controller."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, NoReturn, Protocol, cast

if TYPE_CHECKING:
    from controller_store import SchedulingLock

sys.path.insert(0, str(Path(__file__).parent))

import controller_policy as policy
import queue_policy

CONTROL_FACTS_SCHEMA: Final = "control-facts/v1"
CONTROL_FACTS_FIELDS: Final = frozenset(
    {"schema", "configured_curator", "desired_outcomes", "initiatives", "work_items", "work_runs"}
)
CONTROL_FACTS_OPTIONAL_FIELDS: Final = frozenset(
    {"worktree_debt", "wip_limit", "external_bars", "priority_order", "ready_transitions"}
)
FACT_FIELDS: Final = frozenset({"key", "state"})
WORK_ITEM_OPTIONAL_FIELDS: Final = frozenset(
    {"issue", "blocked_by", "priority", "exclusive_resources", "seat", "profile", "ready_at"}
)
WORK_RUN_OPTIONAL_FIELDS: Final = frozenset(
    {"work_item_key", "dispatch_id", "failure_class", "worktree", "issue"}
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

    def collect(self) -> policy.ControlFacts:
        """Collect graph facts, then add live runs and owed worktree debt."""
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
        runs = list(facts.work_runs)
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
            if any(
                (run.item_key == item_key or run.issue == holder.issue)
                and (
                    run.state in policy.LIVE_WORK_RUN_STATES
                    or run.failure_class in policy.NON_RESULT_CLASSES
                )
                for run in runs
            ):
                continue
            dispatch_id = next(
                (
                    source.removeprefix("dispatch:")
                    for source in holder.sources
                    if source.startswith("dispatch:")
                ),
                None,
            )
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
    return policy.WorkRunFact(
        key,
        state,
        _optional_nonempty_text(value, "work_item_key", source, name),
        _optional_nonempty_text(value, "dispatch_id", source, name),
        _optional_nonempty_text(value, "failure_class", source, name),
        _optional_nonempty_text(value, "worktree", source, name),
        _optional_positive_int(value, "issue", source, name),
    )


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
