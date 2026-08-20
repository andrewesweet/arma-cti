"""Refuse `Bash(just ...)` grants that name no just recipe (#448).

This check is deliberately one-way. An ungranted recipe may be orchestrator-only, so
requiring every recipe to have a grant would widen dispatched-session permissions rather
than validate them.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Final

GRANT: Final = re.compile(r"^Bash\(just\s+(?P<recipe>[^\s:)]+)(?::\*)?(?:\s+[^)]*)?\)$")


def defined_recipes(justfile: Path) -> set[str]:
    """Return recipe and alias names from just's own parser."""
    completed = subprocess.run(  # noqa: S603 — fixed command; path is not shell-expanded
        [  # noqa: S607 — the repository's required `just` binary resolves from PATH
            "just",
            "--dump",
            "--dump-format",
            "json",
            "--justfile",
            str(justfile),
        ],
        cwd=justfile.parent,
        check=True,
        capture_output=True,
        text=True,
    )
    document = json.loads(completed.stdout)
    return set(document["recipes"]) | set(document["aliases"])


def failures(settings: Path, justfile: Path) -> list[str]:
    """Name every grant whose recipe just does not define."""
    document = json.loads(settings.read_text(encoding="utf-8"))
    allowed = document.get("permissions", {}).get("allow", [])
    defined = defined_recipes(justfile)
    missing: list[str] = []
    for grant in allowed:
        match = GRANT.fullmatch(grant)
        if match and match["recipe"] not in defined:
            recipe = match["recipe"]
            missing.append(f"`{grant}` grants `{recipe}`, which `{justfile.name}` does not define")
    return missing


def main(argv: list[str] | None = None) -> int:
    """Check the repository paths, with path overrides for the negative test."""
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", type=Path, default=root / ".claude" / "settings.json")
    parser.add_argument("--justfile", type=Path, default=root / "justfile")
    args = parser.parse_args(argv)
    found = failures(args.settings.resolve(), args.justfile.resolve())
    for failure in found:
        print(failure, file=sys.stderr)  # noqa: T201 — the check speaks to its runner
    return bool(found)


if __name__ == "__main__":
    raise SystemExit(main())
