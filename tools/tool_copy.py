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

The governed set is the machinery this tree loads, and it is deliberately coarser than
the paths this session's own commands invoke: the **whole of** ``tools/`` — the helpers
``tools/dispatch.py`` imports and runs are machinery no recipe names — beside the
``.claude/hooks/`` surface the harness runs from this tree's own copy (the #120 shape),
the ``.claude/settings.json`` that wires it, and the justfile itself. It will therefore
name a landed change to a tool this session never invoked, and that over-report is the
correct direction of error: "your copy is not what landed" is true either way and the
reader's response is the same, while under-reporting is what silently ships a stale
dispatcher (#676, the narrowing ruling of round three). Test modules, docs and other
sources stay outside it — they are read, not executed, and naming them would turn every
landing into a drift report.

A path is **stale** where the copy this tree holds — mode and bytes — differs from what
``origin/main`` holds. That fact is read off the blob comparison alone, never off commit
topology: the question is which bytes the interpreter loads, and ancestry is a property
of history, not of bytes (#676 round four deleted the ancestry test, which had read even
that question wrong a different way in each of three rounds). Reading ``origin/main``
uses the local ref without fetching — ``just land`` and ``just worktree add`` fetch as
a matter of routine, so the ref is fresh exactly where the loop needs it to be. The walk
is over the **union** of the two governed sets, so a path the landing added is surveyed
though no local set could hold it, and the record and the rung carry the mode and blob
sha each of the three sides holds: the working tree, ``HEAD`` and ``origin/main``, empty
where a side does not hold the path. ``HEAD`` is what separates a path only the working
tree holds — this session's own uncommitted new work, never a report — from every other
drift; a path this tree holds **committed** and ``origin/main`` does not has the same
signature whether it is a landed removal or the session's own candidate, so it is named
either way — the over-report the narrowing ruling calls the correct direction of error.
Blob shas come from ``git hash-object`` over the working-tree bytes, so an uncommitted
edit shows as drift too.
"""

from __future__ import annotations

import argparse
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

GOVERNED_JUSTFILE: Final = "justfile"
GOVERNED_HOOK_DIR: Final = ".claude/hooks"
GOVERNED_SETTINGS: Final = ".claude/settings.json"
GOVERNED_TOOL_DIR: Final = "tools"

# The governed roots and singletons, named once: both walks read these, and the two
# halves of the walk drifting apart is the defect round two's finding 2 was (#676).
_GOVERNED_DIRS: Final = (GOVERNED_TOOL_DIR, GOVERNED_HOOK_DIR)
_GOVERNED_FILES: Final = (GOVERNED_JUSTFILE, GOVERNED_SETTINGS)

# A `git ls-tree` entry is `<mode> <type> <sha>\t<path>`; fewer fields carries no blob.
_LS_TREE_FIELDS: Final = 3

# A comparison side that does not hold the path: a real entry always names a mode and a
# blob, so the empty pair is unambiguous.
_ABSENT_SIDE: Final = ("", "")

# Every git read is bounded, because this module runs at the top of an orchestrator turn
# (the `just watch-report` rung) and a git that never answers would stall that turn rather
# than fail it (#676 round three, finding 4). A timed-out read is untellable, like every
# other read git refused.
GIT_TIMEOUT: Final = 30.0

# The state-directory seam the other rungs carry (#249), so a test never depends on what
# the box is holding. This one reads the repository instead of a state directory, so the
# seam names the repository.
REPO_SEAM: Final = "CTI_TOOL_COPY_REPO"


class _GitUnreadableError(Exception):
    """git refused or never started — the same "could not tell me" dispatch.py's git encodes."""


def _git(*args: str, root: Path) -> str:
    """Run one bounded git command and return its stdout; raise where git could not answer."""
    try:
        done = subprocess.run(  # noqa: S603 — fixed argv list, never a shell string
            ["git", *args],  # noqa: S607 — the checkout's toolchain is the caller's
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=GIT_TIMEOUT,
        )
    except OSError as unreadable:
        raise _GitUnreadableError(str(unreadable)) from unreadable
    except subprocess.TimeoutExpired as unanswered:
        detail = f"git {' '.join(args)}: no answer within {GIT_TIMEOUT:g}s"
        raise _GitUnreadableError(detail) from unanswered
    if done.returncode != 0:
        detail = (done.stderr or "").strip().splitlines()
        raise _GitUnreadableError(
            detail[-1] if detail else f"git {' '.join(args)}: exit {done.returncode}"
        )
    return done.stdout


def _is_machinery(path: Path) -> bool:
    """``__pycache__`` is interpreter output, not machinery, on either side of the walk."""
    return "__pycache__" not in path.parts


def _directory_files(root: Path, relative: str) -> set[Path]:
    """Every file under ``root/relative``, repo-relative; empty where there is no directory."""
    directory = root / relative
    if not directory.is_dir():
        return set()
    return {
        path.relative_to(root)
        for path in directory.rglob("*")
        if path.is_file() and _is_machinery(path)
    }


def governed_paths(root: Path) -> tuple[Path, ...]:
    """Return the files this tree loads as its own command machinery, sorted, posix-named.

    The set is deliberately coarser than the paths this session's own commands invoke:
    the whole of ``tools/`` — the helpers ``tools/dispatch.py`` imports and runs are
    machinery no recipe names — beside the ``.claude/hooks/`` surface and its wiring and
    the justfile. So it names a landed change to a tool this session never invoked, and
    that over-report is the correct direction of error: "your copy is not what landed" is
    true either way and the reader's response is the same, while under-reporting is what
    silently ships a stale dispatcher (#676, the narrowing ruling of round three).
    """
    governed = {Path(name) for name in _GOVERNED_FILES}
    for relative in _GOVERNED_DIRS:
        governed |= _directory_files(root, relative)
    return tuple(sorted(governed, key=lambda path: path.as_posix()))


@dataclass(frozen=True)
class Survey:
    """One read of a tree's copies against ``origin/main``, at one instant.

    ``paths`` carries **only** the governed paths whose working-tree copy — mode and
    bytes — differs from ``origin/main``'s, walked over the **union** of the two governed
    sets, with the mode and blob sha each of the three sides holds beside the others:
    ``worktree``/``worktree_mode`` (the working tree), ``head``/``head_mode`` (the tree's
    own ``HEAD`` commit) and ``origin_main``/``origin_main_mode`` — empty where that side
    does not hold the path. Every other path is current and is deliberately absent: a
    full listing per dispatch would be a dashboard of sameness (#209).
    """

    head: str
    # Empty exactly where git could not answer, which is the "could not tell" verdict the
    # report prints; a read that succeeded always carries the sha `rev-parse` printed. It
    # is never folded into a healthy-looking value, because an unreadable ref reads as
    # health nowhere else in this project's reporting.
    origin_main: str
    paths: Mapping[str, Mapping[str, str]] = field(default_factory=dict)

    def stale_paths(self) -> tuple[str, ...]:
        """Return the governed paths whose copy is not what ``origin/main`` landed.

        One exclusion keeps the report from crying wolf: a path only the working tree
        holds — ``origin/main`` and ``HEAD`` both empty — is this session's own
        uncommitted new work, which no landing has superseded. Every other drift is
        named, a landed removal included.
        """
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
            "paths": {name: dict(entry) for name, entry in sorted(self.paths.items())},
        }

    @classmethod
    def from_document(cls, document: object) -> Survey | None:
        """Read back what ``document`` wrote, or ``None`` where no record carries one."""
        if not isinstance(document, dict):
            return None
        paths = document.get("paths")
        return cls(
            head=str(document.get("worktree_head", "")),
            origin_main=str(document.get("origin_main_head", "")),
            paths={
                str(name): dict(entry) for name, entry in paths.items() if isinstance(entry, dict)
            }
            if isinstance(paths, dict)
            else {},
        )


def _worktree_mode(path: Path) -> str:
    """Return the mode git records for this file: any executable bit is 100755."""
    if path.is_symlink():
        return "120000"
    return "100755" if os.access(path, os.X_OK) else "100644"


def _worktree_entries(root: Path, names: Sequence[str]) -> dict[str, tuple[str, str]]:
    """Each name's ``(mode, blob sha)`` as the working tree holds it; absent where it has no file.

    Absent from the result is "not present", never "not hashed": a name the caller has no
    entry for yet is hashed here on demand, so an unchanged file a landing newly governs
    cannot be read as an empty worktree side and reported superseded (#676 round three,
    finding 3).
    """
    present = [name for name in names if (root / name).is_file()]
    if not present:
        return {}
    listed = _git("hash-object", "--", *present, root=root).split()
    return {
        name: (_worktree_mode(root / name), blob)
        for name, blob in zip(present, listed, strict=False)
    }


def _local_side(root: Path) -> tuple[str, tuple[str, ...], dict[str, tuple[str, str]]]:
    """Read this tree's own half: HEAD, the governed set, each path's mode and blob."""
    head = _git("rev-parse", "HEAD", root=root).strip()
    names = tuple(path.as_posix() for path in governed_paths(root))
    return head, names, _worktree_entries(root, names)


def _origin_governed(root: Path) -> tuple[str, ...]:
    """Read the governed set as ``origin/main`` names it, without a checkout.

    One ``ls-tree`` over the two machinery directories, plus the justfile and the wiring
    files — the same definition ``governed_paths`` applies to this tree, applied to the
    landing's own tree, so the two halves of the walk cannot drift apart: a path the
    landing added or renamed is surveyed on the origin side even where this tree has
    never had it.
    """
    listed = _git(
        "ls-tree",
        "-r",
        "--name-only",
        "-z",
        "origin/main",
        "--",
        *_GOVERNED_DIRS,
        root=root,
    )
    names = {Path(name) for name in _GOVERNED_FILES}
    names.update(Path(line) for line in listed.split("\0") if line and _is_machinery(Path(line)))
    return tuple(sorted({name.as_posix() for name in names}))


def _ls_tree_entries(rev: str, names: Sequence[str], root: Path) -> dict[str, tuple[str, str]]:
    """Each name's ``(mode, blob sha)`` as ``rev`` holds it; absent where ``rev`` has no file."""
    entries: dict[str, tuple[str, str]] = {}
    if not names:
        return entries
    for entry in _git("ls-tree", "-z", rev, "--", *names, root=root).split("\0"):
        if not entry:
            continue
        meta, _, path = entry.partition("\t")
        parts = meta.split()
        if len(parts) >= _LS_TREE_FIELDS:
            entries[path] = (parts[0], parts[2])
    return entries


def _origin_side(
    root: Path, names: tuple[str, ...]
) -> tuple[str, tuple[str, ...], dict[str, tuple[str, str]]]:
    """``origin/main``'s half: its head, its governed set, and each governed path's mode and blob.

    The origin side derives its own governed set, so a path the landing added or renamed
    is surveyed on the origin side even where this tree has never had it — a tool the
    landing added is behind on exactly that file, and deriving the set only from this
    tree would read that absence as current.
    """
    origin_main = _git("rev-parse", "origin/main", root=root).strip()
    origin_names = _origin_governed(root)
    # One listing over the whole surveyed set, rather than a `rev-parse` per path.
    blobs = _ls_tree_entries("origin/main", list(dict.fromkeys([*names, *origin_names])), root)
    return origin_main, origin_names, blobs


def survey(root: Path) -> Survey:
    """Read one tree's copies against ``origin/main``, answering even where git cannot.

    Each half is read independently: a tree git cannot read at all is untellable in its
    own words, and so is a tree whose ``origin/main`` is missing — never a tree silently
    reported current.
    """
    try:
        head, names, local = _local_side(root)
    except _GitUnreadableError:
        return Survey(head="", origin_main="", paths={})
    try:
        origin_main, origin_names, origin = _origin_side(root, names)
        walked = sorted(set(names).union(origin_names))
        # A name the local set never held has no entry yet — that is "not hashed", never
        # "not present". Hash on demand, so an unchanged file a landing newly governs is
        # not read as an empty worktree side and reported superseded (round three, #3).
        local.update(_worktree_entries(root, [name for name in walked if name not in local]))
        # One comparison per path, over mode and blob together: a permissions-only
        # landing keeps the same blob sha, so the mode is the other half of the copy
        # (#676 round four). Nothing here reads commit topology.
        drifted = {
            name: {
                "worktree": mine[1],
                "worktree_mode": mine[0],
                "head": "",
                "head_mode": "",
                "origin_main": theirs[1],
                "origin_main_mode": theirs[0],
            }
            for name in walked
            if (mine := local.get(name, _ABSENT_SIDE)) != (theirs := origin.get(name, _ABSENT_SIDE))
        }
        # `HEAD` holding the blob separates a path only the working tree holds — the
        # session's own new work, never reported — from every other drift.
        for name, (mode, blob) in _ls_tree_entries("HEAD", sorted(drifted), root).items():
            drifted[name]["head"] = blob
            drifted[name]["head_mode"] = mode
    except _GitUnreadableError:
        return Survey(head=head, origin_main="", paths={})
    return Survey(head=head, origin_main=origin_main, paths=drifted)


def _report_line(name: str, entry: Mapping[str, str]) -> str:
    return (
        f"tool-copy: {name} is not what origin/main landed"
        f" worktree={entry.get('worktree', '')[:12]}"
        f" worktree_mode={entry.get('worktree_mode', '')}"
        f" origin/main={entry.get('origin_main', '')[:12]}"
        f" origin/main_mode={entry.get('origin_main_mode', '')}"
    )


def main(argv: list[str] | None = None) -> int:
    """Report one line per governed path whose copy is not what ``origin/main`` landed.

    Every outcome exits 0 — this is a verdict, never a gate; the recipe's own site
    classifies a killed or crashed rung (ADR-0049). "Cannot tell" prints rather than
    staying silent, because silence is health everywhere else on this read.
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
    if not state.origin_main:
        print(  # noqa: T201 — the orchestrator reads this
            "tool-copy: cannot tell whether this tree's tools are what origin/main landed"
            f" worktree={state.head[:12] or 'unreadable'}"
        )
        return 0
    for name in state.stale_paths():
        print(_report_line(name, state.paths[name]))  # noqa: T201 — the orchestrator reads this
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
