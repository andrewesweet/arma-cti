"""`just check-arbiter`: nothing restates the arbiter walk except its authority (#390).

`tools/arbiter.py` is the authoritative surface for who arbitrates when a review
loop runs out of rounds. Every other surface that told a reader what that walk
does was a copy, and the copies drifted: `dispatch.escalation_head`'s docstring
said the conflicted-head fall-through was unbuilt while citing, as its authority,
the very ADR passage the same round had rewritten to say it was built.
arbiter-rule: stated — this module's rationale records the exact drift #390 prevents.

**Why this is a derived check rather than a better list.** The enumeration of
those copies was wrong at every count anyone made on #361 — round 1 wrote a false
statement, round 2 corrected four surfaces and left a fifth, an arbiter upheld
that and ruled the enumeration itself the defect, round 3 asserted in the ADR that
it had *derived* the set with two named greps and a sixth site stood 140 lines
above the fifth in the same file, and the compliance check found a seventh. Five
counts, five wrong. The second-order instance is the same shape one level up: a
sweep brief told a round to grep `config/`, `docs/`, `AGENTS.md` and `tools/`, and
the copy that survived sat in `tests/`. So the subject set here is **every tracked
file**, from `git ls-files`, with no path list to be incomplete — not the
directories anyone remembered.

**The rule, on the human's ruling of 2026-08-16 (design 2, the #361 arbiter's own
recommendation — "a copy that cannot drift beats a copy under surveillance"):** a
site that states what the walk does is cut to a pointer at `tools/arbiter.py`.
Where the prose genuinely must state the rule — a dated record in `CHANGELOG.md`
or an ADR amendment, the authority's own executable assertions — design 1 stays
available and the site carries `arbiter-rule: stated — <reason>`, which this gate
enumerates rather than recalls.

**What a site is.** In Python, one comment run or one paragraph of one string
token, so a claim in a class-body comment is not covered by a pointer eighty lines
down the same class. Elsewhere, one blank-line paragraph, split further at
top-level list items so one marked changelog bullet does not license its
neighbours. Granularity is the whole mechanism: the #361 sixth site was missed
because a reader took a file to be one place.

**What this deliberately does not check.** Whether a marked statement is *true* —
the marker records that a human chose to state the rule here, not that the
statement survives reading `tools/arbiter.py`. And whether an unmarked site that
cites the authority without stating it is a *good* pointer: silence here means
only that nothing checkable was left to drift.
"""

from __future__ import annotations

import argparse
import io
import re
import subprocess
import sys
import token
import tokenize
from pathlib import Path
from typing import Final, NamedTuple

# The one surface allowed to state the rule, because it is the rule: the walk,
# its exclusion rungs and its two named refusals are code here, not prose about
# code. Every finding names it, so a reader lands on the authority rather than on
# whichever copy they happened to open (#390 acceptance criterion 5).
AUTHORITY: Final = "tools/arbiter.py"

# Is this site about the arbiter walk at all? "escalation entry" and "escalation
# column" are deliberately absent: `resolve_seat`'s own walk reads the same
# registry columns and is a *different* resolution, so naming a column is not
# naming this rule. The arbiter is.
CONTEXT: Final = re.compile(r"arbiter|_walk\b|_walk_first|escalation_head", re.IGNORECASE)
# Does it state what the walk *does*? These are the predicates that drifted
# across #361's five rounds: the fall-through, and the order of the entry's two
# profiles. "Refuses by name" is deliberately not among them — every tool in this
# repository refuses by name, so it is house vocabulary rather than this rule's,
# and matching it marked changelog bullets that never mention the walk. The cost
# is stated: a copy that gets the empty column's answer wrong, and gets it wrong
# in no other way, is not caught here.
CLAIM: Final = re.compile(
    r"entry (?:head|tail)|fall(?:s|ing)?[ -]through|fell through|head first",
    re.IGNORECASE,
)
# Design 1's escape, with its reason beside it and visible in the diff — the
# `NO_MUTABLE_SUBJECT` shape (ADR-0064). An em dash and a reason are required:
# a bare marker is an exclusion wearing a marker's hat.
MARKER: Final = re.compile(r"arbiter-rule: stated — (\S.*)")

REMEDY: Final = (
    f"Cut it to a pointer at {AUTHORITY}, or, where the prose must state the rule, "
    "mark the site `arbiter-rule: stated — <reason>` (#390, on the human ruling of "
    "2026-08-16 and the #361 arbitration of 2026-08-15)."
)

# A blank line is not the only boundary a reader sees. A changelog bullet and a
# command-table row are each a place of their own, and treating the list or the
# table as one place is the file-is-one-place mistake at a smaller scale — it
# would let one marked row license every row around it.
# Indentation changes presentation, not document structure: every list item and
# table row still starts a new site.
NEW_SITE: Final = re.compile(r"^\s*(?:[-*+] |\d+[.)] |\|)")


class Site(NamedTuple):
    """One place a reader meets prose, with the line its body starts on."""

    path: str
    line: int
    body: str

    def claim_line(self) -> int:
        """Return the line the claim sits on, not the line the site opens on."""
        match = CLAIM.search(self.body)
        return self.line if match is None else self.line + self.body.count("\n", 0, match.start())


class Finding(NamedTuple):
    """One site that states the arbiter rule with nothing recording the choice."""

    path: str
    line: int
    problem: str
    remedy: str = REMEDY

    def __str__(self) -> str:
        """Render as an editor-clickable location."""
        return f"{self.path}:{self.line}: {self.problem}. {self.remedy}"


def _paragraphs(body: str, path: str, first_line: int) -> list[Site]:
    """Split prose into blank-line paragraphs, then at list items and table rows.

    The second split is what keeps a marked changelog bullet from covering the
    bullets around it — the file-is-one-place mistake that hid #361's sixth copy,
    in the granularity where a human-curated list makes it easiest to repeat.
    """
    sites: list[Site] = []
    start: int | None = None
    lines = body.splitlines()
    for index, line in enumerate(lines):
        if not line.strip():
            if start is not None:
                sites.append(Site(path, first_line + start, "\n".join(lines[start:index])))
                start = None
            continue
        if start is not None and NEW_SITE.match(line):
            sites.append(Site(path, first_line + start, "\n".join(lines[start:index])))
            start = index
        elif start is None:
            start = index
    if start is not None:
        sites.append(Site(path, first_line + start, "\n".join(lines[start:])))
    return sites


def _python_sites(source: str, path: str) -> list[Site] | None:
    """Every comment run and string paragraph in a Python file, or `None` if unparsable.

    Comment runs merge only across consecutive lines, so a comment above one
    registry column is a different site from the comment above the next — which
    is the distinction #361's sixth and fifth copies needed and did not get.
    """
    sites: list[Site] = []
    pending: list[str] = []
    pending_at = 0
    last = -2
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return None
    for item in tokens:
        if item.type == token.COMMENT:
            if item.start[0] != last + 1:
                if pending:
                    sites.append(Site(path, pending_at, "\n".join(pending)))
                pending, pending_at = [], item.start[0]
            pending.append(item.string)
            last = item.start[0]
        elif item.type == token.STRING:
            sites.extend(_paragraphs(item.string, path, item.start[0]))
    if pending:
        sites.append(Site(path, pending_at, "\n".join(pending)))
    return sites


def sites_in(source: str, path: str) -> list[Site]:
    """Every site in one file, at the granularity that file's syntax supports."""
    if path.endswith(".py"):
        python = _python_sites(source, path)
        if python is not None:
            return python
    return _paragraphs(source, path, 1)


def marker_reason(site: Site, source: str, path: str) -> str | None:
    """Return the reason recorded for stating the rule here, or `None` where none is.

    In Python the marker may also sit on the line above or below the site: a
    docstring or a printed string cannot carry one inside it without changing what
    the program says, so the only place left is the code around it. Prose is under
    no such constraint, so there the marker is in the site or nowhere — a wider
    window over a markdown table would let one row's marker cover the rows either
    side of it, which is the granularity mistake this gate exists to catch.
    """
    body = site.body
    if path.endswith(".py"):
        lines = source.splitlines()
        end = site.line + body.count("\n")
        above = lines[site.line - 2] if site.line > 1 else ""
        below = lines[end] if end < len(lines) else ""
        body = f"{above}\n{body}\n{below}"
    match = MARKER.search(body)
    return match.group(1).strip() if match else None


def claim_sites(source: str, path: str) -> list[Site]:
    """Every site in `source` that states what the walk does, marked or not."""
    return [
        site
        for site in sites_in(source, path)
        if CONTEXT.search(site.body) and CLAIM.search(site.body)
    ]


def scan_source(source: str, path: str) -> list[Finding]:
    """Report every site in `source` that states the arbiter rule unmarked."""
    if path == AUTHORITY:
        return []
    return [
        Finding(
            path,
            site.claim_line(),
            f"states what {AUTHORITY}'s walk does, and nothing here records that choice",
        )
        for site in claim_sites(source, path)
        if marker_reason(site, source, path) is None
    ]


def stated_in(source: str, path: str) -> list[tuple[Site, str]]:
    """Every marked restatement in `source`, with its reason — design 1's escape."""
    if path == AUTHORITY:
        return []
    marked = ((site, marker_reason(site, source, path)) for site in claim_sites(source, path))
    return [(site, reason) for site, reason in marked if reason is not None]


def tracked_files(root: Path) -> list[str]:
    """Every tracked file, which is this gate's whole subject set.

    Derived rather than listed, and the point of the issue: a checker with a
    hand-maintained list of places to look reproduces the defect it checks for.
    """
    proc = subprocess.run(
        ["git", "ls-files", "-z"],  # noqa: S607 — git off PATH, as elsewhere in tools/
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return sorted(entry for entry in proc.stdout.split("\0") if entry)


def _read(root: Path, relative: str) -> str | None:
    """Return the file's text, or `None` where there is no prose here to read.

    A tracked symlink is skipped rather than followed: `CLAUDE.md` is a committed
    symlink to `AGENTS.md` (#264), and following it would report the same site
    twice under two names — which reads as two copies of a rule that has one.
    """
    path = root / relative
    if path.is_symlink():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def scan_tree(root: Path) -> list[Finding]:
    """Report every unmarked restatement anywhere in the tree."""
    findings: list[Finding] = []
    for relative in tracked_files(root):
        source = _read(root, relative)
        if source is not None:
            findings.extend(scan_source(source, relative))
    return findings


def tree_stated(root: Path) -> list[tuple[Site, str]]:
    """Every marked restatement in the tree, with its reason, in path order."""
    stated: list[tuple[Site, str]] = []
    for relative in tracked_files(root):
        source = _read(root, relative)
        if source is not None:
            stated.extend(stated_in(source, relative))
    return stated


def main(argv: list[str] | None = None) -> int:
    """Check the tree and print one line per finding; `--report` also lists the markers."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".", type=Path)
    parser.add_argument(
        "--report",
        action="store_true",
        help="also print every marked restatement and its reason, and never red on them",
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()

    if args.report:
        for site, reason in tree_stated(root):
            print(  # noqa: T201 — the report is the output
                f"{site.path}:{site.claim_line()}: stated — {reason}"
            )
    findings = scan_tree(root)
    for finding in findings:
        print(finding, file=sys.stderr)  # noqa: T201
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
