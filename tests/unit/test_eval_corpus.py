"""The eval runner is judged on what it does with a corpus, never what a model says.

Every arrangement injects fake task outcomes through a synthetic adapter, so every
case is deterministic and none of these tests can be confused with a claim about a
configuration's quality — the trap #615 names as the whole spec's point.
"""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING

import pytest
from conftest import load_tool

if TYPE_CHECKING:
    from pathlib import Path

eval_corpus = load_tool("eval_corpus")

# A minimal grader: the answer's first token selects the class. Every corpus the tests
# declare uses it, hash-pinned by the builder below.
GRADER_SOURCE = '''"""State the grader contract the runner reads."""


def grade(record):
    """Assign a class from the answer's leading marker."""
    answer = record.get("answer") or ""
    if not isinstance(answer, str):
        return {"class": "unclear", "note": "not_a_string"}
    if answer.startswith("GOOD"):
        return {"class": "expected_cls", "note": "marker"}
    if answer.startswith("BAD"):
        return {"class": "other_cls", "note": "marker"}
    return {"class": "unclear", "note": "no_marker"}
'''


def _grader_sha() -> str:
    """Hash the test grader the way the runner verifies it."""
    return eval_corpus.sha256_bytes(GRADER_SOURCE.encode("utf-8"))


# The runner's own vocabulary, imported for direct assertions.
CASE_PASS = eval_corpus.CaseState.PASS


def _write_task(  # noqa: PLR0913 — a fixture builder with independently varied knobs
    corpus: Path,
    *,
    task_id: str = "t1",
    variants: list[dict[str, object]] | None = None,
    repeats: int = 5,
    tolerance: float = 0.2,
    expected: str = "expected_cls",
    budget: dict[str, object] | None = None,
) -> None:
    """Write one task file into the corpus directory."""
    if variants is None:
        variants = [{"id": "v1", "file": None}]
    document = {
        "schema": eval_corpus.TASK_SCHEMA,
        "id": task_id,
        "provenance": "test fixture",
        "prompt": "Answer GOOD or BAD.",
        "classes": ["expected_cls", "other_cls", "unclear"],
        "expected_class": expected,
        "repeats": repeats,
        "tolerance": tolerance,
        "grader": f"graders/{task_id}.py",
        "grader_sha256": _grader_sha(),
        "variants": variants,
    }
    if budget is not None:
        document["budget"] = budget
    (corpus / f"{task_id}.json").write_text(json.dumps(document), encoding="utf-8")
    graders = corpus.parent / "graders"
    graders.mkdir(parents=True, exist_ok=True)
    (graders / f"{task_id}.py").write_text(GRADER_SOURCE, encoding="utf-8")


def _write_config(  # noqa: PLR0913 — a fixture builder with independently varied knobs
    corpus: Path,
    name: str,
    answer: str,
    *,
    env_marker: str | None = None,
    stopped_by: str | None = None,
    exit_code: int = 0,
    sleep_s: int = 0,
) -> Path:
    """Write a configuration whose synthetic adapter always gives one answer."""
    config_path = corpus.parent / f"config-{name}.json"
    adapter = corpus.parent / f"adapter-{name}.py"
    lines = [
        "import json, os, sys, time",
        "record = {",
        f'    "answer": {answer!r},',
        f'    "stopped_by": {stopped_by or "completed"!r},',
        '    "tokens_in": 11,',
        '    "tokens_out": 7,',
        '    "commands": 3,',
        '    "harness": "synthetic-1.0",',
        '    "env_seen": sorted(os.environ),',
        "}",
    ]
    if sleep_s:
        lines.append(f"time.sleep({sleep_s})")
    if exit_code:
        lines.append(f"sys.exit({exit_code})")
    lines.append(
        "with open('trial.json', 'w', encoding='utf-8') as handle:\n    json.dump(record, handle)"
    )
    adapter.write_text("\n".join(lines), encoding="utf-8")
    document = {
        "schema": eval_corpus.CONFIGURATION_SCHEMA,
        "name": name,
        "harness": {
            "argv": [sys.executable, str(adapter)],
            "env": {env_marker: "1"} if env_marker else {},
        },
    }
    config_path.write_text(json.dumps(document), encoding="utf-8")
    return config_path


def _run(
    tmp_path: Path,
    corpus: Path,
    configs: list[Path],
    *,
    dry_run: bool = False,
) -> tuple[int, Path]:
    """Run the runner over the fixture corpus and return (exit code, runs root)."""
    runs_root = tmp_path / "runs"
    argv = ["--corpus", str(corpus)]
    for config in configs:
        argv += ["--configuration", str(config)]
    if dry_run:
        argv.append("--dry-run")
    argv += ["--runs-root", str(runs_root)]
    exit_code = eval_corpus.main(argv)
    return exit_code, runs_root


def test_passing_corpus_exits_zero(tmp_path: Path) -> None:
    """A corpus whose cases meet their expectation is worst_class=pass, exit 0."""
    corpus = tmp_path / "evals" / "corpus"
    corpus.mkdir(parents=True)
    _write_task(corpus, task_id="t1", repeats=3)
    _write_task(corpus, task_id="t2", repeats=3)
    config = _write_config(corpus, "a", "GOOD answer")
    exit_code, runs_root = _run(tmp_path, corpus, [config])
    assert exit_code == 0
    report = sorted(runs_root.rglob("report.txt"))
    assert len(report) == 1
    body = report[0].read_text(encoding="utf-8")
    assert "worst_class=pass exit=0" in body
    assert "state=pass" in body
    assert "met=3/3" in body
    assert "claim=not_supported" in body  # two cases is far below the claim floor


def test_one_failing_case_sets_the_worst_class(tmp_path: Path) -> None:
    """One case grading outside its tolerance types `fail` and sets the exit."""
    corpus = tmp_path / "evals" / "corpus"
    corpus.mkdir(parents=True)
    _write_task(corpus, repeats=3)
    passing = _write_config(corpus, "a", "GOOD answer")
    failing = _write_config(corpus, "b", "BAD answer")
    exit_code, runs_root = _run(tmp_path, corpus, [passing, failing])
    assert exit_code == 3
    body = (min(runs_root.iterdir()) / "report.txt").read_text(encoding="utf-8")
    assert "worst_class=fail exit=3" in body
    assert "state=fail" in body
    assert "state=pass" in body  # the passing configuration is shown too, never netted


def test_infra_failure_is_never_a_failed_configuration(tmp_path: Path) -> None:
    """An adapter that dies types not-a-result, never `fail`."""
    corpus = tmp_path / "evals" / "corpus"
    corpus.mkdir(parents=True)
    _write_task(corpus, repeats=2)
    broken = _write_config(corpus, "b", "GOOD answer", exit_code=1)
    exit_code, runs_root = _run(tmp_path, corpus, [broken])
    assert exit_code == 4
    body = (min(runs_root.iterdir()) / "report.txt").read_text(encoding="utf-8")
    assert "worst_class=infra_unavailable exit=4" in body
    assert "state=fail" not in body


def test_budget_stop_is_recorded_as_a_budget_stop(tmp_path: Path) -> None:
    """A trial the budget ended is a measurement that did not finish, never a fail."""
    corpus = tmp_path / "evals" / "corpus"
    corpus.mkdir(parents=True)
    _write_task(corpus, repeats=2, budget={"seconds": 600, "tokens": 10, "commands": 200})
    config = _write_config(corpus, "a", "GOOD answer")
    exit_code, runs_root = _run(tmp_path, corpus, [config])
    assert exit_code == 2
    body = (min(runs_root.iterdir()) / "report.txt").read_text(encoding="utf-8")
    assert "worst_class=budget_stopped exit=2" in body
    assert "state=fail" not in body
    assert "budget=tokens" in body


def _usage() -> dict[str, float]:
    """Return an empty usage block, as the runner would total it."""
    return {
        "wall_seconds": 0.0,
        "tokens_in": 0.0,
        "tokens_out": 0.0,
        "commands": 0.0,
        "currency_cost": 0.0,
    }


def test_rate_over_repeats_judged_against_tolerance() -> None:
    """The verdict is the rate over the graded repeats, not any single trial."""
    outcomes = [
        eval_corpus.TrialOutcome("1", "expected_cls", "met"),
        eval_corpus.TrialOutcome("2", "expected_cls", "met"),
        eval_corpus.TrialOutcome("3", "other_cls", "not_met"),
    ]
    result = eval_corpus.aggregate_case("cfg", "t/v", outcomes, "expected_cls", 0.4, _usage())
    assert result.state is eval_corpus.CaseState.PASS
    assert (result.met, result.graded) == (2, 3)
    assert result.under_powered is True


def test_quarantine_beyond_tolerance_with_reproduction_baseline() -> None:
    """A spread beyond tolerance quarantines the case and reports its baseline."""
    outcomes = [
        eval_corpus.TrialOutcome("1", "expected_cls", "met"),
        eval_corpus.TrialOutcome("2", "other_cls", "not_met"),
        eval_corpus.TrialOutcome("3", "unclear", "not_met"),
    ]
    result = eval_corpus.aggregate_case("cfg", "t/v", outcomes, "expected_cls", 0.2, _usage())
    assert result.state is eval_corpus.CaseState.QUARANTINED
    baseline = result.baseline or {}
    assert baseline["run_count"] == 3
    assert baseline["outcomes"] == ["expected_cls", "other_cls", "unclear"]
    assert baseline["disagreement"] == pytest.approx(2 / 3, abs=1e-3)
    assert "tolerance" in baseline
    assert result.graded == 3
    assert result.state is not eval_corpus.CaseState.FAIL


def test_power_statement_is_derived_from_the_case_count() -> None:
    """The quoted corpus statistics come from the formula, never from prose."""
    assert eval_corpus.half_width(20) == pytest.approx(0.1753, abs=5e-4)
    assert eval_corpus.half_width(50) == pytest.approx(0.1109, abs=5e-4)
    assert eval_corpus.half_width(50) == pytest.approx(0.1109, abs=5e-4)
    assert eval_corpus.zero_failure_upper_bound(20) == pytest.approx(0.15, abs=1e-9)
    lines = eval_corpus.power_statement(1, min_cases_for_claim=20)
    rendered = "\n".join(lines)
    assert "claim=not_supported" in rendered
    assert "too few independent tasks" in rendered


def test_pairwise_comparison_shows_both_sides_never_netted(tmp_path: Path) -> None:
    """A change that fixes one case and breaks another shows both, named."""
    corpus = tmp_path / "evals" / "corpus"
    corpus.mkdir(parents=True)
    _write_task(corpus, task_id="t1", repeats=2)
    _write_task(corpus, task_id="t2", repeats=2)
    incumbent = _write_config(corpus, "incumbent", "GOOD answer")
    candidate = _write_config(corpus, "candidate", "BAD answer")
    exit_code, runs_root = _run(tmp_path, corpus, [incumbent, candidate])
    assert exit_code == 3
    body = (min(runs_root.iterdir()) / "report.txt").read_text(encoding="utf-8")
    assert "comparison=task_by_task netted=no" in body
    assert "pair=t1/v1 incumbent=pass candidate=fail divergent=yes" in body
    pair_t2 = [line for line in body.splitlines() if line.startswith("pair=t2/v1 ")]
    assert len(pair_t2) == 1
    assert "divergent=yes" in pair_t2[0]
    assert body.count("pair=") == 2
    assert "divergent_cases=2" in body


def test_grader_hash_mismatch_refuses_before_any_trial(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A moved oracle is a refusal before the run is trusted at all."""
    corpus = tmp_path / "evals" / "corpus"
    corpus.mkdir(parents=True)
    _write_task(corpus, repeats=1)
    config = _write_config(corpus, "a", "GOOD answer")
    grader = corpus.parent / "graders" / "t1.py"
    grader.write_text(GRADER_SOURCE + "# tampered\n", encoding="utf-8")
    exit_code, runs_root = _run(tmp_path, corpus, [config])
    assert exit_code == 6
    err = capsys.readouterr().err
    assert "grader_hash_mismatch" in err
    assert (
        not runs_root.exists() or [p.name for p in runs_root.iterdir() if p.name != "graders"] == []
    )


def test_child_environment_is_allowlisted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No lane variable, credential or dispatch identity reaches the harness child."""
    monkeypatch.setenv("CTI_DISPATCH_ID", "dispatch-123")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://example.invalid")
    corpus = tmp_path / "evals" / "corpus"
    corpus.mkdir(parents=True)
    _write_task(corpus, repeats=1)
    config = _write_config(corpus, "a", "GOOD answer", env_marker="CTI_EVAL_MARKER")
    exit_code, runs_root = _run(tmp_path, corpus, [config])
    assert exit_code == 0
    record = json.loads(min(runs_root.rglob("record.json")).read_text(encoding="utf-8"))
    env_seen = record["env_seen"]
    assert "CTI_EVAL_MARKER" in env_seen  # the configuration's declared extra arrived
    assert "CTI_DISPATCH_ID" not in env_seen
    assert not [name for name in env_seen if name.startswith("ANTHROPIC")]
    allowed = set(eval_corpus.CHILD_ENV_ALLOWLIST) | {"CTI_EVAL_MARKER"}
    assert set(env_seen) <= allowed


def test_dry_run_prints_the_plan_and_runs_nothing(tmp_path: Path) -> None:
    """--dry-run names every case and creates no run directory."""
    corpus = tmp_path / "evals" / "corpus"
    corpus.mkdir(parents=True)
    _write_task(corpus, repeats=2)
    config = _write_config(corpus, "a", "GOOD answer")
    exit_code, runs_root = _run(tmp_path, corpus, [config], dry_run=True)
    assert exit_code == 0
    assert [p.name for p in runs_root.iterdir() if p.name != "graders"] == []


def test_every_trial_retains_its_artefacts_and_nothing_is_overwritten(tmp_path: Path) -> None:
    """Two runs keep separate directories; each trial keeps workspace and outcomes."""
    corpus = tmp_path / "evals" / "corpus"
    corpus.mkdir(parents=True)
    _write_task(corpus, repeats=2)
    config = _write_config(corpus, "a", "GOOD answer")
    _first_exit, runs_root = _run(tmp_path, corpus, [config])
    _second_exit, runs_root = _run(tmp_path, corpus, [config])
    run_dirs = sorted(p for p in runs_root.iterdir() if p.name != "graders")
    assert len(run_dirs) == 2
    for run_dir in run_dirs:
        records = list(run_dir.rglob("record.json"))
        assert len(records) == 2
        for record_path in records:
            trial_dir = record_path.parent
            assert (trial_dir / "outcome.json").is_file()
            assert (trial_dir / "workspace" / "task.txt").is_file()
            assert (trial_dir / "workspace" / "trial.json").is_file()
            assert (trial_dir / "harness-stdout.txt").exists()


def test_time_budget_exhaustion_types_a_budget_stop(tmp_path: Path) -> None:
    """A trial still running when its time budget closes is a budget stop."""
    corpus = tmp_path / "evals" / "corpus"
    corpus.mkdir(parents=True)
    _write_task(corpus, repeats=1, budget={"seconds": 2, "tokens": 250000, "commands": 200})
    config = _write_config(corpus, "a", "GOOD answer", sleep_s=30)
    exit_code, runs_root = _run(tmp_path, corpus, [config])
    assert exit_code == 2
    body = (min(runs_root.iterdir()) / "report.txt").read_text(encoding="utf-8")
    assert "worst_class=budget_stopped exit=2" in body
