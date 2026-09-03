"""Who arbitrates when a loop runs out of rounds (#333, per the human ruling on #361).

One rule, one answer, decided before the dispute rather than during it. The two live
cases it must survive:

- **#318** — a retro's own loop escalated and the seat had no escalation entry, so the
  orchestrator chose an arbiter by hand. Against the very instruction the escalation was
  about, which is whose judge it was choosing. The ruling's answer: the table names the
  arbiter (the seat's escalation entry, head first), and every dispatchable seat now
  carries one.
- **#326** — the implementer seat's entry head (`codex-sol-high`) was refused by routing
  class 6 on the branch's own files, and the loop fell through to the entry's second
  profile (`opus-high`) with the exclusions recorded. The ruling's answer: fall through,
  recording what was excluded and why, and refuse by name when the walk is exhausted.

The walk is the seat's escalation entry, head first, then the seat's preference list —
#326 proved the entry tail is walked (it landed there), and the ruling's conflict case
walks on into the preference list. An empty escalation column refuses outright: the
blanket `fable-high` default is struck (#361 ruling 4), the only empty columns left are
the two marked not-applicable (`recon`, the interlocutor), and **adding a seat now
requires deciding its arbiter**.

The exclusions:

- the issue's dispatch records, through `dispatch.potential_authors_and_reviewers` — a
  *potential*-author set, never proof, because nothing on a record names the commits a
  run produced. Over-excluding costs a resolution step; under-excluding costs an author
  arbitrating its own work. The scan includes review records where the arbiter is
  concerned (#361: a prior reviewer is exactly the profile the walk must not select, and
  #318's real reviewer is on the records as a review dispatch and nowhere else).
- the routing policy over the branch under review's own paths, derived here and never
  caller-supplied (#391, on the orchestrator's ruling of 2026-08-19): `enforcing_match`
  per candidate, the landing read `just land` runs, so #326's head — eligible by records,
  refused by the policy on the diff's own paths — is passed over with its class and its
  matched paths recorded. This rung was caller-supplied flags for one cycle and the flags
  were never passed; the walk now holds the read itself. Against the shipped policy it
  excludes nobody, because since ADR-0073 no row refuses a landing — the rung runs
  anyway, and a refusing row is one table edit away from being honoured.
- live dispatchability, through `resolve_dispatchable`: the same `(lane, profile, seat)`
  rungs `just dispatch`'s ladder judges by, read through `dispatch.candidate_refusal`, so
  a profile resolved here cannot be one the ladder refuses two lines later.

Both properties carry over from `--reviewing` (#361 ruling 3): where a record could not
be read, the resolution is still taken — everything read is excluded — but is marked
`unchecked` rather than allowed to read as verified (#41: a check that could not run is
not a check that passed).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

# The registry this rule reads; the path was set above. `review_loop` supplies the
# journal constant the loop's events share, so the arbiter's events land beside them.
import dispatch
import otel_event
import review_loop
import routing_policy

RESOLVED: Final = "resolved"
REFUSED: Final = "refused"

# The named refusals #361's acceptance criteria demand: by name, never a default nobody
# chose. Neither carries a failure class — nothing here says anything about a provider or
# about code under test; one says the registry lacks a decision, the other that every
# candidate was excluded with the exclusions attached.
NO_ENTRY_REFUSAL: Final = "arbiter_no_entry"
EXHAUSTED_REFUSAL: Final = "arbiter_excluded"

NO_ENTRY_DETAIL: Final = (
    "the seat carries no escalation entry — adding a seat now requires deciding its"
    " arbiter (human ruling on #361, 2026-08-14, striking the blanket fable-high default;"
    " the only not-applicable rows are recon and the interlocutor)"
)
EXHAUSTED_DETAIL: Final = "every candidate in the walk was excluded — the exclusions are attached"

RECORDS_EXCLUSION: Final = "records_place_on_work"
ROUTING_EXCLUSION: Final = "routing_refused"
UNREGISTERED_EXCLUSION: Final = "unregistered_profile"
DISPATCH_EXCLUSION: Final = "dispatch_refused"

# `dispatch.Authorship` sets its `why` states alongside the profiles it did read (#41's
# two halves: the incomplete read still excludes, and still must not read as checked).
# Every state that is not a complete read — the directory absent, no dispatch on this
# issue, a record that would not open — leaves the resolution taken but unchecked, which
# is why `resolve` reads `Authorship.complete` rather than matching one `why` value:
# `no_dispatch_records` and `no_authoring_dispatch` are gaps the same way
# `records_unreadable` is (#333 round 1, High 3).
RECORDS_UNREADABLE: Final = "records_unreadable"

RESOLUTION_EVENT: Final = "cti.review.arbiter.resolved"


class Exclusion(NamedTuple):
    """One profile the walk passed over, and the fact that excluded it."""

    profile: str
    reason: str
    detail: str


class Resolution(NamedTuple):
    """The walk's answer: one arbiter, or a named refusal with the exclusions attached.

    `unchecked` is #41's mark: a record that could not be read leaves the resolution
    taken but not verifiable, so the caller records it `unchecked` — the same property
    `--reviewing` carries as `reviewing_checked`, never `reviewing_verified`.
    """

    kind: str
    arbiter: str = ""
    unchecked: bool = False
    passed_over: tuple[Exclusion, ...] = ()
    refusal: str = ""
    detail: str = ""


def _walk(seat: dispatch.Seat) -> tuple[str, ...]:
    """Walk the entry head first, then the entry tail, then the preference list — deduped.

    The order is the ruling's own: the table names the head (#361 ruling 1), a conflicted
    head falls through (#361 ruling 3), and #326 is the live proof the entry tail is
    walked before the preference list — the implementer seat landed on its entry's second
    profile, `opus-high`, which its preference list does not carry at all.
    """
    seen: list[str] = []
    for profile in (*seat.escalation, *seat.preference):
        if profile not in seen:
            seen.append(profile)
    return tuple(seen)


def _walk_first(
    seat: dispatch.Seat,
    authorship: dispatch.Authorship,
    policy: routing_policy.Policy,
    paths: tuple[str, ...],
    candidate: Callable[[str], dispatch.Refusal | None] | None,
) -> Resolution:
    """Walk one seat's candidates and return the first profile nothing excludes.

    The rungs, in order: the registry, the routing policy over the branch's own paths,
    the records, and — where `candidate` is supplied — the live `(lane, profile, seat)`
    rungs of `dispatch.candidate_refusal`. Every exclusion is recorded with its reason
    and its detail, whether the walk then answers or refuses. `unchecked` reads
    `Authorship.complete`, so every incomplete read — not only the unreadable one —
    leaves the resolution taken but not verifiable.
    """
    passed_over: list[Exclusion] = []
    for profile in _walk(seat):
        if profile not in dispatch.PROFILES:
            passed_over.append(
                Exclusion(profile, UNREGISTERED_EXCLUSION, "the registry carries no such profile")
            )
            continue
        match = routing_policy.enforcing_match(policy, paths, dispatch.PROFILES[profile].lane)
        if match is not None:
            # The #326 leg, derived rather than trusted since #391: the landing read over
            # this branch's paths, so a head the policy refuses never resolves.
            passed_over.append(
                Exclusion(
                    profile,
                    ROUTING_EXCLUSION,
                    f"routing_class={match.rule.id}:{match.rule.name} {' '.join(match.evidence)}",
                )
            )
            continue
        if profile in dispatch.never_alone_exclusions(authorship):
            # Resolved through `profile_lineage` (#413): the records rung asks who an arbiter
            # must not be, and a retired author's successor is as much an answer to that as
            # the author's own name — which no registry walk can select once renamed away.
            passed_over.append(
                Exclusion(profile, RECORDS_EXCLUSION, f"records={','.join(authorship.records)}")
            )
            continue
        if candidate is not None:
            refusal = candidate(profile)
            if refusal is not None:
                passed_over.append(
                    Exclusion(profile, DISPATCH_EXCLUSION, "; ".join(refusal.lines()))
                )
                continue
        return Resolution(
            kind=RESOLVED,
            arbiter=profile,
            unchecked=not authorship.complete,
            passed_over=tuple(passed_over),
        )
    return Resolution(
        kind=REFUSED,
        unchecked=not authorship.complete,
        passed_over=tuple(passed_over),
        refusal=EXHAUSTED_REFUSAL,
        detail=EXHAUSTED_DETAIL,
    )


def _no_entry() -> Resolution:
    return Resolution(kind=REFUSED, refusal=NO_ENTRY_REFUSAL, detail=NO_ENTRY_DETAIL)


def resolve(
    seat: dispatch.Seat,
    authorship: dispatch.Authorship,
    policy: routing_policy.Policy,
    paths: tuple[str, ...],
) -> Resolution:
    """Resolve one seat's arbiter over records and the routing policy alone.

    An empty escalation column refuses before any walk — the struck default's replacement
    is a decision the registry now requires, not a fallback. This is the seam tests and
    callers that already hold an `Authorship` use; `resolve_for_issue` is the production
    path that reads the records, and `resolve_dispatchable` is the one that also walks the
    live dispatchability rungs.
    """
    if not seat.escalation:
        return _no_entry()
    return _walk_first(seat, authorship, policy, paths, None)


def resolve_for_issue(
    seat: dispatch.Seat,
    issue: int,
    dispatch_dir: Path,
    policy: routing_policy.Policy,
    paths: tuple[str, ...],
) -> Resolution:
    """Resolve one seat's arbiter by reading the issue's own dispatch records.

    The production path (#333 round 1, High 2): the records are where the reviewers
    actually are. The scan is `dispatch.potential_authors_and_reviewers` — authors
    **and** reviewers, #361's criterion — because #318's real reviewer reached the
    records as a review dispatch and an authorship-only scan cannot see the one profile
    its criterion exists to exclude. A test that injects a reviewer by hand exercises a
    seam production never takes; this is the seam production takes.
    """
    authorship = dispatch.potential_authors_and_reviewers(issue, dispatch_dir)
    return resolve(seat, authorship, policy, paths)


def resolve_dispatchable(  # noqa: PLR0913 — the parameters are the walk's own inputs: seat, records, the clock, the policy and paths the routing rung reads, and the three directories the live rungs read
    seat: dispatch.Seat,
    authorship: dispatch.Authorship,
    now: datetime,
    policy: routing_policy.Policy,
    paths: tuple[str, ...],
    *,
    admission_dir: str | None = None,
    breaker_dir: str | None = None,
    credentials: str | None = None,
) -> Resolution:
    """Resolve one seat's arbiter, walking the live dispatchability rungs as well.

    #333 round 1, High 4: `resolve` walks a table, and a table cannot say whether a
    profile is dispatchable *now*. This runs `dispatch.candidate_refusal` per candidate —
    the same rungs `just dispatch`'s ladder judges by, called rather than restated, so a
    second copy is not how a profile comes to be resolved here and refused by the ladder
    two lines later. The directories default to whatever `dispatch.parse_args` resolves
    on this box and are overridable, which is how a test points the rungs at scratch
    records rather than at this box's live state.
    """
    if not seat.escalation:
        return _no_entry()
    args = dispatch.parse_args([])
    if admission_dir is not None:
        args.admission_dir = admission_dir
    if breaker_dir is not None:
        args.breaker_dir = breaker_dir
    if credentials is not None:
        args.credentials = credentials

    def candidate(profile: str) -> dispatch.Refusal | None:
        return dispatch.candidate_refusal(args, seat.name, profile, now)

    return _walk_first(seat, authorship, policy, paths, candidate)


def resolution_event(
    resolution: Resolution,
    seat: dispatch.Seat,
    issue: str,
    at: float,
) -> otel_event.Event:
    """Render the arbiter-invocation observable (ADR-0071 ruling 6): who, for what seat.

    Refusals are events too — a loop that escalates into a refusal is the #318 shape, and
    the trace that says so is worth more than the one that says the walk worked. The
    exclusions travel as `profile:reason` identities rather than a count (#333 round 1,
    Medium 5): a count says a walk passed two profiles over, and only the identities say
    which two or why — the distinction the terminus hands to post-landing review lives or
    dies on.
    """
    excluded = ",".join(f"{e.profile}:{e.reason}" for e in resolution.passed_over)
    return otel_event.Event(
        name=RESOLUTION_EVENT,
        at=at,
        attributes={
            "cti.issue": issue,
            "cti.review.seat": seat.name,
            "cti.review.arbiter": resolution.arbiter,
            "cti.review.arbiter.refusal": resolution.refusal,
            "cti.review.arbiter.unchecked": resolution.unchecked,
            "cti.review.arbiter.excluded": excluded,
        },
        resource={"service.name": "arma-cti-review-loop", "cti.issue": issue},
    )


def emit_resolution(
    resolution: Resolution,
    seat: dispatch.Seat,
    issue: str,
    at: float,
    journal: Path | None = None,
) -> bool:
    """Emit one resolution event; telemetry never fails the caller (see `otel_event`)."""
    return otel_event.emit(
        resolution_event(resolution, seat, issue, at),
        journal=journal or review_loop.JOURNAL,
    )
