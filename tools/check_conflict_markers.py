"""Refuse git conflict markers in tracked files (issue #231, ADR-0062).

A marker reached `main` and then ate 1,669 lines of the changelog. The sequence,
from #227's close comment: a stray common-ancestor marker landed inside 2b4f99b,
and the next landing, 5a966f3, resolved *its* rebase against the already-corrupt
file and cut everything from that line onwards. So a marker in the base is not an
untidy line — it is a live trap for the next agent, because git's merge machinery
reads the corrupted region as structure and the resolution inherits the damage.

Both halves of that are why this gate exists and why it sits where it does: in
`just check`, so a marker cannot be committed, and as a named rung in
`tools/land.py`, so a landing refuses on the rebased tree by name rather than
inside the gate's output.

## The four forms, and why the separator is scoped differently

Three are unambiguous and are findings wherever they appear at the start of a
line: the opener (`<`), the diff3 common-ancestor line (`|`), and the closer
(`>`). The one that slipped was the middle one, and it slipped because this box
sets `merge.conflictStyle = diff3` globally — so the ancestor line is not an
exotic shape here, it is the shape every conflict has.

The separator (`=`) is a finding **only between an unclosed opener and its
closer**. Alone on a line it is indistinguishable from a setext heading rule or
a documentation separator, and that is not hypothetical: six vendored wiki pages
under `docs/reference/arma-wiki/` carry such lines today, so an unconditional
rule would red `just check` on the tree it is meant to protect. The cost of the
scope is stated rather than hidden: a lone separator, every marker around it
deleted by hand, is not caught here. It is also the one form that cannot poison
a later merge on its own, because it is the region delimiters that git re-reads.

`SIZE` is git's default `conflict-marker-size`, and the runs are matched at
**seven or more** so that a path raising the attribute is covered too.

## The gate must not red on its own fixtures

The #186/#207 lesson: a checker whose subject is a literal string cannot spell
that string. Every marker here is *derived* (`"<" * SIZE`), never written out,
so this file matches none of its own patterns; the tests build their fixtures
the same way and write them into temporary trees rather than committing them.
Matching is anchored to the start of a line, which is a third layer of the same
reasoning — prose may name a marker inline, in backticks, mid-sentence, and this
file and ADR-0062 both do.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Final, NamedTuple

# git's default `conflict-marker-size`. Runs are matched at this length *or
# longer*, so a path that raises the attribute is covered without a second rule.
SIZE: Final = 7

OPEN: Final = "<"
ORIGIN: Final = "|"
SPLIT: Final = "="
CLOSE: Final = ">"

WHAT: Final = {
    OPEN: "opens a conflict region",
    ORIGIN: "is a diff3 conflict's common-ancestor line",
    SPLIT: "separates the two sides of a conflict region",
    CLOSE: "closes a conflict region",
}

REMEDY: Final = (
    "Resolve the conflict by hand and delete every marker line. A marker that reaches the "
    "base poisons the next agent's resolution — that is how 1,669 changelog lines were lost "
    "between 2b4f99b and 5a966f3 (#231)."
)


def _run(char: str) -> str:
    """Return a regex fragment matching a run of `char`, `SIZE` long or longer."""
    return f"{re.escape(char)}{{{SIZE},}}"


# The three unambiguous forms: a run at the start of a line, then end-of-line or
# a space and git's label. Requiring the space is what keeps a run of eight from
# reading as the seven-run plus rubbish — a longer run matches as a longer run.
_DELIMITERS: Final = f"{_run(OPEN)}|{_run(ORIGIN)}|{_run(CLOSE)}"
_LABELLED: Final = "( .*)?$"
DELIMITER: Final = re.compile(rf"^(?P<mark>{_DELIMITERS}){_LABELLED}")
# The separator carries no label — git writes it alone on its line.
SEPARATOR: Final = re.compile(rf"^{_run(SPLIT)}$")

# The same two shapes as POSIX ERE, which is what `git grep -E` speaks: it has
# no named groups, so the shortlist pattern is spelled without the one above's.
GREP_PATTERNS: Final = (rf"^({_DELIMITERS}){_LABELLED}", SEPARATOR.pattern)


class Finding(NamedTuple):
    """One conflict marker, where it is and what it does."""

    path: str
    line: int
    mark: str

    @property
    def problem(self) -> str:
        """What was found, in git's own terms."""
        return f"a conflict marker ({self.mark * SIZE}) that {WHAT[self.mark]}"

    def __str__(self) -> str:
        """Render as an editor-clickable location."""
        return f"{self.path}:{self.line}: {self.problem}. {REMEDY}"


def scan_source(source: str, path: str) -> list[Finding]:
    """Report every conflict marker in one file's text.

    The separator is judged in context — it counts only while a region opened by
    an opener has not been closed — so the reader is handed the whole extent of a
    conflict rather than just its ends.
    """
    findings: list[Finding] = []
    inside = False
    for number, line in enumerate(source.splitlines(), start=1):
        delimiter = DELIMITER.match(line)
        if delimiter is not None:
            mark = delimiter.group("mark")[0]
            inside = mark != CLOSE
            findings.append(Finding(path, number, mark))
        elif inside and SEPARATOR.match(line):
            findings.append(Finding(path, number, SPLIT))
    return findings


def candidates(root: Path) -> list[str]:
    """Shortlist the tracked files carrying any marker-shaped line, via `git grep`.

    Tracked files in the working tree, which is the scope #231 asks for: an
    agent's uncommitted scratch is not what lands, and #105 says a tool must not
    judge untracked files at all. `-I` drops binaries, so nothing here has to
    guess at encoding. Exit 1 is git's "no match", which is the ordinary answer.
    """
    argv = ["git", "grep", "--no-color", "-l", "-I", "-E"]
    for pattern in GREP_PATTERNS:
        argv += ["-e", pattern]
    done = subprocess.run(  # noqa: S603 — fixed argv from module constants, no shell
        argv,
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode == 1:
        return []
    if done.returncode != 0:
        message = f"git grep: {done.stderr.strip()}"
        raise RuntimeError(message)
    return [line for line in done.stdout.splitlines() if line]


def find_in_tree(root: Path) -> list[Finding]:
    """Report every conflict marker in `root`'s tracked files.

    Two steps rather than one because the honest rule needs a file's whole line
    sequence — `git grep` cannot say whether a separator sits inside a region —
    while reading every tracked file to find that out would put 6,690 vendored
    wiki pages in the path of every `just check`. So git shortlists and Python
    decides, and on a clean tree Python reads nothing at all.
    """
    findings: list[Finding] = []
    for name in candidates(root):
        text = (root / name).read_text(encoding="utf-8", errors="replace")
        findings.extend(scan_source(text, name))
    return findings


def main(argv: list[str] | None = None) -> int:
    """Check the tree and print one line per marker found."""
    parser = argparse.ArgumentParser(description="Refuse git conflict markers in tracked files.")
    parser.add_argument("root", nargs="?", default=".", type=Path)
    args = parser.parse_args(argv)

    findings = find_in_tree(args.root)
    for finding in findings:
        print(finding, file=sys.stderr)  # noqa: T201 — stderr text IS this gate's output
    if findings:
        files = len({finding.path for finding in findings})
        print(f"conflict markers in {files} file(s)", file=sys.stderr)  # noqa: T201
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
