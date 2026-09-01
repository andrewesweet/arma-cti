#!/usr/bin/env python3
"""Refuse unproven GitHub CLI body sources before shell substitution (#675).

The shell executes backticks in an inline body before ``gh`` starts.  This
guard therefore asks whether a direct ``gh`` invocation's body is positively
file-backed, resolving the option meanings against the command.  A complete
recognised file option clears the refusal; an inline, unknown, or incomplete
body option remains unestablished and is denied.  Known commands that cannot
carry a body do not inspect unrelated options; an unmodelled command's
body-shaped options remain unestablished.

The command reader is deliberately shared with the Bash hooks.  An unreadable
shell command is not an approval.  The guard covers shell-visible direct
``gh`` invocations and the wrappers it can parse; nested interpreters, shell
aliases, and arbitrary wrapper scripts remain outside its reach and are not
claimed safe by this module.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
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
    " command-specific file-backed body option (for example `--body-file` or"
    " `gh api --input`) instead; this keeps Markdown backticks literal and"
    " prevents shell command substitution."
)
UNREADABLE = (
    "Could not establish a command-specific file-backed GitHub CLI body or read"
    " this Bash command. Compose the body in a file and retry with the command's"
    " file-backed body option."
)

_BODY_PREFIXES = ("--body", "--comment")
_BODY_INLINE_SHORTS = frozenset({"-b", "-c"})
_BODY_FILE_SHORTS = frozenset({"-F", "-f"})
_GH_WRAPPERS = frozenset({"command", "exec", "env"})
_GLOBAL_VALUE_OPTIONS = frozenset({"-R", "--repo"})


@dataclass(frozen=True, slots=True)
class _CommandSpec:
    """The body-relevant and short options for one body-capable command."""

    body_inline: frozenset[str]
    body_file: frozenset[str]
    short_value_options: frozenset[str]
    short_flags: frozenset[str]
    non_body_long: frozenset[str] = frozenset()


_BODY_FILE_SPEC = _CommandSpec(
    body_inline=frozenset({"--body", "-b"}),
    body_file=frozenset({"--body-file", "-F"}),
    short_value_options=frozenset({"-F", "-R", "-b"}),
    short_flags=frozenset({"-e", "-w"}),
)
_ISSUE_CREATE_SPEC = _CommandSpec(
    body_inline=frozenset({"--body", "-b"}),
    body_file=frozenset({"--body-file", "-F"}),
    short_value_options=frozenset({"-R", "-F", "-a", "-b", "-l", "-m", "-p", "-t", "-T"}),
    short_flags=frozenset({"-e", "-w"}),
)
_ISSUE_EDIT_SPEC = _CommandSpec(
    body_inline=frozenset({"--body", "-b"}),
    body_file=frozenset({"--body-file", "-F"}),
    short_value_options=frozenset({"-R", "-F", "-b", "-m", "-t"}),
    short_flags=frozenset(),
)
_ISSUE_CLOSE_SPEC = _CommandSpec(
    body_inline=frozenset({"--comment", "-c"}),
    body_file=frozenset(),
    short_value_options=frozenset({"-R", "-c", "-r"}),
    short_flags=frozenset(),
)
_PR_CREATE_SPEC = _CommandSpec(
    body_inline=frozenset({"--body", "-b"}),
    body_file=frozenset({"--body-file", "-F"}),
    short_value_options=frozenset(
        {"-B", "-R", "-F", "-H", "-a", "-b", "-l", "-m", "-p", "-r", "-t"}
    ),
    short_flags=frozenset({"-d", "-e", "-f", "-w"}),
)
_PR_EDIT_SPEC = _CommandSpec(
    body_inline=frozenset({"--body", "-b"}),
    body_file=frozenset({"--body-file", "-F"}),
    short_value_options=frozenset({"-B", "-R", "-F", "-b", "-m", "-t"}),
    short_flags=frozenset(),
)
_PR_CLOSE_SPEC = _CommandSpec(
    body_inline=frozenset({"--comment", "-c"}),
    body_file=frozenset(),
    short_value_options=frozenset({"-R", "-c"}),
    short_flags=frozenset({"-d"}),
)
_PR_REVIEW_SPEC = _CommandSpec(
    body_inline=frozenset({"--body", "-b"}),
    body_file=frozenset({"--body-file", "-F"}),
    short_value_options=frozenset({"-F", "-R", "-b"}),
    short_flags=frozenset({"-a", "-c", "-r"}),
    non_body_long=frozenset({"--comment"}),
)
_PR_MERGE_SPEC = _CommandSpec(
    body_inline=frozenset({"--body", "-b"}),
    body_file=frozenset({"--body-file", "-F"}),
    short_value_options=frozenset({"-A", "-F", "-R", "-b", "-t"}),
    short_flags=frozenset({"-d", "-m", "-r", "-s"}),
)
_PR_REVERT_SPEC = _CommandSpec(
    body_inline=frozenset({"--body", "-b"}),
    body_file=frozenset({"--body-file", "-F"}),
    short_value_options=frozenset({"-F", "-R", "-b", "-t"}),
    short_flags=frozenset({"-d"}),
)
_DISCUSSION_CREATE_SPEC = _CommandSpec(
    body_inline=frozenset({"--body", "-b"}),
    body_file=frozenset({"--body-file", "-F"}),
    short_value_options=frozenset({"-F", "-R", "-b", "-c", "-l", "-t"}),
    short_flags=frozenset(),
)

_BODY_COMMANDS: dict[tuple[str, ...], _CommandSpec] = {
    ("issue", "comment"): _BODY_FILE_SPEC,
    ("issue", "create"): _ISSUE_CREATE_SPEC,
    ("issue", "edit"): _ISSUE_EDIT_SPEC,
    ("issue", "close"): _ISSUE_CLOSE_SPEC,
    ("issue", "new"): _ISSUE_CREATE_SPEC,
    ("pr", "comment"): _BODY_FILE_SPEC,
    ("pr", "create"): _PR_CREATE_SPEC,
    ("pr", "edit"): _PR_EDIT_SPEC,
    ("pr", "close"): _PR_CLOSE_SPEC,
    ("pr", "review"): _PR_REVIEW_SPEC,
    ("pr", "merge"): _PR_MERGE_SPEC,
    ("pr", "revert"): _PR_REVERT_SPEC,
    ("pr", "new"): _PR_CREATE_SPEC,
    ("discussion", "create"): _DISCUSSION_CREATE_SPEC,
}
_NO_BODY_COMMANDS = frozenset(
    {
        ("issue", "delete"),
        ("issue", "develop"),
        ("issue", "list"),
        ("issue", "lock"),
        ("issue", "pin"),
        ("issue", "reopen"),
        ("issue", "status"),
        ("issue", "transfer"),
        ("issue", "unlock"),
        ("issue", "unpin"),
        ("issue", "view"),
        ("pr", "checkout"),
        ("pr", "checks"),
        ("pr", "diff"),
        ("pr", "list"),
        ("pr", "lock"),
        ("pr", "ready"),
        ("pr", "reopen"),
        ("pr", "status"),
        ("pr", "unlock"),
        ("pr", "update-branch"),
        ("pr", "view"),
        ("repo", "view"),
    }
)
_COMMAND_PARENTS = frozenset({"discussion", "issue", "pr", "repo"})

_API_FIELD_OPTIONS = frozenset({"--field", "--raw-field", "-F", "-f"})
_API_INPUT_OPTIONS = frozenset({"--input"})
_API_SHORT_VALUE_OPTIONS = frozenset({"-H", "-X", "-p", "-q", "-t"})
_API_SHORT_FLAGS = frozenset({"-i"})
_API_LONG_VALUE_OPTIONS = frozenset(
    {"--cache", "--header", "--hostname", "--jq", "--method", "--preview", "--template"}
)
_API_LONG_FLAGS = frozenset(
    {
        "--allow-escape-sequences",
        "--include",
        "--paginate",
        "--silent",
        "--slurp",
        "--verbose",
    }
)


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


def _matched_option(word: str, options: frozenset[str]) -> tuple[str, bool, str] | None:
    """Match an exact or value-attached option and return its value form."""
    for option in options:
        if word == option:
            return option, False, ""
        if option.startswith("--") and word.startswith(f"{option}="):
            return option, True, word[len(option) + 1 :]
        if option.startswith("-") and not option.startswith("--") and word.startswith(option):
            value = word[len(option) :].removeprefix("=")
            return option, True, value
    return None


def _short_option(word: str) -> str | None:
    """Return the short option name from an option with an attached value."""
    if len(word) > 1 and word.startswith("-") and not word.startswith("--"):
        return word[:2]
    return None


def _command_path(words: Sequence[str]) -> tuple[str, ...] | None:
    """Read the modeled command path, skipping root and parent repo options."""
    index = 1
    while index < len(words):
        word = words[index]
        if word == "--":
            return None
        if word.startswith("-"):
            match = _matched_option(word, _GLOBAL_VALUE_OPTIONS)
            index += 1 if match is None or match[1] else 2
            continue
        if word not in _COMMAND_PARENTS:
            return (word,)
        parent = word
        index += 1
        while index < len(words):
            word = words[index]
            if word == "--":
                return (parent,)
            if word.startswith("-"):
                match = _matched_option(word, _GLOBAL_VALUE_OPTIONS)
                index += 1 if match is None or match[1] else 2
                continue
            return parent, word
        return (parent,)
    return None


def _body_option_match(
    word: str, spec: _CommandSpec
) -> tuple[_BodySource, tuple[str, bool, str] | None] | None:
    """Classify a body-shaped option using its command's option meanings."""
    file_match = _matched_option(word, spec.body_file)
    if file_match is not None:
        return _BodySource.FILE, file_match
    inline_match = _matched_option(word, spec.body_inline)
    if inline_match is not None:
        return _BodySource.INLINE, inline_match
    if word in spec.non_body_long or word == "--comments":
        return None
    if word.startswith(_BODY_PREFIXES):
        return _BodySource.UNKNOWN, None
    short = _short_option(word)
    if short in _BODY_INLINE_SHORTS | _BODY_FILE_SHORTS and short not in (
        spec.short_value_options | spec.short_flags
    ):
        return _BodySource.UNKNOWN, None
    return None


def _file_option_incomplete(words: Sequence[str], index: int, match: tuple[str, bool, str]) -> bool:
    """Report whether a file option has no usable path value."""
    _option, attached, value = match
    if attached:
        return not value
    return index + 1 >= len(words) or (words[index + 1].startswith("-") and words[index + 1] != "-")


def _inline_option_incomplete(
    words: Sequence[str], index: int, match: tuple[str, bool, str]
) -> bool:
    """Report whether an inline option is missing its separate value."""
    _option, attached, _value = match
    return not attached and index + 1 >= len(words)


def _known_short_step(
    words: Sequence[str],
    index: int,
    value_options: frozenset[str],
    flags: frozenset[str],
) -> tuple[str | None, int] | None:
    """Advance over a known short option, or refuse an unknown one."""
    short = _short_option(words[index])
    if short is None:
        return None
    if short not in value_options | flags:
        return UNREADABLE, index
    if short in value_options and words[index] == short:
        if index + 1 >= len(words):
            return UNREADABLE, index
        return None, index + 2
    return None, index + 1


def _spec_body_step(
    words: Sequence[str], index: int, spec: _CommandSpec
) -> tuple[str | None, int] | None:
    """Classify and advance over one option in a modeled body command."""
    body_match = _body_option_match(words[index], spec)
    if body_match is not None:
        source, match = body_match
        if source is _BodySource.UNKNOWN or match is None:
            return UNREADABLE, index
        if source is _BodySource.FILE:
            if _file_option_incomplete(words, index, match):
                return UNREADABLE, index
            return None, index + (1 if match[1] else 2)
        if _inline_option_incomplete(words, index, match):
            return UNREADABLE, index
        return INLINE_BODY, index
    return _known_short_step(words, index, spec.short_value_options, spec.short_flags)


def _gh_denial_for_spec(words: Sequence[str], spec: _CommandSpec) -> str | None:
    """Inspect one modeled body-capable command."""
    index = 1
    while index < len(words) and words[index] != "--":
        step = _spec_body_step(words, index, spec)
        if step is None:
            index += 1
            continue
        reason, index = step
        if reason is not None:
            return reason
    return None


def _unmodeled_body_option_source(word: str) -> _BodySource | None:
    """Classify only body-shaped options when the command is not modeled."""
    if word == "--comments":
        return None
    if word in {"--body", "--comment"} or word.startswith(("--body=", "--comment=")):
        return _BodySource.INLINE
    if word.startswith(_BODY_PREFIXES):
        return _BodySource.UNKNOWN
    short = _short_option(word)
    if short in _BODY_INLINE_SHORTS:
        return _BodySource.INLINE
    if short in _BODY_FILE_SHORTS:
        return _BodySource.UNKNOWN
    return None


def _gh_denial_for_unmodeled(words: Sequence[str]) -> str | None:
    """Inspect body-shaped options without guessing an unmodeled command's flags."""
    index = 1
    while index < len(words):
        word = words[index]
        if word == "--":
            break
        source = _unmodeled_body_option_source(word)
        if source is _BodySource.INLINE:
            if word in {"--body", "--comment", "-b", "-c"} and index + 1 >= len(words):
                return UNREADABLE
            return INLINE_BODY
        if source is _BodySource.UNKNOWN:
            return UNREADABLE
        index += 1
    return None


def _api_field_denial(value: str, *, raw: bool) -> str | None:
    """Classify one ``gh api`` field argument when it addresses a body."""
    if "=" not in value:
        return UNREADABLE
    key, field_value = value.split("=", 1)
    if key != "body" and "[body]" not in key and not key.startswith("body["):
        return None
    if not raw and field_value.startswith("@"):
        return None if len(field_value) > 1 else UNREADABLE
    return INLINE_BODY


def _api_field_step(words: Sequence[str], index: int) -> tuple[str | None, int] | None:
    """Inspect a ``gh api`` field option, including its value form."""
    match = _matched_option(words[index], _API_FIELD_OPTIONS)
    if match is None:
        return None
    option, attached, value = match
    if attached:
        if not value:
            return UNREADABLE, index
        next_index = index + 1
    else:
        if index + 1 >= len(words) or (
            words[index + 1].startswith("-") and words[index + 1] != "-"
        ):
            return UNREADABLE, index
        value = words[index + 1]
        next_index = index + 2
    return _api_field_denial(value, raw=option in {"-f", "--raw-field"}), next_index


def _api_input_step(words: Sequence[str], index: int) -> tuple[str | None, int] | None:
    """Inspect the file-backed request-body option of ``gh api``."""
    match = _matched_option(words[index], _API_INPUT_OPTIONS)
    if match is None:
        return None
    if _file_option_incomplete(words, index, match):
        return UNREADABLE, index
    return None, index + (1 if match[1] else 2)


def _api_body_step(words: Sequence[str], index: int) -> tuple[str | None, int] | None:
    """Inspect generic body-shaped options in ``gh api``."""
    source = _unmodeled_body_option_source(words[index])
    if source is None:
        return None
    if source is _BodySource.UNKNOWN:
        return UNREADABLE, index
    if words[index] in {"--body", "--comment", "-b", "-c"} and index + 1 >= len(words):
        return UNREADABLE, index
    return INLINE_BODY, index


def _api_long_step(words: Sequence[str], index: int) -> tuple[str | None, int] | None:
    """Advance over a known non-body long option in ``gh api``."""
    match = _matched_option(words[index], _API_LONG_VALUE_OPTIONS)
    if match is not None:
        if not match[1] and index + 1 >= len(words):
            return UNREADABLE, index
        return None, index + (1 if match[1] else 2)
    if words[index] in _API_LONG_FLAGS:
        return None, index + 1
    return None


def _api_option_step(words: Sequence[str], index: int) -> tuple[str | None, int]:
    """Classify and advance over one ``gh api`` option or argument."""
    for handler in (_api_field_step, _api_input_step, _api_body_step, _api_long_step):
        step = handler(words, index)
        if step is not None:
            return step
    short_step = _known_short_step(words, index, _API_SHORT_VALUE_OPTIONS, _API_SHORT_FLAGS)
    return (None, index + 1) if short_step is None else short_step


def _gh_api_denial(words: Sequence[str]) -> str | None:
    """Inspect ``gh api`` with its command-specific field and input options."""
    index = 1
    while index < len(words) and words[index] != "--":
        reason, next_index = _api_option_step(words, index)
        if reason is not None:
            return reason
        index = next_index
    return None


def _gh_denial(words: Sequence[str]) -> str | None:
    """Inspect one complete ``gh`` argv with command-specific option meanings."""
    path = _command_path(words)
    if path == ("api",):
        return _gh_api_denial(words)
    if path in _NO_BODY_COMMANDS:
        return None
    spec = _BODY_COMMANDS.get(path)
    if spec is not None:
        return _gh_denial_for_spec(words, spec)
    return _gh_denial_for_unmodeled(words)


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
