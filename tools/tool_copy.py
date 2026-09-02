#!/usr/bin/env python3
"""Which copy of this project's own command machinery a session is running (#676).

``just dispatch`` runs ``tools/dispatch.py`` from the dispatching session's worktree, so a
landing that changes the dispatch path does not govern the session that landed it: the
orchestrator is the seat that lands those changes, so it is systematically the last to run
them, and the failure is silent by construction. This module makes the copy visible in two
halves and never goes further:

- ``tools/dispatch.py`` embeds ``survey``'s document in every dispatch record, so a reader
  can tell a stale dispatcher from a current one after the fact;
- ``report`` — a ``just watch-report`` rung — names the drift one line per governed path,
  silent while current, and fixes nothing. Rebasing a live session's tree is a judgement
  with uncommitted state at stake, so the report is a verdict, never an act.

The governed set is what this tree executes as machinery, not the whole tree: every
existing file under ``tools/`` the justfile names, the ``.claude/hooks/`` surface the
harness runs from this tree's own copy (the #120 shape), the ``.claude/settings.json``
that wires it, and the justfile itself. Test modules, docs and other sources are
deliberately outside it — they are read, not executed, and naming them would turn every
landing into a drift report.

A path is **behind** only where this tree's ``HEAD`` is an ancestor of ``origin/main``:
that is the fact "a landing has superseded this copy". A tree carrying its own commits is
a session mid-work, and its drifted paths are its own candidate, never a report. Reading
``origin/main`` uses the local ref without fetching — ``just land`` and ``just worktree
add`` fetch as a matter of routine, so the ref is fresh exactly where the loop needs it
to be. The walk is over the **union** of the two governed sets — this tree's and
``origin/main``'s — so a path the landing added is surveyed though no local set could
hold it, and the record and the rung carry the blob sha each of the three sides holds:
the working tree, ``HEAD`` and ``origin/main``, empty where a side does not hold the
path. ``HEAD`` is what tells a landed removal from the session's own new work, which
neither commit has. Blob shas come from ``git hash-object`` over the working-tree bytes,
so an uncommitted edit shows as drift too; where a checkout filter rewrites bytes, the
shas a drifted path carries are the evidence a reader needs to see it.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

GOVERNED_JUSTFILE: Final = "justfile"
GOVERNED_HOOK_DIR: Final = ".claude/hooks"
GOVERNED_SETTINGS: Final = ".claude/settings.json"

# The justfile is shell, where a path is spelled the same wherever it is invoked; every
# existing hit that resolves to a file in this tree is machinery a recipe runs or reads.
_TOOL_REFERENCE: Final = re.compile(r"tools/[A-Za-z0-9_./-]+")

# A `git ls-tree` entry is `<mode> <type> <sha>\t<path>`; fewer fields carries no blob.
_LS_TREE_FIELDS: Final = 3

# The state-directory seam the other rungs carry (#249), so a test never depends on what
# the box is holding. This one reads the repository instead of a state directory, so the
# seam names the repository.
REPO_SEAM: Final = "CTI_TOOL_COPY_REPO"


class _GitUnreadableError(Exception):
    """git refused or never started — the same "could not tell me" dispatch.py's git encodes."""


def _git(*args: str, root: Path) -> str:
    """Run one git command and return its stdout; raise where git could not answer."""
    try:
        done = subprocess.run(  # noqa: S603
            ["git", *args],  # noqa: S607 — the checkout's toolchain is the caller's
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as unreadable:
        raise _GitUnreadableError(str(unreadable)) from unreadable
    if done.returncode != 0:
        detail = (done.stderr or "").strip().splitlines()
        raise _GitUnreadableError(
            detail[-1] if detail else f"git {' '.join(args)}: exit {done.returncode}"
        )
    return done.stdout


def governed_paths(root: Path) -> tuple[Path, ...]:
    """Return the files this tree executes as its own command machinery, sorted, posix-named.

    A justfile reference to a file this tree does not have names nothing a session can
    run, so it is not governed; ``__pycache__`` under the hook surface is interpreter
    output, not a hook.
    """
    governed = {Path(GOVERNED_JUSTFILE), Path(GOVERNED_SETTINGS)}
    try:
        justfile = (root / GOVERNED_JUSTFILE).read_text(encoding="utf-8")
    except OSError:
        justfile = ""
    for reference in _TOOL_REFERENCE.findall(justfile):
        candidate = Path(reference)
        if ".." not in candidate.parts and (root / candidate).is_file():
            governed.add(candidate)
    hook_dir = root / GOVERNED_HOOK_DIR
    if hook_dir.is_dir():
        governed.update(
            path.relative_to(root)
            for path in hook_dir.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        )
    return tuple(sorted(governed, key=lambda path: path.as_posix()))


@dataclass(frozen=True)
class Survey:
    """One read of a tree's copies against ``origin/main``, at one instant.

    ``paths`` carries **only** the governed paths whose working-tree bytes and
    ``origin/main`` bytes differ — the drift, walked over the **union** of the two
    governed sets, with the blob sha each of the three sides holds beside the others:
    ``worktree`` (the working tree), ``head`` (the tree's own ``HEAD`` commit) and
    ``origin_main`` — empty where that side does not hold the path. Every other path is
    current and is deliberately absent: a full listing per dispatch would be a dashboard
    of sameness (#209).
    """

    head: str
    origin_main: str
    # ``None`` is "could not tell" — git refused, or the ref is not there, or
    # `merge-base --is-ancestor` failed rather than answering. It is never folded into
    # ``False``, because an unreadable ref reads as health nowhere else in this
    # project's reporting.
    behind_origin_main: bool | None
    paths: Mapping[str, Mapping[str, str]] = field(default_factory=dict)

    def stale_paths(self) -> tuple[str, ...]:
        """Return the governed paths a landing has superseded; empty unless the tree is behind.

        Two exclusions keep the report from crying wolf. A tree carrying its own commits
        is not behind even where its bytes differ from ``origin/main`` — that drift is the
        session's own candidate, and naming it would report every mid-issue tree as stale.
        And a path only the working tree holds — ``origin/main`` and ``HEAD`` both empty —
        is this session's own new work, which no landing has superseded. A path
        ``origin/main`` has **deleted**, by contrast, is named: ``HEAD`` still holds what
        the landing removed, so it is drift with its two sides stated like any other.
        """
        if self.behind_origin_main is not True:
            return ()
        return tuple(
            name
            for name in sorted(self.paths)
            if self.paths[name].get("origin_main", "") or self.paths[name].get("head", "")
        )

    def document(self) -> dict[str, object]:
        """Render the record half: the instant's heads, and both sides of every drift."""
        return {
            "worktree_head": self.head,
            "origin_main_head": self.origin_main,
            "behind_origin_main": self.behind_origin_main,
            "paths": {name: dict(entry) for name, entry in sorted(self.paths.items())},
        }

    @classmethod
    def from_document(cls, document: object) -> Survey | None:
        """Read back what ``document`` wrote, or ``None`` where no record carries one."""
        if not isinstance(document, dict):
            return None
        paths = document.get("paths")
        behind = document.get("behind_origin_main")
        return cls(
            head=str(document.get("worktree_head", "")),
            origin_main=str(document.get("origin_main_head", "")),
            behind_origin_main=None if behind is None else behind is True,
            paths={
                str(name): dict(entry) for name, entry in paths.items() if isinstance(entry, dict)
            }
            if isinstance(paths, dict)
            else {},
        )


def _local_side(root: Path) -> tuple[str, tuple[str, ...], dict[str, str]]:
    """Read this tree's own half: HEAD, the governed set, each path's working-tree blob."""
    head = _git("rev-parse", "HEAD", root=root).strip()
    names = tuple(path.as_posix() for path in governed_paths(root))
    blobs: dict[str, str] = {}
    if names:
        listed = _git("hash-object", "--", *names, root=root).split()
        blobs = dict(zip(names, listed, strict=False))
    return head, names, blobs


def _origin_governed(root: Path) -> tuple[str, ...]:
    """Read the governed set as ``origin/main`` names it, without a checkout.

    The justfile comes off ``git show``; the hook surface and the wiring come off one
    ``ls-tree``. A path that exists only here is still governed on the origin side's
    read of nothing: what the landing changed is what the landing's own tree names.
    """
    justfile = _git("show", "origin/main:justfile", root=root)
    names = {
        candidate
        for candidate in (
            Path(reference)
            for reference in _TOOL_REFERENCE.findall(justfile)
            if ".." not in Path(reference).parts
        )
        if candidate.parts  # an empty candidate is a malformed reference, not a path
    }
    names.update({Path(GOVERNED_JUSTFILE), Path(GOVERNED_SETTINGS)})
    listed = _git(
        "ls-tree", "-r", "--name-only", "-z", "origin/main", "--", GOVERNED_HOOK_DIR, root=root
    )
    # The same exclusion the local read applies: interpreter output under the hook
    # surface is not a hook, on either side.
    names.update(
        Path(line) for line in listed.split("\0") if line and "__pycache__" not in Path(line).parts
    )
    return tuple(sorted({name.as_posix() for name in names}))


def _ls_tree_blobs(rev: str, names: Sequence[str], root: Path) -> dict[str, str]:
    """Each name's blob sha as ``rev`` holds it; absent where ``rev`` does not have it."""
    blobs: dict[str, str] = {}
    if not names:
        return blobs
    for entry in _git("ls-tree", "-z", rev, "--", *names, root=root).split("\0"):
        if not entry:
            continue
        meta, _, path = entry.partition("\t")
        parts = meta.split()
        if len(parts) >= _LS_TREE_FIELDS:
            blobs[path] = parts[2]
    return blobs


def _origin_side(root: Path, names: tuple[str, ...]) -> tuple[str, tuple[str, ...], dict[str, str]]:
    """``origin/main``'s half: its head, its governed set, and each governed path's blob.

    The origin side derives its own governed set, so a path the landing added or renamed
    is surveyed on the origin side even where this tree has never had it — a tree whose
    justfile lost a reference is behind on exactly that file, and deriving the set only
    from the local justfile would read that absence as current.
    """
    origin_main = _git("rev-parse", "origin/main", root=root).strip()
    origin_names = _origin_governed(root)
    # One listing over the whole surveyed set, rather than a `rev-parse` per path.
    blobs = _ls_tree_blobs("origin/main", list(dict.fromkeys([*names, *origin_names])), root)
    return origin_main, origin_names, blobs


def _git_code(*args: str, root: Path) -> int:
    """Run one git command for its exit code alone, which `--is-ancestor`'s answer is.

    A non-zero exit is an *answer* here — `merge-base --is-ancestor` writes nothing and
    exits 1 for "no" — so it must not collapse into the refusal the stdout runner raises.
    """
    try:
        return subprocess.run(  # noqa: S603
            ["git", *args],  # noqa: S607
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        ).returncode
    except OSError as unreadable:
        raise _GitUnreadableError(str(unreadable)) from unreadable


def _is_behind(root: Path) -> bool | None:
    """Whether this tree's HEAD is an ancestor of ``origin/main``, or ``None`` where git errored.

    ``merge-base --is-ancestor`` answers in its exit code — 0 for yes, 1 for no — and
    exits with anything else when it fails rather than answering, so a failure is
    untellable, never a folded "no" (git-merge-base's own contract; #676 review round
    two).
    """
    code = _git_code("merge-base", "--is-ancestor", "HEAD", "origin/main", root=root)
    if code in (0, 1):
        return code == 0
    detail = f"git merge-base --is-ancestor: exit {code}"
    raise _GitUnreadableError(detail)


def survey(root: Path) -> Survey:
    """Read one tree's copies against ``origin/main``, answering even where git cannot.

    Each half is read independently: a tree git cannot read at all is untellable in its
    own words, and so is a tree whose ``origin/main`` is missing — never a tree silently
    reported current.
    """
    try:
        head, names, local = _local_side(root)
    except _GitUnreadableError:
        return Survey(head="", origin_main="", behind_origin_main=None, paths={})
    try:
        origin_main, origin_names, origin = _origin_side(root, names)
        behind = _is_behind(root)
        drifted = {
            name: {
                "worktree": local.get(name, ""),
                "head": "",
                "origin_main": origin.get(name, ""),
            }
            for name in sorted(set(names).union(origin_names))
            if local.get(name, "") != origin.get(name, "")
        }
        # A path only the working tree holds is the session's own new work and stays out
        # of the report; `HEAD` holding the blob is what separates that from a landed
        # removal this tree has not taken yet.
        for name, blob in _ls_tree_blobs("HEAD", sorted(drifted), root).items():
            drifted[name]["head"] = blob
    except _GitUnreadableError:
        return Survey(head=head, origin_main="", behind_origin_main=None, paths={})
    return Survey(head=head, origin_main=origin_main, behind_origin_main=behind, paths=drifted)


def _report_line(name: str, entry: Mapping[str, str]) -> str:
    return (
        f"tool-copy: {name} behind origin/main"
        f" worktree={entry.get('worktree', '')[:12]}"
        f" origin/main={entry.get('origin_main', '')[:12]}"
    )


def main(argv: list[str] | None = None) -> int:
    """Report one line per stale governed path, silent while current.

    Every outcome exits 0 — this is a verdict, never a gate. "Cannot tell" prints rather
    than staying silent, because silence is health everywhere else on this read.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path(os.environ.get(REPO_SEAM) or Path.cwd()),
        help="the tree whose own copies are read; the calling directory by default",
    )
    parser.add_argument("verb", nargs="?", default="report", choices=("report",))
    arguments = parser.parse_args(argv)

    state = survey(arguments.repo)
    if state.behind_origin_main is None:
        print(  # noqa: T201 — the orchestrator reads this
            "tool-copy: cannot tell whether this tree's tools are behind origin/main"
            f" worktree={state.head[:12] or 'unreadable'}"
        )
        return 0
    for name in state.stale_paths():
        print(_report_line(name, state.paths[name]))  # noqa: T201 — the orchestrator reads this
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
