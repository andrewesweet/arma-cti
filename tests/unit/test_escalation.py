"""Transferring-escalation conditions as data, emitted when one fires (ADR-0071 ruling 5, #325).

Two layers. The data first — the four seeded conditions read off the live table, their shape
asserted so a partial or drifted table can never govern silently, the way `routing_policy`'s
parse is asserted. Then each condition's predicate, exercised for the case that fires it and the
near-misses that must not: the wall with a fact missing, the consecutive pair with one item shy
of the wall, the retry on the same profile. `None` is the third value under test throughout: a
fact not recorded is distinct from a fact recorded false, and a condition that lacks a fact it
needs emits nothing rather than guessing.
"""

from __future__ import annotations

import json
import shutil
from typing import TYPE_CHECKING

import pytest
from conftest import REPO, load_tool

if TYPE_CHECKING:
    from pathlib import Path

escalation = load_tool("escalation")

TABLE = REPO / escalation.CONDITIONS_RELATIVE


def live() -> escalation.Conditions:
    # Read in the caller's body, not at module import, so a mutant in escalation.py
    # fails a test that notices it instead of breaking the module's collection —
    # which tools/mutation_smoke.py reads as a non-verdict rather than a kill.
    # Asserted parseable here so a broken shipped table is still caught at test time.
    result = escalation.read_conditions(TABLE)
    assert result.conditions is not None, result.error
    return result.conditions


def item(
    routing_class: int | None = None,
    *,
    review_rounds: int | None = None,
    finding_above_low: bool | None = None,
    attempts: tuple[escalation.Attempt, ...] = (),
) -> escalation.ItemState:
    return escalation.ItemState(
        routing_class=routing_class,
        review_rounds=review_rounds,
        finding_above_low=finding_above_low,
        attempts=attempts,
    )


def fired(conditions: escalation.Conditions | None, context: escalation.Context) -> set[int]:
    return {emission.condition.id for emission in escalation.evaluate(conditions, context)}


# --------------------------------------------------------------------------- the data table


def test_the_live_table_seeds_exactly_the_four_conditions() -> None:
    conditions = live()
    assert [condition.id for condition in conditions.conditions] == [1, 2, 3, 4]
    names = {condition.name for condition in conditions.conditions}
    assert names == {
        "review_stuck_after_three_rounds",
        "two_consecutive_same_class_stuck",
        "retry_on_new_profile_stuck",
        "plausible_wrong_fix_goes_green",
    }


def test_every_seeded_condition_is_decided_and_carries_a_remedy() -> None:
    for condition in live().conditions:
        assert condition.predicate in escalation.PREDICATES, condition.name
        assert condition.remedy, condition.name


def test_the_live_table_is_read_again_for_each_call(tmp_path: Path) -> None:
    """Two reads in one process see a table edit between them (no module cache)."""
    path = tmp_path / escalation.CONDITIONS_RELATIVE
    path.parent.mkdir(parents=True)
    shutil.copyfile(TABLE, path)

    first = escalation.read_conditions(path).conditions
    assert first is not None
    assert len(first.conditions) == 4

    document = json.loads(path.read_text(encoding="utf-8"))
    document["conditions"][0]["name"] = "renamed_first_condition"
    path.write_text(json.dumps(document), encoding="utf-8")

    second = escalation.read_conditions(path).conditions
    assert second is not None
    assert second.conditions[0].name == "renamed_first_condition"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ('{"version": 2, "conditions": []}', escalation.VERSION_ERROR),
        ('{"version": 1}', escalation.CONDITIONS_LIST_ERROR),
        ('{"version": 1, "conditions": [{}]}', escalation.CONDITION_FIELDS_ERROR),
        ('{"version": 1, "conditions": ["not-an-object"]}', escalation.CONDITION_OBJECT_ERROR),
        (
            (
                '{"version": 1, "conditions": ['
                '{"id": 1, "name": "x", "predicate": "not_a_real_predicate", "remedy": "r"}'
                "]}"
            ),
            escalation.PREDICATE_ERROR,
        ),
        (
            (
                '{"version": 1, "conditions": ['
                '{"id": 1, "name": "x", "predicate": "routing_class_four", "remedy": ""}'
                "]}"
            ),
            escalation.REMEDY_ERROR,
        ),
        (
            (
                '{"version": 1, "conditions": ['
                '{"id": 1, "name": "x", "predicate": "routing_class_four", "remedy": "r"},'
                '{"id": 1, "name": "y", "predicate": "three_round_wall", "remedy": "r"}'
                "]}"
            ),
            escalation.IDS_UNIQUE_ERROR,
        ),
    ],
)
def test_a_partial_table_is_rejected_not_silently_skipped(text: str, message: str) -> None:
    with pytest.raises(escalation.EscalationError, match=message):
        escalation.parse_conditions(text)


def test_an_unreadable_table_emits_nothing() -> None:
    """Escalation is advisory: the safe fall-through for a missing table is silence, not a crash."""
    context = escalation.Context(item=item(routing_class=4))
    assert escalation.evaluate(None, context) == ()
    assert escalation.read_conditions(REPO / "does-not-exist.json").conditions is None


# ------------------------------------------------------------------ condition 4: the #181 shape


def test_condition_four_fires_for_an_item_declaring_class_four() -> None:
    assert fired(live(), escalation.Context(item=item(routing_class=4))) == {4}


@pytest.mark.parametrize("routing_class", [None, 1, 3, 5])
def test_condition_four_does_not_fire_for_any_other_class(routing_class: int | None) -> None:
    assert 4 not in fired(live(), escalation.Context(item=item(routing_class=routing_class)))


# ---------------------------------------- condition 1: three rounds and a finding above Low


def test_condition_one_fires_after_three_rounds_with_a_finding_above_low() -> None:
    context = escalation.Context(
        item=item(routing_class=6, review_rounds=3, finding_above_low=True),
        arbiter="codex-sol-high",
    )
    assert 1 in fired(live(), context)
    (one,) = [e for e in escalation.evaluate(live(), context) if e.condition.id == 1]
    assert "review_rounds=3" in one.evidence
    assert "finding_above_low=true" in one.evidence
    assert "arbiter=codex-sol-high" in one.evidence


@pytest.mark.parametrize(
    "row",
    [
        (2, True, "not enough rounds"),
        (3, False, "no finding above Low"),
        (3, None, "finding not recorded"),
        (None, True, "rounds not recorded"),
        (None, None, "neither recorded — the brief's live state today"),
    ],
)
def test_condition_one_does_not_fire_short_of_the_wall_or_on_missing_facts(
    row: tuple[int | None, bool | None, str],
) -> None:
    review_rounds, finding_above_low, why = row
    context = escalation.Context(
        item=item(
            routing_class=6, review_rounds=review_rounds, finding_above_low=finding_above_low
        ),
        arbiter="codex-sol-high",
    )
    assert 1 not in fired(live(), context), why


def test_condition_one_names_no_arbiter_when_the_caller_did_not_resolve_one() -> None:
    context = escalation.Context(item=item(review_rounds=3, finding_above_low=True))
    (one,) = [e for e in escalation.evaluate(live(), context) if e.condition.id == 1]
    assert not any(fact.startswith("arbiter=") for fact in one.evidence)


def test_condition_one_would_have_fired_on_the_323_record_naming_its_arbiter() -> None:
    """#323 reached review round 3 with a Medium still open and escalated to codex-sol-high.

    The seed condition has to fire on that record at that moment and name the arbiter the
    transfer reached — the head of the implementer seat's escalation entry. If it would not, one
    of the two is wrong.
    """
    context = escalation.Context(
        item=item(review_rounds=3, finding_above_low=True),
        arbiter="codex-sol-high",
    )
    (one,) = [e for e in escalation.evaluate(live(), context) if e.condition.id == 1]
    assert "arbiter=codex-sol-high" in one.evidence


# ----------------------------------- condition 3: a retry on a new profile at the wall


def test_condition_three_fires_when_a_retry_on_a_new_profile_reaches_the_wall() -> None:
    context = escalation.Context(
        item=item(
            routing_class=6,
            review_rounds=3,
            finding_above_low=True,
            attempts=(
                escalation.Attempt(profile="opus-low", clean_base=False),
                escalation.Attempt(profile="codex-luna-max", clean_base=True),
            ),
        )
    )
    assert 3 in fired(live(), context)
    (three,) = [e for e in escalation.evaluate(live(), context) if e.condition.id == 3]
    assert "prior_profile=opus-low" in three.evidence
    assert "retry_profile=codex-luna-max" in three.evidence
    assert "retry_clean_base=true" in three.evidence


@pytest.mark.parametrize(
    ("attempts", "why"),
    [
        ((), "no attempts recorded"),
        ((escalation.Attempt(profile="opus-low", clean_base=False),), "only one attempt"),
        (
            (
                escalation.Attempt(profile="opus-low", clean_base=False),
                escalation.Attempt(profile="opus-low", clean_base=True),
            ),
            "same profile",
        ),
        (
            (
                escalation.Attempt(profile="opus-low", clean_base=False),
                escalation.Attempt(profile="codex-luna-max", clean_base=False),
            ),
            "retry not from a clean base",
        ),
    ],
)
def test_condition_three_does_not_fire_for_a_non_retry(
    attempts: tuple[escalation.Attempt, ...], why: str
) -> None:
    context = escalation.Context(
        item=item(routing_class=6, review_rounds=3, finding_above_low=True, attempts=attempts)
    )
    assert 3 not in fired(live(), context), why


def test_condition_three_does_not_fire_when_the_retry_has_not_reached_the_wall() -> None:
    context = escalation.Context(
        item=item(
            routing_class=6,
            review_rounds=2,  # the retry is stuck but not yet at three rounds
            finding_above_low=True,
            attempts=(
                escalation.Attempt(profile="opus-low", clean_base=False),
                escalation.Attempt(profile="codex-luna-max", clean_base=True),
            ),
        )
    )
    assert 3 not in fired(live(), context)


# -------------------------------------- condition 2: two consecutive items of one class at the wall


def _wall(routing_class: int | None, review_rounds: int = 3) -> escalation.ItemState:
    return item(routing_class=routing_class, review_rounds=review_rounds, finding_above_low=True)


def test_condition_two_fires_for_two_consecutive_items_of_one_class_at_the_wall() -> None:
    context = escalation.Context(
        item=item(routing_class=5),
        prior=(_wall(5, review_rounds=3), _wall(5, review_rounds=4)),
    )
    assert 2 in fired(live(), context)
    (two,) = [e for e in escalation.evaluate(live(), context) if e.condition.id == 2]
    assert "routing_class=5" in two.evidence
    assert "consecutive_items=2" in two.evidence


@pytest.mark.parametrize(
    ("prior", "why"),
    [
        ((), "no history"),
        ((_wall(5),), "only one prior item"),
        ((_wall(5), _wall(6)), "the two prior items do not share a class"),
        ((_wall(None), _wall(None)), "the prior items declare no class"),
        ((_wall(5, review_rounds=2), _wall(5)), "the older prior item is shy of the wall"),
        ((_wall(5), _wall(5, review_rounds=2)), "the newer prior item is shy of the wall"),
        (
            (
                _wall(6),
                _wall(5),
                _wall(6),
            ),  # the most recent two differ; the shared pair is not consecutive
            "the consecutive pair do not share a class",
        ),
    ],
)
def test_condition_two_does_not_fire_short_of_two_consecutive_at_the_wall(
    prior: tuple[escalation.ItemState, ...], why: str
) -> None:
    context = escalation.Context(item=item(routing_class=5), prior=prior)
    assert 2 not in fired(live(), context), why


# ----------------------------------------------------------------- co-firing and the silent default


def test_independent_conditions_co_fire_in_id_order() -> None:
    """A class-4 item also at the wall fires both 1 and 4; each is decided, neither suppresses."""
    context = escalation.Context(
        item=item(routing_class=4, review_rounds=3, finding_above_low=True),
        arbiter="codex-sol-high",
    )
    ids = [emission.condition.id for emission in escalation.evaluate(live(), context)]
    assert ids == sorted(ids)
    assert set(ids) == {1, 4}


def test_an_item_with_no_recorded_facts_emits_nothing() -> None:
    """The brief's live state today: only routing_class is recorded, and it is absent here."""
    assert escalation.evaluate(live(), escalation.Context(item=item())) == ()


def test_render_names_the_condition_its_facts_and_its_remedy() -> None:
    context = escalation.Context(item=item(routing_class=4))
    (rendered,) = escalation.evaluate(live(), context)
    lines = escalation.render((rendered,))
    assert lines[0] == "escalation=4:plausible_wrong_fix_goes_green"
    assert "  routing_class=4" in lines
    assert any("#181 shape" in line for line in lines)
