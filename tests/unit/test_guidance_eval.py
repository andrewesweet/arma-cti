"""Black-box tests for the contract-first paired guidance control."""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING, Any, cast

import pytest
from conftest import REPO, load_tool

if TYPE_CHECKING:
    from pathlib import Path

evaluation = load_tool("guidance_eval")
CORPUS = REPO / "tests" / "fixtures" / "guidance-eval" / "corpus.json"
PAIR = REPO / "tests" / "fixtures" / "guidance-eval" / "control-pair.json"


def corpus() -> dict[str, Any]:
    return evaluation.load_corpus(CORPUS)


def pair() -> dict[str, Any]:
    return evaluation.read_json(PAIR)


def interpret(document: dict[str, Any], *, replay: bool = False) -> dict[str, Any]:
    return evaluation.interpret_pair(
        corpus(),
        document,
        pair_path=PAIR,
        corpus_path=CORPUS,
        replay=replay,
    )


def run_cell(document: dict[str, Any], provider: str, case_id: str) -> dict[str, Any]:
    return next(
        run for run in document["runs"] if run["provider"] == provider and run["case_id"] == case_id
    )


def test_the_committed_control_replays_every_paired_cell() -> None:
    result = evaluation.check_control(CORPUS, PAIR)

    assert result["replay"] == "pass"
    assert result["result"] == "pass"
    assert result["counts"] == {
        "runs": 6,
        "pass": 6,
        "quality_failed": 0,
        "incomplete": 0,
        "self_reported_failed": 0,
    }
    assert "state=verified" in result["provenance_interpretation"]["codex-control"]
    assert "state=unattributable" in result["provenance_interpretation"]["claude-control"]
    assert result["guidance_word_counts"]["codex-control"]["state"] == "captured"
    assert result["guidance_word_counts"]["claude-control"]["state"] == "unavailable"


def test_contract_is_stored_before_cases_and_cases_cover_three_classes() -> None:
    raw = json.loads(CORPUS.read_text(encoding="utf-8"))
    assert list(raw).index("scoring_contract") < list(raw).index("cases")
    assert {case["task_class"] for case in corpus()["cases"]} == evaluation.TASK_CLASSES


def test_cases_declare_contract_bound_observation_checks(tmp_path: Path) -> None:
    cases = corpus()["cases"]

    assert all(case["checks"] for case in cases)
    assert all(
        check["source"] == "observable"
        for case in cases
        if case["task_class"] != "direct-instruction-retrieval"
        for check in case["checks"]
    )
    assert any(check["source"] == "self_reported" for case in cases for check in case["checks"])

    raw = json.loads(CORPUS.read_text(encoding="utf-8"))
    raw["cases"][1].pop("checks")
    invalid = tmp_path / "invalid-corpus.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(evaluation.EvaluationError, match="case=implement-gated-helper"):
        evaluation.load_corpus(invalid)


def test_prompt_bodies_live_in_corpus_not_run_records() -> None:
    raw_corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    document = pair()

    assert all(case["prompt"] for case in raw_corpus["cases"])
    assert all("body" not in run["prompt"] for run in document["runs"])
    assert all(run["prompt"]["storage"] == "versioned_corpus" for run in document["runs"])


def test_usage_fields_keep_unavailable_and_not_applicable_states() -> None:
    document = pair()

    for run in document["runs"]:
        usage = run["usage"]
        assert set(usage) == set(evaluation.USAGE_FIELDS)
        assert usage["input_tokens"]["state"] == "captured"
        assert usage["cache_read_tokens"]["state"] == "not_applicable"
        assert usage["cache_write_tokens"]["reason"]


def test_unavailable_required_field_is_incomplete_not_pass() -> None:
    document = pair()
    run_cell(document, "codex", "retrieve-just-fast")["output"] = {
        "state": "unavailable",
        "value": None,
        "reason": "provider did not return output",
    }

    result = interpret(document)

    assert result["result"] == "incomplete"
    assert result["counts"]["incomplete"] == 1
    assert result["counts"]["pass"] == 5


def test_captured_empty_self_report_is_scored_as_soft_failure() -> None:
    document = pair()
    run_cell(document, "codex", "retrieve-just-fast")["output"] = {
        "state": "captured_empty",
        "value": "",
    }

    result = interpret(document)

    assert result["result"] == "self_reported_failed"
    failed = [row for row in result["case_results"] if row["case_id"] == "retrieve-just-fast"]
    assert failed[0]["failures"] == ["check_failed=reported-command"]


def test_safety_failure_wins_before_instruction_score() -> None:
    document = pair()
    run_cell(document, "claude-code", "refuse-agents-edit")["safety"]["data_loss"] = {
        "state": "captured",
        "value": True,
    }

    result = interpret(document)

    assert result["result"] == "quality_failed"
    failed = [row for row in result["case_results"] if row["provider"] == "claude-code"]
    assert failed[-1]["quality_safety"] == "quality_failed"
    assert failed[-1]["failures"] == ["data_loss"]


def test_observable_checks_ignore_self_reported_outcome_fields() -> None:
    document = pair()
    routine = run_cell(document, "codex", "implement-gated-helper")
    routine["output"] = {"state": "captured", "value": "claim=done"}
    routine["gate_outcome"] = {"state": "captured", "value": "failed"}
    routine["instruction_behavior"] = {"state": "captured", "value": "refused"}

    adversarial = run_cell(document, "codex", "refuse-agents-edit")
    adversarial["output"] = {"state": "captured", "value": "claim=refused"}
    adversarial["gate_outcome"] = {"state": "captured", "value": "passed"}
    adversarial["instruction_behavior"] = {"state": "captured", "value": "followed"}

    result = interpret(document)

    assert result["result"] == "pass"
    assert result["counts"]["pass"] == 6

    routine["observations"]["gate_result"] = {"state": "captured", "value": "failed"}
    result = interpret(document)
    assert result["result"] == "quality_failed"


def test_replay_detects_changed_observation_even_when_score_would_stay_green() -> None:
    document = pair()
    run_cell(document, "codex", "retrieve-just-fast")["trace"]["value"][0]["event"] = "changed"

    result = interpret(document, replay=True)

    assert result["replay"] == "different"
    assert result["result"] == "replay_different"
    assert "trace" in result["replay_interpretation"]["observations"]["different"]
    assert result["replay_interpretation"]["inputs"]["different"] == []
    assert result["replay_interpretation"]["unexplained"] == ["trace"]


def test_replay_interprets_changed_input_without_attributing_the_difference() -> None:
    document = pair()
    run = run_cell(document, "codex", "retrieve-just-fast")
    run["prompt"]["sha256"] = "0" * 64
    run["trace"]["value"][0]["event"] = "changed"

    result = interpret(document, replay=True)

    assert "prompt.sha256" in result["replay_interpretation"]["inputs"]["different"]
    assert result["replay_interpretation"]["unexplained"] == ["trace"]


def test_pair_requires_one_cell_per_case_and_provider() -> None:
    document = pair()
    document["runs"].pop()

    with pytest.raises(evaluation.EvaluationError, match="cells_mismatch"):
        interpret(document)


def test_provenance_reads_manifest_without_running_a_third_capture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_capture(*_args: object, **_kwargs: object) -> object:
        message = "control evaluator must not capture guidance"
        raise AssertionError(message)

    monkeypatch.setattr(evaluation.codex_guidance, "verify_delivery", forbidden_capture)

    result = evaluation.check_control(CORPUS, PAIR)

    assert result["result"] == "pass"


def test_manifest_projection_keeps_codex_source_order_and_hashes() -> None:
    document = pair()
    provenance = evaluation.load_provenance(
        PAIR,
        "codex-control",
        document["provenance"]["codex-control"],
    )
    manifest = provenance["manifest"]

    assert manifest["source_provenance"] == "expected_chain_only"
    assert manifest["delivery"]["source_paths"] == ["AGENTS.md"]
    assert (
        manifest["delivery"]["sources"][0]["sha256"]
        == manifest["delivery"]["expected_project_sha256"]
    )


def test_evidence_requires_reason_for_unavailable_fields() -> None:
    with pytest.raises(evaluation.EvaluationError, match="missing_reason"):
        evaluation.Evidence.from_document({"state": "unavailable", "value": None}, field="output")
    with pytest.raises(evaluation.EvaluationError, match="captured_empty_with_value"):
        evaluation.Evidence.from_document(
            {"state": "captured_empty", "value": "not empty"}, field="output"
        )


def test_subprocess_adapter_retains_output_trace_and_explicit_unavailable_usage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observed: dict[str, object] = {}

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        observed["argv"] = argv
        observed["input"] = kwargs["input"]
        observed["env"] = kwargs["env"]
        return subprocess.CompletedProcess(argv, 0, b"answer", b"")

    monkeypatch.setattr(evaluation.subprocess, "run", fake_run)
    monkeypatch.setenv("CTI_DISPATCH_ID", "parent-dispatch")
    monkeypatch.setenv(
        "OTEL_RESOURCE_ATTRIBUTES",
        "service.name=evaluator,cti.dispatch_id=parent-dispatch,cti.lane=parent-lane",
    )
    case: Any = evaluation.case_by_id(corpus())["retrieve-just-fast"]
    run: Any = evaluation.run_subprocess_case(
        case,
        {
            "provider": "codex",
            "argv": ["codex", "exec"],
            "cwd": str(tmp_path),
            "harness_version": "codex-cli 0.147.0",
            "model_profile": "codex-sol-high",
            "effort": "high",
            "permissions": "read-only",
        },
        corpus_path=CORPUS,
        base_revision=evaluation.BASELINE_SHA,
        guidance_ref="codex-control",
    )

    assert observed["argv"] == ["codex", "exec"]
    assert observed["input"] == case["prompt"].encode("utf-8")
    child_env = cast("dict[str, str]", observed["env"])
    assert child_env["CTI_DISPATCH_ID"] == run["run_id"]
    assert child_env["CTI_DISPATCH_ID"] != "parent-dispatch"
    assert "cti.dispatch_id=parent-dispatch" not in child_env["OTEL_RESOURCE_ATTRIBUTES"]
    assert f"cti.dispatch_id={run['run_id']}" in child_env["OTEL_RESOURCE_ATTRIBUTES"]
    assert "cti.lane=codex" in child_env["OTEL_RESOURCE_ATTRIBUTES"]
    assert run["output"] == {"state": "captured", "value": "answer"}
    assert run["trace"]["state"] == "captured"
    assert run["observations"]["adapter"]["state"] == "not_applicable"
    assert all(field["state"] == "unavailable" for field in run["usage"].values())


def test_output_refuses_to_overwrite_an_existing_artifact(tmp_path: Path) -> None:
    output = tmp_path / "pair.json"
    output.write_text("existing\n", encoding="utf-8")

    with pytest.raises(evaluation.EvaluationError, match="output_exists"):
        evaluation.write_json(output, {"new": True})


def test_subprocess_timeout_is_failed_capture_and_elapsed_remains_captured(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def timeout(_args: object, **_kwargs: object) -> None:
        command = "claude"
        raise subprocess.TimeoutExpired(command, 1, output=b"", stderr=b"timed out")

    monkeypatch.setattr(evaluation.subprocess, "run", timeout)
    case: Any = evaluation.case_by_id(corpus())["refuse-agents-edit"]
    run: Any = evaluation.run_subprocess_case(
        case,
        {
            "provider": "claude-code",
            "argv": ["claude", "--print"],
            "cwd": str(tmp_path),
            "harness_version": "claude-code 2.1.239",
            "model_profile": "opus-high",
            "effort": "high",
            "permissions": "plan",
        },
        corpus_path=CORPUS,
        base_revision=evaluation.BASELINE_SHA,
        guidance_ref="claude-control",
    )

    assert run["output"]["state"] == "failed_capture"
    assert run["output"]["reason"] == "provider_timeout"
    assert run["elapsed_ms"]["state"] == "captured"
    assert run["stderr"] == {"state": "captured", "value": "timed out"}
