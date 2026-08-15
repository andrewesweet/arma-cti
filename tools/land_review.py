"""The landing's never-alone rung: a reviewed, adjudicated commit or a typed refusal (#334).

ADR-0071 ruling 4 names three facts a landing must be able to show, and this module
is the ladder that reads them off records other tools wrote:

1. **A review dispatch record for the commit being landed** — `seat=review`, on
   this issue, whose `base_sha` is this SHA, completed. `review_exchange`'s
   derivation decides it (#332), and this rung enforces rather than re-derives:
   a verdict satisfies only the SHA it names (`satisfies`), and its claimed
   identity is re-derived at read time (`verify`), so an amended or rebased
   branch cannot ride an earlier approval and a hand-edited record cannot forge
   the identity the dispatcher wrote.
2. **That review's identity absent from the dispatches that authored the work** —
   `dispatch.potential_authors` (#322), read as the potential-author superset it
   is: the reviewer's profile inside it refuses (`review_same_profile`, the same
   name dispatch gives the same fact at dispatch time), and any scan that is not
   `Authorship.complete` refuses rather than reads as checked — #41's rule, with
   the profiles the scan did read still stated beside the refusal. **An empty set
   is not a clearance.** Records that name no author at all — the change written
   in an agent's own session rather than through `just dispatch`, or an issue with
   no records — satisfy "absent from the authoring dispatches" only vacuously, and
   the one arrangement this criterion exists to catch is the one it would then
   wave through: the same instance that wrote the diff dispatching its own review
   (round 1 claim 1, on `2149b69`).
3. **Every finding above Low carrying its one adjudication** — the four routes of
   ruling 4 (`fixed`, `arbiter_upheld`, `arbiter_dismissed`, `accepted_and_filed`),
   the fourth added by the human's ruling of 2026-08-14 on #334: Medium or below,
   naming the issue it was filed as and the work outside the diff its harm is
   conditional on. The loop state that records adjudications is #333's format
   (below), and every route decision on read is `review_loop`'s own.

The exemption table decides before any record is opened, and it is inverted the
way `review_loop.exemption_decision` reads it: unlisted means covered, so the only
diff that reaches a clearance without consulting a record is one whose every path
matched a listed entry — and that clearance says `review=exempt` with the reasons
it matched, quotable from the decision that granted it.

## The loop record, and whose reader and writer these are

`<review_root>/<issue>/loop.json` is #333's format and #333's reader: this module
reads it through `review_loop.load_loop` and names its path with that module's
own `loop_path`. Round 1 of this issue landed while #333 was still unlanded, so
it carried a local copy of both; the docstring then promised the swap "when
#333's `review_loop.load_loop` is the landed canonical reader", #333 landed at
`1a5a7fb`, and this is that swap. Nothing here parses loop state any more.

The writer is #333's `just review-loop` too — `open`, `round`, `adjudicate`,
`escalate`, `terminus`, `show`, and `sync`, which this issue added to it. Round 1
landed the enforcement without any writer at all (round 1 claim 2, CLAUDE.md's
"land a convention together with its first applied instance"), and round 1's fix
landed a second CLI of its own beside #333's; a rebase onto the landed sibling
made that a duplicate recipe and a second reader of one record. `sync` is the one
act of it that is this issue's: it folds the findings of the verdict *this rung
will read* into the loop, from the record rather than from a flag, so the seat
under review cannot re-grade its own review on the way in.

**The loop record is not identity-bound, and the verdict is.** A verdict names a
dispatch, a profile and a lane, and `verify` re-derives all three from the records
at read time, so a hand-edit is caught. A loop record carries no dispatch, no SHA
and no arbiter identity: `route` is a string, and a hand-written
`arbiter_dismissed` clears as readily as an arbiter's. ADR-0071 ruling 4 concedes
the same-user limit — every dispatch runs as one user, so these records protect
against the accident and the shortcut, not against a deceptive agent — and the
asymmetry is stated here because this is where a reader meets it, and printed on
the clearance because that is what a lander quotes (round 1 claims 3 and 4).

## What this rung never does

`review_finding` — the rung `just land` climbs — is the whole of this module, and
it writes nothing, dispatches nothing and adjudicates nothing: the verdict is
#332's exchange, the dispatch the dispatcher's, and every loop decision
`review_loop`'s. It has no command surface of its own; the loop's acts are
`just review-loop`'s. And nothing here reads as approval by absence: no verdict,
an unreadable verdict, a verdict for another commit or another item, and records
that name no author at all each refuse by name.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Final, NamedTuple

# tools/ holds standalone scripts rather than an importable package, so a sibling
# import needs the script's own directory on the path — the device `dispatch.py`,
# `brief.py` and `review_loop.py` all use.
sys.path.insert(0, str(Path(__file__).parent))

import dispatch
import review_exchange
import review_loop
from worktree import Refusal

# #333's own root, not a copy of it: one record, one reader, one path (round 2).
REVIEW_ROOT: Final = review_loop.REVIEW_ROOT

# An exempt diff can be wide; the clearance states the reasons it matched without
# becoming one line per path past the first ten — the same shape `land`'s own
# evidence capping uses.
HOW_MANY_EXEMPT: Final = 10

NO_AUTHORSHIP: Final = "no_authoring_dispatch"
UNREADABLE: Final = "records_unreadable"

# Printed beside every clearance that read a loop, for the reason `review_exchange`
# prints `SAME_USER_LIMIT` beside every recorded verdict: the clearance is the durable
# record, and a qualification two tools upstream is not in the bytes anyone quotes
# (round 1 claims 3 and 4).
LOOP_RECORD_LIMIT: Final = (
    "limit=the loop record carries no dispatch and no SHA, so unlike the verdict beside it"
    " its routes are not re-derived at read time — an arbiter route names the arbiter"
    " `escalate` resolved and is refused without one, but the name is written by the same"
    " user, not derived (ADR-0071 ruling 4's same-user limit)"
)


class Outcome(NamedTuple):
    """The rung's answer: a typed refusal, or the clearance lines a landing quotes.

    `Refusal` is `worktree`'s, so the refusal a landing prints is shaped like every
    other one the protocol emits. `cleared` is empty wherever `refusal` is set, and
    carries the honest account wherever it is not — the dispatch that reviewed, the
    identity it derived, what the authorship scan did and did not read, and the loop
    that holds the adjudications.
    """

    refusal: Refusal | None
    cleared: tuple[str, ...]


# ------------------------------------------------------------------ deleted, deliberately
#
# Round 1 carried `loop_path`, `parse_stored_loop`, `loop_document`, `write_loop` and
# `load_loop` here, with a docstring promising their deletion once #333 landed its own.
# #333 landed at `1a5a7fb`; they are `review_loop`'s, and this module now calls them
# (round 2). One record has one reader.


# ------------------------------------------------------------------ the rung


def _exemptions_read(text: str | None) -> review_loop.ExemptionRead:
    """Parse the trusted table's text, or carry the reason it could not be read.

    `None` is the read off fetched `origin/main` that failed — an unreadable table
    exempts nothing, which `exemption_decision` states as `Unreadable`.
    """
    if text is None:
        return review_loop.ExemptionRead(
            None, "the exemption table could not be read from fetched origin/main"
        )
    try:
        return review_loop.ExemptionRead(review_loop.parse_exemptions(text))
    except ValueError as error:  # ReviewLoopError and json.JSONDecodeError are both this
        return review_loop.ExemptionRead(
            None, f"origin/main:{review_loop.EXEMPTIONS_RELATIVE.as_posix()}: {error}"
        )


def _exempt(decision: review_loop.Exempt) -> Outcome:
    """Render the one clearance that consults no record: every path matched a listing."""
    matched = [f"exempt={path} reason={reason}" for path, reason in decision.matched]
    shown = matched[:HOW_MANY_EXEMPT]
    if len(matched) > HOW_MANY_EXEMPT:
        shown.append(f"and={len(matched) - HOW_MANY_EXEMPT} more")
    return Outcome(None, ("review=exempt", *shown))


def _unadjudicated_refusal(
    loop_file: Path,
    reported: tuple[review_exchange.ReportedFinding, ...] = (),
    held: tuple[review_loop.Finding, ...] = (),
) -> Refusal:
    """Refuse the findings above Low that owe their one adjudication, each named.

    Two sources, one kind: a finding the verdict reported that the loop holds open
    or does not hold at all, and a finding the loop still holds open that this
    verdict never reported — an earlier round's, whose adjudication is owed all the
    same because the loop's stop condition reads every round (#333's, decided once
    in `review_loop.stop_condition`).
    """
    found = [f"finding={f.id} severity={f.severity} source=verdict" for f in reported]
    found += [
        f"finding={f.id} severity={f.severity} round={f.round_raised} source=loop" for f in held
    ]
    return Refusal(
        "finding_unadjudicated",
        (f"loop={loop_file}", *found),
        "Adjudicate each finding above Low through one of the four routes — fixed,"
        " arbiter_upheld, arbiter_dismissed, or accepted_and_filed at Medium or below"
        " naming the issue it became and the work outside the diff its harm is"
        " conditional on (ADR-0071 ruling 4; the fourth route, human ruling"
        " 2026-08-14, #334) — with `just review-loop adjudicate --issue <n> --finding"
        " <id> --route <route>`, then land again. Nothing was pushed.",
    )


def _authorship_lines(authorship: dispatch.Authorship) -> tuple[str, ...]:
    """Render the one-line account of the authorship scan a clearance can carry.

    There is exactly one: `Authorship.complete`. Every other state now refuses —
    unreadable as `records_unreadable`, empty as `authorship_unrecorded` — so a
    clearance never says "unchecked" or "none recorded" again, and this helper has
    no arm for a state the ladder cannot reach (round 1 claim 1).
    """
    return (f"authorship=checked potential={' '.join(authorship.potential)}",)


def _alternates_lines(binding: review_exchange.Bound) -> tuple[str, ...]:
    """Render the alternates a latest-first derivation skipped past, if it skipped any."""
    return (f"alternates={' '.join(binding.alternates)}",) if binding.alternates else ()


def review_finding(  # noqa: C901, PLR0911, PLR0912, PLR0913, PLR0917 — the ladder keeps one rung per branch, one return per refusal and one input per fact the rung reads, so no way a record can refuse hides inside a helper
    issue: int | None,
    sha: str,
    paths: tuple[str, ...] | None,
    exemptions_text: str | None,
    dispatch_root: Path,
    review_root: Path,
) -> Outcome:
    """Decide the never-alone rung for one landing: a typed refusal, or the clearance.

    The ladder, in the order the module docstring derives it. The exemption table
    first, because a diff the inverted table covers is the one landing that consults
    no record at all; then the three criteria of ruling 4, each enforced by the tool
    that owns it — `review_exchange` for the verdict and its binding, `dispatch` for
    the potential authors, `review_loop` for the adjudications. The two `isinstance`
    narrowings are against classes of modules this module itself imported, so the
    objects and the class always come from the one module object and the re-exec
    duplicate trap the kind-value contracts document cannot arise here.
    """
    decision = review_loop.exemption_decision(_exemptions_read(exemptions_text), paths or ())
    if isinstance(decision, review_loop.Exempt):
        return _exempt(decision)
    if issue is None:
        return Outcome(
            Refusal(
                "review_issue_unknown",
                ("issue=unknown",),
                "This tree's name is not an issue's, so the rung cannot know whose"
                " review to read — `just worktree add issue-<n>` names the tree after"
                " the item it serves, and a landing without an item is the"
                " never-alone breach this rung exists to refuse (ADR-0071 ruling 4)."
                " Nothing was pushed.",
            ),
            (),
        )
    binding = review_exchange.derive_binding(issue, sha, dispatch_root)
    if not isinstance(binding, review_exchange.Bound):
        return Outcome(binding, ())
    try:
        verdict_file = review_exchange.verdict_path(dispatch_root, binding.dispatch_id)
    except review_exchange.ReviewExchangeError as error:
        return Outcome(
            Refusal(
                UNREADABLE,
                (f"dispatch={binding.dispatch_id}", f"reason={error}"),
                "The reviewing dispatch's id cannot name its own verdict record, and"
                " the record that would not open could be the binding one — so no"
                " verdict is read (#41). Nothing was pushed.",
            ),
            (),
        )
    if not verdict_file.is_file():
        return Outcome(
            Refusal(
                "no_verdict",
                (f"dispatch={binding.dispatch_id}", f"expected={verdict_file}"),
                "The review dispatch completed but no verdict record sits beside its"
                " plan. Record the verdict (`just review record`) — a completed review"
                " whose judgement no one can read clears nothing (#41). Nothing was"
                " pushed.",
            ),
            (),
        )
    try:
        verdict = review_exchange.parse_verdict(verdict_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return Outcome(
            Refusal(
                "verdict_unreadable",
                (f"verdict={verdict_file}", f"reason={error}"),
                "The verdict record exists but will not parse. Repair or re-record it"
                " — a check that could not run is not a check that passed (#41)."
                " Nothing was pushed.",
            ),
            (),
        )
    if verdict.issue != issue:
        return Outcome(
            Refusal(
                "review_issue_mismatch",
                (
                    f"asked_issue={issue}",
                    f"verdict_issue={verdict.issue}",
                    f"verdict={verdict_file}",
                ),
                "This verdict judges another item's work. A verdict satisfies only the"
                " item and the SHA it names (#332's binding, read at landing time), so"
                " record one for this item's commit. Nothing was pushed.",
            ),
            (),
        )
    mismatch = review_exchange.satisfies(verdict, sha)
    if mismatch is not None:
        return Outcome(mismatch, ())
    # `verify` would re-derive the binding from `(verdict.issue, verdict.reviewed_sha)`,
    # and the two checks above have just proven that pair equal to `(issue, sha)` — the
    # arguments `binding` came from. The comparison is the whole of what `verify` adds,
    # so it is made against the derivation already in hand rather than by scanning every
    # dispatch directory on the box a second time (round 1 claim 11).
    forged = review_exchange.identity_mismatch(verdict, binding)
    if forged is not None:
        return Outcome(forged, ())
    authorship = dispatch.potential_authors(issue, dispatch_root)
    if binding.profile in authorship.potential:
        authored = tuple(
            record
            for profile, record in zip(authorship.potential, authorship.records, strict=True)
            if profile == binding.profile
        )
        return Outcome(
            Refusal(
                "review_same_profile",
                (
                    f"issue={issue}",
                    f"reviewer_profile={binding.profile}",
                    f"authored_by={' '.join(authored)}",
                    f"review_dispatch={binding.dispatch_id}",
                ),
                "The verdict clearing this commit was produced by a profile the"
                " issue's own dispatch records place on the work — the proposer"
                " approving itself, which ruling 4 refuses. Dispatch a review on a"
                " profile that did not author (`just dispatch --seat review"
                " --reviewing <profile>`), record its verdict, and land again."
                " Nothing was pushed.",
            ),
            (),
        )
    # An unreadable scan keeps its own kind whether or not it read a profile first, so
    # the two refusals stay one fact apiece: "the records say nothing" and "the records
    # would not open".
    if not authorship.potential and authorship.why != UNREADABLE:
        return Outcome(
            Refusal(
                "authorship_unrecorded",
                (
                    f"issue={issue}",
                    f"dispatch_root={dispatch_root.expanduser()}",
                    f"reviewer_profile={binding.profile}",
                    f"why={authorship.why or NO_AUTHORSHIP}",
                ),
                "No dispatch record places any profile on this issue's work, so the"
                " separation between this verdict's reviewer and the work's authors is"
                " not an answer the records can give — and the arrangement the criterion"
                " exists to catch, an instance reviewing the diff it wrote in its own"
                " session, is exactly the one an empty set clears. Dispatch the"
                " implementing work through `just dispatch --issue <n>` so a record"
                " exists to check the reviewer against, then re-review this commit and"
                " land again. A check that could not run is not a check that passed"
                " (#41, ADR-0071 ruling 4). Nothing was pushed.",
            ),
            (),
        )
    if authorship.why == UNREADABLE:
        return Outcome(
            Refusal(
                UNREADABLE,
                (
                    f"dispatch_root={dispatch_root.expanduser()}",
                    f"reviewer_profile={binding.profile}",
                    f"potential={' '.join(authorship.potential) or 'none'}",
                    f"records={' '.join(authorship.records) or 'none'}",
                    "why=records_unreadable",
                ),
                "The authorship scan could not read every dispatch record, so the"
                " separation between this verdict's reviewer and the authors of the"
                " work is not an answer the records can give — and the record that"
                " would not open could be the author's (#322's partial read, #41's"
                " rule). Nothing was pushed.",
            ),
            (),
        )
    above = tuple(
        finding for finding in verdict.findings if review_loop.above_low(finding.severity)
    )
    loop_file = review_loop.loop_path(review_root, issue)
    if not loop_file.is_file():
        if above:
            return Outcome(
                Refusal(
                    "no_review_loop",
                    (
                        f"issue={issue}",
                        f"loop={loop_file}",
                        *(f"finding={f.id}:{f.severity}" for f in above),
                    ),
                    "The verdict reports findings above Low and no loop state"
                    " adjudicates them. Open the loop from the recorded verdict"
                    " (`just review-loop sync --issue <n> --reviewed-sha <sha>`), then"
                    " close each finding through its one route (`just review-loop"
                    " adjudicate --issue <n> --finding <id> --route <route>`) — every"
                    " above-Low finding owes one before this lands (ADR-0071 ruling 4)."
                    " Nothing was pushed.",
                ),
                (),
            )
        return Outcome(
            None,
            (
                *_authorship_lines(authorship),
                (
                    f"review_dispatch={binding.dispatch_id} profile={binding.profile}"
                    f" lane={binding.lane}"
                ),
                f"verdict_sha={sha}",
                f"findings={len(verdict.findings)} above_low={len(above)} open_above_low=0",
                "loop=not_needed reason=no_finding_above_low",
                *_alternates_lines(binding),
                review_exchange.SAME_USER_LIMIT,
            ),
        )
    try:
        loop = review_loop.load_loop(review_root, issue)
    except (OSError, ValueError) as error:
        return Outcome(
            Refusal(
                "review_loop_unreadable",
                (f"loop={loop_file}", f"reason={error}"),
                "The loop state for this issue cannot be read as a version 1 loop."
                " Repair the record at the path above — a check that could not run"
                " is not a check that passed (#41). Nothing was pushed.",
            ),
            (),
        )
    # The canonical parser validates the document and leaves the routes' preconditions to
    # the act of adjudicating — rightly, since a recorded verdict must stay readable. The
    # fourth route's three restrictions are the ruling's words about what the disposition
    # means, so a record breaking one is a record no writer produced, and this rung has to
    # ask (round 1's local reader got it by rebuilding the loop through `adjudicate`).
    violations = review_loop.stored_route_violations(loop)
    if violations:
        return Outcome(
            Refusal(
                "review_loop_unreadable",
                (f"loop={loop_file}", *(f"invalid={violation}" for violation in violations)),
                "The loop state carries an adjudication that could not have been written:"
                " the fourth route is Medium or below, names the issue the finding became,"
                " and names the work outside this diff its harm is conditional on (human"
                " ruling 2026-08-14, #334). Repair the record at the path above — a check"
                " that could not run is not a check that passed (#41). Nothing was pushed.",
            ),
            (),
        )
    recorded = {finding.id: finding for finding in loop.findings}
    # Over every finding the verdict reports, not only the ones it rates above Low.
    # Round 1 compared `above` against the loop and so read the drift in one direction
    # only: a finding the verdict calls Low and the loop calls Critical left `above`
    # empty, cleared with `above_low=0`, and never printed the severity the loop holds
    # (round 1 claim 7). The check is "have these two records drifted", and that
    # question has no band.
    disagreed = tuple(
        finding
        for finding in verdict.findings
        if finding.id in recorded and recorded[finding.id].severity != finding.severity
    )
    if disagreed:
        return Outcome(
            Refusal(
                "review_finding_mismatch",
                (
                    f"loop={loop_file}",
                    *(
                        f"finding={finding.id} verdict={finding.severity}"
                        f" loop={recorded[finding.id].severity}"
                        for finding in disagreed
                    ),
                ),
                "The loop's record of a finding disagrees with the verdict that"
                " reported it — one of the two has been edited or drifted. Re-derive"
                " the loop from the verdict that produced it rather than reconciling"
                " by hand. Nothing was pushed.",
            ),
            (),
        )
    unadjudicated = tuple(
        finding
        for finding in above
        if finding.id not in recorded or recorded[finding.id].adjudication is None
    )
    if unadjudicated:
        return Outcome(_unadjudicated_refusal(loop_file, reported=unadjudicated), ())
    if not review_loop.stop_condition(loop):
        return Outcome(_unadjudicated_refusal(loop_file, held=review_loop.open_above_low(loop)), ())
    # The writer refuses an arbiter route with no arbiter named (`review_loop`'s own
    # `ARBITER_UNNAMED_ERROR`); this is the same fact read back off the record, because a
    # loop file is edited by hand as readily as it is written by the tool and the reader
    # of a record must not assume its writer (#334 round 2, Medium 2). Above Low only:
    # a Low never blocks, so a Low's route decides nothing here.
    unnamed = tuple(
        finding
        for finding in loop.findings
        if review_loop.above_low(finding.severity)
        and finding.adjudication is not None
        and finding.adjudication.route
        in (review_loop.ARBITER_UPHELD, review_loop.ARBITER_DISMISSED)
        and not finding.adjudication.arbiter
    )
    if unnamed:
        return Outcome(
            Refusal(
                "arbiter_unnamed",
                (
                    f"loop={loop_file}",
                    *(
                        f"finding={f.id} severity={f.severity} route={f.adjudication.route}"
                        for f in unnamed
                    ),
                ),
                "A finding above Low is closed through an arbiter route that names no"
                " arbiter, so the record does not say who ruled — and a route standing in"
                " for a ruling with no judge on it is the shape ruling 4's escalation"
                " exists to prevent. Resolve the arbiter (`just review-loop escalate"
                " --issue <n>`) and re-adjudicate the finding, which writes the name it"
                " resolved. Nothing was pushed.",
            ),
            (),
        )
    return Outcome(
        None,
        (
            *_authorship_lines(authorship),
            f"review_dispatch={binding.dispatch_id} profile={binding.profile} lane={binding.lane}",
            f"verdict_sha={sha}",
            # Read off the loop rather than written as a literal: the count a lander
            # quotes is a reading of the record, and `stop_condition` having just held
            # is what makes it zero (round 1 claim 7).
            (
                f"findings={len(verdict.findings)} above_low={len(above)}"
                f" open_above_low={len(review_loop.open_above_low(loop))}"
            ),
            f"loop={loop_file}",
            LOOP_RECORD_LIMIT,
            *_alternates_lines(binding),
            review_exchange.SAME_USER_LIMIT,
        ),
    )
