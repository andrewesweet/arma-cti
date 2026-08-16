"""Stopping a dispatch, and refusing a second one into a tree that already has one (#308).

The whole of this module comes from #105's sixth instance, recorded live on 2026-08-10.
The orchestration seat dispatched an issue with a mis-spliced brief, killed the dispatch,
saw `ps -p <pid>` return nothing, pre-flighted the worktree clean, and re-dispatched into
it 28 seconds later. **The first dispatch was not dead.** The signal had reached the
launcher and its immediate children; the `claude --print` session survived, reparented,
and worked in that tree for the next half hour. Two agents, one worktree.

Three findings from that incident are what this file mechanises, and each is a rule
rather than a convenience:

- **The worktree, not a pid, is the handle that identifies a dispatch's processes.**
  `just dispatch` gives every dispatch its own tree, so "every process whose
  `/proc/<pid>/cwd` resolves inside that tree" names the session *and* the MCP servers it
  spawned — four processes in the incident, only one of them the session. The launcher pid
  the record used to publish identifies the launcher and nothing else, and it reliably
  outlives nothing. `stop` never reads a recorded pid; `tests/unit/test_dispatch_stop.py`
  asserts that a recorded pid outside the tree is left alone.
- **A stop that does not verify is a guess.** Signalling is followed by a re-scan of the
  same predicate, and a tree that is not empty afterwards is a `stop_unverified` finding
  rather than a success. The first attempt's entire failure was believing that `ps -p
  <launcher>` returning nothing meant the work had stopped.
- **Report what was killed.** The lingering MCP servers are the half nobody would have
  looked for.

**Every refusal path here writes nothing and kills nothing**, which is
`tools/worktree.py`'s property and matters more here because this tool sends signals. The
refusals are all decided before a single `os.kill`, so "refused" and "nothing happened"
are the same state.

## The predicate, and the negative case that matters more than the positive one

`inside` is component-wise containment between *resolved* paths, never a string prefix.
The cases it must exclude are the expensive ones: the repository root is an **ancestor**
of `.claude/worktrees/issue-308` and so is never inside it (killing it would kill the
orchestrator's own session); a sibling `issue-304` is not inside `issue-308`; and
`issue-3080` is not inside `issue-308` either, which a `case "$cwd" in *issue-308*)` glob —
the shape the incident's by-hand scan used — would have matched.

Two processes are deliberately never signalled:

- **This process and its own ancestors.** `just dispatch --stop` run from inside the
  target tree would otherwise kill the shell that typed it, and could never verify. They
  are reported (`skipped_self.<pid>=`) rather than silently dropped.
- **A process whose cwd `/proc` reports as deleted.** The path text of a removed directory
  still matches by name, and after `just worktree done` + `just worktree add` at the same
  path that text belongs to the tree's *previous* occupant. Counted and reported
  (`skipped_deleted_cwd=`), never killed.

## Why `--stop` writes a `result.json` and what it deliberately leaves out

The occupancy rung below reads "no `result.json`" as "live, or dead without writing one",
which is #105's own wording and is what makes a crashed dispatch block its tree. Without a
way to record an ending, that block would have no remedy. So a completed stop lays down a
facts-only result — what was killed, when, and by what — and the tree is dispatchable
again. It **never overwrites a result that is already there**: that one is the run's own
account of itself and this tool did not observe what it says.

The document carries no `refusal` key, and that absence is load-bearing.
`tools/ledger.py`'s `type_end_state` treats `result.json`'s `refusal` as decisive proof
that the dispatcher refused *before the lane was reached*, which is false of a stop — the
lane was reached and work was done. Facts only, as `write_result` says.

Refs #308, #105, ADR-0022, ADR-0049.
"""

from __future__ import annotations

import json
import os
import re
import signal
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple

# tools/ holds standalone scripts rather than an importable package, so a sibling import
# needs the script's own directory on the path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import dispatch_follow  # for `runner_state`; it imports nothing of this module's (#359)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

EXIT_REFUSED: Final = 1
# A finding, not a refusal: signals were sent and the tree is still not empty. Separated
# from the refusal code because the two demand opposite things of the reader — a refusal
# means nothing happened, and this means something happened and did not finish.
EXIT_FINDING: Final = 2

PROCFS: Final = Path("/proc")

# How long the tree is watched for emptiness after each signal. Neither is a backoff and
# neither may be raised to make a stop pass: a process that ignores SIGKILL is in
# uninterruptible sleep, which more waiting does not fix and which the caller must be told
# about rather than waited out.
TERM_GRACE_S: Final = 5.0
KILL_GRACE_S: Final = 2.0
POLL_S: Final = 0.05

# `/proc/<pid>/cwd` for a removed directory reads back as the old path plus this marker.
DELETED_MARKER: Final = " (deleted)"

# A dispatch id becomes a path segment under the dispatch root, so it is checked against
# the alphabet it is minted in rather than joined and hoped for. Kept here rather than
# imported from `tools/dispatch.py`, which imports *this* module.
ID_ALPHABET: Final = re.compile(r"\A[a-z0-9][a-z0-9-]*\Z")

# A guard on the walk up the process tree, not a limit anybody should reach: a `/proc`
# whose PPid links form a cycle is a kernel this project has never seen, and a loop that
# trusted it would hang the one tool the seat reaches for when it is already in trouble.
ANCESTOR_LIMIT: Final = 64

STOPPED: Final = "stopped"
ALREADY_STOPPED: Final = "already_stopped"
ALREADY_FINISHED: Final = "already_finished"

OCCUPIED_ACTION: Final = (
    "A dispatch is already attached to this worktree and has written no result, so it is "
    "either live or dead without having recorded an ending — and neither justifies a "
    "second agent in the tree (#105's sixth instance). Nothing was dispatched. Stop the "
    "holder with `just dispatch --stop <id>`, which verifies by re-scanning the tree and "
    "records the ending, or dispatch into a tree of its own."
)
UNVERIFIED_ACTION: Final = (
    "The tree is still not empty after SIGTERM and SIGKILL, so the stop is not proven and "
    "must not be treated as one — this is exactly the belief that produced two agents in "
    "one worktree. Do not re-dispatch into this tree. Look at the survivors by hand "
    "(`ls -l /proc/<pid>/cwd`, `cat /proc/<pid>/status`); a process that outlives SIGKILL "
    "is in uninterruptible sleep and is the box's problem, not this dispatch's."
)


class Refusal(NamedTuple):
    """One refusal: its class, what was found, and what the caller should do."""

    kind: str
    found: tuple[str, ...]
    action: str
    failure_class: str = ""

    def lines(self) -> tuple[str, ...]:
        """Render the refusal as the lines the caller reads."""
        classed = (f"class={self.failure_class}",) if self.failure_class else ()
        return (f"refusal={self.kind}", *classed, *self.found, f"action={self.action}")


class Process(NamedTuple):
    """One process the scan found, and the two things about it worth reporting."""

    pid: int
    command: str


class Record(NamedTuple):
    """A dispatch as this module needs it: its id, its tree, and where its record lives."""

    dispatch_id: str
    worktree: Path
    directory: Path

    @property
    def finished(self) -> bool:
        """Whether the run recorded an ending of its own."""
        return (self.directory / "result.json").is_file()


class Scan(NamedTuple):
    """What one pass over `/proc` found for a worktree, split by what may be signalled."""

    matched: tuple[Process, ...]
    mine: tuple[Process, ...]
    deleted: int


class Machine(NamedTuple):
    """The box, as the four calls this module makes into it.

    A seam rather than a mock: `procfs` lets the negative cases — the repository root, a
    sibling worktree, a prefix lookalike — be arranged exactly, and `kill` lets the
    signalling order be asserted without spawning anything. The end-to-end test still runs
    against the real `/proc` and a real process, because the contract under test is the
    kernel's.
    """

    procfs: Path = PROCFS
    kill: Callable[[int, int], None] = os.kill
    monotonic: Callable[[], float] = time.monotonic
    pause: Callable[[float], None] = time.sleep
    term_grace: float = TERM_GRACE_S
    kill_grace: float = KILL_GRACE_S
    poll: float = POLL_S
    # 0 means "ask the process", which is what every real caller wants; a test that
    # arranges a fake `/proc` names the pid it planted there instead.
    self_pid: int = 0

    @property
    def me(self) -> int:
        """Return the running process's own pid, as the scan must see it."""
        return self.self_pid or os.getpid()


# ------------------------------------------------------------------ reading the records


def read_record(directory: Path) -> Record | None:
    """Read one dispatch record, or `None` for anything that is not one."""
    plan = directory / "dispatch.json"
    if not plan.is_file():
        return None
    try:
        document = json.loads(plan.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(document, dict):
        return None
    worktree = document.get("worktree")
    dispatch_id = document.get("dispatch_id")
    if not isinstance(worktree, str) or not worktree.strip():
        return None
    if not isinstance(dispatch_id, str) or not dispatch_id.strip():
        return None
    return Record(dispatch_id, Path(worktree), directory)


def read_records(dispatch_dir: Path) -> tuple[Record, ...]:
    """Read every dispatch record on this box, skipping anything unreadable."""
    if not dispatch_dir.is_dir():
        return ()
    found = (read_record(entry) for entry in sorted(dispatch_dir.iterdir()) if entry.is_dir())
    return tuple(record for record in found if record is not None)


def find_record(dispatch_dir: Path, dispatch_id: str) -> tuple[Record | None, Refusal | None]:
    """Resolve a dispatch id to its record, or say precisely which half is missing."""
    if not ID_ALPHABET.fullmatch(dispatch_id):
        return None, Refusal(
            "invalid_dispatch_id",
            (f"dispatch={dispatch_id}", f"want={ID_ALPHABET.pattern}"),
            (
                "A dispatch id is a path segment under the dispatch root and is checked "
                "against the alphabet it is minted in rather than joined. Nothing was "
                "read, nothing was signalled. Name the id `just dispatch` printed."
            ),
        )
    directory = dispatch_dir / dispatch_id
    if not (directory / "dispatch.json").is_file():
        return None, Refusal(
            "unknown_dispatch",
            (f"dispatch={dispatch_id}", f"record={directory}"),
            (
                "No dispatch record with that id exists on this box, so there is nothing "
                "to resolve to a worktree and nothing was signalled. Check the id against "
                f"`ls {dispatch_dir}`."
            ),
        )
    record = read_record(directory)
    if record is None:
        return None, Refusal(
            "dispatch_unreadable",
            (f"dispatch={dispatch_id}", f"record={directory / 'dispatch.json'}"),
            (
                "The record exists and does not read as a dispatch plan, so the worktree "
                "this dispatch was assigned could not be resolved — and a check that "
                "could not run is not a check that passed (#41). Nothing was signalled. "
                "Find the tree by hand and stop it there."
            ),
            failure_class="infra_unavailable",
        )
    return record, None


# --------------------------------------------------------------------- the predicate


def inside(cwd: Path, worktree: Path) -> bool:
    """Whether a process's working directory is the worktree or sits under it.

    Component-wise, against paths both sides have resolved, and never a string prefix.
    The three exclusions this buys are the ones that make the tool safe to run at all:
    the repository root is an *ancestor* of a worktree under `.claude/worktrees/` and so
    is never inside it, a sibling tree is not inside its neighbour, and `issue-3080` is
    not inside `issue-308` — which the incident's `case "$cwd" in *issue-308*)` glob would
    have matched.
    """
    return cwd == worktree or cwd.is_relative_to(worktree)


def _pids(procfs: Path) -> tuple[int, ...]:
    """Every pid `/proc` currently lists, in numeric order."""
    try:
        entries = sorted(int(entry.name) for entry in procfs.iterdir() if entry.name.isdigit())
    except OSError:
        return ()
    return tuple(entries)


def _cwd_of(procfs: Path, pid: int) -> str:
    """Read one process's working directory link, or the empty string if it is gone."""
    try:
        return str((procfs / str(pid) / "cwd").readlink())
    except OSError:
        return ""


def _command_of(procfs: Path, pid: int) -> str:
    """Render one process's command line, falling back to its `comm` for a kernel thread."""
    try:
        raw = (procfs / str(pid) / "cmdline").read_bytes()
    except OSError:
        raw = b""
    rendered = raw.replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()
    if rendered:
        return rendered
    try:
        return (procfs / str(pid) / "comm").read_text(encoding="utf-8").strip() or "unknown"
    except OSError:
        return "unknown"


def _parent_of(procfs: Path, pid: int) -> int:
    """Read one process's parent pid from `status`, which names its fields.

    `stat` is the more usual source and is the wrong one here: its second field is the
    command in parentheses and a command containing `) ` splits it, so a positional parse
    of `stat` is a parse a process can choose to break.
    """
    try:
        status = (procfs / str(pid) / "status").read_text(encoding="utf-8")
    except OSError:
        return 0
    for line in status.splitlines():
        if line.startswith("PPid:"):
            value = line.removeprefix("PPid:").strip()
            return int(value) if value.isdigit() else 0
    return 0


def own_chain(machine: Machine) -> frozenset[int]:
    """Return the running process and its ancestors — the pids no stop may signal."""
    chain: set[int] = set()
    pid = machine.me
    for _ in range(ANCESTOR_LIMIT):
        if pid <= 0 or pid in chain:
            break
        chain.add(pid)
        pid = _parent_of(machine.procfs, pid)
    return frozenset(chain)


def scan(worktree: Path, machine: Machine) -> Scan:
    """Find every process working inside this worktree, split by what may be signalled."""
    resolved = worktree.resolve()
    mine = own_chain(machine)
    matched: list[Process] = []
    ours: list[Process] = []
    deleted = 0
    for pid in _pids(machine.procfs):
        link = _cwd_of(machine.procfs, pid)
        if not link:
            continue
        if link.endswith(DELETED_MARKER):
            if inside(Path(link.removesuffix(DELETED_MARKER)), resolved):
                deleted += 1
            continue
        if not inside(Path(link), resolved):
            continue
        found = Process(pid, _command_of(machine.procfs, pid))
        (ours if pid in mine else matched).append(found)
    return Scan(tuple(matched), tuple(ours), deleted)


# ------------------------------------------------------------------------- stopping


def _signal(processes: Sequence[Process], number: int, machine: Machine) -> None:
    """Send one signal to each process, treating an already-gone pid as done."""
    for process in processes:
        try:
            machine.kill(process.pid, number)
        except OSError:
            # Gone between the scan and the signal, or not ours to signal. Either way the
            # re-scan below is what decides, and it is the only thing that decides.
            continue


def _await_empty(worktree: Path, machine: Machine, budget: float) -> tuple[Process, ...]:
    """Re-scan until the tree holds no signallable process, or the budget runs out."""
    deadline = machine.monotonic() + budget
    while True:
        found = scan(worktree, machine)
        if not found.matched:
            return ()
        if machine.monotonic() >= deadline:
            return found.matched
        machine.pause(machine.poll)


class Stopped(NamedTuple):
    """What the signalling rounds achieved: which pid ended how, and what would not."""

    finished: dict[int, str]
    survivors: tuple[Process, ...]
    commands: dict[int, str]

    def killed_lines(self) -> tuple[str, ...]:
        """Render one line per process this stop ended, with the signal that ended it."""
        return tuple(
            f"killed.{pid}={how} {self.commands.get(pid, 'unknown')}"
            for pid, how in sorted(self.finished.items())
        )


def _stop_processes(worktree: Path, first: Scan, machine: Machine) -> Stopped:
    """Signal, verify, escalate, verify again — and report which signal finished each pid.

    The second round re-signals whatever the *re-scan* found rather than whatever the
    first scan held, so a supervisor that respawns a child under SIGTERM is escalated
    against rather than reported as a survivor of a signal it never received.
    """
    commands = {process.pid: process.command for process in first.matched}
    finished: dict[int, str] = {}

    _signal(first.matched, signal.SIGTERM, machine)
    survivors = _await_empty(worktree, machine, machine.term_grace)
    alive = {process.pid for process in survivors}
    finished.update({pid: "SIGTERM" for pid in commands if pid not in alive})
    if survivors:
        commands.update({process.pid: process.command for process in survivors})
        _signal(survivors, signal.SIGKILL, machine)
        survivors = _await_empty(worktree, machine, machine.kill_grace)
        alive = {process.pid for process in survivors}
        finished.update(
            {pid: "SIGKILL" for pid in commands if pid not in alive and pid not in finished}
        )
    return Stopped(finished, survivors, commands)


def _record_ending(record: Record, finished: dict[int, str]) -> str:
    """Lay down the facts-only result a stop produces, or leave an existing one alone."""
    if record.finished:
        return "preserved"
    path = record.directory / "result.json"
    path.write_text(
        json.dumps(
            {
                "dispatch_id": record.dispatch_id,
                "stopped_by": "just dispatch --stop",
                "stopped_at": datetime.now(tz=UTC).isoformat(),
                "killed": [f"{pid} {how}" for pid, how in sorted(finished.items())],
                "ended_at": datetime.now(tz=UTC).isoformat(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return str(path)


def _context(record: Record, found: Scan) -> tuple[str, ...]:
    """Render the lines every stop outcome carries, whatever it decided."""
    lines = [f"dispatch={record.dispatch_id}", f"worktree={record.worktree}"]
    lines += [f"skipped_self.{process.pid}={process.command}" for process in found.mine]
    if found.deleted:
        lines.append(f"skipped_deleted_cwd={found.deleted}")
    return tuple(lines)


def stop(record: Record, machine: Machine | None = None) -> tuple[int, tuple[str, ...]]:
    """Stop every process working in this dispatch's worktree and prove it by re-scanning."""
    machine = machine or Machine()
    if not record.worktree.is_dir():
        return EXIT_REFUSED, Refusal(
            "worktree_gone",
            (f"dispatch={record.dispatch_id}", f"worktree={record.worktree}"),
            (
                "The tree this dispatch was assigned is not on disk, so the scan that "
                "identifies its processes cannot run — and its absence does not prove "
                "the dispatch stopped, because a process holding a removed directory "
                "keeps reporting that path. Nothing was signalled. Find it by hand: "
                "`for p in /proc/[0-9]*; do readlink $p/cwd; done`."
            ),
            failure_class="infra_unavailable",
        ).lines()
    if not machine.procfs.is_dir():
        return EXIT_REFUSED, Refusal(
            "procfs_unavailable",
            (f"dispatch={record.dispatch_id}", f"procfs={machine.procfs}"),
            (
                "This stop resolves a dispatch to its processes through /proc and there "
                "is none here, so nothing could be found and nothing was signalled. Not "
                "a result about the dispatch."
            ),
            failure_class="infra_unavailable",
        ).lines()

    found = scan(record.worktree, machine)
    if not found.matched:
        return _nothing_running(record, found)

    done = _stop_processes(record.worktree, found, machine)
    if done.survivors:
        return EXIT_FINDING, (
            "finding=stop_unverified",
            *_context(record, found),
            *done.killed_lines(),
            *(f"survivor.{p.pid}={p.command}" for p in done.survivors),
            f"survivors={len(done.survivors)}",
            "verified=no",
            "result=none",
            f"action={UNVERIFIED_ACTION}",
        )
    return 0, (
        f"stop={STOPPED}",
        *_context(record, found),
        *done.killed_lines(),
        f"killed={len(done.finished)}",
        "verified=no_process_in_worktree",
        f"result={_record_ending(record, done.finished)}",
    )


def _nothing_running(record: Record, found: Scan) -> tuple[int, tuple[str, ...]]:
    """Answer the two benign endings: already finished, or dead without saying so.

    A seat that has lost track of what is running types `--stop` on a dispatch that ended
    cleanly, and that must be a named outcome rather than a refusal or a silent success —
    the two readings a caller cannot tell apart from an empty exit 0.
    """
    already = record.finished
    return 0, (
        f"stop={ALREADY_FINISHED if already else ALREADY_STOPPED}",
        *_context(record, found),
        "killed=0",
        "verified=no_process_in_worktree",
        f"result={'preserved' if already else _record_ending(record, {})}",
        (
            "note=the dispatch had already recorded its own ending; nothing was signalled"
            if already
            else "note=no process and no recorded ending, so this stop recorded one and the "
            "tree is dispatchable again"
        ),
    )


def stop_by_id(dispatch_dir: Path, dispatch_id: str) -> tuple[int, tuple[str, ...]]:
    """Resolve a dispatch id and stop it, or refuse without signalling anything."""
    record, refusal = find_record(dispatch_dir, dispatch_id)
    if refusal is not None or record is None:
        return EXIT_REFUSED, refusal.lines() if refusal else ()
    return stop(record)


# ------------------------------------------------------------------ the occupancy rung


def holders(worktree: Path, dispatch_dir: Path) -> tuple[Record, ...]:
    """Every dispatch attached to this exact tree that has recorded no ending."""
    resolved = worktree.resolve()
    return tuple(
        record
        for record in read_records(dispatch_dir)
        if not record.finished and record.worktree.resolve() == resolved
    )


def occupancy_refusal(worktree: Path, dispatch_dir: Path) -> Refusal | None:
    """Refuse a second dispatch into a tree that already holds one with no result (#105).

    The dispatch record directory is the authority, exactly as #105's first proposal put
    it: a record with no `result.json` is either live or dead without having written one,
    and neither justifies a second agent in the tree. A predecessor that *did* record an
    ending is not a holder and does not refuse.

    **No failure class.** CLAUDE.md's table types what a run found, and this found nothing
    about any provider, any lane or any code — the same reasoning `off_peak_refusal` and
    `queue_refusal` carry. It is this project declining to put two agents in one tree.
    """
    occupied = holders(worktree, dispatch_dir)
    if not occupied:
        return None
    return Refusal(
        "worktree_occupied_by_dispatch",
        (
            f"worktree={worktree}",
            # `runner=` is the half `result=absent` cannot say (#359). A holder whose
            # runner is alive is a dispatch to wait for; one whose pipe is at EOF is a
            # record that died without recording its ending, and the reader could not
            # previously tell which without reasoning about a pid this deliberately does
            # not publish. It changes nothing about the refusal — both still refuse — only
            # what the reader is told they are looking at.
            *(
                f"holder={record.dispatch_id} record={record.directory} result=absent"
                f" runner={dispatch_follow.runner_state(record.directory)}"
                for record in occupied
            ),
        ),
        OCCUPIED_ACTION,
    )
