"""The never-alone decision surface: exemption, rounds, adjudication, escalation (#331).

Three layers. The exemption table first — the shipped file read in the caller's body, its
shape asserted, its emptiness pinned as the state nothing has yet earned its way off. Then
the decision, both directions and the third state: unlisted means covered, listed means
exempt with its reason quotable, unreadable never exempts, and a diff touching the list
itself is never exempt whatever the list says. Then the loop: round stamping, the four
adjudication routes with the fourth's three restrictions, one-adjudication-per-finding, and
the escalation bridge that turns a live loop into the two recorded wall facts — which
lights condition one, while conditions two and three wait on a `prior` history and recorded
`attempts` that no loop carries.
"""

from __future__ import annotations

import json
import shutil
from typing import TYPE_CHECKING

import pytest
from conftest import REPO, load_tool

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

review_loop = load_tool("review_loop")
# The copy review_loop imported, not a second exec of the same file: two copies hold
# different class objects, and this module narrows escalation outcomes by `isinstance`
# below, where the decision kinds are pinned separately.
escalation = review_loop.escalation

TABLE = REPO / review_loop.EXEMPTIONS_RELATIVE
CONDITIONS = REPO / escalation.CONDITIONS_RELATIVE


def live() -> review_loop.Exemptions:
    # Read in the caller's body, not at module import, so a mutant in review_loop.py fails
    # a test that notices it instead of breaking collection — which tools/mutation_smoke.py
    # reads as a non-verdict rather than a kill. Asserted parseable here so a broken shipped
    # table is still caught at test time.
    result = review_loop.read_exemptions(TABLE)
    assert result.exemptions is not None, result.error
    return result.exemptions


def conditions() -> escalation.Conditions:
    result = escalation.read_conditions(CONDITIONS)
    assert result.conditions is not None, result.error
    return result.conditions


def exemptions_ok(entries: tuple[review_loop.Exemption, ...]) -> review_loop.ExemptionRead:
    return review_loop.ExemptionRead(review_loop.Exemptions("test", entries))


def doc_entry(surface: str, reason: str = "the reason beside it") -> review_loop.Exemption:
    return review_loop.Exemption(surface, reason)


def finding(
    identifier: str,
    severity: str = review_loop.MEDIUM,
    round_raised: int = 0,
    adjudication: review_loop.Adjudication | None = None,
) -> review_loop.Finding:
    return review_loop.Finding(identifier, severity, round_raised, adjudication)


def adjud(
    route: str,
    issue: str = "",
    conditional_on: str = "",
) -> review_loop.Adjudication:
    return review_loop.Adjudication(route, issue, conditional_on)


def refused(call: Callable[[], object]) -> str:
    with pytest.raises(review_loop.ReviewLoopError) as error:
        call()
    return str(error.value)


# --------------------------------------------------------------------------- the exemption table


def test_the_shipped_table_parses_and_names_no_entry() -> None:
    """The list ships empty: every landing is reviewed, because nothing has earned off it."""
    table = live()
    assert table.entries == ()
    assert table.source == "ADR-0071 ruling 4, 2026-08-11; module landed by #331"


def test_the_shipped_table_is_read_again_for_each_call(tmp_path: Path) -> None:
    """Two reads in one process see a table edit between them (no module cache)."""
    path = tmp_path / review_loop.EXEMPTIONS_RELATIVE
    path.parent.mkdir(parents=True)
    shutil.copyfile(TABLE, path)

    first = review_loop.read_exemptions(path).exemptions
    assert first is not None
    assert first.entries == ()

    document = json.loads(path.read_text(encoding="utf-8"))
    document["entries"] = [{"surface": "docs/", "reason": "r"}]
    path.write_text(json.dumps(document), encoding="utf-8")

    second = review_loop.read_exemptions(path).exemptions
    assert second is not None
    assert second.entries == (review_loop.Exemption("docs/", "r"),)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ('{"version": 2, "entries": []}', review_loop.VERSION_ERROR),
        ('{"version": 1}', review_loop.ENTRIES_LIST_ERROR),
        ('{"version": 1, "entries": [{}]}', review_loop.ENTRY_FIELDS_ERROR),
        ('{"version": 1, "entries": ["not-an-object"]}', review_loop.ENTRY_OBJECT_ERROR),
        (
            '{"version": 1, "entries": [{"surface": "", "reason": "r"}]}',
            review_loop.ENTRY_FIELDS_ERROR,
        ),
        (
            '{"version": 1, "entries": [{"surface": "docs/", "reason": ""}]}',
            review_loop.ENTRY_FIELDS_ERROR,
        ),
        (
            # Two entries for one surface is a second reason for the same exemption, and a
            # table that cannot tell is a table whose growth is invisible in the diff.
            (
                '{"version": 1, "entries": ['
                '{"surface": "docs/", "reason": "r1"},'
                '{"surface": "docs/", "reason": "r2"}]}'
            ),
            review_loop.ENTRY_UNIQUE_ERROR,
        ),
        (
            # The self-exemption refusal, refused at parse: a list that tried to except
            # itself never parses far enough to govern anything.
            (
                '{"version": 1, "entries": ['
                f'{{"surface": "{review_loop.EXEMPTIONS_RELATIVE.as_posix()}",'
                ' "reason": "the list itself"}]}'
            ),
            review_loop.SELF_EXEMPTION_ERROR,
        ),
    ],
)
def test_a_table_that_cannot_govern_silently_is_refused(text: str, message: str) -> None:
    assert refused(lambda: review_loop.parse_exemptions(text)) == message


# --------------------------------------------------------------------------- the decision


def test_an_unlisted_surface_requires_review() -> None:
    read = exemptions_ok(())
    decision = review_loop.exemption_decision(read, ("src/cti_daemon/daemon.py",))
    assert isinstance(decision, review_loop.ReviewRequired)
    assert decision.kind == review_loop.REVIEW_REQUIRED
    assert decision.evidence == ("unlisted=src/cti_daemon/daemon.py",)


def test_a_listed_surface_is_exempt_with_its_reason_quotable() -> None:
    read = exemptions_ok((doc_entry("docs/research/", "published research notes"),))
    decision = review_loop.exemption_decision(read, ("docs/research/arma-toolchain.md",))
    assert isinstance(decision, review_loop.Exempt)
    assert decision.kind == review_loop.EXEMPT
    assert decision.matched == (("docs/research/arma-toolchain.md", "published research notes"),)


def test_a_directory_prefix_covers_what_is_under_it_and_only_that() -> None:
    read = exemptions_ok((doc_entry("docs/adr/"), doc_entry("justfile")))
    covered = review_loop.exemption_decision(read, ("docs/adr/0049-review-loop.md",))
    assert isinstance(covered, review_loop.Exempt)
    # An exact-file entry covers the file, not its neighbours — the same `path_matches`
    # semantics the routing policy's landing prefixes run under.
    beside = review_loop.exemption_decision(read, ("justfile.lock",))
    assert isinstance(beside, review_loop.ReviewRequired)
    assert beside.evidence == ("unlisted=justfile.lock",)


def test_a_mixed_diff_requires_review_naming_only_the_unlisted_paths() -> None:
    read = exemptions_ok((doc_entry("docs/research/"),))
    decision = review_loop.exemption_decision(
        read, ("docs/research/x.md", "tools/review_loop.py", "docs/research/y.md")
    )
    assert isinstance(decision, review_loop.ReviewRequired)
    assert decision.evidence == ("unlisted=tools/review_loop.py",)


def test_a_diff_touching_the_list_is_never_exempt_under_it() -> None:
    """The acceptance criterion: construct the diff the rule exists for and watch it refuse.

    The list would happily cover the other path — that is what makes this the false-pass
    case: the entry is live, the match is real, and the refusal must fire anyway.
    """
    read = exemptions_ok((doc_entry("docs/research/", "anything at all"),))
    decision = review_loop.exemption_decision(
        read,
        (
            "docs/research/x.md",
            review_loop.EXEMPTIONS_RELATIVE.as_posix(),
        ),
    )
    assert isinstance(decision, review_loop.ReviewRequired)
    assert decision.evidence == (
        review_loop.SELF_EXEMPTION_EVIDENCE.format(path=review_loop.EXEMPTIONS_RELATIVE.as_posix()),
    )


def test_a_table_that_could_not_be_read_never_exempts() -> None:
    read = review_loop.ExemptionRead(None, "config/review-exemptions.json: gone")
    decision = review_loop.exemption_decision(read, ("docs/research/x.md",))
    assert isinstance(decision, review_loop.Unreadable)
    assert decision.kind == review_loop.UNREADABLE
    assert decision.reasons == ("config/review-exemptions.json: gone",)


def test_a_decision_with_no_paths_exempts_nothing() -> None:
    read = exemptions_ok((doc_entry("docs/"),))
    decision = review_loop.exemption_decision(read, ())
    assert isinstance(decision, review_loop.ReviewRequired)
    assert decision.evidence == (review_loop.EMPTY_PATHS_EVIDENCE,)


# --------------------------------------------------------------------------- the loop state


def test_the_first_review_opens_the_loop_at_round_zero() -> None:
    loop = review_loop.first_review((finding("F1"), finding("F2", review_loop.LOW)))
    assert loop.review_rounds == 0
    assert [f.id for f in loop.findings] == ["F1", "F2"]
    assert all(f.round_raised == 0 for f in loop.findings)


def test_a_severity_outside_the_four_levels_is_refused() -> None:
    assert (
        refused(lambda: review_loop.first_review((finding("F1", "urgent"),)))
        == review_loop.SEVERITY_ERROR
    )


def test_a_duplicate_id_in_one_review_is_refused() -> None:
    assert (
        refused(lambda: review_loop.first_review((finding("F1"), finding("F1"))))
        == review_loop.DUPLICATE_FINDING_ERROR
    )


def test_a_finding_cannot_be_smuggled_in_at_another_round() -> None:
    assert (
        refused(lambda: review_loop.first_review((finding("F1", round_raised=2),)))
        == review_loop.ROUND_STAMP_ERROR
    )


def test_a_re_review_advances_the_round_and_stamps_its_findings() -> None:
    loop = review_loop.next_round(
        review_loop.first_review((finding("F1"),)), (finding("F2", round_raised=1),)
    )
    assert loop.review_rounds == 1
    assert [f.id for f in loop.findings] == ["F1", "F2"]
    assert loop.findings[1].round_raised == 1


def test_an_id_an_earlier_round_carried_is_the_reopening_the_ruling_forbids() -> None:
    loop = review_loop.first_review((finding("F1"),))
    assert (
        refused(lambda: review_loop.next_round(loop, (finding("F1", round_raised=1),)))
        == review_loop.DUPLICATE_FINDING_ERROR
    )


def test_a_re_review_refuses_a_finding_stamped_with_another_round() -> None:
    loop = review_loop.first_review((finding("F1"),))
    assert (
        refused(lambda: review_loop.next_round(loop, (finding("F2", round_raised=4),)))
        == review_loop.ROUND_STAMP_ERROR
    )


def test_each_of_the_four_routes_closes_a_finding() -> None:
    for route in sorted(review_loop.ROUTES):
        record = (
            adjud(review_loop.ACCEPTED_AND_FILED, "#99", "a future caller widens the input")
            if route == review_loop.ACCEPTED_AND_FILED
            else adjud(route)
        )
        loop = review_loop.first_review((finding("F1"),))
        closed = review_loop.adjudicate(loop, "F1", record)
        assert closed.findings[0].adjudication == record


def test_an_unknown_route_is_refused() -> None:
    loop = review_loop.first_review((finding("F1"),))
    assert (
        refused(lambda: review_loop.adjudicate(loop, "F1", adjud("implemented")))
        == review_loop.ROUTE_ERROR
    )


def test_an_unknown_finding_is_refused() -> None:
    loop = review_loop.first_review((finding("F1"),))
    assert (
        refused(lambda: review_loop.adjudicate(loop, "F9", adjud(review_loop.FIXED)))
        == review_loop.UNKNOWN_FINDING_ERROR
    )


def test_a_closed_finding_takes_no_second_adjudication() -> None:
    loop = review_loop.adjudicate(
        review_loop.first_review((finding("F1"),)), "F1", adjud(review_loop.FIXED)
    )
    assert (
        refused(lambda: review_loop.adjudicate(loop, "F1", adjud(review_loop.FIXED)))
        == review_loop.CLOSED_FINDING_ERROR
    )


def test_accepted_and_filed_is_available_at_medium_and_low() -> None:
    for severity in (review_loop.MEDIUM, review_loop.LOW):
        loop = review_loop.first_review((finding("F1", severity),))
        closed = review_loop.adjudicate(
            loop, "F1", adjud(review_loop.ACCEPTED_AND_FILED, "#42", "work X")
        )
        assert closed.findings[0].adjudication == adjud(
            review_loop.ACCEPTED_AND_FILED, "#42", "work X"
        )


def test_accepted_and_filed_is_refused_above_medium() -> None:
    for severity in (review_loop.CRITICAL, review_loop.HIGH):
        loop = review_loop.first_review((finding("F1", severity),))

        def close(that_loop: review_loop.Loop = loop) -> object:
            return review_loop.adjudicate(
                that_loop, "F1", adjud(review_loop.ACCEPTED_AND_FILED, "#42", "work X")
            )

        assert refused(close) == review_loop.ROUTE_SEVERITY_ERROR


def test_accepted_and_filed_must_name_the_issue_and_the_outside_work() -> None:
    loop = review_loop.first_review((finding("F1", review_loop.MEDIUM),))
    assert (
        refused(
            lambda: review_loop.adjudicate(
                loop, "F1", adjud(review_loop.ACCEPTED_AND_FILED, conditional_on="work X")
            )
        )
        == review_loop.FILED_ISSUE_ERROR
    )
    assert (
        refused(
            lambda: review_loop.adjudicate(
                loop, "F1", adjud(review_loop.ACCEPTED_AND_FILED, issue="#42")
            )
        )
        == review_loop.CONDITIONAL_ON_ERROR
    )


def test_above_low_reads_the_band_the_stop_condition_adjudicates() -> None:
    assert [review_loop.above_low(s) for s in review_loop.SEVERITIES] == [
        True,
        True,
        True,
        False,
    ]


def test_the_stop_condition_blocks_on_an_open_finding_above_low_and_nothing_else() -> None:
    loop = review_loop.first_review(
        (finding("F1", review_loop.HIGH), finding("F2", review_loop.LOW))
    )
    assert review_loop.stop_condition(loop) is False
    assert review_loop.holding_above_low(loop) is True

    fixed = review_loop.adjudicate(loop, "F1", adjud(review_loop.FIXED))
    assert review_loop.stop_condition(fixed) is True
    assert review_loop.holding_above_low(fixed) is False

    low_only = review_loop.first_review((finding("F2", review_loop.LOW),))
    assert review_loop.stop_condition(low_only) is True
    assert review_loop.holding_above_low(low_only) is False


# --------------------------------------------------------------------------- the escalation bridge


def test_item_state_records_the_two_wall_facts_condition_one_fires_on() -> None:
    """The material change, pinned: rounds and the open finding arrive recorded, not None."""
    loop = review_loop.next_round(
        review_loop.first_review((finding("F1"),)),
        (finding("F2", round_raised=1),),
    )
    state = review_loop.item_state(loop, routing_class=6)
    assert state == escalation.ItemState(
        routing_class=6, review_rounds=1, finding_above_low=True, attempts=None
    )


def test_the_wall_fires_at_three_rounds_holding_a_finding_above_low() -> None:
    def at(rounds: int, *, holding_above_low: bool) -> bool:
        severity = review_loop.MEDIUM if holding_above_low else review_loop.LOW
        loop = review_loop.Loop(review_rounds=rounds, findings=(finding("F1", severity),))
        return review_loop.at_wall(loop)

    assert at(3, holding_above_low=True) is True
    assert at(2, holding_above_low=True) is False
    assert at(3, holding_above_low=False) is False
    assert at(4, holding_above_low=True) is True


def test_a_loop_at_the_wall_fires_condition_one_through_the_bridge() -> None:
    loop = review_loop.Loop(review_rounds=3, findings=(finding("F1"),))
    outcome = review_loop.evaluate_escalation(
        escalation.ReadResult(conditions()), loop, arbiter="codex-sol-high"
    )
    assert isinstance(outcome, escalation.Firing)
    assert [emission.condition.id for emission in outcome.emissions] == [1]


def test_a_loop_below_the_wall_fires_nothing() -> None:
    loop = review_loop.Loop(review_rounds=2, findings=(finding("F1"),))
    outcome = review_loop.evaluate_escalation(
        escalation.ReadResult(conditions()), loop, arbiter="codex-sol-high"
    )
    assert isinstance(outcome, escalation.NoFiring)


def test_a_two_item_wall_history_fires_condition_two_through_the_bridge() -> None:
    """`prior` passes through the wrapper — dropped, condition two emits nothing.

    The round-1 review's pin: a bridge shown firing conditions 1 and 4 only proves two of
    its four inputs, so a regression that stops carrying `prior` would read green until the
    history is recorded for real. The prior items are built through `item_state` too, so the
    wall facts they fire on are the bridge's own recording rather than a hand-built state.
    """
    at_wall = review_loop.Loop(review_rounds=3, findings=(finding("F1"),))
    history = (
        review_loop.item_state(at_wall, routing_class=5),
        review_loop.item_state(at_wall, routing_class=5),
    )
    outcome = review_loop.evaluate_escalation(
        escalation.ReadResult(conditions()), at_wall, routing_class=5, prior=history
    )
    assert isinstance(outcome, escalation.Firing)
    assert [emission.condition.id for emission in outcome.emissions] == [2]


def test_a_clean_base_retry_fires_condition_three_through_the_bridge() -> None:
    """`attempts` passes through the wrapper — dropped, condition three emits nothing.

    Recorded attempts are the observatory's sequenced work, so this seam is what keeps the
    pass-through honest until a real attempt history exists to exercise it.
    """
    at_wall = review_loop.Loop(review_rounds=3, findings=(finding("F1"),))
    attempts = (
        escalation.Attempt("opus-high", None),
        escalation.Attempt("codex-sol-high", clean_base=True),
    )
    outcome = review_loop.evaluate_escalation(
        escalation.ReadResult(conditions()), at_wall, attempts=attempts
    )
    assert isinstance(outcome, escalation.Firing)
    assert [emission.condition.id for emission in outcome.emissions] == [3]


def test_a_class_four_item_fires_condition_four_through_the_bridge() -> None:
    loop = review_loop.Loop(review_rounds=0, findings=())
    outcome = review_loop.evaluate_escalation(
        escalation.ReadResult(conditions()), loop, routing_class=4
    )
    assert isinstance(outcome, escalation.Firing)
    assert [emission.condition.id for emission in outcome.emissions] == [4]


def test_an_unreadable_condition_table_passes_through_as_unreadable() -> None:
    loop = review_loop.Loop(review_rounds=3, findings=(finding("F1"),))
    outcome = review_loop.evaluate_escalation(
        escalation.ReadResult(None, "config/escalation-conditions.json: gone"),
        loop,
        arbiter="codex-sol-high",
    )
    assert isinstance(outcome, escalation.Unreadable)
