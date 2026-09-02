"""Print the ADR review queue: the count and the file list (issue #351).

The count of `docs/adr/` ADRs carrying `Reviewed-by-human: pending` has been
over-reported 6-for-1 twice by the same trap: an unanchored grep for the
marker matches prose that quotes it in approved ADRs. Retro 15 made the error
inside the retro skill's step 3 and fixed it by anchoring the skill's text;
this cycle the orchestration seat made it again from outside the skill, and
retro 29 spent a finding withdrawing the fix that would have rewritten six
correct records (#316, finding 7). Two occurrences of one trap is
ADR-0038's escalation shape, and #209's rule applies: where a rule-table
already decides, an agent is not handed the job of remembering. So nobody
types the grep again — the anchored match lives here, once.

This is a report, not a gate: exit 0 whatever the count says, because a queue
with depth is the human's cadence to choose, not a failure. Surfacing the
size is the job (retro skill, step 3); clearing it is not.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Final

# Line-anchored, per ADR-0013: the marker is a field line, and only a field
# line counts. A prose mention — backticked, mid-sentence, quoted in a fenced
# grep example — never begins a line with the bare string, which is exactly
# the distinction the two 6-for-1 reports lost.
PENDING: Final = re.compile(r"^Reviewed-by-human: pending", re.MULTILINE)


def pending_lines(source: str) -> list[int]:
    """Line numbers of every `Reviewed-by-human: pending` field line."""
    return [source.count("\n", 0, match.start()) + 1 for match in PENDING.finditer(source)]


def pending_adrs(root: Path) -> list[tuple[str, list[int]]]:
    """Every ADR under `root`'s `docs/adr/` carrying a pending review.

    `rglob("*.md")` rather than a walk: `.claude/worktrees/` sits outside
    `docs/`, so no nested agent tree is scanned — the same reason
    `check_adr_form.adr_files` globs one directory.
    """
    queue: list[tuple[str, list[int]]] = []
    for path in sorted((root / "docs" / "adr").glob("*.md")):
        lines = pending_lines(path.read_text(encoding="utf-8"))
        if lines:
            queue.append((path.relative_to(root).as_posix(), lines))
    return queue


def render(queue: list[tuple[str, list[int]]]) -> str:
    """Render the count, then one ADR per line with the field line's number."""
    count = len(queue)
    plural = count != 1
    head = f"{count} ADR{'s' if plural else ''} await{'' if plural else 's'} human review"
    return "\n".join([head, *(f"{path}:{line}" for path, lines in queue for line in lines)])


def main(argv: list[str] | None = None) -> int:
    """Print the queue. Exit 0 whatever the depth: a report, not a gate."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".", type=Path)
    args = parser.parse_args(argv)

    print(render(pending_adrs(args.root.resolve())))  # noqa: T201 — the queue IS this script's output
    return 0


if __name__ == "__main__":
    sys.exit(main())
