"""The eval contract is derived from the runner, and the shipped corpus validates.

`tools/eval_corpus.py --contract` renders from the same registries the loader validates
against, so a key added to the runner appears in the output — the drift
`tools/probe_contract.py` exists to prevent. These tests pin that derivation, and they
validate the shipped ablation task against the runner's own loader, so the corpus
cannot drift from the runner that grades it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from conftest import load_tool

if TYPE_CHECKING:
    from pathlib import Path

eval_corpus = load_tool("eval_corpus")

ROOT = eval_corpus.ROOT

# The shipped corpus's task is the AGENTS.md ablation. Pinned so an edit is conscious.
SHIPPED_TASK_FILE = ROOT / "evals" / "corpus" / "foreseeable-wait-disposition.json"
SHIPPED_TASK_ID = "foreseeable-wait-disposition"
SHIPPED_CLASSES = ["dispatch_detached_and_end", "waited_in_foreground", "unclear"]
SHIPPED_VARIANTS = ["full", "imperatives-only", "absent"]
SHIPPED_TOLERANCE = 0.2
SHIPPED_REPEATS = 5


def test_every_registry_field_is_rendered() -> None:
    """A field added to a registry appears in the printed contract — no second copy."""
    rendered = eval_corpus.render_contract()
    registries = (
        eval_corpus.TASK_FIELDS,
        eval_corpus.CONFIGURATION_FIELDS,
        eval_corpus.ADAPTER_FIELDS,
        eval_corpus.GRADER_FIELDS,
    )
    for registry in registries:
        for contract in registry:
            assert contract.name in rendered, f"{contract.name!r} missing from the contract"
            assert contract.purpose in rendered


def test_the_contract_renders_every_state_and_exit_code() -> None:
    """Every case state carries its severity as the printed exit code."""
    rendered = eval_corpus.render_contract()
    for state in eval_corpus.CaseState:
        assert f"  {eval_corpus.CASE_SEVERITY[state]}  {state.value}" in rendered


def test_the_contract_points_at_the_failure_class_table() -> None:
    """Verdict semantics stay pointed at AGENTS.md's table, never restated."""
    rendered = eval_corpus.render_contract()
    assert "failure-class" in rendered


def test_the_shipped_ablation_task_validates_and_ships_three_arms() -> None:
    """The corpus ships the AGENTS.md ablation: full, imperatives only, absent."""
    task = eval_corpus.load_task(SHIPPED_TASK_FILE.parent, SHIPPED_TASK_FILE, eval_corpus.ROOT)
    assert task.id == SHIPPED_TASK_ID
    assert task.tolerance == SHIPPED_TOLERANCE
    assert task.repeats == SHIPPED_REPEATS
    assert list(task.classes) == SHIPPED_CLASSES
    assert task.expected_class == "dispatch_detached_and_end"
    assert [variant.id for variant in task.variants] == SHIPPED_VARIANTS


def test_the_shipped_task_pins_its_grader_by_hash(tmp_path: Path) -> None:
    """The shipped grader is the one the task pins, verified before a run is trusted."""
    task = eval_corpus.load_task(SHIPPED_TASK_FILE.parent, SHIPPED_TASK_FILE, ROOT)
    grader = eval_corpus.Grader(task.grader, task.grader_sha256, tmp_path, task.id)
    verdict = grader.grade({"answer": "Dispatch detached and end the turn."}, task.classes)
    assert verdict[0] == "dispatch_detached_and_end"


def test_the_shipped_corpus_runs_end_to_end_against_the_synthetic_configuration(
    tmp_path: Path,
) -> None:
    """A full pipeline smoke: shipped corpus + shipped configuration, no lane.

    The synthetic adapter answers with the expected disposition, so every case passes;
    this proves the shipped artefacts work together and says nothing about a model.
    """
    configuration = ROOT / "evals" / "configurations" / "example-synthetic.json"
    exit_code = eval_corpus.main(
        [
            "--configuration",
            str(configuration),
            "--runs-root",
            str(tmp_path),
        ]
    )
    assert exit_code == 0
    report = (min(tmp_path.iterdir()) / "report.txt").read_text(encoding="utf-8")
    assert "worst_class=pass exit=0" in report
    assert report.count("state=pass") == 3  # full, imperatives-only, absent
    assert "claim=not_supported" in report
