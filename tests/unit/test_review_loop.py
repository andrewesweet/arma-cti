"""The never-alone decision surface: exemption, rounds, adjudication, escalation (#331, #333).

Five layers. The exemption table first — the shipped file read in the caller's body, its
shape asserted, its emptiness pinned as the state nothing has yet earned its way off. Then
the decision, both directions and the third state: unlisted means covered, listed means
exempt with its reason quotable, unreadable never exempts, and a diff touching the list
itself is never exempt whatever the list says. Then the loop: round stamping, the four
adjudication routes with the fourth's three restrictions and the arbiter routes'
precondition — decided per finding, the escalation must have fired on the finding itself,
so a verdict in a later round inherits nothing from an earlier one —
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
import subprocess
from typing import TYPE_CHECKING, Final

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
# The copy review_loop itself resolved the rung's inputs through, never a second exec.
routing_policy = review_loop.routing_policy

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


ARBITER: Final = "opus-xhigh"


def adjud(
    route: str,
    issue: str = "",
    conditional_on: str = "",
    arbiter: str | None = None,
) -> review_loop.Adjudication:
    """One adjudication, with an arbiter named wherever the route stands in for a ruling.

    The default is the arrangement the writer produces: `_cmd_adjudicate` fills the name
    from the escalation record, and an arbiter route without one is refused (#334 round 2,
    Medium 2). `arbiter=""` is the way a test asks for the refused shape.
    """
    if arbiter is None:
        arbiter = (
            ARBITER if route in (review_loop.ARBITER_UPHELD, review_loop.ARBITER_DISMISSED) else ""
        )
    return review_loop.Adjudication(route, issue, conditional_on, arbiter)


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


def test_the_precondition_reads_the_wall_and_this_finding_not_the_loop() -> None:
    """Per finding, round 2's Critical: the escalation must have fired *on this finding*.

    The round-1 loop-level form — the wall, or any recorded arbiter verdict — let a new
    finding inherit an earlier verdict as its licence. The three conjuncts are each pinned
    by the case that drops it: below the wall, below Low, introduced by the round itself.
    """
    held = finding("F1", review_loop.HIGH, round_raised=1)
    assert review_loop.escalation_fires_on(review_loop.Loop(3, (held,)), held) is True
    # Below the wall: the escalation has not fired at all.
    assert (
        review_loop.escalation_fires_on(
            review_loop.Loop(2, (finding("F1", review_loop.HIGH, round_raised=1),)), held
        )
        is False
    )
    # At the wall, but this finding is a Low — never what the escalation fires on.
    low = finding("F2", review_loop.LOW, round_raised=1)
    assert (
        review_loop.escalation_fires_on(
            review_loop.Loop(3, (finding("F1", review_loop.HIGH, round_raised=1), low)), low
        )
        is False
    )
    # At the wall via a held finding, but this finding the round itself introduced (#356).
    introduced = finding("F3", review_loop.HIGH, round_raised=3)
    assert (
        review_loop.escalation_fires_on(
            review_loop.Loop(3, (finding("F1", review_loop.HIGH, round_raised=1), introduced)),
            introduced,
        )
        is False
    )
    # The recorded verdict is a fact about the finding it closed, never about the loop:
    # once the wall's own verdict closes the held finding, nothing fires on anything.
    adjudicated = review_loop.adjudicate(
        review_loop.Loop(3, (held,)), "F1", adjud(review_loop.ARBITER_UPHELD)
    )
    assert review_loop.at_wall(adjudicated) is False
    assert all(
        review_loop.escalation_fires_on(adjudicated, f) is False for f in adjudicated.findings
    )


def test_a_new_finding_in_a_later_round_inherits_no_historical_verdict() -> None:
    """Round 2's Critical, constructed as the adjudication asked — no hand-built loop.

    The arbiter closes the wall-held findings, a later round raises a new finding, and its
    dismissal must refuse: #333's own body says a finding raised in a later round is a new
    item, not a reopening, and the round-1 loop-level precondition let the old verdict
    authorise the new item as its licence.
    """
    loop = review_loop.first_review((finding("F1", review_loop.HIGH),))
    loop = review_loop.next_round(loop, ())
    loop = review_loop.next_round(loop, ())
    loop = review_loop.next_round(loop, ())  # the wall: round 3, F1 held across
    assert review_loop.at_wall(loop) is True
    loop = review_loop.adjudicate(loop, "F1", adjud(review_loop.ARBITER_DISMISSED))
    loop = review_loop.next_round(loop, (finding("F2", review_loop.HIGH, round_raised=4),))
    assert review_loop.at_wall(loop) is False
    assert (
        refused(lambda: review_loop.adjudicate(loop, "F2", adjud(review_loop.ARBITER_DISMISSED)))
        == review_loop.ARBITER_UNAUTHORISED_ERROR
    )
    # F2 earns its own arbiter only through its own wall: held across at round 5, the
    # escalation fires on it and a fresh `escalate`/`adjudicate` pair is admissible again.
    loop = review_loop.next_round(loop, ())
    assert review_loop.at_wall(loop) is True
    closed = review_loop.adjudicate(loop, "F2", adjud(review_loop.ARBITER_UPHELD))
    assert closed.findings[1].adjudication == adjud(review_loop.ARBITER_UPHELD)


def test_held_across_siblings_stay_admissible_in_either_order() -> None:
    """What the round-1 widen clause was for, answered per finding instead.

    `holding_above_low` counts open findings, and the finding under adjudication is open at
    its own adjudication — so each held-across sibling is itself among what the wall reads,
    and verdict order within one arbitration cannot decide which verdicts are legal.
    """
    both = review_loop.Loop(
        3,
        (
            finding("F1", review_loop.HIGH, round_raised=1),
            finding("F2", review_loop.CRITICAL, round_raised=1),
        ),
    )
    forward = review_loop.adjudicate(
        review_loop.adjudicate(both, "F1", adjud(review_loop.ARBITER_UPHELD)),
        "F2",
        adjud(review_loop.ARBITER_DISMISSED),
    )
    backward = review_loop.adjudicate(
        review_loop.adjudicate(both, "F2", adjud(review_loop.ARBITER_DISMISSED)),
        "F1",
        adjud(review_loop.ARBITER_UPHELD),
    )
    assert forward == backward


def test_a_round_introduced_finding_takes_no_verdict_from_the_walls_arbitration() -> None:
    """#356's shape at the wall.

    The round's own finding is a new item, whatever the arbiter does to the
    held one beside it.
    """
    loop = review_loop.Loop(
        3,
        (
            finding("F1", review_loop.HIGH, round_raised=1),
            finding("F2", review_loop.HIGH, round_raised=3),
        ),
    )
    assert review_loop.at_wall(loop) is True
    assert (
        refused(lambda: review_loop.adjudicate(loop, "F2", adjud(review_loop.ARBITER_DISMISSED)))
        == review_loop.ARBITER_UNAUTHORISED_ERROR
    )
    first = review_loop.adjudicate(loop, "F1", adjud(review_loop.ARBITER_UPHELD))
    assert review_loop.at_wall(first) is False
    assert (
        refused(lambda: review_loop.adjudicate(first, "F2", adjud(review_loop.ARBITER_UPHELD)))
        == review_loop.ARBITER_UNAUTHORISED_ERROR
    )


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

    The recorded state is built directly because an upheld Low is no longer *reachable*
    through `adjudicate` — a Low is never what the escalation fires on, so its arbiter route
    refuses (the test below pins that). The terminus reads recorded verdicts without
    re-deriving the precondition, the same rule that keeps a pre-precondition verdict
    readable, and this is the severity-blindness of that read.
    """
    loop = review_loop.Loop(
        3,
        (
            finding(
                "F1",
                review_loop.HIGH,
                round_raised=1,
                adjudication=adjud(review_loop.ARBITER_UPHELD),
            ),
            finding(
                "F2",
                review_loop.LOW,
                round_raised=2,
                adjudication=adjud(review_loop.ARBITER_UPHELD),
            ),
        ),
    )
    end = review_loop.terminus(loop)
    assert end.default_applies is True
    assert end.filings == (
        review_loop.Filing("F1", review_loop.HIGH, 1),
        review_loop.Filing("F2", review_loop.LOW, 2),
    )


def test_a_low_takes_no_arbiter_route_even_at_the_wall() -> None:
    """A Low never blocks and never feeds the wall, so no arbiter settles one.

    Fix it, file it, or leave it open — the round-1 sibling clause that let a
    beside-it High authorise the Low's verdict was the related-fact-as-the-fact
    shape.
    """
    loop = review_loop.Loop(
        3,
        (
            finding("F1", review_loop.HIGH, round_raised=1),
            finding("F2", review_loop.LOW, round_raised=2),
        ),
    )
    assert review_loop.at_wall(loop) is True
    assert (
        refused(lambda: review_loop.adjudicate(loop, "F2", adjud(review_loop.ARBITER_DISMISSED)))
        == review_loop.ARBITER_UNAUTHORISED_ERROR
    )
    # The wall's own finding still closes: the refusal is about the Low, not the wall.
    closed = review_loop.adjudicate(loop, "F1", adjud(review_loop.ARBITER_UPHELD))
    assert closed.findings[0].adjudication == adjud(review_loop.ARBITER_UPHELD)


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
    # Silence and unreadable input are states the observatory must count, not read past —
    # and neither carries an arbiter, whatever the caller resolved (#333 round 2, Medium 5):
    # a profile is an arbiter only where a firing transferred to it.
    quiet = review_loop.escalation_event(escalation.NoFiring(), "#348", at=3.0, arbiter="opus-max")
    quiet_attributes = rendered(quiet)
    assert quiet_attributes["cti.review.evaluation"] == {"stringValue": escalation.NO_FIRING}
    assert quiet_attributes["cti.review.conditions"] == {"stringValue": ""}
    assert quiet_attributes["cti.review.arbiter"] == {"stringValue": ""}
    blind = review_loop.escalation_event(
        escalation.Unreadable(("gone",)), "#348", at=3.0, arbiter="opus-max"
    )
    blind_attributes = rendered(blind)
    assert blind_attributes["cti.review.evaluation"] == {"stringValue": escalation.UNREADABLE}
    assert blind_attributes["cti.review.arbiter"] == {"stringValue": ""}


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
        refused(lambda: review_loop.parse_loop({**document, "version": 3}))
        == review_loop.LOOP_VERSION_ERROR
    )
    # A version-1 document predates the self-review block (#589) and stays readable: the
    # version is the distinction, never a repudiation of state that could not govern. A
    # stray key at that version is read as absent, because nothing at v1 could write one.
    legacy = {
        **document,
        "version": 1,
        "self_review": {"rounds": []},
    }
    assert review_loop.parse_loop(legacy).self_review is None
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


# The shipped policy, read per call rather than at import, for the same reason `live()`
# gives: a broken shipped file is a test-time catch, not a collection failure.
POLICY_PATH = REPO / "config/dispatch-routing-policy.json"


def _refusing_policy_text() -> str:
    """Plant class 6 back to refusing in the shipped policy — #326's own arrangement.

    The same single-flag edit `tests/unit/test_arbiter.py`'s `refusing_policy` makes: the
    shipped document has refused nothing since ADR-0073, so a CLI test that wants the rung
    to bite plants the row the one way the shipped file defines.
    """
    document = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    for row in document[routing_policy.REFOUNDED.classes]:
        if row["id"] == routing_policy.CONFLICT_OF_INTEREST_CLASS_ID:
            row["refuses"] = True
    return json.dumps(document)


def _git(*args: str, cwd: Path) -> str:
    # S603/S607: fixed literals and tmp_path-derived paths, `git` off PATH on purpose —
    # the same reasoning as `tests/unit/test_land.py`'s helper.
    return subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


@pytest.fixture
def exchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Build a scratch `origin` carrying the shipped policy on `main`.

    The caller is chdir'd into its main checkout.

    `escalate` derives its routing inputs from git since #391 — the policy off fetched
    `origin/main`, the branch off `refs/heads/issue-<n>` — so every escalate test runs
    against a bare repository this fixture builds, never this box's real remote. No
    exchange ref exists yet: a test pushes `main:refs/heads/issue-<n>` (optionally past a
    commit of its own) to name the branch under review.
    """
    origin = tmp_path / "origin.git"
    _git("init", "--bare", "--initial-branch=main", str(origin), cwd=tmp_path)
    main = tmp_path / "repo"
    _git("clone", str(origin), str(main), cwd=tmp_path)
    _git("config", "user.email", "t@example.com", cwd=main)
    _git("config", "user.name", "T", cwd=main)
    (main / "config").mkdir(parents=True, exist_ok=True)
    (main / "config" / "dispatch-routing-policy.json").write_text(
        POLICY_PATH.read_text(encoding="utf-8"), encoding="utf-8"
    )
    _git("add", "config/dispatch-routing-policy.json", cwd=main)
    _git("commit", "-m", "feat: shipped routing policy", cwd=main)
    _git("push", "origin", "main", cwd=main)
    monkeypatch.chdir(main)
    return main


@pytest.fixture(autouse=True)
def default_git_transport_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default this module's Git calls away from non-file transports (#458).

    `GIT_ALLOW_PROTOCOL=file` is Git's own protocol policy: it behaves as
    `protocol.allow=never` plus `protocol.file.allow=always`, overriding Git config. Tests
    that leave the process environment intact therefore keep their scratch repositories while
    Git rejects HTTP, SSH, git and external-helper transports after resolving argv, config,
    rewrites, multiple URLs and submodule state.

    This is an accidental-network guard, not an isolation boundary: a test can unset or replace
    the environment variable, and a file remote outside `tmp_path` remains reachable. The suite
    needs file transport for its scratch topology. The walk's separate HTTP seam remains bounded
    and pinned at its CLI boundary. Fetch deadlines are owned by
    `review_loop._routing_remote_git`, and `remote_ref_sha` owns its own deadline; neither is
    inferred from Git argv here.
    """
    monkeypatch.setenv("GIT_ALLOW_PROTOCOL", "file")


def _exchange_branch(main: Path, issue: int, *commits: tuple[str, str]) -> None:
    """Push `refs/heads/issue-<n>`, the branch under review.

    At `main`, or past commits of `(path, body)` pairs staged onto it.
    """
    _git("checkout", "-b", f"issue-{issue}", cwd=main)
    for path, body in commits:
        target = main / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        _git("add", path, cwd=main)
        _git("commit", "-m", f"feat: {path}", cwd=main)
    _git("push", "origin", f"issue-{issue}:refs/heads/issue-{issue}", cwd=main)
    _git("checkout", "main", cwd=main)


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


def test_the_command_surface_drives_one_loop_end_to_end(tmp_path: Path, exchanged: Path) -> None:
    """Open, three rounds, escalate, adjudicate, terminus — one issue, all durable state real.

    The escalation reads a dispatch directory the test writes (`resolve_dispatchable`'s
    production inputs: records, scratch admission/breaker state, a key-less credentials
    file) and derives its routing inputs from the scratch origin (`exchanged`), so the
    arbiter answered here is the one the walk would answer on the box — the implementer
    seat's entry head, `codex-sol-high`, held clean by the scratch state the test points
    the rungs at.
    """
    # arbiter-rule: stated — names the profile this test asserts the walk answers (#390), over
    # inputs the test itself writes; the assertion below is what holds it true (#390).
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
    _exchange_branch(exchanged, 333)
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
    assert landing["findings"] == [
        {
            "finding": "F1",
            "severity": "critical",
            "round_raised": 0,
            "route": review_loop.ARBITER_UPHELD,
        },
        {
            "finding": "F2",
            "severity": "high",
            "round_raised": 1,
            "route": review_loop.ARBITER_DISMISSED,
        },
    ]
    assert landing["filings"] == [
        {"finding": "F1", "severity": "critical", "round_raised": 0, "issue": 401}
    ]
    assert landing["dismissals"] == [{"finding": "F2", "severity": "high", "round_raised": 1}]
    # The claim on the right to run is released once the landing record is written.
    assert not (root / "333" / review_loop.PENDING_FILE).exists()
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


def drive_to_the_wall(
    root: Path, journal: Path, *, issue: int = 326, escalated: bool = True
) -> list[str]:
    """Open at round zero and advance to the three-round wall.

    `escalated` writes the record `escalate` would have written — a firing evaluation
    naming an arbiter — because `adjudicate` now refuses an arbiter route that names no
    arbiter (#334 round 2, Medium 2) and reads the name from this record rather than from
    a flag. `escalated=False` is the arrangement of a loop nobody's resolution chose, which
    the terminus refuses on its own account.
    """
    base = ["--root", str(root), "--journal", str(journal)]
    clock = stepped_clock()
    assert (
        review_loop.main(["open", "--issue", str(issue), *base, "--finding", "F1=high"], now=clock)
        == review_loop.OK
    )
    for _ in range(3):
        assert (
            review_loop.main(["round", "--issue", str(issue), *base], now=clock) == review_loop.OK
        )
    if escalated:
        record = root / str(issue) / review_loop.ESCALATION_FILE
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(
            json.dumps(
                {"arbiter": "opus-high", "unchecked": False, "evaluation": escalation.FIRING}
            )
            + "\n",
            encoding="utf-8",
        )
    return base


def test_every_variadic_recipe_preserves_argument_boundaries() -> None:
    lines = (REPO / "justfile").read_text(encoding="utf-8").splitlines()
    headers = [index for index, line in enumerate(lines) if "*args:" in line]
    assert headers
    assert all(lines[index - 1] == "[positional-arguments]" for index in headers)
    assert all(
        "{{ args }}" not in line
        for line in lines
        if line.startswith((" ", "\t")) and not line.lstrip().startswith("#")
    )


@pytest.mark.parametrize(
    "conditional_on",
    ["correcting the stale comment", "correcting the stale comment, which no rung reads"],
)
def test_the_recipe_preserves_the_conditional_work_as_one_argument(
    tmp_path: Path, conditional_on: str
) -> None:
    root = tmp_path / "review"
    journal = tmp_path / "journal.jsonl"
    assert (
        review_loop.main(
            [
                "open",
                "--issue",
                "477",
                "--root",
                str(root),
                "--journal",
                str(journal),
                "--finding",
                "F1=medium",
            ]
        )
        == review_loop.OK
    )

    completed = subprocess.run(  # noqa: S603 — exercises the public recipe seam
        [  # noqa: S607 — `just` resolves off PATH by design
            "just",
            "review-loop",
            "adjudicate",
            "--issue",
            "477",
            "--root",
            str(root),
            "--journal",
            str(journal),
            "--finding",
            "F1",
            "--route",
            review_loop.ACCEPTED_AND_FILED,
            "--filed-issue",
            "476",
            "--conditional-on",
            conditional_on,
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    stored = json.loads((root / "477" / review_loop.LOOP_FILE).read_text(encoding="utf-8"))
    assert stored["findings"][0]["adjudication"]["conditional_on"] == conditional_on


def close_by_hand(root: Path, issue: int, finding_id: str, route: str, arbiter: str = "") -> None:
    """Write an adjudication straight into the stored loop, past every writer's gate.

    For the tests whose subject is a *later* gate's independence: the terminus refuses
    arbiter verdicts no escalation record chose, and that guard must hold against a record
    the command surface would not have written — which, since #334 round 2, is the only way
    such a record comes to exist.
    """
    loop = review_loop.load_loop(root, issue)
    review_loop.store_loop(
        root,
        issue,
        review_loop.Loop(
            loop.review_rounds,
            tuple(
                found._replace(adjudication=review_loop.Adjudication(route, "", "", arbiter))
                if found.id == finding_id
                else found
                for found in loop.findings
            ),
        ),
    )


def test_a_terminus_refuses_verdicts_no_escalation_record_chose(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Round 2's High 2: the terminus needs an escalation record.

    Verdicts no arbiter resolution chose are not dischargeable, and the missing record
    must not read as an empty arbiter that lets the landing proceed. Since #334 round 2
    the command surface refuses to *write* such a verdict, so the record is staged past
    it — which is the whole point of the guard: it holds against a loop file the writer
    would not have produced.
    """
    root = tmp_path / "review"
    base = drive_to_the_wall(root, tmp_path / "journal.jsonl", escalated=False)
    clock = stepped_clock()
    close_by_hand(root, 326, "F1", review_loop.ARBITER_DISMISSED)
    filings: list[tuple[str, str]] = []
    comments: list[tuple[int, str]] = []
    code = review_loop.main(
        ["terminus", "--issue", "326", *base],
        now=clock,
        create_issue=lambda title, body: filings.append((title, body)) or 0,
        post_comment=lambda issue, body: comments.append((issue, body)),
    )
    assert code == review_loop.REFUSED
    assert (
        review_loop.ARBITER_UNRESOLVED_ERROR.format(issue=326, root=root) in capsys.readouterr().err
    )
    assert filings == []
    assert comments == []
    assert not (root / "326" / review_loop.LANDING_FILE).exists()


def test_terminus_prompt_counts_findings_and_marks_incomplete_claims() -> None:
    """The prompt carries closeout state, not a remembered convention."""
    assert review_loop.terminus_prompt(
        553,
        review_loop.first_review((finding("F1", review_loop.LOW),)),
        pending=False,
    ) == review_loop.TerminusPrompt(issue=553, findings=1, open_above_low=0, incomplete=False)
    assert review_loop.terminus_prompt(
        554,
        review_loop.first_review((finding("F2"),)),
        pending=True,
    ) == review_loop.TerminusPrompt(issue=554, findings=1, open_above_low=1, incomplete=True)
    assert review_loop.terminus_prompt(556, review_loop.first_review(()), pending=False) == (
        review_loop.TerminusPrompt(issue=556, findings=0, open_above_low=0, incomplete=False)
    )


def test_a_non_firing_escalation_record_does_not_authorise_the_terminus(
    tmp_path: Path, exchanged: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A record that resolved a profile but fired nothing transferred to it.

    `escalate` below the wall writes its record — arbiter resolved, evaluation `no_firing`.
    The wall can still fire rounds later and `adjudicate` with it, and the round-1 terminus
    would have blessed those verdicts with a recorded arbiter name that never transferred.
    """
    root = tmp_path / "review"
    journal = tmp_path / "journal.jsonl"
    base = ["--root", str(root), "--journal", str(journal)]
    dispatch_dir = tmp_path / "dispatches"
    write_record(dispatch_dir, "d1", issue=333, profile="opus-high", seat="implementer")
    credentials = tmp_path / "credentials.env"
    credentials.write_text("# no keys the walk reads\n", encoding="utf-8")
    credentials.chmod(0o600)
    clock = stepped_clock()
    kwargs: dict[str, object] = {"now": clock}
    assert (
        review_loop.main(["open", "--issue", "326", *base, "--finding", "F1=high"], **kwargs)
        == review_loop.OK
    )
    assert review_loop.main(["round", "--issue", "326", *base], **kwargs) == review_loop.OK
    assert review_loop.main(["round", "--issue", "326", *base], **kwargs) == review_loop.OK
    _exchange_branch(exchanged, 326)
    assert (
        review_loop.main(
            [
                "escalate",
                "--issue",
                "326",
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
    record = json.loads((root / "326" / review_loop.ESCALATION_FILE).read_text(encoding="utf-8"))
    assert record["evaluation"] == escalation.NO_FIRING
    assert record["arbiter"] == "codex-sol-high"
    assert review_loop.main(["round", "--issue", "326", *base], **kwargs) == review_loop.OK
    # Staged past the writer, which since #334 round 2 fills the arbiter from a *firing*
    # record and so refuses this route here: the subject is the terminus's own refusal to
    # bless a verdict that a resolution which fired nothing would otherwise have named.
    close_by_hand(root, 326, "F1", review_loop.ARBITER_DISMISSED, arbiter="codex-sol-high")
    filings: list[tuple[str, str]] = []
    assert (
        review_loop.main(
            ["terminus", "--issue", "326", *base],
            now=clock,
            create_issue=lambda title, body: filings.append((title, body)) or 0,
            post_comment=lambda _issue, _body: None,
        )
        == review_loop.REFUSED
    )
    assert (
        review_loop.ARBITER_UNRESOLVED_ERROR.format(issue=326, root=root) in capsys.readouterr().err
    )
    assert filings == []


def test_a_terminus_that_died_mid_post_refuses_the_blind_retry(
    tmp_path: Path, exchanged: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Round 2's High 4: side effects on GitHub plus two local writes is not a transaction.

    The pending claim is what makes "once" true anyway — a run that dies mid-post leaves the
    marker naming what it was about to post, the retry refuses rather than filing twice, and
    the marker is cleared by hand once the thread is accounted (then the retry proceeds).
    Two concurrent calls are the same mechanism: `O_CREAT | O_EXCL` is decided by the kernel,
    so exactly one of them wins the create.
    """
    root = tmp_path / "review"
    journal = tmp_path / "journal.jsonl"
    dispatch_dir = tmp_path / "dispatches"
    write_record(dispatch_dir, "d1", issue=333, profile="opus-high", seat="implementer")
    credentials = tmp_path / "credentials.env"
    credentials.write_text("# no keys the walk reads\n", encoding="utf-8")
    credentials.chmod(0o600)
    base = ["--root", str(root), "--journal", str(journal)]
    clock = stepped_clock()
    assert (
        review_loop.main(["open", "--issue", "326", *base, "--finding", "F1=critical"], now=clock)
        == review_loop.OK
    )
    for _ in range(3):
        assert review_loop.main(["round", "--issue", "326", *base], now=clock) == review_loop.OK
    escalate_args = [
        "escalate",
        "--issue",
        "326",
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
    ]
    _exchange_branch(exchanged, 326)
    assert review_loop.main(escalate_args, now=clock) == review_loop.OK
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
                review_loop.ARBITER_UPHELD,
            ],
            now=clock,
        )
        == review_loop.OK
    )

    def broken(_title: str, _body: str) -> int:
        message = "`gh` refused: rate limited"
        raise review_loop.ExternalError(message)

    assert (
        review_loop.main(
            ["terminus", "--issue", "326", *base],
            now=clock,
            create_issue=broken,
            post_comment=lambda _i, _b: None,
        )
        == review_loop.NO_RESULT
    )
    pending = root / "326" / review_loop.PENDING_FILE
    assert pending.exists()
    assert json.loads(pending.read_text(encoding="utf-8"))["filings"] == ["F1"]
    assert not (root / "326" / review_loop.LANDING_FILE).exists()
    # The blind retry files nothing: the marker is the refusal, and what it names is the
    # audit trail for what a hand must account on the thread first.
    filings: list[tuple[str, str]] = []
    assert (
        review_loop.main(
            ["terminus", "--issue", "326", *base],
            now=clock,
            create_issue=lambda title, body: filings.append((title, body)) or 0,
            post_comment=lambda _issue, _body: None,
        )
        == review_loop.REFUSED
    )
    assert (
        review_loop.TERMINUS_INCOMPLETE_ERROR.format(issue=326, root=root)
        in capsys.readouterr().err
    )
    assert filings == []
    # Cleared by hand once accounted, the retry proceeds and completes its own claim.
    pending.unlink()
    assert (
        review_loop.main(
            ["terminus", "--issue", "326", *base],
            now=clock,
            create_issue=lambda title, body: filings.append((title, body)) or 401,
            post_comment=lambda _issue, _body: None,
        )
        == review_loop.OK
    )
    assert len(filings) == 1
    assert (root / "326" / review_loop.LANDING_FILE).exists()
    assert not pending.exists()


def test_the_landing_record_is_the_claim_moved_not_a_second_fact_written_beside_it(
    tmp_path: Path, exchanged: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Round 3's mutator race: a marker plus a record is two facts that can disagree.

    The old completion wrote `landing.json` under the claim and unlinked the marker after
    it — a crash between the two writes left both files, and a crash inside the first left
    a partial record that the retry's first check read as a completed terminus. The
    structural fix is one file: the claim is rewritten with the record and moved onto
    `landing.json` by a single atomic rename, so no reachable state carries both files and
    the record is never partial. Dying at the rename leaves the marker alone — the
    refusing answer, because the terminus is incomplete, not terminal.
    """
    root = tmp_path / "review"
    journal = tmp_path / "journal.jsonl"
    dispatch_dir = tmp_path / "dispatches"
    write_record(dispatch_dir, "d1", issue=333, profile="opus-high", seat="implementer")
    credentials = tmp_path / "credentials.env"
    credentials.write_text("# no keys the walk reads\n", encoding="utf-8")
    credentials.chmod(0o600)
    base = ["--root", str(root), "--journal", str(journal)]
    clock = stepped_clock()
    assert (
        review_loop.main(["open", "--issue", "326", *base, "--finding", "F1=critical"], now=clock)
        == review_loop.OK
    )
    for _ in range(3):
        assert review_loop.main(["round", "--issue", "326", *base], now=clock) == review_loop.OK
    _exchange_branch(exchanged, 326)
    assert (
        review_loop.main(
            [
                "escalate",
                "--issue",
                "326",
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
            now=clock,
        )
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
                review_loop.ARBITER_UPHELD,
            ],
            now=clock,
        )
        == review_loop.OK
    )
    pending = root / "326" / review_loop.PENDING_FILE
    landing = root / "326" / review_loop.LANDING_FILE
    filings: list[tuple[str, str]] = []
    observed: list[tuple[bool, bool]] = []

    def filing(title: str, body: str) -> int:
        # Mid-side-effect view of the durable state: the record is not there yet, the
        # claim is — the only two files that ever exist before the rename.
        observed.append((landing.exists(), pending.exists()))
        filings.append((title, body))
        return 401

    def died_at_the_rename(self: object, target: object) -> None:
        message = f"the disk died moving {self} to {target}"
        raise OSError(message)

    with pytest.MonkeyPatch.context() as patch:
        # `Path.replace` is `os.replace` underneath; patching it on the class the module
        # uses intercepts the one move the terminus makes without reaching pathlib itself.
        patch.setattr(review_loop.Path, "replace", died_at_the_rename)
        assert (
            review_loop.main(
                ["terminus", "--issue", "326", *base],
                now=clock,
                create_issue=filing,
                post_comment=lambda _i, _b: None,
            )
            == review_loop.NO_RESULT
        )
    assert observed == [(False, True)]
    assert not landing.exists()
    assert pending.exists()
    # The blind retry refuses on the marker and files nothing twice.
    assert (
        review_loop.main(
            ["terminus", "--issue", "326", *base],
            now=clock,
            create_issue=filing,
            post_comment=lambda _i, _b: None,
        )
        == review_loop.REFUSED
    )
    assert (
        review_loop.TERMINUS_INCOMPLETE_ERROR.format(issue=326, root=root)
        in capsys.readouterr().err
    )
    assert len(filings) == 1
    # Accounted and cleared by hand, the retry runs to the rename and past it: the claim
    # becomes the record, the two never coexist, and the record carries what was filed.
    pending.unlink()
    assert (
        review_loop.main(
            ["terminus", "--issue", "326", *base],
            now=clock,
            create_issue=filing,
            post_comment=lambda _i, _b: None,
        )
        == review_loop.OK
    )
    assert len(filings) == 2
    assert landing.exists()
    assert not pending.exists()
    assert json.loads(landing.read_text(encoding="utf-8"))["filings"][0]["issue"] == 401


@pytest.mark.parametrize("broken", ["[]", "null", '"codex-sol-high"', "3"])
def test_an_escalation_record_that_decodes_to_a_non_object_is_a_named_no_result(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], broken: str
) -> None:
    """Round 3's untyped traceback: `.get` on a record that is not an object.

    A list, a bare string, a null and a number all decode as JSON but carry no arbiter,
    and the old read raised `AttributeError` out of `main` — the one failure in this
    module with no name. Exists-but-not-an-object is the same answer as
    exists-but-unreadable: an unperformable read, exit 3, never a silent empty arbiter.
    """
    root = tmp_path / "review"
    base = drive_to_the_wall(root, tmp_path / "journal.jsonl")
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
            now=stepped_clock(),
        )
        == review_loop.OK
    )
    (root / "326" / review_loop.ESCALATION_FILE).write_text(broken + "\n", encoding="utf-8")
    filings: list[tuple[str, str]] = []
    assert (
        review_loop.main(
            ["terminus", "--issue", "326", *base],
            now=stepped_clock(),
            create_issue=lambda title, body: filings.append((title, body)) or 1,
            post_comment=lambda _issue, _body: None,
        )
        == review_loop.NO_RESULT
    )
    assert "the escalation record for #326 exists but is not an object" in capsys.readouterr().err
    assert filings == []


def absent(field: str) -> str:
    return review_loop.ESCALATION_FIELD_ABSENT_ERROR.format(issue=326, field=field)


def wrong(field: str, value: object, expected: str) -> str:
    return review_loop.ESCALATION_FIELD_TYPE_ERROR.format(
        issue=326, field=field, value=repr(value), expected=expected
    )


@pytest.mark.parametrize(
    ("record", "message"),
    [
        # The arbiter's own four, reproduced against the fixed read. Each coerced to a
        # truthy arbiter and a boolean `unchecked` under the old `str()`/`bool()` read,
        # and each opened the gate.
        (
            {"arbiter": ["opus-high"], "unchecked": "false", "evaluation": escalation.FIRING},
            wrong("arbiter", ["opus-high"], "a string"),
        ),
        (
            # `str(None)` is "None", which is truthy: a record naming no arbiter at all
            # authorised the terminus, and the landing record then carried "arbiter":
            # "None" for a post-landing reader to mistake for an absence marker.
            {"arbiter": None, "unchecked": None, "evaluation": escalation.FIRING},
            wrong("arbiter", None, "a string"),
        ),
        (
            {"arbiter": 0, "unchecked": 1, "evaluation": escalation.FIRING},
            wrong("arbiter", 0, "a string"),
        ),
        (
            # The unsafe direction of the `unchecked` bug: absent defaulted to False, so a
            # record that never said whether the resolution was checked read as checked.
            {"arbiter": "opus-high", "evaluation": escalation.FIRING},
            absent("unchecked"),
        ),
        (
            # The reported case, and the safe direction of the same bug.
            {"arbiter": "opus-high", "unchecked": "false", "evaluation": escalation.FIRING},
            wrong("unchecked", "false", "a boolean"),
        ),
        (
            # `isinstance(True, int)` is true and the converse is not, so a bool checked as
            # itself refuses 1 — an int check would have read it as unchecked.
            {"arbiter": "opus-high", "unchecked": 1, "evaluation": escalation.FIRING},
            wrong("unchecked", 1, "a boolean"),
        ),
        ({"unchecked": False, "evaluation": escalation.FIRING}, absent("arbiter")),
        ({"arbiter": "opus-high", "unchecked": False}, absent("evaluation")),
        (
            {"arbiter": "opus-high", "unchecked": False, "evaluation": 3},
            wrong("evaluation", 3, "a string"),
        ),
    ],
)
def test_a_malformed_escalation_record_never_authorises_the_terminus(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    record: dict[str, object],
    message: str,
) -> None:
    """The arbiter's ruling on #333: validate the authorising record, never coerce it.

    `_recorded_arbiter` read the three fields through `str()`/`bool()` over `.get`
    defaults, and there was no malformed `arbiter` it rejected — every value of the
    deciding field was truthy, `None` included. The gate is put in the position of
    *opening*: the finding is adjudicated `arbiter_upheld`, so `end.filings` is non-empty
    and a good record here would file an issue and write the landing record. Each
    malformed record must instead be an unperformable read — exit 3, the field and its
    value named so the file can be repaired — with nothing filed, nothing posted, no
    claim, and no landing record.
    """
    root = tmp_path / "review"
    base = drive_to_the_wall(root, tmp_path / "journal.jsonl")
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
                review_loop.ARBITER_UPHELD,
            ],
            now=stepped_clock(),
        )
        == review_loop.OK
    )
    (root / "326" / review_loop.ESCALATION_FILE).write_text(
        json.dumps(record) + "\n", encoding="utf-8"
    )
    filings: list[tuple[str, str]] = []
    comments: list[tuple[int, str]] = []
    assert (
        review_loop.main(
            ["terminus", "--issue", "326", *base],
            now=stepped_clock(),
            create_issue=lambda title, body: filings.append((title, body)) or 1,
            post_comment=lambda issue, body: comments.append((issue, body)),
        )
        == review_loop.NO_RESULT
    )
    assert message in capsys.readouterr().err
    assert filings == []
    assert comments == []
    assert not (root / "326" / review_loop.LANDING_FILE).exists()
    assert not (root / "326" / review_loop.PENDING_FILE).exists()


def test_a_well_formed_escalation_record_still_opens_the_gate(tmp_path: Path) -> None:
    """The validation's other side: the shape `escalate` writes is not refused.

    Without this, every test above passes on a read that refuses everything — the
    parametrised cases prove the gate closes, and only this one proves it still opens on
    the exact record production emits.
    """
    root = tmp_path / "review"
    base = drive_to_the_wall(root, tmp_path / "journal.jsonl")
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
                review_loop.ARBITER_UPHELD,
            ],
            now=stepped_clock(),
        )
        == review_loop.OK
    )
    (root / "326" / review_loop.ESCALATION_FILE).write_text(
        json.dumps({"arbiter": "opus-high", "unchecked": False, "evaluation": escalation.FIRING})
        + "\n",
        encoding="utf-8",
    )
    filings: list[tuple[str, str]] = []
    assert (
        review_loop.main(
            ["terminus", "--issue", "326", *base],
            now=stepped_clock(),
            create_issue=lambda title, body: filings.append((title, body)) or 402,
            post_comment=lambda _issue, _body: None,
        )
        == review_loop.OK
    )
    assert len(filings) == 1
    landing = json.loads((root / "326" / review_loop.LANDING_FILE).read_text(encoding="utf-8"))
    assert landing["arbiter"] == "opus-high"
    assert landing["arbiter_unchecked"] is False


def test_a_completed_terminus_refuses_a_second_run_without_side_effects(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The once rule is exercised through the public command, including its guard."""
    root = tmp_path / "review"
    base = ["--root", str(root), "--journal", str(tmp_path / "journal.jsonl")]
    clock = stepped_clock()
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
        )
        == review_loop.OK
    )
    assert review_loop.main(["terminus", "--issue", "326", *base], now=clock) == review_loop.OK
    landing = root / "326" / review_loop.LANDING_FILE
    before = landing.read_text(encoding="utf-8")
    calls: list[str] = []
    assert (
        review_loop.main(
            ["terminus", "--issue", "326", *base],
            now=clock,
            create_issue=lambda title, _body: calls.append(title) or 999,
            post_comment=lambda _issue, _body: calls.append("comment"),
        )
        == review_loop.REFUSED
    )
    assert (
        review_loop.ALREADY_TERMINATED_ERROR.format(issue=326, root=root) in capsys.readouterr().err
    )
    assert calls == []
    assert landing.read_text(encoding="utf-8") == before


def test_the_landing_record_carries_every_findings_verdict(tmp_path: Path) -> None:
    """Round 2's High 3: the landing record must say every finding's verdict.

    `fixed` has no trace but the diff, and a Low left open at the terminus is a
    fact the record must be able to say — post-landing review reads the
    per-finding verdicts here, not the diff.
    """
    root = tmp_path / "review"
    base = drive_to_the_wall(root, tmp_path / "journal.jsonl", issue=328)
    clock = stepped_clock()
    assert (
        review_loop.main(
            [
                "adjudicate",
                "--issue",
                "328",
                *base,
                "--finding",
                "F1",
                "--route",
                review_loop.FIXED,
            ],
            now=clock,
        )
        == review_loop.OK
    )
    assert (
        review_loop.main(
            [
                "round",
                "--issue",
                "328",
                *base,
                "--finding",
                "F2=low",
            ],
            now=clock,
        )
        == review_loop.OK
    )
    assert (
        review_loop.main(
            [
                "adjudicate",
                "--issue",
                "328",
                *base,
                "--finding",
                "F2",
                "--route",
                review_loop.ACCEPTED_AND_FILED,
                "--filed-issue",
                "#376",
                "--conditional-on",
                "work X widens the input",
            ],
            now=clock,
        )
        == review_loop.OK
    )
    assert (
        review_loop.main(
            ["terminus", "--issue", "328", *base],
            now=clock,
            create_issue=lambda _title, _body: 0,
            post_comment=lambda _issue, _body: None,
        )
        == review_loop.OK
    )
    landing = json.loads((root / "328" / review_loop.LANDING_FILE).read_text(encoding="utf-8"))
    assert landing["findings"] == [
        {
            "finding": "F1",
            "severity": "high",
            "round_raised": 0,
            "route": review_loop.FIXED,
        },
        {
            "finding": "F2",
            "severity": "low",
            "round_raised": 4,
            "route": review_loop.ACCEPTED_AND_FILED,
            "issue": "#376",
            "conditional_on": "work X widens the input",
        },
    ]


def test_a_stored_loop_that_will_not_decode_is_a_named_refusal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Round 2's Medium 6: an unreadable loop is a named refusal.

    A truncated `loop.json` is a state the tool looked at and refused, never an
    unclassified traceback on the command surface.
    """
    root = tmp_path / "review"
    base = ["--root", str(root), "--journal", str(tmp_path / "journal.jsonl")]
    assert (
        review_loop.main(
            ["open", "--issue", "326", *base, "--finding", "F1=high"], now=stepped_clock()
        )
        == review_loop.OK
    )
    (root / "326" / review_loop.LOOP_FILE).write_text('{"version": 1, "iss', encoding="utf-8")
    assert (
        review_loop.main(["show", "--issue", "326", "--root", str(root)], now=stepped_clock())
        == review_loop.REFUSED
    )
    err = capsys.readouterr().err
    assert f"the stored loop for #326 under {root} will not read —" in err
    assert "Traceback" not in err  # a refusal line, never an unclassified traceback


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


def test_escalate_derives_its_routing_inputs_and_passes_the_refused_head_over(
    tmp_path: Path, exchanged: Path
) -> None:
    """#391: the walk reads the policy and the branch itself — no caller flag to forget.

    Class 6 planted back to refusing on the scratch origin's `main`, the branch under
    review touching a gate path: the entry head (`codex-sol-high`, codex lane) is passed
    over `routing_refused` and the tail (`opus-high`, the lane the row exempts) resolves.
    Against the shipped policy this same command resolves the head — the inert
    arrangement the end-to-end test above already carries — so this is the rung biting on
    inputs the command derived, which is the whole of what #391 asked for.
    """
    policy = exchanged / "config" / "dispatch-routing-policy.json"
    policy.write_text(_refusing_policy_text(), encoding="utf-8")
    _git("add", "config/dispatch-routing-policy.json", cwd=exchanged)
    _git("commit", "-m", "feat: class 6 refuses again", cwd=exchanged)
    _git("push", "origin", "main", cwd=exchanged)
    _exchange_branch(exchanged, 391, ("tools/dispatch.py", "# a gate path\n"))

    root = tmp_path / "review"
    journal = tmp_path / "journal.jsonl"
    dispatch_dir = tmp_path / "dispatches"
    write_record(dispatch_dir, "d1", issue=391, profile="opus-low", seat="implementer")
    credentials = tmp_path / "credentials.env"
    credentials.write_text("# no keys the walk reads\n", encoding="utf-8")
    credentials.chmod(0o600)
    base = ["--root", str(root), "--journal", str(journal)]
    clock = stepped_clock()
    assert (
        review_loop.main(["open", "--issue", "391", *base, "--finding", "F1=high"], now=clock)
        == review_loop.OK
    )
    assert (
        review_loop.main(
            [
                "escalate",
                "--issue",
                "391",
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
            now=clock,
        )
        == review_loop.OK
    )
    record = json.loads((root / "391" / review_loop.ESCALATION_FILE).read_text(encoding="utf-8"))
    assert record["arbiter"] == "opus-high"
    events = [
        json.loads(line)
        for line in journal.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    resolutions = [e for e in events if e["event"] == "cti.review.arbiter.resolved"]
    assert resolutions, "the resolution event is the rung's durable trace"
    attributes = resolutions[-1]["attributes"]
    assert attributes["cti.review.arbiter"] == "opus-high"
    assert "codex-sol-high:routing_refused" in attributes["cti.review.arbiter.excluded"]


def test_escalate_without_an_exchange_ref_refuses_rather_than_skipping_the_rung(
    tmp_path: Path, exchanged: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """No `refs/heads/issue-<n>` on the origin: a named refusal, nothing written.

    The rung that reads the branch cannot run, and a check that could not run is not a
    check that passed (#41) — the escalation refuses by name rather than resolving past a
    rung whose input is absent, and no escalation record exists to adjudicate against.
    """
    root = tmp_path / "review"
    base = ["--root", str(root), "--journal", str(tmp_path / "journal.jsonl")]
    clock = stepped_clock()
    assert (
        review_loop.main(["open", "--issue", "326", *base, "--finding", "F1=high"], now=clock)
        == review_loop.OK
    )
    # The fixture built the origin; nothing pushed `issue-326` onto it — stated as the
    # ground it is, not left as a comment.
    assert _git("ls-remote", "--heads", "origin", "refs/heads/issue-326", cwd=exchanged) == ""
    assert (
        review_loop.main(["escalate", "--issue", "326", *base, "--seat", "implementer"], now=clock)
        == review_loop.REFUSED
    )
    assert (
        review_loop.EXCHANGE_REF_ABSENT_ERROR.format(ref="refs/heads/issue-326")
        in capsys.readouterr().err
    )
    assert not (root / "326" / review_loop.ESCALATION_FILE).exists()


def test_escalate_outside_a_repository_refuses_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Refuse by name when run from a directory git does not know.

    Never resolved past the unreadable rung.
    """
    root = tmp_path / "review"
    base = ["--root", str(root), "--journal", str(tmp_path / "journal.jsonl")]
    clock = stepped_clock()
    assert (
        review_loop.main(["open", "--issue", "326", *base, "--finding", "F1=high"], now=clock)
        == review_loop.OK
    )
    (tmp_path / "nowhere").mkdir()
    monkeypatch.chdir(tmp_path / "nowhere")
    assert (
        review_loop.main(["escalate", "--issue", "326", *base, "--seat", "implementer"], now=clock)
        == review_loop.REFUSED
    )
    assert review_loop.NOT_A_REPOSITORY_ERROR in capsys.readouterr().err
    assert not (root / "326" / review_loop.ESCALATION_FILE).exists()


NON_FILE_REMOTE: Final = "https://127.0.0.1:9/never.git"


def test_routing_remote_git_owns_the_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The timeout remains structural after the argv parser that checked it is removed."""
    calls: list[tuple[tuple[str, ...], Path, bool, float | None]] = []

    def git_call(*args: str, cwd: Path, check: bool = True, timeout: float | None = None) -> str:
        calls.append((args, cwd, check, timeout))
        return "read"

    monkeypatch.setattr(review_loop, "git", git_call)

    assert (
        review_loop._routing_remote_git(  # noqa: SLF001 — deadline boundary is the subject
            "fetch", "origin", "main", cwd=tmp_path
        )
        == "read"
    )
    assert calls == [
        (("fetch", "origin", "main"), tmp_path, True, review_loop.ROUTING_READ_TIMEOUT_S)
    ]


def _assert_git_denies_transport(repo: Path, *args: str) -> None:
    """Assert Git's protocol policy, not a test-side destination model, refused one call."""
    with pytest.raises(review_loop.GitError) as failure:
        review_loop.git(*args, cwd=repo, timeout=review_loop.ROUTING_READ_TIMEOUT_S)
    assert "transport 'https' not allowed" in failure.value.stderr


def test_git_denies_a_destination_selected_by_an_instead_of_rewrite(exchanged: Path) -> None:
    """Git resolves a URL rewrite hidden behind a token, then its protocol policy refuses it."""
    _assert_git_denies_transport(
        exchanged,
        "-c",
        "protocol.https.allow=always",
        "-c",
        f"url.{NON_FILE_REMOTE.rpartition('/')[0]}/.insteadOf=guarded:",
        "fetch",
        "guarded:never.git",
    )


def test_git_denies_push_repo_without_a_repository_operand(exchanged: Path) -> None:
    """`push --repo=<url>` has no repository operand for a test-side parser to find (#458)."""
    _assert_git_denies_transport(exchanged, "push", f"--repo={NON_FILE_REMOTE}", "--all")


def test_git_denies_every_remote_selected_by_fetch_multiple(exchanged: Path) -> None:
    """Git, not a first-token approximation, selects both named remotes (#458)."""
    _git("remote", "add", "preserved", NON_FILE_REMOTE, cwd=exchanged)
    _assert_git_denies_transport(exchanged, "fetch", "--multiple", "origin", "preserved")


@pytest.mark.parametrize("key", ["url", "pushurl"])
def test_git_denies_a_non_file_value_among_multiple_push_urls(exchanged: Path, key: str) -> None:
    """Git applies its policy to each URL selected from a multi-valued remote key (#458)."""
    scratch = _git("remote", "get-url", "origin", cwd=exchanged).strip()
    _git("remote", "add", "preserved", scratch, cwd=exchanged)
    if key == "pushurl":
        _git("config", "--add", "remote.preserved.pushurl", scratch, cwd=exchanged)
    _git("config", "--add", f"remote.preserved.{key}", NON_FILE_REMOTE, cwd=exchanged)
    _assert_git_denies_transport(exchanged, "push", "preserved", "--all")


def test_git_denies_an_initialised_submodules_configured_url(exchanged: Path) -> None:
    """Git reads an initialised submodule's live config, then refuses its transport (#458)."""
    scratch = _git("remote", "get-url", "origin", cwd=exchanged).strip()
    _git("submodule", "add", "--name", "preserved", scratch, "preserved", cwd=exchanged)
    _git("config", "submodule.preserved.url", NON_FILE_REMOTE, cwd=exchanged)
    shutil.rmtree(exchanged / "preserved")
    shutil.rmtree(exchanged / ".git" / "modules" / "preserved")
    _assert_git_denies_transport(exchanged, "submodule", "update", "--init", "preserved")


def test_git_protocol_policy_allows_the_local_scratch_remote(exchanged: Path) -> None:
    """The file protocol remains available for the scratch topology used by `escalate`."""
    review_loop.git(
        "fetch", "origin", "main", cwd=exchanged, timeout=review_loop.ROUTING_READ_TIMEOUT_S
    )


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
    assert not (root / "326" / review_loop.PENDING_FILE).exists()  # a dry run claims nothing


# ------------------------------------------------- the fold from the verdict (#334)


SYNC_SHA: Final = "c" * 40


def stage_verdict(
    tmp_path: Path, *, issue: int = 334, findings: tuple[tuple[str, str], ...] = (("F1", "high"),)
) -> Path:
    """One dispatch root carrying a bound, completed review and its verdict for `SYNC_SHA`."""
    dispatch_root = tmp_path / "dispatches"
    record = dispatch_root / "d-review-1"
    record.mkdir(parents=True, exist_ok=True)
    (record / "dispatch.json").write_text(
        json.dumps(
            {
                "seat": "review",
                "issue": issue,
                "base_sha": SYNC_SHA,
                "profile": "codex-luna-max",
                "lane": "codex",
                "planned_at": "20260815T0000Z",
                "dispatch_id": "d-review-1",
            }
        ),
        encoding="utf-8",
    )
    (record / "result.json").write_text(
        json.dumps({"returncode": 0, "outcome": "ok", "ended_at": "20260815T0000Z"}),
        encoding="utf-8",
    )
    (record / "verdict.json").write_text(
        json.dumps(
            {
                "version": 1,
                "issue": issue,
                "reviewed_sha": SYNC_SHA,
                "diff_id": "d" * 64,
                "review_dispatch": "d-review-1",
                "reviewer_profile": "codex-luna-max",
                "reviewer_lane": "codex",
                "findings": [{"id": name, "severity": sev} for name, sev in findings],
                "recorded_at": "20260815T0000Z",
                "alternates": [],
            }
        ),
        encoding="utf-8",
    )
    return dispatch_root


def sync_args(root: Path, journal: Path, dispatch_root: Path, issue: int = 334) -> list[str]:
    return [
        "sync",
        "--issue",
        str(issue),
        "--root",
        str(root),
        "--journal",
        str(journal),
        "--reviewed-sha",
        SYNC_SHA,
        "--dispatch-dir",
        str(dispatch_root),
    ]


def test_sync_opens_the_loop_from_the_verdicts_own_severities(tmp_path: Path) -> None:
    """The severities are the reviewer's: the fold copies the record, never a flag.

    The distinction from `open`, whose `--finding id=severity` a caller types: the seat
    under review cannot re-grade its own review on the way into the record the landing
    reads.
    """
    root = tmp_path / "review"
    dispatch_root = stage_verdict(tmp_path, findings=(("F1", "high"), ("F2", "low")))

    assert (
        review_loop.main(sync_args(root, tmp_path / "journal.jsonl", dispatch_root))
        == review_loop.OK
    )

    loop = review_loop.load_loop(root, 334)
    assert [(f.id, f.severity, f.round_raised) for f in loop.findings] == [
        ("F1", "high", 0),
        ("F2", "low", 0),
    ]
    assert loop.review_rounds == 0


def test_sync_records_a_round_for_the_ids_the_loop_does_not_hold(tmp_path: Path) -> None:
    """A later verdict's new findings are the next round, stamped by `next_round` itself."""
    root = tmp_path / "review"
    journal = tmp_path / "journal.jsonl"
    dispatch_root = stage_verdict(tmp_path)
    assert review_loop.main(sync_args(root, journal, dispatch_root)) == review_loop.OK
    stage_verdict(tmp_path, findings=(("F1", "high"), ("F2", "medium")))

    assert review_loop.main(sync_args(root, journal, dispatch_root)) == review_loop.OK

    loop = review_loop.load_loop(root, 334)
    assert loop.review_rounds == 1
    assert [(f.id, f.round_raised) for f in loop.findings] == [("F1", 0), ("F2", 1)]


def test_sync_is_a_no_op_where_the_verdict_raises_nothing_new(tmp_path: Path) -> None:
    root = tmp_path / "review"
    journal = tmp_path / "journal.jsonl"
    dispatch_root = stage_verdict(tmp_path)
    assert review_loop.main(sync_args(root, journal, dispatch_root)) == review_loop.OK

    assert review_loop.main(sync_args(root, journal, dispatch_root)) == review_loop.OK

    assert review_loop.load_loop(root, 334).review_rounds == 0


def test_sync_refuses_a_verdict_that_regrades_a_finding_the_loop_holds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """#334 round 2, Medium 3: the drift is named by the tool that reads both records.

    The fold used to report `loop_unchanged` — a success — over the exact disagreement the
    landing then refuses `review_finding_mismatch` on, with a remedy no command performed:
    the fold had declined it, `next_round` refuses a duplicate id by rule, and the landing
    was wedged short of hand-editing the record the refusal says not to hand-edit.
    """
    root = tmp_path / "review"
    journal = tmp_path / "journal.jsonl"
    dispatch_root = stage_verdict(tmp_path)
    assert review_loop.main(sync_args(root, journal, dispatch_root)) == review_loop.OK
    stage_verdict(tmp_path, findings=(("F1", "critical"),))

    assert review_loop.main(sync_args(root, journal, dispatch_root)) == review_loop.REFUSED

    assert "F1 loop=high verdict=critical" in capsys.readouterr().err
    assert review_loop.load_loop(root, 334).findings[0].severity == "high"


def test_sync_refuses_a_verdict_bound_to_another_commit(tmp_path: Path) -> None:
    """The loop is opened from the verdict the landing will read, or from nothing."""
    root = tmp_path / "review"
    dispatch_root = stage_verdict(tmp_path)
    argv = sync_args(root, tmp_path / "journal.jsonl", dispatch_root)
    argv[argv.index("--reviewed-sha") + 1] = "d" * 40

    assert review_loop.main(argv) == review_loop.REFUSED

    assert not review_loop.loop_path(root, 334).exists()


# ------------------------------------------------- the arbiter a route has to name (#334)


def test_an_arbiter_route_is_refused_without_an_arbiter() -> None:
    """The route stands in for a ruling, so the record names the judge that gave it."""
    loop = review_loop.Loop(3, (finding("F1", review_loop.HIGH, round_raised=1),))
    for route in (review_loop.ARBITER_UPHELD, review_loop.ARBITER_DISMISSED):
        assert (
            refused(
                lambda route=route: review_loop.adjudicate(loop, "F1", adjud(route, arbiter=""))
            )
            == review_loop.ARBITER_UNNAMED_ERROR
        )


def test_the_writer_takes_the_arbiter_from_the_record_and_not_from_a_flag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--arbiter` does not exist: the name written is the one `escalate` resolved.

    Both directions in one arrangement — at the wall with no firing record the route is
    refused, and with the record `escalate` writes the same command closes the finding and
    the name lands on the record a lander quotes.
    """
    root = tmp_path / "review"
    journal = tmp_path / "journal.jsonl"
    base = drive_to_the_wall(root, journal, escalated=False)
    close = ["adjudicate", "--issue", "326", *base, "--finding", "F1", "--route"]

    assert review_loop.main([*close, review_loop.ARBITER_UPHELD]) == review_loop.REFUSED
    assert review_loop.ARBITER_UNNAMED_ERROR in capsys.readouterr().err

    (root / "326" / review_loop.ESCALATION_FILE).write_text(
        json.dumps({"arbiter": "opus-high", "unchecked": False, "evaluation": escalation.FIRING})
        + "\n",
        encoding="utf-8",
    )
    assert review_loop.main([*close, review_loop.ARBITER_UPHELD]) == review_loop.OK
    assert review_loop.load_loop(root, 326).findings[0].adjudication.arbiter == "opus-high"


# ------------------------------------------------- the store, guarded and atomic (#334)


def test_an_unwritable_review_root_is_a_named_refusal_not_a_traceback(tmp_path: Path) -> None:
    """Round 2, Medium 4: the write sits inside the failure boundary, as the verdict's does."""
    root = tmp_path / "review"
    root.mkdir()
    root.chmod(0o500)
    try:
        message = refused(
            lambda: review_loop.store_loop(root, 334, review_loop.first_review((finding("F1"),)))
        )
    finally:
        root.chmod(0o700)

    assert "could not be written" in message


def test_a_failed_store_leaves_the_loop_as_it_stood(tmp_path: Path) -> None:
    """Atomic: a reader sees the old loop or the new one, never a truncated one."""
    root = tmp_path / "review"
    first = review_loop.first_review((finding("F1", review_loop.HIGH),))
    review_loop.store_loop(root, 334, first)
    before = review_loop.loop_path(root, 334).read_text(encoding="utf-8")
    (root / "334").chmod(0o500)
    try:
        with pytest.raises(review_loop.ReviewLoopError):
            review_loop.store_loop(root, 334, review_loop.next_round(first, ()))
    finally:
        (root / "334").chmod(0o700)

    assert review_loop.loop_path(root, 334).read_text(encoding="utf-8") == before
    assert list((root / "334").iterdir()) == [review_loop.loop_path(root, 334)]


# ------------------------------------------------- the self-review record (#589, ADR-0079)


def self_finding(
    identifier: str,
    category: str = review_loop.WORTH_ADDRESSING,
    origin: str = review_loop.PRE_EXISTING,
    round_raised: int = 1,
) -> review_loop.SelfReviewFinding:
    return review_loop.SelfReviewFinding(identifier, category, origin, "a reason", round_raised)


def test_a_round_is_recorded_and_reads_back() -> None:
    """Category, reason and origin ride the finding; the round reads back what was written."""
    record = review_loop.self_review_round(review_loop.SelfReview(), (self_finding("S1"),))
    attempt = record.rounds[0]
    assert attempt.number == 1
    assert attempt.findings[0].category == review_loop.WORTH_ADDRESSING
    assert attempt.findings[0].origin == review_loop.PRE_EXISTING
    assert attempt.findings[0].reason == "a reason"
    assert attempt.refutations == ()


def test_a_refutation_is_recorded_with_evidence_and_is_not_a_finding() -> None:
    """A disproved candidate carries its evidence and is never counted as a finding."""
    record = review_loop.self_review_round(
        review_loop.SelfReview(),
        (),
        (review_loop.SelfReviewRefutation("R1", "the evidence that refuted it", 1),),
    )
    attempt = record.rounds[0]
    assert attempt.findings == ()
    assert attempt.refutations[0].reason == "the evidence that refuted it"
    assert review_loop.self_review_clean(attempt) is True


def test_a_round_of_only_dismissals_is_clean() -> None:
    """A round raising no worth-addressing finding is clean; dismissals never block."""
    record = review_loop.self_review_round(
        review_loop.SelfReview(), (self_finding("D1", review_loop.NOT_WORTH_ADDRESSING),)
    )
    assert review_loop.self_review_clean(record.rounds[0]) is True
    worth = review_loop.self_review_round(review_loop.SelfReview(), (self_finding("W1"),))
    assert review_loop.self_review_clean(worth.rounds[0]) is False


def test_convergence_names_its_commit_and_adds_a_gate_fix_with_reason() -> None:
    """The record covers the commit it converged on, plus a gate-only commit with a reason."""
    record = review_loop.self_review_round(review_loop.SelfReview(), ())
    record = review_loop.self_review_converge(record, "a" * 40)
    assert record.converged_on == "a" * 40
    record = review_loop.self_review_add_gate_fix(record, "b" * 40, "confined to the gate")
    assert review_loop.self_review_covers(record, "a" * 40)
    assert review_loop.self_review_covers(record, "b" * 40) is True
    assert review_loop.self_review_covers(record, "c" * 40) is False


def test_gate_fix_refusals_are_typed() -> None:
    """A gate-fix commit joins a converged record only, and always with sha and reason."""
    record = review_loop.SelfReview()
    assert (
        refused(lambda: review_loop.self_review_add_gate_fix(record, "b" * 40, "gate fix"))
        == review_loop.SELF_REVIEW_NOT_CONVERGED_ERROR
    )
    converged = review_loop.self_review_converge(
        review_loop.self_review_round(review_loop.SelfReview(), ()), "a" * 40
    )
    assert (
        refused(lambda: review_loop.self_review_add_gate_fix(converged, "b" * 40, ""))
        == review_loop.SELF_REVIEW_REASON_ERROR
    )
    assert (
        refused(lambda: review_loop.self_review_add_gate_fix(converged, "", "reason"))
        == review_loop.SELF_REVIEW_COMMIT_ERROR
    )


def test_five_cleanless_rounds_fail_typed_from_the_fifth_round() -> None:
    """Five rounds, none clean, is a failure typed from what the fifth round raised."""

    def typed_from(fifth: tuple[review_loop.SelfReviewFinding, ...]) -> str:
        record = review_loop.SelfReview()
        for number in range(1, 6):
            findings = (
                fifth
                if number == 5
                else (
                    self_finding(
                        f"F{number}", review_loop.WORTH_ADDRESSING, review_loop.INTRODUCED, number
                    ),
                )
            )
            record = review_loop.self_review_round(record, findings)
        return review_loop.self_review_fail(record).failure

    assert (
        typed_from((self_finding("P5", review_loop.WORTH_ADDRESSING, review_loop.PRE_EXISTING, 5),))
        == review_loop.DISCOVERY_DOMINATED
    )
    assert (
        typed_from((self_finding("I5", review_loop.WORTH_ADDRESSING, review_loop.INTRODUCED, 5),))
        == review_loop.INJECTION_DOMINATED
    )


def test_failure_needs_the_budget_and_no_clean_round() -> None:
    """`self_review_fail` is refused short of the budget or where a clean round exists."""
    empty = review_loop.SelfReview()
    assert (
        refused(lambda: review_loop.self_review_fail(empty))
        == review_loop.SELF_REVIEW_FAILURE_BUDGET_ERROR
    )
    clean = review_loop.self_review_round(review_loop.SelfReview(), ())
    assert (
        refused(lambda: review_loop.self_review_fail(clean))
        == review_loop.SELF_REVIEW_FAILURE_BUDGET_ERROR
    )


def test_per_round_counts_by_origin_are_derivable() -> None:
    """The retro's per-round origin split reads off the record as counts, no re-read."""
    record = review_loop.SelfReview()
    first = (
        self_finding("P1", review_loop.WORTH_ADDRESSING, review_loop.PRE_EXISTING),
        self_finding("I1", review_loop.WORTH_ADDRESSING, review_loop.INTRODUCED),
    )
    second = (self_finding("P2", review_loop.WORTH_ADDRESSING, review_loop.PRE_EXISTING, 2),)
    record = review_loop.self_review_round(record, first)
    record = review_loop.self_review_round(record, second)
    counts = review_loop.self_review_origin_counts(record)
    assert counts[0] == {"pre_existing": 1, "introduced": 1}
    assert counts[1] == {"pre_existing": 1, "introduced": 0}


def test_the_self_review_block_never_disturbs_the_independent_loop() -> None:
    """The trap: two loops, one file — the block reads, writes and disturbs neither field."""
    finding_value = review_loop.Finding("F1", review_loop.HIGH, 0)
    loop = review_loop.first_review((finding_value,))
    record = review_loop.self_review_round(review_loop.SelfReview(), ())
    record = review_loop.self_review_converge(record, "a" * 40)
    carried = loop._replace(self_review=record)
    stored = json.loads(json.dumps(review_loop.render_loop(589, carried)))
    parsed = review_loop.parse_loop(stored)
    assert parsed.review_rounds == 0
    assert parsed.findings == (review_loop.Finding("F1", review_loop.HIGH, 0),)
    assert parsed.self_review is not None
    assert parsed.self_review.converged_on == "a" * 40
    assert parsed.independent_opened is True


def test_the_independent_loop_advances_without_disturbing_the_block() -> None:
    """`next_round` on a loop carrying a record leaves the record exactly as it stood."""
    record = review_loop.self_review_round(review_loop.SelfReview(), ())
    record = review_loop.self_review_converge(record, "a" * 40)
    loop = review_loop.first_review((review_loop.Finding("F1", review_loop.HIGH, 0),))
    loop = review_loop.next_round(loop, (review_loop.Finding("F2", review_loop.HIGH, 1),))
    carried = loop._replace(self_review=record)
    stored = json.loads(json.dumps(review_loop.render_loop(589, carried)))
    parsed = review_loop.parse_loop(stored)
    assert parsed.review_rounds == 1
    assert parsed.findings == (
        review_loop.Finding("F1", review_loop.HIGH, 0),
        review_loop.Finding("F2", review_loop.HIGH, 1),
    )
    assert parsed.self_review is not None
    assert parsed.self_review.converged_on == "a" * 40
    assert parsed.self_review.rounds[0].number == 1
    assert parsed.independent_opened is True


def test_the_schema_version_is_incremented_and_v1_reads_as_no_record() -> None:
    """A v1 document parses as carrying no record; v2 may carry one (#589's version rule)."""
    v1 = {
        "version": 1,
        "issue": 1,
        "review_rounds": 0,
        "findings": [],
        "self_review": {"rounds": []},
    }
    assert review_loop.parse_loop(v1).self_review is None


def test_self_review_verbs_write_through_the_cli(tmp_path: Path) -> None:
    """The four verbs drive the block through `main`, refusing typed and non-zero."""
    root = str(tmp_path / "review")
    journal = str(tmp_path / "journal.jsonl")
    assert (
        review_loop.main(["open", "--issue", "589", "--root", root, "--journal", journal])
        == review_loop.OK
    )
    assert (
        review_loop.main(
            [
                "self-round",
                "--issue",
                "589",
                "--root",
                root,
                "--finding",
                "S1=worth_addressing=pre_existing=the reason",
                "--refuted",
                "R1=the evidence",
            ]
        )
        == review_loop.OK
    )
    assert (
        review_loop.main(
            [
                "self-round",
                "--issue",
                "589",
                "--root",
                root,
                "--finding",
                "D1=not_worth_addressing=pre_existing=a dismissal",
            ]
        )
        == review_loop.OK
    )
    assert (
        review_loop.main(["self-converge", "--issue", "589", "--root", root, "--sha", "a" * 40])
        == review_loop.OK
    )
    assert (
        review_loop.main(
            [
                "self-gate-fix",
                "--issue",
                "589",
                "--root",
                root,
                "--sha",
                "b" * 40,
                "--reason",
                "confined to the gate",
            ]
        )
        == review_loop.OK
    )
    stored = json.loads(
        (tmp_path / "review" / "589" / review_loop.LOOP_FILE).read_text(encoding="utf-8")
    )
    assert stored["self_review"]["gate_fixes"] == [
        {"sha": "b" * 40, "reason": "confined to the gate"}
    ]
    # A record that has ended takes no further rounds: typed, exit 1.
    assert review_loop.main(["self-round", "--issue", "589", "--root", root]) == review_loop.REFUSED
    assert (
        review_loop.main(["self-converge", "--issue", "589", "--root", root, "--sha", "c" * 40])
        == review_loop.REFUSED
    )


def test_self_round_refuses_a_malformed_or_unknown_finding_spec() -> None:
    """A malformed spec is a parser exit; an unknown category or origin is a typed refusal."""
    for spec in (
        "S1=worth_addressing=pre_existing",
        "S1=worth_addressing=pre_existing=",
    ):
        with pytest.raises(SystemExit) as exit_code:
            review_loop.parse_args(["self-round", "--issue", "589", "--finding", spec])
        assert exit_code.value.code == 2
    assert (
        refused(
            lambda: review_loop.self_review_round(
                review_loop.SelfReview(),
                (review_loop.SelfReviewFinding("S1", "not_a_category", "pre_existing", "r", 1),),
            )
        )
        == review_loop.SELF_REVIEW_CATEGORY_ERROR + ": not_a_category"
    )
    assert (
        refused(
            lambda: review_loop.self_review_round(
                review_loop.SelfReview(),
                (review_loop.SelfReviewFinding("S1", "worth_addressing", "not_an_origin", "r", 1),),
            )
        )
        == review_loop.SELF_REVIEW_ORIGIN_ERROR + ": not_an_origin"
    )


def test_self_fail_types_from_the_fifth_round_through_the_cli(tmp_path: Path) -> None:
    """Five cleanless rounds then `self-fail` records the type the fifth round decides."""
    root = str(tmp_path / "review")
    journal = str(tmp_path / "journal.jsonl")
    review_loop.main(["open", "--issue", "589", "--root", root, "--journal", journal])
    for number in range(1, 6):
        assert (
            review_loop.main(
                [
                    "self-round",
                    "--issue",
                    "589",
                    "--root",
                    root,
                    "--finding",
                    f"S{number}=worth_addressing=pre_existing=round {number} reason",
                ]
            )
            == review_loop.OK
        )
    assert review_loop.main(["self-fail", "--issue", "589", "--root", root]) == review_loop.OK
    loop = review_loop.load_loop(tmp_path / "review", 589)
    assert loop.self_review.failure == review_loop.DISCOVERY_DOMINATED
    # The budget exhausted, a further round refuses and the close states the type.
    assert (
        review_loop.main(
            [
                "self-round",
                "--issue",
                "589",
                "--root",
                root,
                "--finding",
                "S6=worth_addressing=pre_existing=one more",
            ]
        )
        == review_loop.REFUSED
    )


def test_open_adopts_a_file_holding_only_a_self_review_record(tmp_path: Path) -> None:
    """The reviewer's round zero adopts the Work Run's block rather than refusing it."""
    root = str(tmp_path / "review")
    journal = str(tmp_path / "journal.jsonl")
    assert review_loop.main(["self-round", "--issue", "589", "--root", root]) == review_loop.OK
    assert (
        review_loop.main(["self-converge", "--issue", "589", "--root", root, "--sha", "a" * 40])
        == review_loop.OK
    )
    assert (
        review_loop.main(
            [
                "open",
                "--issue",
                "589",
                "--root",
                root,
                "--journal",
                journal,
                "--finding",
                "F1=high",
            ]
        )
        == review_loop.OK
    )
    loop = review_loop.load_loop(tmp_path / "review", 589)
    assert loop.review_rounds == 0
    assert [item.id for item in loop.findings] == ["F1"]
    assert loop.self_review is not None
    assert loop.self_review.converged_on == "a" * 40


def test_open_still_refuses_a_second_open_of_a_loop_with_state(tmp_path: Path) -> None:
    """A file carrying the independent loop's own state is a second open, still refused."""
    root = str(tmp_path / "review")
    journal = str(tmp_path / "review" / "journal.jsonl")
    assert (
        review_loop.main(
            [
                "open",
                "--issue",
                "589",
                "--root",
                root,
                "--journal",
                journal,
                "--finding",
                "F1=high",
            ]
        )
        == review_loop.OK
    )
    assert (
        review_loop.main(["open", "--issue", "589", "--root", root, "--journal", journal])
        == review_loop.REFUSED
    )


def test_open_refuses_after_an_opened_clean_round_zero(tmp_path: Path) -> None:
    """The opened fact is carried, never inferred: opened clean at round zero still refuses.

    Round two's Critical: `open` on a self-review-only file adopts it, and the adopted
    file is then indistinguishable from an independent round zero opened clean — so a
    second `open` succeeded, silently re-opening the reviewer's loop. `independent_opened`
    is the fact that separates the two, so the second one refuses.
    """
    root = str(tmp_path / "review")
    journal = str(tmp_path / "review" / "journal.jsonl")
    # Self-review first, then the reviewer's clean round zero adopts the block.
    assert review_loop.main(["self-round", "--issue", "589", "--root", root]) == review_loop.OK
    assert (
        review_loop.main(["open", "--issue", "589", "--root", root, "--journal", journal])
        == review_loop.OK
    )
    assert (
        review_loop.main(["open", "--issue", "589", "--root", root, "--journal", journal])
        == review_loop.REFUSED
    )


def test_sync_treats_a_self_review_only_file_as_an_unopened_loop(tmp_path: Path) -> None:
    """A self-review-only file is round zero to `sync`, never a phantom round one.

    The first independent findings land at round zero because the independent loop has
    not been opened — the file's `independent_opened` says so — even though a `loop.json`
    exists and `review_rounds` is already 0.
    """
    root = tmp_path / "review"
    dispatch_root = stage_verdict(tmp_path, findings=(("R1", "high"),))
    assert review_loop.main(["self-round", "--issue", "334", "--root", str(root)]) == (
        review_loop.OK
    )

    assert (
        review_loop.main(sync_args(root, tmp_path / "journal.jsonl", dispatch_root))
        == review_loop.OK
    )

    loop = review_loop.load_loop(root, 334)
    assert loop.independent_opened is True
    assert loop.review_rounds == 0
    assert [(f.id, f.round_raised) for f in loop.findings] == [("R1", 0)]
    assert loop.self_review is not None
    assert loop.self_review.rounds[0].number == 1


def test_sync_opens_round_zero_for_a_clean_verdict_on_a_self_review_only_file(
    tmp_path: Path,
) -> None:
    """A clean first verdict over a self-review-only file is still an observed round zero."""
    root = tmp_path / "review"
    dispatch_root = stage_verdict(tmp_path, findings=())
    assert review_loop.main(["self-round", "--issue", "334", "--root", str(root)]) == (
        review_loop.OK
    )

    assert (
        review_loop.main(sync_args(root, tmp_path / "journal.jsonl", dispatch_root))
        == review_loop.OK
    )

    loop = review_loop.load_loop(root, 334)
    assert loop.independent_opened is True
    assert loop.review_rounds == 0
    assert loop.findings == ()


def test_sync_still_advances_a_loop_that_is_opened(tmp_path: Path) -> None:
    """Once opened, the fold is the next round exactly as before."""
    root = tmp_path / "review"
    journal = tmp_path / "journal.jsonl"
    dispatch_root = stage_verdict(tmp_path, findings=(("F1", "high"),))
    assert review_loop.main(sync_args(root, journal, dispatch_root)) == review_loop.OK
    stage_verdict(tmp_path, findings=(("F1", "high"), ("F2", "medium")))

    assert review_loop.main(sync_args(root, journal, dispatch_root)) == review_loop.OK

    loop = review_loop.load_loop(root, 334)
    assert loop.independent_opened is True
    assert loop.review_rounds == 1
    assert [(f.id, f.round_raised) for f in loop.findings] == [("F1", 0), ("F2", 1)]


def test_a_round_refuses_an_id_shared_across_finding_and_refutation() -> None:
    """The whole-record identity contract holds at the write, not only at the next read."""
    assert refused(
        lambda: review_loop.self_review_round(
            review_loop.SelfReview(),
            (self_finding("S1"),),
            (review_loop.SelfReviewRefutation("S1", "the evidence", 1),),
        )
    ) == review_loop.SELF_REVIEW_DUPLICATE_ERROR.format(id="S1")


def test_stored_self_review_states_no_writer_produces_are_refused() -> None:
    """The read half of the writers' preconditions: closed states stay consistent."""
    finding = {
        "id": "S1",
        "category": review_loop.WORTH_ADDRESSING,
        "origin": review_loop.PRE_EXISTING,
        "reason": "a reason",
        "round_raised": 1,
    }
    document = review_loop.render_loop(
        589,
        review_loop.Loop(review_rounds=0, findings=(), self_review=review_loop.SelfReview()),
    )

    def refused_block(**overrides: object) -> str:
        stored = {
            "rounds": [{"number": 1, "findings": [finding], "refutations": []}],
            **overrides,
        }
        return refused(lambda: review_loop.parse_loop({**document, "self_review": stored}))

    # A sixth round: the budget is five, and the exit is self-fail, never another pass.
    six = [
        {
            "number": number,
            "findings": [{**finding, "round_raised": number}],
            "refutations": [],
        }
        for number in range(1, 7)
    ]
    assert (
        refused(lambda: review_loop.parse_loop({**document, "self_review": {"rounds": six}}))
        == review_loop.SELF_REVIEW_SHAPE_ERROR
    )
    # A failure short of the budget.
    assert refused_block(failure=review_loop.DISCOVERY_DOMINATED) == (
        review_loop.SELF_REVIEW_SHAPE_ERROR
    )
    assert (
        refused_block(
            failure=review_loop.DISCOVERY_DOMINATED,
            rounds=[
                {
                    "number": number,
                    "findings": [{**finding, "round_raised": number}],
                    "refutations": [],
                }
                for number in range(1, 6)
            ]
            + [{"number": 6, "findings": [], "refutations": []}],
        )
        == review_loop.SELF_REVIEW_SHAPE_ERROR
    )
    # Convergence without an observed clean last round.
    assert refused_block(converged_on="a" * 40) == review_loop.SELF_REVIEW_SHAPE_ERROR
    # Gate fixes without convergence.
    assert (
        refused_block(
            rounds=[],
            gate_fixes=[{"sha": "b" * 40, "reason": "confined to the gate"}],
        )
        == review_loop.SELF_REVIEW_SHAPE_ERROR
    )
    # Non-list findings or refutations: an uncaught TypeError before, typed now.
    assert (
        refused_block(rounds=[{"number": 1, "findings": "S1", "refutations": []}])
        == review_loop.SELF_REVIEW_SHAPE_ERROR
    )
    assert (
        refused_block(rounds=[{"number": 1, "findings": [], "refutations": 7}])
        == review_loop.SELF_REVIEW_SHAPE_ERROR
    )
    assert (
        refused(
            lambda: review_loop.parse_loop(
                {**document, "self_review": {"rounds": [], "converged_on": 3}}
            )
        )
        == review_loop.SELF_REVIEW_SHAPE_ERROR
    )
    # An empty block still reads: present, carrying nothing, refusing nothing.
    assert review_loop.parse_loop({**document, "self_review": {"rounds": []}}).self_review == (
        review_loop.SelfReview()
    )


def test_an_opened_loop_round_trips_its_opened_fact() -> None:
    """`independent_opened` renders, reads back, and derives where a legacy document omits it."""
    opened = review_loop.first_review(())
    stored = json.loads(json.dumps(review_loop.render_loop(589, opened)))
    assert stored["independent_opened"] is True
    assert review_loop.parse_loop(stored).independent_opened is True
    closed = stored | {"independent_opened": False}
    assert review_loop.parse_loop(closed).independent_opened is False
    assert (
        refused(lambda: review_loop.parse_loop({**stored, "independent_opened": "yes"}))
        == review_loop.LOOP_OPENED_ERROR
    )
    # A legacy document without the key: real loop state derives opened, an empty loop
    # with a self-review block derives unopened.
    legacy_opened = json.loads(
        json.dumps(
            review_loop.render_loop(
                589, review_loop.first_review((review_loop.Finding("F1", "high", 0),))
            )
        )
    )
    del legacy_opened["independent_opened"]
    assert review_loop.parse_loop(legacy_opened).independent_opened is True
    self_only = {
        "version": 2,
        "issue": 589,
        "review_rounds": 0,
        "findings": [],
        "self_review": {"rounds": []},
    }
    assert review_loop.parse_loop(self_only).independent_opened is False
