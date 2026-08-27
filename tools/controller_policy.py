"""Pure System-of-Work reconciliation policy.

This module is deliberately a facts-to-actions kernel.  It owns no capability
that can observe or mutate the host; adapters and the command coordinator keep
those concerns outside the policy seam.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Final

NO_ADMISSIBLE_INITIATIVE: Final = "no_admissible_initiative"


@dataclass(frozen=True, slots=True)
class DesiredOutcomeFact:
    """One normalized Product Curator input."""

    key: str
    revision: int
    content_digest: str
    content: str | None = None
    parent_issue: int | None = None


@dataclass(frozen=True, slots=True)
class InitiativeFact:
    """The visible lifecycle fact for one Initiative."""

    key: str
    state: str


@dataclass(frozen=True, slots=True)
class WorkItemFact:
    """The visible lifecycle fact for one Work Item."""

    key: str
    state: str


@dataclass(frozen=True, slots=True)
class WorkRunFact:
    """The visible lifecycle fact for one detached Work Run."""

    key: str
    state: str


@dataclass(frozen=True, slots=True)
class ControlFacts:
    """Normalized facts supplied to one reconciliation cycle."""

    configured_curator: str | None
    desired_outcomes: tuple[DesiredOutcomeFact, ...]
    initiatives: tuple[InitiativeFact, ...]
    work_items: tuple[WorkItemFact, ...]
    work_runs: tuple[WorkRunFact, ...]


@dataclass(frozen=True, slots=True)
class LifecycleState:
    """Derived lifecycle state; never a second mutable source of truth."""

    state: str
    admitted_initiative: str | None
    reason: str


@dataclass(frozen=True, slots=True)
class ControlAction:
    """One ordered, idempotent request to an external port."""

    kind: str
    logical_key: str
    payload: tuple[tuple[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class Reconciliation:
    """The complete pure result of reducing one fact set."""

    lifecycle: LifecycleState
    actions: tuple[ControlAction, ...]


def derive(
    facts: ControlFacts,
    previously_confirmed: LifecycleState | None = None,
) -> Reconciliation:
    """Derive the first slice's conservative no-admission result.

    The previous state is accepted so replay callers can pass the confirmed
    journal state explicitly.  It is intentionally not trusted as authority:
    the lifecycle is derived from the newly collected facts every time.
    """
    del previously_confirmed
    if facts.configured_curator is None:
        reason = "no_product_curator_configured"
    elif not facts.desired_outcomes:
        reason = "no_desired_outcome"
    elif len(facts.desired_outcomes) != 1:
        reason = "desired_outcome_cardinality_not_one"
    elif facts.initiatives:
        reason = "active_initiative_present"
    else:
        reason = "initiative_admission_not_implemented"
    return Reconciliation(
        lifecycle=LifecycleState(NO_ADMISSIBLE_INITIATIVE, None, reason),
        actions=(),
    )


def facts_document(facts: ControlFacts) -> dict[str, object]:
    """Render normalized facts without introducing an I/O dependency."""
    desired_outcomes = []
    for outcome in facts.desired_outcomes:
        document: dict[str, object] = {
            "key": outcome.key,
            "revision": outcome.revision,
            "content_digest": outcome.content_digest,
        }
        if outcome.content is not None:
            document["content"] = outcome.content
        if outcome.parent_issue is not None:
            document["parent_issue"] = outcome.parent_issue
        desired_outcomes.append(document)
    return {
        "configured_curator": facts.configured_curator,
        "desired_outcomes": desired_outcomes,
        "initiatives": [asdict(item) for item in facts.initiatives],
        "work_items": [asdict(item) for item in facts.work_items],
        "work_runs": [asdict(item) for item in facts.work_runs],
    }


def lifecycle_document(lifecycle: LifecycleState) -> dict[str, object]:
    """Render derived lifecycle state as a stable value document."""
    return asdict(lifecycle)


def actions_document(actions: tuple[ControlAction, ...]) -> list[dict[str, object]]:
    """Render the ordered action plan, preserving its sequence."""
    return [
        {
            "order": index,
            "kind": action.kind,
            "logical_key": action.logical_key,
            "payload": dict(action.payload),
        }
        for index, action in enumerate(actions, start=1)
    ]
