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
import socket
import threading
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

from conftest import load_tool, no_lane_network

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

breaker = load_tool("breaker")
land_review = load_tool("land_review")
review_loop = load_tool("review_loop")
review_exchange = load_tool("review_exchange")

SHA: Final = "a" * 40
OTHER_SHA: Final = "b" * 40
BASE_SHA: Final = "e" * 40
DIFF_ID: Final = "c" * 64
OTHER_DIFF_ID: Final = "d" * 64
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
    diff_id: str = DIFF_ID,
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
            "diff_id": diff_id,
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
    rebases: tuple[tuple[str, str], ...] = ((SHA, OTHER_SHA),),
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

    `rebases` writes the clean-rebase links `just land` records (#417), one
    `(before, after)` per replay it ran to completion without conflict. The default
    records the reviewed `SHA` reaching `OTHER_SHA`, so the tests that move the SHA
    exercise the identity half against a provenance half that holds; `rebases=()`
    withholds every link, which is the arrangement `rebase_unproven` is asserted on.
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
    for before, after in rebases:
        review_exchange.record_rebase(
            review_root,
            ISSUE,
            review_exchange.RebaseLink(before=before, after=after, base=BASE_SHA, at=STAMP),
        )
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
    diff_id: str | None = None,
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

    `diff_id=None` is the landing that cannot state its own diff's identity; the tests
    that clear over a moved SHA (#417) name the identity the verdict carries, which the
    rung reads together with the clean-rebase links `_stage` recorded.
    """
    dispatch_root, review_root = roots
    return land_review.review_finding(
        issue, sha, paths, gate_paths, exemptions, dispatch_root, review_root, diff_id
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
    """#332's binding as #417 reworked it: both SHAs and both identities named.

    The links run the other way here — the reviewed commit is `OTHER_SHA` and the
    landing asks about `SHA` — so the provenance half holds and the refusal is the
    identity's, which is the one that names what the reviewer did not see.
    """
    outcome = _rung(
        _stage(tmp_path, verdict=_verdict(sha=OTHER_SHA), rebases=((OTHER_SHA, SHA),)),
        diff_id=OTHER_DIFF_ID,
    )

    refusal = outcome.refusal
    assert refusal.kind == "sha_mismatch"
    assert f"asked={SHA}" in refusal.found
    assert f"reviewed={OTHER_SHA}" in refusal.found
    assert f"diff_id=mismatch asked={OTHER_DIFF_ID} reviewed={DIFF_ID}" in refusal.found


def test_a_recorded_clean_rebase_and_a_matching_identity_carry_the_verdict(
    tmp_path: Path,
) -> None:
    """#417's clearance, reworked: both halves hold, so the review rides.

    The plan and verdict both name the reviewed SHA; the landing names the SHA the
    rebase produced, the identity of the diff it still is, and the links `just land`
    recorded when it replayed that rebase clean. The reviewer identity derives against
    the verdict's own SHA, never the landing's, so the reviewer of record is the one
    who reviewed the diff — not whoever the landing would rather name.
    """
    outcome = _rung(_stage(tmp_path), sha=OTHER_SHA, diff_id=DIFF_ID)

    assert outcome.refusal is None
    cleared = "\n".join(outcome.cleared)
    assert f"carried_by=diff_id {DIFF_ID}" in cleared
    assert "provenance=clean_rebase_recorded" in cleared
    assert review_exchange.DIFF_ID_LIMIT in cleared


def test_a_conflict_resolved_rebase_changes_the_identity_and_forces_re_review(
    tmp_path: Path,
) -> None:
    """A hand that resolved a conflict changed the diff, and exact identity notices.

    The links are staged, so this is the residue the provenance half cannot catch —
    a replay the tooling ran clean that still reshaped the diff, by dropping a commit
    as already upstream. Only the identity half sees it, which is why both are read.
    """
    outcome = _rung(_stage(tmp_path), sha=OTHER_SHA, diff_id=OTHER_DIFF_ID)

    refusal = outcome.refusal
    assert refusal.kind == "sha_mismatch"
    assert f"diff_id=mismatch asked={OTHER_DIFF_ID} reviewed={DIFF_ID}" in refusal.found


def test_a_moved_sha_with_no_recorded_rebase_refuses_however_the_diff_hashes(
    tmp_path: Path,
) -> None:
    """The rework's whole lesson: an identical diff is not proof the replay was clean.

    Nothing recorded this commit reaching here, so a hand may have resolved a conflict
    into it — and hashing the output cannot tell. The identity matches exactly and the
    landing still refuses.
    """
    outcome = _rung(_stage(tmp_path, rebases=()), sha=OTHER_SHA, diff_id=DIFF_ID)

    assert _kind(outcome) == "rebase_unproven"
    assert "clean_rebase=no recorded chain connects the reviewed commit to this one" in _text(
        outcome
    )


def test_a_moved_sha_with_no_landing_identity_refuses_rather_than_guess(
    tmp_path: Path,
) -> None:
    """The half that carries across a rebase could not run, so it did not pass (#41)."""
    outcome = _rung(_stage(tmp_path), sha=OTHER_SHA)

    assert _kind(outcome) == "diff_id_unreadable"
    assert f"landing_diff_id={None!r}" in outcome.refusal.found


def test_a_pre_rework_verdict_refuses_by_its_own_name_not_as_unreadable(
    tmp_path: Path,
) -> None:
    """The one-time migration (#417 round 1, Medium): a `patch_id` record is named as one.

    A verdict recorded before the rework parses no further than its missing identity,
    and folding that into `verdict_unreadable` would send a reader to repair a record
    that is not corrupt. It re-reviews instead, and the refusal says so.
    """
    stale = json.loads(_verdict())
    del stale["diff_id"]
    stale["patch_id"] = "c" * 40
    outcome = _rung(_stage(tmp_path, verdict=json.dumps(stale)))

    assert _kind(outcome) == "diff_id_unreadable"
    assert "predates #417's rework" in outcome.refusal.action


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


def test_a_declared_human_review_clears_and_names_its_provenance(tmp_path: Path) -> None:
    roots = _stage(tmp_path, plan=None, result=None, verdict=None, rebases=())
    dispatch_root, review_root = roots
    recorded = review_exchange.record_human_verdict(
        ISSUE,
        SHA,
        "[]",
        dispatch_root,
        review_root=review_root,
        diff_id=DIFF_ID,
        reviewer_profile=REVIEWER,
        now=STAMP,
    )
    assert not isinstance(recorded, review_exchange.Refusal)

    outcome = _rung(roots)

    assert outcome.refusal is None
    assert "reviewer_kind=declared" in outcome.cleared
    assert "review_dispatch=none profile=codex-luna-max lane=codex" in outcome.cleared
    assert (
        land_review.attribute_registry.Relation("reviewer", "human_reviewer", REVIEWER)
        in outcome.relations
    )


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

# Two instants that decide z.ai's off-peak bar without asking this box's clock. Peak is
# Mon-Fri 14:00-18:00 SGT (UTC+8), so 07:00 UTC on a Wednesday is inside it and the same
# hour on a Saturday is outside — `tools/breaker.py`'s `zai_is_peak` is the authority and
# these two are read off it rather than off a second copy of the schedule.
PEAK: Final = datetime(2026, 8, 19, 7, 0, tzinfo=UTC)
OFF_PEAK: Final = datetime(2026, 8, 22, 7, 0, tzinfo=UTC)


def _reach(
    tmp_path: Path,
    at: datetime = OFF_PEAK,
    *,
    tripped: tuple[str, ...] = (),
    key: bool = True,
) -> land_review.LaneReach:
    """Build a `LaneReach` over scratch state, so every bar is one this test staged (#426).

    The real defaults are the box's breaker directory, its credentials file and the wall
    clock; asserting on those would make the record under test a fact about this machine
    and about the hour of the day. `tripped` opens a lane's breaker on the quota rule with
    a published reset in the future, which is the `quota_exhausted` bar the human's ruling
    names. `key=False` writes the file without `ZAI_API_KEY`, which is the third of
    `lane_bar`'s three rungs — the one arm #426 covered in `dispatch` but never composed
    through a landing (#427).

    The quota reader is the no-network one for every arrangement, so the bars asserted below
    are the staged state and nothing a provider said.
    """
    credentials = tmp_path / "credentials.env"
    credentials.write_text("ZAI_API_KEY=staged-for-this-test\n" if key else "", encoding="utf-8")
    credentials.chmod(0o600)
    directory = tmp_path / "breaker"
    for lane in tripped:
        breaker.write_state(
            directory,
            breaker.LaneState(
                lane,
                breaker.Circuit(
                    state=breaker.OPEN,
                    rule="quota",
                    reason="a 429 from the provider",
                    opened_at=at.timestamp(),
                    reset_at=at.timestamp() + 3600,
                ),
                None,
                at.timestamp(),
            ),
        )
    return land_review.LaneReach(directory, credentials, at, no_lane_network)


def _gate_rung(  # noqa: PLR0913 — one parameter per staged fact the rung reads
    roots: tuple[Path, Path],
    *,
    reviewer: str = REVIEWER,
    reviewer_lane: str = "codex",
    gate_paths: tuple[str, ...] | None = (GATE_PATH,),
    paths: tuple[str, ...] | None = (GATE_PATH,),
    reach: land_review.LaneReach | None = None,
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
        ISSUE,
        SHA,
        paths,
        gate_paths,
        None,
        dispatch_root,
        review_root,
        reach=reach or _reach(review_root.parent),
    )


# ---- #426: the lane half is a preference with a mandatory record, not a refusal


def test_a_same_lane_gate_landing_clears_and_records_that_a_free_lane_was_available(
    tmp_path: Path,
) -> None:
    """The human's ruling of 2026-08-19, and the case it is most exposed on.

    `AUTHOR` is `opus-high`, a `claude-native` profile, so a `claude-native` reviewer is on
    the author's lane even though it is a different profile. That used to refuse
    `review_same_lane`; under the ruling it clears — and because `zai` and `codex` were both
    reachable at the moment of the landing, the record says the preferred check was
    available and was not the one that ran. That is the third of the three causes, and the
    only one the ruling leaves to a person's judgement: a single flag would hide it inside
    exhaustion (#426, criterion 4).
    """
    outcome = _gate_rung(_stage(tmp_path), reviewer=CLAUDE_REVIEWER, reviewer_lane="claude-native")

    assert outcome.refusal is None
    assert (
        f"gate_review=same_lane_chosen reviewer_lane=claude-native"
        f" author_lanes=claude-native gate_paths={GATE_PATH}"
        f" same_lane_authors={AUTHOR} free_lanes=zai codex barred_lanes=none"
        f" review_dispatch=d-review-1" in outcome.cleared
    )
    assert land_review.SAME_LANE_CHOSEN_LIMIT in outcome.cleared


def test_a_same_lane_gate_landing_names_the_bar_on_every_free_lane(tmp_path: Path) -> None:
    """The second cause, and the one the ruling was actually given for (#390's shape).

    A lane no record places on this issue existed and could not be dispatched to: `zai` sat
    inside its off-peak window and `codex`'s breaker was open on quota. Both bars are named
    with the kind and the failure class `tools/dispatch.py` itself gives them, so a reader
    can tell "the window" from "a provider quota" — which the ruling asks for by name.
    """
    _, review_root = roots = _stage(tmp_path)
    outcome = _gate_rung(
        roots,
        reviewer=CLAUDE_REVIEWER,
        reviewer_lane="claude-native",
        reach=_reach(review_root.parent, PEAK, tripped=("codex",)),
    )

    assert outcome.refusal is None
    assert (
        f"gate_review=lane_barred reviewer_lane=claude-native"
        f" author_lanes=claude-native gate_paths={GATE_PATH}"
        f" same_lane_authors={AUTHOR}"
        f" barred_lanes=zai:lane_peak_hours codex:lane_breaker_open/quota_exhausted"
        in outcome.cleared
    )
    assert land_review.LANE_BARRED_LIMIT in outcome.cleared


def test_one_reachable_free_lane_is_enough_to_make_it_the_operators_choice(
    tmp_path: Path,
) -> None:
    """The boundary between the second cause and the third, moved by one lane's bar.

    Same staging as the barred case but for `codex`'s breaker, which is closed here: one
    reachable lane is a cross-lane review that could have been dispatched, so the record is
    `same_lane_chosen` and it names the lane that was free rather than the one that was not.
    A downgrade that read "barred" while a lane stood open would be the record saying the
    stronger check was impossible when it was merely not taken.

    It names the lane that was *not* free as well (#427). This is the partially barred
    arrangement — `zai` off-peak, `codex` reachable — and a record carrying only
    `free_lanes=codex` could not say whether `zai` had been considered and rejected or never
    asked at all. Both halves of the free set, and the bar on every rejection, are the
    record's own bytes.
    """
    _, review_root = roots = _stage(tmp_path)
    outcome = _gate_rung(
        roots,
        reviewer=CLAUDE_REVIEWER,
        reviewer_lane="claude-native",
        reach=_reach(review_root.parent, PEAK),
    )

    assert outcome.refusal is None
    assert any(
        line.startswith("gate_review=same_lane_chosen")
        and line.endswith(
            f"same_lane_authors={AUTHOR} free_lanes=codex barred_lanes=zai:lane_peak_hours"
            f" review_dispatch=d-review-1"
        )
        for line in outcome.cleared
    )
    assert not any(line.startswith("gate_review=lane_barred") for line in outcome.cleared)


def test_a_free_lane_with_no_credential_on_this_box_is_a_bar_the_record_names(
    tmp_path: Path,
) -> None:
    """`lane_bar`'s third rung, composed through a landing rather than asserted alone (#427).

    #426 pinned the breaker and off-peak arms through this rung and left the credential arm
    covered only in `tools/dispatch.py`'s own tests, so the wiring from a landing to that
    rung was unproven. Here the credentials file carries no `ZAI_API_KEY`: `zai` is barred
    with the kind and the `infra_unavailable` class the credential read gives it, `codex`
    needs no credential and stays free, and the record names both — one arrangement covering
    the composition and the partially barred record together.
    """
    _, review_root = roots = _stage(tmp_path)
    outcome = _gate_rung(
        roots,
        reviewer=CLAUDE_REVIEWER,
        reviewer_lane="claude-native",
        reach=_reach(review_root.parent, key=False),
    )

    assert outcome.refusal is None
    assert any(
        line.startswith("gate_review=same_lane_chosen")
        and " barred_lanes=zai:credential_absent/infra_unavailable " in line
        and " free_lanes=codex " in line
        for line in outcome.cleared
    )


def test_the_quota_reader_the_landing_reaches_the_provider_through_is_the_callers_own(
    tmp_path: Path,
) -> None:
    """The one network seam in this rung, proven to be a seam (#427).

    `dispatch.lane_bar` asks z.ai's quota endpoint for a lane held open on availability with
    no published boundary — the only outbound call `just land`'s decision path can make, and
    the one #426 disclosed as a state-file write alone. The arrangement is that lane: open on
    `provider_errors`, which carries no reset. A reader this test owns is handed in and comes
    back saying nothing, so the lane stays barred on its own rule; asserting it was called is
    what proves the parameter reaches the breaker rather than sitting unused beside a live
    default. Every other arrangement here hands in `no_lane_network`, which fails if this branch
    is ever reached unstaged.
    """
    _, review_root = roots = _stage(tmp_path)
    asked: list[str] = []

    def reader(lane: str, _credentials: Path, now: float) -> breaker.QuotaReading:
        asked.append(lane)
        return breaker.QuotaReading(
            lane=lane,
            source="staged-for-this-test",
            estimated=False,
            windows=(),
            unavailable="staged",
            observed_at=now,
        )

    directory = review_root.parent / "breaker"
    credentials = review_root.parent / "credentials.env"
    credentials.write_text("ZAI_API_KEY=staged-for-this-test\n", encoding="utf-8")
    credentials.chmod(0o600)
    breaker.write_state(
        directory,
        breaker.LaneState(
            "zai",
            breaker.Circuit(
                state=breaker.OPEN,
                rule="provider_errors",
                reason="three consecutive provider errors",
                opened_at=OFF_PEAK.timestamp(),
                reset_at=None,
            ),
            None,
            OFF_PEAK.timestamp(),
        ),
    )
    outcome = _gate_rung(
        roots,
        reviewer=CLAUDE_REVIEWER,
        reviewer_lane="claude-native",
        reach=land_review.LaneReach(directory, credentials, OFF_PEAK, reader),
    )

    assert asked == ["zai"]
    assert outcome.refusal is None
    assert any(
        " barred_lanes=zai:lane_breaker_open/infra_unavailable " in line for line in outcome.cleared
    )


def test_the_ruling_relaxes_the_lane_rule_and_not_ruling_4(tmp_path: Path) -> None:
    """`review_same_profile` is untouched, and it fires a rung above the lane record (#426).

    The reviewing profile is the author's own, on a gate path, with every free lane
    reachable — the arrangement that now clears on lane grounds and must still refuse on
    ruling 4's. The preference relaxes the strengthening, never the invariant.
    """
    outcome = _gate_rung(
        _stage(tmp_path, author=CLAUDE_REVIEWER),
        reviewer=CLAUDE_REVIEWER,
        reviewer_lane="claude-native",
    )

    assert _kind(outcome) == "review_same_profile"
    assert not any(line.startswith("gate_review=") for line in outcome.cleared)


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
    either. The author's lane is the successor's lane, so a zai reviewer of zai-authored gate
    work is recorded as a same-lane review rather than cleared as a cross-lane one — which
    is where #413's finding lives now that #426 made the lane half a record instead of a
    refusal.
    """
    outcome = _gate_rung(
        _stage(tmp_path, author="zai-glm52-max"),
        reviewer="zai-glm47-max",
        reviewer_lane="zai",
    )

    assert outcome.refusal is None
    found = "\n".join(outcome.cleared)
    assert "gate_review=same_lane_chosen reviewer_lane=zai author_lanes=zai" in found
    assert "same_lane_authors=zai-glm52-max" in found
    assert "free_lanes=claude-native codex" in found


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


# ------------- #416: exhaustion degrades the cross-lane rule rather than refusing forever


def _authored(profile: str, dispatch_id: str) -> tuple[str, str, str]:
    """One authoring record as `records=` takes it, on the profile and id named."""
    return (
        dispatch_id,
        "dispatch.json",
        json.dumps(
            {
                "seat": "implementer",
                "issue": ISSUE,
                "profile": profile,
                "dispatch_id": dispatch_id,
            }
        ),
    )


def test_an_exhausted_gate_landing_degrades_to_the_different_profile_rule(
    tmp_path: Path,
) -> None:
    """#405's state: the records place a profile on every lane, so no reviewer lane is free.

    The cross-lane predicate cannot be satisfied by any dispatch, and the fallback is
    ruling 4's own different-profile rule — already enforced one rung up, so an arrangement
    that reaches the cross-lane rung holds a different-profile verdict by construction. What
    the landing records is the degradation itself: `gate_review=lane_exhausted` beside the
    reviewer lane and the author lanes, in its own key rather than by omission (ADR-0073
    Amendment A1).
    """
    outcome = _gate_rung(
        _stage(
            tmp_path,
            records=(
                _authored("zai-glm53-max", "d-author-2"),
                _authored("codex-sol-high", "d-author-3"),
            ),
        )
    )

    assert outcome.refusal is None
    assert (
        f"gate_review=lane_exhausted reviewer_lane=codex"
        f" author_lanes=claude-native zai codex gate_paths={GATE_PATH}" in outcome.cleared
    )
    assert land_review.LANE_EXHAUSTED_LIMIT in outcome.cleared


def test_exhaustion_degrades_to_ruling_4_not_to_nothing(tmp_path: Path) -> None:
    """The fallback rule still refuses the proposer approving itself.

    A degradation to the different-profile rule is a degradation to a rule, and the same
    verdict this rung would refuse on profile grounds is refused before the lane question
    is ever reached — so exhaustion cannot be read as the cross-lane predicate turning off.
    """
    outcome = _gate_rung(
        _stage(
            tmp_path,
            records=(
                _authored("zai-glm53-max", "d-author-2"),
                _authored(REVIEWER, "d-author-3"),
            ),
        )
    )

    assert _kind(outcome) == "review_same_profile"


def test_a_gate_landing_with_a_lane_still_free_is_not_recorded_as_exhausted(
    tmp_path: Path,
) -> None:
    """Two lanes authored, one free: exhaustion does not fire and the cause is the other one.

    The degradation is bounded by derivation — `lane_exhausted` fires only where no
    admissible reviewer lane exists at all — so a landing that could have dispatched its
    review cross-lane records the choice instead. Distinguishing the two is criterion 2 of
    #426: a reader must be able to tell "no lane was free" from "one was".
    """
    outcome = _gate_rung(
        _stage(tmp_path, records=(_authored("zai-glm53-max", "d-author-2"),)),
        reviewer=CLAUDE_REVIEWER,
        reviewer_lane="claude-native",
    )

    assert outcome.refusal is None
    found = "\n".join(outcome.cleared)
    assert "gate_review=same_lane_chosen" in found
    assert "author_lanes=claude-native zai" in found
    assert "free_lanes=codex" in found
    assert "lane_exhausted" not in found


def test_exhaustion_follows_the_registry_rather_than_any_record_of_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The boundary where a lane leaves the registry, both directions, live at landing time.

    One staging, one verdict, three registries: under the registry as it stands a `codex`
    reviewer was available, so the record is `same_lane_chosen`; under one that has lost
    `codex` no free lane is left and the record is `lane_exhausted`; under one that has
    gained a lane it is `same_lane_chosen` again. The comparison is computed from `LANES` at
    every landing, so a registry that moves moves the cause with it — never a flag, never a
    record of a past exhaustion (#416, unchanged by #426).
    """
    staged = _stage(tmp_path, records=(_authored("zai-glm53-max", "d-author-2"),))
    full = _gate_rung(staged, reviewer=CLAUDE_REVIEWER, reviewer_lane="claude-native")

    assert any(line.startswith("gate_review=same_lane_chosen") for line in full.cleared)

    lanes = land_review.dispatch.LANES
    shrunk = {name: lane for name, lane in lanes.items() if name != "codex"}
    monkeypatch.setattr(land_review.dispatch, "LANES", shrunk)
    without_codex = _gate_rung(staged, reviewer=CLAUDE_REVIEWER, reviewer_lane="claude-native")

    assert without_codex.refusal is None
    assert (
        f"gate_review=lane_exhausted reviewer_lane=claude-native"
        f" author_lanes=claude-native zai gate_paths={GATE_PATH}" in without_codex.cleared
    )

    grown = dict(lanes)
    grown["a-fourth-lane"] = lanes["zai"]
    monkeypatch.setattr(land_review.dispatch, "LANES", grown)
    regrown = _gate_rung(staged, reviewer=CLAUDE_REVIEWER, reviewer_lane="claude-native")

    assert regrown.refusal is None
    assert any(
        line.startswith("gate_review=same_lane_chosen")
        and line.endswith(
            "free_lanes=codex a-fourth-lane barred_lanes=none review_dispatch=d-review-1"
        )
        for line in regrown.cleared
    )


def test_a_stalled_resolver_cannot_hold_the_landing_past_the_readers_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The live reader's bound is the whole call's, not the socket's (#427, round 2).

    `urlopen`'s timeout begins once the hostname has resolved, so a stalled `getaddrinfo`
    escapes it entirely and holds this serial rung for as long as the resolver hangs — the
    landing waiting on a name lookup with nothing to cancel it. What is stalled here is
    resolution specifically: `socket.getaddrinfo` is replaced by one that sleeps far past the
    deadline, so no socket is ever created, no packet leaves this box, and a bound that covered
    only the socket would not fire at all. The reader is the live default rather than a stub,
    so the deadline under test is the one `just land` runs.

    The landing comes back inside the deadline with the lane still barred: a read that could
    not complete is an unavailable reading, which leaves an open circuit open. A deadline that
    expired into "closed, proceed" would be worse than the hang it replaced. The abandoned read
    is left on a daemon thread, which is what keeps the deadline from being a wait the process
    still owes at exit.
    """
    _, review_root = roots = _stage(tmp_path)
    deadline = 0.25
    stall = 5.0
    monkeypatch.setattr(breaker, "ZAI_USAGE_TIMEOUT_SECS", deadline)

    def stalled_resolver(*_args: object, **_kwargs: object) -> list[object]:
        time.sleep(stall)
        return []

    monkeypatch.setattr(socket, "getaddrinfo", stalled_resolver)

    directory = review_root.parent / "breaker"
    credentials = review_root.parent / "credentials.env"
    credentials.write_text("ZAI_API_KEY=staged-for-this-test\n", encoding="utf-8")
    credentials.chmod(0o600)
    breaker.write_state(
        directory,
        breaker.LaneState(
            "zai",
            breaker.Circuit(
                state=breaker.OPEN,
                rule="provider_errors",
                reason="three consecutive provider errors",
                opened_at=OFF_PEAK.timestamp(),
                reset_at=None,
            ),
            None,
            OFF_PEAK.timestamp(),
        ),
    )
    reach = land_review.LaneReach(directory, credentials, OFF_PEAK, breaker.query_first_party_quota)

    started = time.monotonic()
    outcome = _gate_rung(
        roots, reviewer=CLAUDE_REVIEWER, reviewer_lane="claude-native", reach=reach
    )
    elapsed = time.monotonic() - started

    assert elapsed < stall / 2
    assert outcome.refusal is None
    assert any(
        " barred_lanes=zai:lane_breaker_open/infra_unavailable " in line for line in outcome.cleared
    )
    abandoned = [worker for worker in threading.enumerate() if worker.name == "cti-bounded-request"]
    assert abandoned
    assert all(worker.daemon for worker in abandoned)
