"""Follow dispatches to the first recorded result without detaching (#280, #295).

`just dispatch` deliberately launches its runner outside the tool harness. This
program is the complementary process seam: the caller starts it as a harness-
tracked background task, so its exit can restore the within-session completion
edge that detachment removed.

The dispatcher records the runner's lifetime pipe and result path before
returning. The follower reads those values back, waits for EOF from that exact
runner, and then distinguishes the two honest endings: the recorded result was
written, or the runner disappeared without one. There is no timeout, polling
interval, failure-class inference, or stall judgement here; `just watch` retains
the latter responsibility.

Several ids may be followed at once, and the wait then ends on the **first** of
them, naming the rest as still pending. That is the whole of #295's mechanism.
Following a cohort to its *last* completion is a barrier: the seat sleeps until
the slowest member finishes, so slots freed by the faster ones stay empty with
nobody awake to refill them. Measured over four days of real dispatches, that
barrier delayed the seat's wake by 292 agent-minutes, once by 115 minutes on a
single cohort; `docs/research/dispatch-cost-and-occupancy.md` carries the
derivation.

`--report` is the other half, and #359 is why it exists. The delivery above is
real — a `select` on the runner's own pipe, no poll — but only for a dispatch
somebody attached a follower to, and the attaching is a tool call the harness
makes rather than anything this repository can arm for itself. On 2026-08-16 a
completion woke nobody because no follower had been armed, and the arming was
attempted four times in a form that produced no notification at all; both look
exactly like a dispatch still running. So a follower now writes `follow.json`
into the record it attaches to, and `--report` reads that back:

* `wake_unarmed` — the runner is alive and nothing is listening. Standing, and
  repeated every read until a follower attaches or the run ends, because it is
  actionable *now* and repetition is the only pressure available.
* `wake_undelivered` — the run finished and nothing was listening. Printing it
  **is** the delivery, so it is stamped and printed once.

Attachment is a claim about *now*, and it was first written as a permanent one:
a record carrying `followed_at` was owed nothing forever, so a follower that
returned on the first of a cohort, or died, or was killed, exempted the rest of
that cohort from the report for good. Two facts settle it and they are not the
same fact. Whether anything is listening is `followed_at` plus a live
`follower_pid`, read with `os.kill(pid, 0)`; whether a wake was *delivered* is
`delivered_at`, written by the follower for the dispatch it actually reported
on. Liveness alone cannot stand in for the second — a follower that delivered
its wake and exited leaves the same dead pid as one that was killed before the
run ended — so the pid check answers the first question only, and a completion
is owed a wake until one is recorded against it.
* `dispatch_abandoned` — no result and the runner's pipe is at EOF, so the
  record is stale rather than in flight. Six days of one 2026-08-10 record
  counting as in-flight is what this names; stamped and printed once.

Stamping on print is not ADR-0053's judgement being automated. `just watch`'s
findings are stamped by a human's `--ack` because acting on a stall is a
judgement; these two are a wake, and a wake that has been delivered is not news
a second time. `--all` re-prints the stamped ones, and `--backfill` stamps the
lot at once for a box whose backlog predates the mechanism.
"""

from __future__ import annotations

import argparse
import json
import os
import select
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Sequence

DEFAULT_DISPATCH_DIR = Path.home() / ".arma-cti" / "dispatches"
EXIT_FINDING = 1
EXIT_REFUSED = 2

# What a record's runner is doing, decided from the record alone.
RUNNER_FINISHED: Final = "finished"
RUNNER_RUNNING: Final = "running"
RUNNER_ABANDONED: Final = "abandoned"
RUNNER_UNKNOWN: Final = "unknown"

# The most findings one read prints. A box that has never run `--report` has a
# record per dispatch it has ever made, and every one of them predates
# `follow.json`, so the first read would otherwise put hundreds of lines at the
# top of an orchestrator's turn. The remainder is named rather than dropped, and
# the stamp means the backlog drains a read at a time.
REPORT_LIMIT: Final = 10

# The most *standing* findings one read prints, out of that limit. A standing finding is
# never stamped, so a read filled with them drains nothing and the once-only backlog behind
# it would wait for the running dispatches to end. Half the read keeps both visible; the WIP
# limit of three makes the cap unreachable today, and it is here so the report cannot be
# jammed by a condition that is merely true a lot.
STANDING_LIMIT: Final = REPORT_LIMIT // 2


@dataclass(frozen=True)
class FollowTarget:
    """The values the dispatcher recorded for one follower."""

    dispatch_id: str
    result_path: Path
    runner_pipe: Path


def arm_record(record: Path, launcher_pid: int, runner_pipe: Path) -> None:
    """Add the authoritative follower fields to an existing dispatch record.

    The pid is recorded as `launcher_pid`, which is what it is (#308). It used to be
    called `runner_pid`, and the name was a trap: the value is the `--run` process the
    seam forks, not the session that process starts, so anything that treated it as a
    handle on the work was reasoning about the wrong process — #105's sixth instance,
    where killing it and seeing `ps -p` come back empty read as a successful stop while
    the session worked on for half an hour. Nothing reads this field; it is kept because
    the seam knows the value and a record should say what it forked, and it is named so
    that a later reader cannot mistake it for the work.
    """
    record = record.resolve()
    record_path = record / "dispatch.json"
    document: dict[str, Any] = json.loads(record_path.read_text(encoding="utf-8"))
    document["result_path"] = str(record / "result.json")
    document["launcher_pid"] = launcher_pid
    document["runner_pipe"] = str(runner_pipe.resolve())

    temporary = record / f".dispatch.json.{os.getpid()}.tmp"
    try:
        temporary.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        temporary.replace(record_path)
    finally:
        temporary.unlink(missing_ok=True)


def read_target(dispatch_dir: Path, dispatch_id: str) -> FollowTarget:
    """Read a follower target, including its paths, from the dispatch record."""
    record_path = dispatch_dir.expanduser() / dispatch_id / "dispatch.json"
    document = json.loads(record_path.read_text(encoding="utf-8"))
    recorded_id = str(document["dispatch_id"])
    if recorded_id != dispatch_id:
        message = f"record names {recorded_id!r}, requested {dispatch_id!r}"
        raise ValueError(message)
    return FollowTarget(
        dispatch_id=recorded_id,
        result_path=Path(str(document["result_path"])),
        runner_pipe=Path(str(document["runner_pipe"])),
    )


def runner_state(record: Path) -> str:
    """Say whether this record's runner is finished, alive, gone, or unreadable.

    The same fact `wait_for_first` blocks on, asked without blocking: a FIFO opened
    read-only and non-blocking answers EOF when no writer holds it and `EAGAIN` when one
    does, and the writer here is the runner itself — `tools/dispatch.sh` opens the pipe
    read-write, forks the runner across it, and closes its own copy, so the fd outlives
    the shell and dies with the run.

    This is what distinguishes a stale record from a live one (#359). `result.json`
    alone cannot: a runner that died without writing one leaves a record indistinguishable
    from a run still going, which is how a 2026-08-10 dispatch counted as in flight for
    six days and inflated every count taken from that directory.

    `unknown` is its own answer and never folded into either neighbour — a record older
    than the arming of `runner.pipe` at all, or one on a filesystem that will not open it,
    is a record this cannot read rather than one it has read as dead. Every caller here
    treats it as the refusing direction, which for a *count* means still in flight.
    """
    if (record / "result.json").is_file():
        return RUNNER_FINISHED
    try:
        pipe_fd = os.open(record / "runner.pipe", os.O_RDONLY | os.O_NONBLOCK)
    except OSError:
        return RUNNER_UNKNOWN
    try:
        # Nothing ever writes to this pipe, so a non-empty read cannot happen; both
        # non-EOF answers mean the same thing, which is that a writer is still holding it.
        return RUNNER_ABANDONED if os.read(pipe_fd, 1) == b"" else RUNNER_RUNNING
    except BlockingIOError:
        return RUNNER_RUNNING
    except OSError:
        return RUNNER_UNKNOWN
    finally:
        os.close(pipe_fd)


def note_attachment(record: Path, pid: int, now: float) -> None:
    """Record that a follower attached, which is the fact `--report` reads back.

    Written when the follow *starts* rather than when it ends, because the question the
    report asks is "is anything listening to this dispatch", and a follower that is still
    waiting is the whole of the answer being yes. Merged into whatever is already there so
    a second follower over the same id does not discard the first's stamp.

    The pid is written for the reader, and now it is read: it is what turns this from a
    permanent claim into a claim about the process that made it.
    """
    document = _follow_document(record)
    document.update({"follower_pid": pid, "followed_at": now})
    _write_follow(record, document)


def note_delivery(record: Path, now: float) -> None:
    """Record that this dispatch's wake was actually delivered to somebody.

    The separate fact from attachment, and the one `wake_undelivered` turns on. A follower
    that attached says something *was* listening; only the follower that returned on this
    dispatch says its ending was told to anyone, and after either the process is gone and
    its pid is dead in both cases.
    """
    document = _follow_document(record)
    document["delivered_at"] = now
    _write_follow(record, document)


def clear_attachment(record: Path) -> None:
    """Drop the claim that a follower is listening, keeping whatever else the file holds.

    Written by the follower over the cohort members it is *not* reporting on, and over
    every target of a refused follow. Pid liveness would eventually answer the same way,
    but only eventually and only until a pid is reused; the follower knows it stopped
    listening, so it says so rather than leaving that to be inferred.
    """
    document = _follow_document(record)
    document.pop("follower_pid", None)
    document.pop("followed_at", None)
    _write_follow(record, document)


def wait_for_first(targets: Sequence[FollowTarget]) -> FollowTarget:
    """Stay attached until the first recorded runner closes its pipe, with no time bound."""
    opened: list[tuple[int, FollowTarget]] = []
    try:
        for target in targets:
            pipe_fd = os.open(target.runner_pipe, os.O_RDONLY | os.O_NONBLOCK)
            opened.append((pipe_fd, target))
            try:
                already_closed = os.read(pipe_fd, 1) == b""
            except BlockingIOError:
                already_closed = False
            if already_closed:
                return target
        readable, _, _ = select.select(tuple(fd for fd, _ in opened), (), ())
        first = readable[0]
        return next(target for fd, target in opened if fd == first)
    finally:
        for pipe_fd, _ in opened:
            os.close(pipe_fd)


def wait_for_runner(target: FollowTarget) -> None:
    """Stay attached until this one recorded runner closes its pipe."""
    wait_for_first((target,))


def pending_ids(targets: Sequence[FollowTarget], reported: FollowTarget) -> tuple[str, ...]:
    """Name the followed dispatches that are neither reported nor finished."""
    return tuple(
        target.dispatch_id
        for target in targets
        if target.dispatch_id != reported.dispatch_id and not target.result_path.is_file()
    )


def _pending_line(pending: Sequence[str]) -> tuple[str, ...]:
    """Render the pending remainder only when there is one, so one id reads as before."""
    return (f"pending={','.join(pending)}",) if pending else ()


def recorded_terminal(result_path: Path) -> str:
    """Read the terminal state the run recorded, without deciding one for it.

    `unrecorded` covers both a result written before `terminal_state` existed and one
    this cannot read; neither is a state, and inventing `committed` for either would be
    the reading #375 makes dangerous — an unanswerable `git status` presented as a clean
    tree.
    """
    try:
        document = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return "unrecorded"
    if not isinstance(document, dict):
        return "unrecorded"
    return str(document.get("terminal_state") or "unrecorded")


def completion_lines(target: FollowTarget, pending: Sequence[str] = ()) -> tuple[str, ...]:
    """Render a completion using only values read from the dispatch record.

    `terminal=` is quoted from `result.json` and not derived here (#359). The wake is the
    one moment the seat's ending is being read at all, so a run that exited with
    uncommitted work in its assigned tree says so in the line that wakes the orchestrator,
    rather than waiting for someone to run `git status` in the tree before the next
    dispatch — which is the convention that missed two of them on 2026-08-16.
    """
    return (
        "completion=dispatch_result_written",
        f"dispatch={target.dispatch_id}",
        f"result={target.result_path}",
        f"terminal={recorded_terminal(target.result_path)}",
        *_pending_line(pending),
    )


def finding_lines(target: FollowTarget, pending: Sequence[str] = ()) -> tuple[str, ...]:
    """Render the ADR-0022 ending without inventing a result or failure class."""
    return (
        "finding=runner_disappeared",
        f"dispatch={target.dispatch_id}",
        f"result={target.result_path}",
        "action=inspect the dispatch log and use just watch for stall classification",
        *_pending_line(pending),
    )


def first_ending(targets: Sequence[FollowTarget]) -> FollowTarget:
    """Name whichever target has already ended, or wait for the first that does."""
    for target in targets:
        if target.result_path.is_file():
            return target
    return wait_for_first(targets)


def result_lines(first: FollowTarget, pending: Sequence[str] = ()) -> tuple[int, tuple[str, ...]]:
    """Render one ended target as a completion or an ADR-0022 disappeared-runner finding."""
    if first.result_path.is_file():
        return 0, completion_lines(first, pending)
    return EXIT_FINDING, finding_lines(first, pending)


def follow_first(targets: Sequence[FollowTarget]) -> tuple[int, tuple[str, ...]]:
    """Follow every target to whichever ends first, naming the rest as pending."""
    first = first_ending(targets)
    return result_lines(first, pending_ids(targets, first))


def follow(target: FollowTarget) -> tuple[int, tuple[str, ...]]:
    """Follow one target to a recorded completion or a disappeared-runner finding."""
    return follow_first((target,))


# -------------------------------------------------------------------- the delivery report


class Finding(NamedTuple):
    """One dispatch whose wake is unarmed, undelivered, or lost, and what to do about it."""

    kind: str
    record: Path
    lines: tuple[str, ...]
    # Whether printing this finding discharges it. A standing condition (`wake_unarmed`)
    # is re-read every turn until it is no longer true; a wake (`wake_undelivered`,
    # `dispatch_abandoned`) is delivered by being printed, and repeating it is noise.
    once: bool


def _follow_document(record: Path) -> dict[str, Any]:
    """Read `follow.json`, or an empty document for anything that will not read as one."""
    try:
        loaded = json.loads((record / "follow.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _write_follow(record: Path, document: dict[str, Any]) -> None:
    """Write `follow.json`, or remove it once nothing is left to say.

    Nothing here may raise into its caller. `--report` is chained ahead of the stall
    watchers in `just watch-report`, so an unwritable record — removed between the survey
    and the stamp, a read-only mount — would otherwise take out the very read that catches
    what this one misses. A write that did not happen costs a finding repeated next read,
    which is the direction that keeps saying something.
    """
    path = record / "follow.json"
    try:
        if document:
            path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        else:
            path.unlink(missing_ok=True)
    except OSError:
        return


def _follower_alive(document: dict[str, Any]) -> bool:
    """Whether the process that claimed to be listening still exists.

    `os.kill(pid, 0)` is the whole check: a pid that is not ours to signal is a pid that
    exists, and only `ProcessLookupError` says the follower is gone. A recorded attachment
    with no pid — a `follow.json` written before this was read back — answers no, which
    reports a wake rather than assuming one was delivered.

    Pid reuse is the known ceiling and it is not defended against: the follower clears its
    own attachment on the way out, so reuse would have to land inside the window between a
    follower dying uncleanly and the next read.
    """
    pid = document.get("follower_pid")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _listening(record: Path) -> bool:
    """Whether a follower is attached to this record *and* still alive to hear it.

    The key and the pid, never the file's existence. `followed_at` and `reported_at` live
    in one file and mean opposite things — the second is written by the stamp — so reading
    the file's existence as attachment once made a stamped `wake_undelivered` vanish from
    `--report --all`, the one read that exists to show what was already delivered.
    """
    document = _follow_document(record)
    return bool(document.get("followed_at")) and _follower_alive(document)


def _delivered(record: Path) -> bool:
    """Whether this dispatch's ending was reported to somebody by a follower."""
    return bool(_follow_document(record).get("delivered_at"))


def _stamped(record: Path) -> bool:
    """Whether a once-only finding on this record has already been printed."""
    return bool(_follow_document(record).get("reported_at"))


def stamp(record: Path, now: float) -> None:
    """Mark a once-only finding delivered, keeping whatever the follower wrote."""
    document = _follow_document(record)
    document["reported_at"] = now
    _write_follow(record, document)


def finding_for(record: Path) -> Finding | None:
    """Judge one record's delivery, or `None` where nothing is owed.

    Nothing is owed by a run whose wake a follower delivered, nor by a run still going
    with a live follower attached; `unknown` is owed nothing either, because a record
    whose pipe cannot be read is not evidence that a wake was lost.

    A finished run with a follower still attached is the ordinary window between the
    result landing and the follower printing it, so it is owed nothing yet — and it is
    owed a wake again the moment that follower is gone without having recorded one.
    """
    dispatch_id = record.name
    listening = _listening(record)
    state = runner_state(record)
    if state == RUNNER_RUNNING and not listening:
        return Finding(
            "wake_unarmed",
            record,
            (
                "finding=wake_unarmed",
                f"dispatch={dispatch_id}",
                "detail=this dispatch is running and no follower is attached to it",
                f"action=just dispatch-follow {dispatch_id}",
            ),
            once=False,
        )
    if state == RUNNER_FINISHED and not (_delivered(record) or listening):
        return Finding(
            "wake_undelivered",
            record,
            (
                "finding=wake_undelivered",
                f"dispatch={dispatch_id}",
                f"result={record / 'result.json'}",
                f"terminal={recorded_terminal(record / 'result.json')}",
                "action=read the result; this completion woke nobody when it happened",
            ),
            once=True,
        )
    if state == RUNNER_ABANDONED:
        return Finding(
            "dispatch_abandoned",
            record,
            (
                "finding=dispatch_abandoned",
                f"dispatch={dispatch_id}",
                f"record={record}",
                # A fact about the runner and about nothing else. #105's sixth instance is
                # exactly a dead runner whose session worked on in the tree for half an
                # hour, so "stale" here must not read as "the tree is free": the record is
                # what is stale, and `just dispatch --stop` still owns the tree's answer.
                (
                    "detail=the runner is gone and wrote no result, so this record is"
                    " stale; it says nothing about whether work is still going on in"
                    " its worktree"
                ),
                "action=inspect the dispatch log; just watch keeps the stall judgement",
            ),
            once=True,
        )
    return None


def survey(dispatch_dir: Path, *, include_stamped: bool = False) -> tuple[Finding, ...]:
    """Judge every record on the box, newest first, dropping what has been delivered."""
    found: list[Finding] = []
    for plan in sorted(dispatch_dir.expanduser().glob("*/dispatch.json"), reverse=True):
        finding = finding_for(plan.parent)
        if finding is None:
            continue
        if finding.once and not include_stamped and _stamped(finding.record):
            continue
        found.append(finding)
    return tuple(found)


def shown_findings(
    findings: Sequence[Finding],
    limit: int = REPORT_LIMIT,
    standing_limit: int = STANDING_LIMIT,
) -> tuple[Finding, ...]:
    """Choose what one read prints, so what is stamped is exactly what was printed."""
    shown: list[Finding] = []
    standing = 0
    for finding in findings:
        if len(shown) >= limit:
            break
        if not finding.once:
            if standing >= standing_limit:
                continue
            standing += 1
        shown.append(finding)
    return tuple(shown)


def report_lines(
    findings: Sequence[Finding],
    limit: int = REPORT_LIMIT,
    standing_limit: int = STANDING_LIMIT,
) -> tuple[str, ...]:
    """Render the report, naming the remainder rather than truncating in silence.

    Standing findings take at most half the read. They are never stamped, so enough of
    them at once would fill every read for as long as they lasted and the once-only
    backlog behind them would never drain — the report would keep saying the same true
    thing and stop saying the new ones. A standing finding dropped from a read is true
    again on the next one, which is the cheapest thing here to lose.
    """
    shown = shown_findings(findings, limit, standing_limit)
    lines = [line for finding in shown for line in finding.lines]
    if len(findings) > len(shown):
        lines.append(
            f"more={len(findings) - len(shown)} detail=re-run just watch-report to read on"
        )
    return tuple(lines)


def run_backfill(args: argparse.Namespace) -> int:
    """Stamp every once-only finding owed right now, and print only how many.

    The first read on a box that has been dispatching since before `follow.json` existed
    owes a `wake_undelivered` for every completion it ever made: 341 of them on 2026-08-16,
    about 34 reads at the top of 34 orchestrator turns to drain a backlog of wakes whose
    dispatches ended days ago. This is the one deliberate act that says so — a human or the
    orchestrator running it once, in the open, with the count printed. It stamps rather than
    deletes, so `--report --all` still shows every one of them.
    """
    findings = survey(args.dispatch_dir)
    now = time.time()
    stamped = [finding for finding in findings if finding.once]
    for finding in stamped:
        stamp(finding.record, now)
    return emit(
        (
            f"backfilled={len(stamped)}",
            "detail=once-only findings stamped as delivered; read them with --report --all",
        ),
        0,
    )


def run_report(args: argparse.Namespace) -> int:
    """Print what is owed, and stamp the once-only findings that printing discharges.

    Silent when nothing is owed, like every other read `just watch-report` chains, and
    exit 0 either way: this reports, and the failure classes stay with what a run found.
    """
    findings = survey(args.dispatch_dir, include_stamped=args.all)
    code = emit(report_lines(findings), 0)
    if not args.all:
        now = time.time()
        for finding in shown_findings(findings):
            if finding.once:
                stamp(finding.record, now)
    return code


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the public follow form and the dispatcher's internal arm form."""
    parser = argparse.ArgumentParser(prog="dispatch-follow", description=__doc__)
    parser.add_argument("dispatch_ids", nargs="*", default=[])
    parser.add_argument(
        "--dispatch-dir",
        type=Path,
        default=Path(os.environ.get("CTI_DISPATCH_DIR", str(DEFAULT_DISPATCH_DIR))),
    )
    parser.add_argument("--arm-record", type=Path)
    parser.add_argument("--launcher-pid", type=int, default=0)
    parser.add_argument("--runner-pipe", type=Path)
    parser.add_argument(
        "--report",
        action="store_true",
        help="name every dispatch whose wake is unarmed, undelivered or lost",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="with --report, re-print the findings already delivered",
    )
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="stamp every once-only finding owed now, printing the count and nothing else",
    )
    return parser.parse_args(argv)


def emit(lines: tuple[str, ...], code: int) -> int:
    """Print a completion to stdout and a finding or refusal to stderr."""
    stream = sys.stdout if code == 0 else sys.stderr
    for line in lines:
        print(line, file=stream)
    return code


def arm_from_args(args: argparse.Namespace) -> int:
    """Record follower fields for the detached seam's internal arm request."""
    if args.launcher_pid <= 0 or args.runner_pipe is None:
        return emit(("refusal=runner_identity_missing",), EXIT_REFUSED)
    try:
        arm_record(args.arm_record, args.launcher_pid, args.runner_pipe)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        return emit(
            ("refusal=dispatch_follow_arm_failed", f"detail={error}"),
            EXIT_REFUSED,
        )
    return 0


def unique_ids(requested: Sequence[str]) -> tuple[str, ...]:
    """Keep the caller's order and follow each named dispatch once."""
    seen: dict[str, None] = {}
    for dispatch_id in requested:
        seen.setdefault(dispatch_id, None)
    return tuple(seen)


def follow_from_args(args: argparse.Namespace) -> int:
    """Read every named dispatch and follow them all to whichever ends first."""
    requested = unique_ids(args.dispatch_ids)
    if not requested:
        return emit(("refusal=dispatch_id_missing",), EXIT_REFUSED)
    targets: list[FollowTarget] = []
    for dispatch_id in requested:
        try:
            targets.append(read_target(args.dispatch_dir, dispatch_id))
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
            return emit(
                (
                    "refusal=dispatch_follow_unavailable",
                    f"dispatch={dispatch_id}",
                    f"detail={error}",
                ),
                EXIT_REFUSED,
            )
    records = {
        target.dispatch_id: args.dispatch_dir.expanduser() / target.dispatch_id
        for target in targets
    }
    # After the last target reads back, so a refused follow leaves no claim that anything
    # was listening, and before the wait, because a follower is attached while it waits.
    for target in targets:
        note_attachment(records[target.dispatch_id], os.getpid(), time.time())
    try:
        first = first_ending(targets)
    except OSError as error:
        # The second refusal path, and it refuses having observed nothing — so it owes the
        # same emptiness the first one leaves. Attachment is already written by here, and a
        # refusal that left it standing was a check that did not run reading as one that
        # passed: every one of these records would have been exempt from `--report`.
        for record in records.values():
            clear_attachment(record)
        return emit(
            (
                "refusal=runner_unobservable",
                f"dispatch={','.join(requested)}",
                f"detail={error}",
            ),
            EXIT_REFUSED,
        )
    now = time.time()
    note_delivery(records[first.dispatch_id], now)
    # This process ends on the first of them, so nothing is listening to the rest from the
    # moment it returns. Leaving the attachment behind is what made the cohort mechanism —
    # built to shorten the wake — the thing that silenced the report for everyone it did
    # not wake (#295's `pending=` list, exempt from `--report` for good).
    for dispatch_id, record in records.items():
        if dispatch_id != first.dispatch_id:
            clear_attachment(record)
    code, lines = result_lines(first, pending_ids(targets, first))
    return emit(lines, code)


def main(argv: list[str] | None = None) -> int:
    """Arm a record, backfill or report undelivered wakes, or follow named dispatches."""
    args = parse_args(argv)
    if args.arm_record is not None:
        return arm_from_args(args)
    if args.backfill:
        return run_backfill(args)
    return run_report(args) if args.report else follow_from_args(args)


if __name__ == "__main__":
    sys.exit(main())
