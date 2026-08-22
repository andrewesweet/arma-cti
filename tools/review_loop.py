"""The never-alone decision surface in one module (ADR-0071 ruling 4, #331, #333).

Five things, and the issue that created this module asked for them **deep rather than
split**: exemption evaluation, the round budget, per-finding adjudication state, the
escalation-condition evaluation #325 built, and — added by #333, over the state #331
landed rather than beside it — the terminus and the loop's telemetry. The alternative
smears the loop's rules across the landing protocol, the routing-policy reader and a
config parser, with no single place to test them — and the consumers already sequenced
(#333's arbiter in `tools/arbiter.py`, #334's landing refusal) all read this one module
rather than each re-deriving a half of it.

## The exemption half, and why its scope is inverted

Every landing is reviewed **except** entries on a named list — so a directory nobody
anticipated is covered by default. That is the opposite of the shape that keeps biting this
project: an allowlist of covered surfaces reads an unlisted surface as cleared. The routing
policy's own coverage sentence is the model (*"a surface this file does not name is
uncovered, never cleared"*), and `routing_policy.COVERAGE_UNSTATED` says it. Here the
inversion is in the code: an unlisted path is a refusal to exempt, and exemption is the
derived answer that has to be earned by every path in the diff matching a listed entry.

The list lives as data in `config/review-exemptions.json`, read on every call with no module
cache — the same discipline `tools/escalation.py` and `tools/routing_policy.py` run under.
Each entry carries its reason beside it, visible in the diff, the shape
`tools/mutation_smoke.py`'s `NO_MUTABLE_SUBJECT` uses. It ships **empty**: nothing is exempt
yet, because the only thing ADR-0071 says may grow it is evidence — the pre-registered
question of whether pre-landing review of gated work finds anything the gates and
post-landing review would not (ruling 6). An entry joins by being argued at a retro on that
evidence, never by an agent's convenience in the moment; the `growth` field of the file says
so.

**The list is itself a gate, so a diff touching it can never be exempt under it.** That is
ruling 4's own sentence, and it is what makes the inverted scope safe against the obvious
attack: a branch cannot add itself to the list in the same diff that the list would judge,
because touching the list is itself the never-exempt case. It also settles *which copy*
judges a landing, a question #302 answered for the routing policy by reading fetched
`origin/main`. Here the two copies cannot disagree on any candidate diff: a diff that does
not touch the list sees the same list in the worktree and on `origin/main`, and a diff that
does touch it is never exempt whichever copy is read. #364's blindness — a worktree gate
reading the policy from the parent checkout — does not reach this module, which reads
whatever path it is handed and changes no policy.

## The loop half: rounds, findings, four adjudication routes

A **round** is one fix-and-re-review cycle; the first review is round zero, so the
escalation wall fires after the third re-review. The count is decided here because "three
rounds" was ambiguous by one and a tool has to decide it — `escalation.THREE_ROUND_THRESHOLD`
is the constant, and this module never restates the number.

A **finding** carries the severity the reviewer assigned
(`docs/agents/review-severity.md`: critical, high, medium, low) and is closed by at most one
**adjudication**. Four routes, and the fourth is the human's ruling of 2026-08-14 on #334,
which amends ruling 4:

- `fixed` — the implementer's accepted fix;
- `arbiter_upheld` — a dispute the arbiter ruled on and upheld;
- `arbiter_dismissed` — an arbiter dismissal;
- `accepted_and_filed` — Medium or below, where the harm is conditional on named work
  outside the diff. The implementer agrees the finding is real, states why the fix does not
  belong in this diff, and files it as an issue on the originating item before landing; the
  adjudication carries both the named condition and the issue it became. Not available
  above Medium, and not available without the condition named — "it only bites if someone
  later does X" is the test, and X must be nameable to be adjudicable.

One adjudication per finding is terminal: a finding the next round re-reports is a **new**
finding with a new id, never a reopening — the ruling's own move, which is why `next_round`
refuses an id an earlier round already carried. What bounds re-argument is this closure;
what
bounds the loop is the round budget above. And the two arbiter routes carry a
**precondition, decided per finding** (`escalation_fires_on`): an arbiter verdict on a
finding is admissible only where the escalation that produces an arbiter has fired **on that
finding** — the wall holds and this finding is one of the held-across findings it read —
because an arbiter nobody's escalation chose is a verdict with no judge. Round 1 made the
precondition a property of the loop, and round 2's Critical was exactly what that buys: once
an arbiter closes the wall-held findings, a new finding raised in a later round inherited the
historical verdict as its licence — the reopening the ticket forbids, arriving as a licence
rather than as a re-raise.

The **stop condition** — nothing above Low remains unadjudicated — is `stop_condition`.
Low findings never block and are recorded; that is the severity document's rule, restated
as code because #334's landing refusal reads it from here.

## The escalation bridge, and the material change it makes

`tools/escalation.py`'s four transferring-escalation conditions fire only on facts a caller
supplies, and its docstring records that `review_rounds` and `finding_above_low` were **not
mechanically recorded** when it landed: conditions 1, 2 and 3 could not fire. This module is
the recorder of those two wall facts — `item_state` derives both off a live loop, recorded
rather than `None` — and that is what makes **condition 1** fireable for the first time, the
arbiter it names staying a caller-resolved fact. Conditions 2 and 3 read the same wall but
wait on more: 2 on a recorded `prior` history and 3 on recorded `attempts`, neither fact a
loop carries, so both still emit nothing until those facts are recorded (#348 banks that
sequencing as open, not complete). The bridge delegates rather than restates: one wall
constant, one condition table, one evaluation, all owned where they already lived.

## The terminus and the telemetry (#333)

The **terminus** is ruling 4's ending as one read: the pre-declared default's gate
(`stop_condition` — nothing above Low unadjudicated), the filings every upheld finding is
owed on the originating item, and the record of every dismissal — ADR-0071's own cost
case being a real Critical an arbiter rejects landing with no trace, which is why a
dismissal is a first-class shape and not an absence. The **telemetry** is ruling 6's
observables as events — rounds, escalations, dispute outcomes, terminuses, the arbiter
invocation homed in `tools/arbiter.py` — because rounds leave no trace in a diff, and a
loop shipped without them is a loop whose cost cannot be recovered.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple

# tools/ holds standalone scripts rather than an importable package, so a sibling import
# needs the script's own directory on the path — the device `dispatch.py` and `brief.py`
# use.
sys.path.insert(0, str(Path(__file__).parent))

import escalation
import otel_event
import routing_policy
import worktree
from worktree import GitError, git, remote_ref_sha

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Mapping

EXEMPTIONS_RELATIVE: Final = Path("config/review-exemptions.json")


class ReviewLoopError(ValueError):
    """An exemption table or loop state whose shape cannot safely govern a landing."""


# --------------------------------------------------------------------------- the exemption table


class Exemption(NamedTuple):
    """One entry: the surface it exempts, and the reason beside it, visible in the diff.

    `surface` matches a diff path the way a routing class's landing prefixes do — a
    directory prefix when it ends in `/`, an exact file otherwise — via
    `routing_policy.path_matches`, so the two tables cannot grow different ideas of what a
    prefix means.
    """

    surface: str
    reason: str


class Exemptions(NamedTuple):
    """The parsed exemption table."""

    source: str
    entries: tuple[Exemption, ...]


class ExemptionRead(NamedTuple):
    """A parsed exemption table or the reason reading it failed."""

    exemptions: Exemptions | None
    error: str = ""


VERSION_ERROR: Final = "exemptions must be a version 1 object"
ENTRIES_LIST_ERROR: Final = "entries must be a list"
ENTRY_OBJECT_ERROR: Final = "each entry must be an object"
ENTRY_FIELDS_ERROR: Final = "each entry must carry surface and reason"
ENTRY_UNIQUE_ERROR: Final = "exemption surfaces must be unique"
SELF_EXEMPTION_ERROR: Final = (
    "an entry may not name the exemption list itself — the list is a gate, and a diff"
    " touching it can never be exempt under it (ADR-0071 ruling 4)"
)


def _entry(raw: object) -> Exemption:
    if not isinstance(raw, dict):
        raise ReviewLoopError(ENTRY_OBJECT_ERROR)
    try:
        surface = str(raw["surface"])
        reason = str(raw["reason"])
    except (KeyError, TypeError) as error:
        raise ReviewLoopError(ENTRY_FIELDS_ERROR) from error
    if not surface or not reason:
        raise ReviewLoopError(ENTRY_FIELDS_ERROR)
    # The self-exemption refusal is decided per diff in `exemption_decision`; refusing the
    # declaration at parse time as well means a list that tried to except itself never
    # parses far enough to govern anything.
    if surface == EXEMPTIONS_RELATIVE.as_posix():
        raise ReviewLoopError(SELF_EXEMPTION_ERROR)
    return Exemption(surface, reason)


def parse_exemptions(text: str) -> Exemptions:
    """Validate enough shape that a partial or self-serving table can never govern silently.

    The shipped table is held to the same shape as the live one by
    `tests/unit/test_review_loop.py`, which reads the file this repository ships; this
    parser governs every copy a landing might be judged by.
    """
    document = json.loads(text)
    if not isinstance(document, dict) or document.get("version") != 1:
        raise ReviewLoopError(VERSION_ERROR)
    raw = document.get("entries")
    if not isinstance(raw, list):
        raise ReviewLoopError(ENTRIES_LIST_ERROR)
    entries = tuple(_entry(item) for item in raw)
    surfaces = [entry.surface for entry in entries]
    if len(set(surfaces)) != len(surfaces):
        raise ReviewLoopError(ENTRY_UNIQUE_ERROR)
    return Exemptions(source=str(document.get("source", "")), entries=entries)


def read_exemptions(path: Path) -> ExemptionRead:
    """Read on every call. There is intentionally no module cache or startup load."""
    try:
        return ExemptionRead(parse_exemptions(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, json.JSONDecodeError, KeyError, TypeError) as error:
        return ExemptionRead(None, f"{path}: {error}")


# ------------------------------------------------------------------- the exemption decision


# The kind a consumer narrows on, by value rather than `isinstance`, for the reason
# `escalation` documents: `load_tool` re-execs a tools/ script, so two copies of this module
# hold different class objects and identity checks across them are False (escalation's
# #325 round 3, claim 1 — the same trap one module later).
REVIEW_REQUIRED: Final = "review_required"
EXEMPT: Final = "exempt"
UNREADABLE: Final = "unreadable"


class ReviewRequired(NamedTuple):
    """A landing this table does not exempt. The default: unlisted means covered.

    `evidence` names why — each unlisted path, and each path that is the list itself. The
    only outcome a landing gate may treat as "no review needed" is `Exempt`, so a consumer
    that has not narrowed past `Unreadable` cannot reach this by accident.
    """

    evidence: tuple[str, ...]

    @property
    def kind(self) -> str:
        """The value a consumer narrows on; a module re-exec cannot change it."""
        return REVIEW_REQUIRED


class Exempt(NamedTuple):
    """Every path in the diff matched a listed entry.

    `matched` pairs each path with the reason its entry carries, so the exemption a landing
    claims is quotable from the decision that granted it.
    """

    matched: tuple[tuple[str, str], ...]

    @property
    def kind(self) -> str:
        """The value a consumer narrows on; a module re-exec cannot change it."""
        return EXEMPT


class Unreadable(NamedTuple):
    """The table could not be read, so no exempt answer is honestly available.

    #347's source-unavailable discipline: neither "exempt" nor the confident
    `ReviewRequired` that names real unlisted paths — an enforcing consumer fails closed
    to requiring review on this state, and the reasons say why it never got to decide.
    """

    reasons: tuple[str, ...]

    @property
    def kind(self) -> str:
        """The value a consumer narrows on; a module re-exec cannot change it."""
        return UNREADABLE


Decision = ReviewRequired | Exempt | Unreadable

EMPTY_PATHS_EVIDENCE: Final = (
    "no_paths=a decision with no paths exempts nothing — exemption is earned per path and"
    " never by default"
)
SELF_EXEMPTION_EVIDENCE: Final = (
    "self_exemption={path}: the exemption list is a gate, and a diff touching it is never"
    " exempt under it (ADR-0071 ruling 4)"
)


def _match(entry: Exemption, path: str) -> bool:
    return routing_policy.path_matches(path, entry.surface)


def exemption_decision(read: ExemptionRead, paths: tuple[str, ...]) -> Decision:
    """Decide whether a landing's diff is exempt from review. Inverted, so fail-closed.

    The order of the guards is the inverted scope said in code:

    1. A table that could not be read is `Unreadable` — never exempt, and never the
       confident refusal either.
    2. No paths at all is a caller error refused rather than vacuously exempted; `all()`
       over an empty diff would otherwise return the fail-open answer.
    3. A path that **is** the list forces `ReviewRequired` whatever else the diff touches —
       the self-exemption refusal.
    4. Otherwise every path must match a listed entry; the first unlisted one is named.
    """
    if read.exemptions is None:
        return Unreadable((read.error or "the exemption table could not be read",))
    if not paths:
        return ReviewRequired((EMPTY_PATHS_EVIDENCE,))
    list_path = EXEMPTIONS_RELATIVE.as_posix()
    evidence = [SELF_EXEMPTION_EVIDENCE.format(path=p) for p in paths if p == list_path]
    if evidence:
        return ReviewRequired(tuple(evidence))
    matched: list[tuple[str, str]] = []
    unlisted: list[str] = []
    for path in paths:
        for entry in read.exemptions.entries:
            if _match(entry, path):
                matched.append((path, entry.reason))
                break
        else:
            unlisted.append(path)
    if unlisted:
        return ReviewRequired(tuple(f"unlisted={path}" for path in unlisted))
    return Exempt(tuple(matched))


# --------------------------------------------------------------------------- the loop state

# The four severities of docs/agents/review-severity.md, worst first. Orderable by rank so
# "above Low" and "Medium or below" are decisions about positions rather than string lists.
CRITICAL: Final = "critical"
HIGH: Final = "high"
MEDIUM: Final = "medium"
LOW: Final = "low"
SEVERITIES: Final = (CRITICAL, HIGH, MEDIUM, LOW)
SEVERITY_RANK: Final[dict[str, int]] = {name: rank for rank, name in enumerate(SEVERITIES)}
SEVERITY_ERROR: Final = (
    f"a finding's severity must be one of {', '.join(SEVERITIES)} — the four levels of"
    " docs/agents/review-severity.md, which the loop's stop condition reads"
)

# The four adjudication routes (ADR-0071 ruling 4; the fourth added by the human's ruling of
# 2026-08-14 on #334). One adjudication per finding is terminal.
FIXED: Final = "fixed"
ARBITER_UPHELD: Final = "arbiter_upheld"
ARBITER_DISMISSED: Final = "arbiter_dismissed"
ACCEPTED_AND_FILED: Final = "accepted_and_filed"
ROUTES: Final[frozenset[str]] = frozenset(
    {FIXED, ARBITER_UPHELD, ARBITER_DISMISSED, ACCEPTED_AND_FILED}
)
ROUTE_ERROR: Final = (
    f"an adjudication must name one of {', '.join(sorted(ROUTES))} — the four routes of"
    " ADR-0071 ruling 4, the fourth added by the human ruling of 2026-08-14 on #334"
)
ARBITER_UNNAMED_ERROR: Final = (
    "an arbiter route must name the arbiter that ruled — the profile the escalation"
    " transferred to, read from the escalation record rather than typed, so an unarbitrated"
    " dismissal is distinguishable from an arbitrated one on the record a landing quotes"
    " (#334 round 2)"
)
UNKNOWN_FINDING_ERROR: Final = "no open finding carries that id in this loop"
CLOSED_FINDING_ERROR: Final = (
    "that finding already carries its one adjudication and is closed — a finding the next"
    " round re-reports is a new finding with a new id, never a reopening"
)
DUPLICATE_FINDING_ERROR: Final = (
    "a finding id may appear in one round only — the same id in a later round is the"
    " reopening ruling 4 forbids, wearing the id it re-opened"
)
ROUND_STAMP_ERROR: Final = (
    "a finding's round is the round that raised it, stamped by the loop — one raised at"
    " another round is a caller error, not a finding to re-stamp"
)
ROUTE_SEVERITY_ERROR: Final = (
    f"{ACCEPTED_AND_FILED} is available at {MEDIUM} and below only — a finding above"
    f" {MEDIUM} is fixed, disputed to an arbiter, or blocks the landing (human ruling"
    " 2026-08-14, #334)"
)
FILED_ISSUE_ERROR: Final = (
    f"{ACCEPTED_AND_FILED} must name the issue it was filed as — the landing record carries"
    " the adjudication naming the issue it became, and an unnamed issue names nothing"
)
CONDITIONAL_ON_ERROR: Final = (
    f"{ACCEPTED_AND_FILED} must name the work outside the diff the harm is conditional on —"
    " 'it only bites if someone later does X' is the test, and X must be nameable to be"
    " adjudicable (human ruling 2026-08-14, #334)"
)
ARBITER_UNAUTHORISED_ERROR: Final = (
    "an arbiter route on one finding is admissible only where the escalation that produces an"
    " arbiter has fired on that finding — the three-round wall holding, and this finding one"
    " of the held-across findings it read. A finding raised in a later round is a new item,"
    " not a reopening: an earlier round's arbiter verdict is not its licence, and a Low is"
    " never what the escalation fires on (ADR-0071 ruling 4; #333 rounds 1 and 2, the"
    " Critical both times)"
)


def above_low(severity: str) -> bool:
    """Whether a severity is above Low — the band the stop condition adjudicates."""
    return SEVERITY_RANK[severity] < SEVERITY_RANK[LOW]


class Finding(NamedTuple):
    """One review finding: its identity, its severity, the round that raised it.

    `adjudication` is `None` while the finding is open and exactly one route's record once
    closed. `round_raised` is stamped by `first_review`/`next_round`, never supplied
    independently.
    """

    id: str
    severity: str
    round_raised: int
    adjudication: Adjudication | None = None


class Adjudication(NamedTuple):
    """One finding's terminal disposition, in one of the four routes.

    `issue` and `conditional_on` are required by `ACCEPTED_AND_FILED` and unused by the
    other three routes: an arbiter verdict needs no issue named (the terminus files what it
    upholds, #333's work) and a fix is in the diff under review.

    `arbiter` names the profile the escalation transferred to, and the two arbiter routes
    are refused without it (`ARBITER_UNNAMED_ERROR`). It is the one field that makes an
    arbitrated dismissal *distinguishable on the record* from an unarbitrated one — the
    same-user limit means it is not forgery-proof and nothing here pretends otherwise, but
    round 2 of #334's review was right that the writer is the surface where the field could
    be asked for, and a route that stands in for a ruling should name the judge that gave
    it. The CLI fills it from `escalation.json` rather than from a flag, so the name on the
    record is the one `escalate` resolved.

    `unchecked` is that resolution's own qualification, carried rather than dropped
    (round 2 re-review, Low 7): the exclusion scan behind the arbiter may have been
    partial, which is why ruling 4's route is `reviewing_checked` and never
    `reviewing_verified`, and a record naming the arbiter alone says something stronger
    than the resolution did. Absent from a stored adjudication it reads as `False`,
    which is safe in the direction that matters here and unlike the escalation record's
    own `unchecked`: this field qualifies a name, where that one decides a gate — every
    record carrying an arbiter at all was written by `adjudicate`, which writes both.
    """

    route: str
    issue: str = ""
    conditional_on: str = ""
    arbiter: str = ""
    unchecked: bool = False


class Loop(NamedTuple):
    """One item's review loop.

    `review_rounds` is completed fix-and-re-review cycles; the first review is round zero.
    `findings` carries every finding every round raised, open and closed, because the
    landing record and the post-landing seat read the closed ones too.
    """

    review_rounds: int
    findings: tuple[Finding, ...]


def _check_ids(existing: tuple[Finding, ...], raised: Iterable[Finding]) -> None:
    seen = {finding.id for finding in existing}
    for finding in raised:
        if finding.id in seen:
            raise ReviewLoopError(DUPLICATE_FINDING_ERROR)
        seen.add(finding.id)


def _check_severities(raised: Iterable[Finding]) -> None:
    for finding in raised:
        if finding.severity not in SEVERITY_RANK:
            raise ReviewLoopError(SEVERITY_ERROR)


def first_review(raised: tuple[Finding, ...]) -> Loop:
    """Open a loop at round zero with the first review's findings.

    `round_raised` must be `0` here — the stamp is validated rather than rewritten, so a
    caller cannot smuggle a finding in at a round it was not raised.
    """
    _check_severities(raised)
    _check_ids((), raised)
    for finding in raised:
        if finding.round_raised != 0:
            raise ReviewLoopError(ROUND_STAMP_ERROR)
    return Loop(review_rounds=0, findings=raised)


def next_round(loop: Loop, raised: tuple[Finding, ...]) -> Loop:
    """Record one fix-and-re-review cycle: the round advances and the new findings join.

    The new findings must carry the round being recorded. An id any earlier round already
    carried is refused — the re-report the ruling makes a *new* finding is a new id, and the
    refusal here is what stops a reopening being smuggled through as a re-raise.
    """
    _check_severities(raised)
    _check_ids(loop.findings, raised)
    rounds = loop.review_rounds + 1
    for finding in raised:
        if finding.round_raised != rounds:
            raise ReviewLoopError(ROUND_STAMP_ERROR)
    return Loop(review_rounds=rounds, findings=(*loop.findings, *raised))


def escalation_fires_on(loop: Loop, finding: Finding) -> bool:
    """Whether the escalation that produces an arbiter has fired **on this finding**.

    A precondition on the route, not a stricter enum — the route set is the ruling's own
    four and does not move while the loop does. Three conjuncts, all about this finding:

    - **The wall holds** — `at_wall(loop)`: three rounds with a finding above Low still
      held across, delegated to `escalation.at_three_round_wall` rather than restated here.
      The finding under adjudication is open at its own adjudication (`adjudicate` refuses
      a closed one first), so when the two conjuncts below hold, this finding is itself one
      of the findings keeping the wall true — verdict order within one arbitration cannot
      decide which verdicts are legal, without any sibling clause.
    - **This finding is above Low** — the escalation fires on the blocking band; a Low is
      never what it fires on, and a Low never blocks, so there is no dispute for an arbiter
      to settle on one.
    - **This finding is held across** — raised at a round below the round count, the
      budget's own distinction. A finding the current round introduced (#356's shape) is a
      new item the escalation has not fired on: it takes another fix round, or its own wall.

    Round 2's Critical, through the door round 1 left open: a loop-level precondition —
    "the wall holds, *or any finding carries an arbiter verdict*" — let a new finding
    raised after an arbitration inherit that historical verdict as its licence, which is the
    reopening #333's own body forbids, arriving as a licence rather than as a re-raise. The
    recorded verdict is a fact about the finding it closed, never about the loop.
    """
    return (
        at_wall(loop) and above_low(finding.severity) and finding.round_raised < loop.review_rounds
    )


def _route_checks(loop: Loop, finding: Finding, adjudication: Adjudication) -> None:
    """Enforce the routes' own restrictions: the arbiter precondition, the fourth route's three."""
    if adjudication.route in (ARBITER_UPHELD, ARBITER_DISMISSED):
        if not escalation_fires_on(loop, finding):
            raise ReviewLoopError(ARBITER_UNAUTHORISED_ERROR)
        if not adjudication.arbiter:
            raise ReviewLoopError(ARBITER_UNNAMED_ERROR)
    if adjudication.route == ACCEPTED_AND_FILED:
        if SEVERITY_RANK[finding.severity] < SEVERITY_RANK[MEDIUM]:
            raise ReviewLoopError(ROUTE_SEVERITY_ERROR)
        if not adjudication.issue:
            raise ReviewLoopError(FILED_ISSUE_ERROR)
        if not adjudication.conditional_on:
            raise ReviewLoopError(CONDITIONAL_ON_ERROR)


def adjudicate(loop: Loop, finding_id: str, adjudication: Adjudication) -> Loop:
    """Close one finding with its one adjudication, returning the loop that carries it.

    Every refusal here is typed: an unknown id, a finding already closed (the
    one-verdict-then-closed rule), an unknown route, the arbiter precondition (an arbiter
    route on a finding the escalation has not fired on), and the fourth route's
    three restrictions. The adjudication is terminal — the returned loop's finding can
    never be adjudicated again, which is what bounds re-argument; the round budget bounds
    the loop.
    """
    if adjudication.route not in ROUTES:
        raise ReviewLoopError(ROUTE_ERROR)
    updated: list[Finding] = []
    found = False
    for finding in loop.findings:
        if finding.id != finding_id:
            updated.append(finding)
            continue
        if finding.adjudication is not None:
            raise ReviewLoopError(CLOSED_FINDING_ERROR)
        _route_checks(loop, finding, adjudication)
        updated.append(finding._replace(adjudication=adjudication))
        found = True
    if not found:
        raise ReviewLoopError(UNKNOWN_FINDING_ERROR)
    return Loop(loop.review_rounds, tuple(updated))


def stored_route_violations(loop: Loop) -> tuple[str, ...]:
    """Name every closed finding whose adjudication could not have been written.

    `parse_loop` validates the shape and leaves the *route's* preconditions alone, and its
    docstring says why for the arbiter one: it governs the act of adjudicating, and a
    verdict recorded before the precondition existed must still be readable. The fourth
    route's three restrictions are not like that — they are the ruling's own words about
    what the disposition *means*, so a record carrying `accepted_and_filed` on a Critical,
    or without the issue it became, or without the work its harm is conditional on, is a
    record no writer would have produced.

    A reader that needs to act on those restrictions asks here rather than re-deriving
    them: #334's landing rung is the reader, and round 1 got the answer by rebuilding the
    whole loop through `adjudicate`, which is not available to a reader once the canonical
    parser is the one that (rightly) does not repudiate recorded verdicts.
    """
    violations: list[str] = []
    for finding in loop.findings:
        adjudication = finding.adjudication
        if adjudication is None or adjudication.route != ACCEPTED_AND_FILED:
            continue
        if SEVERITY_RANK[finding.severity] < SEVERITY_RANK[MEDIUM]:
            violations.append(f"{finding.id}: {ROUTE_SEVERITY_ERROR}")
        if not adjudication.issue:
            violations.append(f"{finding.id}: {FILED_ISSUE_ERROR}")
        if not adjudication.conditional_on:
            violations.append(f"{finding.id}: {CONDITIONAL_ON_ERROR}")
    return tuple(violations)


def open_findings(loop: Loop) -> tuple[Finding, ...]:
    """Return the findings still awaiting their one adjudication."""
    return tuple(finding for finding in loop.findings if finding.adjudication is None)


def open_above_low(loop: Loop) -> tuple[Finding, ...]:
    """Return the open findings above Low — the band the stop condition adjudicates."""
    return tuple(finding for finding in open_findings(loop) if above_low(finding.severity))


def holding_above_low(loop: Loop) -> bool:
    """Whether a finding above Low is held across rounds — escalation's `finding_above_low`.

    Held across, not merely open: `round_raised` below the round count, so the budget
    counts rounds spent failing to close a finding rather than capping how many defects a
    branch may reveal. Two live shapes fix the semantics (#333):

    - **#326** — the claim was raised in round 2 and still open at round 3: held, and the
      wall fires. #348 the same, escalated one round early by choice.
    - **#356/#327** — round 3's re-review raised a finding of its own, everything earlier
      closed: introduced by the round, not held across it, so no escalation and another
      fix round is taken. The distinction is the whole of the budget: a wall that cannot
      express it escalates work that should not escalate and vice versa.

    The first review (round zero) holds nothing across by definition — no round has been
    failed yet — and the wall's three-round floor makes that indistinguishable to
    condition one either way. `stop_condition` is deliberately **not** narrowed to match:
    a landing is blocked by any open finding above Low, whenever raised; only the
    escalation budget counts held-across.
    """
    return any(finding.round_raised < loop.review_rounds for finding in open_above_low(loop))


def stop_condition(loop: Loop) -> bool:
    """Return whether the loop's stop condition holds: nothing above Low remains unadjudicated.

    Low findings never block and are recorded; that is the severity document's rule. #334's
    landing refusal reads this through, so it is decided once, here.
    """
    return not open_above_low(loop)


def at_wall(loop: Loop) -> bool:
    """Return whether the loop sits at the three-round wall conditions one to three share.

    Delegates to `escalation.at_three_round_wall` over the recorded facts, so the wall
    cannot mean one thing to the escalation table and another to the loop that feeds it.
    """
    return escalation.at_three_round_wall(item_state(loop))


# --------------------------------------------------------------------------- the escalation bridge


def item_state(
    loop: Loop,
    routing_class: int | None = None,
    attempts: tuple[escalation.Attempt, ...] | None = None,
) -> escalation.ItemState:
    """Derive the escalation facts a live loop records.

    `review_rounds` and `finding_above_low` arrive as recorded facts rather than `None` —
    the two wall facts, which is what makes condition 1 of
    `config/escalation-conditions.json` fireable for the first time. Conditions 2 and 3 read
    the same wall but wait on facts a loop does not carry: condition 2 on the `prior` history
    this function's caller supplies or does not, condition 3 on `attempts`, which stays
    `None` until the observatory records it. `routing_class` stays a caller-supplied fact
    (it is recorded on the dispatch record, #323, not in the loop).
    """
    return escalation.ItemState(
        routing_class=routing_class,
        review_rounds=loop.review_rounds,
        finding_above_low=holding_above_low(loop),
        attempts=attempts,
    )


def evaluate_escalation(  # noqa: PLR0913 — the six parameters are escalation.Context's own three facts plus the read and the loop they derive from; the bridge's job is exactly to carry them together
    read: escalation.ReadResult,
    loop: Loop,
    *,
    routing_class: int | None = None,
    prior: tuple[escalation.ItemState, ...] | None = None,
    arbiter: str | None = None,
    attempts: tuple[escalation.Attempt, ...] | None = None,
) -> escalation.Evaluation:
    """Evaluate the transferring-escalation conditions over a live loop.

    The whole of `tools/escalation.py`'s evaluation, homed where its inputs are recorded.
    The outcome is escalation's own discriminated `Evaluation` — a consumer narrows on its
    `kind` value, never `isinstance`, for the re-exec reason both modules document.
    """
    return escalation.evaluate(
        read,
        escalation.Context(
            item=item_state(loop, routing_class, attempts),
            prior=prior,
            arbiter=arbiter,
        ),
    )


# --------------------------------------------------------------------------- the terminus


class Filing(NamedTuple):
    """One finding the terminus owes a filed issue for, on the originating item.

    The filing act itself is the caller's — this module names what is owed, never posts
    it. The live practice it encodes: #326's arbiter ordered #365 filed with a date,
    #348's ordered #374, and neither left the trace to memory.
    """

    finding: str
    severity: str
    round_raised: int


class Dismissal(NamedTuple):
    """One arbiter dismissal, carried to the record rather than left in the thread.

    ADR-0071's own cost accounting is why dismissals are a first-class shape and not an
    empty note: a real Critical the arbiter rejects is the one finding that lands with no
    trace and nothing downstream firing, so every dismissal is recorded and the
    post-landing seat reads them off the record.
    """

    finding: str
    severity: str
    round_raised: int


class Terminus(NamedTuple):
    """What the pre-declared default requires before it may apply (#333).

    `default_applies` is `stop_condition` — nothing above Low unadjudicated — read here
    as the default's own gate. `filings` and `dismissals` are what the landing owes: the
    upheld filed, the dismissals recorded. `ACCEPTED_AND_FILED` findings do not appear in
    either because their adjudication already names the issue they became; `fixed`
    findings appear in neither because the diff under review is their trace.
    """

    default_applies: bool
    filings: tuple[Filing, ...] = ()
    dismissals: tuple[Dismissal, ...] = ()


def terminus(loop: Loop) -> Terminus:
    """Compute what the loop's end owes: the default's gate, the filings, the dismissals.

    Ruling 4's terminus sentence — the change lands, every finding the arbiter upheld is
    filed on the originating item, every dismissal recorded — as one read over the loop.
    The same call answers the convergent case (everything fixed: the default applies
    owing nothing) and the non-convergent one (the wall fired and an arbiter adjudicated
    what remained: the default applies owing filings and dismissals). A `default_applies`
    of False is an answer, not an error — an above-Low finding is still open, and #334's
    landing refusal is the consumer that refuses on it.

    Upheld findings are owed filings at any severity, the ruling's sentence carrying no
    severity qualifier of its own: the trace an upheld Low deserves is the same trace an
    upheld Critical gets, and the stop condition already treats the two differently where
    difference belongs.
    """
    filings = tuple(
        Filing(f.id, f.severity, f.round_raised)
        for f in loop.findings
        if f.adjudication is not None and f.adjudication.route == ARBITER_UPHELD
    )
    dismissals = tuple(
        Dismissal(f.id, f.severity, f.round_raised)
        for f in loop.findings
        if f.adjudication is not None and f.adjudication.route == ARBITER_DISMISSED
    )
    return Terminus(
        default_applies=stop_condition(loop),
        filings=filings,
        dismissals=dismissals,
    )


# --------------------------------------------------------------------------- telemetry

# Rounds leave no trace in a diff, so a loop shipped without telemetry is a loop whose
# cost cannot be recovered (#333). The observables are ADR-0071 ruling 6's own list —
# review rounds, escalations, arbiter invocations, dispute outcomes, landings — with the
# arbiter invocation homed in `tools/arbiter.py` beside the rule that resolves it. Events
# are pure constructors over loop state (the clock arrives as `at`, from the caller); the
# emitters wrap `otel_event.emit`, which never fails the caller and journals every event
# whether or not the collector took it.
JOURNAL: Final = Path.home() / ".arma-cti" / "review" / "journal.jsonl"

ROUND_EVENT: Final = "cti.review.round"
ESCALATION_EVENT: Final = "cti.review.escalation"
DISPUTE_EVENT: Final = "cti.review.dispute"
TERMINUS_EVENT: Final = "cti.review.terminus"


def round_event(loop: Loop, issue: str, at: float) -> otel_event.Event:
    """One review round recorded — the observable ruling 6 counts loops by."""
    raised = sum(1 for f in loop.findings if f.round_raised == loop.review_rounds)
    return otel_event.Event(
        name=ROUND_EVENT,
        at=at,
        attributes={
            "cti.issue": issue,
            "cti.review.round": loop.review_rounds,
            "cti.review.raised": raised,
            "cti.review.open_above_low": len(open_above_low(loop)),
            "cti.review.holding_above_low": holding_above_low(loop),
        },
        resource={"service.name": "arma-cti-review-loop", "cti.issue": issue},
    )


def escalation_event(
    evaluation: escalation.Evaluation,
    issue: str,
    at: float,
    arbiter: str = "",
) -> otel_event.Event:
    """One escalation evaluation recorded — firing, silence and unreadable input alike.

    A firing carries its condition ids and the arbiter it transfers to; the other two
    kinds carry empty ids, because an evaluation that could not answer is a state the
    observatory must count, not one it may read past (`no_firing`'s confident silence is
    reserved for inputs that all read). The arbiter travels the same way (#333 round 2,
    Medium 5): a resolved profile is an arbiter only where a firing transferred to it, so
    a `no_firing` or `unreadable` event carries an empty one whatever the caller resolved —
    the resolver's answer is who *would* arbitrate, and an event claiming that name without
    a transfer is a count of arbitrations that never happened. The evaluation's own `kind`
    travels too (#333 round 1, Medium 5): a count of events cannot tell a loop that
    confidently fired nothing from one whose condition table would not open, and the
    observatory's first question of an escalation signal is which of the three states it
    was.
    """
    conditions = ""
    attributed = ""
    if evaluation.kind == escalation.FIRING:
        conditions = ",".join(str(e.condition.id) for e in evaluation.emissions)
        attributed = arbiter
    return otel_event.Event(
        name=ESCALATION_EVENT,
        at=at,
        attributes={
            "cti.issue": issue,
            "cti.review.evaluation": evaluation.kind,
            "cti.review.conditions": conditions,
            "cti.review.arbiter": attributed,
        },
        resource={"service.name": "arma-cti-review-loop", "cti.issue": issue},
    )


def dispute_event(
    finding: Finding,
    adjudication: Adjudication,
    issue: str,
    at: float,
) -> otel_event.Event:
    """One dispute outcome recorded — the per-finding trace arbitration leaves behind."""
    return otel_event.Event(
        name=DISPUTE_EVENT,
        at=at,
        attributes={
            "cti.issue": issue,
            "cti.review.finding": finding.id,
            "cti.review.severity": finding.severity,
            "cti.review.round_raised": finding.round_raised,
            "cti.review.route": adjudication.route,
        },
        resource={"service.name": "arma-cti-review-loop", "cti.issue": issue},
    )


def terminus_event(end: Terminus, issue: str, at: float) -> otel_event.Event:
    """One terminus recorded — ruling 6's landings-per-issue observable.

    The filings and dismissals travel as `id:severity` identities rather than counts
    (#333 round 1, Medium 5): the terminus exists so that nothing lands with no trace,
    and a count is exactly the shape that says *a* Critical was dismissed while naming
    neither which finding nor at what severity. The identities are also what
    post-landing review reads back against the issue thread.
    """
    filings = ",".join(f"{f.finding}:{f.severity}" for f in end.filings)
    dismissals = ",".join(f"{d.finding}:{d.severity}" for d in end.dismissals)
    return otel_event.Event(
        name=TERMINUS_EVENT,
        at=at,
        attributes={
            "cti.issue": issue,
            "cti.review.default_applies": end.default_applies,
            "cti.review.filings": filings,
            "cti.review.dismissals": dismissals,
        },
        resource={"service.name": "arma-cti-review-loop", "cti.issue": issue},
    )


def _emit(event: otel_event.Event, journal: Path) -> bool:
    """Emit one loop event — bounded, journaled, never failing the caller."""
    return otel_event.emit(event, journal=journal)


def emit_round(loop: Loop, issue: str, at: float, journal: Path = JOURNAL) -> bool:
    """Emit one round event at the round's recording."""
    return _emit(round_event(loop, issue, at), journal)


def emit_escalation(
    evaluation: escalation.Evaluation,
    issue: str,
    at: float,
    arbiter: str = "",
    journal: Path = JOURNAL,
) -> bool:
    """Emit one escalation event at the evaluation that produced it."""
    return _emit(escalation_event(evaluation, issue, at, arbiter), journal)


def emit_dispute(
    finding: Finding,
    adjudication: Adjudication,
    issue: str,
    at: float,
    journal: Path = JOURNAL,
) -> bool:
    """Emit one dispute event at the adjudication that closed the finding."""
    return _emit(dispute_event(finding, adjudication, issue, at), journal)


def emit_terminus(end: Terminus, issue: str, at: float, journal: Path = JOURNAL) -> bool:
    """Emit one terminus event at the landing decision."""
    return _emit(terminus_event(end, issue, at), journal)


# --------------------------------------------------------------------------- the durable loop
#
# #333 round 1, High 5: the module shipped as a library whose `emit_*` helpers nothing
# called — a loop that lived only inside one process's memory could not survive the turn
# that opened it, let alone reach post-landing review. The durable half is one directory
# per issue under `REVIEW_ROOT` (outside every worktree, beside the journal), holding
# `loop.json` while the loop runs, `escalation.json` once an arbiter is resolved, and
# `landing.json` once the terminus has run. The command surface below is the production
# caller that drives all of it — every `emit_*` helper's first production caller.

REVIEW_ROOT: Final = Path.home() / ".arma-cti" / "review"
LOOP_VERSION: Final = 1
LOOP_FILE: Final = "loop.json"
ESCALATION_FILE: Final = "escalation.json"
LANDING_FILE: Final = "landing.json"
# The terminus's claim on the right to run: created `O_EXCL` before the first GitHub side
# effect (#333 round 2, High 4). A terminus is side effects on a remote plus local writes,
# which is not a transaction — the claim is what makes "once" true anyway: exactly one of
# two concurrent calls wins the create, and a call that died mid-post leaves the marker
# behind naming what it was about to post, so the retry refuses rather than filing every
# upheld finding twice. The claim file is also the landing record's former name: completion
# rewrites it in place and moves it onto `landing.json` with one atomic rename (#333 round 3),
# so the terminal state is structural — the rename is the fact, never two files kept in step.
# `landing.json` can appear only whole and only by that move, and no reachable state carries
# both files: before it the loop is in flight, after it the terminus is done, and a crash at
# any instant leaves the marker alone, which is the refusing answer.
PENDING_FILE: Final = "terminus.pending"

LOOP_VERSION_ERROR: Final = "a stored loop must be a version 1 object"
LOOP_ISSUE_ERROR: Final = "a stored loop must name its issue as a positive integer"
LOOP_ROUNDS_ERROR: Final = "a stored loop's review_rounds must be a non-negative integer"
LOOP_FINDINGS_ERROR: Final = "a stored loop's findings must be a list of finding objects"
FINDING_FIELDS_ERROR: Final = "each finding must carry a non-empty id, a severity and a round"
ADJUDICATION_SHAPE_ERROR: Final = (
    "a stored adjudication must be an object naming one of the four routes, with issue and"
    " conditional_on as strings when present"
)
ISSUE_MISMATCH_ERROR: Final = (
    "the stored loop names issue {stored} but was read as #{asked} — the wrong directory's"
    " state, never a loop to act on"
)
ROUND_RANGE_ERROR: Final = (
    "a finding's round must lie between 0 and the loop's review_rounds — one raised at a"
    " round the loop has not reached is state this loop never recorded"
)
REGRADE_ERROR: Final = (
    "the verdict re-grades a finding #{issue}'s loop already holds ({findings}) — a"
    " severity is the reviewer's and an id is the finding's, so the two records have"
    " drifted or a later round reused an id. A re-report is a new finding with a new id"
    " (ADR-0071 ruling 4's no-reopening rule); nothing was written, and the landing would"
    " refuse this same disagreement as review_finding_mismatch"
)
LOOP_UNWRITTEN_ERROR: Final = (
    "the loop for #{issue} could not be written to {target} — {reason}. Nothing was"
    " changed: the document is staged beside its target and renamed onto it, so a failed"
    " write leaves the loop as it stood"
)
LOOP_UNREADABLE_ERROR: Final = (
    "the stored loop for #{issue} under {root} will not read — {reason}. A loop that cannot"
    " be read cannot govern an act: repair or re-record it before driving this loop"
)


def _render_adjudication(adjudication: Adjudication) -> dict[str, object]:
    rendered: dict[str, object] = {"route": adjudication.route}
    if adjudication.issue:
        rendered["issue"] = adjudication.issue
    if adjudication.conditional_on:
        rendered["conditional_on"] = adjudication.conditional_on
    if adjudication.arbiter:
        rendered["arbiter"] = adjudication.arbiter
        # Written whenever an arbiter is, including as `false`: the qualification is
        # about the name beside it, so a record that carries the name and omits this
        # would be the dropped `unchecked` again in the document rather than in the code.
        rendered["arbiter_unchecked"] = adjudication.unchecked
    return rendered


def render_loop(issue: int, loop: Loop) -> dict[str, object]:
    """Render one loop as the document `loop.json` carries between turns."""
    return {
        "version": LOOP_VERSION,
        "issue": issue,
        "review_rounds": loop.review_rounds,
        "findings": [
            {
                "id": finding.id,
                "severity": finding.severity,
                "round_raised": finding.round_raised,
                **(
                    {"adjudication": _render_adjudication(finding.adjudication)}
                    if finding.adjudication is not None
                    else {}
                ),
            }
            for finding in loop.findings
        ],
    }


def _parse_adjudication(raw: object) -> Adjudication | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ReviewLoopError(ADJUDICATION_SHAPE_ERROR)
    route = str(raw.get("route", ""))
    if route not in ROUTES:
        raise ReviewLoopError(ROUTE_ERROR)
    issue = raw.get("issue", "")
    conditional_on = raw.get("conditional_on", "")
    arbiter = raw.get("arbiter", "")
    unchecked = raw.get("arbiter_unchecked", False)
    if (
        not isinstance(issue, str)
        or not isinstance(conditional_on, str)
        or not isinstance(arbiter, str)
        # `bool` as itself, never `int`: `isinstance(True, int)` holds and the converse
        # does not, so an int check would let `0`/`1` through as a qualification.
        or not isinstance(unchecked, bool)
    ):
        raise ReviewLoopError(ADJUDICATION_SHAPE_ERROR)
    return Adjudication(route, issue, conditional_on, arbiter, unchecked)


def parse_loop(document: object) -> Loop:
    """Rebuild one loop from its stored document, refusing any state that could not govern.

    Validates everything the constructors validate — severities, route names, unique ids —
    plus the facts only storage adds: the round count is a non-negative integer, the round
    a finding was raised lies within the rounds the loop has recorded, and the
    adjudication shape round-trips. The arbiter
    precondition is deliberately **not** re-derived here: it governs the act of
    adjudicating, and a loop that carries a verdict written before this precondition
    existed must still be readable — the precondition refuses new acts, it does not
    repudiate recorded ones.
    """
    if not isinstance(document, dict) or document.get("version") != LOOP_VERSION:
        raise ReviewLoopError(LOOP_VERSION_ERROR)
    review_rounds = document.get("review_rounds")
    if not isinstance(review_rounds, int) or isinstance(review_rounds, bool) or review_rounds < 0:
        raise ReviewLoopError(LOOP_ROUNDS_ERROR)
    raw_findings = document.get("findings")
    if not isinstance(raw_findings, list):
        raise ReviewLoopError(LOOP_FINDINGS_ERROR)
    findings: list[Finding] = []
    for raw in raw_findings:
        if not isinstance(raw, dict):
            raise ReviewLoopError(LOOP_FINDINGS_ERROR)
        identifier = raw.get("id")
        severity = raw.get("severity")
        round_raised = raw.get("round_raised")
        if (
            not isinstance(identifier, str)
            or not identifier
            or not isinstance(severity, str)
            or not isinstance(round_raised, int)
            or isinstance(round_raised, bool)
        ):
            raise ReviewLoopError(FINDING_FIELDS_ERROR)
        if round_raised < 0 or round_raised > review_rounds:
            raise ReviewLoopError(ROUND_RANGE_ERROR)
        findings.append(
            Finding(
                identifier, severity, round_raised, _parse_adjudication(raw.get("adjudication"))
            )
        )
    _check_severities(tuple(findings))
    _check_ids((), tuple(findings))
    return Loop(review_rounds=review_rounds, findings=tuple(findings))


def loop_path(root: Path, issue: int) -> Path:
    """One issue's loop file under the review root."""
    return Path(root).expanduser() / str(issue) / LOOP_FILE


def _sync_directory(directory: Path) -> None:
    """Fsync a directory so a completed rename survives a power loss, never a crash alone.

    Separate from the write because the failure it covers is separate: `replace` makes the
    rename atomic to any reader, and this makes it durable to the machine losing power
    before the rename reaches the disk. A directory that cannot be opened `O_RDONLY` is
    left alone rather than raised on — the record is already in place by then, and a
    durability hint is not a reason to fail a write that succeeded.
    """
    try:
        handle = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(handle)
    except OSError:
        pass
    finally:
        os.close(handle)


def store_loop(root: Path, issue: int, loop: Loop) -> Path:
    """Write the loop's document atomically, creating the issue's directory on first store.

    Two properties the plain `write_text` this replaced did not have (#334 round 2, Medium
    4), and `review_exchange`'s verdict writer already had:

    - **Guarded.** An unwritable or removed review root leaves as this module's own named
      error rather than as a `PermissionError` traceback out of `mkdir` — a failure with no
      class is the `untyped_harness_failure` the table exists to prevent.
    - **Atomic.** The document is staged beside the target and renamed onto it, so an
      interrupt mid-write cannot leave a truncated `loop.json` that the landing then refuses
      `review_loop_unreadable` with a remedy no tool performs. A reader sees the old loop or
      the new one.
    - **Durable.** The staged file and the directory that holds it are both fsynced, which
      is the parity with `review_exchange._write_verdict_once` the paragraph above claimed
      and did not have (round 2 re-review, Low 6). `replace` covers the interrupt; it does
      not cover a power loss between the write and its writeback, which on a filesystem
      without ext4's `auto_da_alloc` leaves a zero-length `loop.json` — the same wedge the
      atomicity closes, arriving by the other door.

    Deliberately left: `mkstemp` creates at `0600` where the `write_text` this replaced took
    the umask default. Single-user directory, no consumer affected, and reading the umask to
    match it means setting it — a process-wide act this function has no business taking.
    """
    target = loop_path(root, issue)
    document = json.dumps(render_loop(issue, loop), indent=2, sort_keys=True) + "\n"
    try:
        _write_atomically(target, document)
    except OSError as unwritable:
        raise ReviewLoopError(
            LOOP_UNWRITTEN_ERROR.format(issue=issue, target=target, reason=unwritable)
        ) from unwritable
    return target


def _write_atomically(target: Path, document: str) -> None:
    """Stage a document beside its target and rename onto it, guarded, atomic and durable.

    The three properties `store_loop` documents above, in one place because the authorship
    record beside it owes the same three (#398) — a second copy of the staging dance is a
    second place for the `replace` to become a `write_text` under a later edit. `OSError`
    leaves as itself: each caller names its own record in its own refusal, which is the half
    that must not be shared.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, staged = tempfile.mkstemp(prefix=f"{target.name}.", suffix=".staged", dir=target.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as writing:
            writing.write(document)
            writing.flush()
            os.fsync(writing.fileno())
        Path(staged).replace(target)
        _sync_directory(target.parent)
    except OSError:
        Path(staged).unlink(missing_ok=True)
        raise


def load_loop(root: Path, issue: int) -> Loop:
    """Read the loop back, refusing a document that names another issue.

    `FileNotFoundError` is raised untouched — the CLI turns it into its own named refusal,
    because "no loop here yet" and "a loop that will not parse" are different answers. A
    document that exists but will not decode is the second of those as well (#333 round 2,
    Medium 6): a truncated or malformed `loop.json` reaches the caller as this module's own
    named refusal rather than a raw `JSONDecodeError` traceback the command surface never
    classified.
    """
    try:
        document = json.loads(loop_path(root, issue).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, ValueError) as broken:
        raise ReviewLoopError(
            LOOP_UNREADABLE_ERROR.format(issue=issue, root=root, reason=broken)
        ) from broken
    if not isinstance(document, dict):
        raise ReviewLoopError(LOOP_VERSION_ERROR)
    stored = document.get("issue")
    if not isinstance(stored, int) or isinstance(stored, bool) or stored <= 0:
        raise ReviewLoopError(LOOP_ISSUE_ERROR)
    if stored != issue:
        raise ReviewLoopError(ISSUE_MISMATCH_ERROR.format(stored=stored, asked=issue))
    return parse_loop(document)


def render_landing(  # noqa: PLR0913 — the terminus record carries what the landing owed and what it discharged, each part read by a different later seat
    issue: int,
    loop: Loop,
    end: Terminus,
    *,
    arbiter: str = "",
    unchecked: bool = False,
    filed_issues: Mapping[str, int] | None = None,
) -> dict[str, object]:
    """Render the landing record: what the pre-declared default discharged, by name.

    `filed_issues` maps each upheld finding's id to the issue its filing created, so the
    record answers "where did that Critical land" rather than "a filing happened".
    Dismissals record the finding, severity and round — the trace ADR-0071 rules every
    dismissal is owed, on the record the post-landing seat reads. `findings` carries every
    finding of the loop with its final verdict — fixed, filed, upheld, dismissed, or open
    (#333 round 2, High 3): `fixed` is the one route whose trace lives only in the diff
    under review, which post-landing review does not re-read, and a Low left open at the
    terminus is a fact that record must be able to say.
    """
    filed = filed_issues or {}
    return {
        "version": LOOP_VERSION,
        "issue": issue,
        "review_rounds": loop.review_rounds,
        "default_applies": end.default_applies,
        "arbiter": arbiter or None,
        "arbiter_unchecked": unchecked,
        "findings": [
            {
                "finding": f.id,
                "severity": f.severity,
                "round_raised": f.round_raised,
                "route": f.adjudication.route if f.adjudication else "open",
                **(
                    {"issue": f.adjudication.issue}
                    if f.adjudication and f.adjudication.issue
                    else {}
                ),
                **(
                    {"conditional_on": f.adjudication.conditional_on}
                    if f.adjudication and f.adjudication.conditional_on
                    else {}
                ),
            }
            for f in loop.findings
        ],
        "filings": [
            {
                "finding": f.finding,
                "severity": f.severity,
                "round_raised": f.round_raised,
                "issue": filed.get(f.finding),
            }
            for f in end.filings
        ],
        "dismissals": [
            {"finding": d.finding, "severity": d.severity, "round_raised": d.round_raised}
            for d in end.dismissals
        ],
    }


# --------------------------------------------------------------------------- the command surface
#
# The production caller (#333 round 1, High 5): `open`, `round`, `adjudicate`, `escalate`,
# `terminus`, `show`. Refusals are typed and named, exit 1; a GitHub or filesystem act
# that could not be performed is exit 3, "could not look", the handoff tool's split — a
# negative result and no result are different answers. `escalate` lazy-imports `arbiter`
# and `dispatch` because `arbiter` imports this module: the import is a handler-local
# fact, and making it module-level would be a cycle.

OK: Final = 0
REFUSED: Final = 1
NO_RESULT: Final = 3

GH_TIMEOUT: Final = 60

FINDING_SPEC_ERROR: Final = "a finding is id=severity, severity one of critical, high, medium, low"
SEAT_UNKNOWN_ERROR: Final = "the registry carries no seat named {seat}"
LOOP_EXISTS_ERROR: Final = (
    "a loop for #{issue} already exists under {root} — `round` advances it; `open` is once"
)
NO_LOOP_ERROR: Final = "no loop for #{issue} under {root} — `open` records the first review"
TERMINUS_NOT_REACHED_ERROR: Final = (
    "the pre-declared default does not apply: findings above Low remain unadjudicated —"
    " #334's landing refusal is the consumer that refuses on this same fact"
)
ALREADY_TERMINATED_ERROR: Final = (
    "a landing record for #{issue} already exists under {root} — the terminus is once, and"
    " re-running it would file every upheld finding twice"
)
TERMINUS_INCOMPLETE_ERROR: Final = (
    "a terminus for #{issue} began and did not finish — a pending record under {root} names"
    " what it was about to post. Check #{issue}'s thread for filings and dismissals already"
    " made and clear the pending record by hand once accounted: a blind retry files every"
    " upheld finding twice (#333 round 2, High 4)"
)
ARBITER_UNRESOLVED_ERROR: Final = (
    "the loop for #{issue} carries arbiter verdicts but no escalation record under {root}"
    " names a firing arbiter — run `escalate` at the wall before `terminus`. A landing whose"
    " verdicts no arbiter resolution chose is the round-2 Critical through its second door"
    " (#333 round 2, High 2)"
)
ESCALATION_FIELD_ABSENT_ERROR: Final = (
    "the escalation record for #{issue} carries no {field} — a record that never said"
    " {field} must not be read as its default. `unchecked` absent would default to False,"
    " which reads an unperformable check as a check that passed, the exact inversion of"
    " #41's mark (#333 arbiter's ruling)"
)
ESCALATION_FIELD_TYPE_ERROR: Final = (
    "the escalation record for #{issue} carries {field}={value}, which is not {expected} —"
    " a record that authorises the terminus is validated, never coerced: `str(None)` is"
    " 'None' and truthy, so every coerced value of `arbiter` authorised (#333 arbiter's"
    " ruling)"
)
NOT_A_REPOSITORY_ERROR: Final = (
    "`escalate` reads the routing policy over the branch under review, and this directory"
    " is not inside a git repository — run it from the repository, any checkout of it"
)
EXCHANGE_REF_ABSENT_ERROR: Final = (
    "the walk's routing rung reads the branch under review, and `origin` carries no"
    " {ref} — the review exchange (`just review exchange`) is what puts it there, and an"
    " escalation with no branch cannot check what the policy would refuse on it (#41: a"
    " check that could not run is not a check that passed)"
)
ROUTING_INPUTS_ERROR: Final = (
    "the walk's routing read could not be performed ({what}): a resolution that skipped it"
    " is the gap #391 closed — an escalation without the policy over the branch resolves"
    " past a head the policy would refuse. Fix the failure quoted in parentheses here and"
    " run `escalate` again"
)
ROUTING_POLICY_ERROR: Final = (
    "the routing policy on `origin/main` could not be read ({why}) — the walk reads the"
    " trusted copy there, never the diff under judgement's own, and a check that could"
    " not run is not a check that passed (#41)"
)

# The marker a filing opens with, so a reader can find every arbiter-upheld filing on an
# originating item the way `Handoff-for:` is found (#210's device, this domain's use).
FILING_MARKER: Final = "Upheld-filing-for:"
DISMISSAL_MARKER: Final = "Dismissal-for:"


class ExternalError(RuntimeError):
    """A GitHub or filesystem act the terminus could not perform — not a result."""


def _issue_number(raw: str) -> int:
    text = raw.strip().removeprefix("#")
    if not text.isdigit() or int(text) <= 0:
        message = f"not an issue number: {raw!r}"
        raise argparse.ArgumentTypeError(message)
    return int(text)


def _finding_spec(raw: str) -> tuple[str, str]:
    identifier, separator, severity = raw.partition("=")
    if not separator or not identifier or severity not in SEVERITY_RANK:
        raise argparse.ArgumentTypeError(FINDING_SPEC_ERROR)
    return identifier, severity


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """One door: the loop act to perform, the issue it belongs to."""
    parser = argparse.ArgumentParser(
        prog="review-loop", description="Drive one issue's never-alone review loop."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    opened = commands.add_parser("open", help="record an issue's first review (round zero)")
    _loop_arguments(opened, findings=True)
    opened.set_defaults(handler=_cmd_open)

    turned = commands.add_parser("round", help="record one fix-and-re-review cycle")
    _loop_arguments(turned, findings=True)
    turned.set_defaults(handler=_cmd_round)

    folded = commands.add_parser(
        "sync", help="fold the verdict recorded for a commit into the loop (#334)"
    )
    _loop_arguments(folded)
    folded.add_argument(
        "--reviewed-sha", required=True, help="the reviewed commit, full 40-character SHA"
    )
    folded.add_argument(
        "--dispatch-dir", default="", help="the dispatch records; default is this box's own"
    )
    folded.set_defaults(handler=_cmd_sync)

    judged = commands.add_parser("adjudicate", help="close one finding with its one adjudication")
    _loop_arguments(judged)
    judged.add_argument("--finding", required=True, help="the finding id to close")
    judged.add_argument("--route", required=True, choices=sorted(ROUTES))
    judged.add_argument("--filed-issue", default="", help="issue it became (accepted_and_filed)")
    judged.add_argument(
        "--conditional-on",
        default="",
        help="the named work outside the diff the harm is conditional on (accepted_and_filed)",
    )
    judged.set_defaults(handler=_cmd_adjudicate)

    escalated = commands.add_parser("escalate", help="resolve the arbiter and evaluate the wall")
    _loop_arguments(escalated)
    escalated.add_argument("--seat", default="implementer", help="the seat whose arbiter resolves")
    escalated.add_argument(
        "--dispatch-dir", default="", help="the dispatch records; default is this box's own"
    )
    escalated.add_argument("--admission-dir", default="")
    escalated.add_argument("--breaker-dir", default="")
    escalated.add_argument("--credentials", default="")
    escalated.add_argument(
        "--conditions",
        default=str(Path(__file__).resolve().parent.parent / escalation.CONDITIONS_RELATIVE),
        help="the escalation condition table to evaluate",
    )
    escalated.set_defaults(handler=_cmd_escalate)

    ended = commands.add_parser("terminus", help="discharge the pre-declared default's debts")
    _loop_arguments(ended)
    ended.add_argument(
        "--dry-run",
        action="store_true",
        help="print what the terminus owes; post and write nothing",
    )
    ended.set_defaults(handler=_cmd_terminus)

    authored = commands.add_parser(
        "author", help="declare that an interactive session authored this issue's change"
    )
    authored.add_argument("--issue", required=True, type=_issue_number)
    authored.add_argument("--root", default=str(REVIEW_ROOT), help="the review state directory")
    authored.add_argument("--profile", required=True, help="the profile that authored the change")
    authored.add_argument(
        "--sha", default="", help="the commit in hand when the declaration was recorded"
    )
    authored.add_argument(
        "--repo",
        default=str(Path.cwd()),
        help="a git repository whose refs contain the declared commit (default: this directory)",
    )
    authored.set_defaults(handler=_cmd_author)

    shown = commands.add_parser("show", help="print an issue's stored loop state")
    shown.add_argument("--issue", required=True, type=_issue_number)
    shown.add_argument("--root", default=str(REVIEW_ROOT))
    shown.set_defaults(handler=_cmd_show)

    return parser.parse_args(argv)


def _loop_arguments(command: argparse.ArgumentParser, *, findings: bool = False) -> None:
    command.add_argument("--issue", required=True, type=_issue_number)
    command.add_argument("--root", default=str(REVIEW_ROOT), help="the review state directory")
    command.add_argument("--journal", default=str(JOURNAL), help="the telemetry journal")
    if findings:
        command.add_argument(
            "--finding",
            action="append",
            default=[],
            type=_finding_spec,
            metavar="ID=SEVERITY",
            help="one raised finding; repeatable",
        )


def _cmd_open(
    args: argparse.Namespace, clock: Callable[[], float], _create: object, _post: object
) -> int:
    root = Path(args.root)
    if loop_path(root, args.issue).exists():
        raise ReviewLoopError(LOOP_EXISTS_ERROR.format(issue=args.issue, root=root))
    loop = first_review(tuple(Finding(i, s, 0) for i, s in args.finding))
    store_loop(root, args.issue, loop)
    emit_round(loop, str(args.issue), clock(), Path(args.journal))
    print(f"[review-loop] #{args.issue} round 0 opened with {len(loop.findings)} finding(s)")  # noqa: T201 — a CLI's output channel
    return OK


def _cmd_round(
    args: argparse.Namespace, clock: Callable[[], float], _create: object, _post: object
) -> int:
    root = Path(args.root)
    loop = _read_loop(root, args.issue)
    raised = tuple(Finding(i, s, loop.review_rounds + 1) for i, s in args.finding)
    loop = next_round(loop, raised)
    store_loop(root, args.issue, loop)
    emit_round(loop, str(args.issue), clock(), Path(args.journal))
    print(  # noqa: T201 — a CLI's output channel
        f"[review-loop] #{args.issue} round {loop.review_rounds} recorded with"
        f" {len(raised)} new finding(s), {len(open_above_low(loop))} above Low open"
    )
    return OK


def _cmd_sync(
    args: argparse.Namespace, clock: Callable[[], float], _create: object, _post: object
) -> int:
    """Fold the verdict recorded for one commit into the issue's loop.

    The findings and their severities come from the verdict record, never from a flag — the
    distinction from `open`/`round`, whose `--finding id=severity` puts the grading of a
    review in the hands of a caller the review judges. The verdict is the one the landing
    will read: same derivation, same binding, same identity re-derived rather than believed.

    Three answers, and the third is #334 round 2's Medium 3. A loop that does not exist is
    opened at round zero; ids the loop does not hold are the next round; and a verdict that
    re-grades a finding the loop already holds is **refused** rather than reported as
    `loop_unchanged`. That case used to print a success over the exact drift the landing
    would then refuse `review_finding_mismatch` on, naming a remedy — re-derive the loop —
    that no command performed: the fold had already declined it, `next_round` refuses a
    duplicate id by rule, and the landing was wedged short of hand-editing the record the
    refusal tells you not to hand-edit. The tool that reads both records first is the one
    that should say so.
    """
    # Handler-local for the reason `_cmd_escalate`'s are: `review_exchange` reaches
    # `dispatch`, and the landing rung that reads this loop imports both.
    import review_exchange  # noqa: PLC0415 — see the comment above

    root = Path(args.root)
    dispatch_root = Path(args.dispatch_dir) if args.dispatch_dir else review_exchange.DISPATCH_ROOT
    bound = review_exchange.bound_verdict(args.issue, args.reviewed_sha, dispatch_root)
    if not isinstance(bound, review_exchange.BoundVerdict):
        for line in bound.lines():
            print(f"[review-loop] {line}")  # noqa: T201 — a CLI's refusal channel
        return REFUSED
    reported = tuple(bound.verdict.findings)
    try:
        loop = load_loop(root, args.issue)
    except FileNotFoundError:
        loop = first_review(tuple(Finding(f.id, f.severity, 0) for f in reported))
        store_loop(root, args.issue, loop)
        emit_round(loop, str(args.issue), clock(), Path(args.journal))
        print(  # noqa: T201 — a CLI's output channel
            f"[review-loop] #{args.issue} round 0 opened from the verdict for"
            f" {args.reviewed_sha} with {len(loop.findings)} finding(s)"
        )
        return OK
    held = {finding.id: finding for finding in loop.findings}
    regraded = tuple(f for f in reported if f.id in held and held[f.id].severity != f.severity)
    if regraded:
        raise ReviewLoopError(
            REGRADE_ERROR.format(
                issue=args.issue,
                findings=", ".join(
                    f"{f.id} loop={held[f.id].severity} verdict={f.severity}" for f in regraded
                ),
            )
        )
    fresh = tuple(f for f in reported if f.id not in held)
    if not fresh:
        print(  # noqa: T201 — a CLI's output channel
            f"[review-loop] #{args.issue} loop unchanged — the verdict for"
            f" {args.reviewed_sha} raises nothing this loop does not hold"
        )
        return OK
    loop = next_round(loop, tuple(Finding(f.id, f.severity, loop.review_rounds + 1) for f in fresh))
    store_loop(root, args.issue, loop)
    emit_round(loop, str(args.issue), clock(), Path(args.journal))
    print(  # noqa: T201 — a CLI's output channel
        f"[review-loop] #{args.issue} round {loop.review_rounds} recorded from the verdict"
        f" for {args.reviewed_sha} with {len(fresh)} new finding(s),"
        f" {len(open_above_low(loop))} above Low open"
    )
    return OK


def _cmd_adjudicate(
    args: argparse.Namespace, clock: Callable[[], float], _create: object, _post: object
) -> int:
    root = Path(args.root)
    loop = _read_loop(root, args.issue)
    # The arbiter is read off the escalation record, never taken from a flag: the name on an
    # arbiter route is the profile `escalate` resolved, and a route standing in for a ruling
    # with no record behind it is refused by `_route_checks` rather than written unnamed
    # (#334 round 2, Medium 2).
    arbiter = ""
    unchecked = False
    if args.route in (ARBITER_UPHELD, ARBITER_DISMISSED):
        authorisation = recorded_arbiter(root, args.issue)
        arbiter = authorisation.arbiter if authorisation.authorises else ""
        # Carried onto the adjudication rather than dropped (round 2 re-review, Low 7):
        # the resolution that named this arbiter may have been made with a dispatch
        # record it could not open, and a loop that records only the name states a
        # stronger fact than the resolution did.
        unchecked = authorisation.unchecked if arbiter else False
    adjudication = Adjudication(
        args.route, args.filed_issue, args.conditional_on, arbiter, unchecked
    )
    updated = adjudicate(loop, args.finding, adjudication)
    store_loop(root, args.issue, updated)
    closed = next(f for f in updated.findings if f.id == args.finding)
    emit_dispute(closed, adjudication, str(args.issue), clock(), Path(args.journal))
    print(  # noqa: T201 — a CLI's output channel
        f"[review-loop] #{args.issue} finding {args.finding} closed as {args.route}"
        f"{f' by arbiter {arbiter}' if arbiter else ''}"
        f"{' (resolution unchecked)' if unchecked else ''}"
    )
    return OK


# The deadline on every read of `origin` the routing rung makes (#425). Three of them
# are network calls — the ls-remote below and the two fetches — and the lane's provider
# had returned a 529 twice and exhausted a five-hour quota twice on the day this landed,
# so an unbounded read here is a `just review-loop escalate` hanging on a bad afternoon.
# 60 s is an order above what a working link needs for this repository's refs and objects
# and well inside the afternoon it exists to cut short; the bound is the subprocess's own
# kill, so a stall anywhere inside git — name resolution included — expires the same way
# (`worktree.git`'s timeout, whose reasoning sits there).
ROUTING_READ_TIMEOUT_S: Final = 60


def _routing_remote_git(*args: str, cwd: Path) -> str:
    """Run one routing Git call that may dial, with its deadline owned here."""
    return git(*args, cwd=cwd, timeout=ROUTING_READ_TIMEOUT_S)


def _arbiter_routing_inputs(issue: int) -> tuple[routing_policy.Policy, tuple[str, ...]]:
    """Read the policy and the branch paths the arbiter walk's routing rung judges by.

    The rung's inputs, derived rather than trusted since #391: the policy off fetched
    `origin/main` — the same trust rule `tools/land.py`'s `_routing_inputs` states, that a
    diff under judgement must not weaken the policy that judges it — and the branch under
    review off the review exchange's own ref (`review_exchange.review_ref`'s naming, the
    one spelling of it), merge-base-relative the same three-dot way, so the paths are the
    branch's own wherever the command runs from. A rung that could not read either refuses
    the escalation rather than resolving past it (#41).

    Two failure classes, split the handoff tool's way: git that could not be reached is
    `ExternalError` — could not look, not a result — while a ref that is not there and a
    policy that will not parse are facts, and refuse by name. Every read of the remote
    carries `ROUTING_READ_TIMEOUT_S`; the local reads (`rev-parse`, `show`, `diff`) do
    not, having no network to stall on.
    """
    # Handler-local for the same reason `_cmd_escalate`'s `arbiter` import is: the
    # exchange module imports this one, so a module-level import here is a cycle.
    from review_exchange import review_ref  # noqa: PLC0415 — the cycle is real; see above

    try:
        root = Path(git("rev-parse", "--show-toplevel", cwd=Path.cwd()).strip()).resolve()
    except GitError as failure:
        raise ReviewLoopError(NOT_A_REPOSITORY_ERROR) from failure
    ref = review_ref(issue)
    try:
        sha = remote_ref_sha(root, ref, timeout=ROUTING_READ_TIMEOUT_S)
    except GitError as failure:
        raise ExternalError(
            ROUTING_INPUTS_ERROR.format(what=f"ls-remote: {failure.stderr}")
        ) from failure
    if sha is None:
        raise ReviewLoopError(EXCHANGE_REF_ABSENT_ERROR.format(ref=ref))
    try:
        _routing_remote_git("fetch", "origin", "main", cwd=root)
        text = git("show", f"origin/main:{routing_policy.POLICY_RELATIVE.as_posix()}", cwd=root)
        _routing_remote_git("fetch", "origin", ref, cwd=root)
        listed = git("diff", "--name-only", f"origin/main...{sha}", cwd=root)
    except GitError as failure:
        raise ExternalError(ROUTING_INPUTS_ERROR.format(what=f"git: {failure.stderr}")) from failure
    try:
        policy = routing_policy.parse_policy(text)
    except (ValueError, KeyError, TypeError) as failure:
        raise ReviewLoopError(ROUTING_POLICY_ERROR.format(why=failure)) from failure
    paths = tuple(line.strip() for line in listed.splitlines() if line.strip())
    return policy, paths


def _cmd_escalate(
    args: argparse.Namespace, clock: Callable[[], float], _create: object, _post: object
) -> int:
    # Handler-local, and necessarily so: `arbiter` imports this module, so a module-level
    # import here is a cycle.
    import arbiter  # noqa: PLC0415 — the cycle is real; see the comment above
    import dispatch  # noqa: PLC0415 — same cycle, same reason

    root = Path(args.root)
    loop = _read_loop(root, args.issue)
    seat = dispatch.SEATS.get(args.seat)
    if seat is None:
        raise ReviewLoopError(SEAT_UNKNOWN_ERROR.format(seat=args.seat))
    dispatch_dir = Path(args.dispatch_dir) if args.dispatch_dir else dispatch.DISPATCH_ROOT
    # The landing rung is not the only reader that takes an absent record for an answer
    # (#398 round 2). The walk below excludes the profiles the records place on the work, a
    # declared author among them — so a declaration whose record has gone leaves the author
    # of an interactively written change eligible to arbitrate it, which is the same silent
    # narrowing the landing refuses, one door over.
    if declaration_lost(root, args.issue):
        raise ExternalError(
            AUTHORSHIP_LOST_ERROR.format(issue=args.issue, target=authorship_path(root, args.issue))
        )
    # The routing rung's inputs are derived, never flagged (#391): a `--routing-refusal`
    # a caller might not pass was a check that did not run reading as one that passed,
    # and no caller ever passed it — its only feeder was the flag itself.
    policy, paths = _arbiter_routing_inputs(args.issue)
    resolution = arbiter.resolve_dispatchable(
        seat,
        # An interactively declared author is an author the arbiter must not be either
        # (#398). The walk's third rung excludes the profiles the records place on the work,
        # and on a `.claude/` change the records place nobody — so without this the arbiter
        # of an interactively authored issue could resolve to the profile that wrote it.
        dispatch.with_declared_authors(
            dispatch.potential_authors_and_reviewers(args.issue, dispatch_dir),
            recorded_authors(root, args.issue),
            str(authorship_path(root, args.issue)),
        ),
        # The one clock the CLI owns, so a test fixes the wall it escalates against: an
        # off-peak rung is a function of the hour, and a test that cannot pin the hour
        # cannot state which profiles the walk may resolve to.
        datetime.fromtimestamp(clock()).astimezone(),
        policy,
        paths,
        admission_dir=args.admission_dir or None,
        breaker_dir=args.breaker_dir or None,
        credentials=args.credentials or None,
    )
    arbiter.emit_resolution(resolution, seat, str(args.issue), clock(), Path(args.journal))
    if resolution.kind == arbiter.REFUSED:
        print(f"[review-loop] arbiter_refused={resolution.refusal}: {resolution.detail}")  # noqa: T201 — a CLI's refusal channel
        for exclusion in resolution.passed_over:
            print(f"[review-loop]   passed over {exclusion.profile}: {exclusion.reason}")  # noqa: T201 — a CLI's refusal channel
        return REFUSED
    read = escalation.read_conditions(Path(args.conditions))
    evaluation = evaluate_escalation(read, loop, arbiter=resolution.arbiter)
    emit_escalation(evaluation, str(args.issue), clock(), resolution.arbiter, Path(args.journal))
    conditions = []
    if evaluation.kind == escalation.FIRING:
        conditions = [e.condition.id for e in evaluation.emissions]
    record = {
        "version": LOOP_VERSION,
        "issue": args.issue,
        "evaluation": evaluation.kind,
        "conditions": conditions,
        "arbiter": resolution.arbiter,
        "unchecked": resolution.unchecked,
        "passed_over": [
            {"profile": e.profile, "reason": e.reason, "detail": e.detail}
            for e in resolution.passed_over
        ],
    }
    target = root / str(args.issue) / ESCALATION_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(  # noqa: T201 — a CLI's output channel
        f"[review-loop] #{args.issue} escalation={evaluation.kind} arbiter={resolution.arbiter}"
        f" unchecked={resolution.unchecked}"
    )
    return OK


def _cmd_terminus(  # the whole ending in one act: gate, filings, dismissals, record, event
    args: argparse.Namespace,
    clock: Callable[[], float],
    create: Callable[[str, str], int],
    post: Callable[[int, str], object],
) -> int:
    root = Path(args.root)
    loop = _read_loop(root, args.issue)
    end = terminus(loop)
    if not end.default_applies:
        raise ReviewLoopError(TERMINUS_NOT_REACHED_ERROR)
    # Verdicts nobody's resolution chose are not dischargeable (#333 round 2, High 2): the
    # arbiter routes' own gate is the wall, and `escalate` is the act that records who the
    # wall transferred to. A loop carrying arbiter verdicts with no firing record beside
    # them is exactly the landing `terminus()` must refuse to bless with `arbiter: null`.
    authorisation = recorded_arbiter(root, args.issue)
    if (end.filings or end.dismissals) and not authorisation.authorises:
        raise ReviewLoopError(ARBITER_UNRESOLVED_ERROR.format(issue=args.issue, root=root))
    landing = root / str(args.issue) / LANDING_FILE
    if landing.exists():
        raise ReviewLoopError(ALREADY_TERMINATED_ERROR.format(issue=args.issue, root=root))
    if args.dry_run:
        for filing in end.filings:
            print(f"[review-loop] would file {filing.finding} ({filing.severity}) on #{args.issue}")  # noqa: T201 — a CLI's output channel
        for dismissal in end.dismissals:
            print(  # noqa: T201 — a CLI's output channel
                f"[review-loop] would record dismissal {dismissal.finding}"
                f" ({dismissal.severity}) on #{args.issue}"
            )
        print("[review-loop] dry run — nothing posted, nothing written")  # noqa: T201 — a CLI's output channel
        return OK
    pending = root / str(args.issue) / PENDING_FILE
    plan = json.dumps(
        {
            "issue": args.issue,
            "filings": [f.finding for f in end.filings],
            "dismissals": [d.finding for d in end.dismissals],
        }
    )
    if not _claim_terminus_pending(pending, plan):
        raise ReviewLoopError(TERMINUS_INCOMPLETE_ERROR.format(issue=args.issue, root=root))
    filed: dict[str, int] = {}
    for filing in end.filings:
        number = create(*_filing(args.issue, filing))
        filed[filing.finding] = number
    for dismissal in end.dismissals:
        post(args.issue, _dismissal(args.issue, dismissal))
    landing.parent.mkdir(parents=True, exist_ok=True)
    # The record is written into the claimed marker itself and moved into place by one
    # atomic rename (#333 round 3): the marker and the record are one file at two points in
    # its life, not two facts that can disagree. A crash before the rename leaves the marker
    # — the refusing answer; the rename itself is the terminal state, so `landing.json` is
    # never partial and never coexists with the marker.
    with pending.open("w", encoding="utf-8") as record:
        record.write(
            json.dumps(
                render_landing(
                    args.issue,
                    loop,
                    end,
                    arbiter=authorisation.arbiter,
                    unchecked=authorisation.unchecked,
                    filed_issues=filed,
                ),
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
    pending.replace(landing)
    emit_terminus(end, str(args.issue), clock(), Path(args.journal))
    print(  # noqa: T201 — a CLI's output channel
        f"[review-loop] #{args.issue} terminus: {len(end.filings)} filed,"
        f" {len(end.dismissals)} dismissal(s) recorded, landing record written"
    )
    return OK


def _cmd_author(
    args: argparse.Namespace, clock: Callable[[], float], _create: object, _post: object
) -> int:
    """Record the one declaration an interactive session can honestly make (#398).

    Two refusals, and each is a fact this command can actually check. A session carrying
    `CTI_DISPATCH_ID` is dispatched, so its profile is already on a record and the work it
    is declaring is work #294 says it must not have done. A profile outside the registry is
    a typo, and a typo here is worse than a refusal: it names an author no reviewer could
    ever be, so the never-alone check would run against a set that excludes nobody.

    What it cannot check is whether the declared profile is the declaring session's own —
    nothing in an interactive session's environment says which model is reading this — so
    the record says `declared` and the landing prints it that way.

    Omitting the optional `--sha` also omits commit validation; the stored record says that
    no commit was named rather than claiming a validation occurred.

    **Nor is the dispatch refusal a barrier.** It reads one environment variable, and a
    dispatched session that runs this command under `env -u CTI_DISPATCH_ID` writes the
    record; that was constructed and confirmed on #398's first review round. It is written
    down here so a later reader does not mistake the guard for something stronger than it
    is, and it is deliberately not chased: detecting a session that edits its own
    environment is an arms race, and winning a round of it would imply a guarantee this
    cannot give. The limit is the one ADR-0071 ruling 4 already states for the landing rung
    — this protects against the accident and the shortcut, not against a deceptive agent; a
    convention with a mechanical floor, not a guarantee.
    """
    import dispatch  # noqa: PLC0415 — the same cycle `_cmd_escalate` documents, same reason

    dispatched = os.environ.get("CTI_DISPATCH_ID", "").strip()
    if dispatched:
        raise ReviewLoopError(AUTHORSHIP_DISPATCHED_ERROR.format(dispatch_id=dispatched))
    if args.profile not in dispatch.PROFILES:
        raise ReviewLoopError(
            AUTHORSHIP_PROFILE_ERROR.format(
                profile=args.profile, known=" ".join(sorted(dispatch.PROFILES))
            )
        )
    if args.sha:
        try:
            commit = worktree.validate_commit(Path(args.repo), args.sha)
        except GitError as failure:
            raise ExternalError(str(failure)) from failure
        if commit is not None:
            raise ReviewLoopError("\n".join(commit.lines()))
    added = store_authorship(
        Path(args.root),
        args.issue,
        args.profile,
        args.sha,
        datetime.fromtimestamp(clock()).astimezone().isoformat(),
    )
    print(  # noqa: T201 — a CLI's output channel
        f"[review-loop] #{args.issue} authorship {'recorded' if added else 'already recorded'}"
        f" profile={args.profile} source={DECLARED}"
        f" record={authorship_path(Path(args.root), args.issue)}"
    )
    return OK


def _cmd_show(
    args: argparse.Namespace, _clock: Callable[[], float], _create: object, _post: object
) -> int:
    root = Path(args.root)
    loop = _read_loop(root, args.issue)
    print(json.dumps(render_loop(args.issue, loop), indent=2, sort_keys=True))  # noqa: T201 — this command's output IS the loop
    return OK


def _read_loop(root: Path, issue: int) -> Loop:
    try:
        return load_loop(root, issue)
    except FileNotFoundError:
        raise ReviewLoopError(NO_LOOP_ERROR.format(issue=issue, root=root)) from None


class ArbiterAuthorisation(NamedTuple):
    """What the escalation record says about the arbiter routes it authorises.

    Three fields and one decision over them, so the decision is made once rather than
    by each consumer: the terminus, `adjudicate`, and #334's landing rung all ask "may
    an arbiter route stand here", and the landing rung asking it a different way is how
    a loop closed by an arbiter nobody's escalation chose reached `just land` while the
    terminus over the same loop refused it (#334 round 2 re-review, Medium 1).

    `unchecked` travels with the pair because the resolution it came from could be
    partial — `Resolution.unchecked`, the reason ruling 4's route is `reviewing_checked`
    and never `reviewing_verified` — and a consumer that drops it records a stronger
    claim than the resolution made (round 2 re-review, Low 7).
    """

    arbiter: str
    unchecked: bool
    evaluation: str

    @property
    def authorises(self) -> bool:
        """Whether an arbiter route is admissible on this record: a name **and** a firing.

        The two only authorise together — a record that resolved a profile but fired
        nothing transferred to it (#333 round 2, High 2). An unknown evaluation string
        fails this comparison and so fails closed.
        """
        return bool(self.arbiter) and self.evaluation == escalation.FIRING


def recorded_arbiter(root: Path, issue: int) -> ArbiterAuthorisation:
    """Read the arbiter `escalate` recorded, if it ran; absent is an answer, not a gap.

    A record that exists but will not read is not the same as no record — defaulting there
    would write a landing record that quietly forgets who arbitrated — so it is an
    unperformable read, exit 3, rather than a silent empty arbiter. The evaluation travels
    with the arbiter because the two only authorise together: a record that resolved a
    profile but fired nothing transferred to it (#333 round 2, High 2).

    The three fields are **validated, never coerced** (#333, the arbiter's ruling). The
    old read was `str(...)`/`bool(...)` over `.get` defaults, and every malformed value of
    the deciding field opened the gate: `str(None)` is `"None"`, which is truthy, so a
    record naming no arbiter at all authorised the terminus and the landing record then
    carried `"arbiter": "None"`. `unchecked` failed open in the #41 direction — `bool(None)`
    and an absent key both read as *checked*, inverting the one property
    `Resolution.unchecked` exists to carry. Keys must be **present**: `arbiter` missing
    fails closed, `unchecked` missing does not, and the fix cannot depend on which.
    `bool` is checked as itself, so `0`/`1` are refused — `isinstance(True, int)` is true
    and the converse is not, so an `int` check would let them through.

    Deliberately not validated: `arbiter` against `dispatch.PROFILES` (a profile retired
    between `escalate` and `terminus` would block a legitimate landing on a fact that is
    not about this record's integrity), and `evaluation` against the known kinds (an
    unknown string already fails the `== FIRING` comparison and fails closed).

    The finding this closes was graded Medium on **reachability**, not on the check: today
    only `_cmd_escalate` writes this file, and it writes a `str` and a `bool`. It becomes
    High the moment a second writer of `escalation.json` exists, or `escalate` learns to
    write `null` into `arbiter` for consistency with `render_landing`'s `arbiter or None`
    — either an ordinary change nobody would file a finding against.
    """
    try:
        record = json.loads((root / str(issue) / ESCALATION_FILE).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ArbiterAuthorisation(arbiter="", unchecked=False, evaluation="")
    except (OSError, ValueError) as broken:
        message = f"the escalation record for #{issue} exists but will not read: {broken}"
        raise ExternalError(message) from broken
    # Decodable JSON that is not an object is the same answer as undecodable JSON (#333
    # round 3): `.get` on a list would escape `main` as a bare `AttributeError` traceback,
    # the one failure in this module with no name. The record cannot yield an arbiter, so
    # it is an unperformable read like its siblings above, never a silent empty one.
    if not isinstance(record, dict):
        message = f"the escalation record for #{issue} exists but is not an object: {record!r}"
        raise ExternalError(message)
    for field, expected, described in (
        ("arbiter", str, "a string"),
        ("unchecked", bool, "a boolean"),
        ("evaluation", str, "a string"),
    ):
        if field not in record:
            raise ExternalError(ESCALATION_FIELD_ABSENT_ERROR.format(issue=issue, field=field))
        if not isinstance(record[field], expected):
            message = ESCALATION_FIELD_TYPE_ERROR.format(
                issue=issue, field=field, value=repr(record[field]), expected=described
            )
            raise ExternalError(message)
    return ArbiterAuthorisation(record["arbiter"], record["unchecked"], record["evaluation"])


# ------------------------------------------------------ the interactive authorship record (#398)
#
# The deadlock this closes: #294 bars a dispatched session from writing under `.claude/`, so
# such a change is authored interactively by construction — and an interactive session leaves
# no dispatch record, so `just land`'s never-alone rung read an empty author set and refused
# (`authorship_unrecorded`). Both halves were right, and together they left no route: #330 sat
# reviewed, adjudicated and green at `c380689` with nowhere to go.
#
# **What this record is.** One declaration per profile, in this issue's own review directory,
# saying that an interactive session on that profile authored this issue's change. It feeds
# the one set the rung checks the reviewer against, and it can only ever *add* a profile the
# reviewer may not be — the check is not loosened, it is given something to run against.
#
# **What it deliberately is not.** It is not a dispatch record and is not written among them:
# a record claiming a dispatch that never happened would be a worse answer than the deadlock,
# and every reader of the dispatch root (`ledger`, `dispatch_stop`, `review_exchange`) would
# meet a run that never ran. Its own file, its own vocabulary, its own root.
#
# **What it asserts.** Strictly less than a dispatch record: the profile is *declared* by the
# session writing it, never resolved by a dispatcher into a child's environment, so `declared`
# travels with it onto the landing's clearance. That is ADR-0071 ruling 4's same-user limit
# arriving by one more door — this protects against the accident and the shortcut, never
# against a session that lies about which profile it is. The one thing it can check, it does:
# a session with `CTI_DISPATCH_ID` in its environment is dispatched, and is refused.

AUTHORSHIP_FILE: Final = "authorship.json"
AUTHORSHIP_LOCK: Final = "authorship.lock"
AUTHORSHIP_VERSION: Final = 1
# The provenance every entry carries, and the word the landing's clearance prints: this
# profile is the recording session's own declaration, not a value read off a dispatch.
DECLARED: Final = "declared"

AUTHORSHIP_UNREADABLE_ERROR: Final = (
    "the authorship record for #{issue} exists but will not read: {reason}. A record that"
    " cannot be read cannot name an author, so nothing is taken from it — repair or"
    " re-record it (#41: a check that could not run is not a check that passed)"
)
AUTHORSHIP_SHAPE_ERROR: Final = (
    "the authorship record for #{issue} is not one this tool wrote: {detail}. It must be a"
    " version {version} object naming this issue and a non-empty authors list whose every"
    " entry names a non-empty profile"
)
AUTHORSHIP_DISPATCHED_ERROR: Final = (
    "this session is dispatched as {dispatch_id}, and a dispatched session's profile is"
    " already on its own dispatch record. The interactive record exists for the work no"
    " dispatch could have done — a `.claude/` change, which #294 bars a dispatched session"
    " from writing — so writing one from inside a dispatch would declare an author the"
    " records cannot corroborate. Nothing was written"
)
AUTHORSHIP_PROFILE_ERROR: Final = (
    "{profile} is not a registered profile. The declared author is checked against the"
    " registry rather than taken as a string, because a typo names a profile no reviewer"
    " could ever be and so clears the never-alone check this record exists to feed. Known:"
    " {known}. Nothing was written"
)
AUTHORSHIP_UNWRITTEN_ERROR: Final = (
    "the authorship record for #{issue} could not be written to {target} — {reason}. Nothing"
    " was changed: the document is staged beside its target and renamed onto it, so a failed"
    " write leaves the record as it stood"
)
AUTHORSHIP_LOST_ERROR: Final = (
    "a declaration was written for #{issue} and its record is gone from {target}, so the"
    " authors it named cannot be read back. An absent record is an answer — most issues are"
    " authored through a dispatch and have none — but not beside the lock a declaration"
    " leaves, and the profile the lost record named is one this walk would otherwise resolve"
    " to. Re-declare with `just review-loop author --issue <n> --profile <profile>`"
)


def authorship_path(root: Path, issue: int) -> Path:
    """One issue's interactive authorship record, beside its loop."""
    return Path(root).expanduser() / str(issue) / AUTHORSHIP_FILE


@contextmanager
def _authorship_lock(root: Path, issue: int) -> Iterator[None]:
    """Hold one issue's declaration lock across a whole read-append-write.

    `_write_atomically` makes the *write* atomic and that is not the property this needs:
    two declarations racing each read the record, each append their own author to what
    they read, and the second `replace` wins with the first author gone. A lost entry is a
    profile the never-alone check no longer excludes — a smaller exclusion set clears a
    reviewer it should refuse, which is the one direction this record must not fail in
    (#41's rule, on the rung #334 needed an arbitration to get right).

    `flock` rather than `_claim_terminus_pending`'s `O_EXCL` because these callers must
    queue and proceed rather than refuse, and because the kernel frees it on holder death
    (ADR-0022): a session killed mid-declaration leaves no lock for the next one to clear.
    """
    lock = authorship_path(root, issue).with_name(AUTHORSHIP_LOCK)
    lock.parent.mkdir(parents=True, exist_ok=True)
    handle = os.open(lock, os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield
    finally:
        os.close(handle)


def _authorship_fault(record: object, issue: int) -> str:
    """Say how a stored authorship record is malformed, or nothing where it is not.

    Validated rather than coerced, `recorded_arbiter`'s reason: this record decides whether
    a landing has an author set at all, and `str(record.get("profile"))` over a missing key
    would put the string `None` into that set — a profile no reviewer can be, clearing the
    check by supplying an author who does not exist.
    """
    if not isinstance(record, dict):
        return f"the record is not an object: {record!r}"
    if record.get("version") != AUTHORSHIP_VERSION:
        return f"version={record.get('version')!r}"
    stored = record.get("issue")
    if not isinstance(stored, int) or isinstance(stored, bool) or stored != issue:
        return f"the record names issue {stored!r}"
    authors = record.get("authors")
    if not isinstance(authors, list) or not authors:
        return f"authors={authors!r}"
    return _authors_fault(authors)


def _authors_fault(authors: list[object]) -> str:
    """Say how one of a record's author entries is malformed, or nothing where none is."""
    for entry in authors:
        if not isinstance(entry, dict):
            return f"an entry is not an object: {entry!r}"
        profile = entry.get("profile")
        if not isinstance(profile, str) or not profile.strip():
            return f"an entry names profile={profile!r}"
    return ""


def _authorship_entries(root: Path, issue: int) -> tuple[dict[str, object], ...]:
    """Read this issue's declared authorship entries, validated; absent is `()`.

    Absent is an answer — most issues are authored through a dispatch and have no such
    record — and unreadable is not: a record that exists and will not parse leaves as an
    unperformable read, exit 3 at the CLI and a named refusal at the landing, because the
    entry that would not open could be the reviewer's own.
    """
    try:
        record = json.loads(authorship_path(root, issue).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ()
    except (OSError, ValueError) as broken:
        message = AUTHORSHIP_UNREADABLE_ERROR.format(issue=issue, reason=broken)
        raise ExternalError(message) from broken
    fault = _authorship_fault(record, issue)
    if fault:
        raise ExternalError(
            AUTHORSHIP_SHAPE_ERROR.format(issue=issue, detail=fault, version=AUTHORSHIP_VERSION)
        )
    return tuple(record["authors"])


def recorded_authors(root: Path, issue: int) -> tuple[str, ...]:
    """Return the profiles an interactive session declared as this issue's authors, in order."""
    seen: list[str] = []
    for entry in _authorship_entries(root, issue):
        profile = str(entry["profile"]).strip()
        if profile not in seen:
            seen.append(profile)
    return tuple(seen)


def declaration_lost(root: Path, issue: int) -> bool:
    """Whether a declaration was written for this issue and its record is no longer there.

    **Absence is an answer, and a *lost* record is not the same absence.** `recorded_authors`
    reads a missing file as `()` because most issues are authored through a dispatch and have
    no declaration at all. That reading is right there and wrong here: where a record was
    written and has since gone, the profiles it named are silently out of the set whose whole
    job is to exclude reviewers — a check that did not run reading as one that passed (#41),
    which is the direction this record must never fail in. Round 1 closed that hole for a
    *corrupted* record and left it open for a removed one; the landing's own
    `authorship_unreadable` remedy invites the removal in as many words ("remove it and
    re-declare"), so the accident is one the tool itself opens the door to.

    **The lock beside the record is the evidence, because the writer is the only thing that
    creates it.** `_authorship_lock` runs on the declaration path and nowhere else — every
    reader here is lock-free, deliberately, since a read that took the lock would create the
    file and destroy the very signal. So the lock present with the record absent says a
    declaration reached the writer and its result is gone.

    **Two limits, both stated rather than engineered around.** A declaration in flight holds
    the lock with the record not yet renamed into place, so a landing racing a declaration on
    one issue can read this as a loss; it refuses, which is the safe direction, and the
    remedy is to run the landing again. And removing the issue's whole review directory takes
    the lock with the record, leaving nothing to detect — the same class of limit as the
    `env -u CTI_DISPATCH_ID` bypass `_cmd_author` records and for the same reason: this
    catches the accident and the shortcut, never a session determined to defeat it.
    """
    record = authorship_path(root, issue)
    return not record.exists() and record.with_name(AUTHORSHIP_LOCK).is_file()


def store_authorship(root: Path, issue: int, profile: str, sha: str, recorded_at: str) -> bool:
    """Declare that an interactive session on `profile` authored this issue's change.

    Returns whether this call added an entry. **The claim is the pair `(profile, sha)`, and
    that is what is deduplicated.** The same pair twice is the same claim, so re-running the
    identical command is idempotent rather than a refusal or a second row; the same profile
    at a *different* commit is a different claim, and it is **appended** rather than
    dropped or overwritten (#398 round 1). A rebase or an amend is the ordinary way a
    second declaration happens, and of the three answers appending is the only one that
    keeps the record true: dropping it leaves the audit trail naming a commit that is not
    the one landed, and overwriting it erases a declaration that was made. Appending costs
    the check nothing, because `recorded_authors` deduplicates on profile — a second entry
    for one profile is one more line of trail and not one more excluded reviewer.

    `sha` is the commit the recording session had in hand and is written only when given: it
    is an audit trail for a later reader, never a claim about which commits that profile
    wrote, which is exactly what a dispatch record cannot say either.

    The read, the append and the write are one locked act. Two sessions declaring on one
    issue would otherwise each write what they read, and the loser's author would be gone
    from a set whose whole job is to exclude reviewers — see `_authorship_lock`.
    """
    with _authorship_lock(root, issue):
        entries = list(_authorship_entries(root, issue))
        if any(
            str(entry["profile"]).strip() == profile and str(entry.get("sha", "")) == sha
            for entry in entries
        ):
            return False
        entry: dict[str, object] = {
            "profile": profile,
            "recorded_at": recorded_at,
            "source": DECLARED,
        }
        if sha:
            entry["sha"] = sha
        entries.append(entry)
        document = (
            json.dumps(
                {"version": AUTHORSHIP_VERSION, "issue": issue, "authors": entries},
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        target = authorship_path(root, issue)
        try:
            _write_atomically(target, document)
        except OSError as unwritable:
            raise ReviewLoopError(
                AUTHORSHIP_UNWRITTEN_ERROR.format(issue=issue, target=target, reason=unwritable)
            ) from unwritable
        return True


def _claim_terminus_pending(path: Path, plan: str) -> bool:
    """Atomically claim the terminus's right to run; exactly one concurrent caller wins.

    `O_CREAT | O_EXCL` is the whole mechanism — the kernel refuses the second create, so
    two terminus calls cannot both pass an exists-check that either could have raced. The
    plan written under the claim names what the run was about to post, so a run that dies
    mid-post leaves an auditable marker rather than an invitation to repeat the side
    effects (#333 round 2, High 4).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(handle, "w", encoding="utf-8") as claimed:
        claimed.write(plan + "\n")
    return True


def _filing(issue: int, filing: Filing) -> tuple[str, str]:
    title = f"Arbiter-upheld finding {filing.finding} ({filing.severity}) from #{issue}"
    body = (
        f"{FILING_MARKER} #{issue}\n\n"
        f"Finding `{filing.finding}` ({filing.severity}, raised round {filing.round_raised}) was"
        f" upheld by the arbiter at the three-round wall on #{issue} and is owed its filing here"
        " (ADR-0071 ruling 4): the change lands, every upheld finding is filed as an issue on"
        " the originating item. This issue is that filing."
    )
    return title, body


def _dismissal(issue: int, dismissal: Dismissal) -> str:
    return (
        f"{DISMISSAL_MARKER} #{issue}\n\n"
        f"Finding `{dismissal.finding}` ({dismissal.severity}, raised round"
        f" {dismissal.round_raised}) was dismissed by the arbiter on #{issue}. Dismissals stay"
        " on the issue thread rather than becoming issues, are recorded in the landing record,"
        " and are handed to post-landing review (ADR-0071 ruling 4)."
    )


def _gh(argv: list[str], *, issue_input: str) -> str:
    """Run one bounded `gh` call with the body on stdin — never on argv, never unbounded."""
    try:
        completed = subprocess.run(  # noqa: S603 — fixed argv, no shell, no interpolation of the body
            argv,
            input=issue_input,
            capture_output=True,
            text=True,
            check=False,
            timeout=GH_TIMEOUT,
        )
    except FileNotFoundError as missing:
        message = "`gh` is not on PATH, so the terminus could not post."
        raise ExternalError(message) from missing
    except subprocess.TimeoutExpired as slow:
        message = f"`gh` did not answer within {GH_TIMEOUT}s."
        raise ExternalError(message) from slow
    if completed.returncode != 0:
        detail = completed.stderr.strip() or f"exit {completed.returncode}"
        message = f"`gh` refused: {detail}"
        raise ExternalError(message)
    return completed.stdout


def gh_create_issue(title: str, body: str) -> int:
    """File one upheld finding on the originating item, returning the issue it became."""
    output = _gh(["gh", "issue", "create", "--title", title, "--body-file", "-"], issue_input=body)
    # Every gh release prints the created issue's URL; the trailing integer is the number,
    # so the number is parsed from the one line gh has always emitted rather than from a
    # `--json` projection whose availability varies by version.
    tail = output.strip().rstrip("/").rsplit("/", 1)[-1]
    if not tail.isdigit():
        message = f"gh answered without an issue URL: {output.strip()!r}"
        raise ExternalError(message)
    return int(tail)


def gh_post_comment(issue: int, body: str) -> None:
    """Record one dismissal on the issue thread, where dismissals stay."""
    _gh(["gh", "issue", "comment", str(issue), "--body-file", "-"], issue_input=body)


def main(
    argv: list[str] | None = None,
    *,
    now: Callable[[], float] | None = None,
    create_issue: Callable[[str, str], int] = gh_create_issue,
    post_comment: Callable[[int, str], object] = gh_post_comment,
) -> int:
    """Drive one loop act. Named refusals exit 1; an unperformable act exits 3."""
    args = parse_args(argv)
    clock = now or time.time
    try:
        return args.handler(args, clock, create_issue, post_comment)
    except ReviewLoopError as refusal:
        print(f"[review-loop] {refusal}", file=sys.stderr)  # noqa: T201 — a CLI's refusal channel
        return REFUSED
    except ExternalError as failure:
        print(f"[review-loop] {failure}", file=sys.stderr)  # noqa: T201 — a CLI's refusal channel
        return NO_RESULT
    except OSError as failure:
        print(f"[review-loop] could not write review state: {failure}", file=sys.stderr)  # noqa: T201 — a CLI's refusal channel
        return NO_RESULT


if __name__ == "__main__":
    sys.exit(main())
