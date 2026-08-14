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
dispatch = load_tool("dispatch")

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
    attempts: tuple[escalation.Attempt, ...] | None = None,
) -> escalation.ItemState:
    return escalation.ItemState(
        routing_class=routing_class,
        review_rounds=review_rounds,
        finding_above_low=finding_above_low,
        attempts=attempts,
    )


def _eval(
    conditions: escalation.Conditions | None, context: escalation.Context
) -> escalation.Evaluation:
    # `evaluate` takes the read result (parsed table or the reason it failed), so a caller wraps
    # the conditions it built directly — and passes None for the unreadable case, which is the
    # third state under test rather than the empty emissions of nothing fired.
    return escalation.evaluate(escalation.ReadResult(conditions), context)


def fired(conditions: escalation.Conditions | None, context: escalation.Context) -> set[int]:
    # `_eval` is only ever called here with a readable table (conditions built directly, never
    # None), so the outcome is NoFiring or Firing — never Unreadable — and narrowing to Firing is
    # the test reading the outcome the way a consumer now must: through the type, not `emissions`.
    outcome = _eval(conditions, context)
    if isinstance(outcome, escalation.NoFiring):
        return set()
    assert isinstance(outcome, escalation.Firing), outcome
    return {emission.condition.id for emission in outcome.emissions}


def _emissions(
    conditions: escalation.Conditions | None, context: escalation.Context
) -> tuple[escalation.Emission, ...]:
    """Return the emissions of a firing outcome — narrowed the way a consumer must, by type."""
    outcome = _eval(conditions, context)
    assert isinstance(outcome, escalation.Firing), outcome
    return outcome.emissions


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


def test_an_unreadable_table_is_a_third_state_not_silence() -> None:
    """An unreadable table is not "nothing fired": it reaches the caller as unreadable (#325).

    Escalation is advisory, which is the reason a failed read must be reported rather than hidden:
    a lost emission costs nothing to surface and everything to silence, and a class-4 issue that
    must escalate would otherwise disappear. Empty emissions are reserved for a condition that has
    not fired, so the empty section a brief carries for that case alone is not reached here.
    """
    context = escalation.Context(item=item(routing_class=4))
    missing = escalation.read_conditions(REPO / "does-not-exist.json")
    assert missing.conditions is None
    evaluation = escalation.evaluate(missing, context)
    # The third state is a type a consumer must narrow to: `emissions` does not exist on it, so a
    # caller cannot inspect `emissions == ()` and silently recover the confident "nothing fired"
    # the two-tuple outcome let it (#325 round 2, claim 2; #347's source-unavailable code).
    assert isinstance(evaluation, escalation.Unreadable)
    assert evaluation.reasons == (missing.error,)
    # `emissions` exists only on Firing, so a consumer cannot read it on the third state at all —
    # the hole two parallel tuples left (#325 round 2, claim 2; #347).
    assert not hasattr(evaluation, "emissions")


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
    (one,) = [e for e in _emissions(live(), context) if e.condition.id == 1]
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


def test_condition_one_does_not_fire_when_the_caller_did_not_resolve_an_arbiter() -> None:
    """The arbiter is the transfer target condition 1 names; without one it must not fire.

    Its remedy orders a transfer to "the arbiter named in the emission", so an emission that
    names none is unactionable. The arbiter is a fact this condition needs, and a condition that
    lacks a fact it needs emits nothing — the same rule as a missing wall fact.
    """
    context = escalation.Context(item=item(review_rounds=3, finding_above_low=True))
    assert 1 not in fired(live(), context)
    assert isinstance(_eval(live(), context), escalation.NoFiring)


def test_condition_one_fires_for_the_323_facts_and_names_the_seat_tables_arbiter() -> None:
    """Condition 1 fires for the facts #323 exhibited and names the arbiter the seat table holds.

    #323 reached review round 3 with a Medium still open and escalated to `codex-sol-high`, the
    head of the implementer seat's escalation entry. The dispatch record does not yet carry
    review rounds or findings (they are sequenced: ADR-0071 rulings 4 and 6, #333), so this is
    not a replay off that record — it asserts the condition fires on the stated facts and names
    the arbiter the seat table resolves, which is the contract a real replay will exercise
    unchanged once the loop records the data.
    """
    arbiter = dispatch.IMPLEMENTER_ESCALATION[0]
    context = escalation.Context(
        item=item(review_rounds=3, finding_above_low=True),
        arbiter=arbiter,
    )
    (one,) = [e for e in _emissions(live(), context) if e.condition.id == 1]
    assert f"arbiter={arbiter}" in one.evidence


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
    (three,) = [e for e in _emissions(live(), context) if e.condition.id == 3]
    assert "prior_profile=opus-low" in three.evidence
    assert "retry_profile=codex-luna-max" in three.evidence
    assert "retry_clean_base=true" in three.evidence


@pytest.mark.parametrize(
    ("attempts", "why"),
    [
        (None, "attempts not recorded"),
        ((), "recorded zero attempts"),
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


def test_condition_three_does_not_fire_on_a_third_attempt() -> None:
    """Ruling 5 names the second attempt; a third is what the remedy says not to dispatch."""
    context = escalation.Context(
        item=item(
            routing_class=6,
            review_rounds=3,
            finding_above_low=True,
            attempts=(
                escalation.Attempt(profile="opus-low", clean_base=False),
                escalation.Attempt(profile="codex-luna-max", clean_base=True),
                escalation.Attempt(profile="zai-glm52-max", clean_base=True),
            ),
        )
    )
    assert 3 not in fired(live(), context)


def test_condition_three_does_not_fire_when_the_clean_base_fact_is_not_recorded() -> None:
    """A not-recorded clean base is distinct from a recorded False, and neither fires (#323)."""
    context = escalation.Context(
        item=item(
            routing_class=6,
            review_rounds=3,
            finding_above_low=True,
            attempts=(
                escalation.Attempt(profile="opus-low", clean_base=False),
                escalation.Attempt(profile="codex-luna-max", clean_base=None),
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
    (two,) = [e for e in _emissions(live(), context) if e.condition.id == 2]
    assert "routing_class=5" in two.evidence
    assert "consecutive_items=2" in two.evidence


@pytest.mark.parametrize(
    ("prior", "why"),
    [
        (None, "prior not recorded — distinct from a recorded-empty history (#325 claim 3)"),
        ((), "no history recorded"),
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
    prior: tuple[escalation.ItemState, ...] | None, why: str
) -> None:
    context = escalation.Context(item=item(routing_class=5), prior=prior)
    assert 2 not in fired(live(), context), why


def test_condition_two_requires_the_current_item_to_share_the_stuck_class() -> None:
    """Ruling 5 re-plans "the next one" of the under-specified class, not an unrelated one."""
    context = escalation.Context(
        item=item(routing_class=6),  # a different class from the stuck pair
        prior=(_wall(5), _wall(5)),
    )
    assert 2 not in fired(live(), context)


def test_condition_two_does_not_fire_when_the_current_item_declares_no_class() -> None:
    context = escalation.Context(
        item=item(routing_class=None),
        prior=(_wall(5), _wall(5)),
    )
    assert 2 not in fired(live(), context)


# ----------------------------------------------------------------- co-firing and the silent default


def test_independent_conditions_co_fire_in_id_order() -> None:
    """A class-4 item also at the wall fires both 1 and 4; each is decided, neither suppresses."""
    context = escalation.Context(
        item=item(routing_class=4, review_rounds=3, finding_above_low=True),
        arbiter="codex-sol-high",
    )
    ids = [emission.condition.id for emission in _emissions(live(), context)]
    assert ids == sorted(ids)
    assert set(ids) == {1, 4}


def test_an_item_with_no_recorded_facts_emits_nothing() -> None:
    """The brief's live state today: only routing_class is recorded, and it is absent here."""
    evaluation = _eval(live(), escalation.Context(item=item()))
    assert isinstance(evaluation, escalation.NoFiring)  # nothing fired, every input readable


def test_render_names_the_condition_its_facts_and_its_remedy() -> None:
    context = escalation.Context(item=item(routing_class=4))
    (rendered,) = _emissions(live(), context)
    lines = escalation.render((rendered,))
    assert lines[0] == "escalation=4:plausible_wrong_fix_goes_green"
    assert "  routing_class=4" in lines
    assert any("#181 shape" in line for line in lines)
