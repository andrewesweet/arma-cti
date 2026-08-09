"""The source-link check refuses every way the arrangement can be undone (#264)."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest
from conftest import load_tool

if TYPE_CHECKING:
    from pathlib import Path

check = load_tool("check_source_symlink")


def git(root: Path, *args: str) -> None:
    """Run one git command in `root`; resolved off PATH as the sibling tests do."""
    subprocess.run(["git", *args], cwd=root, check=True)  # noqa: S603, S607


def repo(tmp_path: Path) -> Path:
    """Build a repository holding the landed arrangement: AGENTS.md and a symlink."""
    git(tmp_path, "init", "-q")
    (tmp_path / "AGENTS.md").write_text("# arma-cti\n")
    (tmp_path / "CLAUDE.md").symlink_to("AGENTS.md")
    git(tmp_path, "add", "AGENTS.md", "CLAUDE.md")
    return tmp_path


def test_the_landed_arrangement_passes(tmp_path: Path) -> None:
    assert check.failures(repo(tmp_path)) == []


def test_a_regular_file_in_the_index_fails_even_when_the_disk_looks_right(
    tmp_path: Path,
) -> None:
    """The index is the authority: a checkout can lack symlinks and still be correct."""
    root = repo(tmp_path)
    git(root, "rm", "--cached", "-q", "CLAUDE.md")
    found = check.failures(root)
    assert any("not 120000" in line for line in found), found


def test_a_copy_replacing_the_link_on_disk_fails(tmp_path: Path) -> None:
    root = repo(tmp_path)
    (root / "CLAUDE.md").unlink()
    (root / "CLAUDE.md").write_text("# a divergent copy\n")
    found = check.failures(root)
    assert any("regular file on disk" in line for line in found), found


def test_a_link_pointing_somewhere_else_fails(tmp_path: Path) -> None:
    root = repo(tmp_path)
    (root / "CLAUDE.md").unlink()
    (root / "CLAUDE.md").symlink_to("README.md")
    found = check.failures(root)
    assert any("points at README.md" in line for line in found), found


def test_a_missing_source_fails(tmp_path: Path) -> None:
    root = repo(tmp_path)
    (root / "AGENTS.md").unlink()
    found = check.failures(root)
    assert any("AGENTS.md is missing" in line for line in found), found


@pytest.mark.parametrize("removed", ["AGENTS.md", "CLAUDE.md"])
def test_every_failure_names_the_source_or_the_property(tmp_path: Path, removed: str) -> None:
    """A refusal a reader cannot act on is a refusal that will be worked around."""
    root = repo(tmp_path)
    (root / removed).unlink()
    for line in check.failures(root):
        assert "AGENTS.md" in line or "symlink" in line, line
