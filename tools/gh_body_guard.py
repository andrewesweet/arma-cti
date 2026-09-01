#!/usr/bin/env python3
"""Refuse unproven GitHub CLI body sources before shell substitution (#675).

The shell executes backticks in an inline body before ``gh`` starts.  This
guard therefore asks whether a direct ``gh`` invocation's body is positively
file-backed, rather than enumerating commands or allowing unknown options by
default.  A complete recognised file option clears the refusal; an inline,
unknown, or incomplete body option remains unestablished and is denied.

The command reader is deliberately shared with the Bash hooks.  An unreadable
shell command is not an approval.  The guard covers shell-visible direct
``gh`` invocations and the wrappers it can parse; nested interpreters, shell
aliases, and arbitrary wrapper scripts remain outside its reach and are not
claimed safe by this module.
"""

from __future__ import annotations

import sys
from enum import Enum
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
    "Inline GitHub CLI body is refused. Compose the body in a file and pass a"
    " file-backed body option (`--body-file` or `-F`) instead; this keeps Markdown"
    " backticks literal and prevents shell command substitution."
)
UNREADABLE = (
    "Could not establish a file-backed GitHub CLI body or read this Bash command."
    " Compose the body in a file and retry with `--body-file` or `-F`."
)

_BODY_FILE = "--body-file"
_BODY_FILE_SHORT = "-F"
_COMMENT_FILE = "--comment-file"
_BODY_INLINE = frozenset({"--body", "--comment"})
_BODY_PREFIXES = ("--body", "--comment")
_GH_WRAPPERS = frozenset({"command", "exec", "env"})


class _BodySource(Enum):
    """Source classification for one body-shaped option."""

    FILE = "file"
    INLINE = "inline"
    UNKNOWN = "unknown"


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


def _body_option_source(word: str) -> _BodySource | None:
    """Classify body-shaped options without enumerating GitHub subcommands."""
    if word in {_BODY_FILE, _COMMENT_FILE, _BODY_FILE_SHORT} or word.startswith(
        (f"{_BODY_FILE}=", f"{_COMMENT_FILE}=", "-F")
    ):
        return _BodySource.FILE
    if word in _BODY_INLINE or word.startswith(("--body=", "--comment=", "-b", "-c")):
        return _BodySource.INLINE
    if word == "--comments":
        return None
    if word.startswith(_BODY_PREFIXES):
        return _BodySource.UNKNOWN
    if word.startswith("-") and not word.startswith("--"):
        return _BodySource.UNKNOWN
    return None


def _gh_denial(words: Sequence[str]) -> str | None:
    """Inspect one complete ``gh`` argv, clearing only proven file bodies."""
    index = 1
    while index < len(words):
        word = words[index]
        if word == "--":
            break
        source = _body_option_source(word)
        if source is _BodySource.FILE:
            if word.endswith("=") or (
                word in {_BODY_FILE, _COMMENT_FILE, _BODY_FILE_SHORT}
                and (
                    index + 1 >= len(words)
                    or (words[index + 1].startswith("-") and words[index + 1] != "-")
                )
            ):
                return UNREADABLE
            index += 1 if word not in {_BODY_FILE, _COMMENT_FILE, _BODY_FILE_SHORT} else 2
            continue
        if source is _BodySource.INLINE:
            if (word in _BODY_INLINE or word in {"-b", "-c"}) and index + 1 >= len(words):
                return UNREADABLE
            return INLINE_BODY
        if source is _BodySource.UNKNOWN:
            return UNREADABLE
        index += 1
    return None


def denial(command: str) -> str | None:
    """Return a refusal for an unsafe/unreadable GitHub body command."""
    segments = read_command(command)
    if segments is None:
        return UNREADABLE
    for tokens in segments:
        raw_words = tuple(without_assignments(list(tokens)))
        wrapper = PurePosixPath(raw_words[0]).name if raw_words else ""
        words = _gh_words(tokens)
        if (
            words is None
            and wrapper in _GH_WRAPPERS
            and any(PurePosixPath(word).name == "gh" for word in raw_words[1:])
        ):
            return UNREADABLE
        if words is not None:
            reason = _gh_denial(words)
            if reason is not None:
                return reason
    return None
