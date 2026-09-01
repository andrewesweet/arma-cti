#!/usr/bin/env python3
"""Refuse inline GitHub CLI bodies before the shell can substitute them (#675).

The shell executes backticks in a double-quoted ``--body`` argument before
``gh`` starts.  This guard therefore denies the whole inline form, not only
the bodies that currently contain backticks.  A body file keeps the Markdown
out of the command line and is the only allowed body form here.

The command reader is deliberately shared with the Bash hooks.  An unreadable
shell command is not an approval: the guard returns a denial, and so does an
incomplete ``--body-file`` option.  The GitHub subcommand vocabulary is not
enumerated; any direct ``gh`` invocation is inspected for the body options so
new comment/create commands cannot silently bypass the rule.
"""

from __future__ import annotations

import sys
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

HOOKS = Path(__file__).resolve().parents[1] / ".claude" / "hooks"
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from shell_reading import (  # noqa: E402 — hook sibling is loaded from its script directory
    read_command,
    without_assignments,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

INLINE_BODY = (
    "Inline GitHub CLI `--body` is refused. Compose the body in a file and pass"
    " `--body-file` instead; this keeps Markdown backticks literal and prevents"
    " shell command substitution."
)
UNREADABLE = (
    "Could not read this Bash command to check GitHub CLI body arguments. Compose"
    " the body in a file and retry with `--body-file`."
)

_BODY_FILE = "--body-file"
_BODY = "--body"
_GH_WRAPPERS = frozenset({"command", "exec", "env"})


def _gh_words(tokens: Sequence[str]) -> tuple[str, ...] | None:
    """Return a wrapped ``gh`` argv, or ``None`` when this is not one."""
    words = tuple(without_assignments(list(tokens)))
    if not words:
        return None
    if PurePosixPath(words[0]).name == "gh":
        return words
    if PurePosixPath(words[0]).name not in _GH_WRAPPERS:
        return None
    return _wrapped_gh_words(words)


def _wrapped_gh_words(words: Sequence[str]) -> tuple[str, ...] | None:
    """Return ``gh`` argv behind the small wrapper set this guard can parse."""
    wrapper = PurePosixPath(words[0]).name
    if wrapper in {"command", "exec"}:
        return _builtin_gh_words(words)
    return _env_gh_words(words)


def _builtin_gh_words(words: Sequence[str]) -> tuple[str, ...] | None:
    """Read the command/exec options needed before their command word."""
    index = 1
    if index < len(words) and words[index] in {"-p", "--"}:
        index += 1
    if index < len(words) and PurePosixPath(words[index]).name == "gh":
        return tuple(words[index:])
    return None


def _env_gh_words(words: Sequence[str]) -> tuple[str, ...] | None:
    """Read ``env`` options and assignments before its command word."""
    index = 1
    while index < len(words):
        word = words[index]
        if word == "--":
            index += 1
            break
        if word in {"-i", "--ignore-environment", "-0", "--null"}:
            index += 1
        elif word in {"-u", "--unset"}:
            if index + 1 >= len(words):
                return None
            index += 2
        elif word.startswith("--unset="):
            index += 1
        elif word.startswith("--"):
            return None
        elif "=" in word:
            index += 1
        else:
            break
    if index < len(words) and PurePosixPath(words[index]).name == "gh":
        return words[index:]
    return None


def _gh_denial(words: Sequence[str]) -> str | None:
    """Inspect one complete ``gh`` argv for body options."""
    index = 1
    while index < len(words):
        word = words[index]
        if word == _BODY:
            if index + 1 >= len(words):
                return UNREADABLE
            return INLINE_BODY
        if word.startswith(f"{_BODY}="):
            return INLINE_BODY
        if word == _BODY_FILE:
            if index + 1 >= len(words):
                return UNREADABLE
            index += 2
            continue
        if word == f"{_BODY_FILE}=":
            return UNREADABLE
        index += 1
    return None


def denial(command: str) -> str | None:
    """Return a refusal for an unsafe/unreadable GitHub body command."""
    segments = read_command(command)
    if segments is None:
        return UNREADABLE
    for tokens in segments:
        words = _gh_words(tokens)
        if words is not None:
            reason = _gh_denial(words)
            if reason is not None:
                return reason
    return None
