"""Follow one dispatch to its recorded result without detaching (#280).

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
"""

from __future__ import annotations

import argparse
import json
import os
import select
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_DISPATCH_DIR = Path.home() / ".arma-cti" / "dispatches"
EXIT_FINDING = 1
EXIT_REFUSED = 2


@dataclass(frozen=True)
class FollowTarget:
    """The values the dispatcher recorded for one follower."""

    dispatch_id: str
    result_path: Path
    runner_pipe: Path


def arm_record(record: Path, runner_pid: int, runner_pipe: Path) -> None:
    """Add the authoritative follower fields to an existing dispatch record."""
    record = record.resolve()
    record_path = record / "dispatch.json"
    document: dict[str, Any] = json.loads(record_path.read_text(encoding="utf-8"))
    document["result_path"] = str(record / "result.json")
    document["runner_pid"] = runner_pid
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


def wait_for_runner(target: FollowTarget) -> None:
    """Stay attached until the recorded runner closes its pipe, with no time bound."""
    pipe_fd = os.open(target.runner_pipe, os.O_RDONLY | os.O_NONBLOCK)
    try:
        try:
            already_closed = os.read(pipe_fd, 1) == b""
        except BlockingIOError:
            already_closed = False
        if not already_closed:
            select.select((pipe_fd,), (), ())
    finally:
        os.close(pipe_fd)


def completion_lines(target: FollowTarget) -> tuple[str, ...]:
    """Render a completion using only values read from the dispatch record."""
    return (
        "completion=dispatch_result_written",
        f"dispatch={target.dispatch_id}",
        f"result={target.result_path}",
    )


def finding_lines(target: FollowTarget) -> tuple[str, ...]:
    """Render the ADR-0022 ending without inventing a result or failure class."""
    return (
        "finding=runner_disappeared",
        f"dispatch={target.dispatch_id}",
        f"result={target.result_path}",
        "action=inspect the dispatch log and use just watch for stall classification",
    )


def follow(target: FollowTarget) -> tuple[int, tuple[str, ...]]:
    """Follow one target to a recorded completion or a disappeared-runner finding."""
    if target.result_path.is_file():
        return 0, completion_lines(target)
    wait_for_runner(target)
    if target.result_path.is_file():
        return 0, completion_lines(target)
    return EXIT_FINDING, finding_lines(target)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the public follow form and the dispatcher's internal arm form."""
    parser = argparse.ArgumentParser(prog="dispatch-follow", description=__doc__)
    parser.add_argument("dispatch_id", nargs="?", default="")
    parser.add_argument(
        "--dispatch-dir",
        type=Path,
        default=Path(os.environ.get("CTI_DISPATCH_DIR", str(DEFAULT_DISPATCH_DIR))),
    )
    parser.add_argument("--arm-record", type=Path)
    parser.add_argument("--runner-pid", type=int, default=0)
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
    if args.runner_pid <= 0 or args.runner_pipe is None:
        return emit(("refusal=runner_identity_missing",), EXIT_REFUSED)
    try:
        arm_record(args.arm_record, args.runner_pid, args.runner_pipe)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        return emit(
            ("refusal=dispatch_follow_arm_failed", f"detail={error}"),
            EXIT_REFUSED,
        )
    return 0


def follow_from_args(args: argparse.Namespace) -> int:
    """Read and follow one public dispatch request."""
    if not args.dispatch_id:
        return emit(("refusal=dispatch_id_missing",), EXIT_REFUSED)
    try:
        target = read_target(args.dispatch_dir, args.dispatch_id)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        return emit(
            (
                "refusal=dispatch_follow_unavailable",
                f"dispatch={args.dispatch_id}",
                f"detail={error}",
            ),
            EXIT_REFUSED,
        )
    try:
        code, lines = follow(target)
    except OSError as error:
        return emit(
            (
                "refusal=runner_unobservable",
                f"dispatch={target.dispatch_id}",
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
