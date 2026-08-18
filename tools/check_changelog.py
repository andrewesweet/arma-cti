"""The changelog-entry check: a user-visible commit carries an entry, as a fragment (#358).

ADR-0010's practice line — a commit with user-visible effect updates the changelog in the
same commit — was prose for as long as `CHANGELOG.md` was the only surface, and the move
to per-branch fragments could have quietly weakened it: a branch that records nothing now
writes nothing anywhere, so nothing would differ between a branch with an entry and a
branch without one. This check is what keeps the requirement real on the fragment shape:
a tree whose commits over `origin/main` include a `feat`, a `fix` or any breaking `!`
carries either a `changelog.d/<issue>-<slug>.md` fragment or a `CHANGELOG.md` edit, and
the same run validates every fragment the fold would have to merge — a fragment that
cannot parse is refused here, at edit time, rather than at a landing that has already
spent a gate.

The boundary is the commit-type vocabulary and it is stated rather than hidden: a
behaviour change landed under `refactor` without `!` is as invisible to this check as it
always was to every mechanical check, and the type is the author's claim about the commit.
`cog verify` owns the message's shape; this owns what the shape owes.

Deliberately not a landing rung. The fold inside `tools/land.py` is the enforcement at
landing — it merges what is here or refuses by name — and a second gate reading the same
tree would be the duplicated judgement ADR-0071 ruling 4 caps. This is the earlier, cheaper
half: red in `just check`, before any rebase or review is spent.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Final, NamedTuple

# tools/ holds standalone scripts rather than an importable package, so a sibling
# import needs the script's own directory on the path — the same device
# `tools/land.py` uses to reach `worktree`.
sys.path.insert(0, str(Path(__file__).parent))

import changelog_fragments
from worktree import git

# Conventional Commits 1.0.0's parseable head: type, optional scope, optional `!`.
# `cog verify` enforces the grammar; this reads the type and the bang and nothing else.
CONVENTIONAL: Final = re.compile(r"^(\w+)(?:\([^)]*\))?(!)?:")

# The types whose commits carry user-visible effect by construction (ADR-0010).
# A `!` on any type joins them, because breaking is user-visible whatever the type.
ENTRY_TYPES: Final = frozenset({"feat", "fix"})

REMOTE_BASE: Final = "origin/main"
CHANGELOG: Final = "CHANGELOG.md"

# `git status --porcelain` prefixes two status columns and a space before the path.
STATUS_PATH_AT: Final = 3


class Finding(NamedTuple):
    """One way this tree's changelog entry requirement is not met."""

    detail: str
    remedy: str

    def __str__(self) -> str:
        """Render as one editor-facing line, the shape the other check tools use."""
        return f"changelog: {self.detail}. {self.remedy}"


def needs_entry(subjects: list[str]) -> list[str]:
    """Return the subjects that carry user-visible effect by their commit type."""
    owed: list[str] = []
    for subject in subjects:
        found = CONVENTIONAL.match(subject)
        if found is None:
            continue
        kind, breaking = found.group(1), found.group(2)
        if kind in ENTRY_TYPES or breaking:
            owed.append(subject)
    return owed


def _status_paths(status: str) -> set[str]:
    return {line[STATUS_PATH_AT:].strip() for line in status.splitlines() if line.strip()}


def entry_paths(paths: set[str]) -> set[str]:
    """Return the paths among `paths` that satisfy the entry requirement."""
    carried = {path for path in paths if path == CHANGELOG}
    carried.update(
        path
        for path in paths
        if path.startswith("changelog.d/")
        and changelog_fragments.FRAGMENT_NAME.match(path.removeprefix("changelog.d/"))
    )
    return carried


def scan(root: Path) -> list[Finding]:
    """Report every way this tree's changelog requirement is not met.

    Read-only, and deliberately silent about everything it cannot see: a tree
    with no `origin/main` to diff against is reported as unchecked rather than
    passed, because a check that could not run is not a check that passed (#41).
    """
    base = git("rev-parse", "--verify", REMOTE_BASE, cwd=root, check=False).strip()
    if not base:
        return [
            Finding(
                f"no `{REMOTE_BASE}` ref to diff against",
                "fetch and re-run; the entry requirement is a claim about this tree's "
                "commits over the remote, and a tree that cannot show them is unchecked "
                "rather than clear",
            )
        ]

    subjects = [
        line
        for line in git("log", "--format=%s", f"{REMOTE_BASE}..HEAD", cwd=root).splitlines()
        if line.strip()
    ]
    owed = needs_entry(subjects)
    paths = set(git("diff", "--name-only", f"{REMOTE_BASE}...HEAD", cwd=root).splitlines())
    # `--untracked-files=all` because the plain form collapses a wholly-untracked
    # directory to its own name — `changelog.d/` — which matches no fragment and
    # would red a branch whose only entry is the fragment it has not committed yet.
    paths |= _status_paths(git("status", "--porcelain", "--untracked-files=all", cwd=root))
    paths.discard("")

    findings: list[Finding] = []
    try:
        fragments = changelog_fragments.collect(root)
    except changelog_fragments.FragmentError as error:
        findings.append(Finding(" ".join(error.found), error.action))
        fragments = []
    if owed and not entry_paths(paths):
        findings.append(
            Finding(
                f"{len(owed)} user-visible commit(s) and no changelog entry among them",
                "record the entry as a fragment of this branch's own — "
                "`changelog.d/<issue>-<slug>.md`, one or more `### <Category>` sections "
                "holding the entries (Added, Changed, Deprecated, Removed, Fixed, "
                "Security). The landing folds it into `CHANGELOG.md` (#358, ADR-0010)",
            )
        )
    if fragments:
        target = root / CHANGELOG
        heading = target.is_file() and any(
            line.strip() == changelog_fragments.UNRELEASED
            for line in target.read_text(encoding="utf-8").splitlines()
        )
        if not heading:
            findings.append(
                Finding(
                    f"{len(fragments)} fragment(s) and no `## [Unreleased]` to fold into",
                    "restore the empty `## [Unreleased]` section in `CHANGELOG.md`, or "
                    "the landing's fold refuses `changelog_unreleased_missing`",
                )
            )
    return findings


def main(argv: list[str] | None = None) -> int:
    """Print every finding and exit non-zero where the requirement is unmet."""
    parser = argparse.ArgumentParser(prog="check-changelog", description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="the tree to check")
    args = parser.parse_args(argv)
    findings = scan(args.root.resolve())
    for finding in findings:
        print(finding, file=sys.stderr)  # noqa: T201 — stderr text IS this gate's output
    if not findings:
        print("changelog=ok")  # noqa: T201 — one line, the shape the other checks print
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
