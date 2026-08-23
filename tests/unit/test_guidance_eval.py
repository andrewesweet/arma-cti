"""Black-box tests for the contract-first paired guidance control."""

from __future__ import annotations

import json
import subprocess
import sys
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
    if replay:
        return evaluation.compare_pair_replay(
            corpus(),
            pair(),
            document,
            stored_pair_path=PAIR,
            replayed_pair_path=PAIR,
            corpus_path=CORPUS,
        )
    return evaluation.interpret_pair(
        corpus(),
        document,
        pair_path=PAIR,
        corpus_path=CORPUS,
    )


def run_cell(document: dict[str, Any], provider: str, case_id: str) -> dict[str, Any]:
    return next(
        run for run in document["runs"] if run["provider"] == provider and run["case_id"] == case_id
    )


def capture_replay_inputs(*documents: dict[str, Any]) -> None:
    for document in documents:
        for run in document["runs"]:
            run["invocation"] = {
                "argv_sha256": "1" * 64,
                "cwd": "/paired-worktree",
                "timeout_seconds": 120.0,
            }
            run["child_environment"] = {
                "state": "captured",
                "value": {"PAIR_ENV": "same"},
            }


def test_the_committed_control_validates_every_paired_cell() -> None:
    result = evaluation.check_control(CORPUS, PAIR)

    assert result["replay"] == "not_requested"
    assert result["result"] == "self_reported_pass"
    assert result["counts"] == {
        "runs": 6,
        "observed_pass": 0,
        "mixed_pass": 0,
        "self_reported_pass": 6,
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
        any(check["source"] == "observable" for check in case["checks"])
        for case in cases
        if case["task_class"] != "direct-instruction-retrieval"
    )
    assert any(check["source"] == "self_reported" for case in cases for check in case["checks"])

    raw = json.loads(CORPUS.read_text(encoding="utf-8"))
    raw["cases"][1].pop("checks")
    invalid = tmp_path / "invalid-corpus.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(evaluation.EvaluationError, match="case=implement-gated-helper"):
        evaluation.load_corpus(invalid)

    raw = json.loads(CORPUS.read_text(encoding="utf-8"))
    raw["cases"][1]["checks"][0]["kind"] = "process_exit"
    invalid = tmp_path / "kind-path-mismatch.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(evaluation.EvaluationError, match="path_kind_mismatch"):
        evaluation.load_corpus(invalid)


def test_contract_marks_unobserved_case_claims_and_fixture_scores_as_soft() -> None:
    document = corpus()
    adapters = document["scoring_contract"]["adapter_evidence"]
    assert adapters["fixture"]["score_source"] == "self_reported"
    assert adapters["subprocess"]["score_source"] == "contract_checks"

    routine = evaluation.case_by_id(document)["implement-gated-helper"]
    adversarial = evaluation.case_by_id(document)["refuse-agents-edit"]
    assert [check["source"] for check in routine["checks"]] == [
        "observable",
        "self_reported",
        "self_reported",
    ]
    assert [check["source"] for check in adversarial["checks"]] == [
        "observable",
        "self_reported",
        "self_reported",
    ]

    result = evaluation.check_control(CORPUS, PAIR)
    assert result["result"] == "self_reported_pass"
    assert result["counts"] == {
        "runs": 6,
        "observed_pass": 0,
        "mixed_pass": 0,
        "self_reported_pass": 6,
        "quality_failed": 0,
        "incomplete": 0,
        "self_reported_failed": 0,
    }
    assert {score["score_source"] for score in result["case_results"]} == {"self_reported"}


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
    assert result["counts"]["self_reported_pass"] == 5


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
    run = run_cell(document, "claude-code", "refuse-agents-edit")
    run["adapter"] = "subprocess"
    run["safety"]["data_loss"] = {
        "state": "captured",
        "value": True,
    }

    result = interpret(document)

    assert result["result"] == "quality_failed"
    failed = [row for row in result["case_results"] if row["provider"] == "claude-code"]
    assert failed[-1]["quality_safety"] == "quality_failed"
    assert failed[-1]["failures"] == ["data_loss"]


def test_observed_file_result_is_hard_and_reported_gate_claims_are_soft() -> None:
    document = pair()
    routine = run_cell(document, "codex", "implement-gated-helper")
    routine["adapter"] = "subprocess"
    routine["output"] = {"state": "captured", "value": "claim=done"}

    result = interpret(document)

    assert result["result"] == "self_reported_failed"
    assert result["counts"]["quality_failed"] == 0

    routine["output"] = {
        "state": "captured",
        "value": "change=implemented gate=just fast gate_result=passed",
    }
    routine["observations"]["file_changed"] = {"state": "captured", "value": False}
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


def test_replay_with_missing_fixture_inputs_is_unavailable_not_equal() -> None:
    document = pair()

    result = evaluation.compare_pair_replay(
        corpus(),
        document,
        document,
        stored_pair_path=PAIR,
        replayed_pair_path=PAIR,
        corpus_path=CORPUS,
    )

    assert result["replay"] == "unavailable"
    assert result["result"] == "replay_unavailable"
    assert result["replay_interpretation"]["inputs"]["unavailable"] == [
        "child_environment",
        "invocation.argv_sha256",
        "invocation.cwd",
        "invocation.timeout_seconds",
    ]


def test_replay_interprets_changed_input_without_attributing_the_difference() -> None:
    document = pair()
    run = run_cell(document, "codex", "retrieve-just-fast")
    run["prompt"]["sha256"] = "0" * 64
    run["trace"]["value"][0]["event"] = "changed"

    result = interpret(document, replay=True)

    assert "prompt.sha256" in result["replay_interpretation"]["inputs"]["different"]
    assert result["replay_interpretation"]["unexplained"] == []


def test_replay_names_every_material_input_and_a_changed_model_as_a_confounder() -> None:
    stored = pair()
    replayed = pair()
    replayed["providers"]["codex"]["model_profile"] = "codex-sol-max"
    run = run_cell(replayed, "codex", "retrieve-just-fast")
    run["model_profile"] = "codex-sol-max"
    run["trace"]["value"][0]["event"] = "changed"

    result = evaluation.compare_pair_replay(
        corpus(),
        stored,
        replayed,
        stored_pair_path=PAIR,
        replayed_pair_path=PAIR,
        corpus_path=CORPUS,
    )

    inputs = result["replay_interpretation"]["inputs"]
    compared = set(inputs["same"]) | set(inputs["different"])
    assert {
        "harness_version",
        "model_profile",
        "effort",
        "permissions",
        "guidance_ref",
        "started_at",
        "ended_at",
    } <= compared
    assert inputs["different"] == ["model_profile"]
    assert inputs["unavailable"] == [
        "child_environment",
        "invocation.argv_sha256",
        "invocation.cwd",
        "invocation.timeout_seconds",
    ]
    assert result["replay_interpretation"]["attribution"] == {
        "status": "not_attributable_to_guidance",
        "guidance_inputs": [],
        "confounding_inputs": ["model_profile"],
        "unavailable_inputs": [
            "child_environment",
            "invocation.argv_sha256",
            "invocation.cwd",
            "invocation.timeout_seconds",
        ],
    }
    summary = evaluation.render_summary(result)
    assert "replay_inputs_different=model_profile" in summary
    assert (
        "replay_inputs_unavailable=child_environment,invocation.argv_sha256,"
        "invocation.cwd,invocation.timeout_seconds" in summary
    )
    assert "replay_attribution=not_attributable_to_guidance" in summary
    assert "replay_confounders=model_profile" in summary


def test_replay_does_not_attribute_a_caller_declared_manifest_hash() -> None:
    stored = pair()
    replayed = pair()
    capture_replay_inputs(stored, replayed)
    replayed["provenance"]["codex-control"]["manifest_sha256"] = "0" * 64
    run_cell(replayed, "codex", "retrieve-just-fast")["trace"]["value"][0]["event"] = "changed"

    with pytest.raises(evaluation.EvaluationError, match="manifest_hash_mismatch"):
        evaluation.interpret_pair(
            corpus(),
            replayed,
            pair_path=PAIR,
            corpus_path=CORPUS,
        )

    result = evaluation.compare_pair_replay(
        corpus(),
        stored,
        replayed,
        stored_pair_path=PAIR,
        replayed_pair_path=PAIR,
        corpus_path=CORPUS,
    )

    assert result["replay_interpretation"]["attribution"] == {
        "status": "not_attributable_to_guidance",
        "guidance_inputs": [],
        "confounding_inputs": [],
        "unavailable_inputs": [],
    }
    assert result["replay_integrity_relaxations"] == [
        {
            "check": "provenance.codex-control.manifest_sha256",
            "reason": (
                "replay compares recorded input drift; guidance attribution uses the parsed "
                "manifest identity"
            ),
        }
    ]
    assert (
        "replay_integrity_relaxed=provenance.codex-control.manifest_sha256 "
        "reason=replay compares recorded input drift; guidance attribution uses the parsed "
        "manifest identity"
    ) in evaluation.render_summary(result)


def test_replay_attributes_only_a_changed_parsed_guidance_manifest(tmp_path: Path) -> None:
    stored = pair()
    replayed = pair()
    capture_replay_inputs(stored, replayed)
    replay_records = tmp_path / "dispatch-records"
    replay_records.mkdir()
    for name in ("claude.json", "codex.json"):
        source = PAIR.parent / "dispatch-records" / name
        (replay_records / name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    codex_record_path = replay_records / "codex.json"
    codex_record = json.loads(codex_record_path.read_text(encoding="utf-8"))
    delivery = codex_record["guidance_manifest"]["delivery"]
    changed_guidance_sha256 = "0" * 64
    delivery["sources"][0]["sha256"] = changed_guidance_sha256
    delivery["expected_project_sha256"] = changed_guidance_sha256
    delivery["delivered_project_sha256"] = changed_guidance_sha256
    delivery["combined_delivered_sha256"] = "1" * 64
    codex_record_path.write_text(json.dumps(codex_record), encoding="utf-8")

    parsed_manifest = evaluation.codex_guidance.manifest_from_record(
        codex_record,
        evaluation.codex_guidance.GuidanceHarness.CODEX,
    ).document()
    stored_manifest = evaluation.load_provenance(
        PAIR,
        "codex-control",
        stored["provenance"]["codex-control"],
    )["manifest"]
    assert parsed_manifest != stored_manifest
    replayed["provenance"]["codex-control"]["manifest_sha256"] = evaluation.sha256_json(
        parsed_manifest
    )
    run_cell(replayed, "codex", "retrieve-just-fast")["trace"]["value"][0]["event"] = "changed"

    result = evaluation.compare_pair_replay(
        corpus(),
        stored,
        replayed,
        stored_pair_path=PAIR,
        replayed_pair_path=tmp_path / "replay-pair.json",
        corpus_path=CORPUS,
    )

    assert result["replay_interpretation"]["attribution"] == {
        "status": "guidance_variant_only_among_recorded_inputs",
        "guidance_inputs": ["provenance.codex-control.observed_manifest_sha256"],
        "confounding_inputs": [],
        "unavailable_inputs": [],
    }
    assert result["replay_integrity_relaxations"] == []
    assert "replay_integrity_relaxed=none" in evaluation.render_summary(result)


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

    assert result["result"] == "self_reported_pass"


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
    assert run["invocation"] == {
        "argv_sha256": evaluation.sha256_json(["codex", "exec"]),
        "cwd": str(tmp_path),
        "timeout_seconds": 120.0,
    }
    assert run["observations"]["adapter"]["state"] == "not_applicable"
    assert all(field["state"] == "unavailable" for field in run["usage"].values())


def test_subprocess_child_receives_only_the_explicit_environment_allowlist(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    parent_path = evaluation.os.environ["PATH"]
    monkeypatch.setattr(
        evaluation.os,
        "environ",
        {
            "PATH": parent_path,
            "HOME": "/safe/home",
            "LANG": "C.UTF-8",
            "TMPDIR": str(tmp_path),
            "ANTHROPIC_BASE_URL": "https://parent-lane.invalid",
            "ANTHROPIC_AUTH_TOKEN": "parent-secret",
            "OPENAI_API_KEY": "parent-secret",
            "CODEX_MODEL": "parent-model",
            "OTEL_SERVICE_NAME": "parent-service",
            "OTEL_SERVICE_NAMESPACE": "parent-namespace",
            "OTEL_RESOURCE_ATTRIBUTES": (
                "service.name=parent,cti.dispatch_id=parent,cti.lane=parent"
            ),
        },
    )
    case: Any = evaluation.case_by_id(corpus())["retrieve-just-fast"]
    run: Any = evaluation.run_subprocess_case(
        case,
        {
            "provider": "codex",
            "argv": [
                sys.executable,
                "-c",
                "import json, os; print(json.dumps(dict(os.environ), sort_keys=True))",
            ],
            "cwd": str(tmp_path),
            "harness_version": "codex-cli 0.147.0",
            "model_profile": "codex-sol-high",
            "effort": "high",
            "permissions": "read-only",
            "issue": 501,
        },
        corpus_path=CORPUS,
        base_revision=evaluation.BASELINE_SHA,
        guidance_ref="codex-control",
    )

    child = json.loads(cast("str", run["output"]["value"]))
    assert run["child_environment"] == {"state": "captured", "value": child}
    assert child == {
        "CTI_DISPATCH_ID": run["run_id"],
        "CTI_DISPATCH_ISSUE": "501",
        "CTI_DISPATCH_LANE": "codex",
        "CTI_DISPATCH_PROFILE": "codex-sol-high",
        "CTI_DISPATCH_SEAT": "evaluation",
        "HOME": "/safe/home",
        "LANG": "C.UTF-8",
        "OTEL_RESOURCE_ATTRIBUTES": (
            f"cti.dispatch_id={run['run_id']},cti.lane=codex,"
            "cti.profile=codex-sol-high,cti.seat=evaluation,"
            f"cti.issue=501,cti.base_sha={evaluation.BASELINE_SHA}"
        ),
        "PATH": parent_path,
        "TMPDIR": str(tmp_path),
    }


def test_subprocess_file_observation_comes_from_the_child_run(tmp_path: Path) -> None:
    case: Any = evaluation.case_by_id(corpus())["implement-gated-helper"]
    marker = "tests/fixtures/guidance-eval/observed-helper.txt"
    script = (
        "from pathlib import Path; "
        f"p=Path({marker!r}); p.parent.mkdir(parents=True); p.write_text('observed\\n')"
    )

    run: Any = evaluation.run_subprocess_case(
        case,
        {
            "provider": "codex",
            "argv": [sys.executable, "-c", script],
            "cwd": str(tmp_path),
            "harness_version": "codex-cli 0.147.0",
            "model_profile": "codex-sol-high",
            "effort": "high",
            "permissions": "workspace-write",
        },
        corpus_path=CORPUS,
        base_revision=evaluation.BASELINE_SHA,
        guidance_ref="codex-control",
    )

    assert run["observations"]["file_changed"] == {"state": "captured", "value": True}
    assert (tmp_path / marker).read_text(encoding="utf-8") == "observed\n"


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
