"""Read local write targets from a conservative subset of Git commands (#673).

The Bash hook already reads shell syntax, but it cannot treat every Git
subcommand as a read or guess every pathspec safely. This module therefore
keeps an explicit, known-incomplete enumeration. Known non-writing commands
return an empty tuple; known writes return absolute repository/work-tree or
path targets; an unknown subcommand, option shape, shell expansion, or
pathspec-file source returns ``None`` so the caller can deny it.

Repository metadata is normally outside a linked worktree's directory. That
is intentional: ordinary ``git add``, ``git commit`` and ``git rebase`` in the
assigned worktree must remain allowed. An explicit ``-C``, ``--git-dir`` or
``--work-tree`` is added to the locations checked by the caller, so a write
aimed at another checkout is not mistaken for that ordinary metadata case.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Final, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Sequence

_GIT_READS: Final = frozenset(
    {
        "blame",
        "cat-file",
        "describe",
        "diff",
        "for-each-ref",
        "grep",
        "log",
        "ls-files",
        "ls-tree",
        "name-rev",
        "rev-list",
        "rev-parse",
        "show",
        "shortlog",
        "status",
        "symbolic-ref",
        "verify-commit",
        "verify-tag",
    }
)

# ``git push`` writes to a remote, not to a local work-tree or Git directory.
# Keep it explicit so the local-write vocabulary does not call a remote write a read.
_GIT_NON_LOCAL_WRITES: Final = frozenset({"push"})

# Known repository-level writes. This is deliberately not a complete Git
# inventory: an unlisted Git subcommand is unreadable and the hook denies it.
_GIT_REPOSITORY_WRITES: Final = frozenset(
    {
        "add",
        "am",
        "cherry-pick",
        "commit",
        "config",
        "fetch",
        "merge",
        "pull",
        "rebase",
        "revert",
        "stash",
        "update-ref",
    }
)

_GIT_PATH_WRITES: Final = frozenset({"checkout", "clean", "mv", "reset", "restore", "rm", "switch"})

_GLOBAL_FLAGS: Final = frozenset(
    {
        "--bare",
        "--glob-pathspecs",
        "--icase-pathspecs",
        "--literal-pathspecs",
        "--no-lazy-fetch",
        "--no-pager",
        "--no-replace-objects",
        "--paginate",
        "--no-optional-locks",
        "--noglob-pathspecs",
    }
)
_GLOBAL_VALUE_FLAGS: Final = frozenset({"--config-env", "--namespace", "--super-prefix"})
_STANDALONE_READS: Final = frozenset({"--help", "--version", "-h"})

_RESTORE_FLAGS: Final = frozenset(
    {
        "--ignore-unmerged",
        "--merge",
        "--no-overlay",
        "--no-progress",
        "--ours",
        "--overlay",
        "--patch",
        "--progress",
        "--quiet",
        "--recurse-submodules",
        "--staged",
        "--theirs",
        "--worktree",
        "-W",
        "-S",
        "-m",
        "-p",
        "-q",
    }
)
_RESTORE_VALUE_FLAGS: Final = frozenset({"--conflict", "--source", "-s"})

_PATH_WRITE_FLAGS: Final = frozenset(
    {
        "--cached",
        "--dry-run",
        "--hard",
        "--ignore-unmatch",
        "--keep",
        "--merge",
        "--quiet",
        "--soft",
        "--verbose",
        "-f",
        "-k",
        "-n",
        "-r",
    }
)

_CLEAN_FLAGS: Final = frozenset("dfinqx")
_CLEAN_VALUE_FLAGS: Final = frozenset({"--exclude", "-e"})
_PATHSPEC_FILE_FLAGS: Final = ("--pathspec-from-file", "--pathspec-file-nul")


class _Invocation(NamedTuple):
    """Resolved Git locations and the subcommand still needing classification."""

    subcommand: str
    args: tuple[str, ...]
    base: Path
    work_tree: Path
    git_dir: Path | None
    explicit_c: bool


def _resolve(value: str, base: Path) -> Path | None:
    """Resolve one path without guessing shell variables or command output."""
    if not value or "\x00" in value or "$" in value or "`" in value:
        return None
    try:
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = base / candidate
        return candidate.resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        return None


def _path_operand(value: str, base: Path) -> Path | None:
    """Resolve a work-tree path, refusing Git pathspec forms this reader cannot bound."""
    if value == "-" or value.startswith(":(") or any(char in value for char in "*?[]"):
        return None
    return _resolve(value, base)


def _parse(  # noqa: C901, PLR0911, PLR0912, PLR0915 — one ordered option ladder fails closed
    words: Sequence[str], cwd: Path
) -> _Invocation | None:
    """Resolve Git's location flags and identify its subcommand."""
    if not words or PurePosixPath(words[0]).name != "git":
        return None
    base = _resolve(str(cwd), Path.cwd())
    if base is None:
        return None
    git_dir: Path | None = None
    work_tree: Path | None = None
    explicit_c = False
    index = 1
    while index < len(words):
        word = words[index]
        if word in _STANDALONE_READS and index == len(words) - 1:
            return _Invocation(word, (), base, work_tree or base, git_dir, explicit_c)
        if word == "-C":
            if index + 1 >= len(words):
                return None
            resolved = _resolve(words[index + 1], base)
            if resolved is None:
                return None
            base = resolved
            explicit_c = True
            index += 2
        elif word.startswith("-C") and word != "-C":
            resolved = _resolve(word[2:], base)
            if resolved is None:
                return None
            base = resolved
            explicit_c = True
            index += 1
        elif word == "--git-dir":
            if index + 1 >= len(words):
                return None
            git_dir = _resolve(words[index + 1], base)
            if git_dir is None:
                return None
            index += 2
        elif word.startswith("--git-dir="):
            git_dir = _resolve(word.removeprefix("--git-dir="), base)
            if git_dir is None:
                return None
            index += 1
        elif word == "--work-tree":
            if index + 1 >= len(words):
                return None
            work_tree = _resolve(words[index + 1], base)
            if work_tree is None:
                return None
            index += 2
        elif word.startswith("--work-tree="):
            work_tree = _resolve(word.removeprefix("--work-tree="), base)
            if work_tree is None:
                return None
            index += 1
        elif word == "-c":
            if index + 1 >= len(words):
                return None
            index += 2
        elif word.startswith("-c") and word != "-c":
            index += 1
        elif word in _GLOBAL_VALUE_FLAGS:
            if index + 1 >= len(words):
                return None
            index += 2
        elif word in _GLOBAL_FLAGS or any(
            word.startswith(f"{flag}=") for flag in _GLOBAL_VALUE_FLAGS
        ):
            index += 1
        elif word.startswith("-"):
            return None
        else:
            selected_work_tree = work_tree or base
            return _Invocation(
                word,
                tuple(words[index + 1 :]),
                base,
                selected_work_tree,
                git_dir,
                explicit_c,
            )
    return None


def _locations(invocation: _Invocation) -> tuple[str, ...]:
    """Return locations whose Git write may change state."""
    locations = [invocation.work_tree]
    if invocation.explicit_c and invocation.base != invocation.work_tree:
        locations.append(invocation.base)
    if invocation.git_dir is not None:
        locations.append(invocation.git_dir)
    return tuple(dict.fromkeys(str(path) for path in locations))


def _output_targets(args: Sequence[str], base: Path) -> tuple[str, ...] | None:
    """Read known output flags on commands that are otherwise read-only."""
    targets: list[str] = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in {"-o", "--output"}:
            if index + 1 >= len(args):
                return None
            target = _path_operand(args[index + 1], base)
            if target is None:
                return None
            targets.append(str(target))
            index += 2
        elif arg.startswith("--output="):
            target = _path_operand(arg.removeprefix("--output="), base)
            if target is None:
                return None
            targets.append(str(target))
            index += 1
        else:
            index += 1
    return tuple(targets)


def _config_is_read(args: Sequence[str]) -> bool | None:
    """Classify common local config reads; refuse scopes this reader cannot locate."""
    if any(
        arg in {"--global", "--system", "--file", "--blob", "--fixed-value"}
        or arg.startswith(("--file=", "--blob="))
        for arg in args
    ):
        return None
    return any(arg in {"--get", "--get-all", "--get-regexp", "--list", "-l"} for arg in args)


def _conditional_read(subcommand: str, args: Sequence[str]) -> bool | None:
    """Handle subcommands that read or write based on their first operand."""
    if subcommand == "config":
        return _config_is_read(args)
    if subcommand == "tag":
        write_flags = {
            "--annotate",
            "--delete",
            "--file",
            "--force",
            "--sign",
            "-a",
            "-d",
            "-f",
            "-s",
        }
        return not any(not arg.startswith("-") for arg in args) and not any(
            arg in write_flags or arg.startswith("--file=") for arg in args
        )
    if subcommand == "branch":
        return not args or all(arg.startswith("-") for arg in args)
    if subcommand == "remote":
        return not args or args[0] in {"-v", "--verbose"}
    return None


def _path_operands(
    args: Sequence[str],
    *,
    flags: frozenset[str],
    value_flags: frozenset[str] = frozenset(),
    short_cluster: str = "",
) -> tuple[str, ...] | None:
    """Extract path operands while refusing option shapes not in this inventory."""
    operands: list[str] = []
    after_separator = False
    index = 0
    while index < len(args):
        arg = args[index]
        if after_separator:
            operands.append(arg)
            index += 1
        elif arg == "--":
            after_separator = True
            index += 1
        elif arg in value_flags:
            if index + 1 >= len(args):
                return None
            index += 2
        elif arg in flags or any(arg.startswith(f"{flag}=") for flag in value_flags):
            index += 1
        elif short_cluster and arg.startswith("-") and not arg.startswith("--"):
            if len(arg) == 1 or not set(arg[1:]).issubset(set(short_cluster)):
                return None
            index += 1
        elif arg.startswith("-"):
            return None
        else:
            operands.append(arg)
            index += 1
    return tuple(operands)


def _restore_targets(invocation: _Invocation) -> tuple[str, ...] | None:
    """Read ``git restore`` pathspecs and distinguish staged-only writes."""
    args = invocation.args
    if any(
        arg == flag or arg.startswith(f"{flag}=") for arg in args for flag in _PATHSPEC_FILE_FLAGS
    ):
        return None
    operands = _path_operands(
        args,
        flags=_RESTORE_FLAGS,
        value_flags=_RESTORE_VALUE_FLAGS,
    )
    if operands is None:
        return None
    staged = "--staged" in args or "-S" in args
    writes_work_tree = not staged or "--worktree" in args or "-W" in args
    if not writes_work_tree:
        return _locations(invocation)
    targets = list(_locations(invocation))
    for operand in operands:
        target = _path_operand(operand, invocation.work_tree)
        if target is None:
            return None
        targets.append(str(target))
    return tuple(dict.fromkeys(targets))


def _checkout_targets(invocation: _Invocation) -> tuple[str, ...] | None:
    """Read only pathspecs after ``--``; branch switches affect the whole tree."""
    args = invocation.args
    if any(
        arg == flag or arg.startswith(f"{flag}=") for arg in args for flag in _PATHSPEC_FILE_FLAGS
    ):
        return None
    if "--" not in args:
        return _locations(invocation)
    separator = args.index("--")
    targets = list(_locations(invocation))
    for operand in args[separator + 1 :]:
        target = _path_operand(operand, invocation.work_tree)
        if target is None:
            return None
        targets.append(str(target))
    return tuple(dict.fromkeys(targets))


def _clean_targets(  # noqa: C901 — short-option clusters and pathspecs share one fail-closed ladder
    invocation: _Invocation,
) -> tuple[str, ...] | None:
    """Read ``git clean``'s bounded option and path forms."""
    args = invocation.args
    if "-n" in args or "--dry-run" in args:
        return ()
    operands: list[str] = []
    index = 0
    after_separator = False
    while index < len(args):
        arg = args[index]
        if after_separator:
            operands.append(arg)
            index += 1
        elif arg == "--":
            after_separator = True
            index += 1
        elif arg in _CLEAN_VALUE_FLAGS:
            if index + 1 >= len(args):
                return None
            index += 2
        elif any(arg.startswith(f"{flag}=") for flag in _CLEAN_VALUE_FLAGS):
            index += 1
        elif arg.startswith("-"):
            if arg.startswith("--") or len(arg) == 1 or not set(arg[1:]).issubset(_CLEAN_FLAGS):
                return None
            index += 1
        else:
            operands.append(arg)
            index += 1
    targets = list(_locations(invocation))
    for operand in operands:
        target = _path_operand(operand, invocation.work_tree)
        if target is None:
            return None
        targets.append(str(target))
    return tuple(dict.fromkeys(targets))


def _reset_targets(invocation: _Invocation) -> tuple[str, ...] | None:
    """Read reset's work-tree-changing modes and optional pathspecs."""
    args = invocation.args
    if any(arg in {"--hard", "--merge", "--keep"} for arg in args):
        operands = _path_operands(args, flags=_PATH_WRITE_FLAGS)
        if operands is None:
            return None
        targets = list(_locations(invocation))
        for operand in operands:
            target = _path_operand(operand, invocation.work_tree)
            if target is None:
                return None
            targets.append(str(target))
        return tuple(dict.fromkeys(targets))
    return _locations(invocation)


def git_write_paths(  # noqa: C901, PLR0911, PLR0912 — command families form one ordered refusal ladder
    words: Sequence[str], cwd: Path
) -> tuple[str, ...] | None:
    """Return Git write targets, ``()`` for known non-writes, or ``None`` to deny."""
    invocation = _parse(words, cwd)
    if invocation is None:
        return None
    if invocation.subcommand in _STANDALONE_READS or invocation.subcommand in _GIT_READS:
        outputs = _output_targets(invocation.args, invocation.base)
        if outputs is None:
            return None
        return outputs
    if invocation.subcommand in _GIT_NON_LOCAL_WRITES:
        return ()
    conditional = _conditional_read(invocation.subcommand, invocation.args)
    if conditional is True:
        return ()
    if invocation.subcommand in _GIT_PATH_WRITES:
        if invocation.subcommand == "restore":
            return _restore_targets(invocation)
        if invocation.subcommand == "checkout":
            return _checkout_targets(invocation)
        if invocation.subcommand == "clean":
            return _clean_targets(invocation)
        if invocation.subcommand == "reset":
            return _reset_targets(invocation)
        if invocation.subcommand in {"mv", "rm"}:
            if any(arg in {"--dry-run", "-n"} for arg in invocation.args):
                return ()
            operands = _path_operands(invocation.args, flags=_PATH_WRITE_FLAGS)
            if operands is None:
                return None
            targets = list(_locations(invocation))
            for operand in operands:
                target = _path_operand(operand, invocation.work_tree)
                if target is None:
                    return None
                targets.append(str(target))
            return tuple(dict.fromkeys(targets))
        return _locations(invocation)
    if invocation.subcommand in _GIT_REPOSITORY_WRITES:
        if invocation.subcommand == "rebase" and any(
            arg in {"-x", "--exec"} or arg.startswith("--exec=") for arg in invocation.args
        ):
            return None
        if invocation.subcommand == "config" and _config_is_read(invocation.args) is None:
            return None
        return _locations(invocation)
    if conditional is False:
        return _locations(invocation)
    return None


def changed_directory(words: Sequence[str], cwd: Path) -> Path | None:
    """Resolve a supported shell ``cd``; return ``None`` for an unreadable cwd change."""
    if not words:
        return cwd
    name = PurePosixPath(words[0]).name
    if name in {"dirs", "popd", "pushd"}:
        return None
    if name != "cd":
        return cwd
    args = list(words[1:])
    while args and args[0] in {"-L", "-P"}:
        args.pop(0)
    if args and args[0] == "--":
        args.pop(0)
    if len(args) != 1:
        return None
    if args[0] == "-":
        return None
    return _resolve(args[0], cwd)
