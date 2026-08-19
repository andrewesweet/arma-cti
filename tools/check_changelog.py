"""Require a branch-owned changelog fragment for tracked source changes (#358)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Final, NamedTuple

sys.path.insert(0, str(Path(__file__).parent))

from worktree import git

BASE: Final = "origin/main"
MARKER: Final = "<!-- scriv-insert-here -->"
STATUS_PATH_AT: Final = 3
NON_SOURCE_ROOTS: Final = frozenset({".claude", ".github", "changelog.d", "docs", "tests"})
NON_SOURCE_FILES: Final = frozenset(
    {".dispatch-commit-message", "AGENTS.md", "CHANGELOG.md", "CLAUDE.md", "LICENSE", "README.md"}
)


class Finding(NamedTuple):
    """One unmet changelog-fragment requirement."""

    detail: str
    remedy: str

    def __str__(self) -> str:
        """Render one editor-facing line."""
        return f"changelog: {self.detail}. {self.remedy}"


def _changed_paths(root: Path) -> set[str]:
    committed = git("diff", "--name-only", f"{BASE}...HEAD", cwd=root).splitlines()
    working = git("status", "--porcelain", "--untracked-files=all", cwd=root).splitlines()
    return {path for path in committed if path} | {
        line[STATUS_PATH_AT:] for line in working if len(line) > STATUS_PATH_AT
    }


def _is_source(path: str) -> bool:
    first = path.split("/", 1)[0]
    return path not in NON_SOURCE_FILES and first not in NON_SOURCE_ROOTS


def scan(root: Path) -> list[Finding]:
    """Return every failure; inability to derive the remote baseline fails closed."""
    if not git("rev-parse", "--verify", BASE, cwd=root, check=False).strip():
        return [
            Finding(
                f"no `{BASE}` ref to diff against",
                "fetch and re-run; an unchecked branch is not a passing branch",
            )
        ]

    findings: list[Finding] = []
    changelog = root / "CHANGELOG.md"
    if not changelog.is_file() or MARKER not in changelog.read_text(encoding="utf-8"):
        findings.append(
            Finding(
                f"`CHANGELOG.md` lacks `{MARKER}`",
                "restore Scriv's release insertion marker",
            )
        )

    paths = _changed_paths(root)
    sources = sorted(path for path in paths if _is_source(path))
    fragments = sorted(
        path
        for path in paths
        if path.startswith("changelog.d/") and path.endswith(".md") and (root / path).is_file()
    )
    if sources and not fragments:
        findings.append(
            Finding(
                f"source changes and no branch-owned fragment; source={','.join(sources)}",
                "add `changelog.d/<issue>-<slug>.md` with an Added, Changed, Deprecated, "
                "Removed, Fixed, or Security section",
            )
        )
    return findings


def main(argv: list[str] | None = None) -> int:
    """Print findings and return non-zero when the branch owes a fragment."""
    parser = argparse.ArgumentParser(prog="check-changelog", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    findings = scan(parser.parse_args(argv).root.resolve())
    for finding in findings:
        print(finding, file=sys.stderr)  # noqa: T201
    if not findings:
        print("changelog=ok")  # noqa: T201
    return bool(findings)


if __name__ == "__main__":
    raise SystemExit(main())
