"""`just check-source-link`: `CLAUDE.md` is a symlink to `AGENTS.md`, never a copy.

`AGENTS.md` is the sole source and `CLAUDE.md` is a committed symlink to it (human
ruling on #221, Decision 2; landed by #264). The arrangement is one `git checkout`
on a hostile platform, one editor that "helpfully" replaces links, or one tool that
writes the path in place away from silently becoming two divergent files — and the
divergence would be invisible, because both names would still read.

So the property is asserted rather than assumed, and it is asserted **in the index**
as well as on disk: a working tree can be checked out with `core.symlinks=false` and
still be correct upstream, but a regular-file blob in the index means the ruling has
actually been undone for everybody.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SOURCE = "AGENTS.md"
LINK = "CLAUDE.md"
SYMLINK_MODE = "120000"


def index_mode(root: Path, path: str) -> str:
    """Return the mode git records for `path`, or an empty string when untracked."""
    proc = subprocess.run(  # noqa: S603 — a fixed argv with no caller input
        ["git", "ls-files", "--stage", "--", path],  # noqa: S607 — git off PATH, as elsewhere
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.split(" ", 1)[0] if proc.stdout.strip() else ""


def failures(root: Path) -> list[str]:
    """Every way the arrangement can be wrong, named one per line."""
    found: list[str] = []
    source, link = root / SOURCE, root / LINK
    if not source.is_file():
        found.append(f"{SOURCE} is missing: it is the sole source (#264, #221 decision 2)")
    mode = index_mode(root, LINK)
    if mode != SYMLINK_MODE:
        found.append(
            f"{LINK} is mode {mode or 'absent'} in the index, not {SYMLINK_MODE}:"
            f" it must be a committed symlink to {SOURCE}, never a copy"
        )
    if link.is_symlink():
        target = link.readlink()
        if str(target) != SOURCE:
            found.append(f"{LINK} points at {target}, not {SOURCE}")
    elif link.exists():
        found.append(f"{LINK} is a regular file on disk: the symlink has been replaced")
    return found


def main() -> int:
    """Print each failure, or nothing at all when the arrangement holds."""
    root = Path(__file__).resolve().parents[1]
    found = failures(root)
    for line in found:
        print(line, file=sys.stderr)  # noqa: T201 — the check speaks to its runner
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
