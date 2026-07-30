"""Scoped bans for SQF commands that must go through an adapter.

HEMTT's `banned_commands` lint is all-or-nothing: a command is banned
everywhere or nowhere, and HEMTT 1.20.1 has no file- or line-scoped
suppression (`#pragma hemtt suppress` covers preprocessor codes only). The
project contract needs the other shape — `random` banned everywhere *except*
the one adapter that wraps it, and the same for `sleep` once a CBA scheduler
adapter exists — so that scoping lives here.

HEMTT still bans `sleep` and `uiSleep` outright; this gate re-bans `random` and
allows it in the seeded PRNG adapter alone.

Comments and string literals are stripped before matching, so prose that
mentions a banned command (this file's own doc comments included) is not a
finding. Matching is case-insensitive because SQF is.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Final, NamedTuple

# Banned command -> the repo-relative files allowed to use it. A file earns a
# place here by being the adapter that makes the command safe, and by carrying
# an inline comment saying so.
SCOPED_BANS: Final[dict[str, frozenset[str]]] = {
    "random": frozenset({"addons/main/functions/fn_prngNext.sqf"}),
}

# Directories that are not our SQF: the vendored wiki quotes engine samples,
# build output is a copy of what we already checked, and .claude holds nested
# agent worktrees — whole checkouts whose files only match the allowlist with
# the worktree prefix stripped, and which run this gate on their own trees.
EXCLUDED_DIRS: Final = frozenset(
    {".git", ".venv", ".hemttout", ".spike-out", ".claude", "docs", "target"}
)


class Finding(NamedTuple):
    """One banned command used outside its allowed files."""

    path: str
    line: int
    command: str

    def __str__(self) -> str:
        """Render as an editor-clickable location."""
        allowed = ", ".join(sorted(SCOPED_BANS[self.command])) or "nothing"
        return (
            f"{self.path}:{self.line}: `{self.command}` is banned outside {allowed}. "
            f"Draw through the adapter instead."
        )


def strip_noncode(source: str) -> str:
    """Blank out comments and string literals, preserving line numbering.

    Everything removed is replaced by spaces (newlines kept), so a match's line
    number in the result is its line number in the original.
    """
    out: list[str] = []
    index = 0
    length = len(source)
    while index < length:
        char = source[index]
        pair = source[index : index + 2]
        if pair == "//":
            end = source.find("\n", index)
            end = length if end == -1 else end
            out.append(" " * (end - index))
            index = end
        elif pair == "/*":
            end = source.find("*/", index + 2)
            end = length if end == -1 else end + 2
            out.append("".join(c if c == "\n" else " " for c in source[index:end]))
            index = end
        elif char in {'"', "'"}:
            # SQF escapes a quote by doubling it, so a closing quote followed by
            # the same quote is an escape and the literal continues.
            end = index + 1
            while end < length:
                if source[end] == char:
                    if source[end + 1 : end + 2] == char:
                        end += 2
                        continue
                    end += 1
                    break
                end += 1
            out.append("".join(c if c == "\n" else " " for c in source[index:end]))
            index = end
        else:
            out.append(char)
            index += 1
    return "".join(out)


def scan_source(source: str, path: str) -> list[Finding]:
    """Report every banned command used in `source` that `path` may not use."""
    code = strip_noncode(source)
    findings: list[Finding] = []
    for command, allowed in SCOPED_BANS.items():
        if path in allowed:
            continue
        findings.extend(
            Finding(path, code.count("\n", 0, match.start()) + 1, command)
            for match in re.finditer(rf"\b{re.escape(command)}\b", code, re.IGNORECASE)
        )
    return sorted(findings, key=lambda f: (f.path, f.line))


def sqf_files(root: Path) -> list[Path]:
    """Every SQF file in the repository that we author."""
    return sorted(
        path
        for path in root.rglob("*.sqf")
        if not (EXCLUDED_DIRS & set(path.relative_to(root).parts))
    )


def scan_tree(root: Path) -> list[Finding]:
    """Report every scoped-ban violation under `root`."""
    findings: list[Finding] = []
    for path in sqf_files(root):
        relative = path.relative_to(root).as_posix()
        findings.extend(scan_source(path.read_text(encoding="utf-8"), relative))
    return findings


def main(argv: list[str] | None = None) -> int:
    """Check the tree and print one line per finding."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".", type=Path)
    args = parser.parse_args(argv)

    findings = scan_tree(args.root.resolve())
    for finding in findings:
        print(finding, file=sys.stderr)  # noqa: T201
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
