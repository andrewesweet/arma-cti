"""Capability ports and deterministic fakes for the System-of-Work Controller."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from controller_store import SchedulingLock

sys.path.insert(0, str(Path(__file__).parent))

import controller_policy as policy


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
        """Report the empty current graph rather than inventing an Initiative."""
        return policy.ControlFacts(
            configured_curator=None,
            desired_outcomes=(),
            initiatives=(),
            work_items=(),
            work_runs=(),
        )


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
