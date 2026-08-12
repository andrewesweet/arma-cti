"""`just watch-report`'s Remote Control half: a session the bridge killed, said once.

The Remote Control servers spawn every worktree session this project runs from a
phone. When the bridge cannot refresh a session's token it SIGTERMs that session's
process and prints three lines into its tmux pane:

    [07:08:18] Error: Failed to refresh session cse_01Czi2G6JHvdRZxNPymhnmCr token:
    [07:13:30] Session failed: Process exited with error cse_01Czi2G6JHvdRZxNPymhnmCr
    [07:13:30] kept worktree …/bridge-cse_01Czi2G6JHvdRZxNPymhnmCr · session crashed

Nothing else records it. The session's transcript simply stops, its telemetry goes
quiet at the last completed turn with no error event, and the journal carries only
the server wrapper's own output. On 2026-08-12 that cost fifteen hours: the session
died at 07:13 and the loss was noticed at 22:44, by which time the pane's 2,000-line
scrollback had nearly evicted the only evidence there was. Two earlier instances
(2026-08-06, twice) were never noticed at all.

So the wrapper greps its pane log for those lines and `record`s what it saw here;
`report` is folded into `just watch-report`, where an orchestrator turn already
looks. This is the same shape as the breaker's and the watchers' reads and for the
same reason: a finding that lands at the top of a turn the seat was taking anyway
costs nothing to notice.

**It only notices.** Nothing here restarts a session, and deliberately: those
servers run at `--permission-mode bypassPermissions`, and a process that
resurrects a bypassPermissions session on a transport fault is a worse failure
than the one it repairs. The line names the resume command; typing it is a
judgement, exactly as ADR-0053 leaves prodding a stalled agent one.

`acknowledged_at` is carried rather than re-stamped, the idiom `tools/stall_watch.py`
established: a crash the orchestrator has already read must not resurface next turn
as news. `--ack` marks what it prints; `--all` re-reads what was acknowledged.

The state directory is `CTI_RC_HEALTH_DIR`, the seam `CTI_WATCH_DIR` and
`CTI_BREAKER_DIR` exist for (#249): without it a unit test of the recipe reads the
live box, and whatever the box happens to be carrying reddens an unrelated run.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Final, NamedTuple

DEFAULT_RC_HEALTH_DIR: Final = Path.home() / ".arma-cti" / "rc-health"
DEFAULT_PROJECTS_DIR: Final = Path.home() / ".claude" / "projects"

# The two lines the bridge prints, and what each one means to a reader. `crashed`
# is terminal — the process is gone and the worktree is stranded; `refresh_failed`
# is the warning that precedes it by minutes and sometimes stands alone, because a
# refresh can fail and then succeed. They are kept as distinct kinds rather than
# folded together so that a lone warning does not read as a lost session.
KIND_CRASHED: Final = "crashed"
KIND_REFRESH_FAILED: Final = "refresh_failed"
KINDS: Final = (KIND_CRASHED, KIND_REFRESH_FAILED)


# The two lines the bridge prints, as the pane carries them: a leading `[HH:MM:SS]`
# stamp the wrapper's own `sed` has already stripped of colour. Matched rather than
# split on, because the tail of each line differs — the crash names only the session,
# the kept-worktree line names the path, and the refresh error's own detail is
# sometimes empty after its colon, as it was on 2026-08-12.
CRASH_PATTERN: Final = re.compile(r"Session failed: Process exited with error (cse_[A-Za-z0-9]+)")
REFRESH_PATTERN: Final = re.compile(r"Failed to refresh session (cse_[A-Za-z0-9]+) token")
WORKTREE_PATTERN: Final = re.compile(r"kept worktree (\S+) · session crashed")


class Marker(NamedTuple):
    """One thing the wrapper saw, as `report` reads it back."""

    session: str
    server: str
    kind: str
    detail: str
    worktree: str
    detected_at: int
    acknowledged_at: int


def project_dir_name(worktree: str) -> str:
    """Claude Code's project-directory name for a working directory.

    Every character outside `[A-Za-z0-9]` becomes a hyphen, so
    `/home/andre/…/.claude/worktrees/bridge-cse_01Czi2G6…` is kept under
    `-home-andre-…--claude-worktrees-bridge-cse-01Czi2G6…`. Derived here rather
    than guessed at the call site: the rule folds `/`, `.` and `_` alike, and the
    doubled hyphen before `claude-worktrees` is the `/.` pair rather than a typo.
    """
    return re.sub(r"[^A-Za-z0-9]", "-", worktree)


def resume_command(worktree: str, projects_dir: Path) -> str:
    """Give the `claude --resume` line for a stranded worktree, or why there is none.

    The bridge names the worktree it kept but never the transcript inside it, and
    the transcript's own name is the session UUID a resume needs. The newest
    `.jsonl` in that project directory is that session — a crashed bridge session
    is the only writer there, and its file's mtime is the moment it died.

    An unresolvable transcript is said, never hidden: an orchestrator that is told
    nothing reads it as nothing to do, and the worktree is stranded either way.
    """
    directory = projects_dir / project_dir_name(worktree)
    transcripts = sorted(
        (path for path in directory.glob("*.jsonl") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
    )
    if not transcripts:
        return f"no transcript under {directory} — resume by hand"
    return f"claude --resume {transcripts[-1].stem}"


def slug(session: str) -> str:
    """One file per session id, with nothing in the name a path can act on."""
    cleaned = re.sub(r"[^A-Za-z0-9_.-]", "-", session).strip("-")
    return cleaned or "unnamed"


def marker_path(rc_health_dir: Path, session: str) -> Path:
    """Where one session's crash record lives."""
    return rc_health_dir / f"{slug(session)}.json"


def read_marker(path: Path) -> Marker | None:
    """Read one marker back, answering `None` for anything unreadable.

    Fail-quiet rather than fail-closed, and only here: this read is a report at
    the top of a turn, so a half-written file must not take out the breaker and
    queue lines printed beside it. The record it cannot parse stays on disk.
    """
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(document, dict):
        return None
    return Marker(
        session=str(document.get("session", "") or ""),
        server=str(document.get("server", "") or ""),
        kind=str(document.get("kind", "") or ""),
        detail=str(document.get("detail", "") or ""),
        worktree=str(document.get("worktree", "") or ""),
        detected_at=int(document.get("detected_at", 0) or 0),
        acknowledged_at=int(document.get("acknowledged_at", 0) or 0),
    )


def marker_document(marker: Marker) -> dict[str, object]:
    """Render a marker as the file the next turn reads."""
    return {
        "session": marker.session,
        "server": marker.server,
        "kind": marker.kind,
        "detail": marker.detail,
        "worktree": marker.worktree,
        "detected_at": marker.detected_at,
        "acknowledged_at": marker.acknowledged_at,
    }


def write_marker(rc_health_dir: Path, marker: Marker) -> Path:
    """Write one marker, creating the state directory on first use."""
    path = marker_path(rc_health_dir, marker.session)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(marker_document(marker), indent=2) + "\n", encoding="utf-8")
    return path


def record(rc_health_dir: Path, seen: Marker) -> Marker:
    """Record what the wrapper saw, letting a crash overwrite its own warning.

    A refresh failure and the crash minutes later are one session's story, so they
    share a file. The crash wins: `refresh_failed` arriving after `crashed` is the
    older news of the two and is dropped rather than downgrading the record. An
    acknowledgement already given is carried onto the warning but **not** onto the
    crash — a read warning must not silence the loss it turned out to precede.
    """
    previous = read_marker(marker_path(rc_health_dir, seen.session))
    is_crash = seen.kind == KIND_CRASHED
    if previous is not None and previous.kind == KIND_CRASHED and not is_crash:
        return previous
    marker = seen._replace(
        worktree=seen.worktree or (previous.worktree if previous else ""),
        acknowledged_at=(previous.acknowledged_at if previous is not None and not is_crash else 0),
    )
    write_marker(rc_health_dir, marker)
    return marker


def scan_text(text: str) -> tuple[Marker, ...]:
    """Read one batch of pane lines into the markers they carry, in order.

    The bridge names the worktree on its own third line rather than on the crash
    line, so a crash takes the worktree from the `kept worktree` line that follows
    it — the pair arrives in the same second and, on 2026-08-12, in the same batch.
    A crash whose companion line never arrives keeps an empty worktree rather than
    borrowing the previous crash's: two sessions dying in one batch is exactly when
    a wrong path would be most confidently reported.
    """
    seen: list[Marker] = []
    for line in text.splitlines():
        refresh = REFRESH_PATTERN.search(line)
        if refresh:
            seen.append(_blank(refresh.group(1), KIND_REFRESH_FAILED, line))
            continue
        crash = CRASH_PATTERN.search(line)
        if crash:
            seen.append(_blank(crash.group(1), KIND_CRASHED, line))
            continue
        kept = WORKTREE_PATTERN.search(line)
        if kept and seen and seen[-1].kind == KIND_CRASHED and not seen[-1].worktree:
            seen[-1] = seen[-1]._replace(worktree=kept.group(1))
    return tuple(seen)


def _blank(session: str, kind: str, line: str) -> Marker:
    """One parsed line, with the fields only the caller can fill left empty."""
    return Marker(
        session=session,
        server="",
        kind=kind,
        detail=line.strip(),
        worktree="",
        detected_at=0,
        acknowledged_at=0,
    )


def offset_path(rc_health_dir: Path, log: Path) -> Path:
    """Where `scan` remembers how far into one log it has already read."""
    return rc_health_dir / f"offset-{slug(log.name)}.txt"


def scan(rc_health_dir: Path, log: Path, *, server: str, now: int) -> tuple[Marker, ...]:
    """Read a pane log forward from where the last scan stopped, and record what is new.

    The offset is kept per log file rather than in memory, because the caller is a
    30-second shell loop that the wrapper's own restart interrupts: an offset in
    memory would replay the whole log as new findings every time systemd restarted
    the unit, and a crash already acknowledged would come back as news.

    A log shorter than the stored offset has been rotated, so the scan restarts at
    zero. That is the only rotation contract between this and the shell: the wrapper
    may rename or truncate whenever it likes, and the worst case is re-reading a file
    whose events `record` then folds onto the markers they already wrote.
    """
    if not log.is_file():
        return ()
    marker_file = offset_path(rc_health_dir, log)
    try:
        start = int(marker_file.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        start = 0
    size = log.stat().st_size
    if size < start:
        start = 0
    with log.open("r", encoding="utf-8", errors="replace") as handle:
        handle.seek(start)
        text = handle.read()
        stopped = handle.tell()
    marker_file.parent.mkdir(parents=True, exist_ok=True)
    marker_file.write_text(f"{stopped}\n", encoding="utf-8")
    return tuple(
        record(rc_health_dir, seen._replace(server=server, detected_at=now))
        for seen in scan_text(text)
    )


def stamp(epoch: int) -> str:
    """Render a local-time stamp, so a line reads against the box's own other logs."""
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(epoch))


def headline(marker: Marker, projects_dir: Path) -> str:
    """One line: what died, when, and the one command that gets it back."""
    where = f" on {marker.server}" if marker.server else ""
    if marker.kind != KIND_CRASHED:
        return (
            f"RC-WARN {marker.session}{where} could not refresh its token at "
            f"{stamp(marker.detected_at)} — the session is still alive; a crash "
            f"follows this line within minutes or nothing does"
        )
    resume = resume_command(marker.worktree, projects_dir) if marker.worktree else "resume by hand"
    kept = f" worktree kept at {marker.worktree};" if marker.worktree else ""
    return (
        f"RC-CRASH {marker.session}{where} was killed at {stamp(marker.detected_at)} "
        f"— the bridge could not refresh its session token.{kept} resume: {resume}"
    )


def unread(rc_health_dir: Path, *, include_read: bool) -> tuple[Marker, ...]:
    """Every marker worth printing, oldest first — nothing at all when clean."""
    if not rc_health_dir.is_dir():
        return ()
    markers = []
    for path in sorted(rc_health_dir.glob("*.json")):
        marker = read_marker(path)
        if marker is None or not marker.session:
            continue
        if marker.acknowledged_at and not include_read:
            continue
        markers.append(marker)
    return tuple(sorted(markers, key=lambda m: m.detected_at))


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Three verbs: record what the wrapper saw, report it, mark it read."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rc-health-dir",
        type=Path,
        default=Path(os.environ.get("CTI_RC_HEALTH_DIR", str(DEFAULT_RC_HEALTH_DIR))),
    )
    parser.add_argument(
        "--projects-dir",
        type=Path,
        default=Path(os.environ.get("CTI_CLAUDE_PROJECTS_DIR", str(DEFAULT_PROJECTS_DIR))),
    )
    parser.add_argument("--now", type=int, default=0)
    verbs = parser.add_subparsers(dest="verb", required=True)

    entry = verbs.add_parser("record", help="one thing the RC wrapper saw in its pane")
    entry.add_argument("--session", required=True)
    entry.add_argument("--server", default="")
    entry.add_argument("--kind", choices=KINDS, default=KIND_CRASHED)
    entry.add_argument("--detail", default="")
    entry.add_argument("--worktree", default="")

    sweep = verbs.add_parser("scan", help="read a pane log forward and record what is new")
    sweep.add_argument("--log", type=Path, required=True)
    sweep.add_argument("--server", default="")

    report = verbs.add_parser("report", help="one line per unread crash; silent when clean")
    report.add_argument("--ack", action="store_true", help="mark what is printed as read")
    report.add_argument("--all", action="store_true", help="include already-read records")

    ack = verbs.add_parser("ack", help="mark one session's record read")
    ack.add_argument("--session", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Record, report or acknowledge. Exit 0 throughout — this reads, never gates."""
    args = parse_args(argv)
    now = args.now or int(time.time())

    if args.verb == "record":
        marker = record(
            args.rc_health_dir,
            Marker(
                session=args.session,
                server=args.server,
                kind=args.kind,
                detail=args.detail,
                worktree=args.worktree,
                detected_at=now,
                acknowledged_at=0,
            ),
        )
        print(f"recorded={marker.session} kind={marker.kind}")  # noqa: T201 — the shell reads this
        return 0

    if args.verb == "scan":
        for marker in scan(args.rc_health_dir, args.log, server=args.server, now=now):
            # The wrapper's own journal line, so a crash is visible where the unit is
            # read as well as where `just watch-report` reads it.
            print(f"recorded={marker.session} kind={marker.kind}")  # noqa: T201 — for the journal
        return 0

    if args.verb == "ack":
        path = marker_path(args.rc_health_dir, args.session)
        marker = read_marker(path)
        if marker is not None:
            write_marker(args.rc_health_dir, marker._replace(acknowledged_at=now))
        return 0

    markers = unread(args.rc_health_dir, include_read=args.all)
    for marker in markers:
        print(headline(marker, args.projects_dir))  # noqa: T201 — the seat reads these lines
        if args.ack:
            write_marker(args.rc_health_dir, marker._replace(acknowledged_at=now))
    return 0


if __name__ == "__main__":
    sys.exit(main())
