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
"""

from __future__ import annotations

import argparse
import json
import os
import select
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

DEFAULT_DISPATCH_DIR = Path.home() / ".arma-cti" / "dispatches"
EXIT_FINDING = 1
EXIT_REFUSED = 2


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


def completion_lines(target: FollowTarget, pending: Sequence[str] = ()) -> tuple[str, ...]:
    """Render a completion using only values read from the dispatch record."""
    return (
        "completion=dispatch_result_written",
        f"dispatch={target.dispatch_id}",
        f"result={target.result_path}",
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


def follow_first(targets: Sequence[FollowTarget]) -> tuple[int, tuple[str, ...]]:
    """Follow every target to whichever ends first, naming the rest as pending."""
    for target in targets:
        if target.result_path.is_file():
            return 0, completion_lines(target, pending_ids(targets, target))
    first = wait_for_first(targets)
    pending = pending_ids(targets, first)
    if first.result_path.is_file():
        return 0, completion_lines(first, pending)
    return EXIT_FINDING, finding_lines(first, pending)


def follow(target: FollowTarget) -> tuple[int, tuple[str, ...]]:
    """Follow one target to a recorded completion or a disappeared-runner finding."""
    return follow_first((target,))


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
    try:
        code, lines = follow_first(targets)
    except OSError as error:
        return emit(
            (
                "refusal=runner_unobservable",
                f"dispatch={','.join(requested)}",
                f"detail={error}",
            ),
            EXIT_REFUSED,
        )
    return emit(lines, code)


def main(argv: list[str] | None = None) -> int:
    """Arm a dispatch record internally, or follow one named dispatch publicly."""
    args = parse_args(argv)
    return arm_from_args(args) if args.arm_record is not None else follow_from_args(args)


if __name__ == "__main__":
    sys.exit(main())
