"""The never-alone rung's ladder: every way a landing can lack its review, by name (#334).

ADR-0071 ruling 4's three criteria, enforced at `just land`'s third gate through
`tools/land_review.py`: a review dispatch record for the landed SHA whose identity
derives from the records (`review_exchange`), a reviewer the issue's own dispatch
records do not place on the work (`dispatch`), and every finding above Low closed
through one of the four routes (`review_loop`). All three are staged here from the
records the owning tools write, so each refusal is asserted by its own kind and its
own words — the same two-layer shape `test_land.py` gives the protocol's other
rungs (#83's precedent: a classification bug should be a red `just unit`).

The loop state read here is #333's `loop.json`, read through #333's own reader: round 1's
local copy of that parser is deleted, and the round trip across the two tools is asserted
rather than assumed (round 2).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

from conftest import load_tool

if TYPE_CHECKING:
    from pathlib import Path

land_review = load_tool("land_review")
review_loop = load_tool("review_loop")
review_exchange = load_tool("review_exchange")

SHA: Final = "a" * 40
OTHER_SHA: Final = "b" * 40
PATCH: Final = "c" * 40
OTHER_PATCH: Final = "d" * 40
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
    lane: str = "codex",
) -> str:
    """One dispatch record, written the shape `tools/dispatch.py` writes it."""
    return json.dumps(
        {
            "seat": seat,
            "issue": issue,
            "base_sha": base_sha,
            "profile": profile,
            "lane": lane,
            "planned_at": planned_at,
            "dispatch_id": dispatch_id,
        }
    )


def _verdict(  # noqa: PLR0913 — one parameter per field of the record under test
    *,
    issue: int = ISSUE,
    sha: str = SHA,
    patch_id: str = PATCH,
    dispatch: str = "d-review-1",
    profile: str = REVIEWER,
    findings: tuple[tuple[str, str], ...] = (),
    alternates: tuple[str, ...] = (),
    lane: str = "codex",
) -> str:
    """One verdict record, written the shape `review_exchange.record_verdict` writes it."""
    return json.dumps(
        {
            "version": 1,
            "issue": issue,
            "reviewed_sha": sha,
            "patch_id": patch_id,
            "review_dispatch": dispatch,
            "reviewer_profile": profile,
            "reviewer_lane": lane,
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
    arbiter: str = "",
) -> dict[str, object]:
    """One stored loop finding, open unless a route closes it."""
    finding: dict[str, object] = {
        "id": identifier,
        "severity": severity,
        "round_raised": round_raised,
    }
    if route is not None:
        finding["adjudication"] = {
            "route": route,
            "issue": issue,
            "conditional_on": conditional_on,
            "arbiter": arbiter,
        }
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


ARBITER: Final = "opus-xhigh"


def _escalation(
    *,
    arbiter: str = ARBITER,
    evaluation: str = "firing",
    unchecked: bool = False,
    conditions: tuple[int, ...] = (1,),
) -> str:
    """One escalation record, the shape `just review-loop escalate` writes it."""
    return json.dumps(
        {
            "version": 1,
            "issue": ISSUE,
            "evaluation": evaluation,
            "conditions": list(conditions),
            "arbiter": arbiter,
            "unchecked": unchecked,
            "passed_over": [],
        }
    )


def _stage(  # noqa: PLR0913 — one parameter per record the rung reads
    tmp_path: Path,
    *,
    plan: str | None = _PLAN_TEXT,
    result: str | None = RESULT,
    verdict: str | None = _VERDICT_TEXT,
    loop: str | None = None,
    escalation: str | None = None,
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

    `escalation` writes the record `just review-loop escalate` leaves beside the loop,
    which is what authorises an arbiter route; it defaults to absent, because the
    landings that carry no arbiter route never read it.

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
    if escalation is not None:
        recorded = review_root / str(ISSUE) / review_loop.ESCALATION_FILE
        recorded.parent.mkdir(parents=True, exist_ok=True)
        recorded.write_text(escalation, encoding="utf-8")
    for name, filename, text in records:
        extra = dispatch_root / name
        extra.mkdir(parents=True, exist_ok=True)
        (extra / filename).write_text(text, encoding="utf-8")
    return dispatch_root, review_root


def _rung(  # noqa: PLR0913 — one keyword per input the rung reads, as the rung has
    roots: tuple[Path, Path],
    *,
    issue: int | None = ISSUE,
    sha: str = SHA,
    patch_id: str | None = None,
    paths: tuple[str, ...] | None = ("tools/worker.py",),
    gate_paths: tuple[str, ...] | None = (),
    exemptions: str | None = None,
) -> land_review.Outcome:
    """Call the rung over staged roots.

    `exemptions=None` is the unreadable table — the state a landing is in wherever
    `origin/main` carries no table, which exempts nothing and so falls into the
    ladder every default here exercises.

    `gate_paths=()` is the caller's read of routing class 6 against this diff, and the
    default is the ordinary landing: `tools/worker.py` is not a gate, so ADR-0073's
    cross-lane predicate does not apply and every rung below it is what it was. The
    cross-lane tests name their own gate paths.

    `patch_id=None` is the landing that cannot state its own diff's hash; the tests
    that clear over a moved SHA (#417) name the patch-id the verdict carries.
    """
    dispatch_root, review_root = roots
    return land_review.review_finding(
        issue, sha, paths, gate_paths, exemptions, dispatch_root, review_root, patch_id
    )


def _kind(outcome: land_review.Outcome) -> str:
    assert outcome is not None
    refusal = outcome.refusal
    assert refusal is not None
    return refusal.kind


def _text(outcome: land_review.Outcome) -> str:
    """Join the refusal's evidence lines, so a test can assert a term is among them."""
    assert outcome.refusal is not None
    return "\n".join(outcome.refusal.found)


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
    """#332's binding as #417 widened it: both SHAs and both patch-ids named."""
    outcome = _rung(_stage(tmp_path, verdict=_verdict(sha=OTHER_SHA)), patch_id=OTHER_PATCH)

    refusal = outcome.refusal
    assert refusal.kind == "sha_mismatch"
    assert f"asked={SHA}" in refusal.found
    assert f"reviewed={OTHER_SHA}" in refusal.found
    assert f"patch_id=mismatch asked={OTHER_PATCH} reviewed={PATCH}" in refusal.found


def test_a_clean_rebase_carries_the_verdict_across_on_the_patch_id(tmp_path: Path) -> None:
    """#417's clearance: the SHA moved and the diff did not, so the review rides.

    The plan and verdict both name the reviewed SHA; the landing names the SHA the
    rebase produced and the patch-id of the diff it still is. The identity derives
    against the verdict's own SHA, never the landing's, so the reviewer of record is
    the one who reviewed the diff — not whoever the landing would rather name.
    """
    outcome = _rung(_stage(tmp_path), sha=OTHER_SHA, patch_id=PATCH)

    assert outcome.refusal is None
    cleared = "\n".join(outcome.cleared)
    assert f"carried_by=patch_id {PATCH}" in cleared
    assert review_exchange.PATCH_ID_LIMIT in cleared


def test_a_conflict_resolved_rebase_changes_the_patch_and_forces_re_review(
    tmp_path: Path,
) -> None:
    """A hand that resolved a conflict changed the diff, and patch-id equality notices."""
    outcome = _rung(_stage(tmp_path), sha=OTHER_SHA, patch_id=OTHER_PATCH)

    refusal = outcome.refusal
    assert refusal.kind == "sha_mismatch"
    assert f"patch_id=mismatch asked={OTHER_PATCH} reviewed={PATCH}" in refusal.found


def test_a_moved_sha_with_no_landing_patch_id_refuses_rather_than_guess(
    tmp_path: Path,
) -> None:
    """The half that carries across a rebase could not run, so it did not pass (#41)."""
    outcome = _rung(_stage(tmp_path), sha=OTHER_SHA)

    assert _kind(outcome) == "patch_id_unreadable"
    assert f"landing_patch_id={None!r}" in outcome.refusal.found


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

    The read refuses the whole loop rather than the one finding (human ruling 2026-08-14,
    #334). The canonical parser leaves the routes' preconditions to the act of
    adjudicating, so this rung asks `stored_route_violations` for the fourth route's three
    restrictions, which are about what the disposition means rather than about when it may
    be given (round 2).
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
        next(line for line in refusal.found if str(line).startswith("invalid="))
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
        next(line for line in refusal.found if str(line).startswith("invalid="))
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
        next(line for line in refusal.found if str(line).startswith("invalid="))
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
    """Upheld and dismissed alike: the arbiter's is a terminal route (#333's terminus).

    Each naming the arbiter that ruled, which is what the route means and what the writer
    records (round 2, Medium 2); the unnamed shape has its own refusal below.
    """
    for route in ("arbiter_upheld", "arbiter_dismissed"):
        outcome = _rung(
            _stage(
                tmp_path,
                verdict=_verdict(findings=(("f1", "critical"),)),
                loop=_loop(findings=(_stored("f1", "critical", route=route, arbiter=ARBITER),)),
                escalation=_escalation(),
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


# ------------------------------------------------- the arbiter the record has to name


def test_an_arbiter_route_naming_no_arbiter_refuses_the_landing(tmp_path: Path) -> None:
    """A route standing in for a ruling, with no judge on the record (round 2, Medium 2).

    `just review-loop adjudicate` will not write this — it fills the name from the
    escalation record and refuses without one — so what reaches the landing this way is a
    hand-edited loop, which is the reader's business rather than the writer's: a reader of
    a record must not assume its writer.
    """
    outcome = _rung(
        _stage(
            tmp_path,
            verdict=_verdict(findings=(("f1", "critical"),)),
            loop=_loop(findings=(_stored("f1", "critical", route="arbiter_dismissed"),)),
        )
    )

    refusal = outcome.refusal
    assert refusal.kind == "arbiter_unnamed"
    assert "finding=f1 severity=critical route=arbiter_dismissed" in refusal.found


def test_an_arbiter_route_that_names_its_arbiter_clears(tmp_path: Path) -> None:
    """The other side of the same check: the shape the writer produces is not refused.

    Which is the escalation record *and* the name — round 2 asserted this arrangement
    with no escalation record at all, and so pinned as correct exactly the state the
    terminus over the same loop refuses (round 2 re-review, Medium 1).
    """
    outcome = _rung(
        _stage(
            tmp_path,
            verdict=_verdict(findings=(("f1", "critical"),)),
            loop=_loop(
                findings=(_stored("f1", "critical", route="arbiter_upheld", arbiter=ARBITER),)
            ),
            escalation=_escalation(),
        )
    )

    assert outcome.refusal is None
    assert f"arbiter={ARBITER} escalation=firing unchecked=false" in outcome.cleared


def test_an_arbiter_route_no_escalation_record_authorised_refuses(tmp_path: Path) -> None:
    """The route names a judge and nothing says a wall ever transferred to one.

    Round 2 checked only that the route named an arbiter, so a hand-written
    `arbiter_dismissed` on a Critical cleared `just land` printing `open_above_low=0`
    while `just review-loop terminus` over the same loop refused it
    `ARBITER_UNRESOLVED_ERROR` — one record, two consumers, and the landing was the
    permissive one (round 2 re-review, Medium 1).
    """
    outcome = _rung(
        _stage(
            tmp_path,
            verdict=_verdict(findings=(("f1", "critical"),)),
            loop=_loop(
                findings=(_stored("f1", "critical", route="arbiter_dismissed", arbiter=ARBITER),)
            ),
        )
    )

    refusal = outcome.refusal
    assert refusal.kind == "arbiter_unresolved"
    assert "evaluation=no_record" in refusal.found
    assert "finding=f1 route=arbiter_dismissed" in refusal.found


def test_an_escalation_that_fired_nothing_authorises_no_arbiter_route(tmp_path: Path) -> None:
    """A record that resolved a profile and fired nothing transferred to it (#333 High 2)."""
    outcome = _rung(
        _stage(
            tmp_path,
            verdict=_verdict(findings=(("f1", "critical"),)),
            loop=_loop(
                findings=(_stored("f1", "critical", route="arbiter_upheld", arbiter=ARBITER),)
            ),
            escalation=_escalation(evaluation="no_firing", conditions=()),
        )
    )

    refusal = outcome.refusal
    assert refusal.kind == "arbiter_unresolved"
    assert "evaluation=no_firing" in refusal.found


def test_an_escalation_record_that_will_not_read_clears_nothing(tmp_path: Path) -> None:
    """A record that could not be read is not a record that authorised (#41)."""
    outcome = _rung(
        _stage(
            tmp_path,
            verdict=_verdict(findings=(("f1", "critical"),)),
            loop=_loop(
                findings=(_stored("f1", "critical", route="arbiter_upheld", arbiter=ARBITER),)
            ),
            escalation="{ nope",
        )
    )

    assert _kind(outcome) == "escalation_unreadable"


def test_an_arbiter_the_escalation_did_not_resolve_refuses_by_name(tmp_path: Path) -> None:
    """`adjudicate` fills the name from the record, so the two disagree only by hand."""
    outcome = _rung(
        _stage(
            tmp_path,
            verdict=_verdict(findings=(("f1", "critical"),)),
            loop=_loop(
                findings=(_stored("f1", "critical", route="arbiter_upheld", arbiter="fable-max"),)
            ),
            escalation=_escalation(),
        )
    )

    refusal = outcome.refusal
    assert refusal.kind == "arbiter_mismatch"
    assert f"resolved={ARBITER}" in refusal.found
    assert "finding=f1 arbiter=fable-max" in refusal.found


def test_a_partial_resolution_is_named_on_the_clearance_it_authorises(tmp_path: Path) -> None:
    """`unchecked` travels to the clearance a lander quotes (round 2 re-review, Low 7).

    The resolution behind an arbiter can be made with a dispatch record it could not
    open — the reason ruling 4's route is `reviewing_checked` and never
    `reviewing_verified` — and a clearance that prints the name alone records a stronger
    claim than the resolution made.
    """
    outcome = _rung(
        _stage(
            tmp_path,
            verdict=_verdict(findings=(("f1", "critical"),)),
            loop=_loop(
                findings=(_stored("f1", "critical", route="arbiter_upheld", arbiter=ARBITER),)
            ),
            escalation=_escalation(unchecked=True),
        )
    )

    assert outcome.refusal is None
    assert f"arbiter={ARBITER} escalation=firing unchecked=true" in outcome.cleared


def test_a_low_closed_by_an_unnamed_arbiter_route_does_not_block(tmp_path: Path) -> None:
    """A Low never blocks a landing, so its route decides nothing here either."""
    outcome = _rung(
        _stage(
            tmp_path,
            verdict=_verdict(findings=(("f1", "low"),)),
            loop=_loop(findings=(_stored("f1", "low", route="arbiter_dismissed"),)),
        )
    )

    assert outcome.refusal is None


# ------------------------------------------- one record, one reader (#333's, not a copy)


def test_the_rung_reads_the_loop_the_loops_own_writer_wrote(tmp_path: Path) -> None:
    """The round trip across the two tools, which is what deleting the local reader buys.

    Round 1 carried its own parser for `loop.json`; #333 landed the canonical one at
    `1a5a7fb` and this rung now calls it. The contract under test is that what
    `review_loop.store_loop` writes, `review_finding` reads — path, version and all — so a
    format change cannot land in one of the two and leave the landing reading the other.
    """
    dispatch_root, review_root = _stage(tmp_path, verdict=_verdict(findings=(("f1", "high"),)))
    loop = review_loop.adjudicate(
        review_loop.first_review((review_loop.Finding("f1", "high", 0),)),
        "f1",
        review_loop.Adjudication("fixed"),
    )
    written = review_loop.store_loop(review_root, ISSUE, loop)

    outcome = _rung((dispatch_root, review_root))

    assert written == review_loop.loop_path(review_root, ISSUE)
    assert outcome.refusal is None
    assert f"loop={written}" in outcome.cleared


# ------------------------------------- the gate paths: a cross-lane review (ADR-0073, #406)
#
# Routing class 6's keep-on-Claude bar retired on the human's instruction of 2026-08-18, and
# what replaced it is one predicate on this rung: for a landing whose diff touches a gate
# path, ruling 4's "not the same profile" becomes "not the same lane". The staging default is
# already cross-lane — `REVIEWER` is `codex-luna-max` on `codex` and `AUTHOR` is `opus-high`
# on `claude-native` — so these tests move the reviewer rather than the author, and the gate
# paths arrive as `gate_paths`, the caller's read of that row against the diff.

GATE_PATH: Final = "tools/land.py"
CLAUDE_REVIEWER: Final = "opus-xhigh"


def _gate_rung(
    roots: tuple[Path, Path],
    *,
    reviewer: str = REVIEWER,
    reviewer_lane: str = "codex",
    gate_paths: tuple[str, ...] | None = (GATE_PATH,),
    paths: tuple[str, ...] | None = (GATE_PATH,),
) -> land_review.Outcome:
    """Call the rung over a gate landing, with the reviewing dispatch's lane named."""
    dispatch_root, review_root = roots
    record = dispatch_root / "d-review-1"
    for name, text in (
        ("dispatch.json", _plan(profile=reviewer)),
        ("verdict.json", _verdict(profile=reviewer)),
    ):
        document = json.loads(text)
        document["lane" if name == "dispatch.json" else "reviewer_lane"] = reviewer_lane
        (record / name).write_text(json.dumps(document), encoding="utf-8")
    return land_review.review_finding(
        ISSUE, SHA, paths, gate_paths, None, dispatch_root, review_root
    )


def test_a_gate_landing_reviewed_from_the_authors_own_lane_refuses_by_name(
    tmp_path: Path,
) -> None:
    """The invariant the retired bar stood in for: no instance authors the gate that judges it.

    `AUTHOR` is `opus-high`, a `claude-native` profile, so a `claude-native` reviewer is on
    the author's lane even though it is a different profile — which is exactly the
    arrangement `review_same_profile` clears and this refusal does not.
    """
    outcome = _gate_rung(_stage(tmp_path), reviewer=CLAUDE_REVIEWER, reviewer_lane="claude-native")

    assert _kind(outcome) == "review_same_lane"
    found = _text(outcome)
    assert "reviewer_lane=claude-native" in found
    assert f"same_lane_authors={AUTHOR}" in found
    assert f"gate_path={GATE_PATH}" in found
    # The remedy names a cross-lane review and the command that produces one (criterion 2).
    assert "--seat review" in outcome.refusal.action
    assert "--lane <lane>" in outcome.refusal.action


def test_a_gate_landing_reviewed_from_another_lane_clears_and_says_which(tmp_path: Path) -> None:
    """The other half: `codex` reviewing `claude-native`'s gate change lands, and prints why."""
    outcome = _gate_rung(_stage(tmp_path))

    assert outcome.refusal is None
    assert (
        f"gate_review=cross_lane reviewer_lane=codex author_lanes=claude-native"
        f" gate_paths={GATE_PATH}" in outcome.cleared
    )
    assert land_review.CROSS_LANE_LIMIT in outcome.cleared


def test_a_landing_outside_the_gate_paths_is_unaffected_by_the_cross_lane_rule(
    tmp_path: Path,
) -> None:
    """Same-lane review, no gate path: cleared, and no cross-lane line claiming a check ran.

    The rule is scoped to routing class 6 rather than to every landing, so this is the
    arrangement that proves the scope — identical to the refusing one but for `gate_paths`.
    """
    outcome = _gate_rung(
        _stage(tmp_path),
        reviewer=CLAUDE_REVIEWER,
        reviewer_lane="claude-native",
        gate_paths=(),
        paths=("tools/worker.py",),
    )

    assert outcome.refusal is None
    assert not any(line.startswith("gate_review=") for line in outcome.cleared)


def test_an_author_profile_the_registry_cannot_place_refuses_rather_than_clearing(
    tmp_path: Path,
) -> None:
    """#41 on this rung: a lane that cannot be derived is not a lane that differs.

    An unregistered author profile has no lane, so the comparison cannot be made — and the
    fail-open reading, "it is not equal to the reviewer's, so clear", would pass by accident
    exactly where the records are worst.
    """
    outcome = _gate_rung(
        _stage(tmp_path, author="retired-profile-name"),
        reviewer=CLAUDE_REVIEWER,
        reviewer_lane="claude-native",
    )

    assert _kind(outcome) == "review_lane_unknown"
    assert "unplaceable_authors=retired-profile-name" in _text(outcome)
    assert "#41" in outcome.refusal.action


def test_a_reviewer_lane_the_registry_cannot_place_refuses_the_same_way(tmp_path: Path) -> None:
    """The other end of the same comparison: `parse_verdict` requires a string, not a lane."""
    outcome = _gate_rung(_stage(tmp_path), reviewer_lane="anthropic-direct")

    assert _kind(outcome) == "review_lane_unknown"
    assert "reviewer_lane_known=false" in _text(outcome)


# ------------------ #413: a renamed profile's old name, on the rung that reads the records


def test_a_reviewer_that_is_a_retired_authors_successor_cannot_clear_it(
    tmp_path: Path,
) -> None:
    """The records carry the old name, the verdict the new one, and the rung meets both.

    A plain membership test on `Authorship.potential` clears this — `zai-glm53-max` is not
    the string `zai-glm52-max` — while the dispatcher refuses the same reviewer over the
    same records. That disagreement is the trap criterion 5 names, and the fix is the same
    resolution both rungs read rather than a second rule on one side.
    """
    outcome = _rung(
        _stage(
            tmp_path,
            author="zai-glm52-max",
            plan=_plan(profile="zai-glm53-max", lane="zai"),
            verdict=_verdict(profile="zai-glm53-max", lane="zai"),
        )
    )

    assert _kind(outcome) == "review_same_profile"
    found = _text(outcome)
    assert "reviewer_profile=zai-glm53-max" in found
    assert "authored_by=d-author-1" in found


def test_a_retired_authors_gate_landing_places_its_lane_through_the_successor(
    tmp_path: Path,
) -> None:
    """`review_lane_unknown` no longer strands a renamed author's gate landing (#413).

    The remedy that refusal used to name — register the profile — is the one act a rename
    exists to make impossible, so before the retirement table there was no answer here
    either. The author's lane is the successor's lane, and a zai reviewer of zai-authored
    gate work refuses `review_same_lane` rather than clearing by unplaceability.
    """
    outcome = _gate_rung(
        _stage(tmp_path, author="zai-glm52-max"),
        reviewer="zai-glm47-max",
        reviewer_lane="zai",
    )

    assert _kind(outcome) == "review_same_lane"
    found = _text(outcome)
    assert "author_lanes=zai" in found
    assert "same_lane_authors=zai-glm52-max" in found


def test_a_retired_authors_gate_landing_clears_from_another_lane(tmp_path: Path) -> None:
    """The other half: the strand is closed in both directions, not traded for a refusal.

    #404's shape — the diff touches no gate path, but the arrangement that would have
    refused on one now clears with the author's lane placed through the successor and the
    cross-lane line stating it.
    """
    outcome = _gate_rung(_stage(tmp_path, author="zai-glm52-max"))

    assert outcome.refusal is None
    assert (
        f"gate_review=cross_lane reviewer_lane=codex author_lanes=zai"
        f" gate_paths={GATE_PATH}" in outcome.cleared
    )


def test_a_diff_that_cannot_be_placed_inside_or_outside_the_gate_paths_refuses(
    tmp_path: Path,
) -> None:
    """Neither `None` reads as "not a gate landing", because that is the fail-open answer."""
    for paths, gate_paths in (((GATE_PATH,), None), (None, (GATE_PATH,))):
        outcome = _gate_rung(_stage(tmp_path), paths=paths, gate_paths=gate_paths)

        assert _kind(outcome) == "gate_class_undetermined"
        assert "#41" in outcome.refusal.action


def test_a_gate_landing_is_not_exemptible_by_the_review_exemption_table(tmp_path: Path) -> None:
    """`binds_every_instance` forbids a routing exception; this forbids the other table's.

    `config/review-exemptions.json` is a different table, so nothing in the routing policy
    reaches it — and an entry there covering a gate path would clear a gate change with no
    review at all, which is worse than the same-lane review this rule was filed about. The
    table ships empty, so today this changes nothing; the order is what stops filling it from
    reopening the hole.
    """
    exempting = json.dumps(
        {
            "version": 1,
            "source": "test",
            "entries": [{"surface": "tools/", "reason": "planted for this test only"}],
        }
    )
    dispatch_root, review_root = _stage(tmp_path)
    outcome = land_review.review_finding(
        ISSUE, SHA, (GATE_PATH,), (GATE_PATH,), exempting, dispatch_root, review_root
    )

    assert outcome.refusal is None
    assert "review=exempt" not in outcome.cleared
    assert any(line.startswith("gate_review=cross_lane") for line in outcome.cleared)
