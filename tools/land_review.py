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
   name dispatch gives the same fact at dispatch time), and an incomplete scan
   refuses rather than reads as checked — #41's rule, with the profiles the scan
   did read still stated beside the refusal.
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

## The loop record, and whose reader this is

`<review_root>/<issue>/loop.json` is #333's format at `ab76974`: a version 1
object of `issue`, `review_rounds` and `findings`, each finding an id, a severity,
the round that raised it, and — once terminal — its adjudication. This module
carries its own reader for it because #333 and this issue landed as siblings off
one base; the reader validates the JSON shape and then rebuilds the loop through
`review_loop`'s own `first_review`, `next_round` and `adjudicate`, so every
semantic decision — the severity vocabulary, the round stamps, the no-reopening
rule on ids, the four routes and the fourth route's three restrictions — is the
loop module's own, run on this record rather than duplicated beside it. When
#333's `review_loop.load_loop` is the landed canonical reader, this module's local
one is deleted in favour of it — a deliberate follow-up, never silent drift. The
version constant gates that day: a stored loop this reader does not recognise
refuses as unreadable rather than guessing.

## What this rung never does

It writes nothing, dispatches nothing and adjudicates nothing — the verdict is
#332's exchange, the dispatch the dispatcher's, the adjudication #333's loop. And
nothing here reads as approval by absence: no verdict, an unreadable verdict, a
verdict for another commit or another item each refuse by name.
"""

from __future__ import annotations

import json
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

REVIEW_ROOT: Final = Path.home() / ".arma-cti" / "review"
LOOP_FILE: Final = "loop.json"
# Mirrors #333's `review_loop.REVIEW_ROOT` and `LOOP_FILE` at ab76974, stated here
# for the sibling-landing reason the module docstring records: this rung reads the
# format, and swaps to the canonical reader when #333 lands.
LOOP_VERSION: Final = 1

# An exempt diff can be wide; the clearance states the reasons it matched without
# becoming one line per path past the first ten — the same shape `land`'s own
# evidence capping uses.
HOW_MANY_EXEMPT: Final = 10

NO_AUTHORSHIP: Final = "no_authoring_dispatch"
UNREADABLE: Final = "records_unreadable"


class LoopStateError(ValueError):
    """A stored loop whose shape cannot safely govern a landing."""


LOOP_VERSION_ERROR: Final = "a stored loop must be a version 1 object"
LOOP_ISSUE_ERROR: Final = "a stored loop must be the loop of the issue it is read for"
LOOP_ROUNDS_ERROR: Final = "review_rounds must be an integer of at least zero"
LOOP_FINDINGS_ERROR: Final = "findings must be a list of objects"
LOOP_FINDING_FIELDS_ERROR: Final = (
    "each finding must carry a non-empty id, one of the four severities, and the"
    " non-negative round that raised it"
)
LOOP_ROUND_RANGE_ERROR: Final = "a finding's round is beyond the rounds the loop records"
LOOP_ADJUDICATION_SHAPE_ERROR: Final = (
    "an adjudication must be an object carrying route, issue and conditional_on as strings"
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


# ------------------------------------------------------------------ the stored loop


def loop_path(root: Path, issue: int) -> Path:
    """Where one issue's loop state lives — #333's layout, `<root>/<issue>/loop.json`."""
    return root.expanduser() / str(issue) / LOOP_FILE


def _stored_finding(
    raw: object, rounds: int
) -> tuple[review_loop.Finding, review_loop.Adjudication | None]:
    """Validate one stored finding, returning it open beside any adjudication it carries.

    The finding comes back parted from its adjudication on purpose: the rebuild in
    `parse_stored_loop` folds findings in by round through `first_review` and
    `next_round`, then closes each one through `adjudicate`, so every semantic check
    — the severity vocabulary, the round stamp, the duplicate-id rule, the four
    routes and the fourth route's three restrictions — is the loop module's own,
    run on this record rather than duplicated beside it.
    """
    if not isinstance(raw, dict):
        raise LoopStateError(LOOP_FINDINGS_ERROR)
    identifier = raw.get("id")
    severity = raw.get("severity")
    round_raised = raw.get("round_raised")
    if not isinstance(identifier, str) or not identifier:
        raise LoopStateError(LOOP_FINDING_FIELDS_ERROR)
    if not isinstance(severity, str) or severity not in review_loop.SEVERITY_RANK:
        raise LoopStateError(LOOP_FINDING_FIELDS_ERROR)
    if (
        not isinstance(round_raised, int)
        or isinstance(round_raised, bool)
        or round_raised < 0
        or round_raised > rounds
    ):
        raise LoopStateError(LOOP_FINDING_FIELDS_ERROR)
    adjudication: review_loop.Adjudication | None = None
    if "adjudication" in raw and raw["adjudication"] is not None:
        document = raw["adjudication"]
        if not isinstance(document, dict):
            raise LoopStateError(LOOP_ADJUDICATION_SHAPE_ERROR)
        route = document.get("route")
        issue = document.get("issue", "")
        conditional_on = document.get("conditional_on", "")
        if (
            not isinstance(route, str)
            or not isinstance(issue, str)
            or not isinstance(conditional_on, str)
        ):
            raise LoopStateError(LOOP_ADJUDICATION_SHAPE_ERROR)
        adjudication = review_loop.Adjudication(route, issue, conditional_on)
    return review_loop.Finding(identifier, severity, round_raised), adjudication


def parse_stored_loop(document: object, issue: int) -> review_loop.Loop:
    """Validate a stored loop document and rebuild it through the loop's own gates.

    Shape validation here; semantics in `review_loop`. A document that parses but
    could not have been written — a severity outside the four, an id two rounds
    share, a round stamp beyond the rounds recorded, an adjudication on a finding
    the loop does not hold, the fourth route above Medium or without its named
    issue and condition — raises that module's own `ReviewLoopError` through the
    rebuild, which is the point of routing every semantic decision there.
    """
    if not isinstance(document, dict):
        raise LoopStateError(LOOP_VERSION_ERROR)
    version = document.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version != LOOP_VERSION:
        raise LoopStateError(LOOP_VERSION_ERROR)
    recorded = document.get("issue")
    if not isinstance(recorded, int) or isinstance(recorded, bool) or recorded != issue:
        raise LoopStateError(LOOP_ISSUE_ERROR)
    rounds = document.get("review_rounds")
    if not isinstance(rounds, int) or isinstance(rounds, bool) or rounds < 0:
        raise LoopStateError(LOOP_ROUNDS_ERROR)
    raw_findings = document.get("findings")
    if not isinstance(raw_findings, list):
        raise LoopStateError(LOOP_FINDINGS_ERROR)
    parsed = [_stored_finding(item, rounds) for item in raw_findings]
    raised: dict[int, list[review_loop.Finding]] = {}
    closed: list[tuple[str, review_loop.Adjudication]] = []
    for finding, adjudication in parsed:
        raised.setdefault(finding.round_raised, []).append(finding)
        if adjudication is not None:
            closed.append((finding.id, adjudication))
    loop = review_loop.first_review(tuple(raised.get(0, ())))
    for number in range(1, rounds + 1):
        loop = review_loop.next_round(loop, tuple(raised.get(number, ())))
    for identifier, adjudication in closed:
        loop = review_loop.adjudicate(loop, identifier, adjudication)
    return loop


def load_loop(root: Path, issue: int) -> review_loop.Loop:
    """Read one issue's stored loop, refusing anything that cannot safely govern.

    A missing record raises `FileNotFoundError` untouched for the caller to read
    as absence — the fact the ladder distinguishes from an unreadable one — and
    everything else lands as `LoopStateError` carrying the path and, where the
    rebuild produced it, `review_loop`'s own words.
    """
    path = loop_path(root, issue)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, ValueError) as error:
        message = f"{path}: {error}"
        raise LoopStateError(message) from error
    try:
        return parse_stored_loop(document, issue)
    except ValueError as error:
        message = f"{path}: {error}"
        raise LoopStateError(message) from error


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
        " 2026-08-14, #334) — then land again. Nothing was pushed.",
    )


def _authorship_lines(authorship: dispatch.Authorship) -> tuple[str, ...]:
    """Render the honest one-line account of the authorship scan: checked, or why not.

    Called only past the states that refuse, so the first arm is the defensive
    restatement of a state the ladder never reaches rather than a fourth outcome.
    """
    if authorship.why == UNREADABLE:
        return ("authorship=unchecked reason=records_unreadable",)
    if not authorship.potential:
        return (f"authorship=none_recorded reason={authorship.why or NO_AUTHORSHIP}",)
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
    checked = review_exchange.verify(verdict, dispatch_root)
    if not isinstance(checked, review_exchange.Bound):
        return Outcome(checked, ())
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
    loop_file = loop_path(review_root, issue)
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
                    " adjudicates them. Run the adjudication (`just review-loop`)"
                    " — every above-Low finding owes its one route before this"
                    " lands (ADR-0071 ruling 4). Nothing was pushed.",
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
            ),
        )
    try:
        loop = load_loop(review_root, issue)
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
    recorded = {finding.id: finding for finding in loop.findings}
    disagreed = tuple(
        finding
        for finding in above
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
    return Outcome(
        None,
        (
            *_authorship_lines(authorship),
            f"review_dispatch={binding.dispatch_id} profile={binding.profile} lane={binding.lane}",
            f"verdict_sha={sha}",
            f"findings={len(verdict.findings)} above_low={len(above)} open_above_low=0",
            f"loop={loop_file}",
            *_alternates_lines(binding),
        ),
    )
