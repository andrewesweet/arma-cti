"""The mutation-smoke contract is rendered from its enforcing constants (#528)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from conftest import load_tool

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

load_tool("mutation_shell")
load_tool("mutation_rust")
mutation_smoke = load_tool("mutation_smoke")


def test_a_value_added_to_the_enforcing_module_appears_in_the_printed_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A new eligible root must be visible without editing the printer."""
    added = "future-source/"
    monkeypatch.setattr(mutation_smoke, "PRODUCT_ROOTS", (*mutation_smoke.PRODUCT_ROOTS, added))

    rendered = mutation_smoke.render_contract()

    assert f"`{added}`" in rendered


def test_a_value_removed_from_the_enforcing_module_leaves_the_printed_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A removed eligible root must not outlive the rule that named it."""
    removed = mutation_smoke.PRODUCT_ROOTS[0]
    monkeypatch.setattr(
        mutation_smoke,
        "PRODUCT_ROOTS",
        tuple(path for path in mutation_smoke.PRODUCT_ROOTS if path != removed),
    )

    rendered = mutation_smoke.render_contract()

    assert f"`{removed}`" not in rendered


def test_the_contract_renders_policy_values_and_reasoned_exemptions() -> None:
    rendered = mutation_smoke.render_contract()

    for name in (
        "PRODUCT_ROOTS",
        "SHELL_ROOTS",
        "SCOPE",
        "MANIFEST",
        "VERSION",
        "JOBS",
        "CAP",
        "FLOOR",
        "BUDGET_S",
        "COLLECT_S",
        "TESTS_PER_MUTANT",
        "TEST_SECONDS_PER_MUTANT",
        "COST_GRAIN",
        "TIMEOUT_FLOOR_S",
        "TIMEOUT_FACTOR",
        "SHELL_CAP",
        "SHELL_FLOOR",
        "SHELL_BUDGET_S",
        "SHELL_TEST_SECONDS_PER_MUTANT",
        "SHELL_DISCRIMINATING",
        "BASELINE",
        "SLACK",
        "HASH_SEED",
        "SHELL_SUBJECT",
        "NO_MUTABLE_SUBJECT",
        "NO_TEST_MODULE",
        "SURVIVES_BY_DESIGN",
    ):
        assert f"`{name}`" in rendered

    for path, reason in mutation_smoke.NO_MUTABLE_SUBJECT.items():
        assert path in rendered
        assert reason in rendered
    for mutant, reason in mutation_smoke.mutation_rust.SURVIVES_BY_DESIGN.items():
        assert mutant in rendered
        assert reason in rendered


def test_the_contract_labels_narration_and_points_to_failure_classes() -> None:
    rendered = mutation_smoke.render_contract()

    assert "Narration" in rendered
    assert "TIMEOUT_FLOOR_S" in rendered
    assert "not a third" in rendered
    assert "counts as killed" in rendered
    assert "CLAUDE.md" in rendered
    assert "Failure classes" in rendered
    for phrase in (
        "Fix the code under test",
        "Investigate synchronisation",
        "Collect dump, escalate to human",
        "Re-dispatch to another lane",
    ):
        assert phrase not in rendered


def test_rules_prints_and_exits_zero_without_creating_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)

    assert mutation_smoke.main(["--rules"]) == 0
    assert "just mutation --rules" in capsys.readouterr().out
    assert tuple(tmp_path.iterdir()) == ()
