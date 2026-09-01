"""The eval contract is derived from the runner, and the shipped corpus validates.

`tools/eval_corpus.py --contract` renders from the same registries the runner validates
or applies, so a field added to a registry appears in the output — the drift
`tools/probe_contract.py` exists to prevent. These tests pin that derivation, and they
validate the shipped ablation task against the runner's own loader, so the corpus
cannot drift from the runner that grades it.
"""

from __future__ import annotations

import argparse
import json
import shutil
from typing import TYPE_CHECKING

import pytest
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
    registries = (registry for _name, registry in eval_corpus.CONTRACT_REGISTRIES)
    for registry in registries:
        for contract in registry:
            assert contract.name in rendered, f"{contract.name!r} missing from the contract"
            assert contract.purpose in rendered


def test_adapter_contract_requires_final_usage_to_match_the_sidecar() -> None:
    """The adapter-facing contract states the equality the runner enforces."""
    rendered = eval_corpus.render_contract()
    for name in ("tokens_in", "tokens_out", "commands"):
        assert f"must exactly equal usage.json.{name}" in rendered
    assert "0 when unknown" not in rendered


def test_published_contract_command_executes() -> None:
    """The command boundary exercised by operators is not hidden by module imports."""
    assert eval_corpus.main(["--contract"]) == 0


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
    assert task.configuration == "per-run"
    assert list(task.classes) == SHIPPED_CLASSES
    assert task.expected_class == "dispatch_detached_and_end"
    assert [variant.id for variant in task.variants] == SHIPPED_VARIANTS


def test_the_shipped_task_pins_its_grader_by_hash(tmp_path: Path) -> None:
    """The shipped grader is the one the task pins, verified before a run is trusted."""
    task = eval_corpus.load_task(SHIPPED_TASK_FILE.parent, SHIPPED_TASK_FILE, ROOT)
    grader = eval_corpus.Grader(task.grader, task.grader_sha256, tmp_path, task.id)
    verdict = grader.grade({"answer": "Dispatch detached and end the turn."}, task.classes)
    assert verdict[0] == "dispatch_detached_and_end"


def test_wait_first_answers_beat_later_handoff_language(tmp_path: Path) -> None:
    """A stated foreground wait stays waited even when its handoff is mentioned later."""
    task = eval_corpus.load_task(SHIPPED_TASK_FILE.parent, SHIPPED_TASK_FILE, ROOT)
    grader = eval_corpus.Grader(task.grader, task.grader_sha256, tmp_path, task.id)
    foreground_waits = (
        (
            "I would wait in the foreground for the gate to finish, then write a handoff "
            "and end my turn."
        ),
        "I stay and poll the gate until it completes, then hand off and finish my turn.",
    )
    for answer in foreground_waits:
        assert grader.grade({"answer": answer}, task.classes)[0] == "waited_in_foreground"
    detached = (
        "I would dispatch the gate as a detached session and end my turn so nothing waits on me."
    )
    assert grader.grade({"answer": detached}, task.classes)[0] == "dispatch_detached_and_end"


def test_grader_does_not_treat_the_word_subagent_as_a_disposition(tmp_path: Path) -> None:
    """A waiting answer mentioning its role is not classified as detached."""
    task = eval_corpus.load_task(SHIPPED_TASK_FILE.parent, SHIPPED_TASK_FILE, ROOT)
    grader = eval_corpus.Grader(task.grader, task.grader_sha256, tmp_path, task.id)
    verdict = grader.grade({"answer": "As a subagent, I wait, then end my turn."}, task.classes)
    assert verdict[0] == "waited_in_foreground"


def test_the_shipped_corpus_runs_end_to_end_against_the_synthetic_configuration(
    tmp_path: Path,
) -> None:
    """A full pipeline smoke: shipped corpus + shipped configuration, no lane.

    The synthetic adapter answers with the expected disposition, so every case passes;
    this proves the shipped artefacts work together and says nothing about a model.
    """
    if shutil.which("bwrap") is None:
        pytest.skip("bubblewrap (`bwrap`) is required for pipeline tests")
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
    assert "worst_class=within_tolerance exit=0" in report
    assert report.count("status=within_tolerance") == 3  # full, imperatives-only, absent
    assert "claim=not_supported" in report


# --- The loader's boundaries, driven directly (mutation smoke grades this module on
# --- tools/eval_corpus.py, so each boundary below is asserted here as well as there).


def _write_corpus_with_grader(tmp_path: Path, **task_overrides: object) -> Path:
    """Write a one-task corpus whose grader hash always matches its file."""
    graders = tmp_path / "graders"
    graders.mkdir(parents=True, exist_ok=True)
    (graders / "g.py").write_text(
        "def grade(record):\n    return {'class': 'c'}\n", encoding="utf-8"
    )
    document = {
        "schema": eval_corpus.TASK_SCHEMA,
        "id": "t",
        "provenance": "test",
        "configuration": "per-run",
        "prompt": "p",
        "classes": ["c"],
        "expected_class": "c",
        "repeats": 1,
        "tolerance": 0.2,
        "grader": "graders/g.py",
        "grader_sha256": eval_corpus.sha256_bytes((graders / "g.py").read_bytes()),
        "variants": [{"id": "v", "file": None}],
    }
    document.update(task_overrides)
    corpus = tmp_path / "corpus"
    corpus.mkdir(parents=True, exist_ok=True)
    (corpus / "t.json").write_text(json.dumps(document), encoding="utf-8")
    return corpus


def _write_config_file(tmp_path: Path, document: dict[str, object], name: str = "c.json") -> Path:
    """Write one configuration document and return its path."""
    path = tmp_path / name
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_budget_legs_reject_bools_and_subfloor_values(tmp_path: Path) -> None:
    """A budget leg that is a bool or below its floor is refused, not coerced."""
    for bad in ({"seconds": True}, {"tokens": 0}, {"commands": -1}):
        corpus = _write_corpus_with_grader(tmp_path, budget=bad)
        with pytest.raises(eval_corpus.EvalRefusalError) as raised:
            eval_corpus.load_corpus(corpus, ROOT)
        assert raised.value.kind == "input_invalid"
        assert any("budget_out_of_range" in detail for detail in raised.value.details)


def test_variant_with_empty_id_is_refused(tmp_path: Path) -> None:
    """A variant arm must carry a non-empty id."""
    corpus = _write_corpus_with_grader(tmp_path, variants=[{"id": "", "file": None}])
    with pytest.raises(eval_corpus.EvalRefusalError) as raised:
        eval_corpus.load_corpus(corpus, ROOT)
    assert any("variant_id_invalid" in detail for detail in raised.value.details)


def test_frozen_variant_refuses_when_its_derived_source_changes(tmp_path: Path) -> None:
    """A reduction cannot run against a different live source than the one it records."""
    source = tmp_path / "repo" / "AGENTS.md"
    source.parent.mkdir()
    source.write_text("source before\n", encoding="utf-8")
    context = tmp_path / "context" / "frozen.md"
    context.parent.mkdir()
    context.write_text("reduction\n", encoding="utf-8")
    source_sha256 = eval_corpus.sha256_file(source)
    corpus = _write_corpus_with_grader(
        tmp_path,
        variants=[
            {
                "id": "frozen",
                "file": "context/frozen.md",
                "derived_from": {"repo_file": "AGENTS.md", "sha256": source_sha256},
            }
        ],
    )
    source.write_text("source after\n", encoding="utf-8")
    with pytest.raises(eval_corpus.EvalRefusalError) as raised:
        eval_corpus.load_corpus(corpus, source.parent)
    assert raised.value.kind == "context_pin_stale"
    assert any("expected=" in detail for detail in raised.value.details)
    assert any("observed=" in detail for detail in raised.value.details)


def test_configuration_with_empty_harness_section_names_the_missing_field(
    tmp_path: Path,
) -> None:
    """A harness section with no argv is refused as the dotted field it is."""
    config = _write_config_file(
        tmp_path, {"schema": eval_corpus.CONFIGURATION_SCHEMA, "name": "c", "harness": {}}
    )
    with pytest.raises(eval_corpus.EvalRefusalError) as raised:
        eval_corpus.load_configuration(config)
    assert raised.value.kind == "input_invalid"
    assert any("missing=c.json.harness.argv" in detail for detail in raised.value.details)


def test_configuration_name_cannot_escape_evidence_paths(tmp_path: Path) -> None:
    """Configuration identities are safe directory components, not path fragments."""
    config = _write_config_file(
        tmp_path,
        {
            "schema": eval_corpus.CONFIGURATION_SCHEMA,
            "name": "../escape",
            "harness": {"argv": ["true"]},
        },
    )
    with pytest.raises(eval_corpus.EvalRefusalError) as raised:
        eval_corpus.load_configuration(config)
    assert any("identifier_invalid" in detail for detail in raised.value.details)


def test_effective_budget_default_resolution() -> None:
    """No budget anywhere resolves to the runner defaults; task legs beat config legs."""
    task_no_budget = eval_corpus.Task("t", "", "p", "p", ("c",), "c", 1, 0.2, None, "", (), None)
    defaults = eval_corpus.effective_budget(
        task_no_budget, eval_corpus.Configuration("c", None, (), {}, None, None, None)
    )
    assert defaults.seconds == eval_corpus.DEFAULT_BUDGET_SECONDS
    configuration_legs = eval_corpus.Configuration(
        "c", None, (), {}, eval_corpus.Budget(30.0, 1000, 50), None, None
    )
    from_config = eval_corpus.effective_budget(task_no_budget, configuration_legs)
    assert (from_config.seconds, from_config.tokens, from_config.commands) == (30.0, 1000, 50)
    task_legs = eval_corpus.Task(
        "t",
        "",
        "p",
        "p",
        ("c",),
        "c",
        1,
        0.2,
        None,
        "",
        (),
        eval_corpus.Budget(60.0, eval_corpus.DEFAULT_BUDGET_TOKENS, 5),
    )
    mixed = eval_corpus.effective_budget(task_legs, configuration_legs)
    assert (mixed.seconds, mixed.tokens, mixed.commands) == (60.0, 1000, 5)


def test_enforce_budget_command_boundary_is_over_not_equal(tmp_path: Path) -> None:
    """A trial at exactly its command budget completes; one past it is a budget stop."""
    trial_dir = tmp_path
    budget = eval_corpus.Budget(60.0, 1000, 3)
    record = {
        "answer": "a",
        "stopped_by": "completed",
        "tokens_in": 0,
        "tokens_out": 0,
        "commands": 3,
    }
    outcome, kept = eval_corpus.enforce_budget(trial_dir, record, budget, {})
    assert outcome.state == "graded_pending"
    assert kept is not None
    over = dict(record, commands=4)
    outcome_over, _ = eval_corpus.enforce_budget(trial_dir, over, budget, {})
    assert outcome_over.state == "budget_stopped"
    assert outcome_over.detail == "budget=commands"


def test_live_usage_is_required_for_execution_records(tmp_path: Path) -> None:
    """A final self-report cannot substitute for a missing live usage sidecar."""
    budget = eval_corpus.Budget(60.0, 1000, 3)
    record = {
        "answer": "a",
        "stopped_by": "completed",
        "tokens_in": 0,
        "tokens_out": 0,
        "commands": 0,
    }
    outcome, kept = eval_corpus.enforce_budget(
        tmp_path,
        record,
        budget,
        {},
        require_live_usage=True,
    )
    assert outcome.state == "untyped_harness_failure"
    assert kept is None
    assert "usage.json" in outcome.detail


def test_aggregate_case_keeps_the_currency_cost_it_was_given() -> None:
    """The case's currency figure travels from the usage block into the result."""
    usage = {
        "wall_seconds": 1.0,
        "tokens_in": 2_000_000.0,
        "tokens_out": 1_000_000.0,
        "commands": 0.0,
        "currency_cost": 21.0,
    }
    outcomes = [eval_corpus.TrialOutcome("1", "c", "met")]
    result = eval_corpus.aggregate_case("cfg", "t/v", outcomes, "c", 0.2, usage)
    assert result.currency_cost == 21.0


def test_configuration_unit_costs_default_to_zero_pricing(tmp_path: Path) -> None:
    """Unit costs missing a leg price at zero, so a currency figure stays auditable."""
    config = _write_config_file(
        tmp_path,
        {
            "schema": eval_corpus.CONFIGURATION_SCHEMA,
            "name": "c",
            "harness": {"argv": ["true"]},
            "unit_costs": {"currency": "GBP"},
        },
    )
    configuration = eval_corpus.load_configuration(config)
    assert configuration.unit_costs is not None
    usage = {"tokens_in": 1_000_000.0, "tokens_out": 0.0}
    assert eval_corpus.currency_cost(configuration, usage) == 0.0


def test_prepare_refuses_zero_and_three_configurations(tmp_path: Path) -> None:
    """Exactly one or two configurations run; anything else is refused by name."""
    corpus = _write_corpus_with_grader(tmp_path)
    config = _write_config_file(
        tmp_path,
        {"schema": eval_corpus.CONFIGURATION_SCHEMA, "name": "c", "harness": {"argv": ["true"]}},
    )
    none_args = argparse.Namespace(
        contract=False, configuration=[], corpus=corpus, runs_root=tmp_path
    )
    with pytest.raises(eval_corpus.EvalRefusalError) as raised:
        eval_corpus.prepare_run(none_args)
    assert raised.value.kind == "input_invalid"
    three_args = argparse.Namespace(
        contract=False,
        configuration=[config, config, config],
        corpus=corpus,
        runs_root=tmp_path,
    )
    with pytest.raises(eval_corpus.EvalRefusalError) as raised:
        eval_corpus.prepare_run(three_args)
    assert raised.value.kind == "input_invalid"
