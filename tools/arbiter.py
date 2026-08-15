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

The exclusions are two facts this module does not derive, read as inputs:

- the issue's dispatch records, through `dispatch.potential_authors` — a
  *potential*-author set, never proof, because nothing on a record names the commits a
  run produced. Over-excluding costs a resolution step; under-excluding costs an author
  arbitrating its own work.
- routing refusals for the branch under review, caller-supplied as `profile -> reason` —
  the #326 leg, where the head was eligible by records and refused by the routing policy
  on the diff's own paths.

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
    from collections.abc import Mapping

sys.path.insert(0, str(Path(__file__).parent))

# The registry this rule reads; the path was set above. `review_loop` supplies the
# journal constant the loop's events share, so the arbiter's events land beside them.
import dispatch
import otel_event
import review_loop

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

# `dispatch.potential_authors` sets this `why` alongside the profiles it did read (#41's
# two halves: the incomplete read still excludes, and still must not read as checked).
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


def resolve(
    seat: dispatch.Seat,
    authorship: dispatch.Authorship,
    routing_refusals: Mapping[str, str] | None = None,
) -> Resolution:
    """Resolve one seat's arbiter: the walk's first profile nothing excludes.

    An empty escalation column refuses before any walk — the struck default's replacement
    is a decision the registry now requires, not a fallback. Every exclusion is recorded
    with its reason and its detail, whether the walk then answers or refuses.
    """
    if not seat.escalation:
        return Resolution(kind=REFUSED, refusal=NO_ENTRY_REFUSAL, detail=NO_ENTRY_DETAIL)
    refusals = routing_refusals or {}
    passed_over: list[Exclusion] = []
    for profile in _walk(seat):
        if profile not in dispatch.PROFILES:
            passed_over.append(
                Exclusion(profile, UNREGISTERED_EXCLUSION, "the registry carries no such profile")
            )
            continue
        if profile in refusals:
            passed_over.append(Exclusion(profile, ROUTING_EXCLUSION, refusals[profile]))
            continue
        if profile in authorship.potential:
            passed_over.append(
                Exclusion(profile, RECORDS_EXCLUSION, f"records={','.join(authorship.records)}")
            )
            continue
        return Resolution(
            kind=RESOLVED,
            arbiter=profile,
            unchecked=authorship.why == RECORDS_UNREADABLE,
            passed_over=tuple(passed_over),
        )
    return Resolution(
        kind=REFUSED,
        unchecked=authorship.why == RECORDS_UNREADABLE,
        passed_over=tuple(passed_over),
        refusal=EXHAUSTED_REFUSAL,
        detail=EXHAUSTED_DETAIL,
    )


def resolution_event(
    resolution: Resolution,
    seat: dispatch.Seat,
    issue: str,
    at: float,
) -> otel_event.Event:
    """Render the arbiter-invocation observable (ADR-0071 ruling 6): who, for what seat.

    Refusals are events too — a loop that escalates into a refusal is the #318 shape, and
    the trace that says so is worth more than the one that says the walk worked.
    """
    return otel_event.Event(
        name=RESOLUTION_EVENT,
        at=at,
        attributes={
            "cti.issue": issue,
            "cti.review.seat": seat.name,
            "cti.review.arbiter": resolution.arbiter,
            "cti.review.arbiter.refusal": resolution.refusal,
            "cti.review.arbiter.unchecked": resolution.unchecked,
            "cti.review.arbiter.excluded": len(resolution.passed_over),
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
