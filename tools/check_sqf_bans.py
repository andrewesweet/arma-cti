"""Scoped bans for SQF commands and shapes that must go through an adapter.

HEMTT's `banned_commands` lint is all-or-nothing: a command is banned
everywhere or nowhere, and HEMTT 1.20.1 has no file- or line-scoped
suppression (`#pragma hemtt suppress` covers preprocessor codes only). The
project contract needs the other shape — `random` banned everywhere *except*
the one adapter that wraps it, and the same for `sleep` once a CBA scheduler
adapter exists — so that scoping lives here.

HEMTT still bans `sleep` and `uiSleep` outright; this gate re-bans `random` and
allows it in the seeded PRNG adapter alone, and bans `setGroupOwner` everywhere
but the one diagnostic that predates the rule (ADR-0039).

The second rule is a shape rather than a command: a hand-rolled locality guard,
`if (!isServer) exitWith { ... }` or the same with `hasInterface`. ADR-0040 puts
those behind the `SERVER_ONLY` / `INTERFACE_ONLY` macros in
`addons/main/script_component.hpp`, because the macro is what supplies the typed
FAIL line a bare guard cannot — a sentinel returned in silence is #112 and #113
all over again. Only the guard shape is banned: asking `isServer` to *branch*
(`if (!isServer) then { ... }`, as the spike mission does to find the headless
client) is a role question and not a refusal, and stays legal.

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


class Ban(NamedTuple):
    """One banned command: who may use it, and what everyone else does instead."""

    allowed: frozenset[str]
    remedy: str


# Banned command -> its ban. A file earns a place on an `allowed` set by being
# the adapter that makes the command safe, or by being the one place a project
# rule exempts, and in either case by carrying an inline comment saying so.
SCOPED_BANS: Final[dict[str, Ban]] = {
    "random": Ban(
        frozenset({"addons/main/functions/fn_prngNext.sqf"}),
        "Draw through the adapter instead.",
    ),
    "setGroupOwner": Ban(
        frozenset({"addons/main/functions/fn_desyncLoad.sqf"}),
        "Squads are never transferred off the server (ADR-0039).",
    ),
}

# The hand-rolled locality guard ADR-0040 replaced. `exitWith` is what makes it a
# guard rather than a role question: the shape refuses on the caller's behalf and
# returns a sentinel, which is the thing that has to carry a log line with it.
# Both spellings the addon has ever used are matched — `if (!isServer)` and
# `if !(isServer)` — because they compile the same and read the same.
GUARD_PATTERN: Final = re.compile(
    r"\bif\s*(?:\(\s*!\s*|!\s*\(\s*)(isServer|hasInterface)\s*\)\s*exitWith\b",
    re.IGNORECASE,
)

# The macros the guard shape has to go through, in the file that defines them.
GUARD_MACROS: Final = "SERVER_ONLY / INTERFACE_ONLY (addons/main/script_component.hpp)"

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
        ban = SCOPED_BANS[self.command]
        allowed = ", ".join(sorted(ban.allowed)) or "nothing"
        return (
            f"{self.path}:{self.line}: `{self.command}` is banned outside {allowed}. {ban.remedy}"
        )


class GuardFinding(NamedTuple):
    """One hand-rolled locality guard, which belongs behind a macro."""

    path: str
    line: int
    command: str

    def __str__(self) -> str:
        """Render as an editor-clickable location."""
        return (
            f"{self.path}:{self.line}: a bare `{self.command}` guard returns its "
            f"sentinel in silence. Use {GUARD_MACROS}, or delete the guard and say "
            f"in the header why the call site already decides the machine."
        )


def _blanked(text: str) -> str:
    """Return `text` as spaces, keeping its newlines so line numbers survive."""
    return "".join(character if character == "\n" else " " for character in text)


def _end_of_line_comment(source: str, index: int) -> int:
    """Return where a `//` comment starting at `index` ends."""
    end = source.find("\n", index)
    return len(source) if end == -1 else end


def _end_of_block_comment(source: str, index: int) -> int:
    """Return where a `/*` comment starting at `index` ends, `*/` included."""
    end = source.find("*/", index + 2)
    return len(source) if end == -1 else end + 2


def _end_of_string(source: str, index: int) -> int:
    """Return where the string literal opening at `index` ends.

    SQF escapes a quote by doubling it, so a closing quote followed by the same
    quote is an escape and the literal continues.
    """
    quote = source[index]
    end = index + 1
    while end < len(source):
        if source[end] == quote:
            if source[end + 1 : end + 2] == quote:
                end += 2
                continue
            return end + 1
        end += 1
    return end


def strip_noncode(source: str) -> str:
    """Blank out comments and string literals, preserving line numbering.

    Everything removed is replaced by spaces (newlines kept), so a match's line
    number in the result is its line number in the original. The three things
    that get blanked each know where they end; this only says which one started.
    """
    out: list[str] = []
    index = 0
    while index < len(source):
        pair = source[index : index + 2]
        if pair == "//":
            end = _end_of_line_comment(source, index)
        elif pair == "/*":
            end = _end_of_block_comment(source, index)
        elif source[index] in {'"', "'"}:
            end = _end_of_string(source, index)
        else:
            out.append(source[index])
            index += 1
            continue
        out.append(_blanked(source[index:end]))
        index = end
    return "".join(out)


def scan_source(source: str, path: str) -> list[Finding | GuardFinding]:
    """Report everything in `source` that `path` is not allowed to contain."""
    code = strip_noncode(source)
    findings: list[Finding | GuardFinding] = []
    for command, ban in SCOPED_BANS.items():
        if path in ban.allowed:
            continue
        findings.extend(
            Finding(path, code.count("\n", 0, match.start()) + 1, command)
            for match in re.finditer(rf"\b{re.escape(command)}\b", code, re.IGNORECASE)
        )
    findings.extend(
        GuardFinding(path, code.count("\n", 0, match.start()) + 1, match.group(1))
        for match in GUARD_PATTERN.finditer(code)
    )
    return sorted(findings, key=lambda f: (f.path, f.line))


def sqf_files(root: Path) -> list[Path]:
    """Every SQF file in the repository that we author."""
    return sorted(
        path
        for path in root.rglob("*.sqf")
        if not (EXCLUDED_DIRS & set(path.relative_to(root).parts))
    )


def scan_tree(root: Path) -> list[Finding | GuardFinding]:
    """Report every scoped-ban violation under `root`."""
    findings: list[Finding | GuardFinding] = []
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
