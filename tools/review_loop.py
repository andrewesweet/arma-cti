"""The never-alone decision surface in one module (ADR-0071 ruling 4, #331).

Four things, and the issue that created this module asked for them **deep rather than split**:
exemption evaluation, the round budget, per-finding adjudication state, and the
escalation-condition evaluation #325 built. The alternative smears the loop's rules across
the landing protocol, the routing-policy reader and a config parser, with no single place to
test them — and the three consumers already sequenced (#333's arbiter and terminus, #334's
landing refusal) all read this one module rather than each re-deriving a half of it.

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
bounds the loop is the round budget above.

The **stop condition** — nothing above Low remains unadjudicated — is `stop_condition`.
Low findings never block and are recorded; that is the severity document's rule, restated
as code because #334's landing refusal reads it from here.

## The escalation bridge, and the material change it makes

`tools/escalation.py`'s four transferring-escalation conditions fire only on facts a caller
supplies, and its docstring records that `review_rounds` and `finding_above_low` were **not
mechanically recorded** when it landed: conditions 1, 2 and 3 could not fire. This module is
the recorder those conditions were waiting for — `item_state` derives both facts off a live
loop, recorded rather than `None`. Supplying loop state to `evaluate_escalation` therefore
makes conditions one to three fireable for the first time, which #348 banks in its
sequencing. The bridge delegates rather than restates: one wall constant, one condition
table, one evaluation, all owned where they already lived.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple

# tools/ holds standalone scripts rather than an importable package, so a sibling import
# needs the script's own directory on the path — the device `dispatch.py` and `brief.py`
# use.
sys.path.insert(0, str(Path(__file__).parent))

import escalation
from routing_policy import path_matches

if TYPE_CHECKING:
    from collections.abc import Iterable

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
    return path_matches(path, entry.surface)


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
    """

    route: str
    issue: str = ""
    conditional_on: str = ""


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


def _route_checks(finding: Finding, adjudication: Adjudication) -> None:
    """Enforce the fourth route's restrictions, which are the ruling's own words."""
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
    one-verdict-then-closed rule), an unknown route, and the fourth route's three
    restrictions. The adjudication is terminal — the returned loop's finding can never be
    adjudicated again, which is what bounds re-argument; the round budget bounds the loop.
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
        _route_checks(finding, adjudication)
        updated.append(finding._replace(adjudication=adjudication))
        found = True
    if not found:
        raise ReviewLoopError(UNKNOWN_FINDING_ERROR)
    return Loop(loop.review_rounds, tuple(updated))


def open_findings(loop: Loop) -> tuple[Finding, ...]:
    """Return the findings still awaiting their one adjudication."""
    return tuple(finding for finding in loop.findings if finding.adjudication is None)


def open_above_low(loop: Loop) -> tuple[Finding, ...]:
    """Return the open findings above Low — the band the stop condition adjudicates."""
    return tuple(finding for finding in open_findings(loop) if above_low(finding.severity))


def holding_above_low(loop: Loop) -> bool:
    """Whether a live finding above Low exists — escalation's `finding_above_low`, recorded.

    The fact #325's conditions could not fire without: `escalation.ItemState` holds it as
    `bool | None`, `None` meaning not recorded, and this is the recorder — a loop that has
    run a round has the fact, whichever way it points.
    """
    return bool(open_above_low(loop))


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
    which is the material change: conditions one to three of
    `config/escalation-conditions.json` become fireable the moment a caller supplies loop
    state. `routing_class` stays a caller-supplied fact (it is recorded on the dispatch
    record, #323, not in the loop) and `attempts` stays `None` until the observatory
    records it.
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
