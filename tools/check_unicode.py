#!/usr/bin/env python3
"""Refuse invisible, direction-controlling, and confusable Unicode (#601).

The check covers every human-gated path and repository Markdown in the candidate
tree. ``docs/reference/arma-wiki/`` is intentionally excluded: it is vendored
third-party content and the live injection channel, so scanning it remains an
open scope decision for the principal rather than an unrecorded implementation
choice.

This gate has no warning or suppression mode. A character that can make an
instruction mean something different from what a human sees must be removed or
explicitly replaced before the tree can pass.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import Final, NamedTuple

sys.path.insert(0, str(Path(__file__).parent))

import gated_paths  # noqa: I001 — sibling import follows standalone-script path setup


# The path is excluded from both the Markdown and gated-path scans. Each entry
# carries the scope decision so the exception cannot become an unexplained
# omission in a later edit.
EXCLUDED_PATHS: Final[dict[str, str]] = {
    "docs/reference/arma-wiki": (
        "vendored third-party pages and the live injection channel; scanning is an open"
        " principal decision (#601)"
    ),
}

# These are intentional confusable-looking characters already used in the
# repository. Every entry has its reason beside it, in the same reviewable shape
# as tools/mutation_smoke.py's named escape lists. A future one must pay the same
# cost rather than silently broadening what the guard accepts.
CONFUSABLE_ALLOWLIST: Final[dict[str, str]] = {
    chr(
        0x00D7
    ): "the process documentation's `validated xN` marker uses the multiplication sign (#186)",
    chr(0x2026): "repository prose uses a visible horizontal ellipsis as punctuation",
    chr(0x03B1): "research prose uses Greek alpha as mathematical notation",
    chr(0x03B2): "research prose uses Greek beta as mathematical notation",
    chr(0x03BA): "research prose uses Greek kappa as mathematical notation",
    chr(0x03BB): "research prose uses Greek lambda as mathematical notation",
    chr(0x03C1): "research prose uses Greek rho as mathematical notation",
    chr(0x03C4): "research prose uses Greek tau as mathematical notation",
    chr(0x03A3): "research prose uses Greek capital sigma as mathematical notation",
    chr(0x00B2): "research prose uses a superscript two in a mathematical expression",
    chr(0x2070): "research prose uses a superscript zero in a mathematical expression",
    chr(0x2074): "research prose uses a superscript four in a mathematical expression",
    chr(0x2075): "research prose uses a superscript five in a mathematical expression",
    chr(0x2076): "research prose uses a superscript six in a mathematical expression",
    chr(0x2080): "research prose uses a subscript zero in a mathematical expression",
    chr(0x2081): "research prose uses a subscript one in a mathematical expression",
    chr(0x2082): "research prose uses a subscript two in a mathematical expression",
    chr(0x2085): "research prose uses a subscript five in a mathematical expression",
    chr(0x2087): "research prose uses a subscript seven in a mathematical expression",
    chr(0x1D62): "research prose uses a subscript i in a mathematical expression",
    chr(0x2095): "research prose uses a subscript h in a mathematical expression",
}

REMEDY: Final = (
    "Remove the character or replace it with visible, approved text; this deny-by-default "
    "check has no bypass"
)

BIDI_CONTROL: Final = "bidi_control"
ZERO_WIDTH: Final = "zero_width"
TAG_CHARACTER: Final = "tag_character"
CONFUSABLE: Final = "confusable"
UNREADABLE: Final = "unreadable"

BIDI_RANGES: Final = ((0x202A, 0x202E), (0x2066, 0x2069))
ZERO_WIDTH_CODEPOINTS: Final = frozenset({*range(0x200B, 0x200E), 0xFEFF, 0x2060})
TAG_RANGE: Final = (0xE0000, 0xE007F)
ASCII_LIMIT: Final = 0x80


class Finding(NamedTuple):
    """One Unicode character that the candidate tree cannot carry."""

    path: str
    line: int
    codepoint: int | None
    name: str
    kind: str

    @property
    def number(self) -> str:
        """Return the Unicode codepoint in the reviewable form the gate prints."""
        if self.codepoint is None:
            return "unknown"
        return f"U+{self.codepoint:04X}"

    def __str__(self) -> str:
        """Render an editor-clickable refusal with its repair."""
        if self.codepoint is None:
            return f"{self.path}:{self.line}: unicode={self.name} kind={self.kind}. {REMEDY}"
        return (
            f"{self.path}:{self.line}: unicode={self.number} {self.name} kind={self.kind}. {REMEDY}"
        )


def _listed_kind(character: str) -> str | None:
    """Return the listed control class for `character`, if it has one."""
    codepoint = ord(character)
    if any(start <= codepoint <= end for start, end in BIDI_RANGES):
        return BIDI_CONTROL
    if codepoint in ZERO_WIDTH_CODEPOINTS:
        return ZERO_WIDTH
    if TAG_RANGE[0] <= codepoint <= TAG_RANGE[1]:
        return TAG_CHARACTER
    return None


def _is_nfkc_confusable(character: str) -> bool:
    """Whether normalization turns a non-ASCII character into ASCII text."""
    normalized = unicodedata.normalize("NFKC", character)
    return (
        normalized != character
        and bool(normalized)
        and all(ord(item) < ASCII_LIMIT for item in normalized)
    )


def _is_script_confusable(character: str) -> bool:
    """Whether a non-ASCII Greek or Cyrillic letter needs explicit review."""
    name = unicodedata.name(character, "")
    return name.startswith(("GREEK ", "CYRILLIC "))


def _kind(character: str) -> str | None:
    """Classify one character, with listed controls outranking any allowlist."""
    listed = _listed_kind(character)
    if listed is not None:
        return listed
    if character in CONFUSABLE_ALLOWLIST:
        return None
    if _is_nfkc_confusable(character) or _is_script_confusable(character):
        return CONFUSABLE
    return None


def scan_source(source: str, path: str) -> list[Finding]:
    """Report every refused character in one decoded file."""
    findings: list[Finding] = []
    for line, text in enumerate(source.splitlines(), start=1):
        for character in text:
            kind = _kind(character)
            if kind is None:
                continue
            findings.append(
                Finding(
                    path=path,
                    line=line,
                    codepoint=ord(character),
                    name=unicodedata.name(character, "UNKNOWN UNICODE CHARACTER"),
                    kind=kind,
                )
            )
    return findings


def _excluded(path: str) -> bool:
    """Whether a repository-relative path lies under an explicit exclusion."""
    return any(path == root or path.startswith(f"{root}/") for root in EXCLUDED_PATHS)


def _filesystem_candidates(root: Path) -> list[str]:
    """Find files for a fixture tree that has no Git repository."""
    found: list[str] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if ".git" in path.relative_to(root).parts or _excluded(relative):
            continue
        if path.is_file() or path.is_symlink():
            found.append(relative)
    return sorted(found)


def candidates(root: Path) -> list[str]:
    """Return candidate files: gated paths and Markdown, including untracked files."""
    command = ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--"]
    completed = subprocess.run(  # noqa: S603 — fixed Git argv, no shell or caller input
        command,
        cwd=root,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        return _filesystem_candidates(root)

    found: list[str] = []
    for raw in completed.stdout.split(b"\0"):
        if not raw:
            continue
        relative = raw.decode("utf-8")
        if _excluded(relative):
            continue
        if relative.casefold().endswith(".md") or any(
            gate.matches(relative) for gate in gated_paths.PATH_GATES
        ):
            found.append(relative)
    return sorted(set(found))


def _read(path: Path) -> str | None:
    """Read UTF-8 text, returning none when the file cannot be decoded or opened."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


def find_in_tree(root: Path) -> list[Finding]:
    """Report every refused character in the candidate tree."""
    findings: list[Finding] = []
    for relative in candidates(root):
        text = _read(root / relative)
        if text is None:
            findings.append(
                Finding(
                    path=relative,
                    line=1,
                    codepoint=None,
                    name="UNREADABLE UTF-8",
                    kind=UNREADABLE,
                )
            )
            continue
        findings.extend(scan_source(text, relative))
    return findings


def scan_tree(root: Path) -> list[Finding]:
    """Public name for the tree scan used by the unit seam and the CLI."""
    return find_in_tree(root)


def main(argv: list[str] | None = None) -> int:
    """Check the candidate tree and print one line per refusal."""
    parser = argparse.ArgumentParser(
        description="Refuse invisible and confusable Unicode in agent files."
    )
    parser.add_argument("root", nargs="?", default=".", type=Path)
    args = parser.parse_args(argv)

    findings = find_in_tree(args.root.resolve())
    for finding in findings:
        print(finding, file=sys.stderr)  # noqa: T201 — stderr is this gate's output
    if findings:
        files = len({finding.path for finding in findings})
        print(f"unicode=refused files={files} findings={len(findings)}", file=sys.stderr)  # noqa: T201
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
