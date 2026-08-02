"""Form checks for delegated-decision ADRs (ADR-0019, issue #137).

ADR-0019 requires that an ADR carrying `Delegated-decision: yes` state what
evidence would overturn each decision it takes, because that is what makes a
post-hoc ratification auditable rather than self-sealing: the reviewer can
disagree by pointing at the evidence the ADR named. It also gives the field
block a `Reviewed-by-human:` line, which is the human's outstanding-review
worklist.

Nothing detected either. Three ADRs (0016, 0030, 0036) reached a guided review
of all twenty-nine delegated decisions without an overturning-evidence section,
and were found only because one sitting read all of them — which is not a
repeatable mechanism. This is the check that is.

Deliberately shallow. It asks whether the words are there, in the file, at all;
it cannot ask whether the evidence named is any good, and that judgement stays
the human's at review. The heading's wording is not fixed either — the corpus
spells it `## What would overturn this`, `## Overturned by`, `**What would
overturn each decision**` and, in ADR-0014, as prose per decision — so the test
is the word itself outside the field block, which is what the review's own grep
asked.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Final, NamedTuple

MARKER: Final = re.compile(r"^Delegated-decision:\s*yes\s*$", re.MULTILINE)
# `[^\S\n]` and not `\s`: under MULTILINE, `\s` would step over the newline and
# find the next paragraph, so an empty field would read as a filled one.
REVIEWED: Final = re.compile(r"^Reviewed-by-human:[^\S\n]*\S", re.MULTILINE)
OVERTURN: Final = re.compile(r"overturn", re.IGNORECASE)


class Finding(NamedTuple):
    """One delegated-decision ADR missing a line ADR-0019 requires."""

    path: str
    missing: str
    remedy: str

    def __str__(self) -> str:
        """Render as an editor-clickable location."""
        return f"{self.path}:1: no {self.missing}. {self.remedy}"


def scan_source(source: str, path: str) -> list[Finding]:
    """Report what `source` lacks, if it is a delegated decision at all."""
    if not MARKER.search(source):
        return []
    findings = []
    if not OVERTURN.search(source):
        findings.append(
            Finding(
                path,
                "overturning evidence",
                "ADR-0019 requires a delegated decision to state what evidence "
                "would overturn each decision it takes.",
            )
        )
    if not REVIEWED.search(source):
        findings.append(
            Finding(
                path,
                "`Reviewed-by-human:` line",
                "Write it `pending`; only the human flips it to a date.",
            )
        )
    return findings


def adr_files(root: Path) -> list[Path]:
    """Every ADR in this checkout.

    Not recursive: `docs/adr/` is flat, and a glob that walked would pick up
    the nested agent worktrees under `.claude/`, which run this gate on their
    own trees.
    """
    return sorted((root / "docs" / "adr").glob("*.md"))


def scan_tree(root: Path) -> list[Finding]:
    """Report every delegated-decision ADR under `root` missing a required line."""
    findings: list[Finding] = []
    for path in adr_files(root):
        relative = path.relative_to(root).as_posix()
        findings.extend(scan_source(path.read_text(encoding="utf-8"), relative))
    return findings


def main(argv: list[str] | None = None) -> int:
    """Check the tree and print one line per finding."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".", type=Path)
    args = parser.parse_args(argv)

    findings = scan_tree(args.root.resolve())
    for finding in findings:
        print(finding, file=sys.stderr)  # noqa: T201
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
