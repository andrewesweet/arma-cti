"""The never-alone decision surface: exemption, rounds, adjudication, escalation (#331, #333).

Five layers. The exemption table first — the shipped file read in the caller's body, its
shape asserted, its emptiness pinned as the state nothing has yet earned its way off. Then
the decision, both directions and the third state: unlisted means covered, listed means
exempt with its reason quotable, unreadable never exempts, and a diff touching the list
itself is never exempt whatever the list says. Then the loop: round stamping, the four
adjudication routes with the fourth's three restrictions and the arbiter routes'
precondition — no arbiter exists until the escalation that produces one has fired —
one-adjudication-per-finding, and the escalation bridge that turns a live loop into the two
recorded wall facts — which lights condition one, while conditions two and three wait on a
`prior` history and recorded `attempts` that no loop carries. Then #333's half over that
state: the budget counts only findings *held across* rounds (introduced-by-the-round is
#356's shape, held is #326's), the terminus computes what the pre-declared default owes,
and every observable leaves its event. Then the durable half: the loop document that
survives the turn that opened it, and the command surface that drives the whole loop from
`open` to `terminus` — the production caller whose absence was round 1's High 5.
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
    """The two review routes at round zero, the two arbiter routes at the wall they require."""
    for route in (review_loop.FIXED, review_loop.ACCEPTED_AND_FILED):
        record = (
            adjud(review_loop.ACCEPTED_AND_FILED, "#99", "a future caller widens the input")
            if route == review_loop.ACCEPTED_AND_FILED
            else adjud(route)
        )
        loop = review_loop.first_review((finding("F1", review_loop.LOW),))
        closed = review_loop.adjudicate(loop, "F1", record)
        assert closed.findings[0].adjudication == record
    for route in (review_loop.ARBITER_UPHELD, review_loop.ARBITER_DISMISSED):
        loop = review_loop.Loop(3, (finding("F1", review_loop.HIGH, round_raised=1),))
        closed = review_loop.adjudicate(loop, "F1", adjud(route))
        assert closed.findings[0].adjudication == adjud(route)


def test_a_round_zero_arbiter_verdict_is_refused() -> None:
    """Round 1's Critical: no escalation has fired, so there is no arbiter to speak of.

    Constructed, not inherited — the acceptance criterion's own ask. Both arbiter routes,
    below the wall, at every round count short of it: the precondition is the escalation,
    never the finding's severity.
    """
    for route in (review_loop.ARBITER_UPHELD, review_loop.ARBITER_DISMISSED):
        for loop in (
            review_loop.first_review((finding("F1", review_loop.CRITICAL),)),
            review_loop.Loop(2, (finding("F1", review_loop.HIGH, round_raised=0),)),
        ):
            assert (
                # Bound as defaults: the lambda runs inside the iteration that made it.
                refused(
                    lambda loop=loop, route=route: review_loop.adjudicate(loop, "F1", adjud(route))
                )
                == review_loop.ARBITER_UNAUTHORISED_ERROR
            )


def test_the_precondition_reads_the_wall_and_the_recorded_verdicts() -> None:
    below = review_loop.Loop(2, (finding("F1", review_loop.HIGH),))
    assert review_loop.escalation_fired(below) is False
    wall = review_loop.Loop(3, (finding("F1", review_loop.HIGH, round_raised=1),))
    assert review_loop.escalation_fired(wall) is True
    # The strongest single fact here: after the wall's own verdict closes the finding the
    # wall read, neither half of the wall holds any more — rounds are 3 but nothing above
    # Low is held across — so the recorded verdict is the only reason this reads True.
    adjudicated = review_loop.adjudicate(wall, "F1", adjud(review_loop.ARBITER_UPHELD))
    assert review_loop.at_wall(adjudicated) is False
    assert review_loop.escalation_fired(adjudicated) is True


def test_the_second_verdict_of_one_arbitration_stays_admissible() -> None:
    """One verdict consumes the held finding the wall reads, so the wall cannot gate the next.

    `holding_above_low` counts open findings; one closed `arbiter_upheld` no longer holds,
    so verdict order within one arbitration must not decide which verdicts are legal. The
    recorded verdict stands in for the wall — the widen clause, pinned as the case that
    would refuse without it.
    """
    loop = review_loop.Loop(
        3,
        (
            finding("F1", review_loop.HIGH, round_raised=1),
            finding("F2", review_loop.HIGH, round_raised=3),
        ),
    )
    assert review_loop.at_wall(loop) is True
    first = review_loop.adjudicate(loop, "F1", adjud(review_loop.ARBITER_UPHELD))
    # F2 was raised by the round itself (#356's shape), so with F1 closed nothing is held
    # across and the wall no longer reads True — the second verdict is admissible on the
    # recorded verdict alone.
    assert review_loop.at_wall(first) is False
    second = review_loop.adjudicate(first, "F2", adjud(review_loop.ARBITER_DISMISSED))
    assert second.findings[1].adjudication == adjud(review_loop.ARBITER_DISMISSED)


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
    # Round zero holds nothing across by definition — no round has been failed yet — and
    # the landing block and the escalation fact part ways here on purpose (#333): any
    # open finding above Low blocks the landing, only held-across feeds the wall.
    assert review_loop.holding_above_low(loop) is False

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


# ------------------------------------------------- held across, or introduced by the round


def test_a_finding_held_across_rounds_feeds_the_wall() -> None:
    """#326's shape: raised in round 2, still open at round 3 — the wall fires."""
    loop = review_loop.Loop(
        3,
        (finding("F1", review_loop.HIGH, round_raised=2),),
    )
    assert review_loop.holding_above_low(loop) is True
    assert review_loop.at_wall(loop) is True
    outcome = review_loop.evaluate_escalation(
        escalation.ReadResult(conditions()), loop, arbiter="opus-max"
    )
    assert isinstance(outcome, escalation.Firing)
    assert [emission.condition.id for emission in outcome.emissions] == [1]


def test_a_finding_the_round_itself_introduced_does_not_feed_the_wall() -> None:
    """#356/#327's shape: round 3 raised it, so another fix round is taken, not a transfer.

    The budget counts rounds spent failing to close a finding; it is not a cap on how
    many defects a branch may reveal. A wall that cannot tell the two apart escalates
    work that should not escalate and vice versa.
    """
    loop = review_loop.Loop(
        3,
        (
            finding(
                "F1", review_loop.MEDIUM, round_raised=0, adjudication=adjud(review_loop.FIXED)
            ),
            finding("F2", review_loop.HIGH, round_raised=3),
        ),
    )
    assert review_loop.holding_above_low(loop) is False
    assert review_loop.at_wall(loop) is False
    outcome = review_loop.evaluate_escalation(
        escalation.ReadResult(conditions()), loop, arbiter="opus-max"
    )
    assert isinstance(outcome, escalation.NoFiring)


def test_a_finding_introduced_in_round_three_becomes_held_in_round_four() -> None:
    """The same finding, one round later, is held — the wall fires on the fourth re-review."""
    loop = review_loop.Loop(
        4,
        (
            finding(
                "F1", review_loop.MEDIUM, round_raised=0, adjudication=adjud(review_loop.FIXED)
            ),
            finding("F2", review_loop.HIGH, round_raised=3),
        ),
    )
    assert review_loop.holding_above_low(loop) is True
    assert review_loop.at_wall(loop) is True


# --------------------------------------------------------------------------- the terminus


def at_the_wall_arbitrated() -> review_loop.Loop:
    """Return a loop that reached the wall and was arbitrated: upheld, dismissed, fixed, filed."""
    loop = review_loop.Loop(
        3,
        (
            finding("F1", review_loop.CRITICAL, round_raised=1),
            finding("F2", review_loop.HIGH, round_raised=2),
            finding("F3", review_loop.MEDIUM, round_raised=0),
            finding("F4", review_loop.LOW, round_raised=2),
        ),
    )
    loop = review_loop.adjudicate(loop, "F1", adjud(review_loop.ARBITER_UPHELD))
    loop = review_loop.adjudicate(loop, "F2", adjud(review_loop.ARBITER_DISMISSED))
    loop = review_loop.adjudicate(loop, "F3", adjud(review_loop.FIXED))
    return review_loop.adjudicate(
        loop, "F4", adjud(review_loop.ACCEPTED_AND_FILED, "#99", "work X")
    )


def test_a_convergent_loop_lands_through_the_default_owing_nothing() -> None:
    loop = review_loop.adjudicate(
        review_loop.first_review((finding("F1", review_loop.HIGH),)),
        "F1",
        adjud(review_loop.FIXED),
    )
    end = review_loop.terminus(loop)
    assert end.default_applies is True
    assert end.filings == ()
    assert end.dismissals == ()


def test_an_arbitrated_loop_lands_through_the_default_owing_both_traces() -> None:
    """Non-convergence to the default: the wall fired, the arbiter ruled, the default applies.

    The upheld Critical is closed by the verdict and still owed its filing — not only the
    unresolved are filed, because an upheld finding that vanished with its verdict is the
    finding that most needs a trace. The dismissal is recorded for the post-landing seat.
    """
    end = review_loop.terminus(at_the_wall_arbitrated())
    assert end.default_applies is True
    assert end.filings == (review_loop.Filing("F1", review_loop.CRITICAL, 1),)
    assert end.dismissals == (review_loop.Dismissal("F2", review_loop.HIGH, 2),)


def test_the_fixed_and_the_accepted_and_filed_appear_in_neither_trace() -> None:
    """A fix's trace is the diff; `accepted_and_filed` already names the issue it became."""
    end = review_loop.terminus(at_the_wall_arbitrated())
    assert [f.finding for f in end.filings + end.dismissals] == ["F1", "F2"]


def test_an_upheld_low_is_owed_its_filing_the_same_as_an_upheld_critical() -> None:
    """Ruling 4's terminus sentence carries no severity qualifier, and neither does the filing.

    The Low cannot reach an arbiter on its own — it holds nothing above Low, so it cannot
    fire the wall — which is itself the precondition's point: the arbitration that closes
    it was authorised by the High beside it.
    """
    loop = review_loop.Loop(
        3,
        (
            finding("F1", review_loop.HIGH, round_raised=1),
            finding("F2", review_loop.LOW, round_raised=2),
        ),
    )
    loop = review_loop.adjudicate(loop, "F1", adjud(review_loop.ARBITER_UPHELD))
    loop = review_loop.adjudicate(loop, "F2", adjud(review_loop.ARBITER_UPHELD))
    end = review_loop.terminus(loop)
    assert end.default_applies is True
    assert end.filings == (
        review_loop.Filing("F1", review_loop.HIGH, 1),
        review_loop.Filing("F2", review_loop.LOW, 2),
    )


def test_an_open_finding_above_low_stops_the_default_with_an_answer_not_an_error() -> None:
    loop = review_loop.adjudicate(
        review_loop.first_review(
            (finding("F1", review_loop.HIGH), finding("F2", review_loop.MEDIUM))
        ),
        "F1",
        adjud(review_loop.FIXED),
    )
    end = review_loop.terminus(loop)
    assert end.default_applies is False
    # The traces are still computed over what was adjudicated — #334's landing refusal is
    # the consumer that refuses on `default_applies`, not on an exception.
    assert end.filings == ()
    assert end.dismissals == ()


# --------------------------------------------------------------------------- telemetry


def rendered(event: object) -> dict[str, object]:
    document = review_loop.otel_event.log_record(event)
    record = document["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]
    return {a["key"]: a["value"] for a in record["attributes"]}


def test_a_round_event_carries_the_observatorys_own_observables() -> None:
    loop = review_loop.next_round(
        review_loop.first_review((finding("F1", review_loop.HIGH),)),
        (finding("F2", review_loop.MEDIUM, round_raised=1),),
    )
    event = review_loop.round_event(loop, "#326", at=2.0)
    attributes = rendered(event)
    assert event.name == review_loop.ROUND_EVENT
    assert attributes["cti.issue"] == {"stringValue": "#326"}
    assert attributes["cti.review.round"] == {"intValue": "1"}
    assert attributes["cti.review.raised"] == {"intValue": "1"}
    assert attributes["cti.review.open_above_low"] == {"intValue": "2"}
    assert attributes["cti.review.holding_above_low"] == {"boolValue": True}


def test_an_escalation_event_carries_the_evaluation_kind_and_the_arbiter() -> None:
    loop = review_loop.Loop(3, (finding("F1", round_raised=2),))
    outcome = review_loop.evaluate_escalation(
        escalation.ReadResult(conditions()), loop, arbiter="opus-max"
    )
    event = review_loop.escalation_event(outcome, "#348", at=3.0, arbiter="opus-max")
    attributes = rendered(event)
    assert event.name == review_loop.ESCALATION_EVENT
    # The kind travels (#333 round 1, Medium 5): a count of events cannot tell a loop that
    # confidently fired nothing from one whose condition table would not open.
    assert attributes["cti.review.evaluation"] == {"stringValue": escalation.FIRING}
    assert attributes["cti.review.conditions"] == {"stringValue": "1"}
    assert attributes["cti.review.arbiter"] == {"stringValue": "opus-max"}
    # Silence and unreadable input are states the observatory must count, not read past.
    quiet = review_loop.escalation_event(escalation.NoFiring(), "#348", at=3.0)
    quiet_attributes = rendered(quiet)
    assert quiet_attributes["cti.review.evaluation"] == {"stringValue": escalation.NO_FIRING}
    assert quiet_attributes["cti.review.conditions"] == {"stringValue": ""}
    blind = review_loop.escalation_event(escalation.Unreadable(("gone",)), "#348", at=3.0)
    assert rendered(blind)["cti.review.evaluation"] == {"stringValue": escalation.UNREADABLE}


def test_a_dispute_event_carries_the_finding_and_its_route() -> None:
    event = review_loop.dispute_event(
        finding("F1", review_loop.CRITICAL, round_raised=1),
        adjud(review_loop.ARBITER_UPHELD),
        "#326",
        at=4.0,
    )
    attributes = rendered(event)
    assert event.name == review_loop.DISPUTE_EVENT
    assert attributes["cti.review.finding"] == {"stringValue": "F1"}
    assert attributes["cti.review.severity"] == {"stringValue": review_loop.CRITICAL}
    assert attributes["cti.review.round_raised"] == {"intValue": "1"}
    assert attributes["cti.review.route"] == {"stringValue": review_loop.ARBITER_UPHELD}


def test_a_terminus_event_carries_the_default_and_both_trace_identities() -> None:
    end = review_loop.terminus(at_the_wall_arbitrated())
    event = review_loop.terminus_event(end, "#326", at=5.0)
    attributes = rendered(event)
    assert event.name == review_loop.TERMINUS_EVENT
    assert attributes["cti.review.default_applies"] == {"boolValue": True}
    # Identities, not counts (#333 round 1, Medium 5): which finding, at what severity.
    assert attributes["cti.review.filings"] == {"stringValue": f"F1:{review_loop.CRITICAL}"}
    assert attributes["cti.review.dismissals"] == {"stringValue": f"F2:{review_loop.HIGH}"}


def test_emission_journals_whether_or_not_the_collector_took_it(tmp_path: Path) -> None:
    journal = tmp_path / "journal.jsonl"
    loop = review_loop.first_review((finding("F1", review_loop.HIGH),))
    review_loop.emit_round(loop, "#326", at=2.0, journal=journal)
    line = json.loads(journal.read_text(encoding="utf-8").splitlines()[0])
    assert line["event"] == review_loop.ROUND_EVENT
    assert line["attributes"]["cti.issue"] == "#326"
    # The journal line carries the export's own outcome — the durable half is written
    # whichever way the bounded attempt landed.
    assert "exported" in line


# --------------------------------------------------------------------------- the durable loop


def test_a_stored_loop_round_trips_through_its_document() -> None:
    """Every route, every severity band, adjudications included: out and back, one loop."""
    loop = at_the_wall_arbitrated()
    assert review_loop.parse_loop(review_loop.render_loop(326, loop)) == loop


def test_a_document_that_could_not_govern_silently_is_refused_on_read() -> None:
    document = review_loop.render_loop(326, review_loop.first_review((finding("F1"),)))
    assert (
        refused(lambda: review_loop.parse_loop({**document, "version": 2}))
        == review_loop.LOOP_VERSION_ERROR
    )
    assert (
        refused(lambda: review_loop.parse_loop({**document, "review_rounds": "three"}))
        == review_loop.LOOP_ROUNDS_ERROR
    )
    assert (
        refused(lambda: review_loop.parse_loop({**document, "findings": "none"}))
        == review_loop.LOOP_FINDINGS_ERROR
    )
    assert (
        refused(
            lambda: review_loop.parse_loop(
                {**document, "findings": [{"id": "F1", "severity": "high", "round_raised": 1}]}
            )
        )
        == review_loop.ROUND_RANGE_ERROR
    )
    # The precondition is deliberately absent from this list: storage does not re-derive
    # it, because a loop carrying a pre-precondition verdict must still be readable.


def test_the_store_refuses_a_document_naming_another_issue(tmp_path: Path) -> None:
    root = tmp_path / "review"
    review_loop.store_loop(root, 326, review_loop.first_review((finding("F1"),)))
    assert review_loop.load_loop(root, 326).findings[0].id == "F1"
    (root / "326" / review_loop.LOOP_FILE).write_text(
        json.dumps(review_loop.render_loop(999, review_loop.first_review((finding("F1"),)))),
        encoding="utf-8",
    )
    assert refused(
        lambda: review_loop.load_loop(root, 326)
    ) == review_loop.ISSUE_MISMATCH_ERROR.format(stored=999, asked=326)


# --------------------------------------------------------------------------- the command surface


def write_record(dispatch_dir: Path, name: str, *, issue: int, profile: str, seat: str) -> None:
    """One dispatch record in the shape `dispatch._read_record` reads."""
    entry = dispatch_dir / name
    entry.mkdir(parents=True)
    (entry / "dispatch.json").write_text(
        json.dumps({"issue": issue, "profile": profile, "seat": seat, "dispatch_id": name}),
        encoding="utf-8",
    )


def stepped_clock() -> Callable[[], float]:
    """Build a clock the tests own: every call advances one second, off any wall clock."""
    tick = [0.0]

    def now() -> float:
        tick[0] += 1.0
        return tick[0]

    return now


def test_the_cli_refuses_the_round_zero_dismissal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The round-1 Critical, driven through the production caller: refuse, exit 1, store nothing."""
    root = tmp_path / "review"
    base = ["--root", str(root), "--journal", str(tmp_path / "journal.jsonl")]
    assert (
        review_loop.main(
            ["open", "--issue", "326", *base, "--finding", "F1=critical"], now=stepped_clock()
        )
        == review_loop.OK
    )
    code = review_loop.main(
        [
            "adjudicate",
            "--issue",
            "326",
            *base,
            "--finding",
            "F1",
            "--route",
            review_loop.ARBITER_DISMISSED,
        ],
        now=stepped_clock(),
    )
    assert code == review_loop.REFUSED
    assert review_loop.ARBITER_UNAUTHORISED_ERROR in capsys.readouterr().err
    # Refused before the store: the loop on disk still carries the finding open.
    assert review_loop.load_loop(root, 326).findings[0].adjudication is None


def test_the_command_surface_drives_one_loop_end_to_end(tmp_path: Path) -> None:
    """Open, three rounds, escalate, adjudicate, terminus — one issue, all durable state real.

    The escalation reads a dispatch directory the test writes (`resolve_dispatchable`'s
    production inputs: records, scratch admission/breaker state, a key-less credentials
    file), so the arbiter answered here is the one the walk would answer on the box — the
    implementer seat's entry head, `codex-sol-high`, held clean by the scratch state the
    test points the rungs at.
    """
    root = tmp_path / "review"
    journal = tmp_path / "journal.jsonl"
    dispatch_dir = tmp_path / "dispatches"
    write_record(dispatch_dir, "d1", issue=333, profile="opus-high", seat="implementer")
    write_record(dispatch_dir, "d2", issue=333, profile="opus-xhigh", seat="review")
    credentials = tmp_path / "credentials.env"
    credentials.write_text("# no keys the walk reads\n", encoding="utf-8")
    credentials.chmod(0o600)
    filings: list[tuple[str, str]] = []
    comments: list[tuple[int, str]] = []

    def create(title: str, body: str) -> int:
        filings.append((title, body))
        return 400 + len(filings)

    def post(issue: int, body: str) -> None:
        comments.append((issue, body))

    clock = stepped_clock()
    base = ["--root", str(root), "--journal", str(journal)]
    kwargs = {"now": clock, "create_issue": create, "post_comment": post}
    assert (
        review_loop.main(["open", "--issue", "333", *base, "--finding", "F1=critical"], **kwargs)
        == review_loop.OK
    )
    assert (
        review_loop.main(["round", "--issue", "333", *base, "--finding", "F2=high"], **kwargs)
        == review_loop.OK
    )
    assert review_loop.main(["round", "--issue", "333", *base], **kwargs) == review_loop.OK
    assert review_loop.main(["round", "--issue", "333", *base], **kwargs) == review_loop.OK
    assert review_loop.load_loop(root, 333).review_rounds == 3
    assert (
        review_loop.main(
            [
                "escalate",
                "--issue",
                "333",
                *base,
                "--seat",
                "implementer",
                "--dispatch-dir",
                str(dispatch_dir),
                "--admission-dir",
                str(tmp_path / "admission"),
                "--breaker-dir",
                str(tmp_path / "breaker"),
                "--credentials",
                str(credentials),
                "--conditions",
                str(CONDITIONS),
            ],
            **kwargs,
        )
        == review_loop.OK
    )
    escalation_record = json.loads(
        (root / "333" / review_loop.ESCALATION_FILE).read_text(encoding="utf-8")
    )
    assert escalation_record["evaluation"] == escalation.FIRING
    assert escalation_record["arbiter"] == "codex-sol-high"
    assert (
        review_loop.main(
            [
                "adjudicate",
                "--issue",
                "333",
                *base,
                "--finding",
                "F1",
                "--route",
                review_loop.ARBITER_UPHELD,
            ],
            **kwargs,
        )
        == review_loop.OK
    )
    assert (
        review_loop.main(
            [
                "adjudicate",
                "--issue",
                "333",
                *base,
                "--finding",
                "F2",
                "--route",
                review_loop.ARBITER_DISMISSED,
            ],
            **kwargs,
        )
        == review_loop.OK
    )
    assert review_loop.main(["terminus", "--issue", "333", *base], **kwargs) == review_loop.OK
    assert [title for title, _ in filings] == ["Arbiter-upheld finding F1 (critical) from #333"]
    assert filings[0][1].startswith(f"{review_loop.FILING_MARKER} #333")
    assert [issue for issue, _ in comments] == [333]
    assert comments[0][1].startswith(f"{review_loop.DISMISSAL_MARKER} #333")
    landing = json.loads((root / "333" / review_loop.LANDING_FILE).read_text(encoding="utf-8"))
    assert landing["arbiter"] == "codex-sol-high"
    assert landing["filings"] == [
        {"finding": "F1", "severity": "critical", "round_raised": 0, "issue": 401}
    ]
    assert landing["dismissals"] == [{"finding": "F2", "severity": "high", "round_raised": 1}]
    # The terminus is once: a second run would file every upheld finding twice.
    assert review_loop.main(["terminus", "--issue", "333", *base], **kwargs) == review_loop.REFUSED
    assert len(filings) == 1
    events = [
        json.loads(line)["event"] for line in journal.read_text(encoding="utf-8").splitlines()
    ]
    assert events == [
        review_loop.ROUND_EVENT,
        review_loop.ROUND_EVENT,
        review_loop.ROUND_EVENT,
        review_loop.ROUND_EVENT,
        "cti.review.arbiter.resolved",
        review_loop.ESCALATION_EVENT,
        review_loop.DISPUTE_EVENT,
        review_loop.DISPUTE_EVENT,
        review_loop.TERMINUS_EVENT,
    ]


def test_the_cli_named_refusals(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "review"
    base = ["--root", str(root), "--journal", str(tmp_path / "journal.jsonl")]
    clock = stepped_clock()
    # Acting before a loop exists, opening one twice, an unknown seat, a terminus the loop
    # has not reached: each is a named refusal, exit 1, nothing written.
    assert review_loop.main(["round", "--issue", "326", *base], now=clock) == review_loop.REFUSED
    assert review_loop.NO_LOOP_ERROR.format(issue=326, root=root) in capsys.readouterr().err
    assert (
        review_loop.main(["open", "--issue", "326", *base, "--finding", "F1=high"], now=clock)
        == review_loop.OK
    )
    assert (
        review_loop.main(["open", "--issue", "326", *base, "--finding", "F1=high"], now=clock)
        == review_loop.REFUSED
    )
    assert review_loop.LOOP_EXISTS_ERROR.format(issue=326, root=root) in capsys.readouterr().err
    assert (
        review_loop.main(["escalate", "--issue", "326", *base, "--seat", "no-such-seat"], now=clock)
        == review_loop.REFUSED
    )
    assert review_loop.SEAT_UNKNOWN_ERROR.format(seat="no-such-seat") in capsys.readouterr().err
    assert review_loop.main(["terminus", "--issue", "326", *base], now=clock) == review_loop.REFUSED
    assert review_loop.TERMINUS_NOT_REACHED_ERROR in capsys.readouterr().err
    assert not (root / "326" / review_loop.LANDING_FILE).exists()


def test_a_dry_run_terminus_posts_and_writes_nothing(tmp_path: Path) -> None:
    root = tmp_path / "review"
    base = ["--root", str(root), "--journal", str(tmp_path / "journal.jsonl")]
    clock = stepped_clock()
    filings: list[tuple[str, str]] = []
    comments: list[tuple[int, str]] = []
    assert (
        review_loop.main(["open", "--issue", "326", *base, "--finding", "F1=low"], now=clock)
        == review_loop.OK
    )
    assert (
        review_loop.main(
            [
                "adjudicate",
                "--issue",
                "326",
                *base,
                "--finding",
                "F1",
                "--route",
                review_loop.FIXED,
            ],
            now=clock,
            create_issue=lambda title, body: filings.append((title, body)) or 0,
            post_comment=lambda issue, body: comments.append((issue, body)),
        )
        == review_loop.OK
    )
    assert (
        review_loop.main(
            ["terminus", "--issue", "326", *base, "--dry-run"],
            now=clock,
            create_issue=lambda title, body: filings.append((title, body)) or 0,
            post_comment=lambda issue, body: comments.append((issue, body)),
        )
        == review_loop.OK
    )
    assert filings == []
    assert comments == []
    assert not (root / "326" / review_loop.LANDING_FILE).exists()
