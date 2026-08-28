"""The landing's never-alone rung: a reviewed, adjudicated commit or a typed refusal (#334).

ADR-0071 ruling 4 names three facts a landing must be able to show, and this module
is the ladder that reads them off records other tools wrote:

1. **A review record for the commit being landed** — either a completed
   `seat=review` dispatch on this issue whose `base_sha` is this SHA, or a declared
   human record for this issue. `review_exchange`'s derivation decides the agent
   case (#332), and this rung enforces rather than re-derives:
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
class 6 — **the gates themselves** — owes one more, and it is criterion 2 extended
rather than a fourth criterion beside it: the verdict's reviewer should be on a
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
never-alone; on the gates it is worth one more predicate. A gate landing is also
**not** exemptible by `config/review-exemptions.json`, which is why `gate_paths` is
decided before the exemption table is consulted rather than after.

**The lane half is a preference and not a rule (ADR-0073 Amendment A2, #426).** The
human ruled on 2026-08-19, on being told that #390 could not be reviewed because both
available lanes had authored it and the third sat inside its off-peak window: *"Same
lane review is a strong preference, not a rule. Amend accordingly."* So no landing is
refused on lane any more — `review_same_lane` is gone — and what replaces it is a
mandatory record naming which of four things happened: `gate_review=cross_lane` where
the preferred check ran, and one of three downgrades where it did not —
`lane_exhausted` (Amendment A1, #416: every registered lane is an author's),
`lane_barred` (a free lane existed and every one of them was unreachable, each named
with the bar that says so), `same_lane_chosen` (a free lane was reachable and a
same-lane verdict cleared the landing anyway). Those are three different facts about a
downgrade and a reader needs to tell them apart; a single flag would hide the third
inside the first. A downgrade nobody can see is worse than the refusal it replaces,
because it is indistinguishable from a landing that met the stronger bar.

Every cause is **derived at landing time and none is declared**: exhaustion from
`tools/dispatch.py`'s registry against the records, a bar from `dispatch.lane_bar` —
the same breaker, off-peak and credential rungs a dispatch would hit, asked through
the one function so the record cannot drift from what a dispatch would have done.

`review_lane_unknown` survives the ruling, for a lane the registry cannot place at
either end: it refuses a landing whose *record* cannot be computed, never one whose
lanes merely coincide. And `review_same_profile` is untouched — an absolute refusal,
a rung above this one, so every downgrade below it is still a verdict from a profile
no record places on the work. The preference relaxes the strengthening, not the
invariant it was strengthening.

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

**The loop record is not identity-bound, and the verdict is.** A derived verdict names
a dispatch, a profile and a lane, and `verify` re-derives all three from the records
at read time, so a hand-edit is caught. A declared human verdict names a registered
profile and lane in its separate review-state record, and the landing re-reads that
record rather than treating it as an agent dispatch. A loop record carries no
dispatch, no SHA and no arbiter identity: `route` is a string, and a hand-written
`arbiter_dismissed` clears as readily as an arbiter's. ADR-0071 ruling 4 concedes
the same-user limit — every dispatch runs as one user, so these records protect
against the accident and the shortcut, not against a deceptive agent — and the
asymmetry is stated here because this is where a reader meets it, and printed on
the clearance because that is what a lander quotes (round 1 claims 3 and 4).

## What this rung never does

`review_finding` — the rung `just land` climbs — is the whole of this module, and
it writes no record, dispatches nothing and adjudicates nothing: the verdict is
#332's exchange, the dispatch the dispatcher's, and every loop decision
`review_loop`'s. Two qualifications, stated in full rather than glossed, because
#426's first statement of the first one was narrower than the behaviour (#427).
Reading a free lane's breaker goes through `dispatch.lane_bar`, and **that read both
writes and can reach the network**. It settles an expired window as it is read, so a
landing that consults one may leave that lane's state file converged; and for a z.ai
lane held open on availability with no published boundary it asks z.ai's own quota
endpoint, which is how that lane heals itself without a dispatch. Both are the
breaker's own convergence on its own record — the same write and the same request any
`just dispatch` or `just breaker` read performs — and neither moves anything this rung
judges. The call is bounded where it fires: one lane can ask it — `zai` is the only lane
with a feed, and every other returns `feed_absent` without a socket — one request, no
retry, a 10 s deadline over the whole call (`tools/bounded_request.py`, so a stalled
resolver expires like a stalled socket rather than escaping the bound), and every failure
a typed unavailable reading rather than an exception, so a landing cannot hang on it and
cannot spend the deadline more than once. `LaneReach.quota_reader` is the seam that
suppresses it, and every test of this rung hands in a reader that refuses to be called,
so no `just fast` run reaches a provider to decide a record. The default stays live,
because the point of the record is what a dispatch would have met at that moment. This
rung has no command surface of its own either; the loop's acts are
`just review-loop`'s. And nothing here reads as approval by absence: no verdict,
an unreadable verdict, a verdict for another commit or another item, and records
that name no author at all each refuse by name.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, NamedTuple

# tools/ holds standalone scripts rather than an importable package, so a sibling
# import needs the script's own directory on the path — the device `dispatch.py`,
# `brief.py` and `review_loop.py` all use.
sys.path.insert(0, str(Path(__file__).parent))

import attribute_registry
import breaker
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

# The second downgrade cause, and the one the human's ruling of 2026-08-19 was given for
# (ADR-0073 Amendment A2, #426): a lane no record places on this issue existed and could not
# be dispatched to at the moment of the landing.
LANE_BARRED_LIMIT: Final = (
    "limit=a free reviewer lane existed and none of them could be dispatched to at the moment"
    " this landing ran — the bars are named above, each one `tools/dispatch.py`'s own answer"
    " for that lane rather than a judgement made here, and each is a state of the provider or"
    " the clock and not of the work. A bar that clears makes a cross-lane review available"
    " again, and this record is the reason to seek one before the next gate change rather"
    " than after it (ADR-0073 Amendment A2, #426)"
)

# The third, and the reason the ruling is a preference rather than a rule: a cross-lane
# reviewer was there to dispatch and a same-lane verdict cleared the landing anyway.
SAME_LANE_CHOSEN_LIMIT: Final = (
    "limit=a cross-lane reviewer was available at the moment this landing ran and the verdict"
    " that cleared it came from an author's own lane — the preferred check did not run, and"
    " nothing here derived a reason it could not have. Same-provider models share failure"
    " modes, which is ruling 4's own argument for never-alone, so a reader weighing this"
    " landing is reading a weaker separation than a cross-lane clearance states (the human's"
    " ruling of 2026-08-19, #217; ADR-0073 Amendment A2, #426)"
)


class LaneReach(NamedTuple):
    """Where the rung reads a free lane's dispatchability from, and the moment it asks.

    A parameter rather than a flag or an environment variable, on `ReviewInputs`' own terms:
    the live breaker directory, the live credentials file and the wall clock are what `just
    land` must read — the whole point of the downgrade record is whether a cross-lane review
    was dispatchable *then* — and a test that read them would be asserting on this box's
    provider state and on the hour of the day, which is what made `just fast` red for the
    four hours a day z.ai sits in peak (#238's note). Defaults are the real ones; `at` of
    `None` is "ask the clock now".

    `quota_reader` is the fourth because the breaker read can reach the network and nothing
    else here can (#427). `breaker.lane_verdict` asks z.ai's own quota endpoint when that
    lane is held open on availability with no published boundary, which is the lane healing
    itself; the default is the live reader and stays live, so this rung's record is what a
    dispatch would have met. It is bounded where it fires — one lane can ask it, one request,
    no retry, a 10 s deadline over the whole call rather than over the socket alone, so a
    stalled resolver cannot outlast it (`tools/bounded_request.py`), and every failure a typed
    unavailable reading rather than an exception — so a landing cannot hang on it. A test hands in a
    reader that refuses to be called, which is how a staged lane state stays a staged fact
    about the record and not a fact about this box's connectivity.
    """

    breaker_dir: Path = breaker.DEFAULT_BREAKER_DIR
    credentials: Path = dispatch.CREDENTIALS
    at: datetime | None = None
    quota_reader: dispatch.QuotaReader = breaker.query_first_party_quota

    def moment(self) -> datetime:
        """Answer the instant the bars are read at — the caller's, or now."""
        return self.at or datetime.now(tz=UTC)


# The reach a landing takes when nobody names one: the box's real breaker, its real
# credentials, and the clock at the moment the rung asks. A module-level singleton rather
# than a default constructed per call, which is B008's own remedy and is also the honest
# shape — the paths are fixed and only `at` varies, and `at=None` is what defers it.
LIVE_REACH: Final = LaneReach()


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

    `relations` and `gate_cause` are the same clearance as a record (#491): the
    qualified object relations the landing event carries — subject, produced
    commit, every author, the reviewer — and, where the diff touched routing
    class 6, which of the four gate-review causes the verdict rode. The landing
    seam records them beside its push; they stay empty on every refusal and on the
    exempt clearance that consults no record, where there is no author set and no
    verdict to relate. `gate_cause` is carried rather than re-derived by the reader
    because two of the four causes rest on bars read live at landing time, which no
    later read of the records can reproduce.
    """

    refusal: Refusal | None
    cleared: tuple[str, ...]
    relations: tuple[attribute_registry.Relation, ...] = ()
    gate_cause: str = ""


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


def _landing_relations(
    issue: int,
    sha: str,
    authorship: dispatch.Authorship,
    declared_record: Path,
    binding: review_exchange.Bound,
) -> tuple[attribute_registry.Relation, ...]:
    """Build the landing's qualified object relations from the facts the rung derived (#491).

    One derivation, this function, feeding both halves of the record: the clearance
    lines a lander quotes and the event the landing journals — a second derivation
    anywhere is the two-readers drift #445's finding 3 named. The subject is the
    issue, the produced object the commit the verdict bound, the reviewer provenance
    that bound it (`dispatch` for a derived reviewer, `human_reviewer` for a declared
    one), and every potential author an object of its own source: a `dispatch` where
    a dispatch record placed the profile, an `authorship_declaration` where an
    interactive session declared it (#398). The
    two are told apart by the record that placed the profile, never by whether the
    profile also appears in the declaration: `with_declared_authors` appends the
    declaration's own path as the record for a name it adds and never re-adds a
    name a dispatch already placed, so a profile that both dispatches and declares
    keeps its dispatch relation — the record is the stronger evidence, and its
    dispatch id is the object a reader of this event wants.
    """
    declared_id = str(declared_record)
    authors = [
        attribute_registry.relation(
            "author",
            "authorship_declaration" if record == declared_id else "dispatch",
            profile if record == declared_id else record,
        )
        for profile, record in zip(authorship.potential, authorship.records, strict=True)
    ]
    reviewer_type = (
        "human_reviewer"
        if binding.reviewer_kind == review_exchange.DECLARED_REVIEWER
        else "dispatch"
    )
    reviewer_id = (
        binding.profile
        if binding.reviewer_kind == review_exchange.DECLARED_REVIEWER
        else binding.dispatch_id
    )
    return (
        attribute_registry.relation("subject", "issue", str(issue)),
        attribute_registry.relation("produced", "commit", sha),
        attribute_registry.relation("reviewer", reviewer_type, reviewer_id),
        *authors,
    )


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


def _lane_bars(free: tuple[str, ...], reach: LaneReach) -> tuple[tuple[str, str], ...]:
    """Ask each free lane whether it could be dispatched to, and name what says no.

    One entry per barred lane, `(lane, bar)`, where the bar is `dispatch.lane_bar`'s own
    refusal kind with its failure class where it carries one — `lane_peak_hours` for the
    human's off-peak window, `lane_breaker_open/quota_exhausted` for a lane out of quota,
    `lane_breaker_open` for one the breaker tripped on quality, and whichever of
    `credential_absent`, `credentials_missing` or `credentials_mode` the lane's own
    credential read gives back. Naming the class as well as the kind is what makes the
    ruling's "barred by its off-peak window, its breaker, or a provider quota" three facts
    in the record rather than one (#217, 2026-08-19).

    A lane the bar clears is absent from the result, so an empty tuple means every free lane
    was reachable. The lanes are asked in registry order, so the record is stable.
    """
    bars = []
    at = reach.moment()
    for name in free:
        bar = dispatch.lane_bar(
            dispatch.LANES[name], reach.breaker_dir, reach.credentials, at, reach.quota_reader
        )
        if bar is None:
            continue
        bars.append((name, f"{bar.kind}/{bar.failure_class}" if bar.failure_class else bar.kind))
    return tuple(bars)


class GateDecision(NamedTuple):
    """A gate landing's lane record as data (#491): the cause, and the lines it clears with.

    The cause is carried beside the lines because the lines are the landing's own
    printed bytes and the cause is the record's value — parsing the one back out of
    the other is exactly the reading of a printed line #491 exists to retire. The
    four spellings are `attribute_registry`'s, stated once there.
    """

    cause: str
    lines: tuple[str, ...]


def _gate_review_decision(
    gate_paths: tuple[str, ...],
    binding: review_exchange.Bound,
    authorship: dispatch.Authorship,
    reach: LaneReach,
) -> Refusal | GateDecision:
    """Decide a gate landing's lane record: the refusal that fires, or a `GateDecision`.

    ADR-0073, on the human's instruction of 2026-08-18. Routing class 6's keep-on-Claude bar
    selected on provenance and exempted the lane that authors nearly every gate change, so
    the surface most at risk was the one the rule cleared. What replaces it is the invariant
    the bar stood in for, spent on the rung that already runs: for a landing whose diff
    touches a class-6 path, ruling 4's "not the same profile" is joined by "and preferably
    not the same **lane**". Same-provider models share failure modes, which is ruling 4's own
    argument for never-alone; on the gates themselves it is worth one more predicate.

    **The lane half is a preference and not a rule (Amendment A2, #426).** The human ruled on
    2026-08-19, on being told that #390 could not be reviewed because both available lanes had
    authored it and the third sat inside its off-peak window: *"Same lane review is a strong
    preference, not a rule. Amend accordingly."* So this rung no longer refuses on lane at all
    — `review_same_lane` is gone — and what it does instead is **record**, in the landing's own
    bytes, which of four things happened. A downgrade nobody can see is worse than the refusal
    it replaces, because it is indistinguishable from a landing that met the stronger bar.

    | key | what it says |
    |---|---|
    | `gate_review=cross_lane` | the preferred check ran: the reviewer's lane is no author's |
    | `gate_review=lane_exhausted` | every lane the registry carries is an author's lane |
    | `gate_review=lane_barred` | a free lane existed and every one of them was unreachable |
    | `gate_review=same_lane_chosen` | a free lane was reachable and a same-lane verdict cleared |

    Those are three different facts about a downgrade and a reader needs to tell them apart:
    a single flag would hide the third inside the first, and the third is the only one the
    ruling leaves to a person's judgement. Amendment A1's `lane_exhausted` (#416) is the first
    of them and is folded in here unchanged rather than left beside them; the second and third
    are this amendment's, and the second is the case the ruling was actually given for — a lane
    barred for hours by a quota, where the old rung turned a preference into an indefinite
    block on completed, gated work.

    **Every cause is derived, and none is declared.** Exhaustion is computed from
    `tools/dispatch.py`'s registry against the records, so a lane joining or leaving moves it
    in both directions. A bar is `dispatch.lane_bar`'s own answer for that lane at the moment
    of the landing — the same three rungs a dispatch would hit, asked through the same
    function so the record cannot drift from what a dispatch would have done — and it is read
    live rather than taken from a caller's flag. `LaneReach` carries only *where* to read them
    from, which is the seam a test needs and not a fact about this landing.

    **What does not move is ruling 4.** `review_same_profile` is an absolute refusal and it
    fires a rung above this one, so every clearance below — exhausted, barred or chosen — is a
    verdict from a profile no record places on the work. The preference relaxes the
    strengthening, never the invariant it was strengthening.

    **Both lanes are placed against the registry, and a lane it cannot place still refuses.**
    The reviewer's lane is a string on a record — `parse_verdict` requires it to be a string
    and not to be a registered one — and an author's lane is derived from the registry entry
    for a profile a record named. Either unplaceable and no honest record can be written: the
    fail-open reading would print `cross_lane` on an inequality between a known lane and an
    unknown one, which is a stronger claim than the records support, exactly where they are
    worst (#41). `review_lane_unknown` therefore survives the ruling — it refuses a landing
    whose *record* cannot be computed, never one whose lanes merely coincide. A retired name
    places through the successor a rename left (#413, `dispatch.resolved_profile`), and a name
    whose chain resolves nowhere still refuses here.

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
            "This landing touches the gates themselves, so the record of which lane reviewed"
            " it must name lanes the registry carries — and a lane above is not one"
            " `tools/dispatch.py`'s registry carries, so the comparison cannot be made and no"
            " honest record can be written. Register the profile or the lane, or re-derive the"
            " record that names it; a check that could not run is not a check that passed"
            " (#41, ADR-0073). Nothing was pushed.",
        )
    author_lanes = tuple(
        dict.fromkeys(dispatch.resolved_profile(profile).lane for profile in authorship.potential)
    )
    where = f"author_lanes={' '.join(author_lanes)} gate_paths={' '.join(gate_paths)}"
    free = tuple(name for name in dispatch.LANES if name not in author_lanes)
    # First because exhaustion subsumes every branch below it: with no free lane, a registered
    # reviewer lane is necessarily an author's, and there is no lane left to ask a bar of. The
    # author lanes print beside the reviewer's so a reader sees the set that exhausted (#416).
    if not free:
        return GateDecision(
            attribute_registry.GATE_LANE_EXHAUSTED,
            (
                (
                    f"gate_review={attribute_registry.GATE_LANE_EXHAUSTED}"
                    f" reviewer_lane={reviewer_lane} {where}"
                ),
                LANE_EXHAUSTED_LIMIT,
            ),
        )
    if reviewer_lane not in author_lanes:
        return GateDecision(
            attribute_registry.GATE_CROSS_LANE,
            (
                (
                    f"gate_review={attribute_registry.GATE_CROSS_LANE}"
                    f" reviewer_lane={reviewer_lane} {where}"
                ),
                CROSS_LANE_LIMIT,
            ),
        )
    # A same-lane verdict from here on, which since the ruling of 2026-08-19 clears either way.
    # What separates the two records is whether the preferred check was *available*: the bars
    # are read live from the same rungs a dispatch would have hit, so "the free lane was
    # barred" and "the operator chose" are derived apart rather than collapsed into one flag.
    shared = " ".join(
        profile
        for profile in authorship.potential
        if dispatch.resolved_profile(profile).lane == reviewer_lane
    )
    bars = _lane_bars(free, reach)
    barred = {name for name, _ in bars}
    available = tuple(name for name in free if name not in barred)
    # Both records carry the whole free set, split into the lanes that were reachable and the
    # lanes that were not with the bar that says so — every free lane considered, and every
    # rejection's reason, in the bytes the landing prints (#427). A record that named only the
    # reachable half left a partially barred `same_lane_chosen` unable to say which lanes it
    # had asked, and the record is the safety property of this whole downgrade.
    named = " ".join(f"{name}:{bar}" for name, bar in bars) or "none"
    if not available:
        return GateDecision(
            attribute_registry.GATE_LANE_BARRED,
            (
                (
                    f"gate_review={attribute_registry.GATE_LANE_BARRED}"
                    f" reviewer_lane={reviewer_lane} {where}"
                    f" same_lane_authors={shared} barred_lanes={named}"
                ),
                LANE_BARRED_LIMIT,
            ),
        )
    return GateDecision(
        attribute_registry.GATE_SAME_LANE_CHOSEN,
        (
            (
                f"gate_review={attribute_registry.GATE_SAME_LANE_CHOSEN}"
                f" reviewer_lane={reviewer_lane} {where}"
                f" same_lane_authors={shared} free_lanes={' '.join(available)}"
                f" barred_lanes={named} review_dispatch={binding.dispatch_id or 'none'}"
            ),
            SAME_LANE_CHOSEN_LIMIT,
        ),
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
    reach: LaneReach = LIVE_REACH,
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
    mismatch. A moved SHA over a diff that changes a binary file refuses
    `binary_diff_uncarried` whatever both halves say (#419).

    `reach` is where the gate rung reads a free lane's dispatchability from and the
    moment it asks (#426) — a seam for tests and nothing else, since every fact the
    downgrade record states is derived through it rather than handed in.
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
        # The exempt clearance consults no record, so it relates no author and no
        # reviewer — but it still landed something, and the landing's own subject
        # and produced objects are facts this rung holds (#491). Where the tree
        # names no issue there is nothing to attach even those to.
        exempt_relations = (
            (
                attribute_registry.relation("subject", "issue", str(issue)),
                attribute_registry.relation("produced", "commit", sha),
            )
            if issue is not None
            else ()
        )
        return _exempt(decision)._replace(relations=exempt_relations)
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
        issue,
        sha,
        dispatch_root,
        diff_id,
        review_exchange.read_rebases(review_root, issue),
        review_root=review_root,
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
                "The verdict clearing this commit names a profile the issue's own"
                " records place on the work — the proposer approving itself, which"
                " ruling 4 refuses. "
                + (
                    "Record the human verdict with a registered profile that did not"
                    " author this change."
                    if binding.reviewer_kind == review_exchange.DECLARED_REVIEWER
                    else "Dispatch a review on a profile that did not author (`just"
                    " dispatch --seat review --reviewing <profile>`), record its verdict,"
                    " and land again."
                )
                + " Nothing was pushed.",
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
    gate_cause = ""
    if gate_paths:
        decision = _gate_review_decision(gate_paths, binding, authorship, reach)
        if isinstance(decision, Refusal):
            return Outcome(decision, ())
        gate_review = decision.lines
        gate_cause = decision.cause
    # Composed once, above the loop block, so the two clearance returns below carry
    # the same relation set without either re-deriving it (#491).
    relations = _landing_relations(issue, sha, authorship, declared_record, binding)
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
                f"reviewer_kind={verdict.reviewer_kind}",
                (
                    f"review_dispatch={binding.dispatch_id or 'none'} profile={binding.profile}"
                    f" lane={binding.lane}"
                ),
                f"verdict_sha={sha}",
                *_binding_lines(bound),
                f"findings={len(verdict.findings)} above_low={len(above)} open_above_low=0",
                "loop=not_needed reason=no_finding_above_low",
                *_alternates_lines(binding),
                review_exchange.SAME_USER_LIMIT,
            ),
            relations=relations,
            gate_cause=gate_cause,
        )
    try:
        loop = review_loop.load_loop(review_root, issue)
    except (OSError, ValueError) as error:
        return Outcome(
            Refusal(
                "review_loop_unreadable",
                (f"loop={loop_file}", f"reason={error}"),
                "The loop state for this issue cannot be read as a loop document this"
                " reader knows (versions 1 or 2)."
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
            f"reviewer_kind={verdict.reviewer_kind}",
            (
                f"review_dispatch={binding.dispatch_id or 'none'} profile={binding.profile}"
                f" lane={binding.lane}"
            ),
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
        relations=relations,
        gate_cause=gate_cause,
    )
