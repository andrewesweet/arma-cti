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

Refusals made before a disposable tree's ownership proof completes write nothing and kill
nothing, which is `tools/worktree.py`'s property and matters more here because this tool
sends signals. A teardown can still fail after signals were verified — for example when
Git refuses to remove the exact owned registration — so that terminal refusal reports the
kills and leaves no result rather than pretending removal succeeded.

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
facts-only result — what was killed, when, and by what — with
`terminal_state: {"state": "stopped"}` and no `ended_at`: the record is closed, but the
sweep did not observe the run's end. The tree is dispatchable again. It **never
overwrites a result that is already there**: that one is the run's own account of itself
and this tool did not observe what it says.

The document carries no `refusal` key, and that absence is load-bearing.
`tools/ledger.py`'s `type_end_state` treats `result.json`'s `refusal` as decisive proof
that the dispatcher refused *before the lane was reached*, which is false of a stop — the
lane was reached and work was done. Facts only, as `write_result` says.

Refs #308, #105, ADR-0022, ADR-0049.
"""

from __future__ import annotations

import errno
import json
import os
import re
import signal
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple

sys.path.insert(0, str(Path(__file__).parent))

import worktree

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

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
DISPOSABLE_PREFIX: Final = "dispatch-"

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
    disposable_worktree: bool = False
    worktree_ref: str = ""
    worktree_owner: str = ""

    @property
    def finished(self) -> bool:
        """Whether the run recorded an ending of its own."""
        return (self.directory / "result.json").is_file()


class Scan(NamedTuple):
    """What one pass over `/proc` found for a worktree, split by what may be signalled.

    An empty `matched` is not proof the tree is empty, so the inputs that can hide
    the difference are reported rather than collapsed into it (#625's cap ruling):
    `unresolved` counts pids of this user's whose cwd could not be read, or whose
    owner could not be read at all, `proc_unreadable` says `/proc` itself could not
    be listed, and `deleted` counts a live process the tree was removed under.
    """

    matched: tuple[Process, ...]
    mine: tuple[Process, ...]
    deleted: int
    unresolved: int = 0
    proc_unreadable: bool = False


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
    # None means "ask the process", for the same reason; a test that arranges a fake
    # `/proc` names the user it is scanning as instead.
    euid: int | None = None

    @property
    def me(self) -> int:
        """Return the running process's own pid, as the scan must see it."""
        return self.self_pid or os.getpid()

    @property
    def effective_uid(self) -> int:
        """Return the running process's user, as the unreadable-cwd placement sees it."""
        return os.geteuid() if self.euid is None else self.euid


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
    return Record(
        dispatch_id,
        Path(worktree),
        directory,
        document.get("disposable_worktree") is True,
        str(document.get("worktree_ref", "")),
        str(document.get("worktree_owner", "")),
    )


def read_records(dispatch_dir: Path) -> tuple[Record, ...]:
    """Read every dispatch record on this box, skipping anything unreadable."""
    if not dispatch_dir.is_dir():
        return ()
    found = (read_record(entry) for entry in sorted(dispatch_dir.iterdir()) if entry.is_dir())
    return tuple(record for record in found if record is not None)


def _cleanup_refusal(record: Record, reason: str) -> Refusal:
    """Refuse disposable-tree removal when the dispatch-owned proof is incomplete."""
    return Refusal(
        "disposable_worktree_unproven",
        (
            f"dispatch={record.dispatch_id}",
            f"worktree={record.worktree}",
            f"reason={reason}",
        ),
        "The dispatch cannot prove that this exact tree belongs to it. Nothing was removed; "
        "inspect the record and worktree by hand rather than guessing (#105).",
        failure_class="infra_unavailable",
    )


def _disposable_proof(  # noqa: PLR0911 — each ownership proof rung refuses independently
    record: Record,
) -> tuple[tuple[Path, Path] | None, Refusal | None]:
    """Prove the id-derived disposable location without removing or touching it."""
    if not record.disposable_worktree:
        return None, None
    if not ID_ALPHABET.fullmatch(record.dispatch_id):
        return None, _cleanup_refusal(record, "invalid_dispatch_id")
    if record.directory.name != record.dispatch_id:
        return None, _cleanup_refusal(record, "record_path_not_derived_from_dispatch_id")
    if record.worktree_owner != record.dispatch_id:
        return None, _cleanup_refusal(record, "worktree_owner_mismatch")
    if record.worktree.name != f"{DISPOSABLE_PREFIX}{record.dispatch_id}":
        return None, _cleanup_refusal(record, "path_name_not_derived_from_dispatch_id")
    try:
        target = record.worktree.resolve()
        root = record.worktree.parent.parent.parent.resolve()
        expected = (root / worktree.WORKTREES / record.worktree.name).resolve()
    except OSError:
        return None, _cleanup_refusal(record, "path_unreadable")
    if target != expected:
        return None, _cleanup_refusal(record, "path_outside_dispatch_worktree_root")
    return (target, root), None


def cleanup_disposable_worktree(  # noqa: PLR0911 — every ownership proof fails closed
    record: Record,
) -> tuple[Refusal | None, tuple[str, ...]]:
    """Remove only a dispatch-owned disposable tree, or refuse without guessing.

    Ownership is three independent facts: the record explicitly marks the tree disposable,
    its owner field is the dispatch id, and the path is exactly the id-derived slot below the
    main checkout. Git's live worktree registration is checked before and after removal. A
    missing proof, a missing registration with a directory still present, or a stale
    registration is a refusal; this function never prunes or removes a path by name alone.
    """
    proof, refusal = _disposable_proof(record)
    if refusal is not None:
        return refusal, ()
    if proof is None:
        return None, ()
    target, root = proof
    try:
        registrations = worktree.parse_registrations(
            worktree.git("worktree", "list", "--porcelain", cwd=root)
        )
        registered = tuple(entry for entry in registrations if entry.path.resolve() == target)
    except (OSError, ValueError, worktree.GitError) as failure:
        detail = getattr(failure, "stderr", str(failure))
        return _cleanup_refusal(record, f"git_failed:{detail}"), ()
    if not registered and not target.exists():
        return None, (f"worktree_cleanup=already_gone path={target}",)
    if len(registered) != 1:
        return _cleanup_refusal(
            record,
            "registration_missing" if not registered else "registration_ambiguous",
        ), ()
    if not target.is_dir():
        return _cleanup_refusal(record, "registration_stale"), ()
    try:
        worktree.git("worktree", "remove", "--force", str(target), cwd=root)
        remaining = worktree.parse_registrations(
            worktree.git("worktree", "list", "--porcelain", cwd=root)
        )
    except (OSError, ValueError, worktree.GitError) as failure:
        detail = getattr(failure, "stderr", str(failure))
        return _cleanup_refusal(record, f"git_failed:{detail}"), ()
    try:
        still_registered = any(entry.path.resolve() == target for entry in remaining)
    except OSError as failure:
        return _cleanup_refusal(record, f"registration_read_failed:{failure}"), ()
    if target.exists() or still_registered:
        return _cleanup_refusal(record, "removal_not_verified"), ()
    return None, (f"worktree_cleanup=removed path={target}",)


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


def _pids(procfs: Path) -> tuple[int, ...] | None:
    """Every pid `/proc` currently lists, in numeric order, or None when it cannot be listed.

    The None is the scan saying it looked at nothing rather than at an empty box
    (#625's cap ruling): a caller reading an empty tuple as an empty tree would be
    reading an absence of evidence as evidence of absence.
    """
    try:
        entries = sorted(int(entry.name) for entry in procfs.iterdir() if entry.name.isdigit())
    except OSError:
        return None
    return tuple(entries)


def _cwd_of(procfs: Path, pid: int) -> tuple[str, int]:
    """Read one process's working directory link, with the errno when it could not be.

    The errno is what lets the scan tell a process that is gone (ENOENT — it exited
    between the listing and this read, so nobody is there) from one it could not look
    at (EPERM, EINVAL, ...) — the two inputs #625's cap ruling places on opposite
    sides of the line.
    """
    try:
        return str((procfs / str(pid) / "cwd").readlink()), 0
    except OSError as failure:
        return "", failure.errno


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


def _status_field(procfs: Path, pid: int, name: str) -> str | None:
    """Read one `status` line's value by its exact field name, or None when unreadable.

    `stat` is the more usual source and is the wrong one here: its second field is the
    command in parentheses and a command containing `) ` splits it, so a positional parse
    of `stat` is a parse a process can choose to break.
    """
    try:
        status = (procfs / str(pid) / "status").read_text(encoding="utf-8")
    except OSError:
        return None
    for line in status.splitlines():
        if line.startswith(f"{name}:"):
            return line.removeprefix(f"{name}:").strip()
    return None


def _parent_of(procfs: Path, pid: int) -> int:
    """Read one process's parent pid from `status`."""
    value = _status_field(procfs, pid, "PPid")
    return int(value) if value and value.isdigit() else 0


def _uid_of(procfs: Path, pid: int) -> int | None:
    """Read one process's real uid from `status`, or None when its owner cannot be placed."""
    fields = (_status_field(procfs, pid, "Uid") or "").split()
    return int(fields[0]) if fields and fields[0].isdigit() else None


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
    """Find every process working inside this worktree, split by what may be signalled.

    An empty `matched` is not proof the tree is empty, so the inputs that could hide
    the difference are reported rather than collapsed into it (#625's cap ruling).
    Each placement is deliberate: a pid of this user's whose cwd cannot be read counts
    in `unresolved`, because that could be an agent this scan cannot see; a pid whose
    owner cannot be read counts too, because unplaceable is not knowably foreign; a
    different owner's unreadable cwd does not count, because a dispatch's processes
    run as the controller's user and that read was never visible to it anyway; an
    ENOENT does not count, because the process is gone, not hidden.  A `/proc` that
    cannot be listed is `proc_unreadable` — a look that never happened.  The
    controller's own chain stays excluded as before, which is a reasoned exclusion
    rather than a failure to look.
    """
    resolved = worktree.resolve()
    mine = own_chain(machine)
    matched: list[Process] = []
    ours: list[Process] = []
    deleted = 0
    unresolved = 0
    pids = _pids(machine.procfs)
    if pids is None:
        return Scan((), (), 0, 0, proc_unreadable=True)
    for pid in pids:
        link, failure = _cwd_of(machine.procfs, pid)
        if failure == errno.ENOENT:
            continue
        if failure:
            if _uid_of(machine.procfs, pid) in (None, machine.effective_uid):
                unresolved += 1
            continue
        if link.endswith(DELETED_MARKER):
            if inside(Path(link.removesuffix(DELETED_MARKER)), resolved):
                deleted += 1
            continue
        if not inside(Path(link), resolved):
            continue
        found = Process(pid, _command_of(machine.procfs, pid))
        (ours if pid in mine else matched).append(found)
    return Scan(tuple(matched), tuple(ours), deleted, unresolved)


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
    """Lay down the facts-only stop closeout, or leave an existing result alone."""
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
                "terminal_state": {"state": STOPPED},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return str(path)


def is_stop_closeout(document: Mapping[str, object]) -> bool:
    """Recognise a `result.json` the stop sweep laid down, in either of its two shapes.

    This is the one home for the closeout shape, beside the `_record_ending` that
    writes it, so the writer and its readers cannot drift apart (#558, after
    #549): `occupancy.py` (a closeout attests no occupancy span),
    `review_exchange.py` (a swept dispatch completed no review) and
    `observatory.py` (`_ended_for` reads no end from it) all call this predicate
    rather than spelling it again. A change to the shape is made here once.

    The current sweep writes `stopped_by` and a `terminal_state` whose state is
    `stopped`, and no `ended_at`. Eleven legacy records write `stopped_by` and
    stamp the sweep's clock into `ended_at`, with no `terminal_state` — so
    `stopped_by` recognises every record that exists, and the `terminal_state`
    check names the current shape exactly: a block carrying any other state is
    some other writer's, not this sweep's.
    """
    terminal_state = document.get("terminal_state")
    return "stopped_by" in document or (
        isinstance(terminal_state, dict) and terminal_state.get("state") == STOPPED
    )


def _context(record: Record, found: Scan) -> tuple[str, ...]:
    """Render the lines every stop outcome carries, whatever it decided."""
    lines = [f"dispatch={record.dispatch_id}", f"worktree={record.worktree}"]
    lines += [f"skipped_self.{process.pid}={process.command}" for process in found.mine]
    if found.deleted:
        lines.append(f"skipped_deleted_cwd={found.deleted}")
    return tuple(lines)


def stop(  # noqa: PLR0911 — the stop protocol preserves each typed terminal outcome
    record: Record, machine: Machine | None = None
) -> tuple[int, tuple[str, ...]]:
    """Stop every process working in this dispatch's worktree and prove it by re-scanning."""
    machine = machine or Machine()
    if not record.worktree.is_dir() and not record.disposable_worktree:
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

    if record.disposable_worktree:
        _, ownership_refusal = _disposable_proof(record)
        if ownership_refusal is not None:
            return EXIT_REFUSED, ownership_refusal.lines()

    found = scan(record.worktree, machine)
    if not record.worktree.is_dir() and (found.matched or found.deleted):
        return EXIT_REFUSED, Refusal(
            "worktree_gone",
            (f"dispatch={record.dispatch_id}", f"worktree={record.worktree}"),
            (
                "The disposable tree is gone but a process still reports its old path, so "
                "the dispatch cannot be proven stopped. Nothing was removed; inspect the "
                "deleted-cwd process by hand."
            ),
            failure_class="infra_unavailable",
        ).lines()
    if not found.matched:
        cleanup_refusal, cleanup_lines = cleanup_disposable_worktree(record)
        if cleanup_refusal is not None:
            return EXIT_REFUSED, (*_context(record, found), *cleanup_refusal.lines())
        return _nothing_running(record, found, cleanup_lines)

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
    cleanup_refusal, cleanup_lines = cleanup_disposable_worktree(record)
    if cleanup_refusal is not None:
        return EXIT_REFUSED, (
            f"stop={STOPPED}",
            *_context(record, found),
            *done.killed_lines(),
            f"killed={len(done.finished)}",
            "verified=no_process_in_worktree",
            *cleanup_refusal.lines(),
            "result=none",
        )
    return 0, (
        f"stop={STOPPED}",
        *_context(record, found),
        *done.killed_lines(),
        f"killed={len(done.finished)}",
        "verified=no_process_in_worktree",
        *cleanup_lines,
        f"result={_record_ending(record, done.finished)}",
    )


def _nothing_running(
    record: Record, found: Scan, cleanup_lines: tuple[str, ...] = ()
) -> tuple[int, tuple[str, ...]]:
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
        *cleanup_lines,
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
            *(
                f"holder={record.dispatch_id} record={record.directory} result=absent"
                for record in occupied
            ),
        ),
        OCCUPIED_ACTION,
    )
