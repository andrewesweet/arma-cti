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
* `dd` with a gated `of=`.

Read-shaped commands on the same paths (`cat`, `grep`, `diff`, `ls`, `sed`
without `-i`) pass, and a gated path inside quoted prose or a heredoc body is
text, not a target. The reader's limits are its docstring's; within them, the
bias is fail-closed: a call or a command that cannot be read is denied (#94
findings 1-2 made fail-open the defect class for this hook family), and
PreToolUse reads any exit other than 2 as approval.
"""

from __future__ import annotations

import fnmatch
import json
import sys
from pathlib import PurePosixPath

from shell_reading import read_command, without_assignments

GATED = [
    ("*/generated/*", "Generated file. Edit the schema source and regenerate; never hand-edit."),
    (
        "*tests/specs/*",
        (
            "Acceptance spec. Specs encode human intent and are sign-off gated"
            " (CLAUDE.md); propose the change to the user instead of editing."
        ),
    ),
]

UNREADABLE = (
    "Could not read this Bash command to check it for writes to gated paths"
    " (generated files, acceptance specs). Simplify the quoting and retry."
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
    """Return the reason `path` is gated, or `None`.

    A relative path is also tried with a `./` prefix (`generated/x` from inside
    the addon) and a trailing slash (the directory itself, as `rm -rf` names
    it), so the globs keep their one authoritative spelling.
    """
    for candidate in (path, f"./{path}", f"{path}/", f"./{path}/"):
        for pattern, reason in GATED:
            if fnmatch.fnmatch(candidate, pattern):
                return reason
    return None


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


def _written_paths(tokens: list[str]) -> list[str]:
    """Return every path this one command writes to, as far as it can be read."""
    targets, words = _redirect_targets_and_words(without_assignments(tokens))
    if not words:
        return targets
    name = PurePosixPath(words[0]).name
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
    return targets


def bash_denial(command: str) -> str | None:
    """Return why this Bash command is denied, or `None` to allow it."""
    segments = read_command(command)
    if segments is None:
        return UNREADABLE
    for tokens in segments:
        for path in _written_paths(tokens):
            reason = _gated(path)
            if reason is not None:
                return reason
    return None


def main() -> int:
    """Read the tool call on stdin and deny a write to a gated path."""
    try:
        data = json.load(sys.stdin)
        tool_name = data.get("tool_name", "")
        tool_input = data["tool_input"]
        target = tool_input["command"] if tool_name == "Bash" else tool_input["file_path"]
    except (json.JSONDecodeError, TypeError, KeyError):
        # #94: fail closed — a call we cannot read is not an approval.
        print(
            "Could not read the tool call to check it for writes to gated paths.",
            file=sys.stderr,
        )
        return 2
    reason = bash_denial(target) if tool_name == "Bash" else _gated(target)
    if reason is not None:
        print(reason, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
