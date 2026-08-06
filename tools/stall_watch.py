"""Decide whether a dispatched agent has parked on a finished run (#198, ADR-0049).

Six stalls in one cycle, six caught by an orchestrator watching by hand (#168
x2, #159, #162, #149 x2), and ADR-0053 ruled the defect underneath — a parked
run's completion does not wake the agent that parked it — Claude Code harness
behaviour rather than this repo's to fix. So the watcher is permanent
compensation, and #195 measured what the hand version costs: an agent turn that
blocks past five minutes loses the prompt cache and pays ~179,000 tokens to
rebuild it, making a *waiting* turn about 110x a working one. `sleep` and
`until` poll loops are 4.24% of everything this project has ever been billed.

The rule that follows, from `docs/research/token-efficiency.md` section 3:

    Work that takes longer than the cache lives belongs outside an agent's
    turn. An orchestrator should be notified that something finished; it
    should not sit inside a turn watching for it.

This module is the deciding half. `tools/stall-watch.sh` is the process seam —
detaching, polling, and running `git` — and hands its readings here as flags,
the split ADR-0049 draws and `probe_verdict.py` already follows.

The predicate, from #198's first criterion, is three conjuncts:

1. **The run's completion artefact exists** — `pool.json` or `verdict.json`
   written under the runs directory since the watch was armed, or the watched
   process is gone, or the awaited path appeared.
2. **No report has arrived within a stated grace window.** Nothing outside the
   harness can observe a report, so what is observed is the agent *acting*:
   any mtime under its worktree moving. Unobservable is treated as no activity,
   never as life — recovery.md's fail-closed rule, earned three times (#41's
   bare `tasklist.exe`, #44's self-agreeing daemon default, the `pgrep -f` that
   matched the orchestrator's own command line). The cost of being wrong is one
   briefing, not work: recovery starts from commits.
3. **The agent's worktree HEAD has not moved since the completion edge.** Not
   since arming: #168's agent had committed its fix (`e24e25d`) *before*
   launching the run it then parked on, so a baseline taken at dispatch would
   have read that stall — twice in one evening, at the identical point — as an
   agent who had already read its own result.

The escalation then splits on what the stall is sitting on, the sharper edge
recovery.md's thirteenth use records: a stall on a **clean** tree risks a
dispatch, a stall on **uncommitted work** risks the work — #149 sat 90 minutes
on five uncommitted addon files. `stalled_dirty` says so, and names the files.

Two things this tool deliberately does not do. It never messages an agent:
prodding is a judgement about a person's work, and the watcher's job ends at
putting the facts where the next orchestrator turn reads them. And it never
retries an `infra_unavailable` run — the failure-class table says that is a
stop, not a result, so the finding reports it and stands down.

The finding lands as a file under `~/.arma-cti/watch/`, not in the harness's
session-task mechanism, for three reasons: it must outlive the worktree it is
about and the orchestrator session that armed it (both die routinely — four
orchestrator deaths in one window, ADR-0022); the task mechanism would put the
watcher back inside a turn, which is the cost this exists to remove; and a file
beside `~/.arma-cti/runs/` is where this project already keeps evidence that
outlives its run.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final, NamedTuple

# tools/ holds standalone scripts rather than an importable package, so a
# sibling import needs the script's own directory on the path — the device
# `push_path_report.py` uses to reach `telemetry_log.py`.
sys.path.insert(0, str(Path(__file__).parent))

# `merged_from_pool` reads the document `pool_merge` itself writes, and lives
# there for that reason (#199): the block a prod quotes stays byte-for-byte the
# block the runner printed (#198 criterion 2), and one schema keeps one reader.
from pool_merge import MergedPool, ProbeRow, merged_from_pool, render_summary

# Outside every worktree, beside the tier's own evidence, for the reason in the
# module docstring: a finding must outlive the worktree it describes.
DEFAULT_WATCH_DIR: Final = Path.home() / ".arma-cti" / "watch"
DEFAULT_RUNS_DIR: Final = Path.home() / ".arma-cti" / "runs"

# How long a watch runs before it gives up on ever seeing its subject finish,
# and how long after a completion edge silence becomes a stall. The grace is
# deliberately longer than a turn: an agent that finished a corpus has verdicts
# to read and a landing to do, and 10 minutes of that is work, not a stall.
DEFAULT_GRACE_SECS: Final = 600
DEFAULT_DEADLINE_SECS: Final = 14400

WATCHING: Final = "watching"
SETTLING: Final = "settling"
STALLED_CLEAN: Final = "stalled_clean"
STALLED_DIRTY: Final = "stalled_dirty"
AGENT_MOVED: Final = "agent_moved"
WATCH_BLIND: Final = "watch_blind"
WATCH_EXPIRED: Final = "watch_expired"
WATCH_BROKEN: Final = "watch_broken"

# A terminal state is one the polling loop stops on: the answer will not
# improve by looking again, and a watcher that kept looking would be the poll
# loop this replaces, merely relocated.
TERMINAL: Final[frozenset[str]] = frozenset(
    {STALLED_CLEAN, STALLED_DIRTY, AGENT_MOVED, WATCH_BLIND, WATCH_EXPIRED, WATCH_BROKEN}
)

# What each terminal state is called on the one line the orchestrator reads.
BANNER: Final[dict[str, str]] = {
    STALLED_CLEAN: "STALL",
    STALLED_DIRTY: "STALL",
    AGENT_MOVED: "DONE",
    WATCH_BLIND: "BLIND",
    WATCH_EXPIRED: "EXPIRED",
    WATCH_BROKEN: "BROKEN",
}

SECS_PER_MIN: Final = 60
SECS_PER_HOUR: Final = 3600
# How many uncommitted paths the one line names before it stops listing them.
DIRTY_NAMES_SHOWN: Final = 5


def issue_ref(issue: str) -> str:
    """Normalise an issue to `#N`, accepting the bare number.

    A `just` recipe body is shell, where `#` opens a comment and swallows the
    rest of the line — so `--issue 198` has to be the spelling that works, and
    the hash is put back here rather than at four call sites.
    """
    stripped = issue.strip().lstrip("#")
    return f"#{stripped}" if stripped.isdigit() else issue.strip()


def slug(name: str) -> str:
    """Reduce a watch's name to what a filename may hold."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-.")
    return cleaned.lower() or "watch"


def human_secs(seconds: int) -> str:
    """Say a duration the way a human reading one line wants it."""
    if seconds < SECS_PER_MIN:
        return f"{seconds}s"
    if seconds < SECS_PER_HOUR:
        return f"{seconds // SECS_PER_MIN}m"
    return f"{seconds // SECS_PER_HOUR}h{(seconds % SECS_PER_HOUR) // SECS_PER_MIN:02d}m"


@dataclass(frozen=True)
class Spec:
    """What the orchestrator knew when it armed the watch."""

    name: str
    worktree: str
    baseline_head: str
    armed_at: int
    subject: str = "pool"
    runs_dir: str = str(DEFAULT_RUNS_DIR)
    grace_secs: int = DEFAULT_GRACE_SECS
    deadline_secs: int = DEFAULT_DEADLINE_SECS
    await_path: str = ""
    pid: int = 0
    issue: str = ""

    @classmethod
    def from_document(cls, document: dict[str, object]) -> Spec:
        """Read a spec back off disk, defaulting every field the file omits."""
        fields = {key: document[key] for key in cls.__dataclass_fields__ if key in document}
        return cls(**fields)  # type: ignore[arg-type]

    def as_document(self) -> dict[str, object]:
        """Render the spec as the JSON the watcher's loop reads back each pass."""
        return {key: getattr(self, key) for key in self.__dataclass_fields__}


@dataclass(frozen=True)
class Observation:
    """One pass of readings the shell took of the agent and its worktree.

    `process_alive` is a tri-state string rather than a bool because "the
    watcher could not tell" is a third answer that must not collapse into
    either — the shape #41 and #44 were both caught by.
    """

    now: int
    head: str
    dirty: tuple[str, ...] = ()
    activity_epoch: int = 0
    process_alive: str = "unknown"


class Completion(NamedTuple):
    """The completion edge the watch was waiting for, once it lands."""

    kind: str
    path: str
    finished_at: int
    class_: str = ""
    tally: str = ""
    wall_secs: int = 0
    git_sha: str = ""
    summary: tuple[str, ...] = ()

    def phrase(self) -> str:
        """Say the verdict in the words the prod will quote."""
        parts = [part for part in (self.class_ and f"worst={self.class_}", self.tally) if part]
        if self.wall_secs:
            parts.append(f"{self.wall_secs}s")
        if self.git_sha:
            parts.append(f"sha {self.git_sha[:12]}")
        return ", ".join(parts)

    def descriptor(self) -> str:
        """Name the edge on the one line: a verdict where there is one, a path otherwise.

        A watched process's exit and a flag file's appearance carry no class,
        no tally and no SHA — saying "worst=" of them would be a verdict this
        watcher never read.
        """
        return f"{self.phrase()} evidence={self.path}" if self.class_ else self.path


class Finding(NamedTuple):
    """What one assessment concluded, and the line the orchestrator reads."""

    state: str
    terminal: bool
    quiet_secs: int
    headline: str
    prod: str
    completion: Completion | None


def read_document(path: Path) -> dict[str, object]:
    """Read one JSON object, answering an empty one for anything unreadable.

    Unreadable is data here rather than an error: a `pool.json` half-written by
    a dying run is exactly the case a watcher exists to notice, and it must not
    take the watcher down with it.
    """
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return document if isinstance(document, dict) else {}


def _newest_artefact(runs_dir: Path, pattern: str, filename: str, not_before: int) -> Path | None:
    """Find the newest completion artefact written since the watch was armed.

    Older evidence is skipped rather than reported: a pool that finished before
    this agent was dispatched is another run's result, and quoting it at the
    orchestrator would be the quote-before-read hole in reverse.
    """
    best: Path | None = None
    best_mtime = 0.0
    for candidate in runs_dir.glob(pattern):
        artefact = candidate / filename
        try:
            mtime = artefact.stat().st_mtime
        except OSError:
            continue
        if mtime < not_before or mtime <= best_mtime:
            continue
        best, best_mtime = artefact, mtime
    return best


def pool_completion(artefact: Path) -> Completion:
    """Read a finished pool into the payload a prod quotes."""
    document = read_document(artefact)
    merged = merged_from_pool(document)
    passes = sum(1 for row in merged.rows if row.class_ == "pass")
    slots = document.get("slots")
    summary = render_summary(
        merged,
        started_at=str(document.get("started_at", "")),
        git_sha=str(document.get("git_sha", "")),
        slot_count=len(slots) if isinstance(slots, list) else 0,
    )
    return Completion(
        kind="pool",
        path=str(artefact.parent),
        finished_at=int(artefact.stat().st_mtime),
        class_=merged.worst_class or "untyped_harness_failure",
        tally=f"{passes}/{len(merged.rows)} pass" if merged.rows else "no verdicts",
        wall_secs=int(document.get("wall_secs", 0) or 0),
        git_sha=str(document.get("git_sha", "")),
        summary=tuple(line for line in summary if line),
    )


def probe_completion(artefact: Path) -> Completion:
    """Read one finished probe into the same payload shape a pool gives."""
    document = read_document(artefact)
    class_ = str(document.get("class", "")) or "untyped_harness_failure"
    row = ProbeRow(
        str(document.get("probe", artefact.parent.name)),
        class_,
        str(document.get("slot", "?")),
        int(document.get("elapsed_secs", 0) or 0),
        str(document.get("evidence", artefact.parent)),
    )
    merged = MergedPool([row], [], [], [], class_)
    summary = render_summary(
        merged,
        started_at=str(document.get("started_at", "")),
        git_sha=str(document.get("git_sha", "")),
        slot_count=1,
    )
    return Completion(
        kind="probe",
        path=str(artefact.parent),
        finished_at=int(artefact.stat().st_mtime),
        class_=class_,
        tally="1/1 pass" if class_ == "pass" else "0/1 pass",
        wall_secs=row.elapsed_secs,
        git_sha=str(document.get("git_sha", "")),
        summary=tuple(line for line in summary if line),
    )


def find_completion(
    spec: Spec, observation: Observation, previous: dict[str, object]
) -> Completion | None:
    """Answer whether the subject this watch was armed over has finished.

    A process's exit and a path's appearance carry no verdict, so the moment
    they were first seen is kept in the previous finding: the loop that sees a
    pid gone at 12:01 must still say "quiet 11 minutes" at 12:12, not "quiet
    zero" forever.
    """
    runs_dir = Path(spec.runs_dir)
    if spec.subject == "pool":
        artefact = _newest_artefact(runs_dir, "*-pool", "pool.json", spec.armed_at)
        return pool_completion(artefact) if artefact else None
    if spec.subject.startswith("probe:"):
        probe = spec.subject.partition(":")[2]
        artefact = _newest_artefact(runs_dir, f"*-{probe}", "verdict.json", spec.armed_at)
        return probe_completion(artefact) if artefact else None
    if spec.subject == "process" and observation.process_alive == "false":
        first_seen = int(previous.get("completed_at", 0) or 0) or observation.now
        return Completion(kind="process", path=f"pid {spec.pid}", finished_at=first_seen)
    if spec.subject == "path" and Path(spec.await_path).exists():
        awaited = Path(spec.await_path)
        return Completion(kind="path", path=str(awaited), finished_at=int(awaited.stat().st_mtime))
    return None


def _prod_without_verdict(spec: Spec, observation: Observation, state: str) -> str:
    """Say what to do in the three states that carry no run to quote."""
    if state == AGENT_MOVED:
        return f"none — HEAD moved to {observation.head[:12]} after the edge; the agent read it"
    if state == WATCH_BLIND:
        return (
            f"none — the watcher could not read HEAD in {spec.worktree}; "
            f'"could not observe" is not "still running" (recovery.md). Look by hand'
        )
    return (
        f"none yet — no {spec.subject} artefact under {spec.runs_dir} within "
        f"{human_secs(spec.deadline_secs)} of arming; the run may never have started"
    )


def _prod_text(spec: Spec, observation: Observation, state: str, done: Completion | None) -> str:
    """Draft what the orchestrator's prod should say — never what it should decide.

    The wording is a draft for a human-or-orchestrator judgement, which is why
    the tool writes it down instead of sending it (ADR-0053: prodding is the
    judgement; noticing is the machine's).
    """
    if state in {AGENT_MOVED, WATCH_BLIND, WATCH_EXPIRED}:
        return _prod_without_verdict(spec, observation, state)
    if done is None:
        return ""
    if done.class_ == "infra_unavailable":
        return (
            f"STOP — {spec.subject} typed infra_unavailable ({done.path}): not a result, "
            f"do not interpret and do not retry. Re-dispatch is a judgement, not this watcher's"
        )
    finished = (
        f"your {done.kind} finished {done.phrase()}"
        if done.class_
        else f"the {done.kind} you were waiting on finished ({done.path})"
    )
    # A run has verdicts to read before landing; a bare process or flag file
    # has only the work the agent left off.
    next_step = f"read {done.path} and land" if done.class_ else "pick the work back up"
    if state == STALLED_DIRTY:
        shown = ", ".join(observation.dirty[:DIRTY_NAMES_SHOWN])
        more = (
            f" (+{len(observation.dirty) - DIRTY_NAMES_SHOWN} more)"
            if (len(observation.dirty) > DIRTY_NAMES_SHOWN)
            else ""
        )
        return (
            f"{finished}; {len(observation.dirty)} path(s) uncommitted in {spec.worktree} "
            f"— {shown}{more} — and uncommitted work dies with the worktree (#149 sat 90 "
            f"minutes on five addon files). Commit first, then {next_step}"
        )
    return (
        f"{finished}; {next_step}. HEAD {observation.head[:12]} is committed, "
        f"so nothing of yours is at risk — this is a lost dispatch, not lost work"
    )


def _headline(
    spec: Spec, observation: Observation, state: str, quiet: int, done: Completion | None
) -> str:
    """Compose #198's one line: who stalled, what evidence, what the prod says."""
    banner = BANNER.get(state, state.upper())
    tree = f"dirty({len(observation.dirty)})" if observation.dirty else "clean"
    subject = f"{done.kind} {done.descriptor()}" if done else f"{spec.subject} — no artefact"
    issue = f" {spec.issue}" if spec.issue else ""
    head = observation.head[:12] or "?"
    prod = _prod_text(spec, observation, state, done)
    return (
        f"{banner} {spec.name}{issue} quiet {human_secs(quiet)} past {subject} "
        f"tree={tree}@{head} prod: {prod}"
    )


def assess(spec: Spec, observation: Observation, previous: dict[str, object]) -> Finding:
    """Apply the module docstring's three-conjunct predicate to one pass."""
    if not observation.head:
        return Finding(
            WATCH_BLIND,
            terminal=True,
            quiet_secs=observation.now - spec.armed_at,
            headline=_headline(
                spec, observation, WATCH_BLIND, observation.now - spec.armed_at, None
            ),
            prod=_prod_text(spec, observation, WATCH_BLIND, None),
            completion=None,
        )

    done = find_completion(spec, observation, previous)
    # The third conjunct is measured from the completion edge, not from
    # arming. #168's agent had *committed* its fix before launching the run it
    # then parked on — `e24e25d`, sitting on no branch, unlanded and
    # unannounced — so "HEAD has moved since dispatch" would have read that
    # stall as an agent who had read its own run. An empty value means this is
    # the first pass since the edge landed, where nothing can say whether the
    # move came before it or after: that pass settles rather than guessing.
    edge_head = str(previous.get("head_at_edge", "") or "")
    if done is None:
        state = WATCH_EXPIRED if observation.now - spec.armed_at >= spec.deadline_secs else WATCHING
        quiet = observation.now - max(spec.armed_at, observation.activity_epoch)
    elif edge_head and observation.head != edge_head:
        state, quiet = AGENT_MOVED, 0
    elif not edge_head and observation.head != spec.baseline_head:
        # A move this watch cannot place: HEAD is past the dispatch baseline
        # and the edge only landed now, so the commit could be #168's (before
        # the run) or the agent reading its own result (after it). One more
        # window and the next pass can tell, at the cost of one interval.
        state = SETTLING
        quiet = observation.now - max(done.finished_at, observation.activity_epoch)
    else:
        # The quiet clock starts at the later of the completion edge and the
        # last thing the agent was seen to do: an agent still editing after its
        # run finished is working, and calling that a stall would prod someone
        # mid-sentence.
        quiet = observation.now - max(done.finished_at, observation.activity_epoch)
        if quiet < spec.grace_secs:
            state = SETTLING
        else:
            state = STALLED_DIRTY if observation.dirty else STALLED_CLEAN
        if state == SETTLING and observation.now - spec.armed_at >= spec.deadline_secs:
            state = WATCH_EXPIRED

    return Finding(
        state,
        terminal=state in TERMINAL,
        quiet_secs=max(quiet, 0),
        headline=_headline(spec, observation, state, max(quiet, 0), done),
        prod=_prod_text(spec, observation, state, done),
        completion=done,
    )


def finding_document(
    spec: Spec, observation: Observation, finding: Finding, previous: dict[str, object]
) -> dict[str, object]:
    """Render the finding as the file the next orchestrator turn reads."""
    done = finding.completion
    return {
        "name": spec.name,
        "issue": spec.issue,
        "state": finding.state,
        "terminal": finding.terminal,
        "headline": finding.headline,
        "prod": finding.prod,
        "worktree": spec.worktree,
        "baseline_head": spec.baseline_head,
        "head": observation.head,
        # The HEAD this watch first saw once its subject had finished, which is
        # what the next pass's move is measured against.
        "head_at_edge": observation.head if done else str(previous.get("head_at_edge", "") or ""),
        "dirty": list(observation.dirty),
        "quiet_secs": finding.quiet_secs,
        "assessed_at": observation.now,
        "completed_at": done.finished_at if done else 0,
        "run_class": done.class_ if done else "",
        "evidence": done.path if done else "",
        "summary": list(done.summary) if done else [],
        # Carried, never re-stamped: a finding the orchestrator has already read
        # must not resurface on the next pass as if it were new.
        "acknowledged_at": int(previous.get("acknowledged_at", 0) or 0),
    }


def write_json(path: Path, document: dict[str, object]) -> None:
    """Write one JSON document, creating the watch directory on first use."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def emit(pairs: tuple[tuple[str, object], ...]) -> None:
    """Print the `key=value` lines the shell acts on — the tier's own format."""
    for key, value in pairs:
        print(f"{key}={value}")  # noqa: T201 — the shell reads these lines


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Five verbs: arm a watch, read its spec, assess it, report, acknowledge."""
    parser = argparse.ArgumentParser(description=__doc__)
    # `CTI_WATCH_DIR` is `CTI_BREAKER_DIR`'s twin, and exists for the same reason
    # (#249, the seam principle of ADR-0049). `just watch-report` folds two reads into
    # one recipe and forwards its arguments to the watchers' half only, so a caller
    # that wants the breaker half pointed elsewhere has no flag to pass — and the
    # unit test of that recipe injected the breaker directory alone, leaving the
    # watch read on the box's live `~/.arma-cti/watch/`. Any unacknowledged finding
    # there then reddened every landing's gate, whatever the diff under test.
    parser.add_argument(
        "--watch-dir",
        type=Path,
        default=Path(os.environ.get("CTI_WATCH_DIR", str(DEFAULT_WATCH_DIR))),
    )
    parser.add_argument("--now", type=int, default=0)
    verbs = parser.add_subparsers(dest="verb", required=True)

    arm = verbs.add_parser("arm", help="record what a dispatch knew")
    arm.add_argument("--name", required=True)
    arm.add_argument("--worktree", required=True)
    arm.add_argument("--baseline-head", required=True)
    arm.add_argument("--subject", default="pool")
    arm.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    arm.add_argument("--grace", type=int, default=DEFAULT_GRACE_SECS)
    arm.add_argument("--deadline", type=int, default=DEFAULT_DEADLINE_SECS)
    arm.add_argument("--await-path", default="")
    arm.add_argument("--pid", type=int, default=0)
    arm.add_argument("--issue", default="")

    spec_env = verbs.add_parser("spec-env", help="the spec as key=value for the shell")
    spec_env.add_argument("--name", required=True)

    check = verbs.add_parser("assess", help="one pass over the readings the shell took")
    check.add_argument("--name", required=True)
    check.add_argument("--head", default="")
    check.add_argument("--porcelain-file", type=Path, default=None)
    check.add_argument("--activity-epoch", type=int, default=0)
    check.add_argument("--process-alive", default="unknown", choices=("true", "false", "unknown"))

    report = verbs.add_parser("report", help="what the watchers found, one line each")
    report.add_argument("--ack", action="store_true", help="mark what is printed as read")
    report.add_argument("--all", action="store_true", help="include already-read findings")

    ack = verbs.add_parser("ack", help="mark one finding read")
    ack.add_argument("--name", required=True)
    return parser.parse_args(argv)


def spec_path(watch_dir: Path, name: str) -> Path:
    """Where one watch keeps what its dispatch knew."""
    return watch_dir / f"{slug(name)}.spec.json"


def finding_path(watch_dir: Path, name: str) -> Path:
    """Where one watch keeps what it has concluded."""
    return watch_dir / f"{slug(name)}.finding.json"


def read_porcelain(path: Path | None) -> tuple[str, ...]:
    """Name the paths `git status --porcelain` reported, as a plain tuple.

    Parsing lives here rather than in the shell because the format has fields —
    two status columns, an optional rename arrow — and picking the path out of
    it is the kind of thing a unit test catches wrong.
    """
    if path is None or not path.exists():
        return ()
    names: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if len(line) < 4:  # noqa: PLR2004 — two status columns, a space, a path
            continue
        entry = line[3:].strip()
        names.append(entry.rpartition(" -> ")[2] if " -> " in entry else entry.strip('"'))
    return tuple(names)


def run_arm(args: argparse.Namespace) -> int:
    """Record the dispatch's knowledge and clear any finding from a past watch."""
    now = args.now or int(time.time())
    spec = Spec(
        name=args.name,
        worktree=str(Path(args.worktree).resolve()),
        baseline_head=args.baseline_head,
        armed_at=now,
        subject=args.subject,
        runs_dir=str(args.runs_dir),
        grace_secs=args.grace,
        deadline_secs=args.deadline,
        await_path=args.await_path,
        pid=args.pid,
        issue=issue_ref(args.issue),
    )
    write_json(spec_path(args.watch_dir, args.name), spec.as_document())
    stale = finding_path(args.watch_dir, args.name)
    if stale.exists():
        stale.unlink()
    emit(
        (
            ("spec", spec_path(args.watch_dir, args.name)),
            ("finding", finding_path(args.watch_dir, args.name)),
            ("armed_at", now),
        )
    )
    return 0


def run_spec_env(args: argparse.Namespace) -> int:
    """Hand the shell the spec fields it needs to take its readings."""
    document = read_document(spec_path(args.watch_dir, args.name))
    if not document:
        emit((("error", "no such watch"),))
        return 1
    spec = Spec.from_document(document)
    emit(
        (
            ("worktree", spec.worktree),
            ("subject", spec.subject),
            ("pid", spec.pid),
            ("await_path", spec.await_path),
            ("spec", spec_path(args.watch_dir, args.name)),
            ("finding", finding_path(args.watch_dir, args.name)),
        )
    )
    return 0


def run_assess(args: argparse.Namespace) -> int:
    """Assess one pass and write the finding where the next turn reads it."""
    document = read_document(spec_path(args.watch_dir, args.name))
    if not document:
        emit((("error", "no such watch"),))
        return 1
    spec = Spec.from_document(document)
    observation = Observation(
        now=args.now or int(time.time()),
        head=args.head,
        dirty=read_porcelain(args.porcelain_file),
        activity_epoch=args.activity_epoch,
        process_alive=args.process_alive,
    )
    previous = read_document(finding_path(args.watch_dir, args.name))
    finding = assess(spec, observation, previous)
    write_json(
        finding_path(args.watch_dir, args.name),
        finding_document(spec, observation, finding, previous),
    )
    emit(
        (
            ("state", finding.state),
            ("terminal", "true" if finding.terminal else "false"),
            ("line", finding.headline),
        )
    )
    return 0


def run_report(args: argparse.Namespace) -> int:
    """Print one line per terminal finding — the whole of the orchestrator's read."""
    now = args.now or int(time.time())
    documents = sorted(
        (path for path in sorted(args.watch_dir.glob("*.finding.json"))),
        key=lambda path: path.stat().st_mtime,
    )
    for path in documents:
        document = read_document(path)
        if not document.get("terminal"):
            continue
        if document.get("acknowledged_at") and not args.all:
            continue
        print(str(document.get("headline", "")))  # noqa: T201 — the report IS the output
        if args.ack:
            write_json(path, {**document, "acknowledged_at": now})
    return 0


def run_ack(args: argparse.Namespace) -> int:
    """Mark one finding read, so it never resurfaces as news."""
    path = finding_path(args.watch_dir, args.name)
    document = read_document(path)
    if not document:
        emit((("error", "no such finding"),))
        return 1
    write_json(path, {**document, "acknowledged_at": args.now or int(time.time())})
    return 0


def main(argv: list[str] | None = None) -> int:
    """Dispatch the verb; every one of them is a read or a small file write."""
    args = parse_args(argv)
    verbs = {
        "arm": run_arm,
        "spec-env": run_spec_env,
        "assess": run_assess,
        "report": run_report,
        "ack": run_ack,
    }
    return verbs[args.verb](args)


if __name__ == "__main__":
    sys.exit(main())
