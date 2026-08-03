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
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import PurePosixPath

from shell_reading import read_command, without_assignments

# `-n` is git commit's short spelling of --no-verify, and it clusters: `-an` is
# --all --no-verify.
_SHORT_BYPASS = re.compile(r"-[A-Za-z]*n[A-Za-z]*\Z")

DENIAL = (
    "Bypassing the commit-msg hook is blocked: it defeats the Conventional"
    " Commits gate (ADR-0010). Fix the commit message instead."
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


def blocks(command: str) -> bool:
    """Report whether this Bash command must be denied. Anything unreadable is."""
    segments = read_command(command)
    if segments is None:
        return True
    return any(_runs_a_bypass(tokens) for tokens in segments)


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
    if blocks(command):
        print(DENIAL, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
