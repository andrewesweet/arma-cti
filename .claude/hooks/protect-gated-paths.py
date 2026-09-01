#!/usr/bin/env python3
"""PreToolUse hook (Edit|Write|Bash): deny writes to sign-off-gated or generated paths.

Edit and Write name their target in `file_path`. Bash does not, so the command
is read with the shared reader in `shell_reading.py` (#168 — before that, an
in-place `sed`, `tee`, or shell redirect onto the same paths landed unchecked)
and each command it runs is checked for a write shape aimed at a gated path:

* a redirection (`>`, `>>`, `&>`) whose target is gated;
* an in-place `sed`/`perl` (`-i`, `--in-place`) naming a gated path;
* `tee`, `rm`, `touch`, `truncate` (and kin) naming one;
* `cp`/`mv`/`ln`/`install` whose *destination* is gated — copying a spec out
  is a read and passes;
* `dd` with a gated `of=`;
* a direct `git` write whose resolved work-tree, Git directory, or pathspec is
  gated or belongs to another checkout; `git_write_paths.py` owns the
  deliberately known-incomplete Git allowlist and its fail-closed default.

Read-shaped commands on the same paths (`cat`, `grep`, `diff`, `ls`, `sed`
without `-i`) pass, and a gated path inside quoted prose or a heredoc body is
text, not a target. The reader's limits are its docstring's; within them, the
bias is fail-closed: a call or a command that cannot be read is denied (#94
findings 1-2 made fail-open the defect class for this hook family), and
PreToolUse reads any exit other than 2 as approval.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path, PurePosixPath

from shell_reading import read_command, without_assignments

# `edit_payload` and the path authority are shared with `tools/`, which is not on
# a hook's script path.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from edit_payload import edited_paths
from gated_paths import hook_denial
from git_write_paths import changed_directory, git_write_paths

REPO = Path(__file__).resolve().parents[2]

UNREADABLE_EDIT = (
    "Could not read this file-editing tool call to check it for writes to gated"
    " paths (generated files, acceptance specs)."
)

UNREADABLE = (
    "Could not read this Bash command to check it for writes to gated paths"
    " or another repository checkout. Simplify the quoting and retry."
)

# Redirections that write their target. `<`-shaped ones read theirs.
_WRITING_REDIRECTS = frozenset({">", ">>", ">|", "&>", "&>>"})
_READING_REDIRECTS = frozenset({"<", "<<", "<<-", "<<<"})
# Commands that write every path operand they are given.
_WRITES_OPERANDS = frozenset({"tee", "rm", "unlink", "shred", "touch", "truncate", "mkdir"})
# Commands that write their last operand (or the -t/--target-directory value).
_WRITES_DESTINATION = frozenset({"cp", "mv", "ln", "install"})
# Commands that write their operands only with an in-place flag.
_EDITS_IN_PLACE = frozenset({"sed", "perl"})


def _gated(path: str) -> str | None:
    """Return the shared path authority's immediate denial, or ``None``."""
    return hook_denial(path, root=REPO)


def _is_in_place_flag(word: str) -> bool:
    """Match an `-i` in a short-option cluster (`-Ei`), or the long spelling."""
    if word.startswith("--"):
        return word.startswith("--in-place")
    return word.startswith("-") and "i" in word


def _redirect_targets_and_words(tokens: list[str]) -> tuple[list[str], list[str]]:
    """Split one command's tokens into redirection targets and everything else."""
    targets: list[str] = []
    words: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in _WRITING_REDIRECTS or token in _READING_REDIRECTS:
            if token in _WRITING_REDIRECTS and index + 1 < len(tokens):
                targets.append(tokens[index + 1])
            index += 2  # skip the operator and its target
        else:
            words.append(token)
            index += 1
    return targets, words


def _shell_targets(paths: list[str], cwd: Path) -> list[str]:
    """Resolve shell paths against the command's current working directory."""
    targets: list[str] = []
    for raw_path in paths:
        path = Path(raw_path)
        targets.append(str(path if path.is_absolute() else cwd / path))
    return targets


def _has_unreadable_wrapper(tokens: list[str], words: list[str]) -> bool:
    """Refuse wrappers that can move Git's destination outside the argv shape."""
    if not words:
        return False
    name = PurePosixPath(words[0]).name
    return name == "env" or (name == "git" and tokens != without_assignments(tokens))


def _written_paths(  # noqa: C901, PLR0912 — shell and Git write classes share one fail-closed classifier
    tokens: list[str], cwd: Path
) -> list[str] | None:
    """Return every path this one command writes to, as far as it can be read."""
    stripped = without_assignments(tokens)
    targets, words = _redirect_targets_and_words(stripped)
    if not words:
        return _shell_targets(targets, cwd)
    if _has_unreadable_wrapper(tokens, words):
        return None
    name = PurePosixPath(words[0]).name
    if name == "git":
        git_targets = git_write_paths(words, cwd)
        if git_targets is None:
            return None
        targets.extend(git_targets)
    else:
        operands = [word for word in words[1:] if not word.startswith("-")]
        if name in _WRITES_OPERANDS:
            targets.extend(operands)
        elif name in _WRITES_DESTINATION:
            if operands:
                targets.append(operands[-1])
            for index, word in enumerate(words):
                if word == "-t" and index + 1 < len(words):
                    targets.append(words[index + 1])
                elif word.startswith("--target-directory="):
                    targets.append(word.removeprefix("--target-directory="))
        elif name in _EDITS_IN_PLACE and any(_is_in_place_flag(word) for word in words[1:]):
            targets.extend(operands)
        elif name == "dd":
            targets.extend(word.removeprefix("of=") for word in words[1:] if word.startswith("of="))
    return _shell_targets(targets, cwd)


def bash_denial(command: str) -> str | None:
    """Return why this Bash command is denied, or `None` to allow it."""
    segments = read_command(command)
    if segments is None:
        return UNREADABLE
    cwd = REPO
    for tokens in segments:
        paths = _written_paths(tokens, cwd)
        if paths is None:
            return UNREADABLE
        for path in paths:
            reason = _gated(path)
            if reason is not None:
                return reason
        _, words = _redirect_targets_and_words(without_assignments(tokens))
        cwd = changed_directory(words, cwd)
        if cwd is None:
            return UNREADABLE
    return None


def main() -> int:
    """Read the tool call on stdin and deny a write to a gated path."""
    try:
        data = json.load(sys.stdin)
        tool_name = data.get("tool_name", "")
        tool_input = data["tool_input"]
        command = tool_input["command"] if tool_name == "Bash" else None
    except (json.JSONDecodeError, TypeError, KeyError):
        # #94: fail closed — a call we cannot read is not an approval.
        print(
            "Could not read the tool call to check it for writes to gated paths.",
            file=sys.stderr,
        )
        return 2
    if command is not None:
        reason = bash_denial(command)
    else:
        # #273: a Codex edit carries a patch envelope, not a `file_path`. `None`
        # is unreadable and denies; `()` would mean "writes nothing", and
        # conflating the two is the #94 fail-open shape one layer in.
        paths = edited_paths(tool_input)
        if paths is None:
            print(UNREADABLE_EDIT, file=sys.stderr)
            return 2
        reason = next((gated for gated in map(_gated, paths) if gated is not None), None)
    if reason is not None:
        print(reason, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
