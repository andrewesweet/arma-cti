"""A guarded single-file discard, allowlisted in place of `git checkout` (#287).

The human's ruling of 2026-08-08 on #248, in full:

    Option 1 adopted. Do not allowlist direct git checkout. Add a
    repository-owned guarded discard command and allowlist only that command.
    The command must accept exactly one normalized repository-relative tracked
    file plus a required ruling reference; refuse globs, directories, untracked
    files, conflicted files, staged changes, paths outside the assigned
    worktree, and any run where another dirty path exists; restore only the
    named unstaged working-tree change from the index; and print the path and
    ruling in its result.

Two dispatches on 2026-08-08 each ended their turn asking permission to run
`git checkout -- <path>` on residue an orchestrator-run probe had left, and both
produced nothing while `main` stayed regressed. The second asked after its own
brief had answered the question in plain words, so the gap was not comprehension:
there was no allowlisted way for a dispatched session to discard a working-tree
change at all.

The blanket grant was declined because discarding a working-tree change is
exactly what CLAUDE.md forbids — foreign files mean stop and report, never reset
(#105) — and `Bash(git checkout -- :*)` leaves room to discard a file the agent
was never told to discard. So the answer is a command constrained until it can
do nothing except the case it was authorised for.

The refusal that does most of the work is ``other_dirty_path``. A run is allowed
only when the named file's unstaged change is the *whole* of this worktree's
dirt, which makes the command useless as a general cleaner and so keeps it from
decaying into a habitual `git reset`. Every other rung is narrower than that one.

**Nothing here discards on a refusal path**, and every refusal is proven in
`tests/unit/test_discard.py` against a real repository with the working tree
asserted unchanged afterwards — a guard that returned non-zero having already
discarded something would be worse than no guard at all.

Refusals, in the order they are heard: ``no_ruling``, ``unnamed_ruling``,
``not_one_path``, ``glob``, ``outside_worktree``, ``directory``, ``untracked``,
``conflicted``, ``staged``, ``other_dirty_path``, ``nothing_to_discard``,
``git_failed``. Exit 0 is discarded, 1 is a refusal; the class is the first line,
in the tier's ``key=value`` form.

The orchestrator-clears-residue path remains the fallback whenever this guard
refuses. That is what happened on 2026-08-08 and it worked; the ruling keeps it
rather than replacing it.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Final, NamedTuple

EXIT_REFUSED: Final = 1

# Pathspec metacharacters. A glob is not one path, and the first thing the
# ruling asks is that it never be treated as one — including the quoted glob a
# shell passes through unexpanded, which is the shape that would otherwise
# reach git and match many files.
GLOB_CHARS: Final = frozenset("*?[]")

# git's own unmerged codes (`git status --porcelain`, "Short Format").
CONFLICTED: Final = frozenset({"DD", "AU", "UD", "UA", "DU", "AA", "UU"})

# What a ruling reference has to name. Every decision this project can be
# authorised by is an issue or an ADR, and a reference naming neither records
# nothing — "on whose authority" is the whole point of the field, so a field
# that accepts `--ruling ok` would satisfy the letter of "required" and none of
# its purpose.
NAMES_A_DECISION: Final = re.compile(r"#\d+|ADR-\d{4}", re.IGNORECASE)

# How many sibling dirty paths a refusal lists before it stops. Enough to decide
# what is going on; not the whole of a wrecked tree.
HOW_MANY_SHOWN: Final = 10

FALLBACK: Final = (
    "Nothing was discarded. The orchestrator-clears-residue path is the fallback whenever "
    "this guard refuses (#287), and foreign files still mean stop and report, never reset (#105)."
)
STOP_AND_REPORT: Final = (
    "Stop and report the paths. This command discards one named file's unstaged change and "
    "nothing else, so it is not the tool for a dirty tree. " + FALLBACK
)


class Refusal(NamedTuple):
    """One refusal: its class, what was found, and what the agent should do."""

    kind: str
    found: tuple[str, ...]
    action: str

    def lines(self) -> tuple[str, ...]:
        """Render the refusal as the lines the caller reads."""
        return (f"refusal={self.kind}", *self.found, f"action={self.action}")


class Report(NamedTuple):
    """One run's whole answer: lines to print and the exit code they carry."""

    lines: tuple[str, ...]
    code: int

    @classmethod
    def refused(cls, refusal: Refusal) -> Report:
        """Render a refusal at the exit code every refusal shares."""
        return cls(refusal.lines(), EXIT_REFUSED)


class Entry(NamedTuple):
    """One `git status --porcelain -z` record, split the way the rungs read it."""

    index: str
    worktree: str
    path: str

    @property
    def code(self) -> str:
        """The two-letter status git printed, e.g. ` M`, `UU`, `??`."""
        return f"{self.index}{self.worktree}"

    @property
    def conflicted(self) -> bool:
        """True for git's unmerged codes: a merge is in progress on this path."""
        return self.code in CONFLICTED

    @property
    def untracked(self) -> bool:
        """True when git has never been told about this path."""
        return self.code == "??"

    @property
    def staged(self) -> bool:
        """True when the index differs from HEAD, which this command never touches.

        `MM` is staged: restoring the working tree from the index would leave
        the staged half in place, and the ruling refuses staged changes outright
        rather than half-discarding them.
        """
        return not self.conflicted and not self.untracked and self.index != " "

    def line(self) -> str:
        """Render as git renders it, because that is what the agent will re-read."""
        return f"{self.code} {self.path}"


# --------------------------------------------------------------------- git seam


class GitError(RuntimeError):
    """A git command this tool depends on failed, and the caller must be told which."""

    def __init__(self, args: tuple[str, ...], stderr: str) -> None:
        """Keep the argv and git's own words, which is what the refusal quotes."""
        super().__init__(f"git {' '.join(args)}: {stderr.strip()}")
        self.args_run = args
        self.stderr = stderr.strip()


def git(*args: str, cwd: Path, check: bool = True) -> str:
    """Run one git command and return its stdout, raising `GitError` when it fails."""
    # S603/S607: the argv is fixed literals plus paths this tool computed, and
    # `git` resolves off PATH on purpose — the repo's toolchain is the caller's.
    done = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if check and done.returncode != 0:
        raise GitError(args, done.stderr)
    return done.stdout


def literal(rel: str) -> str:
    """Return the pathspec that means exactly this one path and nothing else.

    `:(literal)` turns off git's own pathspec globbing and magic, so a tracked
    file genuinely named `a[b]` is addressed rather than matched. Belt and
    braces over the `glob` rung: that rung refuses the metacharacters before
    anything reaches git, and this makes the pathspec inert even if it did.
    """
    return f":(literal){rel}"


# --------------------------------------------------------------------- parsing


def read_status(payload: str) -> tuple[Entry, ...]:
    """Parse `git status --porcelain -z` into one entry per path.

    `-z` rather than the plain form for two reasons that both end in comparing
    the wrong path: without it a rename prints as `R  old -> new`, and a path
    carrying a space or a quote is re-quoted by `core.quotePath`. Under `-z`
    each record is `XY <path>`, and a rename or a copy is followed by its source
    as a field of its own — consumed here and not reported, because the file
    that changed is the destination.
    """
    fields = payload.split("\0")
    entries: list[Entry] = []
    index = 0
    while index < len(fields):
        field = fields[index]
        index += 1
        if len(field) < 4:  # noqa: PLR2004 — `XY ` plus at least one character of path
            continue
        code, path = field[:2], field[3:]
        if code[0] in {"R", "C"}:
            index += 1  # the rename/copy source, which is not a second subject
        entries.append(Entry(code[0], code[1], path))
    return tuple(entries)


def read_worktrees(porcelain: str) -> tuple[Path, ...]:
    """Return every registered worktree path from `git worktree list --porcelain`."""
    return tuple(
        Path(line.partition(" ")[2])
        for line in porcelain.splitlines()
        if line.startswith("worktree ")
    )


# --------------------------------------------------------------------- ladders


def classify_ruling(ruling: str) -> Refusal | None:
    """Refuse a run that records no authority for the discard."""
    if not ruling.strip():
        return Refusal(
            "no_ruling",
            ("ruling=<empty>",),
            "Name the decision that authorises this discard, e.g. "
            '`just discard tools/x.py "#287 (human ruling 2026-08-08 on #248)"`. ' + FALLBACK,
        )
    if not NAMES_A_DECISION.search(ruling):
        return Refusal(
            "unnamed_ruling",
            (f"ruling={ruling}", "expected=an issue (#287) or an ADR (ADR-0013)"),
            "The ruling reference is the record of on whose authority a file was discarded, "
            "so it has to name a decision this project can be pointed at. " + FALLBACK,
        )
    return None


def classify_paths(raw: tuple[str, ...]) -> Refusal | None:
    """Refuse anything that is not exactly one path, and refuse a glob."""
    named = tuple(one for one in raw if one.strip())
    if len(named) != 1:
        return Refusal(
            "not_one_path",
            (f"paths={len(named)}", *(f"path={one}" for one in named[:HOW_MANY_SHOWN])),
            "This command discards exactly one named file. Run it once per file, "
            "reading the refusals each time. " + FALLBACK,
        )
    if GLOB_CHARS.intersection(named[0]):
        return Refusal(
            "glob",
            (f"path={named[0]}", f"metacharacters={''.join(sorted(GLOB_CHARS))}"),
            "A glob is not one file: it is a set whose members you have not read. "
            "Name the one file. " + FALLBACK,
        )
    return None


def classify_location(
    root: Path, registrations: tuple[Path, ...], candidate: Path, raw: str
) -> Refusal | None:
    """Refuse a path that resolves outside the worktree this command was run in.

    Two ways out, and both refuse: resolving above the worktree root at all, and
    resolving into a *different* registered worktree nested under it. The second
    is the one that matters — `.claude/worktrees/issue-N` sits inside the main
    checkout's directory tree while belonging to another agent, which is exactly
    the collision #105 records.

    Resolution is what makes this true rather than hopeful: a symlink pointing
    out of the tree resolves out of the tree and is refused here, and a `..` that
    stays inside normalises to a path that is.
    """
    outside = Refusal(
        "outside_worktree",
        (f"path={raw}", f"resolved={candidate}", f"worktree={root}"),
        "This command only ever touches the worktree it was run in. If the file belongs to "
        "another agent's tree, stop and report it — never reset another holder's tree (#105). "
        + FALLBACK,
    )
    if not candidate.is_relative_to(root):
        return outside
    for other in registrations:
        if other != root and candidate.is_relative_to(other):
            return Refusal(
                "outside_worktree", (*outside.found, f"belongs_to={other}"), outside.action
            )
    return None


def classify_target(rel: str, *, is_dir: bool, tracked: bool) -> Refusal | None:
    """Refuse a directory, and refuse anything git is not tracking."""
    if is_dir:
        return Refusal(
            "directory",
            (f"path={rel}", "kind=directory"),
            "A directory is a set of files whose members you have not read. Name the one file. "
            + FALLBACK,
        )
    if not tracked:
        return Refusal(
            "untracked",
            (f"path={rel}", "tracked=no"),
            "There is no index version to restore from, so discarding this would delete a file "
            "rather than revert one — and an untracked file may be another agent's (#105). "
            + FALLBACK,
        )
    return None


def classify_change(rel: str, entries: tuple[Entry, ...]) -> Refusal | None:
    """Refuse unless the named file's unstaged change is the whole of this tree's dirt."""
    mine = next((entry for entry in entries if entry.path == rel), None)
    others = tuple(entry for entry in entries if entry.path != rel)
    if mine is not None and mine.conflicted:
        return Refusal(
            "conflicted",
            (f"path={rel}", f"status={mine.code}", "unmerged=yes"),
            "A merge or rebase is in progress on this path. Resolve it, or abort the operation "
            "that started it — discarding half of a conflict loses the resolution. " + FALLBACK,
        )
    if mine is not None and mine.staged:
        return Refusal(
            "staged",
            (f"path={rel}", f"status={mine.code}", "index=differs from HEAD"),
            "This command restores the working tree from the index and never touches the index, "
            "so a staged change would survive it and the result would not be what you asked for. "
            + FALLBACK,
        )
    if others:
        return Refusal(
            "other_dirty_path",
            (
                f"path={rel}",
                f"other_dirty={len(others)}",
                *(entry.line() for entry in others[:HOW_MANY_SHOWN]),
            ),
            STOP_AND_REPORT,
        )
    if mine is None:
        return Refusal(
            "nothing_to_discard",
            (f"path={rel}", "status=clean"),
            "The working tree already matches the index for this path. Nothing was there to "
            "discard, so nothing was done — check you named the file you meant. " + FALLBACK,
        )
    return None


# --------------------------------------------------------------------- the act


def discard(cwd: Path, raw: tuple[str, ...], ruling: str) -> Report:
    """Run the whole ladder and, if every rung passes, restore the one file."""
    refusal = classify_ruling(ruling) or classify_paths(raw)
    if refusal is not None:
        return Report.refused(refusal)
    named = next(one for one in raw if one.strip())

    root = Path(git("rev-parse", "--show-toplevel", cwd=cwd).strip()).resolve()
    registrations = tuple(
        path.resolve() for path in read_worktrees(git("worktree", "list", "--porcelain", cwd=cwd))
    )
    candidate = (cwd / named).resolve()
    refusal = classify_location(root, registrations, candidate, named)
    if refusal is not None:
        return Report.refused(refusal)

    rel = candidate.relative_to(root).as_posix()
    tracked = bool(git("ls-files", "-z", "--", literal(rel), cwd=root).strip("\0"))
    refusal = classify_target(rel, is_dir=candidate.is_dir(), tracked=tracked)
    if refusal is not None:
        return Report.refused(refusal)

    entries = read_status(git("status", "--porcelain", "-z", cwd=root))
    refusal = classify_change(rel, entries)
    if refusal is not None:
        return Report.refused(refusal)

    git("restore", "--worktree", "--", literal(rel), cwd=root)
    return Report(
        (
            "ok=discarded",
            f"worktree={root}",
            f"path={rel}",
            f"ruling={ruling.strip()}",
            "restored_from=index (the named unstaged working-tree change, and nothing else)",
        ),
        0,
    )


# ------------------------------------------------------------------ invocation


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """One path, and the ruling that authorises discarding it."""
    parser = argparse.ArgumentParser(prog="just discard", description=__doc__)
    parser.add_argument("paths", nargs="*", default=[])
    parser.add_argument("--ruling", default="")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Discard one named file's unstaged change, or refuse loudly and touch nothing."""
    args = parse_args(argv)
    try:
        report = discard(Path.cwd(), tuple(args.paths), args.ruling)
    except GitError as failure:
        # Fail closed, with git's own words: a rung of the ladder that did not
        # run is not a rung that passed (#41's shape).
        report = Report.refused(
            Refusal(
                "git_failed",
                (f"command=git {' '.join(failure.args_run)}", f"stderr={failure.stderr}"),
                "Read git's own error above. " + FALLBACK,
            )
        )
    stream = sys.stdout if report.code == 0 else sys.stderr
    for line in report.lines:
        print(line, file=stream)
    return report.code


if __name__ == "__main__":
    sys.exit(main())
