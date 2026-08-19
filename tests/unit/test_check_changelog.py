"""The source-to-fragment check and Scriv release configuration (#358)."""

from __future__ import annotations

import subprocess
import sys
from typing import TYPE_CHECKING

from conftest import REPO, load_tool

if TYPE_CHECKING:
    from pathlib import Path

check_changelog = load_tool("check_changelog")


def _git(root: Path, *args: str) -> str:
    done = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return done.stdout


def _repo(root: Path) -> None:
    root.mkdir()
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n<!-- scriv-insert-here -->\n", encoding="utf-8"
    )
    _git(root, "add", "CHANGELOG.md")
    _git(root, "commit", "-m", "chore: seed")
    _git(root, "update-ref", "refs/remotes/origin/main", "HEAD")


def test_source_changes_need_a_live_fragment(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _repo(root)
    (root / "tools").mkdir()
    (root / "tools" / "feature.py").write_text("value = 1\n", encoding="utf-8")

    findings = check_changelog.scan(root)
    assert any("no branch-owned fragment" in finding.detail for finding in findings)

    fragment = root / "changelog.d" / "358-feature.md"
    fragment.parent.mkdir()
    fragment.write_text("### Added\n\n- Feature.\n", encoding="utf-8")
    assert check_changelog.scan(root) == []

    fragment.unlink()
    assert any("no branch-owned fragment" in f.detail for f in check_changelog.scan(root))

    (root / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    assert any("scriv-insert-here" in f.detail for f in check_changelog.scan(root))


def test_scriv_collects_in_filename_and_category_order_then_deletes_fragments(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        (REPO / "pyproject.toml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n<!-- scriv-insert-here -->\n", encoding="utf-8"
    )
    fragments = tmp_path / "changelog.d"
    fragments.mkdir()
    (fragments / "002.md").write_text("### Fixed\n\n- second\n", encoding="utf-8")
    (fragments / "001.md").write_text(
        "### Added\n\n- added\n\n### Fixed\n\n- first\n", encoding="utf-8"
    )

    subprocess.run(
        [
            sys.executable,
            "-m",
            "scriv",
            "collect",
            "--version",
            "0.2.0",
        ],
        cwd=tmp_path,
        check=True,
    )

    text = (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8")
    assert text.index("### Added") < text.index("### Fixed")
    assert text.index("- first") < text.index("- second")
    assert "## [0.2.0] - " in text
    assert list(fragments.iterdir()) == []
