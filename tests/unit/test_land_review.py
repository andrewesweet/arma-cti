"""The never-alone rung's ladder: every way a landing can lack its review, by name (#334).

ADR-0071 ruling 4's three criteria, enforced at `just land`'s third gate through
`tools/land_review.py`: a review dispatch record for the landed SHA whose identity
derives from the records (`review_exchange`), a reviewer the issue's own dispatch
records do not place on the work (`dispatch`), and every finding above Low closed
through one of the four routes (`review_loop`). All three are staged here from the
records the owning tools write, so each refusal is asserted by its own kind and its
own words — the same two-layer shape `test_land.py` gives the protocol's other
rungs (#83's precedent: a classification bug should be a red `just unit`).

The loop state read here is #333's `loop.json` format as it stood at `ab76974`; the
swap to that issue's own reader is the follow-up `land_review`'s docstring records.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

import pytest
from conftest import load_tool

if TYPE_CHECKING:
    from pathlib import Path

land_review = load_tool("land_review")
review_loop = load_tool("review_loop")
review_exchange = load_tool("review_exchange")

SHA: Final = "a" * 40
OTHER_SHA: Final = "b" * 40
STAMP: Final = "20260815T0000Z"
ISSUE: Final = 334
REVIEWER: Final = "codex-luna-max"
AUTHOR: Final = "opus-high"

# The trusted table's text as a landing reads it off `origin/main`: a docs prefix
# and one exact file, both with their reasons. Nothing here exempts itself, because
# a table that tried to would not parse far enough to govern anything.
TABLE: Final = json.dumps(
    {
        "version": 1,
        "source": "test",
        "entries": [
            {"surface": "docs/", "reason": "prose is reviewed in the issue that asked for it"},
            {"surface": "CHANGELOG.md", "reason": "the changelog row follows the landing"},
        ],
    }
)
RESULT: Final = json.dumps({"returncode": 0, "outcome": "ok", "ended_at": STAMP})


def _plan(  # noqa: PLR0913 — one parameter per field of the record under test
    *,
    seat: str = "review",
    issue: int = ISSUE,
    base_sha: str = SHA,
    profile: str = REVIEWER,
    planned_at: str = STAMP,
    dispatch_id: str = "d-review-1",
) -> str:
    """One dispatch record, written the shape `tools/dispatch.py` writes it."""
    return json.dumps(
        {
            "seat": seat,
            "issue": issue,
            "base_sha": base_sha,
            "profile": profile,
            "lane": "codex",
            "planned_at": planned_at,
            "dispatch_id": dispatch_id,
        }
    )


def _verdict(  # noqa: PLR0913 — one parameter per field of the record under test
    *,
    issue: int = ISSUE,
    sha: str = SHA,
    dispatch: str = "d-review-1",
    profile: str = REVIEWER,
    findings: tuple[tuple[str, str], ...] = (),
    alternates: tuple[str, ...] = (),
) -> str:
    """One verdict record, written the shape `review_exchange.record_verdict` writes it."""
    return json.dumps(
        {
            "version": 1,
            "issue": issue,
            "reviewed_sha": sha,
            "review_dispatch": dispatch,
            "reviewer_profile": profile,
            "reviewer_lane": "codex",
            "findings": [{"id": name, "severity": severity} for name, severity in findings],
            "recorded_at": STAMP,
            "alternates": list(alternates),
        }
    )


def _stored(  # noqa: PLR0913, PLR0917 — one parameter per field of the record under test
    identifier: str,
    severity: str,
    round_raised: int = 0,
    route: str | None = None,
    issue: str = "",
    conditional_on: str = "",
) -> dict[str, object]:
    """One stored loop finding, open unless a route closes it."""
    finding: dict[str, object] = {
        "id": identifier,
        "severity": severity,
        "round_raised": round_raised,
    }
    if route is not None:
        finding["adjudication"] = {"route": route, "issue": issue, "conditional_on": conditional_on}
    return finding


def _loop(
    *,
    issue: int = ISSUE,
    rounds: int = 1,
    findings: tuple[dict[str, object], ...] = (),
) -> str:
    """One stored loop document, in #333's format as it stood at `ab76974`."""
    return json.dumps(
        {"version": 1, "issue": issue, "review_rounds": rounds, "findings": list(findings)}
    )


_PLAN_TEXT: Final = _plan()
_VERDICT_TEXT: Final = _verdict()


def _authoring(profile: str) -> str:
    """One implementing dispatch record on this issue, the shape the scan reads it."""
    return json.dumps(
        {"seat": "implementer", "issue": ISSUE, "profile": profile, "dispatch_id": "d-author-1"}
    )


def _stage(  # noqa: PLR0913 — one parameter per record the rung reads
    tmp_path: Path,
    *,
    plan: str | None = _PLAN_TEXT,
    result: str | None = RESULT,
    verdict: str | None = _VERDICT_TEXT,
    loop: str | None = None,
    author: str | None = AUTHOR,
    records: tuple[tuple[str, str, str], ...] = (),
) -> tuple[Path, Path]:
    """Stage the dispatch and review roots a rung reads.

    Defaults to a bound, completed, clean review over authored work: the plan given
    (a review seat on this issue bound to `SHA`), its completed result, the verdict
    given (clean, identity matching), and one implementing dispatch on this issue by
    a profile that is not the reviewer's.

    That last record is a default rather than a per-test extra because no landing
    clears without it: records naming no author at all satisfy criterion 2 only
    vacuously and refuse `authorship_unrecorded` (round 1 claim 1). `author=None`
    withholds it, which is the arrangement that refusal is asserted on.

    `None` writes nothing, so a test names the record it withholds; `records` writes
    further dispatch directories beside the review's own — authoring records,
    alternates, the unreadable — and is applied last, so a test may overwrite the
    default authoring record by naming `d-author-1` itself.
    """
    dispatch_root = tmp_path / "dispatches"
    review_root = tmp_path / "review"
    dispatch_root.mkdir(parents=True, exist_ok=True)
    if author is not None:
        authored = dispatch_root / "d-author-1"
        authored.mkdir(parents=True, exist_ok=True)
        (authored / "dispatch.json").write_text(_authoring(author), encoding="utf-8")
    record = dispatch_root / "d-review-1"
    if plan is not None or result is not None or verdict is not None:
        record.mkdir(parents=True, exist_ok=True)
    if plan is not None:
        (record / "dispatch.json").write_text(plan, encoding="utf-8")
    if result is not None:
        (record / "result.json").write_text(result, encoding="utf-8")
    if verdict is not None:
        (record / "verdict.json").write_text(verdict, encoding="utf-8")
    if loop is not None:
        target = review_root / str(ISSUE) / "loop.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(loop, encoding="utf-8")
    for name, filename, text in records:
        extra = dispatch_root / name
        extra.mkdir(parents=True, exist_ok=True)
        (extra / filename).write_text(text, encoding="utf-8")
    return dispatch_root, review_root


def _rung(
    roots: tuple[Path, Path],
    *,
    issue: int | None = ISSUE,
    sha: str = SHA,
    paths: tuple[str, ...] = ("tools/worker.py",),
    exemptions: str | None = None,
) -> land_review.Outcome:
    """Call the rung over staged roots.

    `exemptions=None` is the unreadable table — the state a landing is in wherever
    `origin/main` carries no table, which exempts nothing and so falls into the
    ladder every default here exercises.
    """
    dispatch_root, review_root = roots
    return land_review.review_finding(issue, sha, paths, exemptions, dispatch_root, review_root)


def _kind(outcome: land_review.Outcome) -> str:
    assert outcome is not None
    refusal = outcome.refusal
    assert refusal is not None
    return refusal.kind


# ------------------------------------------------------ the binding and the verdict


def test_a_tree_with_no_dispatch_directory_refuses_by_name(tmp_path: Path) -> None:
    """No records to derive a reviewing identity from is not the same as no review owed."""
    outcome = _rung((tmp_path / "none", tmp_path / "review"))

    assert _kind(outcome) == "no_dispatch_records"


def test_an_unreadable_review_plan_refuses_the_scan_it_belongs_to(tmp_path: Path) -> None:
    """The record that would not open could be the binding one (#41, in #322's shape)."""
    outcome = _rung(_stage(tmp_path, plan="not json at all"))

    assert _kind(outcome) == "records_unreadable"
    assert "record=d-review-1" in outcome.refusal.found


def test_a_review_plan_that_names_no_commit_binds_none_visibly(tmp_path: Path) -> None:
    """A plan without `base_sha` is not a shape the dispatcher writes, and never `past`."""
    outcome = _rung(_stage(tmp_path, plan=json.dumps({"seat": "review", "issue": ISSUE})))

    assert _kind(outcome) == "records_unreadable"


def test_no_completed_review_bound_to_this_sha_refuses_by_name(tmp_path: Path) -> None:
    """An empty directory, and a record bound to another commit: one refusal, both ways."""
    empty = _stage(tmp_path, plan=None, result=None, verdict=None)
    assert _kind(_rung(empty)) == "no_review_dispatch"

    other = _stage(tmp_path, plan=_plan(base_sha=OTHER_SHA))
    assert _kind(_rung(other)) == "no_review_dispatch"


def test_a_review_that_ended_not_ok_completed_nothing(tmp_path: Path) -> None:
    """`quota_exhausted` carries an `ended_at` like any other ending — and is not a result."""
    outcome = _rung(
        _stage(
            tmp_path,
            result=json.dumps({"returncode": 1, "outcome": "quota_exhausted", "ended_at": STAMP}),
        )
    )

    assert _kind(outcome) == "no_review_dispatch"


def test_a_dispatch_that_refused_before_running_reviewed_nothing(tmp_path: Path) -> None:
    """A `result.json` carrying a refusal never reached a lane, so it binds nothing."""
    outcome = _rung(_stage(tmp_path, result=json.dumps({"refusal": "infra_unavailable"})))

    assert _kind(outcome) == "no_review_dispatch"


def test_a_completed_review_without_its_verdict_clears_nothing(tmp_path: Path) -> None:
    """A finished review whose judgement no one can read is #41's own shape."""
    outcome = _rung(_stage(tmp_path, verdict=None))

    assert _kind(outcome) == "no_verdict"
    found = outcome.refusal.found
    assert "dispatch=d-review-1" in found
    assert any(str(line).startswith("expected=") for line in found)


def test_a_verdict_that_will_not_parse_refuses_by_name(tmp_path: Path) -> None:
    """The record exists and cannot be read — never a silence that reads as approval."""
    outcome = _rung(_stage(tmp_path, verdict="{ nope"))

    assert _kind(outcome) == "verdict_unreadable"


def test_a_verdict_for_another_issue_does_not_clear_this_landing(tmp_path: Path) -> None:
    """`verify` derives on the verdict's own issue, so this rung checks whose work first."""
    outcome = _rung(_stage(tmp_path, verdict=_verdict(issue=999)))

    assert _kind(outcome) == "review_issue_mismatch"
    assert "asked_issue=334" in outcome.refusal.found


def test_a_verdict_for_another_commit_does_not_clear_this_one(tmp_path: Path) -> None:
    """#332's binding, enforced here rather than re-derived: both SHAs named."""
    outcome = _rung(_stage(tmp_path, verdict=_verdict(sha=OTHER_SHA)))

    refusal = outcome.refusal
    assert refusal.kind == "sha_mismatch"
    assert f"asked={SHA}" in refusal.found
    assert f"reviewed={OTHER_SHA}" in refusal.found


def test_a_verdict_claiming_an_identity_the_records_do_not_derive(tmp_path: Path) -> None:
    """The dispatch, the profile and the lane are the derivation's to say, not the record's."""
    outcome = _rung(_stage(tmp_path, verdict=_verdict(profile="opus-max")))

    refusal = outcome.refusal
    assert refusal.kind == "identity_mismatch"
    assert "claimed=d-review-1 profile=opus-max lane=codex" in refusal.found


# ------------------------------------------------------------- the authorship floor


def test_the_reviewer_the_records_place_on_the_work_cannot_clear_it(tmp_path: Path) -> None:
    """The proposer approving itself — ruling 4's second criterion, on #322's potential set."""
    outcome = _rung(
        _stage(
            tmp_path,
            records=(
                (
                    "d-author-1",
                    "dispatch.json",
                    json.dumps(
                        {
                            "seat": "implementer",
                            "issue": ISSUE,
                            "profile": REVIEWER,
                            "dispatch_id": "d-author-1",
                        }
                    ),
                ),
            ),
        )
    )

    refusal = outcome.refusal
    assert refusal.kind == "review_same_profile"
    assert "reviewer_profile=codex-luna-max" in refusal.found
    assert "authored_by=d-author-1" in refusal.found


def test_an_authorship_scan_that_could_not_read_every_record_refuses(tmp_path: Path) -> None:
    """A partial read is never a complete one.

    The separation is not the records' to give while one of them stays closed —
    #322's partial read under #41's rule. The authoring record's plan reads cleanly
    and its seat walks past the binding scan, which never opens a non-candidate's
    `result.json`; the authorship scan does, and a `result.json` that will not
    parse is exactly the gap between the two.
    """
    outcome = _rung(
        _stage(
            tmp_path,
            records=(
                (
                    "d-author-1",
                    "dispatch.json",
                    json.dumps(
                        {
                            "seat": "implementer",
                            "issue": ISSUE,
                            "profile": "opus-high",
                            "dispatch_id": "d-author-1",
                        }
                    ),
                ),
                ("d-author-1", "result.json", "not json"),
            ),
        )
    )

    refusal = outcome.refusal
    assert refusal.kind == "records_unreadable"
    assert "why=records_unreadable" in refusal.found


def test_the_clearance_names_the_profiles_the_authorship_scan_read(tmp_path: Path) -> None:
    """`checked` beside the profiles the records place on the work — the one clearing state."""
    checked = _rung(_stage(tmp_path))

    assert checked.refusal is None
    assert "authorship=checked potential=opus-high" in checked.cleared


def test_records_naming_no_author_at_all_clear_nothing(tmp_path: Path) -> None:
    """An empty potential set is not the separation; it is the absence of the check.

    The arrangement is live rather than hypothetical: an agent writes the change in
    its own session — the orchestrator's own fixes, a retro's docs work, work #294
    bars a dispatched session from — then dispatches `--seat review --reviewing X`.
    Round 1 read `binding.profile in ()` as false and cleared, with the reviewing
    profile free to be the authoring one, and `just dispatch` does not catch it
    either: `review_subject_contradicted` fires only on a complete read (claim 1).
    """
    outcome = _rung(_stage(tmp_path, author=None))

    refusal = outcome.refusal
    assert refusal.kind == "authorship_unrecorded"
    assert "why=no_authoring_dispatch" in refusal.found
    assert "reviewer_profile=codex-luna-max" in refusal.found


def test_an_issue_with_no_dispatch_records_at_all_clears_nothing(tmp_path: Path) -> None:
    """The other empty read — records exist, none of them on this issue — refuses alike."""
    outcome = _rung(
        _stage(
            tmp_path,
            author=None,
            records=(
                (
                    "d-elsewhere",
                    "dispatch.json",
                    json.dumps(
                        {
                            "seat": "implementer",
                            "issue": ISSUE + 1,
                            "profile": "opus-high",
                            "dispatch_id": "d-elsewhere",
                        }
                    ),
                ),
            ),
        )
    )

    assert _kind(outcome) == "authorship_unrecorded"


def test_an_unreadable_scan_keeps_its_own_kind_with_nothing_read(tmp_path: Path) -> None:
    """Unreadable outranks empty: the two refusals stay one fact apiece.

    A scan that read no profile *and* could not read a record is `records_unreadable`,
    not `authorship_unrecorded` — "the records would not open" and "the records say
    nothing" are different things to go and do.
    """
    outcome = _rung(
        _stage(
            tmp_path,
            author=None,
            records=(
                ("d-author-2", "dispatch.json", _authoring("opus-high").replace("opus-high", "")),
                ("d-author-2", "result.json", "not json"),
            ),
        )
    )

    assert _kind(outcome) == "records_unreadable"


# --------------------------------------------------------------- the adjudications


def test_findings_above_low_with_no_loop_state_refuses_by_name(tmp_path: Path) -> None:
    """A review that found something is not a clearance until each finding owes its route."""
    outcome = _rung(_stage(tmp_path, verdict=_verdict(findings=(("f1", "high"),)), loop=None))

    refusal = outcome.refusal
    assert refusal.kind == "no_review_loop"
    assert "finding=f1:high" in refusal.found


def test_an_unparseable_loop_state_refuses_by_name(tmp_path: Path) -> None:
    outcome = _rung(_stage(tmp_path, verdict=_verdict(findings=(("f1", "high"),)), loop="{ nope"))

    assert _kind(outcome) == "review_loop_unreadable"


def test_a_loop_of_a_later_version_refuses_rather_than_governs(tmp_path: Path) -> None:
    """A version this reader does not know is a shape it cannot safely read."""
    later = json.dumps({"version": 2, "issue": ISSUE, "review_rounds": 1, "findings": []})
    outcome = _rung(_stage(tmp_path, verdict=_verdict(findings=(("f1", "high"),)), loop=later))

    refusal = outcome.refusal
    assert refusal.kind == "review_loop_unreadable"
    assert "version 1" in str(
        next(line for line in refusal.found if str(line).startswith("reason="))
    )


def test_a_loop_recorded_for_another_issue_does_not_govern_this_one(tmp_path: Path) -> None:
    outcome = _rung(_stage(tmp_path, loop=_loop(issue=999)))

    assert _kind(outcome) == "review_loop_unreadable"


def test_a_loop_severity_disagreeing_with_its_verdict_refuses_by_name(tmp_path: Path) -> None:
    """One of the two records has been edited or drifted, and neither is reconciled by hand."""
    outcome = _rung(
        _stage(
            tmp_path,
            verdict=_verdict(findings=(("f1", "high"),)),
            loop=_loop(findings=(_stored("f1", "medium"),)),
        )
    )

    refusal = outcome.refusal
    assert refusal.kind == "review_finding_mismatch"
    assert "finding=f1 verdict=high loop=medium" in refusal.found


def test_a_verdict_finding_the_loop_holds_open_refuses_by_name(tmp_path: Path) -> None:
    """The finding is known and owed its route — `source=verdict`, the verdict's own claim."""
    outcome = _rung(
        _stage(
            tmp_path,
            verdict=_verdict(findings=(("f1", "high"),)),
            loop=_loop(findings=(_stored("f1", "high"),)),
        )
    )

    refusal = outcome.refusal
    assert refusal.kind == "finding_unadjudicated"
    assert "finding=f1 severity=high source=verdict" in refusal.found


def test_a_verdict_finding_the_loop_does_not_hold_refuses_by_name(tmp_path: Path) -> None:
    """A verdict reporting a finding no loop carries — neither record governs the other."""
    outcome = _rung(
        _stage(tmp_path, verdict=_verdict(findings=(("f1", "high"),)), loop=_loop(findings=()))
    )

    refusal = outcome.refusal
    assert refusal.kind == "finding_unadjudicated"
    assert "finding=f1 severity=high source=verdict" in refusal.found


def test_a_loop_finding_a_clean_verdict_never_reported_still_owes_its_route(
    tmp_path: Path,
) -> None:
    """An earlier round's finding, whose adjudication is owed all the same: `source=loop`."""
    outcome = _rung(_stage(tmp_path, loop=_loop(findings=(_stored("f1", "high"),))))

    refusal = outcome.refusal
    assert refusal.kind == "finding_unadjudicated"
    assert "finding=f1 severity=high round=0 source=loop" in refusal.found


# ----------------------------------------------- the fourth route and its restrictions


def test_the_fourth_route_above_medium_does_not_govern_the_landing(tmp_path: Path) -> None:
    """Above Medium, `accepted_and_filed` is not an adjudication at all.

    The rebuild refuses the whole loop rather than the one finding (human ruling
    2026-08-14, #334).
    """
    outcome = _rung(
        _stage(
            tmp_path,
            verdict=_verdict(findings=(("f1", "high"),)),
            loop=_loop(findings=(_stored("f1", "high", route="accepted_and_filed"),)),
        )
    )

    refusal = outcome.refusal
    assert refusal.kind == "review_loop_unreadable"
    assert "medium and below only" in str(
        next(line for line in refusal.found if str(line).startswith("reason="))
    )


def test_the_fourth_route_without_its_named_issue_does_not_govern(tmp_path: Path) -> None:
    outcome = _rung(
        _stage(
            tmp_path,
            verdict=_verdict(findings=(("f1", "medium"),)),
            loop=_loop(
                findings=(
                    _stored(
                        "f1", "medium", route="accepted_and_filed", conditional_on="the later work"
                    ),
                )
            ),
        )
    )

    refusal = outcome.refusal
    assert refusal.kind == "review_loop_unreadable"
    assert "must name the issue" in str(
        next(line for line in refusal.found if str(line).startswith("reason="))
    )


def test_the_fourth_route_without_its_named_condition_does_not_govern(tmp_path: Path) -> None:
    outcome = _rung(
        _stage(
            tmp_path,
            verdict=_verdict(findings=(("f1", "medium"),)),
            loop=_loop(
                findings=(_stored("f1", "medium", route="accepted_and_filed", issue="999"),)
            ),
        )
    )

    refusal = outcome.refusal
    assert refusal.kind == "review_loop_unreadable"
    assert "must name the work outside the diff" in str(
        next(line for line in refusal.found if str(line).startswith("reason="))
    )


def test_an_unknown_route_is_not_an_adjudication(tmp_path: Path) -> None:
    outcome = _rung(
        _stage(
            tmp_path,
            verdict=_verdict(findings=(("f1", "high"),)),
            loop=_loop(findings=(_stored("f1", "high", route="waved_through"),)),
        )
    )

    assert _kind(outcome) == "review_loop_unreadable"


# ------------------------------------------------------------------- the clearances


def test_a_clean_review_clears_without_a_loop(tmp_path: Path) -> None:
    """The clearance quotes the dispatch, the identity, the SHA and the honest authorship."""
    outcome = _rung(_stage(tmp_path))

    assert outcome.refusal is None
    cleared = outcome.cleared
    assert "review_dispatch=d-review-1 profile=codex-luna-max lane=codex" in cleared
    assert f"verdict_sha={SHA}" in cleared
    assert "findings=0 above_low=0 open_above_low=0" in cleared
    assert "loop=not_needed reason=no_finding_above_low" in cleared


def test_low_findings_adjudicate_nothing(tmp_path: Path) -> None:
    """Low is below the stop condition's band: no loop, no route, no refusal."""
    outcome = _rung(_stage(tmp_path, verdict=_verdict(findings=(("f1", "low"),))))

    assert outcome.refusal is None
    cleared = outcome.cleared
    assert "findings=1 above_low=0 open_above_low=0" in cleared
    assert "loop=not_needed reason=no_finding_above_low" in cleared


def test_a_fixed_finding_clears_the_landing(tmp_path: Path) -> None:
    """The plainest route, and the clearance names the loop it read the adjudication from."""
    outcome = _rung(
        _stage(
            tmp_path,
            verdict=_verdict(findings=(("f1", "high"),)),
            loop=_loop(findings=(_stored("f1", "high", route="fixed"),)),
        )
    )

    assert outcome.refusal is None
    cleared = outcome.cleared
    assert "findings=1 above_low=1 open_above_low=0" in cleared
    assert any(
        str(line).startswith("loop=") and str(line).endswith("loop.json") for line in cleared
    )


def test_the_arbiter_routes_clear_the_landing(tmp_path: Path) -> None:
    """Upheld and dismissed alike: the arbiter's is a terminal route (#333's terminus)."""
    for route in ("arbiter_upheld", "arbiter_dismissed"):
        outcome = _rung(
            _stage(
                tmp_path,
                verdict=_verdict(findings=(("f1", "critical"),)),
                loop=_loop(findings=(_stored("f1", "critical", route=route),)),
            )
        )
        assert outcome.refusal is None, route


def test_the_fourth_route_clears_at_medium_with_both_names(tmp_path: Path) -> None:
    """Accepted, filed as a named issue, conditional on named work outside the diff."""
    outcome = _rung(
        _stage(
            tmp_path,
            verdict=_verdict(findings=(("f1", "medium"),)),
            loop=_loop(
                findings=(
                    _stored(
                        "f1",
                        "medium",
                        route="accepted_and_filed",
                        issue="999",
                        conditional_on="the later work",
                    ),
                )
            ),
        )
    )

    assert outcome.refusal is None
    assert "findings=1 above_low=1 open_above_low=0" in outcome.cleared


def test_an_alternate_review_is_named_on_the_clearance(tmp_path: Path) -> None:
    """Where more than one completed dispatch bound, the skipped-past one is not discarded."""
    outcome = _rung(
        _stage(
            tmp_path,
            records=(
                ("d-review-0", "dispatch.json", _plan(dispatch_id="d-review-0")),
                ("d-review-0", "result.json", RESULT),
                ("d-review-0", "verdict.json", _verdict(dispatch="d-review-0")),
                (
                    "d-review-1",
                    "dispatch.json",
                    _plan(planned_at="20260815T0200Z"),
                ),
            ),
        )
    )

    assert outcome.refusal is None
    assert "alternates=d-review-0" in outcome.cleared


def test_a_tree_that_serves_no_issue_cannot_have_a_review_read_for_it(tmp_path: Path) -> None:
    """The worktree's own name is the protocol's record of what the landing serves."""
    outcome = _rung(_stage(tmp_path), issue=None)

    refusal = outcome.refusal
    assert refusal.kind == "review_issue_unknown"
    assert "issue=unknown" in refusal.found


# ------------------------------------------------------------------- the exemptions


def test_an_exempt_diff_clears_on_the_table_alone(tmp_path: Path) -> None:
    """The one landing that consults no record: every path matched a listing.

    The clearance states the reasons it matched — with the dispatch directory
    absent, so the exemption is the only thing that can be clearing this.
    """
    outcome = _rung(
        (tmp_path / "none", tmp_path / "review"),
        paths=("docs/design.md",),
        exemptions=TABLE,
    )

    assert outcome.refusal is None
    cleared = outcome.cleared
    assert "review=exempt" in cleared
    assert (
        "exempt=docs/design.md reason=prose is reviewed in the issue that asked for it" in cleared
    )


def test_one_unlisted_path_loses_the_whole_diff_its_exemption(tmp_path: Path) -> None:
    """Exemption is earned per landing, not per path: the unlisted one is named."""
    outcome = _rung(
        (tmp_path / "none", tmp_path / "review"),
        paths=("docs/design.md", "src/cti_daemon/daemon.py"),
        exemptions=TABLE,
    )

    assert _kind(outcome) == "no_dispatch_records"


def test_a_diff_touching_the_table_itself_is_never_exempt_under_it(tmp_path: Path) -> None:
    """Ruling 4's self-exemption refusal, from the decision the rung leans on."""
    outcome = _rung(
        (tmp_path / "none", tmp_path / "review"),
        paths=("config/review-exemptions.json",),
        exemptions=TABLE,
    )

    assert _kind(outcome) == "no_dispatch_records"


def test_an_unreadable_table_exempts_nothing(tmp_path: Path) -> None:
    """`origin/main` unreadable is the landing's own default state, fail-closed."""
    outcome = _rung(
        (tmp_path / "none", tmp_path / "review"), paths=("docs/design.md",), exemptions=None
    )

    assert _kind(outcome) == "no_dispatch_records"


def test_a_malformed_table_exempts_nothing(tmp_path: Path) -> None:
    outcome = _rung(
        (tmp_path / "none", tmp_path / "review"),
        paths=("docs/design.md",),
        exemptions="{ broken",
    )

    assert _kind(outcome) == "no_dispatch_records"


def test_a_decision_with_no_paths_is_not_vacuously_exempt(tmp_path: Path) -> None:
    """`all()` over an empty diff would return the fail-open answer; the guard refuses it."""
    outcome = _rung((tmp_path / "none", tmp_path / "review"), paths=(), exemptions=TABLE)

    assert _kind(outcome) == "no_dispatch_records"


# --------------------------------------------------- the stored loop, read directly


def test_a_round_stamp_beyond_the_rounds_recorded_refuses() -> None:
    """A finding stamped at a round the loop never reached cannot have been written."""
    with pytest.raises(ValueError, match="round"):
        land_review.parse_stored_loop(
            json.loads(_loop(rounds=1, findings=(_stored("f1", "high", round_raised=2),))),
            ISSUE,
        )


def test_a_finding_id_may_not_appear_in_two_rounds() -> None:
    """The reopening ruling 4 forbids, wearing the id it re-opened."""
    with pytest.raises(ValueError, match="one round only"):
        land_review.parse_stored_loop(
            json.loads(
                _loop(
                    rounds=2,
                    findings=(_stored("f1", "high", 0), _stored("f1", "high", 1)),
                )
            ),
            ISSUE,
        )


def test_a_multiround_loop_rebuilds_in_order() -> None:
    """Round zero's finding closed through `fixed`, round one's left open.

    The rebuild carries both, and the stop condition reads every round — the loop
    owes its route.
    """
    loop = land_review.parse_stored_loop(
        json.loads(
            _loop(
                rounds=2,
                findings=(
                    _stored("f1", "high", 0, route="fixed"),
                    _stored("f2", "medium", 1),
                ),
            )
        ),
        ISSUE,
    )

    assert loop.review_rounds == 2
    assert tuple(finding.id for finding in review_loop.open_findings(loop)) == ("f2",)


# ------------------------------------------------------- the drift, in both directions


def test_a_loop_severity_above_a_verdicts_low_is_still_drift(tmp_path: Path) -> None:
    """The disagreement is checked over every finding, not only the verdict's above-Low set.

    Round 1 compared the loop against `above`, so drift in this direction — the verdict
    rates a finding Low, the loop rates it Critical — left the mismatch check with
    nothing to compare, cleared, and printed `above_low=0` while the loop's own record
    of the same finding was Critical (round 1 claim 7).
    """
    outcome = _rung(
        _stage(
            tmp_path,
            verdict=_verdict(findings=(("f1", "low"),)),
            loop=_loop(findings=(_stored("f1", "critical", route="fixed"),)),
        )
    )

    refusal = outcome.refusal
    assert refusal.kind == "review_finding_mismatch"
    assert "finding=f1 verdict=low loop=critical" in refusal.found


def test_the_clearance_carries_both_limits_it_is_quoted_under(tmp_path: Path) -> None:
    """A lander quotes these lines into an issue, so the qualifications travel with them.

    `SAME_USER_LIMIT` is `review_exchange`'s, printed beside every recorded verdict and
    round 1 dropped from the clearance; `LOOP_RECORD_LIMIT` is this module's, and states
    the asymmetry the docstring derives — the verdict's identity is re-derived at read
    time and the loop's routes are not (round 1 claims 3 and 4).
    """
    outcome = _rung(
        _stage(
            tmp_path,
            verdict=_verdict(findings=(("f1", "high"),)),
            loop=_loop(findings=(_stored("f1", "high", route="fixed"),)),
        )
    )

    assert outcome.refusal is None
    assert review_exchange.SAME_USER_LIMIT in outcome.cleared
    assert land_review.LOOP_RECORD_LIMIT in outcome.cleared


def test_a_clean_clearance_carries_the_same_user_limit(tmp_path: Path) -> None:
    """The loop-less clearance is quoted the same way and carries the same qualification."""
    outcome = _rung(_stage(tmp_path))

    assert outcome.refusal is None
    assert review_exchange.SAME_USER_LIMIT in outcome.cleared


# ------------------------------------------------------------------ the loop's writer


def _loop_root(tmp_path: Path) -> Path:
    return tmp_path / "review"


def test_sync_opens_the_loop_from_the_verdicts_own_findings(tmp_path: Path) -> None:
    """The severities are the reviewer's: `sync` copies the record, never a flag."""
    dispatch_root, review_root = _stage(
        tmp_path, verdict=_verdict(findings=(("f1", "high"), ("f2", "low")))
    )

    report = land_review.sync(ISSUE, SHA, dispatch_root, review_root)

    assert report.code == 0
    assert "ok=opened" in report.lines
    loop = land_review.load_loop(review_root, ISSUE)
    assert [(f.id, f.severity, f.round_raised) for f in loop.findings] == [
        ("f1", "high", 0),
        ("f2", "low", 0),
    ]
    assert loop.review_rounds == 0


def test_sync_is_a_no_op_where_the_verdict_holds_nothing_new(tmp_path: Path) -> None:
    """Re-running against the same verdict records no round — nothing new was raised."""
    dispatch_root, review_root = _stage(tmp_path, verdict=_verdict(findings=(("f1", "high"),)))
    land_review.sync(ISSUE, SHA, dispatch_root, review_root)

    again = land_review.sync(ISSUE, SHA, dispatch_root, review_root)

    assert again.code == 0
    assert "ok=loop_unchanged" in again.lines
    assert land_review.load_loop(review_root, ISSUE).review_rounds == 0


def test_sync_records_a_round_for_the_ids_the_loop_does_not_hold(tmp_path: Path) -> None:
    """A later verdict's new findings are a new round, stamped by `review_loop` itself."""
    dispatch_root, review_root = _stage(tmp_path, verdict=_verdict(findings=(("f1", "high"),)))
    land_review.sync(ISSUE, SHA, dispatch_root, review_root)
    (dispatch_root / "d-review-1" / "verdict.json").write_text(
        _verdict(findings=(("f1", "high"), ("f2", "medium"))), encoding="utf-8"
    )

    report = land_review.sync(ISSUE, SHA, dispatch_root, review_root)

    assert "ok=round_recorded" in report.lines
    loop = land_review.load_loop(review_root, ISSUE)
    assert loop.review_rounds == 1
    assert [(f.id, f.round_raised) for f in loop.findings] == [("f1", 0), ("f2", 1)]


def test_sync_refuses_a_verdict_bound_to_another_commit(tmp_path: Path) -> None:
    """The loop is opened from the verdict the landing will read, or from nothing."""
    dispatch_root, review_root = _stage(tmp_path)

    report = land_review.sync(ISSUE, OTHER_SHA, dispatch_root, review_root)

    assert report.code != 0
    assert not land_review.loop_path(review_root, ISSUE).exists()


def test_adjudicate_closes_one_finding_and_the_rung_then_clears(tmp_path: Path) -> None:
    """The writer's record is the reader's: what `adjudicate` writes, `just land` reads."""
    roots = _stage(tmp_path, verdict=_verdict(findings=(("f1", "high"),)))
    dispatch_root, review_root = roots
    land_review.sync(ISSUE, SHA, dispatch_root, review_root)
    assert _kind(_rung(roots)) == "finding_unadjudicated"

    report = land_review.adjudicate(ISSUE, "f1", "fixed", "", "", review_root)

    assert report.code == 0
    assert "ok=adjudicated" in report.lines
    assert _rung(roots).refusal is None


def test_adjudicate_refuses_a_second_verdict_on_one_finding(tmp_path: Path) -> None:
    """Terminal is terminal — `review_loop`'s one-verdict-then-closed rule, unduplicated."""
    dispatch_root, review_root = _stage(tmp_path, verdict=_verdict(findings=(("f1", "high"),)))
    land_review.sync(ISSUE, SHA, dispatch_root, review_root)
    land_review.adjudicate(ISSUE, "f1", "fixed", "", "", review_root)

    report = land_review.adjudicate(ISSUE, "f1", "arbiter_dismissed", "", "", review_root)

    assert report.code != 0
    assert any(line.startswith("refusal=adjudication_refused") for line in report.lines)
    assert land_review.load_loop(review_root, ISSUE).findings[0].adjudication.route == "fixed"


def test_adjudicate_refuses_the_fourth_route_above_medium(tmp_path: Path) -> None:
    """The restrictions are the ruling's, decided in `review_loop` and not re-stated here."""
    dispatch_root, review_root = _stage(tmp_path, verdict=_verdict(findings=(("f1", "high"),)))
    land_review.sync(ISSUE, SHA, dispatch_root, review_root)

    report = land_review.adjudicate(ISSUE, "f1", "accepted_and_filed", "999", "later", review_root)

    assert report.code != 0
    assert land_review.load_loop(review_root, ISSUE).findings[0].adjudication is None


def test_adjudicate_without_a_loop_names_how_to_open_one(tmp_path: Path) -> None:
    """The refusal a seat meets first, and the remedy it names is a command that exists."""
    report = land_review.adjudicate(ISSUE, "f1", "fixed", "", "", _loop_root(tmp_path))

    assert report.code != 0
    assert any("just review-loop sync" in line for line in report.lines)


def test_show_reads_the_loop_without_writing_to_it(tmp_path: Path) -> None:
    """A read is a read: every finding, the open count, and the stop condition's verdict."""
    dispatch_root, review_root = _stage(
        tmp_path, verdict=_verdict(findings=(("f1", "high"), ("f2", "low")))
    )
    land_review.sync(ISSUE, SHA, dispatch_root, review_root)
    before = land_review.loop_path(review_root, ISSUE).read_text(encoding="utf-8")

    report = land_review.show(ISSUE, review_root)

    assert report.code == 0
    assert "finding=f1 severity=high round=0 adjudication=open" in report.lines
    assert "open_above_low=1" in report.lines
    assert "stop_condition=not_met" in report.lines
    assert land_review.loop_path(review_root, ISSUE).read_text(encoding="utf-8") == before


def test_a_written_loop_reads_back_through_the_readers_own_gates(tmp_path: Path) -> None:
    """The round trip is the contract: whatever the writer writes, `load_loop` accepts."""
    dispatch_root, review_root = _stage(
        tmp_path, verdict=_verdict(findings=(("f1", "medium"), ("f2", "critical")))
    )
    land_review.sync(ISSUE, SHA, dispatch_root, review_root)
    land_review.adjudicate(
        ISSUE, "f1", "accepted_and_filed", "999", "the later caller", review_root
    )
    land_review.adjudicate(ISSUE, "f2", "arbiter_upheld", "", "", review_root)

    loop = land_review.load_loop(review_root, ISSUE)

    assert review_loop.stop_condition(loop)
    assert loop.findings[0].adjudication.issue == "999"
    assert loop.findings[0].adjudication.conditional_on == "the later caller"
