"""Set the standard handles to blocking, then exec the named command (#678).

`ansible-playbook` refuses to start when any of stdin, stdout or stderr is
open non-blocking — the `check_blocking_io` precondition at the top of the
installed ansible/cli/__init__.py, before any playbook work. A dispatched
session's captured output presents exactly that arrangement, so the same
assertions passed or failed on who called the gate rather than on the tree
under test. The recipe satisfies the precondition instead of tripping it:
flipping the flag here is what a terminal or a file would already present,
and exec keeps the gate's own command, output and exit status unchanged.

The flag lives on the open file description, so a handle this process still
shares with its parent is flipped for the parent too; the parent of a
capturing harness reads the other end of the pipe, whose description is a
different one, and a harness that polls its own end reads nothing different.
"""

from __future__ import annotations

import os
import sys
from typing import Final

STANDARD_FDS: Final = (0, 1, 2)


def ensure_blocking(fds: tuple[int, ...] = STANDARD_FDS) -> list[int]:
    """Set each given descriptor to blocking; return the ones flipped."""
    flipped: list[int] = []
    for fd in fds:
        try:
            if not os.get_blocking(fd):
                os.set_blocking(fd, True)
                flipped.append(fd)
        except OSError:
            continue  # not an open descriptor; nothing to satisfy
    return flipped


def main(argv: list[str]) -> int:
    """Flip the standard handles to blocking, then become the named command."""
    if not argv:
        print("usage: blocking_exec.py COMMAND [ARGS...]", file=sys.stderr)  # noqa: T201 — stderr text IS this wrapper's output
        return 2
    ensure_blocking()
    try:
        os.execvp(argv[0], argv)  # noqa: S606 — no shell by design: argv is passed through untouched
    except FileNotFoundError:
        print(f"blocking_exec: command not found: {argv[0]}", file=sys.stderr)  # noqa: T201 — stderr text IS this wrapper's output
        return 127
    return 0  # unreachable; execvp only returns on failure


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
