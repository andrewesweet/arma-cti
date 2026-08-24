"""Direct tests for the command-table confinement and resolution checker."""

from __future__ import annotations

from typing import TYPE_CHECKING

from conftest import load_tool
from test_command_table_gate import delegated_record, repository

if TYPE_CHECKING:
    from pathlib import Path


check_command_table = load_tool("check_command_table")


def test_check_accepts_a_confined_row_with_a_resolving_recipe(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    agents = (repo / "AGENTS.md").read_text(encoding="utf-8")
    (repo / "AGENTS.md").write_text(
        agents.replace("`just old-recipe`", "`just new-recipe`"), encoding="utf-8"
    )
    (repo / "justfile").write_text(
        "old-recipe:\n    @true\n\nnew-recipe:\n    @true\n", encoding="utf-8"
    )
    delegated_record(repo)

    result = check_command_table.check(repo)

    assert result.applicable
    assert result.failure is None
    assert result.lines == ("command_table=ok path=AGENTS.md rows=1 recipes=new-recipe",)


def test_check_names_an_escape_outside_the_command_table(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    agents = (repo / "AGENTS.md").read_text(encoding="utf-8")
    (repo / "AGENTS.md").write_text(
        agents.replace("Other prose.", "Changed prose."), encoding="utf-8"
    )
    delegated_record(repo)

    result = check_command_table.check(repo)

    assert result.failure is not None
    assert result.failure.kind == check_command_table.COMMAND_TABLE_ESCAPE
    assert any(detail.startswith("escaped=") for detail in result.failure.details)


def test_check_rejects_a_pure_deletion_of_non_row_prose(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    agents = (repo / "AGENTS.md").read_text(encoding="utf-8")
    (repo / "AGENTS.md").write_text(agents.replace("Other prose.\n", ""), encoding="utf-8")
    delegated_record(repo)

    result = check_command_table.check(repo)

    assert result.failure is not None
    assert result.failure.kind == check_command_table.COMMAND_TABLE_ESCAPE
    assert any(detail.startswith("escaped=baseline:") for detail in result.failure.details)


def test_check_rejects_a_pure_insertion_of_non_row_prose(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    agents = (repo / "AGENTS.md").read_text(encoding="utf-8")
    (repo / "AGENTS.md").write_text(
        agents.replace("Other prose.\n", "Other prose.\nInserted prose.\n"),
        encoding="utf-8",
    )
    delegated_record(repo)

    result = check_command_table.check(repo)

    assert result.failure is not None
    assert result.failure.kind == check_command_table.COMMAND_TABLE_ESCAPE
    assert any(detail.startswith("escaped=candidate:") for detail in result.failure.details)


def test_check_names_a_recipe_that_is_absent_from_the_candidate_justfile(
    tmp_path: Path,
) -> None:
    repo = repository(tmp_path)
    agents = (repo / "AGENTS.md").read_text(encoding="utf-8")
    (repo / "AGENTS.md").write_text(
        agents.replace("`just old-recipe`", "`just missing-recipe`"), encoding="utf-8"
    )
    delegated_record(repo)

    result = check_command_table.check(repo)

    assert result.failure is not None
    assert result.failure.kind == check_command_table.COMMAND_TABLE_RECIPE_UNRESOLVED
    assert "recipe=missing-recipe" in result.failure.details


def test_check_is_not_applicable_when_agents_is_unchanged(tmp_path: Path) -> None:
    repo = repository(tmp_path)

    result = check_command_table.check(repo)

    assert not result.applicable
    assert result.failure is None
