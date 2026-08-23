"""One home for every name this project puts on an event (#484).

ADR-0078 decision 6's attribute registry, in the shape of `SEATS`: a name is
typed by hand into a surface or it is written here once, with its requirement
level and a one-line reason. `tools/check_attributes.py` (`just check`'s
`check-attributes` leg) derives every name the tracked Python actually carries
and reds on one this registry does not, which is `just check-arbiter`'s
discipline applied to names — a registry nothing enforces is a fourth copy
(#537's retention rule was written into five places and had already drifted in
three by the time it was reviewed).

**What is in it, and why event names too.** The registry's subject is every
`cti.*` and `gen_ai.*` name, marked by `kind`: attributes, event names, the
breaker's OTel scope, and the provider-side `gen_ai.usage.*` names this
project *reads* rather than emits. Events and the scope are in because the
check cannot tell an attribute key from an event name in a token stream and
should not have to — one rule, no per-site exceptions to be wrong about — and
because #480 asks for "every `cti.*` name", not only the attribute subset.

**Naming.** Names follow the GenAI semantic conventions where one exists and
the project prefix where none does, never one nested inside the other: nothing
in those conventions covers queueing or a wait's cause, so the wait family is
`cti.wait.*` and not `gen_ai.cti.*` or a `gen_ai.*` stretch. The `gen_ai.*`
rows here are read-side: the providers emit them (#480's plan adopts the same
conventions when this project emits its own seat and usage attributes) and
`tools/ledger.py` reads them, so they are registered as the standard they are.

**No name is ever deleted or repurposed** (#480 user story 22). A rename is a
deprecation with the old name kept readable; the archive is permanent and a
silent rename breaks every query written before it.

**The closed `block_reason` vocabulary** is this module's other half: the nine
values a wait's cause may take, each with its reason beside it, stated once
(#480 user story 30). `undetermined` exists because a guessed cause is worse
than a stated absence — "waiting for the human" and "waiting for a lane's peak
band to close" are opposite interventions, and a plausible wrong cause sends
the reader to fix the wrong thing. Absent, undetermined and a real value are
three facts, and each renders differently.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Mapping

# tools/ holds standalone scripts rather than an importable package, so a sibling import
# needs the script's own directory on the path — the device `breaker.py` uses to reach here.
sys.path.insert(0, str(Path(__file__).parent))

# The path insert above is what makes this importable.
import otel_event


class Name(NamedTuple):
    """One registry row: what the name is, how required, and why it exists."""

    kind: str
    requirement: str
    reason: str


# The registry. Requirement levels are the semantic conventions' own four
# (required, conditionally required, recommended, opt-in) as words with
# underscores; a row's reason carries anything the level cannot.
NAMES: Final[dict[str, Name]] = {
    # ---- events -------------------------------------------------------------
    "cti.breaker.transition": Name(
        "event", "required", "One lane breaker state change, the event #226 built the seam for."
    ),
    "cti.queue.transition": Name(
        "event", "required", "One dispatch-policy write, beside the policy file it changed."
    ),
    "cti.admission.trial.transition": Name(
        "event", "required", "One trial-cycle state change on the #242 cycle's kept history."
    ),
    "cti.review.round": Name(
        "event",
        "required",
        "One review loop's round count; also an attribute on it, which is why the"
        " row's kind is both — the string is one name serving two OTel positions.",
    ),
    "cti.review.escalation": Name(
        "event", "required", "One escalation record, when a loop's condition fired."
    ),
    "cti.review.dispute": Name("event", "required", "One finding's adjudication outcome."),
    "cti.review.terminus": Name(
        "event", "required", "One loop's terminal filing and dismissal record."
    ),
    "cti.review.arbiter.resolved": Name(
        "event, attribute",
        "required",
        "One arbiter resolution, from the walk's own module; the same string is"
        " the event's name and the attribute saying it resolved — one name, two"
        " OTel positions, as `cti.review.round`'s row says.",
    ),
    "cti.wait.blocked": Name(
        "event",
        "required",
        "One wait recognised at a seam that knows its cause (#484); paired with the"
        " next activity at that seam, this is the interval's start, not a span.",
    ),
    # ---- attributes: dispatch identity -------------------------------------
    "cti.dispatch_id": Name(
        "attribute",
        "required",
        "The dispatch a record belongs to; the join key every ledger row reads.",
    ),
    "cti.lane": Name(
        "attribute",
        "conditionally_required",
        "The lane a breaker transition or dispatch identity names; present wherever"
        " a lane exists to name.",
    ),
    "cti.profile": Name(
        "attribute", "required", "The profile half of a dispatch identity's route."
    ),
    "cti.seat": Name("attribute", "required", "The seat half of a dispatch identity's route."),
    "cti.issue": Name(
        "attribute",
        "conditionally_required",
        "The issue a review or dispatch identity belongs to; present wherever one does.",
    ),
    "cti.base_sha": Name(
        "attribute", "required", "The origin/main commit a dispatch's diff is measured from."
    ),
    # ---- attributes: breaker ------------------------------------------------
    "cti.breaker.from": Name("attribute", "required", "The state a breaker transition left."),
    "cti.breaker.to": Name("attribute", "required", "The state a breaker transition entered."),
    "cti.breaker.rule": Name(
        "attribute", "required", "Which rule tripped, so a trip is attributable."
    ),
    "cti.breaker.reason": Name(
        "attribute", "required", "The trip's own account, in the rule's words."
    ),
    "cti.breaker.reset_at": Name(
        "attribute",
        "conditionally_required",
        "The provider's published window boundary; absent only where none was published,"
        " which is itself the fact — never guessed, never defaulted (#483's discipline).",
    ),
    "cti.breaker.streak": Name(
        "attribute", "conditionally_required", "The consecutive-refusal count that fed the trip."
    ),
    "cti.breaker.escalates": Name(
        "attribute", "required", "Whether the trip auto-resets or waits on a human."
    ),
    # ---- attributes: admission trial ---------------------------------------
    "cti.admission.trial.bar_id": Name(
        "attribute", "required", "Which pre-registered bar a trial transition assessed against."
    ),
    "cti.admission.trial.from": Name("attribute", "required", "The trial state a transition left."),
    "cti.admission.trial.to": Name(
        "attribute", "required", "The trial state a transition entered."
    ),
    "cti.admission.trial.assessed": Name(
        "attribute", "conditionally_required", "The cycle an assessment read, where one did."
    ),
    "cti.admission.trial.reason": Name(
        "attribute", "conditionally_required", "The transition's own account."
    ),
    # ---- attributes: queue --------------------------------------------------
    "cti.queue.verb": Name("attribute", "required", "The policy write a transition records."),
    "cti.queue.state": Name(
        "attribute", "conditionally_required", "The freeze state a freeze verb wrote."
    ),
    "cti.queue.ruling": Name(
        "attribute", "required", "The human's words a write transcribed, never a decision."
    ),
    "cti.queue.value": Name(
        "attribute", "conditionally_required", "The limit a wip write recorded."
    ),
    "cti.queue.name": Name(
        "attribute", "conditionally_required", "The package a package verb touched."
    ),
    "cti.queue.issues": Name(
        "attribute", "conditionally_required", "The package's issue count at write time."
    ),
    # ---- attributes: review loop -------------------------------------------
    "cti.review.raised": Name(
        "attribute", "required", "Findings the round raised, severities inline."
    ),
    "cti.review.open_above_low": Name(
        "attribute", "required", "Unadjudicated above-low findings the round left open."
    ),
    "cti.review.holding_above_low": Name(
        "attribute", "required", "Above-low findings held for arbitration."
    ),
    "cti.review.evaluation": Name(
        "attribute", "required", "The condition kind that fired an escalation."
    ),
    "cti.review.conditions": Name(
        "attribute", "required", "The conditions the escalation recorded."
    ),
    "cti.review.arbiter": Name(
        "attribute", "required", "The profile the walk resolved to, where one did."
    ),
    "cti.review.finding": Name("attribute", "required", "The finding a dispute adjudicated."),
    "cti.review.severity": Name("attribute", "required", "The adjudicated finding's severity."),
    "cti.review.round_raised": Name(
        "attribute", "required", "The round the disputed finding was raised in."
    ),
    "cti.review.route": Name(
        "attribute", "required", "The adjudication's route, upheld or dismissed."
    ),
    "cti.review.default_applies": Name(
        "attribute", "required", "Whether the terminus applied the default verdict."
    ),
    "cti.review.filings": Name("attribute", "required", "Upheld findings the terminus filed."),
    "cti.review.dismissals": Name(
        "attribute", "required", "Dismissed findings the terminus recorded."
    ),
    "cti.review.seat": Name(
        "attribute", "required", "The seat an arbiter resolution was asked for."
    ),
    "cti.review.arbiter.excluded": Name(
        "attribute", "conditionally_required", "Profiles the resolution excluded."
    ),
    "cti.review.arbiter.refusal": Name(
        "attribute", "conditionally_required", "The refusal the walk stopped on, where one did."
    ),
    "cti.review.arbiter.unchecked": Name(
        "attribute", "conditionally_required", "Checks the walk could not read, kept visible."
    ),
    # ---- attributes: wait (#484) --------------------------------------------
    "cti.wait.block_reason": Name(
        "attribute",
        "required",
        "The closed vocabulary's value for this wait's cause; always present on"
        " cti.wait.blocked, `undetermined` where the cause could not be determined —"
        " never omitted, never guessed.",
    ),
    "cti.wait.surface": Name(
        "attribute",
        "required",
        "The seam that recognised the wait — queue, dispatch or review — so one"
        " journal line says where the measurement came from.",
    ),
    "cti.wait.refusal": Name(
        "attribute",
        "conditionally_required",
        "The refusal kind that carried the cause; present wherever a refusal was"
        " the wait's evidence, and most worth reading beside `undetermined`.",
    ),
    # ---- scope ---------------------------------------------------------------
    "cti.breaker": Name(
        "scope",
        "opt_in",
        "The OTel scope every family's records render under unless one names its own;"
        " the seam's default, not a family's name.",
    ),
    # ---- read-side: provider conventions this project reads, not emits -------
    "gen_ai.usage.input_tokens": Name(
        "attribute",
        "recommended",
        "Read from Codex spans by the ledger; the GenAI convention this project"
        " adopts rather than reinvents (#480).",
    ),
    "gen_ai.usage.prompt_tokens": Name(
        "attribute", "recommended", "Read-side GenAI convention, as above."
    ),
    "gen_ai.usage.output_tokens": Name(
        "attribute", "recommended", "Read-side GenAI convention, as above."
    ),
    "gen_ai.usage.completion_tokens": Name(
        "attribute", "recommended", "Read-side GenAI convention, as above."
    ),
}


# The closed vocabulary (#480's Implementation Decisions, verbatim set). A new
# value is an explicit edit here with its reason — the same spellings cannot
# arrive three ways across three call sites if there is one spelling to use.
BLOCK_REASONS: Final[dict[str, str]] = {
    "waiting_human": "A human ruling, sign-off or clear the queue is stopped on; the"
    " human's is the only hand that ends it.",
    "lane_peak_band": "The lane's published peak band; it opens on a schedule nobody"
    " here can move.",
    "quota_exhausted": "The provider's quota; it reopens at the provider's own"
    " published window boundary, never a backoff we chose.",
    "breaker_open": "This project's own quality breaker tripped; it reopens only by a"
    " human's hand, never on a timer.",
    "waiting_reviewer": "Work exchanged and awaiting its reviewer's verdict.",
    "worktree_occupied": "Another holder owns the worktree; it frees when they land or"
    " leave. Registered ahead of the surface, not emitted by one: `tools/worktree.py`"
    " refuses with this kind and no seam journals it yet (#484 round 2, finding 2).",
    "wip_limit": "The ruled work-in-progress limit is reached; it clears when something lands.",
    "slot_unavailable": "No regression-tier slot is free; reserved for the tier's"
    " no-slot stop, whose bash seam (ADR-0049) does not yet emit — the value is"
    " registered ahead of the surface, not emitted by one.",
    "undetermined": "The wait is real and its cause is not determinable as one of the"
    " closed set; stated rather than guessed because a plausible wrong cause sends"
    " the reader to fix the wrong thing.",
}

UNDETERMINED: Final = "undetermined"

WAIT_EVENT: Final = "cti.wait.blocked"

# Which refusal kind announces which cause, at the seams that emit waits. Kinds
# not listed are not waits — a bad argument or an unknown seat refuses a request
# that was never going to happen, and emitting a wait for it would be the guess
# this vocabulary exists to refuse. `lane_breaker_open` is decided by its
# failure class instead of its kind, because quota and a quality trip are two
# different remedies wearing one refusal.
WAIT_REFUSAL_REASONS: Final[Mapping[str, str]] = {
    "dispatch_frozen": "waiting_human",
    "wip_reached": "wip_limit",
    "lane_peak_hours": "lane_peak_band",
    "worktree_occupied": "worktree_occupied",
}

# The one failure class that does not map through the kind row above.
_BREAKER_QUOTA: Final = "quota_exhausted"
_BREAKER_QUALITY: Final = "provider_refused"


def block_reason_for(refusal: object) -> str | None:
    """Return the wait cause a refusal names, `None` where it names no wait at all.

    `lane_breaker_open` reads its failure class — quota reopens at a published
    boundary and a quality trip waits on a human, and those are different rows
    of the vocabulary. A breaker trip on a class this mapping does not know is
    a real wait with an unnamed cause, which is `undetermined` and not a guess.
    `no_ready_issue` is deliberately absent: whether it is a wait at all depends
    on whether any candidate existed, which the seam knows and a kind does not.
    """
    kind = getattr(refusal, "kind", "")
    failure_class = getattr(refusal, "failure_class", "") or ""
    if kind == "lane_breaker_open":
        if failure_class == _BREAKER_QUOTA:
            return _BREAKER_QUOTA
        if failure_class == _BREAKER_QUALITY:
            return "breaker_open"
        return UNDETERMINED
    return WAIT_REFUSAL_REASONS.get(kind)


def wait_event(
    reason: str,
    surface: str,
    at: float,
    *,
    refusal: str = "",
    issue: int | None = None,
) -> otel_event.Event:
    """Build one `cti.wait.blocked` event; the only place its attributes are spelled.

    Raises on a value outside the closed vocabulary: that is a programming error
    this module exists to make impossible, not a transport failure to swallow —
    `emit_wait` stays fail-open over the *emission*, never over the spelling.
    """
    if reason not in BLOCK_REASONS:
        message = f"block_reason not in the closed vocabulary: {reason!r}"
        raise ValueError(message)
    attributes: dict[str, object] = {
        "cti.wait.block_reason": reason,
        "cti.wait.surface": surface,
    }
    if refusal:
        attributes["cti.wait.refusal"] = refusal
    if issue is not None:
        attributes["cti.issue"] = issue
    return otel_event.Event(
        name=WAIT_EVENT,
        at=at,
        attributes=attributes,
        resource={"service.name": "arma-cti-wait"},
    )


def emit_wait(
    event: otel_event.Event,
    journal: Path,
    endpoint: str = "",
) -> bool:
    """Export one wait event and journal it with its export's own outcome.

    Fail-open exactly as every family is: the wait was real whatever a collector
    did, so a refusal is journalled with `exported: false` and never raised. The
    journal lives beside the surface's own state (`store.directory`, the
    dispatch records' root, the review root) — no new state directory (#484).
    """
    return otel_event.emit(event, journal=journal, endpoint=endpoint)
