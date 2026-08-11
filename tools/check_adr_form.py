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

# The second convention this module checks, and it arrived the same way the
# first did. ADR-0071 adopted a `Supersedes:` field-block trailer so that "tell
# me every ruling that has been amended" is a grep, the way
# `Delegated-decision: yes` already answers "tell me every decision made on my
# behalf". Its own first draft then claimed this check existed before it did —
# caught by an independent review, not by a sitting. So the check lands with the
# convention, which is what `AGENTS.md` asks for and what the first draft broke.
#
# The trigger is two words on one line, not one word anywhere. The verb alone is
# too broad: this project's domain uses it — ADR-0005 says a presence report
# "supersedes" the one before it, which is about reports and not about rulings.
# So the line must also name what is being taken out of force. ADR-0005's own
# real supersession, "two clauses above are superseded", names no ruling either,
# and correctly does not fire: an ADR amending itself is not what the trailer is
# for.
#
# `SUPERSEDES` uses `[^\S\n]` rather than `\s` for the same reason `REVIEWED`
# does — under MULTILINE, `\s` steps over the newline and an empty trailer would
# read as a filled one.
RESCISSION: Final = re.compile(
    r"\b(?:rescind(?:s|ed|ing)?|supersed(?:e|es|ed|ing))\b", re.IGNORECASE
)
GOVERNANCE: Final = re.compile(r"\b(?:ADR-\d{4}|decisions?|rulings?)\b", re.IGNORECASE)
SUPERSEDES: Final = re.compile(r"^Supersedes:[^\S\n]*\S", re.MULTILINE)


# The three ADRs that superseded something before the trailer existed, each with
# its reason beside it and visible in the diff — the shape `mutation_smoke.py`'s
# `NO_MUTABLE_SUBJECT` uses. Retrofitting the trailer would mean editing three
# human-signed-off ADRs to satisfy a convention written after them; naming them
# here costs nothing and makes the pre-convention supersessions discoverable,
# which a silent cutoff would not. A fourth entry is a visible diff, so this
# cannot grow quietly.
PRE_CONVENTION: Final[dict[str, str]] = {
    "0005-rust-arma-rs-shim.md": (
        "records being superseded *by* ADR-0018, retroactively. The trailer is "
        "for the ADR doing the superseding, which is 0018."
    ),
    "0031-the-commander-multiplies-considerations-rather-than-summing-weights.md": (
        "supersedes ADR-0014's mechanism, 2026-07-31, five days before the trailer was adopted."
    ),
    "0066-the-landed-initiative-rulings-get-their-adr-and-two-corrections-are-recorded.md": (
        "amends passages of ADR-0061, 2026-08-08, three days before adoption."
    ),
}


def rescinds_a_ruling(source: str) -> bool:
    """Whether any one line both rescinds and names what it rescinds."""
    return any(
        RESCISSION.search(line) and GOVERNANCE.search(line)
        for line in source.splitlines()
        if not line.lstrip().startswith("Supersedes:")
    )


class Finding(NamedTuple):
    """One delegated-decision ADR missing a line ADR-0019 requires."""

    path: str
    missing: str
    remedy: str

    def __str__(self) -> str:
        """Render as an editor-clickable location."""
        return f"{self.path}:1: no {self.missing}. {self.remedy}"


def supersession_failures(source: str, path: str) -> list[Finding]:
    """Report a rescinding ADR that names nothing in a `Supersedes:` trailer.

    Independent of the delegated-decision marker: ADR-0071 is
    `Delegated-decision: no` — every ruling in it was the human's, taken in
    session — and it rescinds four decisions of ADR-0061, so it needs the
    trailer for a reason that has nothing to do with who decided.
    """
    if path.rsplit("/", 1)[-1] in PRE_CONVENTION:
        return []
    if not rescinds_a_ruling(source) or SUPERSEDES.search(source):
        return []
    return [
        Finding(
            path,
            "`Supersedes:` line",
            "An ADR that takes a prior ruling out of force names it in the "
            "field block, so the amended set is a grep (ADR-0071).",
        )
    ]


def scan_source(source: str, path: str) -> list[Finding]:
    """Report what `source` lacks: its supersessions, and its delegated form."""
    findings = supersession_failures(source, path)
    if not MARKER.search(source):
        return findings
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
