"""The retrospective observatory (ADR-0071 ruling 6, #336).

Three properties carry the module, and each has a way of failing silently that a count of
lines would not catch — so each is asserted on the number, not on the presence of a row.

**The key exists only where its denominator does.** A profile with landings ranks on fix
rounds per landing; one without appears with its rounds visible and no rank at all, and a
seat that lands nothing by contract is neither. The near-misses matter more than the hits:
`no_landings` must not become a rank of infinity that sorts, and a `review` row must not
read as an implementer that failed to land.

**The strata are the pre-work signals and nothing else**, grouped by #347's typed code
rather than by the prose beside it — the two degradation states that differ only in their
reason must land in different buckets.

**Spend never crosses a lane.** Asserted as an absence, which is the awkward kind: the test
reads every emitted line and requires that no lane's figure contains another lane's tokens.

The unreachable root is tested because it is the finding this issue was asked to establish:
a dispatched seat cannot read `~/.arma-cti`, and an observatory that answered "no rework"
from inside one would be the dropped bar's failure inverted.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from conftest import load_tool

if TYPE_CHECKING:
    from pathlib import Path

observatory = load_tool("observatory")
dispatch = load_tool("dispatch")


def write_dispatch(  # noqa: PLR0913 — keyword-only, one parameter per field of the record under test
    root: Path,
    dispatch_id: str,
    *,
    profile: str = "opus-high",
    seat: str = "implementer",
    lane: str = "claude-native",
    issue: int = 1,
    strata: dict[str, object] | None = None,
    usage: dict[str, int] | None = None,
) -> None:
    record = root / dispatch_id
    record.mkdir(parents=True)
    document: dict[str, object] = {
        "dispatch_id": dispatch_id,
        "lane": lane,
        "profile": profile,
        "seat": seat,
        "issue": issue,
    }
    if strata is not None:
        document["strata"] = strata
    (record / "dispatch.json").write_text(json.dumps(document), encoding="utf-8")
    if usage is not None:
        (record / "ledger.json").write_text(json.dumps({"usage": usage}), encoding="utf-8")


def write_loop(root: Path, issue: int, rounds: int, *, terminus: bool) -> None:
    directory = root / str(issue)
    directory.mkdir(parents=True)
    name = "landing.json" if terminus else "loop.json"
    (directory / name).write_text(json.dumps({"review_rounds": rounds}), encoding="utf-8")


def roots(tmp_path: Path) -> tuple[Path, Path]:
    """Both state roots, present and empty.

    Present because `rollup` reads roots that exist — deciding "I could not look" is
    `unreachable`'s job and duplicating it inside the readers would be two answers to one
    question. The one test that wants an absent root arranges it by hand, below.
    """
    dispatches = tmp_path / "dispatches"
    review = tmp_path / "review"
    dispatches.mkdir()
    review.mkdir()
    return dispatches, review


def rows_by_profile(found: Any) -> dict[str, Any]:  # noqa: ANN401 — `load_tool` returns a bare module, so its types are unnameable here
    """Index the rollup's rows by profile."""
    return {row.profile: row for row in found.rows}


# --------------------------------------------------------------------- the key and its denominator


def test_key_is_rounds_over_landings(tmp_path: Path) -> None:
    """Two terminated issues, five rounds between them: the key is 2.5 and not a count."""
    dispatches, review = roots(tmp_path)
    write_dispatch(dispatches, "d-1", issue=1)
    write_dispatch(dispatches, "d-2", issue=2)
    write_loop(review, 1, 3, terminus=True)
    write_loop(review, 2, 2, terminus=True)
    row = rows_by_profile(observatory.rollup(dispatches, review))["opus-high"]
    assert row.landings == 2
    assert row.rounds == 5
    assert row.key == 2.5


def test_one_issue_counts_once_however_many_dispatches(tmp_path: Path) -> None:
    """Three dispatches onto one issue are one loop: rounds must not be multiplied by three.

    The failure this catches is the natural implementation — iterate the records and add the
    issue's rounds each time — which turns one item's rework into a profile-wide finding.
    """
    dispatches, review = roots(tmp_path)
    for name in ("d-1", "d-2", "d-3"):
        write_dispatch(dispatches, name, issue=7)
    write_loop(review, 7, 4, terminus=True)
    row = rows_by_profile(observatory.rollup(dispatches, review))["opus-high"]
    assert row.dispatches == 3
    assert row.issues == 1
    assert row.rounds == 4
    assert row.landings == 1
    assert row.key == 4.0


def test_no_landings_is_unranked_with_its_rounds_visible(tmp_path: Path) -> None:
    """A loop in flight is rework with no denominator: the rounds show, the key is None."""
    dispatches, review = roots(tmp_path)
    write_dispatch(dispatches, "d-1", issue=1)
    write_loop(review, 1, 6, terminus=False)
    row = rows_by_profile(observatory.rollup(dispatches, review))["opus-high"]
    assert row.verdict == observatory.NO_LANDINGS
    assert row.rounds == 6
    assert row.landings == 0
    assert row.key is None


def test_key_none_is_rendered_as_none_and_never_as_a_number(tmp_path: Path) -> None:
    """The unranked row's key must not render as a value another row could be sorted against."""
    dispatches, review = roots(tmp_path)
    write_dispatch(dispatches, "d-1", issue=1)
    write_loop(review, 1, 6, terminus=False)
    found = observatory.rollup(dispatches, review)
    rendered = observatory.render(found, dispatches, review)
    line = next(text for text in rendered if text.startswith("row "))
    assert "key=none" in line
    assert "rounds=6" in line


def test_seat_that_lands_nothing_is_reported_and_never_ranked(tmp_path: Path) -> None:
    """A `review` row carries its rework under `lands_nothing`, not under `no_landings`.

    The distinction is the whole of ruling 6's sentence about the seats that land nothing by
    contract: `no_landings` on a review row would read as a failure to land.
    """
    dispatches, review = roots(tmp_path)
    write_dispatch(dispatches, "d-1", seat="review", profile="codex-sol-high", issue=1)
    write_loop(review, 1, 3, terminus=True)
    row = rows_by_profile(observatory.rollup(dispatches, review))["codex-sol-high"]
    assert row.seat == "review"
    assert row.verdict == "lands_nothing"
    assert row.key is None
    assert row.rounds == 3


def test_only_the_implementer_seat_is_ranked(tmp_path: Path) -> None:
    """Every non-implementer seat on the roster is reported, and none of them ranks."""
    dispatches, review = roots(tmp_path)
    seats = [seat for seat in dispatch.SEATS if seat != observatory.RANKED_SEAT]
    assert seats, "the roster must carry seats other than the ranked one"
    for index, seat in enumerate(seats):
        write_dispatch(dispatches, f"d-{index}", seat=seat, profile=f"p-{seat}", issue=index + 1)
        write_loop(review, index + 1, 2, terminus=True)
    found = observatory.rollup(dispatches, review)
    assert found.rows, "the non-implementer seats must still be reported"
    assert all(row.key is None for row in found.rows)
    assert all(row.verdict == "lands_nothing" for row in found.rows)


def test_thin_evidence_is_a_verdict_and_not_a_rank(tmp_path: Path) -> None:
    """Two landings support no conclusion: the row shows its numbers under `thin_evidence`."""
    dispatches, review = roots(tmp_path)
    for issue in (1, 2):
        write_dispatch(dispatches, f"d-{issue}", issue=issue)
        write_loop(review, issue, 1, terminus=True)
    row = rows_by_profile(observatory.rollup(dispatches, review))["opus-high"]
    assert row.verdict == observatory.THIN
    assert row.landings == 2
    assert row.rounds == 2
    assert row.key == 1.0


def test_verdict_turns_at_the_stated_threshold() -> None:
    """The estimate is a boundary, and the boundary is where the module says it is."""
    assert observatory.verdict(0) == observatory.NO_LANDINGS
    assert observatory.verdict(observatory.THIN_EVIDENCE_BELOW - 1) == observatory.THIN
    assert observatory.verdict(observatory.THIN_EVIDENCE_BELOW) == observatory.RANKED


def test_ranked_rows_sort_before_unranked_ones_and_by_the_key(tmp_path: Path) -> None:
    """The row order is the ranking, so an unranked row must not land among the ranked."""
    dispatches, review = roots(tmp_path)
    issue = 0
    for profile, rounds in (("clean", 0), ("noisy", 2)):
        for _ in range(observatory.THIN_EVIDENCE_BELOW):
            issue += 1
            write_dispatch(dispatches, f"d-{issue}", profile=profile, issue=issue)
            write_loop(review, issue, rounds, terminus=True)
    issue += 1
    write_dispatch(dispatches, f"d-{issue}", profile="unlanded", issue=issue)
    write_loop(review, issue, 9, terminus=False)
    order = [row.profile for row in observatory.rollup(dispatches, review).rows]
    assert order == ["clean", "noisy", "unlanded"]


def test_shared_issue_attribution_is_counted_and_reported(tmp_path: Path) -> None:
    """Two implementer profiles on one issue book its rounds to both, and the count says so."""
    dispatches, review = roots(tmp_path)
    write_dispatch(dispatches, "d-1", profile="a", issue=4)
    write_dispatch(dispatches, "d-2", profile="b", issue=4)
    write_dispatch(dispatches, "d-3", profile="a", issue=5)
    write_loop(review, 4, 3, terminus=True)
    write_loop(review, 5, 1, terminus=True)
    found = observatory.rollup(dispatches, review)
    assert found.shared_issues == 1
    assert rows_by_profile(found)["b"].rounds == 3
    assert "shared_issues=1" in observatory.render(found, dispatches, review)[0]


# --------------------------------------------------------------------------------- spend per lane


def test_spend_is_per_lane_and_no_line_sums_across_lanes(tmp_path: Path) -> None:
    """Each lane's tokens stay in its own line, and nothing in the output carries the sum."""
    dispatches, review = roots(tmp_path)
    write_dispatch(
        dispatches, "d-1", lane="claude-native", usage={"input_tokens": 10, "output_tokens": 3}
    )
    write_dispatch(
        dispatches, "d-2", lane="zai", issue=2, usage={"input_tokens": 100, "output_tokens": 7}
    )
    found = observatory.rollup(dispatches, review)
    per_lane = {spend.lane: spend for spend in found.spend}
    assert per_lane["claude-native"].output_tokens == 3
    assert per_lane["zai"].output_tokens == 7
    rendered = observatory.render(found, dispatches, review)
    # 110 and 10 are the cross-lane sums. Their absence is the assertion: a total line, or a
    # lane line carrying another lane's tokens, would put back the conversion ADR-0061
    # Decision 5 forbids.
    assert not [line for line in rendered if "in=110" in line or "out=10" in line]
    assert len([line for line in rendered if line.startswith("spend ")]) == 2


def test_a_dispatch_without_a_ledger_row_is_unmeasured_and_not_zero(tmp_path: Path) -> None:
    """`dispatches` counts the run, `ledger_rows` counts the measurement, and they differ."""
    dispatches, review = roots(tmp_path)
    write_dispatch(dispatches, "d-1", usage={"input_tokens": 5, "output_tokens": 2})
    write_dispatch(dispatches, "d-2", issue=2)
    spend = observatory.rollup(dispatches, review).spend[0]
    assert spend.dispatches == 2
    assert spend.rows == 1
    assert spend.output_tokens == 2


# ------------------------------------------------------------------------- the pre-work strata


def test_strata_group_on_the_typed_code_and_never_on_the_reason(tmp_path: Path) -> None:
    """Two degradation states whose only difference is #347's code must not merge.

    Before #347 these two were told apart only by their prose, and `Stratum.unknown("")`
    collided exactly with pre-#323 absence — which is the collision this asserts is gone.
    """
    dispatches, review = roots(tmp_path)
    for index, code in enumerate(
        (dispatch.STRATUM_SOURCE_UNAVAILABLE, dispatch.STRATUM_PRE_STRATA_ABSENT)
    ):
        write_dispatch(
            dispatches,
            f"d-{index}",
            issue=index + 1,
            strata={
                "gate_tier": None,
                "gate_tier_checked": False,
                "gate_tier_unchecked_why": "",
                "gate_tier_code": code,
            },
        )
    found = observatory.rollup(dispatches, review)
    gate = next(counter for _, signal, counter in found.strata if signal == "gate_tier")
    assert gate[dispatch.STRATUM_SOURCE_UNAVAILABLE] == 1
    assert gate[dispatch.STRATUM_PRE_STRATA_ABSENT] == 1


def test_a_checked_stratum_groups_on_its_value(tmp_path: Path) -> None:
    """A gate tier that was read groups under the tier, not under a degradation code."""
    dispatches, review = roots(tmp_path)
    write_dispatch(
        dispatches,
        "d-1",
        strata={
            "gate_tier": "fast",
            "gate_tier_checked": True,
            "gate_tier_unchecked_why": "",
            "gate_tier_code": dispatch.STRATUM_CHECKED,
            "routing_class_id": "6",
            "routing_class_name": "gates",
            "routing_class_checked": True,
            "routing_class_unchecked_why": "",
            "routing_class_code": dispatch.STRATUM_CHECKED,
        },
    )
    signals = {
        signal: counter for _, signal, counter in observatory.rollup(dispatches, review).strata
    }
    assert signals["gate_tier"]["fast"] == 1
    assert signals["routing_class"]["6"] == 1


def test_strata_are_reported_only_for_the_ranked_seat(tmp_path: Path) -> None:
    """The strata qualify a comparison, and there is no comparison outside the ranked seat."""
    dispatches, review = roots(tmp_path)
    write_dispatch(dispatches, "d-1", seat="review", profile="reviewer", issue=1)
    write_dispatch(dispatches, "d-2", seat="implementer", profile="builder", issue=2)
    profiles = {profile for profile, _, _ in observatory.rollup(dispatches, review).strata}
    assert profiles == {"builder"}


# ----------------------------------------------------------------------- reading, and not reading


def test_an_unreadable_record_is_counted_and_never_silently_dropped(tmp_path: Path) -> None:
    """A corrupt record makes the rollup smaller, and the count is how a reader learns that."""
    dispatches, review = roots(tmp_path)
    write_dispatch(dispatches, "d-1")
    broken = dispatches / "d-2"
    broken.mkdir()
    (broken / "dispatch.json").write_text("{not json", encoding="utf-8")
    (dispatches / "d-3").mkdir()
    found = observatory.rollup(dispatches, review)
    assert len(found.dispatches.records) == 1
    assert found.dispatches.unreadable == ("d-2", "d-3")
    assert "dispatches_unreadable=2" in observatory.render(found, dispatches, review)[0]


def test_a_dispatch_naming_no_issue_cannot_be_joined_and_is_counted_unreadable(
    tmp_path: Path,
) -> None:
    """The join is on the issue, so a record without one is unjoinable rather than issue zero."""
    dispatches, review = roots(tmp_path)
    record = dispatches / "d-1"
    record.mkdir(parents=True)
    (record / "dispatch.json").write_text(
        json.dumps({"lane": "claude-native", "profile": "p", "seat": "implementer", "issue": 0}),
        encoding="utf-8",
    )
    found = observatory.rollup(dispatches, review)
    assert found.dispatches.records == ()
    assert found.dispatches.unreadable == ("d-1",)


def test_the_terminus_record_supplies_the_round_count_over_the_in_flight_one(
    tmp_path: Path,
) -> None:
    """`landing.json` is the loop's final word; a stale `loop.json` beside it must not win."""
    dispatches, review = roots(tmp_path)
    directory = review / "3"
    directory.mkdir(parents=True)
    (directory / "loop.json").write_text(json.dumps({"review_rounds": 1}), encoding="utf-8")
    (directory / "landing.json").write_text(json.dumps({"review_rounds": 4}), encoding="utf-8")
    write_dispatch(dispatches, "d-1", issue=3)
    row = rows_by_profile(observatory.rollup(dispatches, review))["opus-high"]
    assert row.rounds == 4
    assert row.landings == 1


def test_a_review_directory_that_will_not_read_is_named(tmp_path: Path) -> None:
    """A negative round count is not a loop this rollup can join, and it says so."""
    dispatches, review = roots(tmp_path)
    for name, body in (("9", '{"review_rounds": -1}'), ("notanissue", '{"review_rounds": 1}')):
        directory = review / name
        directory.mkdir(parents=True)
        (directory / "loop.json").write_text(body, encoding="utf-8")
    found = observatory.rollup(dispatches, review)
    assert found.loops == ()
    assert found.unreadable_loops == ("9", "notanissue")


# ------------------------------------------------------------------------------- the confinement


def test_an_unreachable_root_refuses_rather_than_reporting_an_empty_rollup(
    tmp_path: Path,
) -> None:
    """The finding this issue was asked to establish, mechanised: exit 3, never a green zero.

    A dispatched seat is confined to its worktree (#294) and `~/.arma-cti` is outside it, so
    the rollup run from inside a dispatch sees nothing. Reporting no rework from there would
    be the dropped bar's failure inverted — a confident quality claim off no data.
    """
    dispatches = tmp_path / "dispatches"
    dispatches.mkdir()
    absent = tmp_path / "review"
    assert observatory.unreachable(dispatches, absent) == (f"root={absent}",)
    assert observatory.unreachable(dispatches, dispatches) == ()
    code = observatory.main(["--dispatch-root", str(dispatches), "--review-root", str(absent)])
    assert code == 3


def test_a_reachable_pair_renders_and_exits_zero(tmp_path: Path) -> None:
    """The happy path exits zero and carries every caveat with the numbers, not beside them."""
    dispatches, review = roots(tmp_path)
    write_dispatch(dispatches, "d-1")
    write_loop(review, 1, 2, terminus=True)
    assert observatory.main(["--dispatch-root", str(dispatches), "--review-root", str(review)]) == 0
    rendered = observatory.render(observatory.rollup(dispatches, review), dispatches, review)
    assert len([line for line in rendered if line.startswith("caveat ")]) == len(
        observatory.CAVEATS
    )
    assert any("containment_column=absent" in line for line in rendered)
