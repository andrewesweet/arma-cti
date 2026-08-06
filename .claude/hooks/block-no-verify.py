#!/usr/bin/env python3
"""PreToolUse hook (Bash): deny commit-hook bypass flags.

They would skip the cog commit-msg hook that enforces Conventional Commits.

The flag only counts as a bypass when it is an *argument to a git commit being
run*, never prose about one, so the command is read structurally with the
shared reader in `shell_reading.py` (its docstring carries the #120/#167
history and the deliberate limits) and only a segment whose command word is
`git` with a `commit` subcommand and a bypass flag is denied.

One limit of its own, on top of the reader's: no option-value tracking.
`git commit -m -n` is denied even though `-n` is there the commit message.
Over-blocking is the safe direction.

Two denials, because there are two findings and for a week one was read as the
other. A *bypass* is a `git commit` that was going to run with the flag. An
*unreadable* command is one the reader could not classify at all; it is denied
just as hard — a command that cannot be read cannot be cleared — but it is not
an accusation, and its remedy is to move the text out of argv rather than to
edit a commit message. #254 was filed because the unreadable denial wore the
bypass wording: three commands denied by a stale worktree copy of the pre-#167
reader (ADR-0042) were reported as false positives of the flag pattern, which
had matched nothing in any of them.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import PurePosixPath

from shell_reading import read_command, without_assignments

# The short options `git commit` takes, as letters. `-n` is its spelling of
# --no-verify and it clusters, so `-an` is --all --no-verify — but a cluster is
# one only when every letter in it is an option git commit has. Over any letter
# (`-[A-Za-z]*n[A-Za-z]*`) the pattern also matched `-anchored` and `-agent`,
# ordinary English words that begin with a hyphen (#254). Nothing real is lost
# by narrowing it: a cluster carrying a letter git commit does not take is a
# command git itself rejects, so it was never a bypass that could run.
_SHORT_OPTIONS = "aCcFeimnopqSstuv"
_SHORT_BYPASS = re.compile(rf"-[{_SHORT_OPTIONS}]*n[{_SHORT_OPTIONS}]*\Z")

BYPASS_DENIAL = (
    "Bypassing the commit-msg hook is blocked: it defeats the Conventional"
    " Commits gate (ADR-0010). Fix the commit message instead."
)

# Says what happened, and what to do about it. No accusation: the reader found
# nothing, which is exactly why it is denying (#254).
UNREADABLE_DENIAL = (
    "This command could not be read, so it could not be checked, and an"
    " unchecked command is not a cleared one. The reader could not tell its"
    " command positions from its text — unbalanced quoting, or a heredoc with no"
    " end marker, both easy to write inside a long body. No commit-hook bypass"
    " was found in it; nothing here is an accusation of one. Take the body out"
    " of the command line and pass it as a file instead: write the file, then"
    " `gh ... --body-file <path>` or `git commit -F <path>`."
)


def _is_bypass_flag(word: str) -> bool:
    return (
        word == "--no-verify"
        or word.startswith("--no-verify=")
        or bool(_SHORT_BYPASS.fullmatch(word))
    )


def _runs_a_bypass(tokens: list[str]) -> bool:
    """Report whether this one command is a `git commit` skipping the commit-msg hook."""
    tokens = without_assignments(tokens)
    if not tokens or PurePosixPath(tokens[0]).name != "git":
        return False
    arguments = tokens[1:]
    return "commit" in arguments and any(_is_bypass_flag(token) for token in arguments)


def denial(command: str) -> str | None:
    """Return the message to deny this Bash command with, or `None` to let it run."""
    segments = read_command(command)
    if segments is None:
        return UNREADABLE_DENIAL
    if any(_runs_a_bypass(tokens) for tokens in segments):
        return BYPASS_DENIAL
    return None


def blocks(command: str) -> bool:
    """Report whether this Bash command must be denied. Anything unreadable is."""
    return denial(command) is not None


def main() -> int:
    """Read the tool call on stdin and deny a commit-hook bypass."""
    try:
        data = json.load(sys.stdin)
        command = data["tool_input"]["command"]
    except (json.JSONDecodeError, TypeError, KeyError):
        # #94: the hook used to fail open here, and PreToolUse reads any exit
        # other than 2 as approval. A call we cannot read is not an approval.
        print(
            "Could not read the Bash tool call to check it for a commit-hook bypass.",
            file=sys.stderr,
        )
        return 2
    message = denial(command)
    if message is not None:
        print(message, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
