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

# A `git ls-tree` entry is `<mode> <type> <sha>\t<path>`; fewer fields carries no blob.
_LS_TREE_FIELDS: Final = 3

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
        done = subprocess.run(  # noqa: S603
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


def _directory_files(root: Path, relative: str) -> set[Path]:
    """Every file under ``root/relative``, repo-relative; empty where there is no directory."""
    directory = root / relative
    if not directory.is_dir():
        return set()
    return {
        path.relative_to(root)
        for path in directory.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
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
    ``__pycache__`` is interpreter output, not machinery, in either directory.
    """
    governed = {Path(GOVERNED_JUSTFILE), Path(GOVERNED_SETTINGS)}
    for relative in (GOVERNED_TOOL_DIR, GOVERNED_HOOK_DIR):
        governed |= _directory_files(root, relative)
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


def _worktree_hashes(root: Path, names: Sequence[str]) -> dict[str, str]:
    """Each name's blob sha as the working tree holds it; absent where the tree has no such file.

    Absent from the result is "not present", never "not hashed": a name the caller has no
    entry for yet is hashed here on demand, so an unchanged file a landing newly governs
    cannot be read as an empty worktree sha and reported superseded (#676 round three,
    finding 3).
    """
    present = [name for name in names if (root / name).is_file()]
    if not present:
        return {}
    listed = _git("hash-object", "--", *present, root=root).split()
    return dict(zip(present, listed, strict=False))


def _local_side(root: Path) -> tuple[str, tuple[str, ...], dict[str, str]]:
    """Read this tree's own half: HEAD, the governed set, each path's working-tree blob."""
    head = _git("rev-parse", "HEAD", root=root).strip()
    names = tuple(path.as_posix() for path in governed_paths(root))
    return head, names, _worktree_hashes(root, names)


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
        GOVERNED_TOOL_DIR,
        GOVERNED_HOOK_DIR,
        root=root,
    )
    names = {Path(GOVERNED_JUSTFILE), Path(GOVERNED_SETTINGS)}
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
    is surveyed on the origin side even where this tree has never had it — a tool the
    landing added is behind on exactly that file, and deriving the set only from this
    tree would read that absence as current.
    """
    origin_main = _git("rev-parse", "origin/main", root=root).strip()
    origin_names = _origin_governed(root)
    # One listing over the whole surveyed set, rather than a `rev-parse` per path.
    blobs = _ls_tree_blobs("origin/main", list(dict.fromkeys([*names, *origin_names])), root)
    return origin_main, origin_names, blobs


def _git_code(*args: str, root: Path) -> int:
    """Run one bounded git command for its exit code alone, which `--is-ancestor`'s answer is.

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
            timeout=GIT_TIMEOUT,
        ).returncode
    except OSError as unreadable:
        raise _GitUnreadableError(str(unreadable)) from unreadable
    except subprocess.TimeoutExpired as unanswered:
        detail = f"git {' '.join(args)}: no answer within {GIT_TIMEOUT:g}s"
        raise _GitUnreadableError(detail) from unanswered


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
        walked = sorted(set(names).union(origin_names))
        # A name the local set never held has no entry yet — that is "not hashed", never
        # "not present". Hash on demand, so an unchanged file a landing newly governs is
        # not read as an empty worktree sha and reported superseded (round three, #3).
        local.update(_worktree_hashes(root, [name for name in walked if name not in local]))
        drifted = {
            name: {
                "worktree": local.get(name, ""),
                "head": "",
                "origin_main": origin.get(name, ""),
            }
            for name in walked
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
