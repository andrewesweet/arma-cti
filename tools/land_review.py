"""The landing's never-alone rung: a reviewed, adjudicated commit or a typed refusal (#334).

ADR-0071 ruling 4 names three facts a landing must be able to show, and this module
is the ladder that reads them off records other tools wrote:

1. **A review dispatch record for the commit being landed** — `seat=review`, on
   this issue, whose `base_sha` is this SHA, completed. `review_exchange`'s
   derivation decides it (#332), and this rung enforces rather than re-derives:
   a verdict satisfies the SHA it names, or a moved SHA where two facts both
   hold (`satisfies`, #417 reworked) — the move is a chain of clean rebases the
   tooling recorded, and the landing diff's exact identity matches the recorded
   one — and its claimed identity is re-derived at read time (`verify`), so an
   amended branch cannot ride an earlier approval and a hand-edited record
   cannot forge the identity the dispatcher wrote. The pair is what keeps a
   **clean** rebase's review alive while a rebase a hand resolved re-reviews,
   however faithfully it reproduced the diff: identity alone can never prove
   whether conflict resolution occurred, and only the rebase's own record can.
   Matching identity plus recorded clean rebases proves the diff is unchanged
   and mechanically replayed, not that its meaning survived the move onto the
   new base; the gate's tests at landing are what catch that difference, and
   they still run.
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
   (round 1 claim 1, on `2149b69`). **The set has a second source** (#398): an
   interactive session declares its authorship through `just review-loop author`,
   because #294 bars a dispatched session from writing under `.claude/` and so
   leaves such a change with no dispatch record to read at all — the deadlock #330
   sat in, reviewed and green with nowhere to go. The rung's logic is unchanged:
   the declaration only ever adds a profile the reviewer may not be, an empty set
   still refuses, and the clearance prints a declared author as `declared` because
   nothing derived it.
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

## The fourth fact, and the one class that has it (ADR-0073, #406)

Ruling 4's three criteria bind every landing. A landing whose diff touches routing
class 6 — **the gates themselves** — owes one more, and it is criterion 2 tightened
rather than a fourth criterion beside it: the verdict's reviewer must be on a
different **lane** than the author's, not merely a different profile. The gate-path
list is data, read from `config/dispatch-routing-policy.json` on fetched
`origin/main` by whoever calls this rung and handed in already filtered, so the one
authority for what a gate path is stays in `routing_policy` (`gate_paths`; `None`
is "could not be read" and refuses, `gate_class_undetermined`).

What this replaces is the keep-on-Claude bar that row used to carry, which the human
retired on 2026-08-18 as not their intent — it refused every non-Claude lane the gate
paths and exempted the Claude lane, which is the lane that authors nearly every gate
change, so the surface most at risk was the one the rule cleared. The invariant it
stood in for is the one enforced here: no instance authors the gate that judges it.
Same-provider models share failure modes, which is ruling 4's own argument for
never-alone; on the gates it is worth one more predicate. Two refusals carry it —
`review_same_lane` and `review_lane_unknown`, the second for a lane the registry
cannot place at either end — and a gate landing is also **not** exemptible by
`config/review-exemptions.json`, which is why `gate_paths` is decided before the
exemption table is consulted rather than after.

**One arrangement degrades rather than refuses (ADR-0073 Amendment A1, #416).**
Where the author lanes are every lane the registry carries, no admissible reviewer
lane exists — the refusal would be permanent, and #405 sat in exactly that state,
green at the gate and unlandable, because the project had deliberately spread its
work across all three lanes. The requirement then falls back to ruling 4's own
different-profile rule — already enforced one rung up, so the fallback holds by
construction wherever a reviewer profile outside the authors exists. Where the records
place every registered profile on the work even that set is empty, and the rung above
refuses `review_same_profile` before this one runs — exhaustion at the lane level lifts
ruling 4 nothing. The landing records the degradation as `gate_review=lane_exhausted`
beside the reviewer lane and the author lanes, in its own key rather than by omission.
Exhaustion is the only trigger, derived from the registry and the records at
landing time and never declared by a caller; every case with a cross-lane reviewer
available refuses exactly as before.

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

# The evidence line every clearance of a gate landing carries, and the reason it names the
# author lanes rather than only the reviewer's: a lander quoting this must be able to see
# the set the reviewer was checked against, the same way `authorship=checked potential=`
# shows the profile set (ADR-0073, #406).
CROSS_LANE_LIMIT: Final = (
    "limit=the author lanes are the lanes of the *potential* author set — every profile a"
    " dispatch record or a declaration places on this issue, whether or not that run wrote a"
    " line — so this rung over-excludes by construction and a cleared cross-lane review is"
    " not evidence that the excluded lanes authored anything"
)

# The line every exhausted clearance carries beside it (ADR-0073 Amendment A1, #416). The
# degradation is the record's own words rather than a fact a lander has to know: what ran
# instead is ruling 4's different-profile rule, and the exhaustion was derived here from the
# registry and the records — never declared by whoever is landing.
LANE_EXHAUSTED_LIMIT: Final = (
    "limit=every lane the registry carries is a lane the records place on this issue, so no"
    " cross-lane reviewer exists to dispatch — the requirement degrades to ruling 4's own"
    " different-profile rule, which the rung above already enforced on this landing, and the"
    " exhaustion is derived at landing time from `tools/dispatch.py`'s registry and the"
    " issue's records, never declared by a caller (ADR-0073 Amendment A1, #416)"
)

# Printed beside every clearance that read a loop, for the reason `review_exchange`
# prints `SAME_USER_LIMIT` beside every recorded verdict: the clearance is the durable
# record, and a qualification two tools upstream is not in the bytes anyone quotes
# (round 1 claims 3 and 4).
# Printed beside every clearance that read a declared author (#398), for the same reason:
# the clearance is the durable record, and this one carries a fact about how its author set
# was arrived at that no other line says.
DECLARED_AUTHOR_LIMIT: Final = (
    "limit=a declared author is the recording session's own word, not a profile a dispatcher"
    " resolved into a child's environment — it excludes a reviewer as firmly as a dispatch"
    " record does and is corroborated by nothing (ADR-0071 ruling 4's same-user limit)"
)

LOOP_RECORD_LIMIT: Final = (
    "limit=the loop record carries no dispatch and no SHA, so unlike the verdict beside it"
    " its routes are not re-derived at read time — an arbiter route is refused without an"
    " escalation record that fired and named the arbiter it carries, but both records are"
    " written by the same user, not derived (ADR-0071 ruling 4's same-user limit)"
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


NOTHING_PUSHED: Final = " Nothing was pushed."


def _landing_refusal(refusal: Refusal) -> Refusal:
    """Carry a shared refusal into the landing's own voice: it also says nothing was pushed.

    `review_exchange`'s derivation is read by `review-loop sync` too, where nothing is
    being pushed and the sentence would be a lie; the landing is where it is true, so the
    landing adds it rather than the shared module carrying a caller's context. Idempotent,
    so a refusal that already ends this way is not told twice.
    """
    if refusal.action.endswith(NOTHING_PUSHED):
        return refusal
    return refusal._replace(action=refusal.action + NOTHING_PUSHED)


def _authorship_lines(
    authorship: dispatch.Authorship, declared: tuple[str, ...]
) -> tuple[str, ...]:
    """Render the one-line account of the authorship scan a clearance can carry.

    There is exactly one: `Authorship.complete`. Every other state now refuses —
    unreadable as `records_unreadable`, empty as `authorship_unrecorded` — so a
    clearance never says "unchecked" or "none recorded" again, and this helper has
    no arm for a state the ladder cannot reach (round 1 claim 1).

    A declared author is named as declared, with the limit beside it (#398): it excluded
    this reviewer as firmly as a dispatch record would, and unlike a dispatch record
    nothing derived it. A lander quotes these bytes, so the qualification travels in them
    rather than living two tools upstream — `LOOP_RECORD_LIMIT`'s reason.
    """
    line = f"authorship=checked potential={' '.join(authorship.potential)}"
    if not declared:
        return (line,)
    return (f"{line} declared={' '.join(declared)}", DECLARED_AUTHOR_LIMIT)


def _undetermined_gate_refusal() -> Refusal:
    """Refuse a landing that cannot be placed inside or outside routing class 6 (ADR-0073).

    Two inputs decide it and the caller hands both as one: the trusted policy off fetched
    `origin/main`, which carries the gate-path list, and this branch's own diff. Either
    unreadable and the rung cannot say whether a cross-lane review is owed — so it says so,
    rather than reading the absence as "not a gate landing", which is the fail-open answer
    and the one an unreadable record always tempts (#41).

    Deliberately one kind for both causes. The lander's routing lines, printed a rung
    earlier, already name which of the two failed, and splitting the kind would have a
    reader choosing between two remedies that are the same remedy.
    """
    return Refusal(
        "gate_class_undetermined",
        ("check=routing class 6 gate paths", "gate_paths=undetermined"),
        "Either the routing policy on fetched `origin/main` or this branch's own diff could"
        " not be read, so whether this landing touches the gates themselves is not an answer"
        " the records can give — and the invariant that rides on that answer is the one no"
        " instance may author the gate that judges it (ADR-0071 ruling 4, ADR-0073). Rebase"
        " this worktree onto origin/main — which `just land` itself does before its own gate"
        " — or repair the repository state, then land again. A check that could not run is"
        " not a check that passed (#41). Nothing was pushed.",
    )


def _gate_review_decision(
    gate_paths: tuple[str, ...],
    binding: review_exchange.Bound,
    authorship: dispatch.Authorship,
) -> Refusal | tuple[str, ...]:
    """Decide a gate landing's lane rule: the refusal that fires, or the lines it clears with.

    ADR-0073, on the human's instruction of 2026-08-18. Routing class 6's keep-on-Claude bar
    selected on provenance and exempted the lane that authors nearly every gate change, so
    the surface most at risk was the one the rule cleared. What replaces it is the invariant
    the bar stood in for, spent as one predicate on the rung that already runs: for a landing
    whose diff touches a class-6 path, ruling 4's "not the same profile" becomes "not the same
    **lane**". Same-provider models share failure modes, which is ruling 4's own argument for
    never-alone; on the gates themselves it is worth one more predicate.

    **Exhaustion degrades the requirement rather than refusing forever (Amendment A1, #416).**
    Where the author lanes are every lane the registry carries, the set of admissible reviewer
    lanes is empty and no dispatch can ever satisfy the predicate — #405 sat exactly there,
    green at the gate and unlandable by construction, because the project had deliberately
    spread its work across all three lanes. The requirement then falls back to ruling 4's own
    rule, a verdict from a **different profile** than any author, which the rung above has
    already enforced by the time this one runs — so the fallback clears rather than refuses
    wherever a profile outside the authors exists. Where the records place every registered
    profile on the work that set is empty too, and the rung above has refused
    `review_same_profile` before this one ran — the degradation bounds the lane rule, never
    ruling 4. The clearance says what happened in its own key (`gate_review=lane_exhausted`) rather
    than by omission, beside the reviewer lane and the author lanes. A rung that silently
    downgrades is worse than one that refuses; a rung that refuses forever is worse than both.
    Exhaustion is the only trigger, it is computed here from the registry and the records at
    landing time — never declared by a caller, never cached in a record — and the refusal
    stands unchanged for every case where a cross-lane reviewer *is* available. The boundary
    follows: a lane joining or leaving the registry moves it, because the comparison is live.

    **Both lanes are placed against `tools/dispatch.py`'s registry, and a lane it cannot place
    refuses.** The reviewer's lane is a string on a record — `parse_verdict` requires it to be
    a string and not to be a registered one — and an author's lane is derived from the
    registry entry for a profile a record named. Either unplaceable and the comparison cannot
    be made, so the rung refuses rather than clearing on an inequality between a known lane
    and an unknown one, which would pass by accident exactly where the records are worst
    (#41). A retired name places through the successor a rename left (#413,
    `dispatch.resolved_profile`) — re-registering the dead name is the one remedy the old
    refusal named that a rename exists to make impossible — and a name whose chain resolves
    nowhere still refuses here. An author whose lane has left the registry still places (the
    profile is registered; the lane is its attribute), and an author lane no reviewer can be
    on removes nothing from the admissible set — so it cannot create exhaustion, only witness
    it.

    The author set is `Authorship.potential`, which is a *potential*-author set: over-excluding
    costs a resolution step and under-excluding costs the invariant, the trade `dispatch`
    already made for the profile check one rung up.
    """
    reviewer_lane = binding.lane
    unplaceable = tuple(
        profile for profile in authorship.potential if dispatch.resolved_profile(profile) is None
    )
    if unplaceable or reviewer_lane not in dispatch.LANES:
        return Refusal(
            "review_lane_unknown",
            (
                f"reviewer_lane={reviewer_lane or 'none'}",
                f"reviewer_lane_known={str(reviewer_lane in dispatch.LANES).lower()}",
                f"unplaceable_authors={' '.join(unplaceable) or 'none'}",
                f"potential={' '.join(authorship.potential)}",
                *(f"gate_path={path}" for path in gate_paths),
            ),
            "This landing touches the gates themselves, so the review clearing it must come"
            " from a different lane than the author's — and a lane above is not one"
            " `tools/dispatch.py`'s registry carries, so the two cannot be compared. Register"
            " the profile or the lane, or re-derive the record that names it; a check that"
            " could not run is not a check that passed (#41, ADR-0073). Nothing was pushed.",
        )
    author_lanes = tuple(
        dict.fromkeys(dispatch.resolved_profile(profile).lane for profile in authorship.potential)
    )
    # Above the same-lane refusal because exhaustion subsumes it: a registered reviewer lane
    # is an author lane wherever every registered lane is one, so the same-lane branch below
    # is unreachable exactly when this fires. A clearance, not a refusal, and the author lanes
    # are printed beside the reviewer's so a reader sees the set that exhausted (#416).
    if frozenset(dispatch.LANES).issubset(author_lanes):
        return (
            (
                f"gate_review=lane_exhausted reviewer_lane={reviewer_lane}"
                f" author_lanes={' '.join(author_lanes)} gate_paths={' '.join(gate_paths)}"
            ),
            LANE_EXHAUSTED_LIMIT,
        )
    if reviewer_lane in author_lanes:
        shared = tuple(
            profile
            for profile in authorship.potential
            if dispatch.resolved_profile(profile).lane == reviewer_lane
        )
        return Refusal(
            "review_same_lane",
            (
                f"reviewer_profile={binding.profile}",
                f"reviewer_lane={reviewer_lane}",
                f"author_lanes={' '.join(author_lanes)}",
                f"same_lane_authors={' '.join(shared)}",
                f"review_dispatch={binding.dispatch_id}",
                *(f"gate_path={path}" for path in gate_paths),
            ),
            "This landing touches the gates themselves, and the verdict clearing it was"
            " produced on the same lane as a profile the records place on the work. A"
            " different profile is not enough here: same-provider models share failure"
            " modes, which is ruling 4's own argument for never-alone, and on the gate paths"
            " the invariant is that no instance authors the gate that judges it (ADR-0073,"
            " the human's instruction of 2026-08-18). Dispatch the review on another lane —"
            " `just dispatch --seat review --reviewing <profile> --lane <lane> --profile"
            " <profile>`, naming a lane none of the authors above is on — record its verdict,"
            " and land again. Nothing was pushed.",
        )
    return (
        (
            f"gate_review=cross_lane reviewer_lane={reviewer_lane}"
            f" author_lanes={' '.join(author_lanes)} gate_paths={' '.join(gate_paths)}"
        ),
        CROSS_LANE_LIMIT,
    )


def _alternates_lines(binding: review_exchange.Bound) -> tuple[str, ...]:
    """Render the alternates a latest-first derivation skipped past, if it skipped any."""
    return (f"alternates={' '.join(binding.alternates)}",) if binding.alternates else ()


def _binding_lines(bound: review_exchange.BoundVerdict) -> tuple[str, ...]:
    """Name which half of #417's binding cleared, and its limit where the diff carried.

    A clearance that rode the SHA prints nothing extra — the SHA is the whole proof the
    record ever offered. One that rode a moved SHA says so and states the limit beside
    it, at the reader: matching identity plus recorded clean rebases proves the diff is
    unchanged and mechanically replayed, not that its meaning survived the move onto
    the new base — the gate's tests at landing are what catch that difference, and
    they still run.
    """
    if not bound.carried_by_diff:
        return ()
    return (
        f"carried_by=diff_id {bound.verdict.diff_id}",
        "provenance=clean_rebase_recorded",
        review_exchange.DIFF_ID_LIMIT,
    )


def _arbiter_authorisation(
    loop_file: Path, loop: review_loop.Loop, review_root: Path, issue: int
) -> Refusal | tuple[str, ...]:
    """Refuse an arbiter route no escalation record authorised; else the lines it clears with.

    The other half of "a reader of a record must not assume its writer" (round 2 re-review,
    Medium 1). Round 2 re-checked that an arbiter route *names* an arbiter and never that
    the route was *authorised*: the writer refuses both — `ARBITER_UNAUTHORISED_ERROR` for a
    route the escalation has not fired on, `ARBITER_UNNAMED_ERROR` for one that names no
    judge — and the terminus over the same loop refuses arbiter verdicts with no firing
    escalation record beside them. A hand-written `{"route": "arbiter_dismissed",
    "arbiter": "opus-xhigh"}` therefore cleared `just land` printing `open_above_low=0`
    while `just review-loop terminus` refused it `ARBITER_UNRESOLVED_ERROR` — one loop, two
    consumers, opposite answers, and the landing was the permissive one.

    The record decides it, through `review_loop.recorded_arbiter`, and the decision itself
    is `ArbiterAuthorisation.authorises` so the terminus and this rung cannot drift apart on
    what a record has to say: a name **and** a firing evaluation.

    **`escalation_fires_on` is deliberately not re-derived here**, and that is not an
    omission of the same kind. Its wall reads `open_above_low`, and the landing only reaches
    this line once every finding above Low is closed — so the wall is false by construction
    at landing time, and asking the predicate here would refuse every arbitrated landing.
    It is a precondition on the *act*, true when `adjudicate` ran; the escalation record is
    the durable trace that act left, and it is what a reader can honestly check.
    """
    arbitrated = tuple(
        finding
        for finding in loop.findings
        if review_loop.above_low(finding.severity)
        and finding.adjudication is not None
        and finding.adjudication.route
        in (review_loop.ARBITER_UPHELD, review_loop.ARBITER_DISMISSED)
    )
    if not arbitrated:
        return ()
    try:
        recorded = review_loop.recorded_arbiter(review_root, issue)
    except review_loop.ExternalError as error:
        return Refusal(
            "escalation_unreadable",
            (f"loop={loop_file}", f"reason={error}"),
            "A finding above Low is closed by an arbiter and the escalation record that"
            " would say who the wall transferred to could not be read. Repair the record —"
            " a check that could not run is not a check that passed (#41). Nothing was"
            " pushed.",
        )
    if not recorded.authorises:
        return Refusal(
            "arbiter_unresolved",
            (
                f"loop={loop_file}",
                f"escalation={review_root.expanduser() / str(issue) / review_loop.ESCALATION_FILE}",
                f"arbiter={recorded.arbiter or 'none'}",
                f"evaluation={recorded.evaluation or 'no_record'}",
                *(f"finding={f.id} route={f.adjudication.route}" for f in arbitrated),
            ),
            "A finding above Low is closed through an arbiter route that no escalation"
            " authorised: the record naming a firing condition and the profile it"
            " transferred to is absent, or it fired nothing. A landing whose verdicts no"
            " arbiter resolution chose is the same state `just review-loop terminus`"
            " refuses. Run `just review-loop escalate --issue <n>` at the wall and"
            " re-adjudicate. Nothing was pushed.",
        )
    disagreed = tuple(f for f in arbitrated if f.adjudication.arbiter != recorded.arbiter)
    if disagreed:
        return Refusal(
            "arbiter_mismatch",
            (
                f"loop={loop_file}",
                f"resolved={recorded.arbiter}",
                *(f"finding={f.id} arbiter={f.adjudication.arbiter}" for f in disagreed),
            ),
            "The arbiter named on an adjudication is not the one the escalation record"
            " resolved. `adjudicate` fills the name from that record, so the two disagree"
            " only where one was edited — re-derive rather than reconcile by hand. Nothing"
            " was pushed.",
        )
    return (
        (
            f"arbiter={recorded.arbiter} escalation={recorded.evaluation}"
            f" unchecked={str(recorded.unchecked).lower()}"
        ),
    )


def review_finding(  # noqa: C901, PLR0911, PLR0912, PLR0913, PLR0917 — the ladder keeps one rung per branch, one return per refusal and one input per fact the rung reads, so no way a record can refuse hides inside a helper
    issue: int | None,
    sha: str,
    paths: tuple[str, ...] | None,
    gate_paths: tuple[str, ...] | None,
    exemptions_text: str | None,
    dispatch_root: Path,
    review_root: Path,
    diff_id: str | Refusal | None = None,
) -> Outcome:
    """Decide the never-alone rung for one landing: a typed refusal, or the clearance.

    The ladder, in the order the module docstring derives it. The gate-path question
    first since ADR-0073, because its answer decides whether the exemption table may
    short-circuit at all; then the exemption table, because a diff the inverted table
    covers is the one landing that consults no record; then the three criteria of ruling
    4, each enforced by the tool that owns it — `review_exchange` for the verdict and its
    binding, `dispatch` for the potential authors, `review_loop` for the adjudications —
    with the cross-lane predicate riding on the second of them, since it is a statement
    about the same reviewer and the same author set. The two `isinstance` narrowings are
    against classes of modules this module itself imported, so the objects and the class
    always come from the one module object and the re-exec duplicate trap the kind-value
    contracts document cannot arise here.

    `gate_paths` is the caller's read of routing class 6's path list against this diff —
    `routing_policy.conflict_of_interest_paths`, computed where the trusted policy is
    read — and `None` is "the policy or the diff could not be read", which refuses. It
    arrives filtered rather than as prefixes so the seam carries a fact rather than a
    rule: the one authority for what a gate path is stays in `routing_policy`, and this
    module never learns how a prefix matches.

    `diff_id` is the landing diff's own exact identity, the caller's computation of
    `review_exchange.diff_id_of` over this tree — one half of #417's binding, which
    carries a verdict across a rebase that moved the SHA. The other half this rung
    reads for itself, from `review_root`: the issue's recorded clean-rebase links,
    because the rebase is the only party that knows whether a hand resolved anything
    and identity alone can never prove it (#417's rework, on the review that
    disproved the patch-id build). `None` is "could not be computed" and a `Refusal`
    is "computed and refused" — both refuse only where they would have been needed:
    a verdict for the exact SHA clears without either, and a moved SHA refuses
    (`diff_id_unreadable`, `rebase_unproven`) rather than reading the miss as a
    mismatch.
    """
    if gate_paths is None or paths is None:
        return Outcome(_undetermined_gate_refusal(), ())
    decision = review_loop.exemption_decision(_exemptions_read(exemptions_text), paths)
    # A gate landing is not exemptible, and the order is what makes that true rather than a
    # sentence (ADR-0073). `config/review-exemptions.json` is a different table from the
    # routing policy's own exceptions, so `binds_every_instance` does not reach it — and an
    # entry there covering a class-6 path would clear a gate change with no review at all,
    # which is worse than the same-lane review this issue was filed about. The table ships
    # empty, so today this changes nothing; it is here so that filling it cannot.
    if isinstance(decision, review_loop.Exempt) and not gate_paths:
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
    # One derivation, in `review_exchange`, for both readers of it (round 2 re-review,
    # Medium 2). Round 2 inlined the same six steps this call makes — the binding, the
    # record beside it, the item, the SHA, the identity re-derived rather than believed —
    # in the same order, and the two agreed only for as long as neither grew a check: a
    # check added to `bound_verdict` alone would have `review-loop sync` folding a loop
    # from a verdict this landing accepts, and one added here alone would refuse a loop
    # `sync` built. The obstacle was that this rung also needs the `Bound`, so the return
    # was widened to carry it rather than the copy kept. The diff identity and the
    # recorded clean-rebase links ride the same call for the same reason: both halves of
    # #417's binding are part of the binding, not of this rung.
    bound = review_exchange.bound_verdict(
        issue, sha, dispatch_root, diff_id, review_exchange.read_rebases(review_root, issue)
    )
    if not isinstance(bound, review_exchange.BoundVerdict):
        return Outcome(_landing_refusal(bound), ())
    verdict, binding = bound.verdict, bound.binding
    authorship = dispatch.potential_authors(issue, dispatch_root)
    # The second source of authors, read before the reviewer is checked against the set so a
    # declared author excludes a reviewer exactly as a dispatched one does (#398). It exists
    # because #294 bars a dispatched session from writing under `.claude/`, which makes such
    # a change interactively authored by construction and so invisible to the scan above —
    # and this rung's empty-set refusal, rightly, does not clear on invisibility.
    declared_record = review_loop.authorship_path(review_root, issue)
    try:
        declared = review_loop.recorded_authors(review_root, issue)
    except review_loop.ExternalError as error:
        return Outcome(
            Refusal(
                "authorship_unreadable",
                (f"issue={issue}", f"record={declared_record}", f"reason={error}"),
                "An interactive authorship record for this issue exists and could not be"
                " read, so who authored this change is not an answer any record can give"
                " — and the entry that would not open could be this reviewer's own. Repair"
                " the record at the path above, or remove it and re-declare with `just"
                " review-loop author --issue <n> --profile <profile>`. A check that could"
                " not run is not a check that passed (#41). Nothing was pushed.",
            ),
            (),
        )
    authorship = dispatch.with_declared_authors(authorship, declared, str(declared_record))
    # Resolved through `retired_names`, not plain membership (#413): a reviewer that is the
    # successor of a retired author is the one arrangement dispatch refuses and a plain
    # string comparison would clear, because the records carry the old name and the verdict
    # carries the new one. Same set `excluded_from_review` builds at dispatch time, minus
    # the declared subject the landing does not have.
    if binding.profile in dispatch.never_alone_exclusions(authorship):
        authored = tuple(
            record
            for profile, record in zip(authorship.potential, authorship.records, strict=True)
            if binding.profile in dispatch.retired_names(profile)
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
                "No record places any profile on this issue's work, so the separation"
                " between this verdict's reviewer and the work's authors is not an answer"
                " the records can give — and the arrangement the criterion exists to"
                " catch, an instance reviewing the diff it wrote in its own session, is"
                " exactly the one an empty set clears. Two routes, and which one applies"
                " is a fact about how this change was written. **Dispatched work:**"
                " dispatch the implementing work through `just dispatch --issue <n>` so a"
                " record exists to check the reviewer against, then re-review this commit."
                " **Interactive work** — which a `.claude/` change must be, since #294"
                " bars a dispatched session from writing there: declare it with `just"
                " review-loop author --issue <n> --profile <profile>`, naming the profile"
                " that wrote it, which must not be the profile that reviewed it. Then land"
                " again. A check that could not run is not a check that passed (#41,"
                " ADR-0071 ruling 4). Nothing was pushed.",
            ),
            (),
        )
    # Below `authorship_unrecorded` on purpose, and the order is the finding rather than a
    # convenience (#398 round 2). Where no record places anybody on the work, the refusal
    # above already states the true fact and already names this one's repair — "declare it
    # with `just review-loop author`" — so a lost record changes nothing a lander must do.
    # Where the dispatch records *do* place somebody, that refusal cannot fire, and the loss
    # of a declaration is then the only thing separating this arrangement from a legitimately
    # dispatched one: the declared author drops out of the set, and a reviewer that profile
    # would have been refused for clears instead. Constructed and measured on round 2 — the
    # rung cleared with `potential=` naming the dispatched profile alone and the declared one
    # nowhere in it.
    if review_loop.declaration_lost(review_root, issue):
        return Outcome(
            Refusal(
                "authorship_lost",
                (
                    f"issue={issue}",
                    f"record={declared_record}",
                    f"lock={declared_record.with_name(review_loop.AUTHORSHIP_LOCK)}",
                    f"potential={' '.join(authorship.potential) or 'none'}",
                    f"reviewer_profile={binding.profile}",
                ),
                "A declaration was written for this issue and its record is gone, so the"
                " profiles it named are absent from the set this reviewer was checked"
                " against — and one of them could be this reviewer. The lock beside the"
                " missing record is what says a declaration reached the writer; only the"
                " writer creates it. Re-declare every interactive author with `just"
                " review-loop author --issue <n> --profile <profile>` and land again. If"
                " this landing ran while a declaration was being written, the record is"
                " there now and re-running is the whole remedy. A check that could not run"
                " is not a check that passed (#41, ADR-0071 ruling 4). Nothing was pushed.",
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
    # Below the three authorship refusals on purpose: this predicate reads the same author
    # set they guard, so asking it above them would compare a reviewer against a set the
    # rung has not yet established it may trust (ADR-0073).
    gate_review: tuple[str, ...] = ()
    if gate_paths:
        decision = _gate_review_decision(gate_paths, binding, authorship)
        if isinstance(decision, Refusal):
            return Outcome(decision, ())
        gate_review = decision
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
                *_authorship_lines(authorship, declared),
                *gate_review,
                (
                    f"review_dispatch={binding.dispatch_id} profile={binding.profile}"
                    f" lane={binding.lane}"
                ),
                f"verdict_sha={sha}",
                *_binding_lines(bound),
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
    authorised = _arbiter_authorisation(loop_file, loop, review_root, issue)
    if isinstance(authorised, Refusal):
        return Outcome(authorised, ())
    return Outcome(
        None,
        (
            *_authorship_lines(authorship, declared),
            *gate_review,
            *authorised,
            f"review_dispatch={binding.dispatch_id} profile={binding.profile} lane={binding.lane}",
            f"verdict_sha={sha}",
            *_binding_lines(bound),
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
