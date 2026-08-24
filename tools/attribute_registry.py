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

**The stage vocabulary is the same discipline one family over** (#490): the six
stages of the work-item pipeline, stated once in `STAGES` and in pipeline
order, and the three states of an arrival's first-pass status in `FIRST_PASS`.
Rolled throughput yield multiplies the per-stage first-pass rates, so an
undeterminable status is recorded as `undetermined` and never defaulted to
true — a defaulted true does not flatter one stage, it inflates every stage
after it. `record_stage_arrival` is the one entry the seams call; it decides
the status against the issue's own stage journal, whose absences it states
rather than borrows a clean past from.
"""

from __future__ import annotations

import json
import os
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
    # ---- attributes: terminal state (#489) ----------------------------------
    "cti.terminal.state": Name(
        "event, attribute",
        "required",
        "One dispatch's recorded terminal state for work that started and did not"
        " finish (#489); also an attribute on it, the `cti.review.round` dual"
        " position — one name, two OTel slots.",
    ),
    "cti.terminal.class": Name(
        "attribute",
        "required",
        "The failure class the terminal state carries, always one of"
        " NOT_A_RESULT_CLASSES — the existing vocabulary, never a parallel one.",
    ),
    # ---- attributes: stage transitions (#490) --------------------------------
    "cti.stage.transition": Name(
        "event",
        "required",
        "One arrival at a stage of the work-item pipeline (#490); the arrival the"
        " first-pass yield of that stage is computed over.",
    ),
    "cti.stage.name": Name(
        "attribute",
        "required",
        "The pipeline stage reached, always one of STAGES; the stage set is the"
        " registry's own closed vocabulary, stated once.",
    ),
    "cti.stage.first_pass": Name(
        "attribute",
        "required",
        "Whether this arrival was the item's first pass at the stage, always one of"
        " FIRST_PASS — `undetermined` where the journal could not say, never a"
        " defaulted true, because yield multiplies and one guess inflates every"
        " stage after it.",
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

# The terminal state's class vocabulary (#489): the failure-class table's own
# not-a-result rows and nothing else. CLAUDE.md's table is the authority and lives
# as prose, so this is its not-a-result half stated once, machine-readably, each
# row's reason quoting what makes the class not a result — the same shape
# `BLOCK_REASONS` gives a wait's causes. `tools/ledger.py`'s `gate_outcome` reads
# this set rather than holding a second tuple of the same names, which is the
# #501/#503/#504 defect class (a value relocated to a more principled-looking
# place while staying declared rather than derived) not repeated: one home,
# everyone derives. The table's other rows — `timeout`, `assertion_failed` and
# their kin — are results a gate acted on, and are deliberately not restated
# here because nothing this registry feeds classifies on them.
NOT_A_RESULT_CLASSES: Final[dict[str, str]] = {
    "infra_unavailable": (
        "Not a result: a lane that cannot be reached says nothing about the work"
        " dispatched to it, so the stop is never interpreted."
    ),
    "quota_exhausted": (
        "Not a result: the provider's quota reopened at its own published boundary"
        " and the partial run is never read."
    ),
    "provider_refused": (
        "Not a result: the provider refused the request, or this project's own"
        " breaker refused the dispatch."
    ),
    "untyped_harness_failure": (
        "Not a result, and it outranks the other three (#184): the default where a"
        " class is missing — a harness bug to fix first, never a verdict on the work."
    ),
}

TERMINAL_EVENT: Final = "cti.terminal.state"
TERMINAL_ABANDONED: Final = "abandoned"

# The work-item pipeline's stages (#490), in pipeline order — the order is data,
# not presentation: an arrival's first-pass status is decided by how many times
# the stages up to and including it were reached before. The spellings carry no
# spaces (`own_gate`, not "own gate") because these are query values. One home:
# consumers — the recorder below, the observatory's stage view, the tests —
# derive the set from here and never restate it (#501's defect class).
STAGES: Final[dict[str, str]] = {
    "brief": "The dispatch briefing composed for the issue; every later stage"
    " arrives through work this one described.",
    "implementation": "The implementer dispatch running the work (#490's stage"
    " arrives when the dispatch record is laid down — the dispatch exists even"
    " where the child then refuses or dies).",
    "own_gate": "The implementer running `just fast` as its own gate; one arrival"
    " per dispatch, because a gate re-run in the same dispatched session is the"
    " same arrival, not a rework of it.",
    "exchange": "The implementer pushing the review branch for the never-alone"
    " handover; the moment the work stops being the implementer's alone.",
    "review": "The review dispatch judging the work, arrived at when the review"
    " dispatch's record is laid down.",
    "land": "The push to `origin/main` that lands the work; reached where"
    " `just land`'s own push succeeded, including the run whose merge step is"
    " still outstanding.",
}

# The three states of a stage arrival's first-pass status (#490's central
# criterion). `undetermined` is not a soft true: rolled throughput yield
# multiplies the per-stage rates, so a defaulted true does not flatter one stage
# — it inflates the product, and five stages at ninety per cent is fifty-nine,
# not sixty-six. Undetermined arrivals are counted beside the yield and never
# inside its denominator.
FIRST_PASS: Final[dict[str, str]] = {
    "first_time": "The item arrived on its first pass: every stage before this"
    " one exactly once, and this one not at all.",
    "after_rework": "The item arrived again — some stage up to and including this"
    " one had already been reached, so this pass follows rework.",
    "undetermined": "The arrival's history could not be read — an unreadable"
    " journal, a line that predates the stage field, or no journal where the"
    " rest of the record says the issue moved before the recorder existed — so"
    " the status is stated as this rather than guessed, and never defaulted to"
    " true.",
}

# Which dispatch seats are arrivals at a pipeline stage. Only two are: the
# implementer's dispatch is the implementation stage and the review seat's is the
# review stage, while a planner, recon, retro or orchestrator dispatch is not a
# pass through the work-item pipeline at all. Values are STAGES' own keys, and
# the brief seam uses the same map — a brief composed for a seat this map leaves
# out is not a brief-stage arrival, because a review dispatch's briefing is
# review logistics rather than the item being re-briefed.
STAGE_OF_SEAT: Final[Mapping[str, str]] = {
    "implementer": "implementation",
    "review": "review",
}

STAGE_EVENT: Final = "cti.stage.transition"

# The stage family's journal (#490): one file per issue, beside the review
# loop's own state under the review root — the per-issue home that already
# exists, so the family adds no directory of its own. Every seam that records a
# stage arrival knows the issue, and first-pass status is decided against this
# journal's own history: an arrival whose history cannot be read from the
# journal says `undetermined` rather than borrowing a clean past it cannot see.
# An absent journal is not itself that clean past (#490 round 2, finding 1):
# nothing has been journalled yet, but something may have happened before the
# recorder existed, so the absence is granted a clean past only where the rest
# of the record holds no prior pipeline act for the issue — the check
# `_pipeline_history_seen` below states that rule where it runs.
STAGE_JOURNAL: Final = "stages.jsonl"

# The dispatch records' default root, for the absent-journal evidence check
# alone — the same home `tools/dispatch.py`, the ledger, the breaker, recovery
# and the observatory each name as their own default, restated rather than
# imported because this module stands below `dispatch.py` (which imports it).
DISPATCH_RECORDS_ROOT: Final = Path.home() / ".arma-cti" / "dispatches"

# What `record_stage_arrival` returns where the caller's own dispatch already
# reached this stage: not a first-pass value and never journalled — a gate
# re-run in the same dispatched session is the same arrival, not a new one.
STAGE_ALREADY_REACHED: Final = "already_reached"


def stage_journal(issue: int, review_root: Path) -> Path:
    """Return the per-issue stage journal's path under the review root."""
    return review_root / str(issue) / STAGE_JOURNAL


def _stage_line(line: str) -> tuple[str, str] | None:
    """Parse one stage journal line into its stage and dispatch id, or say unreadable.

    `None` is every way a line can fail to be a readable stage arrival: not
    JSON, not an object, not this family's event, no attributes, or a stage
    name outside the closed set — which includes the line that predates the
    field and carries none (#490's historical-shape case, read as a hole in the
    history rather than as an arrival).
    """
    try:
        document = json.loads(line)
    except ValueError:
        return None
    if not isinstance(document, dict) or document.get("event") != STAGE_EVENT:
        # Not a stage line — a foreign or corrupt line in the family's own journal.
        return None
    attributes = document.get("attributes")
    if not isinstance(attributes, dict):
        return None
    named = attributes.get("cti.stage.name")
    if named not in STAGES:
        return None
    recorded = attributes.get("cti.dispatch_id")
    return named, recorded if isinstance(recorded, str) else ""


def _prior_arrivals(
    journal: Path, stage: str, dispatch_id: str, issue: int, review_root: Path
) -> tuple[dict[str, int], bool, bool]:
    """Read the journal's arrival history, or say it cannot be read.

    Returns the count of prior arrivals per stage, whether that count is
    complete enough to decide a first-pass status, and whether this dispatch
    already reached this stage. A journal that is absent is a readable zero
    only where the rest of the record holds no prior pipeline act for the
    issue — `_pipeline_history_seen` decides that, because every issue that
    predates the recorder has no journal and most of those have a past. A
    journal that exists and will not parse, or carries a stage line without a
    placeable stage name (a line that predates the field), is not readable:
    the history has a hole in it, and a hole is `undetermined` rather than a
    guess at what fell in.
    """
    counts = dict.fromkeys(STAGES, 0)
    if not journal.is_file():
        return counts, not _pipeline_history_seen(issue, review_root, dispatch_id), False
    try:
        lines = journal.read_text(encoding="utf-8").splitlines()
    except OSError:
        return counts, False, False
    for line in lines:
        parsed = _stage_line(line)
        if parsed is None:
            return counts, False, False
        named, recorded = parsed
        counts[named] += 1
        if dispatch_id and named == stage and recorded == dispatch_id:
            return counts, True, True
    return counts, True, False


def dispatch_records_root() -> Path:
    """Return the dispatch records' root, read at call time like the review root.

    `CTI_DISPATCH_DIR` is the redirection seam `tools/dispatch_follow.py` and
    the observatory already document, so the recorder honours the same spelling
    rather than minting a second variable for one directory.
    """
    return Path(os.environ.get("CTI_DISPATCH_DIR", str(DISPATCH_RECORDS_ROOT)))


def _pipeline_history_seen(issue: int, review_root: Path, dispatch_id: str) -> bool:
    """Say whether the record outside the journal shows a prior pipeline act.

    The rule (#490 round 2, finding 1): an absent journal is the absence of
    evidence, not evidence of a clean past, so it buys `first_time` only where
    nothing outside it names a prior act of the pipeline for this issue. Two
    checks, both over records that already exist — never a guess at dates or
    an issue number chosen by hand:

    - the issue's own directory under the review root holds any entry at all.
      Every file there is an act's artefact — a loop opened, an arbiter
      escalation, an authorship declared, a wait journalled — and none of those
      precedes the work they judge, so any entry says the item moved.
    - a dispatch record names the issue from a seat whose dispatch is a
      pipeline stage (`STAGE_OF_SEAT` — implementer and review). A recon or
      planner dispatch names triage, not a pass through the pipeline, so it is
      deliberately not evidence; the arrival being decided is a pipeline
      status and the evidence is the pipeline's own acts. The current
      `dispatch_id` is passed over, because the record laying down this very
      arrival is this arrival, not prior history.

    A dispatch record that exists and will not read is taken as evidence seen:
    the seat inside it cannot be known, and the criterion's own bar is to
    never grant a clean past a read could not confirm. That is the pessimistic
    direction and fires once — the arrival it undetermines founds the journal.
    """
    directory = review_root / str(issue)
    if directory.is_dir():
        try:
            if any(directory.iterdir()):
                return True
        except OSError:
            return True
    for record in sorted(dispatch_records_root().glob("*/dispatch.json")):
        try:
            document = json.loads(record.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return True
        if not isinstance(document, dict):
            return True
        if dispatch_id and document.get("dispatch_id") == dispatch_id:
            continue
        if str(document.get("issue", "")) != str(issue):
            continue
        if document.get("seat") in STAGE_OF_SEAT:
            return True
    return False


def _arrival_status(stage: str, counts: Mapping[str, int]) -> str:
    """Decide first-pass status from the journal's own counts.

    An arrival is first-time when every stage before this one was reached
    exactly once and this one not at all — per-stage equality, not a sum over
    the prefix, because a skipped stage and a doubled one compensate in a sum
    (a second brief beside an implementation line that failed open reads 2 at
    the own gate) while the deviation both represent is rework. Any second
    arrival at any stage up to here, or any hole where a first should stand,
    breaks the equality, which is the point: rework upstream makes a
    downstream first arrival not-first-pass, exactly as rolled throughput
    yield counts it.
    """
    order = list(STAGES)
    position = order.index(stage)
    first_time = all(
        counts[named] == (index < position) for index, named in enumerate(order[: position + 1])
    )
    return "first_time" if first_time else "after_rework"


def stage_event(
    stage: str,
    first_pass: str,
    at: float,
    *,
    issue: int,
    dispatch_id: str = "",
) -> otel_event.Event:
    """Build one `cti.stage.transition` event; the only place its attributes are spelled.

    Raises on a stage or first-pass value outside the closed vocabularies, as
    `wait_event` does: a misspelling is a programming error this module exists
    to make impossible, not a transport failure to swallow — `emit_stage` stays
    fail-open over the emission, never over the spelling.
    """
    if stage not in STAGES:
        message = f"stage not in the closed set: {stage!r}"
        raise ValueError(message)
    if first_pass not in FIRST_PASS:
        message = f"first_pass not in the closed vocabulary: {first_pass!r}"
        raise ValueError(message)
    attributes: dict[str, object] = {
        "cti.stage.name": stage,
        "cti.stage.first_pass": first_pass,
        "cti.issue": issue,
    }
    if dispatch_id:
        attributes["cti.dispatch_id"] = dispatch_id
    return otel_event.Event(
        name=STAGE_EVENT,
        at=at,
        attributes=attributes,
        resource={"service.name": "arma-cti-stage"},
    )


def emit_stage(
    event: otel_event.Event,
    journal: Path,
    endpoint: str = "",
) -> bool:
    """Export one stage-transition event and journal it with its export's outcome.

    Fail-open as every family is: the stage was reached whatever a collector or
    a journal did, so a failure to record degrades to no record and never
    reaches the dispatch, the gate or the landing the record is about (#490).
    """
    return otel_event.emit(event, journal=journal, endpoint=endpoint)


def record_stage_arrival(
    stage: str,
    issue: int,
    review_root: Path,
    at: float,
    *,
    dispatch_id: str = "",
) -> str:
    """Record one stage arrival with its first-pass status, fail-open (#490).

    The one entry the seams call. Reads the issue's stage journal, decides the
    status against it, and emits — never raising, because an arrival the record
    could not take must not fail the brief, dispatch, gate, exchange or landing
    that was arriving. Where no journal exists yet, the status is decided
    against the rest of the record first (`_pipeline_history_seen`): a clean
    `first_time` is granted only to an issue nothing moved before, never to one
    that merely predates the recorder. A dispatch that already reached this
    stage records nothing and answers `STAGE_ALREADY_REACHED`, so a re-run
    inside one dispatched session is the same arrival, not rework of it;
    arrivals with no dispatch to name (a brief, an exchange by hand) cannot be
    deduplicated and count every time, which is the journal's honest reading
    of a re-brief.
    """
    if stage not in STAGES:
        message = f"stage not in the closed set: {stage!r}"
        raise ValueError(message)
    journal = stage_journal(issue, review_root)
    counts, determinable, repeat = _prior_arrivals(journal, stage, dispatch_id, issue, review_root)
    if repeat:
        return STAGE_ALREADY_REACHED
    status = _arrival_status(stage, counts) if determinable else UNDETERMINED
    emit_stage(
        stage_event(stage, status, at, issue=issue, dispatch_id=dispatch_id),
        journal=journal,
    )
    return status


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


def terminal_event(
    state: str,
    failure_class: str,
    at: float,
    *,
    dispatch_id: str,
    identity: Mapping[str, object] | None = None,
) -> otel_event.Event:
    """Build one `cti.terminal.state` event; the only place its attributes are spelled.

    `identity` is the dispatch's own ledger row, read for the attributes it
    carries (`lane`, `profile`, `seat`, `issue`) and never required to carry
    them. Raises on a state or class outside the closed vocabulary, exactly as
    `wait_event` does: a misspelling is a programming error this module exists
    to make impossible, not a transport failure to swallow.
    """
    if state != TERMINAL_ABANDONED:
        message = f"terminal state not in the closed vocabulary: {state!r}"
        raise ValueError(message)
    if failure_class not in NOT_A_RESULT_CLASSES:
        message = f"terminal class not in the closed vocabulary: {failure_class!r}"
        raise ValueError(message)
    attributes: dict[str, object] = {
        "cti.dispatch_id": dispatch_id,
        "cti.terminal.state": state,
        "cti.terminal.class": failure_class,
    }
    row = identity or {}
    for column, key in (("lane", "cti.lane"), ("profile", "cti.profile"), ("seat", "cti.seat")):
        value = row.get(column)
        if isinstance(value, str) and value:
            attributes[key] = value
    issue = row.get("issue")
    if isinstance(issue, int) and not isinstance(issue, bool):
        attributes["cti.issue"] = issue
    return otel_event.Event(
        name=TERMINAL_EVENT,
        at=at,
        attributes=attributes,
        resource={"service.name": "arma-cti-terminal"},
    )


def emit_terminal(
    event: otel_event.Event,
    journal: Path,
    endpoint: str = "",
) -> bool:
    """Export one terminal-state event and journal it with its export's outcome.

    Fail-open as `emit_wait` is: the abandonment was a fact whatever a collector
    or a journal did, so a failure to record degrades to no record and never
    reaches the dispatch the record is about (#489). The journal lives beside the
    dispatch record it names, like `waits.jsonl` before it.
    """
    return otel_event.emit(event, journal=journal, endpoint=endpoint)
