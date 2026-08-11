"""Form checks over ADRs: the delegated-decision block, and the supersession trailer.

Two conventions, checked here for the same reason. The first (ADR-0019, issue
#137) binds an ADR carrying `Delegated-decision: yes`; the second (ADR-0071)
binds any ADR from 0071 onward that takes a prior ruling out of force, whoever
decided it.


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
# So the line must also name what is being taken out of force.
#
# The verb list is wide on purpose, and it was not at first. A narrow
# `rescind|supersede` pair missed every one of ADR-0071's four principal
# withdrawals, because that ADR says "withdrawn" — the check fired on one
# incidental sentence and looked like it worked. An independent review found it;
# no gate could have.
RESCISSION: Final = re.compile(
    r"\b(?:rescind|supersed|withdraw|amend|repeal|replace)\w*\b", re.IGNORECASE
)
GOVERNANCE: Final = re.compile(r"\b(?:ADR-\d{4}|decisions?|rulings?)\b", re.IGNORECASE)

# Shallow, and the limit is stated rather than hidden: a line saying a ruling is
# *not* superseded, or *may* be one day, reads the same to a regex as one saying
# it is. Skipping the obvious negations costs nothing and catches the common
# phrasings; a determined false positive is answered by writing the trailer,
# which is cheap and true.
NEGATED: Final = re.compile(r"\b(?:not|never|nothing|neither|without)\b", re.IGNORECASE)

# The trailer belongs in the field block, which in this corpus is the run of
# `Key: value` lines between the title and the first `##` section. Anchoring
# there is what makes the convention a grep: a `Supersedes:` line inside a body
# paragraph or a fenced example would satisfy an unanchored search while
# answering no question a reader actually has.
#
# `[^\S\n]` rather than `\s` for the same reason `REVIEWED` uses it — under
# MULTILINE, `\s` steps over the newline and an empty trailer reads as a filled
# one.
SUPERSEDES: Final = re.compile(r"^Supersedes:[^\S\n]*\S", re.MULTILINE)
SECTION: Final = re.compile(r"^##\s", re.MULTILINE)

# The convention starts at ADR-0071, which adopted it. Twenty earlier ADRs amend
# or supersede an earlier ruling in their prose — 0005, 0008, 0012, 0013, 0017,
# 0018, 0019, 0023, 0024, 0028, 0031, 0036, 0038, 0039, 0040, 0042, 0044, 0045,
# 0047, 0053 among them — and retrofitting a trailer into that many
# human-signed-off records to satisfy a rule written after them is not
# proportionate.
#
# This started life as a named exemption list in the `NO_MUTABLE_SUBJECT` shape
# and that was the wrong borrowing, which the same review caught: a named list
# names exceptions to a rule that otherwise applies, and here the rule simply did
# not exist yet. Three entries also looked complete and were not — they were the
# three a too-narrow detector happened to see. A number is honest about being a
# start date, and cannot quietly grow.
CONVENTION_FROM: Final = 71
ADR_NUMBER: Final = re.compile(r"^(\d{4})-")


def governed(path: str) -> bool:
    """Whether this ADR is new enough for the trailer convention to bind it."""
    found = ADR_NUMBER.match(path.rsplit("/", 1)[-1])
    return found is not None and int(found.group(1)) >= CONVENTION_FROM


def rescinds_a_ruling(source: str) -> bool:
    """Whether any one line both rescinds and names what it rescinds."""
    return any(
        RESCISSION.search(line) and GOVERNANCE.search(line) and not NEGATED.search(line)
        for line in source.splitlines()
        if not line.lstrip().startswith("Supersedes:")
    )


def field_block(source: str) -> str:
    """Return the header above the first `##` section, where the trailers live."""
    found = SECTION.search(source)
    return source[: found.start()] if found else source


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
    if not governed(path):
        return []
    if not rescinds_a_ruling(source) or SUPERSEDES.search(field_block(source)):
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
