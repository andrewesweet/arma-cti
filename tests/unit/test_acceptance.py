"""Executable obligation specifications: linting, execution, and typed outcomes (#592)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import patch

from conftest import load_tool

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    import pytest

acceptance = load_tool("acceptance")

CONTEXT = """## Language

**Commander**: the decision-maker.
**Campaign**: the persistent playthrough.
**Funds**: per-side currency.
"""


def repository(tmp_path: Path) -> Path:
    """Create the smallest checkout the acceptance tool reads."""
    root = tmp_path / "repo"
    (root / "tests" / "specs").mkdir(parents=True)
    (root / "CONTEXT.md").write_text(CONTEXT, encoding="utf-8")
    return root


def write_obligation(
    root: Path,
    key: str,
    feature: str | None,
    **overrides: object,
) -> None:
    """Write one key-addressed obligation record and, where applicable, its feature."""
    record = {
        "binding": "unit",
        "kind": acceptance.BEHAVIOURAL,
        "provisional_terms": [],
        "runner": "python",
        "step_library": "",
    }
    record.update(overrides)
    spec = root / "tests" / "specs"
    (spec / f"{key}.json").write_text(json.dumps(record), encoding="utf-8")
    if feature is not None:
        (spec / f"{key}.feature").write_text(feature, encoding="utf-8")


def feature(*steps: str) -> str:
    """Build a small valid Gherkin feature from step lines."""
    return "Feature: executable obligation\n  Scenario: one\n" + "".join(
        f"    {step}\n" for step in steps
    )


def test_a_standard_gherkin_parser_handles_scenario_outlines_and_angle_parameters(
    tmp_path: Path,
) -> None:
    root = repository(tmp_path)
    source = """Feature: funds are visible
  Scenario Outline: the Commander sees <amount>
    Given the `Commander` has <amount> Funds
    Then ordinary prose can mention an unratified thing

    Examples:
      | amount |
      | 10     |
      | 20     |
"""
    write_obligation(root, "funds-visible", source)

    report = acceptance.lint_obligation(root, "funds-visible")

    assert report.errors == ()
    assert report.document is not None
    assert len(report.steps) == 2


def test_a_feature_without_a_scenario_is_not_executable(tmp_path: Path) -> None:
    root = repository(tmp_path)
    write_obligation(root, "no-scenario", "Feature: only a feature declaration\n")

    report = acceptance.lint_obligation(root, "no-scenario")

    assert [finding.code for finding in report.errors] == ["no_scenarios"]


def test_a_behavioural_record_declares_its_runner_and_binding(tmp_path: Path) -> None:
    root = repository(tmp_path)
    write_obligation(
        root, "undeclared-runner", feature("Given an implementation exists"), runner=""
    )

    report = acceptance.lint_obligation(root, "undeclared-runner")

    assert len(report.errors) == 1
    assert report.errors[0].code == "record_invalid"
    assert "runner must be declared" in report.errors[0].detail


def test_lint_reads_the_language_section_each_time(tmp_path: Path) -> None:
    root = repository(tmp_path)
    write_obligation(root, "new-term", feature("Given a `New Term` exists"))

    before = acceptance.lint_obligation(root, "new-term")
    (root / "CONTEXT.md").write_text(
        CONTEXT + "\n**New Term**: a term added by the human.\n", encoding="utf-8"
    )
    after = acceptance.lint_obligation(root, "new-term")

    assert len(before.errors) == 1
    assert before.errors[0].code == acceptance.UNKNOWN_TERM
    assert after.errors == ()


def test_an_unresolved_marked_term_names_the_term_and_a_remedy(tmp_path: Path) -> None:
    root = repository(tmp_path)
    write_obligation(root, "unknown", feature("Given a `Not A Domain Term` exists"))

    report = acceptance.lint_obligation(root, "unknown")

    assert len(report.errors) == 1
    message = report.errors[0].detail
    assert "Not A Domain Term" in message
    assert "CONTEXT.md" in message
    assert "provisional" in message
    assert "backticks" in message


def test_an_avoided_marked_term_names_the_ratified_replacement(tmp_path: Path) -> None:
    root = repository(tmp_path)
    (root / "CONTEXT.md").write_text(
        CONTEXT + "\n**Campaign**: the persistent playthrough.\n_Avoid_: Game, save\n",
        encoding="utf-8",
    )
    write_obligation(root, "avoided", feature("Given the `Game` is live"))

    report = acceptance.lint_obligation(root, "avoided")

    assert len(report.errors) == 1
    message = report.errors[0].detail
    assert "Game" in message
    assert "Campaign" in message
    assert "Use" in message


def test_unmarked_prose_is_not_vocabulary_checked(tmp_path: Path) -> None:
    root = repository(tmp_path)
    write_obligation(
        root,
        "ordinary-prose",
        feature("Given the ordinary prose names Game and an entirely new thing"),
    )

    report = acceptance.lint_obligation(root, "ordinary-prose")

    assert report.errors == ()


def test_a_provisional_term_is_accepted_and_recorded_by_the_lint(tmp_path: Path) -> None:
    root = repository(tmp_path)
    write_obligation(
        root,
        "provisional",
        feature("Given a `New Term` exists"),
        provisional_terms=[{"term": "New Term", "definition": "a temporary domain term"}],
    )

    report = acceptance.lint_obligation(root, "provisional")

    assert report.errors == ()
    assert tuple(term.term for term in report.provisional) == ("New Term",)
    assert report.unratified == ("New Term",)


def test_the_static_check_refuses_unratified_provisional_terms_until_ratified(
    tmp_path: Path,
) -> None:
    root = repository(tmp_path)
    write_obligation(
        root,
        "provisional",
        feature("Given a `New Term` exists"),
        provisional_terms=[{"term": "New Term", "definition": "a temporary domain term"}],
    )

    refused = acceptance.check(root)
    (root / "CONTEXT.md").write_text(
        CONTEXT + "\n**New Term**: a ratified domain term.\n", encoding="utf-8"
    )
    cleared = acceptance.check(root)

    assert refused.exit_code == 1
    assert "refusal=provisional_unratified" in refused.lines
    assert any("New Term" in line and "ratify" in line for line in refused.lines)
    assert cleared.exit_code == 0
    assert cleared.lines == ("acceptance_specs=ok count=1 provisional=none",)


def test_a_non_behavioural_provisional_term_still_blocks_landing(tmp_path: Path) -> None:
    root = repository(tmp_path)
    write_obligation(
        root,
        "human-judgement",
        None,
        kind=acceptance.NON_BEHAVIOURAL,
        provisional_terms=[{"term": "New Term", "definition": "a temporary domain term"}],
    )

    report = acceptance.check(root)

    assert report.exit_code == 1
    assert "refusal=provisional_unratified" in report.lines


def test_one_key_runs_all_of_its_scenarios(tmp_path: Path) -> None:
    root = repository(tmp_path)
    source = """Feature: two scenarios
  Scenario: first
    Given the `Commander` exists
    Then the `Campaign` is visible

  Scenario: second
    Given the `Commander` exists
    Then the `Campaign` is visible
"""
    write_obligation(root, "two-scenarios", source)
    calls: list[str] = []

    def given(_context: acceptance.ExecutionContext, text: str) -> None:
        calls.append(text)

    def then(_context: acceptance.ExecutionContext, text: str) -> bool:
        calls.append(text)
        return True

    definitions: Mapping[str, object] = {
        "the `Commander` exists": given,
        "the `Campaign` is visible": then,
    }

    result = acceptance.run_obligation(root, "two-scenarios", definitions=definitions)

    assert result.result == acceptance.PASSED
    assert result.scenarios == 2
    assert len(calls) == 4


def test_a_step_that_does_not_satisfy_the_implementation_is_a_failure(tmp_path: Path) -> None:
    root = repository(tmp_path)
    write_obligation(root, "broken", feature("Then the implementation is satisfied"))

    def broken(_context: acceptance.ExecutionContext, _text: str) -> bool:
        return False

    result = acceptance.run_obligation(
        root,
        "broken",
        definitions={"the implementation is satisfied": broken},
    )

    assert result.result == acceptance.FAILURE
    assert result.detail is not None
    assert "implementation is satisfied" in result.detail


def test_a_specification_without_a_bound_step_is_a_typed_non_result(tmp_path: Path) -> None:
    root = repository(tmp_path)
    write_obligation(root, "unbound", feature("Given the implementation is reachable"))

    result = acceptance.run_obligation(root, "unbound", definitions={})

    assert result.result == acceptance.NON_RESULT
    assert result.detail is not None
    assert "step definition" in result.detail


def test_a_specification_lint_error_has_no_executed_scenarios(tmp_path: Path) -> None:
    root = repository(tmp_path)
    write_obligation(root, "invalid", feature("Given a `Not A Domain Term` exists"))

    result = acceptance.run_obligation(root, "invalid", definitions={})

    assert result.result == acceptance.NON_RESULT
    assert result.scenarios == 0


def test_a_missing_specification_is_a_typed_non_result(tmp_path: Path) -> None:
    root = repository(tmp_path)

    result = acceptance.run_obligation(root, "does-not-exist", definitions={})

    assert result.result == acceptance.NON_RESULT
    assert result.detail is not None
    assert "obligation" in result.detail


def test_a_non_behavioural_obligation_is_held_to_review(tmp_path: Path) -> None:
    root = repository(tmp_path)
    write_obligation(
        root,
        "human-judgement",
        None,
        kind=acceptance.NON_BEHAVIOURAL,
    )

    result = acceptance.run_obligation(root, "human-judgement", definitions={})

    assert result.result == acceptance.HELD_TO_REVIEW
    assert result.scenarios == 0
    assert result.detail is not None
    assert "non-behavioural" in result.detail


def test_the_keyed_runner_loads_the_declared_shared_step_library(tmp_path: Path) -> None:
    root = repository(tmp_path)
    (root / "steps.py").write_text(
        "def satisfied(_context, _text):\n"
        "    return True\n\n"
        "STEPS = {'the implementation is satisfied': satisfied}\n",
        encoding="utf-8",
    )
    write_obligation(
        root,
        "keyed-runner",
        feature("Then the implementation is satisfied"),
        step_library="steps.py",
    )

    result = acceptance.run_obligation(root, "keyed-runner")

    assert result.result == acceptance.PASSED
    assert result.scenarios == 1


def test_a_step_library_without_a_loader_is_a_typed_refusal(tmp_path: Path) -> None:
    root = repository(tmp_path)
    (root / "steps.py").write_text("STEPS = {}\n", encoding="utf-8")
    write_obligation(
        root,
        "unloadable",
        feature("Given the implementation is reachable"),
        step_library="steps.py",
    )

    with patch.object(
        acceptance.importlib.util,
        "spec_from_file_location",
        return_value=SimpleNamespace(loader=None),
    ):
        result = acceptance.run_obligation(root, "unloadable")

    assert result.result == acceptance.NON_RESULT
    assert result.detail is not None
    assert "could not be loaded" in result.detail


def test_the_command_renders_a_typed_result_as_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repository(tmp_path)
    write_obligation(root, "human-judgement", None, kind=acceptance.NON_BEHAVIOURAL)

    assert acceptance.main(["run", "human-judgement", "--root", str(root)]) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["obligation_key"] == "human-judgement"
    assert output["result"] == acceptance.HELD_TO_REVIEW


def test_the_command_has_distinct_pass_and_non_result_exit_codes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repository(tmp_path)
    (root / "steps.py").write_text(
        "def satisfied(_context, _text):\n"
        "    return True\n\n"
        "STEPS = {'the implementation is satisfied': satisfied}\n",
        encoding="utf-8",
    )
    write_obligation(
        root,
        "passed",
        feature("Then the implementation is satisfied"),
        step_library="steps.py",
    )

    assert acceptance.main(["run", "passed", "--root", str(root)]) == 0
    assert json.loads(capsys.readouterr().out)["result"] == acceptance.PASSED
    assert acceptance.main(["run", "missing", "--root", str(root)]) == 2
    assert json.loads(capsys.readouterr().out)["result"] == acceptance.NON_RESULT


def test_result_json_omits_absent_detail_but_keeps_failure_detail(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repository(tmp_path)
    (root / "steps.py").write_text(
        "def passed(_context, _text):\n"
        "    return True\n\n"
        "def failed(_context, _text):\n"
        "    return False\n\n"
        "STEPS = {'the implementation passes': passed, 'the implementation fails': failed}\n",
        encoding="utf-8",
    )
    write_obligation(root, "ok", feature("Then the implementation passes"), step_library="steps.py")
    write_obligation(
        root, "broken", feature("Then the implementation fails"), step_library="steps.py"
    )

    assert acceptance.main(["run", "ok", "--root", str(root)]) == 0
    passed = json.loads(capsys.readouterr().out)
    assert acceptance.main(["run", "broken", "--root", str(root)]) == 1
    failed = json.loads(capsys.readouterr().out)

    assert "detail" not in passed
    assert "not satisfied" in failed["detail"]
