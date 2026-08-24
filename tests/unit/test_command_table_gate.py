"""The ADR-0013 command-table route is mechanically confined and resolvable (#544)."""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

from conftest import REPO, load_tool

if TYPE_CHECKING:
    from pathlib import Path


gated_paths = load_tool("gated_paths")
check_command_table = load_tool("check_command_table")


def git(repo: Path, *args: str) -> None:
    """Run fixture Git and expose any setup failure."""
    completed = subprocess.run(  # noqa: S603 — fixture Git argv only
        ["git", *args],  # noqa: S607 — Git resolves from the test toolchain
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def repository(root: Path) -> Path:
    """Create a candidate tree with one command row and one just recipe."""
    repo = root / "issue-544"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "work")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "user.name", "test")
    (repo / "AGENTS.md").write_text(
        "# Instructions\n\n"
        "## Command surface\n\n"
        "| Command | Purpose | Requires Arma | Run when |\n"
        "|---|---|---|---|\n"
        "| `just old-recipe` | Old purpose | No | Always |\n\n"
        "Other prose.\n",
        encoding="utf-8",
    )
    (repo / "justfile").write_text("old-recipe:\n    @true\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "base")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")

    return repo


def delegated_record(repo: Path) -> None:
    """Add the ADR-0013 record that supplies the standing route."""
    adr = repo / "docs" / "adr" / "0099-command-table-rule.md"
    adr.parent.mkdir(parents=True)
    adr.write_text(
        "# Command-table rule\n\n"
        "Delegated-decision: yes\n"
        "Date: 2026-08-24\n"
        "Supersedes: none\n"
        "Reviewed-by-human: pending\n\n"
        "## What would overturn this\n\n"
        "A failed command-table check.\n",
        encoding="utf-8",
    )


def test_a_delegated_row_change_passes_when_the_candidate_recipe_resolves(
    tmp_path: Path,
) -> None:
    repo = repository(tmp_path)
    (repo / "AGENTS.md").write_text(
        (repo / "AGENTS.md")
        .read_text(encoding="utf-8")
        .replace("`just old-recipe`", "`just new-recipe`"),
        encoding="utf-8",
    )
    (repo / "justfile").write_text(
        "old-recipe:\n    @true\n\nnew-recipe:\n    @true\n",
        encoding="utf-8",
    )
    delegated_record(repo)

    report = gated_paths.check(repo, tmp_path / "approvals", issue=544)

    assert report.exit_code == 0
    assert "authorization=command_table" in report.lines[0]
    assert any(line.startswith("command_table=ok path=AGENTS.md") for line in report.lines)


def test_a_delegated_row_change_with_prose_outside_the_table_is_refused(
    tmp_path: Path,
) -> None:
    repo = repository(tmp_path)
    current = (repo / "AGENTS.md").read_text(encoding="utf-8")
    (repo / "AGENTS.md").write_text(
        current.replace("`just old-recipe`", "`just new-recipe`").replace(
            "Other prose.", "Changed prose."
        ),
        encoding="utf-8",
    )
    delegated_record(repo)

    report = gated_paths.check(repo, tmp_path / "approvals", issue=544)

    assert report.exit_code == 1
    assert "refusal=command_table_escape" in report.lines
    assert any(line.startswith("escaped=") for line in report.lines)


def test_a_delegated_row_change_with_an_unknown_recipe_is_refused(
    tmp_path: Path,
) -> None:
    repo = repository(tmp_path)
    (repo / "AGENTS.md").write_text(
        (repo / "AGENTS.md")
        .read_text(encoding="utf-8")
        .replace("`just old-recipe`", "`just missing-recipe`"),
        encoding="utf-8",
    )
    delegated_record(repo)

    report = gated_paths.check(repo, tmp_path / "approvals", issue=544)

    assert report.exit_code == 1
    assert "refusal=command_table_recipe_unresolved" in report.lines
    assert "recipe=missing-recipe" in report.lines


def test_just_check_runs_the_command_table_leg() -> None:
    completed = subprocess.run(
        ["just", "--dump", "--dump-format", "json"],  # noqa: S607 — required just binary
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    recipes = json.loads(completed.stdout)["recipes"]
    check_body = "\n".join(line[0] for line in recipes["check"]["body"])
    command_table_body = "\n".join(line[0] for line in recipes["check-command-table"]["body"])

    assert "--leg check-command-table" in check_body
    assert "tools/check_command_table.py" in command_table_body


def test_the_named_leg_checks_the_delegated_candidate_route(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    (repo / "AGENTS.md").write_text(
        (repo / "AGENTS.md")
        .read_text(encoding="utf-8")
        .replace("`just old-recipe`", "`just new-recipe`"),
        encoding="utf-8",
    )
    (repo / "justfile").write_text(
        "old-recipe:\n    @true\n\nnew-recipe:\n    @true\n",
        encoding="utf-8",
    )
    delegated_record(repo)

    assert check_command_table.main(["--root", str(repo)]) == 0
