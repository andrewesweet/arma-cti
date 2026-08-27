"""Pure policy cases for the first System-of-Work Controller slice."""

from __future__ import annotations

import pytest
from conftest import load_tool

policy = load_tool("controller_policy")


def facts(
    *,
    curator: str | None = None,
    outcomes: tuple[object, ...] = (),
    initiatives: tuple[object, ...] = (),
) -> policy.ControlFacts:
    """Build a fact set while keeping the branch cases easy to read."""
    return policy.ControlFacts(
        configured_curator=curator,
        desired_outcomes=outcomes,
        initiatives=initiatives,
        work_items=(),
        work_runs=(),
    )


OUTCOME = policy.DesiredOutcomeFact("outcome-1", 1, "digest-1")
ACTIVE = policy.InitiativeFact("initiative-1", "active")


@pytest.mark.parametrize(
    ("arrangement", "expected_reason"),
    [
        (facts(), "no_product_curator_configured"),
        (facts(curator="curator-1"), "no_desired_outcome"),
        (
            facts(curator="curator-1", outcomes=(OUTCOME, OUTCOME)),
            "desired_outcome_cardinality_not_one",
        ),
        (
            facts(curator="curator-1", outcomes=(OUTCOME,), initiatives=(ACTIVE,)),
            "active_initiative_present",
        ),
        (facts(curator="curator-1", outcomes=(OUTCOME,)), "initiative_admission_not_implemented"),
    ],
)
def test_first_slice_always_explains_why_no_initiative_is_admissible(
    arrangement: object, expected_reason: str
) -> None:
    """Every conservative no-admission branch is explicit and action-free."""
    result = policy.derive(arrangement)

    assert result.lifecycle == policy.LifecycleState(
        policy.NO_ADMISSIBLE_INITIATIVE, None, expected_reason
    )
    assert result.actions == ()


def test_previous_confirmed_state_is_not_an_authority_for_replay() -> None:
    """The same current facts derive the same result regardless of prior state."""
    current = facts(curator="curator-1", outcomes=(OUTCOME,))
    previous = policy.LifecycleState("unexpected", "initiative-9", "old")

    assert policy.derive(current) == policy.derive(current, previous)


def test_renderers_preserve_normalized_facts_and_action_order() -> None:
    """Stable documents expose all fields, including an ordered action payload."""
    current = facts(curator="curator-1", outcomes=(OUTCOME,))
    actions = (
        policy.ControlAction("tracker.record", "outcome-1", (("revision", 1),)),
        policy.ControlAction("evidence.write", "cycle-1"),
    )

    assert policy.facts_document(current) == {
        "configured_curator": "curator-1",
        "desired_outcomes": [{"key": "outcome-1", "revision": 1, "content_digest": "digest-1"}],
        "initiatives": [],
        "work_items": [],
        "work_runs": [],
    }
    lifecycle = policy.LifecycleState(policy.NO_ADMISSIBLE_INITIATIVE, None, "reason")
    assert policy.lifecycle_document(lifecycle) == {
        "state": policy.NO_ADMISSIBLE_INITIATIVE,
        "admitted_initiative": None,
        "reason": "reason",
    }
    assert policy.actions_document(actions) == [
        {
            "order": 1,
            "kind": "tracker.record",
            "logical_key": "outcome-1",
            "payload": {"revision": 1},
        },
        {"order": 2, "kind": "evidence.write", "logical_key": "cycle-1", "payload": {}},
    ]


def test_fact_renderer_returns_a_new_document() -> None:
    """Rendering cannot mutate the immutable fact input through its result."""
    current = facts(curator="curator-1", outcomes=(OUTCOME,))

    rendered = policy.facts_document(current)
    rendered["desired_outcomes"].clear()  # type: ignore[union-attr]

    assert current.desired_outcomes == (OUTCOME,)
