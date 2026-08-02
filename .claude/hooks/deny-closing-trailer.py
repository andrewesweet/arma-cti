#!/usr/bin/env python3
"""commit-msg hook: deny a commit message that would auto-close a GitHub issue.

`docs/agents/issue-tracker.md` has banned closing keywords on issues carrying
acceptance criteria since #89 was auto-closed with two boxes unticked. #24
repeated it, and #127's landing repeated it again — three self-corrected
instances against a written rule, which is the document-vs-mechanism shape
ADR-0038 named. This is the mechanism.

Not a Claude Code hook despite living beside them: `cog.toml` installs a
commit-msg script that calls this one, so it fires for every commit by every
committer and on every path a message can arrive by (`-m`, `-F`, an editor,
`--amend`), with no shell quoting to undo first. A PreToolUse Bash hook would
have to dig the message back out of arbitrary shell, which is the parsing job
that produced #120's four false denials. Per ADR-0042 the installed script
resolves this file from the *committing worktree*, so a session enforces its own
copy and picks up changes on rebase.

What is matched is exactly what GitHub acts on, per its documented keyword list
(docs.github.com, "Linking a pull request to an issue"): `close`, `closes`,
`closed`, `fix`, `fixes`, `fixed`, `resolve`, `resolves`, `resolved`, each
optionally followed by a colon and case-insensitive, then a reference — `#N`,
`GH-N`, `owner/repo#N`, or a github.com issue/pull URL. The same page says a
commit message's keyword closes the issue when the commit reaches the default
branch, which is exactly how this repo lands work.

That exactness sets the false-positive rule: GitHub matches the keyword
*anywhere* in the message, not only in a trailer, so there is no innocent prose
spelling of the thing. `Fixes #129` in the middle of a body paragraph really
does close #129, so it is denied too. Prose about the rule stays writable
because the keyword only counts when a reference follows it directly: "the
`fixes`/`closes` keywords" and "fixes the flake #129 reported" both pass.

Two deliberate edges:

* `fix: #129 stop the thing` is denied. It reads as a Conventional Commits type,
  but `Fixes: #10` is GitHub's documented colon form, so that subject would
  close #129. Spell the subject in words instead.
* Comment lines and anything past the scissors line are dropped first, because
  git strips them after this hook runs and GitHub therefore never sees them.
  `git commit -v` puts the diff below the scissors, and in this repo that diff
  contains these very test strings. The knowing cost is a message passed by `-m`
  whose keyword or reference sits in column one behind a `#` — git keeps that
  line where an editor-composed message would have lost it, so GitHub would
  honour a close this hook never saw.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# GitHub's documented keyword list, with the colon form (`Closes: #10`).
_KEYWORD = r"clos(?:e|es|ed)|fix(?:es|ed)?|resolv(?:e|es|ed)"
# The reference forms a keyword can close through.
_REFERENCE = (
    r"#\d+"
    r"|GH-\d+"
    r"|[\w.-]+/[\w.-]+#\d+"
    r"|https?://(?:www\.)?github\.com/[\w.-]+/[\w.-]+/(?:issues|pull)/\d+"
)
# `(?<![\w-])` keeps the keyword a word of its own, so "prefixes #12" and
# "hotfix-#12" are not closes. One line break may sit between the two halves;
# a blank line may not, which is where a trailer stops and a new paragraph
# starts.
CLOSING = re.compile(
    rf"(?<![\w-])(?:{_KEYWORD})[ \t]*:?[ \t]*(?:\r?\n[ \t]*)?(?:{_REFERENCE})",
    re.IGNORECASE,
)
_SCISSORS = re.compile(r"^#\s*-+\s*>8\s*-+", re.MULTILINE)

DENIAL = (
    "This commit message would auto-close a GitHub issue: {found!r}.\n"
    "Closing keywords are banned here — they close the issue on push and skip the"
    " criterion-by-criterion audit (docs/agents/issue-tracker.md, 'Closing an issue"
    " that carries acceptance criteria'; #89, #24, #127).\n"
    "Reference the issue without a keyword — `(#N)` or `refs #N` — and close it by"
    " hand with `gh issue close N --comment ...`."
)


def commit_text(message: str) -> str:
    """Return the part of `message` that will survive git's cleanup into the commit.

    Everything from a scissors line on is dropped, then comment lines. That is
    what GitHub is given, so it is what the keyword search is run against.
    """
    cut = _SCISSORS.search(message)
    if cut is not None:
        message = message[: cut.start()]
    return "\n".join(line for line in message.split("\n") if not line.startswith("#"))


def closing_reference(message: str) -> str | None:
    """Return the closing keyword and reference this message carries, if any."""
    found = CLOSING.search(commit_text(message))
    return None if found is None else " ".join(found.group().split())


def main() -> int:
    """Read the commit message file named on the command line and deny a close."""
    try:
        message = Path(sys.argv[1]).read_text(encoding="utf-8")
    except (IndexError, OSError) as error:
        # Fail closed, as the Bash hook learned to in #94: a message that cannot
        # be read has not been checked, and an unchecked message is not a pass.
        print(f"Could not read the commit message to check it: {error}", file=sys.stderr)
        return 1
    found = closing_reference(message)
    if found is None:
        return 0
    print(DENIAL.format(found=found), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
