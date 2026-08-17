"""Refuse a document naming a repository path the tree does not carry (issue #395).

## What this catches, and what it does not

A rebase conflict resolver reads *conflicts*. Nothing reads the passages that
merged **cleanly** and became false because of what landed underneath them.
#329's rebase left `docs/agents/orchestration.md` saying that two mechanisms were
"still live in `tools/admission.py`" while the rebase base was the very commit
that renamed that file to `tools/trial.py` and dropped them — a region that never
conflicted, so it was never one of the nine the resolver read.

This gate catches one family of that: **a document that names a file which is
gone**. It is the cheap mechanical half, and it is explicitly *not* the whole
defect. The issue's own correction proved the limit on the next rebase of the
same branch: `AGENTS.md` was made false about the arbiter's walk with **no path
name changed and nothing greppable wrong**, and this check would have come back
clean. Do not read a green here as "the prose still matches the tree". The
load-bearing half is `tools/land.py`'s rebase report, which names the cleanly
replayed files and the commits the new base contributed so a reviewer can go and
read them.

## Which tokens are judged

A candidate is a slash-bearing token inside an inline backtick span whose **first
segment is a tracked top-level entry** of this repository. That one rule is what
keeps the gate off everything that is not a claim about our tree: `origin/main`,
`~/.arma-cti/dispatches/<id>/`, `refs/heads/issue-N`, `commands/setDamage.wiki`
and every URL fail it, without a hand-maintained ignore list to drift.

Resolution is against `git ls-files` and the directory prefixes it implies —
never the filesystem — so an untracked build artefact cannot make a path resolve
on the machine that built it and vanish on the one that did not. A token carrying
a glob metacharacter (`docs/**`, `spike/probes/*.sqf`) resolves when at least one
tracked path matches it; matching nothing is a finding, because a pattern that
selects nothing is the same claim about the tree as a name that is gone.

Fenced code blocks are out of scope as a consequence of reading inline spans
rather than by a rule of their own: a fence's content lines carry no backtick
pair, so nothing in one is a candidate.

Two families are dropped before any of that, because neither is a claim about
what the tree carries. A path **git ignores** is runtime state — `.claude/worktrees/`
is where every dispatched agent works and is in `.gitignore` by design — and a
path under `~/` belongs to the host, not here, which is why `~` is a segment
character: without it the token would start at `.claude/` and `~/.claude/settings.json`
would silently resolve against *this repository's* `.claude/settings.json`.

## Marking a path the tree deliberately does not carry

`MARKER` is how an author says the absence is meant:

* on a line with other text, it exempts **that line's** paths;
* alone on a line, it exempts **the whole file**, wherever in the file it sits.

The whole-file form is not "the rest of the file" on purpose: a rule that depends
on where the marker sits is a rule an author has to remember the direction of,
and the only thing it would buy is a half-marked document, which is not a state
worth being able to express.

Either form may carry its reason — `<!-- absent-path: reserved for Phase 3 -->` —
and the line form generally should, since a bare marker mid-prose tells the next
human nothing. The whole-file markers in this tree put their reason in a second
comment beneath instead, because the reason runs to three lines and a comment
that wraps is no longer a line the file form can recognise.

It is spelled for absence rather than for history, because #395 asked for
"marked historical" and the tree holds both directions of the same thing. Behind
it sit dated research records and superseded ADRs, `docs/agents/orchestration.md`'s
"there is no `tools/admission.py`" — the sentence this gate was built from, whose
whole point is that the file is gone — and also `tests/specs/`, which ADR-0016
reserves for Phase 3 and nothing has created yet. One marker rather than two,
because the author's act is the same in both directions and the check's question
is only ever "is this absence meant?".

Whole-file scope exists because a dated record is historical in one act rather
than a path at a time: measured before it was built, 85 of the 121 findings on
the tree as #395 opened sat in `docs/research/`, and marking those line by line
would be a hundred edits saying one thing. A directory exemption was the other
way to reach that, and it was declined — an exemption the checker holds is
invisible to the author, while a marker the file carries is in the diff.

The marker is an HTML comment so it renders as nothing, and it is the same string
in prose and in Markdown tables.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath
from typing import Final, NamedTuple

MARKER: Final = "<!-- absent-path -->"

# The marker may carry its reason — `<!-- absent-path: reserved for Phase 3 -->` — because
# a bare marker on a prose line explains nothing to the human who meets it next, and the
# line form has nowhere else to put the reason. `[^>]*` keeps a reason on one comment and
# out of the rest of the line; a reason needing `>` needs rewording.
MARKER_RE: Final = re.compile(r"<!--\s*absent-path\b[^>]*-->")

# `docs/**` and `AGENTS.md`, the surfaces #395 names. `CLAUDE.md` is a committed
# symlink to `AGENTS.md` (#264), so naming both would judge one file twice.
SCOPE: Final = ("docs/", "AGENTS.md")

# The vendored Bohemia wiki is upstream's prose, not ours to mark, and its 6,690
# pages name wiki paths rather than this repository's.
EXCLUDED: Final = ("docs/reference/arma-wiki/",)

SUFFIX: Final = ".md"

# One inline span. Anchored within a line, so a fence delimiter — three backticks
# with nothing between them — matches nothing.
BACKTICKED: Final = re.compile(r"`([^`\n]+)`")

# A path segment as this repository writes them. `:` is deliberately absent, so
# `tools/arbiter.py:135` yields the path and drops the line reference for free.
# `~` is deliberately present, so a home path stays one: matched without it, the
# token would begin at `.claude/` and a host file would resolve against ours.
SEGMENT: Final = r"[A-Za-z0-9_.*?@+~-]+"
PATHLIKE: Final = re.compile(rf"{SEGMENT}(?:/{SEGMENT})+/?")

GLOB: Final = "*?["

REMEDY: Final = (
    "Either the path moved and the sentence naming it is now false — fix the sentence — or "
    f"the absence is meant, in which case say so: `{MARKER}` on the line exempts that line's "
    "paths, and alone on a line it exempts the whole file. Either form may carry its reason "
    "(`<!-- absent-path: reserved for Phase 3 -->`), and a dated record naming what the tree "
    "carried when it was written takes the file form."
)


class Finding(NamedTuple):
    """One backticked path that this tree does not carry."""

    path: str
    line: int
    named: str

    @property
    def problem(self) -> str:
        """What was found, in the document's own spelling of it."""
        return f"`{self.named}` is not in the tree"

    def __str__(self) -> str:
        """Render as an editor-clickable location.

        The remedy is printed once at the end rather than on every line, unlike the
        conflict-marker gate's: that one fires on a handful of lines in one file, and
        this one can fire across a document set, where a repeated four-line remedy
        buries the list it is meant to explain.
        """
        return f"{self.path}:{self.line}: {self.problem}"


class Tree(NamedTuple):
    """The tracked paths a document may name, and the roots that make a token one."""

    known: frozenset[str]
    roots: frozenset[str]

    @classmethod
    def of(cls, tracked: list[str]) -> Tree:
        """Derive the directory prefixes a tracked file list implies."""
        known = set(tracked)
        for name in tracked:
            parent = PurePosixPath(name).parent
            while str(parent) != ".":
                known.add(str(parent))
                parent = parent.parent
        roots = (name.split("/", maxsplit=1)[0] for name in tracked)
        return cls(frozenset(known), frozenset(roots))

    def claims_a_path(self, token: str) -> bool:
        """Report whether this token is a claim about *this* repository at all."""
        return token.split("/", maxsplit=1)[0] in self.roots

    def resolves(self, token: str) -> bool:
        """Report whether the tree carries what this token names."""
        path = token.rstrip("/")
        if any(char in path for char in GLOB):
            return any(fnmatch(name, path) for name in self.known)
        return path in self.known


def tracked_files(root: Path) -> list[str]:
    """Every tracked path, repository-relative, in git's own order."""
    done = subprocess.run(
        # S607: `git` off PATH, as every tool here does.
        ["git", "ls-files", "-z"],  # noqa: S607
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        message = f"git ls-files: {done.stderr.strip()}"
        raise RuntimeError(message)
    return [name for name in done.stdout.split("\0") if name]


def _forms(token: str) -> frozenset[str]:
    """Return one token's file and directory spellings, for `git check-ignore`."""
    bare = token.rstrip("/")
    return frozenset((bare, f"{bare}/"))


def ignored(root: Path, tokens: set[str]) -> frozenset[str]:
    """Return the subset of `tokens` that git ignores.

    One batched call rather than one per finding, and asked only of what has
    already failed to resolve, so a clean tree never runs it. Exit 1 is git's "none
    of these are ignored", which is the ordinary answer once the runtime paths are
    marked; anything else is this checker failing rather than the tree being clean,
    so it raises rather than returning an empty set.
    """
    if not tokens:
        return frozenset()
    done = subprocess.run(
        # S607: `git` off PATH, as every tool here does.
        ["git", "check-ignore", "--stdin"],  # noqa: S607
        cwd=root,
        input="\n".join(sorted(tokens)),
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode not in (0, 1):
        message = f"git check-ignore: {done.stderr.strip()}"
        raise RuntimeError(message)
    return frozenset(line for line in done.stdout.splitlines() if line)


def documents(tracked: list[str]) -> list[str]:
    """Shortlist the prose files whose paths this gate judges."""
    return [
        name
        for name in tracked
        if name.endswith(SUFFIX) and name.startswith(SCOPE) and not name.startswith(EXCLUDED)
    ]


def scan_source(source: str, path: str, tree: Tree) -> list[Finding]:
    """Report every backticked path in one document that `tree` does not carry.

    The whole-file marker is looked for first and over the whole text, so it holds
    wherever the author put it; the line form is then read before each line's spans
    are, so a marked line costs nothing to scan.
    """
    lines = source.splitlines()
    if any(MARKER_RE.fullmatch(line.strip()) for line in lines):
        return []
    findings: list[Finding] = []
    for number, line in enumerate(lines, start=1):
        if MARKER_RE.search(line):
            continue
        seen: set[str] = set()
        for span in BACKTICKED.findall(line):
            for token in PATHLIKE.findall(span):
                if token in seen or not tree.claims_a_path(token) or tree.resolves(token):
                    continue
                seen.add(token)
                findings.append(Finding(path, number, token))
    return findings


def find_in_tree(root: Path) -> list[Finding]:
    """Report every unresolvable backticked path across the documents in scope."""
    tracked = tracked_files(root)
    tree = Tree.of(tracked)
    findings: list[Finding] = []
    for name in documents(tracked):
        text = (root / name).read_text(encoding="utf-8", errors="replace")
        findings.extend(scan_source(text, name, tree))
    # Both spellings, because `.gitignore`'s directory patterns end in a slash and
    # `git check-ignore` answers about the string it is handed: `.claude/worktrees/`
    # matches the pattern that hides every dispatched agent's tree and
    # `.claude/worktrees` does not.
    runtime = ignored(root, {form for finding in findings for form in _forms(finding.named)})
    return sorted(
        finding for finding in findings if not runtime.intersection(_forms(finding.named))
    )


def main(argv: list[str] | None = None) -> int:
    """Check the tree and print one line per unresolvable path."""
    parser = argparse.ArgumentParser(
        description="Refuse a document naming a repository path the tree does not carry."
    )
    parser.add_argument("root", nargs="?", default=".", type=Path)
    args = parser.parse_args(argv)

    findings = find_in_tree(args.root)
    for finding in findings:
        print(finding, file=sys.stderr)  # noqa: T201 — stderr text IS this gate's output
    if findings:
        files = len({finding.path for finding in findings})
        summary = f"{len(findings)} absent path(s) named in {files} document(s)"
        print(f"{summary}. {REMEDY}", file=sys.stderr)  # noqa: T201
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
