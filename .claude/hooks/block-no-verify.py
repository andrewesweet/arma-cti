#!/usr/bin/env python3
"""PreToolUse hook (Bash): deny commit-hook bypass flags.

They would skip the cog commit-msg hook that enforces Conventional Commits.

The flag only counts as a bypass when it is an *argument to a git commit being
run*. Substring matching could not tell that from prose, and denied agents for
writing about the rule: a heredoc whose text quoted the phrase, and `gh issue
comment --body "..."` bodies naming the flag (#120). So the command is read
structurally instead — prose is removed (heredoc bodies, shell comments), what
is left is tokenised, split on command separators, and only a segment whose
command word is `git` with a `commit` subcommand and a bypass flag is denied.

Where the line is drawn, deliberately, because a hook too clever to audit is
worse than a blunt one:

* Uncertainty blocks. Unbalanced quotes and an unterminated heredoc mean the
  text could not be read, so the answer is deny.
* No option-value tracking. `git commit -m -n` is denied even though `-n` is
  there the commit message. Over-blocking is the safe direction.
* No modelling of backticks or `eval`. `` `git commit --no-verify` `` is not
  detected. Backticked flag names are ordinary prose in the bodies this hook
  must stop denying, and treating them as command positions would reintroduce
  the false positives wholesale. `$(...)` is covered incidentally: shlex reads
  the parentheses as separators, so the substitution becomes its own segment.
"""

from __future__ import annotations

import json
import re
import shlex
import sys
from pathlib import PurePosixPath

# `-n` is git commit's short spelling of --no-verify, and it clusters: `-an` is
# --all --no-verify.
_SHORT_BYPASS = re.compile(r"-[A-Za-z]*n[A-Za-z]*\Z")
# A leading `VAR=value` environment assignment, which precedes the command word.
_ASSIGNMENT = re.compile(r"[A-Za-z_]\w*=")
# A heredoc delimiter, quoted or bare, after `<<` or `<<-`.
_DELIMITER = re.compile(r"-?\s*(?:'([^']*)'|\"([^\"]*)\"|([A-Za-z_][\w.-]*))")
# `;`, `&&`, `||`, `|`, `&`, `(`, `)` — shlex.punctuation_chars emits these as
# their own tokens, and each of them ends a command.
_SEPARATORS = frozenset({";", "&", "&&", "|", "||", "|&", "(", ")", ";;"})

DENIAL = (
    "Bypassing the commit-msg hook is blocked: it defeats the Conventional"
    " Commits gate (ADR-0010). Fix the commit message instead."
)


def _read_line(line: str, quote: str) -> tuple[str, str, list[str], bool] | None:
    """Read one line of shell text outside of any heredoc body.

    Returns the code with an unquoted trailing comment removed, the quote still
    open at the end of it, the heredoc delimiters the line opened, and whether
    it ends in a backslash continuation. `None` if the line could not be read.
    """
    kept: list[str] = []
    delimiters: list[str] = []
    index = 0
    while index < len(line):
        char = line[index]
        if quote == '"' and char == "\\" and index + 1 < len(line):
            kept.append(line[index : index + 2])  # an escaped quote does not close it
            index += 2
        elif quote:
            kept.append(char)
            quote = "" if char == quote else quote
            index += 1
        elif char in "'\"":
            quote = char
            kept.append(char)
            index += 1
        elif char == "\\" and index + 1 < len(line):
            kept.append(line[index : index + 2])
            index += 2
        elif char == "#" and (index == 0 or line[index - 1].isspace()):
            break  # a comment runs to the end of the line
        elif line.startswith("<<", index) and not line.startswith("<<<", index):
            match = _DELIMITER.match(line, index + 2)
            if match is None:
                return None  # a heredoc we cannot name the end of
            delimiters.append(next(group for group in match.groups() if group is not None))
            kept.append(line[index : match.end()])
            index = match.end()
        else:
            kept.append(char)
            index += 1
    code = "".join(kept)
    return code, quote, delimiters, not quote and code.endswith("\\")


def _shell_code(command: str) -> str | None:
    """Return `command` with its prose removed, or `None` if it cannot be read.

    Heredoc bodies and comments are dropped. An unquoted line ending becomes an
    explicit `;`, because the tokeniser treats a newline as plain whitespace and
    would otherwise run two commands together into one.
    """
    pieces: list[str] = []
    quote = ""
    pending: list[str] = []
    for line in command.split("\n"):
        if pending:
            if line.strip() == pending[0]:
                pending.pop(0)
            continue  # heredoc body: text, not commands
        read = _read_line(line, quote)
        if read is None:
            return None
        code, quote, delimiters, continued = read
        pending.extend(delimiters)
        pieces.append(code)
        if quote or continued:
            pieces.append("\n")  # inside a string, or a wrapped command line
        else:
            pieces.append(" ; ")
    if quote or pending:
        return None  # unbalanced quote, or a heredoc that never ends
    return "".join(pieces)


def _segments(code: str) -> list[list[str]] | None:
    """Split shell code into one token list per command, or `None` if unreadable."""
    lexer = shlex.shlex(code, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""  # comments were removed already, quote-aware
    try:
        tokens = list(lexer)
    except ValueError:
        return None
    commands: list[list[str]] = [[]]
    for token in tokens:
        if token in _SEPARATORS:
            commands.append([])
        else:
            commands[-1].append(token)
    return commands


def _is_bypass_flag(word: str) -> bool:
    return (
        word == "--no-verify"
        or word.startswith("--no-verify=")
        or bool(_SHORT_BYPASS.fullmatch(word))
    )


def _runs_a_bypass(tokens: list[str]) -> bool:
    """Report whether this one command is a `git commit` skipping the commit-msg hook."""
    while tokens and _ASSIGNMENT.match(tokens[0]):
        tokens = tokens[1:]  # leading VAR=value environment assignments
    if not tokens or PurePosixPath(tokens[0]).name != "git":
        return False
    arguments = tokens[1:]
    return "commit" in arguments and any(_is_bypass_flag(token) for token in arguments)


def blocks(command: str) -> bool:
    """Report whether this Bash command must be denied. Anything unreadable is."""
    code = _shell_code(command)
    if code is None:
        return True
    segments = _segments(code)
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
