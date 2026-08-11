"""Form checks over ADRs: the delegated-decision block, and the supersession trailer.

Two conventions, checked here for the same reason — a rule nothing enforces is a
rule that goes missing. The first (ADR-0019, issue #137) binds an ADR carrying
`Delegated-decision: yes`. The second (ADR-0071) binds every ADR from 0071
onward, whoever decided it.

ADR-0019 requires that a delegated decision state what evidence would overturn
it, because that is what makes a post-hoc ratification auditable rather than
self-sealing: the reviewer can disagree by pointing at the evidence the ADR
named. It also gives the field block a `Reviewed-by-human:` line, which is the
human's outstanding-review worklist. Nothing detected either — three ADRs (0016,
0030, 0036) reached a guided review of all twenty-nine delegated decisions
without an overturning-evidence section, found only because one sitting read all
of them, which is not a repeatable mechanism.

**The supersession check does not read prose, and that is its whole design.**
Three earlier versions tried to decide from the body whether an ADR took a prior
ruling out of force, and three independent reviews defeated each in turn: a
narrow `rescind|supersede` pair missed every one of ADR-0071's own withdrawals,
which say "withdrawn"; widening it still missed "deleted", "dropped",
"overturned" and "retired"; requiring a governance noun on the same line missed
"the Model roles mapping is replaced" and broke on line wrapping; a negation
guard then discarded "withdrawn *without* changing decision 5". Each version
looked like it worked because it fired on something.

So the trigger is gone. **Every ADR from 0071 carries a `Supersedes:` line** —
one per superseded target, or the single line `Supersedes: none`. That is exactly
checkable, has no vocabulary, wrapping or negation to defeat, and costs one line
in each new ADR. One target per line rather than a wrapped list, because the
convention's promise is that `rg '^Supersedes:'` returns the amended set, and a
continuation line does not answer that grep.

Deliberately shallow throughout. It asks whether the words are there, in the
right part of the file; it cannot ask whether the evidence named is any good or
whether the supersession list is complete, and those judgements stay the human's
at review.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Final, NamedTuple

# `[^\S\n]` and not `\s`: under MULTILINE, `\s` would step over the newline and
# find the next paragraph, so an empty field would read as a filled one.
MARKER: Final = re.compile(r"^Delegated-decision:[^\S\n]*yes[^\S\n]*$", re.MULTILINE)
REVIEWED: Final = re.compile(r"^Reviewed-by-human:[^\S\n]*\S", re.MULTILINE)
SUPERSEDES: Final = re.compile(r"^Supersedes:[^\S\n]*\S", re.MULTILINE)
OVERTURN: Final = re.compile(r"overturn", re.IGNORECASE)

# The field block is the first unbroken run of non-blank lines after the title,
# and it is defined that way rather than "up to the first `##`" because nine ADRs
# in this corpus have no `##` at all — 0013, 0014, 0015, 0016, 0017, 0019, 0020,
# 0023 and 0025 are short prose records. Sectioning would have given every one of
# them an empty body and failed them all, which is how this definition was found.
# It also tolerates a wrapped field value, which ADR-0070's four-line
# `Reviewed-by-human:` needs.
#
# Anchoring the field regexes here is what stops a fenced example or a body
# paragraph from satisfying them — the failure ADR-0013 cares about most, since
# `Reviewed-by-human:` in body prose would drop an ADR off the human's pending
# worklist without a human ever seeing it.
FENCE: Final = re.compile(r"^[^\S\n]*(?:```|~~~).*?^[^\S\n]*(?:```|~~~)", re.MULTILINE | re.DOTALL)
FIELD: Final = re.compile(r"^[A-Z][A-Za-z-]*:")

# The convention starts at the ADR that adopted it. Twenty earlier ADRs amend or
# supersede a ruling in their prose, and retrofitting a trailer into that many
# human-signed-off records to satisfy a rule written after them is not
# proportionate.
#
# Known gap, stated rather than hidden: the cutoff is on the file's number, which
# is fixed at creation, so an ADR below it that is *later* amended to withdraw
# something is not covered. Closing that would mean reading git history in a form
# check, which is a worse trade than the gap.
CONVENTION_FROM: Final = 71
ADR_NUMBER: Final = re.compile(r"^(\d{4})-")


class Finding(NamedTuple):
    """One ADR missing a line one of the two conventions requires."""

    path: str
    missing: str
    remedy: str

    def __str__(self) -> str:
        """Render as an editor-clickable location."""
        return f"{self.path}:1: no {self.missing}. {self.remedy}"


def strip_fences(source: str) -> str:
    """Return `source` with fenced code blocks removed."""
    return FENCE.sub("", source)


def _split(source: str) -> tuple[list[str], list[str]]:
    """Return the field-block lines and the body lines, fenced examples removed."""
    lines = strip_fences(source).splitlines()
    start = 0
    while start < len(lines) and (not lines[start].strip() or lines[start].startswith("#")):
        start += 1

    # Consume blank-line-separated chunks for as long as each still carries a
    # field. ADR-0031's block has a blank line inside it — `Stood-in-for:`, a gap,
    # then `Reviewed-by-human:` — so a single unbroken run is not enough, and a
    # single chunk would have failed it.
    end = start
    while end < len(lines):
        stop = end
        while stop < len(lines) and lines[stop].strip():
            stop += 1
        chunk = lines[end:stop]
        if not chunk or not any(FIELD.match(line) for line in chunk):
            break
        end = stop
        while end < len(lines) and not lines[end].strip():
            end += 1
    return lines[start:end], lines[end:]


def field_block(source: str) -> str:
    """Return the field block: the first unbroken run of lines after the title."""
    return "\n".join(_split(source)[0])


def body(source: str) -> str:
    """Return everything after the field block."""
    return "\n".join(_split(source)[1])


def governed(path: str) -> bool:
    """Return whether the supersession convention binds this ADR."""
    found = ADR_NUMBER.match(path.rsplit("/", 1)[-1])
    return found is not None and int(found.group(1)) >= CONVENTION_FROM


def scan_source(source: str, path: str) -> list[Finding]:
    """Report what `source` lacks under both conventions."""
    header = field_block(source)
    findings: list[Finding] = []

    if governed(path) and not SUPERSEDES.search(header):
        findings.append(
            Finding(
                path,
                "`Supersedes:` line",
                "Every ADR from 0071 carries one per superseded ruling, or "
                "`Supersedes: none` — so the amended set is a grep (ADR-0071).",
            )
        )

    if not MARKER.search(header):
        return findings
    if not OVERTURN.search(body(source)):
        findings.append(
            Finding(
                path,
                "overturning evidence",
                "ADR-0019 requires a delegated decision to state what evidence "
                "would overturn each decision it takes.",
            )
        )
    if not REVIEWED.search(header):
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
    """Report every ADR under `root` missing a line either convention requires."""
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
