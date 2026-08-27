"""Capability ports and deterministic fakes for the System-of-Work Controller."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, NoReturn, Protocol, cast

if TYPE_CHECKING:
    from controller_store import SchedulingLock

sys.path.insert(0, str(Path(__file__).parent))

import controller_policy as policy

CONTROL_FACTS_SCHEMA: Final = "control-facts/v1"
CONTROL_FACTS_FIELDS: Final = frozenset(
    {"schema", "configured_curator", "desired_outcomes", "initiatives", "work_items", "work_runs"}
)
FACT_FIELDS: Final = frozenset({"key", "state"})
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

    def apply(self, action: policy.ControlAction) -> None:
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
class FileFactCollector:
    """Normalize one strict local Control Fact snapshot for a controller cycle."""

    path: Path

    def collect(self) -> policy.ControlFacts:
        """Read one versioned fact envelope and fail closed on every malformed shape."""
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            _fact_fail(f"source={self.path}: {error}")
        if not isinstance(raw, dict) or set(raw) != CONTROL_FACTS_FIELDS:
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
        )


def _list(document: dict[str, object], name: str, source: Path) -> list[object]:
    """Read one required list from a fact envelope."""
    value = document.get(name)
    if not isinstance(value, list):
        _fact_fail(f"source={source}: {name}")
    return value


def _fact(
    value: object, name: str, source: Path
) -> policy.InitiativeFact | policy.WorkItemFact | policy.WorkRunFact:
    """Normalize one lifecycle fact with its collection name retained in errors."""
    if not isinstance(value, dict) or set(value) != FACT_FIELDS:
        _fact_fail(f"source={source}: {name} entry")
    key = value.get("key")
    state = value.get("state")
    if not isinstance(key, str) or not key or not isinstance(state, str) or not state:
        _fact_fail(f"source={source}: {name} value")
    if name == "initiatives":
        return policy.InitiativeFact(key, state)
    if name == "work_items":
        return policy.WorkItemFact(key, state)
    return policy.WorkRunFact(key, state)


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
