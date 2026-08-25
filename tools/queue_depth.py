"""Sample the seven queues nothing else watches (#492).

An issue behind the WIP limit, a branch pushed and awaiting its reviewer, a
finding filed and unadjudicated — none of these appear anywhere unless
deliberately counted, and counting them is most of the job: queue depth is the
leading indicator where cycle time is the lagging one. This module is the
counter. **Where it runs is half the design**: the sampler folds into
`tools/queue_policy.py`'s `report` verb — the queue rung of `just watch-report`,
the read CLAUDE.md already puts at the top of every orchestrator turn — so it
adds no process, no recipe and no directory, and the reads it shares with that
rung (the policy, the in-flight derivation, the candidate list) are made once,
by the caller, and handed in.

**What an idle sample costs.** Every source is one small file, one directory
listing, or a read the same report invocation already made: the policy file,
the review waits journal, the review loop's journal (read once for each of the
reviewer and human-ruling queues), one listing of the review root with a stat
per historical issue directory, and — only per in-flight tree — the git reads
the landing queue needs. The dispatch waits journal is read only inside the
published peak band; the queue waits journal is not read by this sampler.
Nothing walks the dispatch records (the in-flight set arrives already derived),
nothing walks a review directory beyond the stats that say whether a loop is
still open, and an idle system samples seven empty queues for the price of
those bounded local reads. The tracker read is shared with the report's
underfill derivation when that read succeeds, including at full WIP; a refused
candidate read is recorded as `unrecorded`, never as a counted zero.

The review-root stat term grows linearly with historical numeric issue
directories, not dispatch-record count. It is small at the current 72-directory
shape on this box (~2 ms per sample), crosses ~10 ms at roughly 800 empty
directories, and is ~130 ms at 8,000; “nothing observable” is therefore a
current-scale observation, not an unbounded guarantee.

**Three facts, three renderings.** A counted depth — zero included — a queue
no record carries (`slot_lock`, whose bash seam journals nothing: the registry
row's own note), and a source this sample could not read are different facts,
and each renders differently (`counted`, `unrecorded`, `unreadable`). The same
discipline one level down: the oldest item's age is `measured` where a record
carries the entry instant, `none` where the queue is empty, and `unrecorded`
where items wait and nothing says since when — never an instant invented from
a file mtime (#485's concealed population and #490's borrowed clean past are
the two defects this trichotomy exists to not repeat). A queue missing from
the journal is a queue that was not sampled, which is why the sampler emits
one event per queue of the closed set, every sample, no exceptions.

**Entry instants, queue by queue.** `reviewer` ages from the exchange's own
`waiting_reviewer` wait; `human_ruling` from the round event that raised the
finding; `lane_window` from the peak-band wait the dispatcher journalled.
`ready_work` and `dispatch_slot` have no local entry record — the instant an
issue was labelled lives in the tracker's timeline, which no bounded read here
reaches — so their oldest is `unrecorded`. `landing`'s demand side (a tree
whose gated paths carry no approval) is recorded nowhere at the moment it
becomes true, so its oldest is `unrecorded` too. `slot_lock` has no source at
all. Which instants are recorded is data the samples carry, not a fact a
reader must take on trust.

Refs #492, #484, #485, #490, #238, ADR-0028.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

# tools/ holds standalone scripts rather than an importable package, so a sibling import
# needs the script's own directory on the path — the device every module here uses.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import attribute_registry
import breaker
import gated_paths
import queue_policy
import review_loop

# The dispatch surface's own waits journal name, mirrored rather than imported
# because `tools/dispatch.py` stands above the import graph this module sits in
# (`queue_policy`'s own mirror of `DISPATCH_ROOT` is the precedent).
DISPATCH_WAIT_JOURNAL: Final = "waits.jsonl"

# How long the one published peak band runs, derived from the breaker's own hour
# constants — never a second copy of the schedule — because the band this reads
# waits from must be the band the dispatcher refuses against (#238's one-home
# rule, `off_peak_refusal`'s own reasoning).
PEAK_BAND_HOURS: Final = breaker.ZAI_PEAK_END_HOUR - breaker.ZAI_PEAK_START_HOUR

# The review loop's two flat files under the review root: the loop events every
# family journals, and the waits the exchange journals (#484).
REVIEW_JOURNAL_NAME: Final = review_loop.JOURNAL.name
REVIEW_WAITS_NAME: Final = "waits.jsonl"

REVIEW_EVENTS: Final = frozenset(
    {
        review_loop.ROUND_EVENT,
        review_loop.ESCALATION_EVENT,
        review_loop.DISPUTE_EVENT,
        review_loop.TERMINUS_EVENT,
    }
)


class Sample(NamedTuple):
    """One queue's sample: depth state, optional refusal reason, and oldest-item age."""

    queue: str
    state: str
    count: int | None
    oldest: str
    oldest_age_s: float | None
    reason: str | None = None


class ReviewQueueRead(NamedTuple):
    """The one review-root read shared by queue depth and the terminus prompt.

    `unreadable` names each `loop.json` that would not read, review-root-relative,
    so one damaged loop is opened by name rather than counted; the prompts it
    stands beside are the loops that did read.
    """

    sample: Sample
    terminus: tuple[review_loop.TerminusPrompt, ...] | None
    unreadable: tuple[str, ...] = ()


def _journal_events(
    path: Path, wanted: frozenset[str]
) -> list[tuple[float, Mapping[str, object]]] | None:
    """Read one journal's events, or `None` where a present file cannot be read.

    An absent journal is empty, never unreadable: no waits were journalled is
    the counted zero the sampler exists to state, and only a file that exists
    and will not read is damage (#490's absent-journal lesson, applied to this
    reader before it could repeat it). A line that will not parse is skipped —
    the sampler is a periodic read, and one damaged line cannot hide the rest
    of the file behind it.
    """
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    except OSError:
        return None
    events: list[tuple[float, Mapping[str, object]]] = []
    for line in lines:
        try:
            document = json.loads(line)
        except ValueError:
            continue
        if not isinstance(document, dict):
            continue
        at = document.get("at")
        attributes = document.get("attributes")
        if document.get("event") not in wanted or not isinstance(at, (int, float)):
            continue
        if not isinstance(attributes, dict):
            continue
        events.append((float(at), attributes))
    return events


def _ready_sample(
    candidates: Sequence[queue_policy.Candidate] | None,
    in_flight: queue_policy.InFlight,
    candidate_refusal: queue_policy.Refusal | None,
) -> Sample:
    """Return the ready queue's sample: labelled work not in flight, by the label itself."""
    if candidate_refusal is not None:
        return Sample("ready_work", "unrecorded", None, "unrecorded", None, candidate_refusal.kind)
    if candidates is None:
        return Sample("ready_work", "unreadable", None, "unrecorded", None)
    waiting = [c for c in candidates if c.issue not in in_flight.issues]
    oldest = "unrecorded" if waiting else "none"
    return Sample("ready_work", "counted", len(waiting), oldest, None)


def _dispatch_slot_sample(
    policy: queue_policy.Policy,
    candidates: Sequence[queue_policy.Candidate] | None,
    in_flight: queue_policy.InFlight,
    candidate_refusal: queue_policy.Refusal | None,
) -> Sample:
    """Return work no slot is open to, measured by the rungs `select` refuses through.

    Ordinary eligibility is the same pre-WIP ladder `select` walks — not in flight,
    not held by the freeze, and not blocked on another issue — read through
    `queue_policy`'s own rung rather than a second copy. The slot term is the
    WIP rung itself, reservations included: a package holding slots open against
    a candidate is a reason there is no slot, so the candidates `wip_refusal`
    refuses belong in the depth exactly as a full list's do — the room
    subtraction this replaces approximated the rung rather than agreeing with
    it (#554). Eligible work beyond the room the limit leaves waits too — the
    batch cap `select` itself applies, which the per-candidate refusal, read
    against the current in-flight set, cannot state.
    """
    if candidate_refusal is not None:
        return Sample(
            "dispatch_slot", "unrecorded", None, "unrecorded", None, candidate_refusal.kind
        )
    if candidates is None:
        return Sample("dispatch_slot", "unreadable", None, "unrecorded", None)
    dispatchable = [
        c
        for c in candidates
        if queue_policy._drops(policy, c, in_flight) is None  # noqa: SLF001 — the rung is the definition; restating it here is the drift this module exists to not have
    ]
    eligible = [
        c for c in dispatchable if queue_policy.wip_refusal(policy, c.issue, in_flight) is None
    ]
    room = max(0, policy.wip_limit.value - len(in_flight.issues))
    held = (len(dispatchable) - len(eligible)) + max(0, len(eligible) - room)
    oldest = "unrecorded" if held else "none"
    return Sample("dispatch_slot", "counted", held, oldest, None)


def _reviewer_sample(review_root: Path, at: float) -> Sample:
    """Return the reviewer queue's sample: branches exchanged whose wait no review event answered.

    An exchange journals one `waiting_reviewer` wait at the moment the branch
    leaves the implementer's hands — the entry instant this queue ages from.
    The wait ends at the loop's next recorded act (a round, an escalation, a
    dispute, a terminus), so the newest wait per issue is live exactly where no
    later event names that issue.
    """
    waits = _journal_events(
        review_root / REVIEW_WAITS_NAME, frozenset({attribute_registry.WAIT_EVENT})
    )
    journal = _journal_events(review_root / REVIEW_JOURNAL_NAME, REVIEW_EVENTS)
    if waits is None or journal is None:
        return Sample("reviewer", "unreadable", None, "unrecorded", None)
    newest_wait: dict[int, float] = {}
    for wait_at, attributes in waits:
        if attributes.get("cti.wait.block_reason") != attribute_registry.REASON_WAITING_REVIEWER:
            continue
        issue = attributes.get("cti.issue")
        if not isinstance(issue, int) or isinstance(issue, bool):
            continue
        newest_wait[issue] = max(wait_at, newest_wait.get(issue, wait_at))
    answered: set[int] = set()
    for event_at, attributes in journal:
        issue = attributes.get("cti.issue")
        if not isinstance(issue, str) or not issue.isdecimal():
            continue
        number = int(issue)
        if number in newest_wait and event_at > newest_wait[number]:
            answered.add(number)
    waiting = {issue: wait for issue, wait in newest_wait.items() if issue not in answered}
    if not waiting:
        return Sample("reviewer", "counted", 0, "none", None)
    oldest = min(waiting.values())
    return Sample("reviewer", "counted", len(waiting), "measured", max(0.0, at - oldest))


def _round_times(review_root: Path) -> dict[tuple[int, int], float] | None:
    """Return the review journal's round events as an (issue, round) to instant map."""
    journal = _journal_events(
        review_root / REVIEW_JOURNAL_NAME, frozenset({review_loop.ROUND_EVENT})
    )
    if journal is None:
        return None
    rounds: dict[tuple[int, int], float] = {}
    for event_at, attributes in journal:
        issue = attributes.get("cti.issue")
        number = attributes.get("cti.review.round")
        if (
            isinstance(issue, str)
            and issue.isdecimal()
            and isinstance(number, int)
            and not isinstance(number, bool)
        ):
            rounds[(int(issue), number)] = event_at
    return rounds


def _open_loop(entry: Path) -> review_loop.Loop | None:
    """Read one issue directory's still-running loop, or `None` where there is none.

    `False` would not do for "a loop exists and will not read": that is damage
    the caller renders as unreadable, not the same thing as a closed loop or
    no loop at all — the exception is raised and the caller's ladder says
    which rung it landed on.
    """
    if (entry / review_loop.LANDING_FILE).is_file():
        return None
    loop_file = entry / review_loop.LOOP_FILE
    if not loop_file.is_file():
        return None
    return review_loop.parse_loop(json.loads(loop_file.read_text(encoding="utf-8")))


def _review_loop_entry(entry: Path) -> tuple[int, review_loop.Loop] | None:
    """Return one numeric, non-terminal loop entry, or skip this directory."""
    if not entry.is_dir() or not entry.name.isdecimal():
        return None
    loop = _open_loop(entry)
    if loop is None:
        return None
    return int(entry.name), loop


def _update_human_ruling_age(
    issue: int,
    loop: review_loop.Loop,
    rounds: dict[tuple[int, int], float],
    depth: int,
    oldest_at: float | None,
) -> tuple[int, float | None]:
    """Add one loop's open findings to the depth and oldest-entry reduction."""
    for finding in review_loop.open_above_low(loop):
        depth += 1
        raised = rounds.get((issue, finding.round_raised))
        if raised is not None and (oldest_at is None or raised < oldest_at):
            oldest_at = raised
    return depth, oldest_at


def _human_ruling_read(review_root: Path, at: float) -> ReviewQueueRead:
    """Read the human-ruling queue and terminus prompts in one review-root walk.

    A loop is running while its directory holds `loop.json` and not
    `landing.json` — the terminus's own terminal state, structural by rename.
    The depth is the open above-low set (the loop's own unadjudicated
    vocabulary, low findings never having blocked); the age is the round event
    that raised the oldest such finding, and `unrecorded` where the journal
    predates the finding's round. A rounds journal that will not read renders
    the sample unreadable rather than degrading every age to `unrecorded` — a
    failed source is not an absent record (#554). One stat per historical
    issue directory is the whole cost, a loop read only where its stat says it
    is still open. A `loop.json` that will not read is named and the walk
    carries on, so one damaged loop suppresses no other loop's prompt.

    The read is fail-open end to end, as `sample()`'s docstring promises:
    `sample()` computes it above its own per-queue catch, so whatever escapes
    the walk's ladders is caught here — the sample renders unreadable and the
    terminus absent, and the other six queues still sample (#567).
    """
    try:
        return _human_ruling_walk(review_root, at)
    except Exception:  # noqa: BLE001 — sample()'s every-queue promise, held here because the reading is computed outside its per-queue catch
        return ReviewQueueRead(Sample("human_ruling", "unreadable", None, "unrecorded", None), None)


def _human_ruling_walk(review_root: Path, at: float) -> ReviewQueueRead:
    """Walk the review root's numeric issue directories; damage is named, never fatal."""
    try:
        # Numeric issue order: directory names are issue numbers, and
        # lexicographic order puts "1000" before "999" the first time an
        # issue crosses a width boundary (#567). Non-decimal entries are
        # skipped by `_review_loop_entry` either way; dropping them here
        # only keeps the key single-typed.
        entries = sorted(
            (entry for entry in review_root.iterdir() if entry.name.isdecimal()),
            key=lambda entry: int(entry.name),
        )
    except OSError:
        return ReviewQueueRead(Sample("human_ruling", "unreadable", None, "unrecorded", None), None)
    rounds = _round_times(review_root)
    depth = 0
    oldest_at: float | None = None
    prompts: list[review_loop.TerminusPrompt] = []
    unreadable: list[str] = []
    for entry in entries:
        try:
            identified = _review_loop_entry(entry)
        except (OSError, ValueError):
            # One damaged loop names itself and the walk carries on: collapsing
            # the population to the failure is #556's shape, absence rendered as
            # the whole read. A depth over a partly-read population is still not
            # a number, so the sample states unreadable while the prompts it
            # stands beside remain the loops that did read.
            unreadable.append(f"{entry.name}/{review_loop.LOOP_FILE}")
            continue
        if identified is None:
            continue
        issue, loop = identified
        prompt = review_loop.terminus_prompt(
            issue, loop, pending=(entry / review_loop.PENDING_FILE).exists()
        )
        prompts.append(prompt)
        if rounds is not None:
            depth, oldest_at = _update_human_ruling_age(issue, loop, rounds, depth, oldest_at)
    if unreadable or rounds is None:
        # `rounds is None` is the journal unreadable, and `or {}` here is what
        # rendered that failure as `unrecorded` ages — the absence-and-failure
        # collapse this module's own vocabulary exists to prevent. The depth
        # over the loops that did read is still not a number beside a failed
        # age source, so the sample states unreadable while the prompts remain
        # the loops that read.
        return ReviewQueueRead(
            Sample("human_ruling", "unreadable", None, "unrecorded", None),
            tuple(prompts),
            tuple(unreadable),
        )
    if not depth:
        sample = Sample("human_ruling", "counted", 0, "none", None)
        return ReviewQueueRead(sample, tuple(prompts))
    if oldest_at is None:
        sample = Sample("human_ruling", "counted", depth, "unrecorded", None)
        return ReviewQueueRead(sample, tuple(prompts))
    sample = Sample("human_ruling", "counted", depth, "measured", max(0.0, at - oldest_at))
    return ReviewQueueRead(sample, tuple(prompts))


def _human_ruling_sample(review_root: Path, at: float) -> Sample:
    """Return only the human-ruling sample for callers that do not render prompts."""
    return _human_ruling_read(review_root, at).sample


def render_terminus_prompts(
    prompts: tuple[review_loop.TerminusPrompt, ...] | None,
    unreadable: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Render the separate terminus closeout's mechanical turn-top prompts.

    A damaged `loop.json` is named in its own `unreadable` line beside the
    prompts for the loops that were read — a count would say something is wrong
    without saying which file to open (#556). The two `unreadable` actions
    distrust different amounts, and the wording is the only thing that says
    which: the root-level line distrusts the whole read, the per-file line
    distrusts one loop and leaves the prompts beside it standing (#567).
    """
    if prompts is None:
        return (
            (
                "review_terminus=unreadable "
                'action="repair review state before relying on closeout prompt"'
            ),
        )
    lines: list[str] = []
    for prompt in prompts:
        if prompt.incomplete:
            status = "incomplete"
            action = "account for pending posts before retrying"
        elif prompt.open_above_low:
            status = "blocked"
            action = "adjudicate or escalate before terminus"
        else:
            status = "due"
            action = f"just review-loop terminus --issue {prompt.issue}"
        rendered_action = f'"{action}"'
        lines.append(
            f"review_terminus={status} issue={prompt.issue} findings={prompt.findings}"
            f" open_above_low={prompt.open_above_low} action={rendered_action}"
        )
    lines.extend(
        f"review_terminus=unreadable path={name} "
        'action="repair this loop before relying on its closeout prompt"'
        for name in unreadable
    )
    return tuple(lines)


def _lane_window_sample(
    dispatch_dir: Path,
    candidates: Sequence[queue_policy.Candidate] | None,
    at: float,
    candidate_refusal: queue_policy.Refusal | None,
) -> Sample:
    """Return the lane-window queue's sample: work a published peak band holds (#238).

    The band is the breaker's own schedule, read by its own functions — open,
    and nothing can be waiting on it (depth zero); closed, and the depth is the
    issues the dispatcher journalled a peak-band wait for since the band began
    that are still candidates, because an issue no longer labelled ready moved
    on rather than waited. A refused issue routed elsewhere mid-band stays
    counted — the waits name what wanted this lane, which is the honest
    membership a journal of waits can state, and the waits carry their own
    instants.
    """
    if not breaker.zai_is_peak(at):
        return Sample("lane_window", "counted", 0, "none", None)
    waits = _journal_events(
        dispatch_dir / DISPATCH_WAIT_JOURNAL, frozenset({attribute_registry.WAIT_EVENT})
    )
    if waits is None:
        return Sample("lane_window", "unreadable", None, "unrecorded", None)
    if candidate_refusal is not None:
        return Sample("lane_window", "unrecorded", None, "unrecorded", None, candidate_refusal.kind)
    if candidates is None:
        return Sample("lane_window", "unreadable", None, "unrecorded", None)
    band_start = (
        breaker.zai_off_peak_opens_at(at) - timedelta(hours=PEAK_BAND_HOURS).total_seconds()
    )
    ready = {c.issue for c in candidates}
    waiting: dict[int, float] = {}
    for wait_at, attributes in waits:
        if attributes.get("cti.wait.block_reason") != attribute_registry.REASON_LANE_PEAK_BAND:
            continue
        if wait_at < band_start:
            continue
        issue = attributes.get("cti.issue")
        if not isinstance(issue, int) or isinstance(issue, bool) or issue not in ready:
            continue
        waiting[issue] = max(wait_at, waiting.get(issue, wait_at))
    if not waiting:
        return Sample("lane_window", "counted", 0, "none", None)
    oldest = min(waiting.values())
    return Sample("lane_window", "counted", len(waiting), "measured", max(0.0, at - oldest))


def _slot_lock_sample() -> Sample:
    """Return the slot-lock queue's sample: no source, stated as that rather than as zero.

    The tier's no-slot stop lives in bash, and ADR-0049's migration seam does
    not journal it — `BLOCK_REASONS`' own `slot_unavailable` note says so. A
    depth of zero here would be #490's borrowed clean past one queue over: the
    honest sample says no record carries this queue's membership at all.
    """
    return Sample("slot_lock", "unrecorded", None, "unrecorded", None)


def _landing_sample(in_flight: queue_policy.InFlight, approvals: Path) -> Sample:
    """Return the landing queue's sample: in-flight work whose gated paths carry no authorisation.

    The same rungs `just gated-paths check` walks — the changed paths, the
    sign-off gate, the delegated-decision marker, the content-bound approval —
    read through `gated_paths`' own functions, never restated. An issue waits
    here where any gated path it touches holds neither a covering approval
    record nor ADR-0013's marker; the instant that became true is recorded
    nowhere, so the oldest is `unrecorded`. The cost is bounded by the
    in-flight set, not by history: an idle system reads nothing at all for
    this queue.
    """
    waiting = 0
    unreadable = False
    for holder in in_flight.holders:
        if holder.worktree is None:
            continue
        try:
            paths = gated_paths.changed_paths(holder.worktree)
            delegated = set(gated_paths.delegated_decisions(holder.worktree, paths))
        except (gated_paths.GitError, OSError):
            unreadable = True
            continue
        for path in paths:
            if path in delegated or gated_paths.signoff_gate(path) is None:
                continue
            try:
                content_id = gated_paths.content_id_of(holder.worktree, path)
            except (gated_paths.GitError, OSError):
                unreadable = True
                continue
            if not gated_paths.approval_path(approvals, holder.issue, content_id).is_file():
                waiting += 1
                break
    if unreadable:
        return Sample("landing", "unreadable", None, "unrecorded", None)
    if not waiting:
        return Sample("landing", "counted", 0, "none", None)
    return Sample("landing", "counted", waiting, "unrecorded", None)


def sample(  # noqa: PLR0913 — the parameters are the report verb's own reads handed in once, plus the roots the queues live under
    store: queue_policy.Store,
    policy: queue_policy.Policy,
    in_flight: queue_policy.InFlight,
    candidates: Sequence[queue_policy.Candidate] | None,
    *,
    candidate_refusal: queue_policy.Refusal | None = None,
    dispatch_dir: Path,
    review_root: Path | None = None,
    approvals: Path | None = None,
    at: float | None = None,
    terminus_lines: list[str] | None = None,
) -> tuple[Sample, ...]:
    """Sample every queue of the closed set once, fail-open, and journal each sample.

    One event per queue, every queue, no exceptions: the sampler's own silence
    is the difference between "sampled and empty" and "not sampled" that the
    journal must never blur. A queue whose read raised the unexpected is
    journalled `unreadable` rather than dropped — a periodic read must survive
    damage, and the damage must be visible where it landed. Returns the samples
    in the registry's own queue order, for the caller that wants them without
    re-reading the journal. `review_root` defaults to `review_loop`'s own
    `CTI_REVIEW_DIR` seam, read here at call time.
    """
    now = datetime.now(tz=UTC).timestamp() if at is None else at
    reviews = review_loop.review_root() if review_root is None else review_root
    approval_root = gated_paths.APPROVAL_ROOT if approvals is None else approvals
    review_read = _human_ruling_read(reviews, now)
    if terminus_lines is not None:
        terminus_lines.extend(render_terminus_prompts(review_read.terminus, review_read.unreadable))
    readings = {
        "ready_work": lambda: _ready_sample(candidates, in_flight, candidate_refusal),
        "dispatch_slot": lambda: _dispatch_slot_sample(
            policy, candidates, in_flight, candidate_refusal
        ),
        "reviewer": lambda: _reviewer_sample(reviews, now),
        "human_ruling": lambda: review_read.sample,
        "lane_window": lambda: _lane_window_sample(
            dispatch_dir, candidates, now, candidate_refusal
        ),
        "slot_lock": _slot_lock_sample,
        "landing": lambda: _landing_sample(in_flight, approval_root),
    }
    samples: list[Sample] = []
    for queue in attribute_registry.QUEUES:
        try:
            reading = readings[queue]()
        except Exception:  # noqa: BLE001 — a periodic read must not die on one queue's damage; the catch renders that queue unreadable, visibly, never silently empty
            reading = Sample(queue, "unreadable", None, "unrecorded", None)
        samples.append(reading)
        attribute_registry.emit_queue_depth(
            attribute_registry.queue_depth_event(
                reading.queue,
                reading.state,
                now,
                count=reading.count,
                oldest=reading.oldest,
                oldest_age_s=reading.oldest_age_s,
                reason=reading.reason,
            ),
            journal=store.directory / attribute_registry.QUEUE_DEPTH_JOURNAL,
            endpoint=store.endpoint,
        )
    return tuple(samples)
