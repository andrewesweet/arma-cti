"""The mutation smoke: what it plants, what it refuses to plant, and what it reds on.

Two halves. The first is the mutator itself, which is pure — source in, mutants
out — and is where the operator set's precision is held: the literals it must
never touch are named here as regressions, because every one of them that
survives in the real tree has to be paid for by lowering the floor (#239, and
mutmut's three equivalent mutants on `dedupe.py` that started it).

The second half is two end-to-end runs against a throwaway repo built in
`tmp_path`: a sound test module clears the floor, and a vacuous one — the
`assert True` shape #239's acceptance names — does not. Those two are the gate's
own acceptance, run every time `just unit` runs, rather than a demonstration
quoted once in a closing comment.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import time
from typing import TYPE_CHECKING, Any, cast

import pytest
from conftest import load_tool

if TYPE_CHECKING:
    from pathlib import Path
    from types import ModuleType

# The two arms first: `tools/` holds scripts rather than a package, so
# `mutation_smoke`'s sibling imports resolve only once `load_tool` has registered
# them in `sys.modules` (the `timeline` / `telemetry_log` pattern `load_tool`
# documents).
load_tool("mutation_shell")
load_tool("mutation_rust")
smoke_tool: ModuleType = load_tool("mutation_smoke")


def _plant(source: str, *, lines: set[int] | None = None) -> list[Any]:
    text = textwrap.dedent(source).strip() + "\n"
    reached = frozenset(lines) if lines else frozenset(range(1, text.count("\n") + 2))
    return smoke_tool.plant(text, path="src/subject.py", lines=reached)


def _operators(source: str, *, lines: set[int] | None = None) -> list[str]:
    return [mutant.operator for mutant in _plant(source, lines=lines)]


def _afters(source: str, *, lines: set[int] | None = None) -> list[str]:
    return [mutant.after for mutant in _plant(source, lines=lines)]


# --- what the mutator plants ------------------------------------------------


@pytest.mark.parametrize(
    ("expression", "flipped"),
    [
        ("a == b", "(a != b)"),
        ("a != b", "(a == b)"),
        ("a < b", "(a >= b)"),
        ("a <= b", "(a > b)"),
        ("a > b", "(a <= b)"),
        ("a >= b", "(a < b)"),
        ("a is b", "(a is not b)"),
        ("a is not b", "(a is b)"),
        ("a in b", "(a not in b)"),
        ("a not in b", "(a in b)"),
    ],
)
def test_every_comparison_is_flipped_to_its_negation(expression: str, flipped: str) -> None:
    assert flipped in _afters(f"def f(a, b):\n    while {expression}:\n        pass\n")


@pytest.mark.parametrize(
    ("expression", "shifted"),
    [
        ("a < b", "(a <= b)"),
        ("a <= b", "(a < b)"),
        ("a > b", "(a >= b)"),
        ("a >= b", "(a > b)"),
    ],
)
def test_an_ordering_comparison_is_also_shifted_by_one(expression: str, shifted: str) -> None:
    # The boundary mutant is the one a suite asserting `is not None` reaches
    # over: a negated `>` usually blows the code up and any red suite kills it.
    assert shifted in _afters(f"def f(a, b):\n    while {expression}:\n        pass\n")


@pytest.mark.parametrize("expression", ["a == b", "a != b", "a is b", "a in b"])
def test_an_equality_has_no_boundary_to_shift(expression: str) -> None:
    assert _operators(f"def f(a, b):\n    while {expression}:\n        pass\n") == ["compare"]


def test_a_chained_comparison_is_left_alone() -> None:
    # One link of a chain is a mutant whose meaning cannot be stated in a report.
    assert "compare" not in _operators("def f(a, b, c):\n    while a < b < c:\n        pass\n")


def test_and_becomes_or_and_or_becomes_and() -> None:
    assert "(a or b)" in _afters("def f(a, b):\n    while a and b:\n        pass\n")
    assert "(a and b)" in _afters("def f(a, b):\n    while a or b:\n        pass\n")


def test_a_boolean_op_of_three_terms_keeps_all_three() -> None:
    assert "(a or b or c)" in _afters("def f(a, b, c):\n    while a and b and c:\n        pass\n")


def test_a_negation_is_dropped() -> None:
    assert "(a)" in _afters("def f(a):\n    while not a:\n        pass\n")


def test_a_boolean_constant_is_flipped() -> None:
    assert _afters("def f():\n    return True\n") == ["False", "None"]


def test_a_number_is_offset_by_one() -> None:
    assert "9" in _afters("def f(a):\n    return a * 8\n")


def test_a_return_value_becomes_none() -> None:
    mutants = _plant("def f(a):\n    return a.total()\n")
    assert [(mutant.operator, mutant.before, mutant.after) for mutant in mutants] == [
        ("return", "a.total()", "None"),
    ]


def test_a_function_that_already_returns_nothing_has_no_return_mutant() -> None:
    assert "return" not in _operators("def f(a):\n    if a:\n        return\n    return None\n")


# --- what it deliberately refuses to plant ----------------------------------


def test_a_string_literal_is_never_touched() -> None:
    # mutmut's `"utf-8"` -> `"UTF-8"` on dedupe.py: unkillable, and it would have
    # to be paid for out of the floor.
    assert _operators('def f(x):\n    return x.encode("utf-8")\n') == ["return"]


def test_a_keyword_argument_value_is_never_touched() -> None:
    # mutmut's `digest_size=16` -> `17`, the same lesson in a number.
    assert _operators("def f(x):\n    return blake2b(x, digest_size=16)\n") == ["return"]


def test_a_parameter_default_is_never_touched() -> None:
    assert _operators("def f(x, window=64):\n    return x\n") == ["return"]


def test_nothing_inside_an_f_string_is_touched() -> None:
    # The comparison in the format expression is left alone; the plain `return`
    # on the next line is not, so this is the freeze and not an empty walk.
    assert _operators('def f(x):\n    y = f"{x == 1}"\n    return y\n') == ["return"]


def test_only_covered_lines_are_planted() -> None:
    source = "def f(a, b):\n    if a == b:\n        return 1\n    return 2\n"
    assert [mutant.line for mutant in _plant(source, lines={2})] == [2]
    # Line 3 is `return 1`, which offers two: the literal and the return value.
    assert [mutant.line for mutant in _plant(source, lines={3})] == [3, 3]


def test_planting_is_deterministic() -> None:
    source = "def f(a, b):\n    if a == b and not b:\n        return a + 1\n    return 0\n"
    assert _plant(source) == _plant(source)


# --- grafting ---------------------------------------------------------------


def test_a_mutant_is_grafted_at_its_own_span() -> None:
    source = "def f(a, b):\n    if a == b:\n        return 1\n    return 2\n"
    mutant = next(m for m in _plant(source) if m.operator == "compare")
    assert smoke_tool.graft(source, mutant) == (
        "def f(a, b):\n    if (a != b):\n        return 1\n    return 2\n"
    )


def test_a_span_is_measured_in_bytes_not_characters() -> None:
    # `ast` reports columns in UTF-8 bytes. A non-ASCII character before the
    # mutation site cuts the file in the wrong place if that is missed.
    source = 'MARK = "×××"\n\n\ndef f(a, b):\n    if a == b:\n        return 1\n    return 2\n'
    mutant = next(m for m in _plant(source) if m.operator == "compare")
    assert mutant.before == "a == b"
    assert "if (a != b):" in (smoke_tool.graft(source, mutant) or "")


def test_a_mutant_that_will_not_compile_is_dropped() -> None:
    source = "def f(a):\n    return a\n"
    mutant = _plant(source)[0]._replace(after="return return")
    assert smoke_tool.graft(source, mutant) is None


# --- the bounded sample -----------------------------------------------------


def test_a_sample_under_the_cap_is_everything() -> None:
    mutants = _plant("def f(a, b):\n    if a == b:\n        return 1\n    return 2\n")
    assert smoke_tool.sample(mutants, seed="x", cap=99) == mutants


def test_a_sample_is_capped_and_reproducible() -> None:
    mutants = _plant("def f(a, b, c):\n" + "".join(f"    x{i} = a == b\n" for i in range(30)))
    first = smoke_tool.sample(mutants, seed="tests/unit/test_x.py", cap=5)
    again = smoke_tool.sample(mutants, seed="tests/unit/test_x.py", cap=5)
    assert len(first) == 5
    assert first == again
    assert first == sorted(first)


def test_a_different_module_draws_a_different_sample() -> None:
    mutants = _plant("def f(a, b, c):\n" + "".join(f"    x{i} = a == b\n" for i in range(30)))
    assert smoke_tool.sample(mutants, seed="tests/unit/test_a.py", cap=5) != smoke_tool.sample(
        mutants,
        seed="tests/unit/test_b.py",
        cap=5,
    )


# --- reading what the tests reached -----------------------------------------


def _report(files: dict[str, dict[str, list[str]]]) -> dict[str, object]:
    return {"files": {path: {"contexts": contexts} for path, contexts in files.items()}}


def test_import_time_lines_do_not_count_as_reached() -> None:
    # An empty context is "something imported this", which is how an assert-true
    # module would otherwise acquire a subject it never exercised.
    reach = smoke_tool.read_reach(_report({"src/a.py": {"3": [""], "4": ["tests/t.py::t|run"]}}))
    assert reach.lines == {"src/a.py": {4: ("tests/t.py::t",)}}


def test_code_outside_this_repos_source_is_never_a_subject() -> None:
    reach = smoke_tool.read_reach(
        _report({".venv/lib/x.py": {"1": ["t|run"]}, "tests/unit/t.py": {"1": ["t|run"]}}),
    )
    assert reach.subject() is None


def test_the_subject_is_the_file_the_tests_tell_apart() -> None:
    # `tools/big.py` has more lines, but all three of them are reached by every
    # test — that is arrangement, not subject.
    reach = smoke_tool.read_reach(
        _report(
            {
                "src/small.py": {"1": ["a"], "2": ["b"]},
                "tools/big.py": {"1": ["a", "b"], "2": ["a", "b"], "3": ["a", "b"]},
            },
        ),
    )
    assert reach.subject() == "src/small.py"


def test_a_file_named_after_the_test_module_is_the_subject() -> None:
    reach = smoke_tool.read_reach(
        _report(
            {
                "src/cti_daemon/budget.py": {"1": ["a"]},
                "src/cti_daemon/manifest.py": {"1": ["a"], "2": ["b"], "3": ["c"]},
            },
        ),
    )
    assert reach.subject("tests/unit/test_budget.py") == "src/cti_daemon/budget.py"


def test_a_qualified_test_module_falls_back_to_the_module_it_qualifies() -> None:
    # `test_daemon_casualties.py` is about `daemon.py`; this repo writes that
    # shape a dozen times. Reading the name that way rather than by discrimination
    # moved the module from 40% to 67% and from 30.8 s to 8.9 s.
    reach = smoke_tool.read_reach(
        _report(
            {
                "src/cti_daemon/daemon.py": {"1": ["a"]},
                "src/cti_daemon/campaign.py": {"1": ["a"], "2": ["b"], "3": ["c"]},
            },
        ),
    )
    assert reach.subject("tests/unit/test_daemon_casualties.py") == "src/cti_daemon/daemon.py"


def test_the_longest_name_that_matches_wins() -> None:
    reach = smoke_tool.read_reach(
        _report(
            {
                "src/cti_daemon/daemon.py": {"1": ["a"]},
                "src/cti_daemon/report_cycle.py": {"1": ["a"]},
            },
        ),
    )
    assert reach.subject("tests/unit/test_report_cycle.py") == "src/cti_daemon/report_cycle.py"


def test_the_name_cannot_point_at_code_no_test_executed() -> None:
    # The convention is a tie-break among files the tests reached, never a way to
    # nominate a file nothing ran.
    reach = smoke_tool.read_reach(_report({"src/cti_daemon/manifest.py": {"1": ["a"]}}))
    assert reach.subject("tests/unit/test_budget.py") == "src/cti_daemon/manifest.py"


def test_lines_every_test_reaches_are_worth_nothing() -> None:
    reach = smoke_tool.read_reach(_report({"src/a.py": {"1": ["x", "y"], "2": ["x"]}}))
    assert reach.tests() == frozenset({"x", "y"})
    assert reach.discrimination("src/a.py") == 0.5


def test_durations_are_summed_over_a_tests_three_phases() -> None:
    costs = smoke_tool.read_durations(
        "0.50s call     tests/unit/test_x.py::test_a\n"
        "0.25s setup    tests/unit/test_x.py::test_a\n"
        "0.01s teardown tests/unit/test_x.py::test_a\n"
        "============= 1 passed =============\n"
        "0.10s call     tests/unit/test_x.py::test_b\n",
    )
    assert costs == pytest.approx(
        {"tests/unit/test_x.py::test_a": 0.76, "tests/unit/test_x.py::test_b": 0.10},
        abs=0.01,
    )


# --- coverage names are not pytest node ids ---------------------------------


@pytest.mark.parametrize(
    ("context", "node"),
    [
        ("test_dedupe.test_a_window_can_be_filled", "test_a_window_can_be_filled"),
        ("test_dedupe.Suite.test_a_method", "Suite::test_a_method"),
    ],
)
def test_a_coverage_context_becomes_the_node_id_that_selects_that_test(
    context: str,
    node: str,
) -> None:
    # The bug this catches scored every module in the repo 100%: handed the
    # coverage spelling, pytest exits 4 with "file or directory not found", and a
    # runner reading any non-zero exit as a kill reads that as the tests noticing.
    assert (
        smoke_tool.node_id("tests/unit/test_dedupe.py", context)
        == f"tests/unit/test_dedupe.py::{node}"
    )


@pytest.mark.parametrize(
    "context",
    [
        # coverage's `test_function` context names *any* function so called, and
        # hypothesis has one; every module using hypothesis recorded this.
        "hypothesis.internal.conjecture.engine.ConjectureRunner.test_function",
        "conftest.reply_to",
        "test_a_window_can_be_filled",
    ],
)
def test_a_context_that_is_not_a_test_of_this_module_has_no_node_id(context: str) -> None:
    assert smoke_tool.node_id("tests/unit/test_dedupe.py", context) is None


def test_a_parametrised_tests_cases_are_summed_into_its_cost() -> None:
    reach = smoke_tool.read_reach(
        {},
        {"tests/unit/t.py::test_a[one]": 1.0, "tests/unit/t.py::test_a[two]": 2.0},
    )
    assert reach.cost("tests/unit/t.py::test_a") == 3.0


def test_the_cheapest_tests_reaching_a_line_are_the_ones_run() -> None:
    # #197's 60 s soak must never be chosen while a cheap test reaches the same line.
    reach = smoke_tool.read_reach({}, {"slow": 60.0, "quick": 0.01, "middling": 1.0})
    assert reach.cheapest(("slow", "middling", "quick")) == ["quick", "middling"]


def test_the_selection_takes_every_test_under_the_per_test_ceiling() -> None:
    # The bound is on the single test, not the cumulative wall clock (#435): six
    # tests at 3.0s each are all members — the cumulative cut this replaced would
    # have kept two, and which two moved with measured jitter the grain does not
    # remove. Membership, not order, is what a verdict is a function of.
    reach = smoke_tool.read_reach({}, {f"t{i}": 3.0 for i in range(6)})
    assert reach.cheapest(tuple(f"t{i}" for i in range(6))) == [f"t{i}" for i in range(6)]


def test_a_line_reached_only_over_the_ceiling_keeps_its_single_cheapest_test() -> None:
    reach = smoke_tool.read_reach({}, {"dear": 12.0, "dearest": 20.0})
    assert reach.cheapest(("dear", "dearest")) == ["dear"]


def test_selection_membership_survives_cost_jitter_the_grain_does_not_remove() -> None:
    # #435's measured shape: two fresh measurements of one unchanged module had
    # 33 of 65 costs move a grain or more, and the cumulative cut selected
    # different tests for 532 of 874 lines. Under the per-test ceiling the same
    # jitter moves only the run order, never the membership.
    before = smoke_tool.read_reach({}, {"a": 0.71, "b": 0.48, "c": 0.5, "d": 0.63})
    after = smoke_tool.read_reach({}, {"a": 0.52, "b": 0.5, "c": 0.68, "d": 0.5})
    tests = ("a", "b", "c", "d")
    assert set(before.cheapest(tests)) == set(after.cheapest(tests)) == set(tests)


def test_an_unmeasured_test_is_assumed_free_rather_than_expensive() -> None:
    reach = smoke_tool.read_reach({}, {"known": 1.0})
    assert reach.cheapest(("known", "unknown")) == ["unknown", "known"]


def test_an_empty_reaching_set_selects_no_tests_rather_than_raising() -> None:
    # The over-ceiling fallback's `min(tests, ...)` raised ValueError on an
    # empty reaching set where the selection used to return empty and
    # `_tally`'s guard skipped the mutant (#435 round 2). Unreachable via
    # `_selected` today, but the contract is the method's, not the caller's.
    assert smoke_tool.read_reach({}, {}).cheapest(()) == []


def test_a_mutants_timeout_is_derived_from_what_its_tests_cost_unmutated() -> None:
    reach = smoke_tool.read_reach({}, {"slow": 30.0})
    assert reach.timeout(["slow"]) == 120.0
    assert reach.timeout([]) == smoke_tool.TIMEOUT_FLOOR_S


def _fake_pytest(
    monkeypatch: pytest.MonkeyPatch,
    *,
    judged: subprocess.CompletedProcess[str] | subprocess.TimeoutExpired,
    collect: subprocess.CompletedProcess[str] | subprocess.TimeoutExpired,
) -> list[list[str]]:
    """Stand in for both subprocesses `_pytest` can start, and record their argv.

    The judged run and the `--collect-only` question are told apart by their
    argv, the same distinction the real code makes; the returned list collects
    every argv for assertions that the right question was asked of the right
    process.
    """
    argvs: list[list[str]] = []

    def run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        argvs.append([str(part) for part in argv])
        outcome = collect if "--collect-only" in argv else judged
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(smoke_tool.subprocess, "run", run)
    return argvs


def test_a_module_that_stops_collecting_under_the_mutant_scores_as_a_kill(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # #338's shape: a mutant that makes a module-level call raise turns the
    # node-id run into an exit 4 — the same code as a usage error — and the
    # collect-only question is what tells them apart.
    argvs = _fake_pytest(
        monkeypatch,
        judged=subprocess.CompletedProcess([], 4, stdout="", stderr=""),
        collect=subprocess.CompletedProcess([], 2, stdout="", stderr=""),
    )
    assert (
        smoke_tool._pytest(  # noqa: SLF001 — the discriminator is the subject
            tmp_path,
            [],
            timeout=1.0,
            mutant=True,
            test_module="tests/unit/test_subject.py",
        )
        == smoke_tool.PYTEST_FAILED
    )
    assert any("--collect-only" in argv for argv in argvs)


def test_a_collection_banner_quoted_from_a_run_that_is_not_this_one_does_not_score_a_kill(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The compound arrangement #424 names: this repo runs pytest inside pytest,
    # and the captured output a failing test leaves behind can quote a
    # collection banner naming the very module under mutation — a stream token
    # the old discriminator matched, right for the wrong reason whenever it
    # agreed. The verdict must come from the collect-only question instead:
    # the module collects, so the odd exit code stands and refuses upstream.
    quoted = (
        "=================================== FAILURES ===================================\n"
        "______ test_inner ______________________________________________________________\n"
        "E   AssertionError: \n"
        "E   =========================== ERRORS ====================================\n"
        "E   ______________ ERROR collecting tests/unit/test_subject.py ______________\n"
        "E   ImportError while importing test module 'tests/unit/test_subject.py'\n"
    )
    _fake_pytest(
        monkeypatch,
        judged=subprocess.CompletedProcess([], 3, stdout=quoted, stderr=""),
        collect=subprocess.CompletedProcess([], 0, stdout="", stderr=""),
    )
    assert (
        smoke_tool._pytest(  # noqa: SLF001 — the discriminator is the subject
            tmp_path,
            [],
            timeout=1.0,
            mutant=True,
            test_module="tests/unit/test_subject.py",
        )
        == 3
    )


def test_a_collect_only_question_that_cannot_be_answered_refuses_rather_than_scores(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_pytest(
        monkeypatch,
        judged=subprocess.CompletedProcess([], 4, stdout="", stderr=""),
        collect=subprocess.TimeoutExpired(cmd="pytest", timeout=1.0),
    )
    assert (
        smoke_tool._pytest(  # noqa: SLF001 — the refusal branch is the subject
            tmp_path,
            [],
            timeout=1.0,
            mutant=True,
            test_module="tests/unit/test_subject.py",
        )
        == 4
    )


def test_pytests_own_codes_for_a_collection_error_are_what_the_gate_reads(
    tmp_path: Path,
) -> None:
    # The anchor (#424): the kill path reads exit codes, not output tokens, so
    # the suite pins what this pytest actually exits — a collection error under
    # node-id selection is 4, the ambiguous code the discriminator exists to
    # resolve, and the bare-path `--collect-only` question is 2. If a pytest
    # upgrade moves either number, this reds before the gate goes quietly blind
    # or quietly generous. The banner is asserted only to document the stream
    # shape the gate deliberately does not parse.
    module = tmp_path / "tests" / "unit" / "test_subject.py"
    module.parent.mkdir(parents=True)
    module.write_text("import module_that_does_not_exist_for_this_fixture\n")
    common = ["-n0", "-q", "-p", "no:cacheprovider", "--no-header"]
    judged = subprocess.run(  # noqa: S603 - argv built here from constants
        [sys.executable, "-m", "pytest", *common, "tests/unit/test_subject.py::test_any"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert judged.returncode == 4
    assert "ERROR collecting" in judged.stdout
    asked = subprocess.run(  # noqa: S603 - argv built here from constants
        [sys.executable, "-m", "pytest", *common, "--collect-only", "tests/unit/test_subject.py"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert asked.returncode == 2


def test_every_spawned_judge_runs_under_one_pinned_hash_seed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # #435: unpinned, each of a module's twenty mutant runs picks its own hash
    # seed, and a subject whose behaviour depends on set or dict iteration order
    # is a coin toss across them. The pin reaches the subprocess by environment
    # only — the gate's own process is left alone.
    environments: list[dict[str, str]] = []

    def run(_argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        environments.append(cast("dict[str, str]", kwargs.get("env")))
        return subprocess.CompletedProcess([], 0, stdout="", stderr="")

    monkeypatch.setattr(smoke_tool.subprocess, "run", run)
    assert (
        smoke_tool._pytest(  # noqa: SLF001 — the spawned environment is the subject
            tmp_path,
            [],
            timeout=1.0,
            test_module="tests/unit/test_subject.py",
        )
        == 0
    )
    assert environments[0]["PYTHONHASHSEED"] == smoke_tool.HASH_SEED
    assert environments[0] is not os.environ


def test_a_pytest_usage_error_refuses_instead_of_counting_as_a_kill() -> None:
    mutant = _plant("def f(a):\n    return a == 1\n")[0]
    node = "tests/unit/test_subject.py::test_missing"
    reach = smoke_tool.Reach({}, {node: 0.0})
    with pytest.raises(smoke_tool.Refusal, match=r"pytest exited 4.*not a verdict"):
        smoke_tool._tally(  # noqa: SLF001 — the refusal branch is the subject
            [mutant],
            reach,
            {mutant.line: (node,)},
            float("inf"),
            lambda _mutant, _tests: 4,
        )


def _two_mutants_on_distinct_lines() -> tuple[Any, Any]:
    """Two planted mutants the covered map can hand different selections."""
    planted = _plant("def f(a):\n    if a == 1:\n        return a > 2\n    return a != 3\n")
    first = planted[0]
    second = next(mutant for mutant in planted if mutant.line != first.line)
    return first, second


def test_a_sample_the_budget_cuts_short_refuses_rather_than_moving_the_denominator() -> None:
    # #435 round 2: with the per-test ceiling replacing the cumulative cut,
    # BUDGET_S became the only cumulative bound, and a deadline that fired
    # mid-sample printed `ok` on a denominator the clock chose — 16/19 at 84%
    # where a full run reads 16/20 at 80%, releasing the ratchet by
    # `row.run != run` and exiting 0. A cut sample is not a result on a smaller
    # denominator; it is no result at all, which is a refusal.
    first, second = _two_mutants_on_distinct_lines()
    node = "tests/unit/test_subject.py::test_any"
    reach = smoke_tool.Reach({}, {node: 0.0})
    with pytest.raises(smoke_tool.Refusal, match=r"budget ran out after 1 of 2"):
        smoke_tool._tally(  # noqa: SLF001 — the refusal branch is the subject
            [first, second],
            reach,
            {first.line: (node,), second.line: (node,)},
            time.monotonic() - 1.0,
            lambda _mutant, _tests: smoke_tool.PYTEST_FAILED,
        )


def test_a_sample_that_runs_to_completion_inside_its_budget_is_no_refusal() -> None:
    first, second = _two_mutants_on_distinct_lines()
    node = "tests/unit/test_subject.py::test_any"
    reach = smoke_tool.Reach({}, {node: 0.0})
    tally = smoke_tool._tally(  # noqa: SLF001 — the happy path is the subject
        [first, second],
        reach,
        {first.line: (node,), second.line: (node,)},
        time.monotonic() + 60.0,
        lambda _mutant, _tests: smoke_tool.PYTEST_FAILED,
    )
    assert (tally.run, tally.killed, tally.survivors) == (2, 2, ())


# --- the verdict ------------------------------------------------------------


# ANN401: a `tools/` script is loaded by path, so its `Verdict` is not a type an
# annotation here can name (the same reasoning as tests/unit/test_land.py).
def _verdict(**overrides: object) -> Any:  # noqa: ANN401
    fields: dict[str, object] = {
        "test_module": "tests/unit/test_x.py",
        "subject": "src/x.py",
        "planted": 30,
        "run": 20,
        "killed": 20,
        "survivors": (),
        "seconds": 4.0,
        "floor": 0.75,
    }
    return smoke_tool.Verdict(**{**fields, **overrides})


def test_a_module_at_the_floor_passes_and_one_below_it_does_not() -> None:
    assert _verdict(killed=15).ok
    assert not _verdict(killed=14).ok


def test_a_module_with_no_subject_is_red_and_says_why() -> None:
    verdict = _verdict(subject=None, planted=0, run=0, killed=0)
    assert not verdict.ok
    assert "no subject" in verdict.reason


def test_a_module_that_reached_no_verdict_is_red_rather_than_a_pass_by_default() -> None:
    verdict = _verdict(run=0, killed=0)
    assert not verdict.ok
    assert "no mutant reached a verdict" in verdict.reason


def test_a_subject_with_no_decision_on_the_reached_lines_is_not_a_red() -> None:
    # `src/cti_daemon/telemetry.py`: no comparison, no boolean, no bare number on
    # any line its tests execute. A module cannot reach this by asserting less.
    verdict = _verdict(planted=0, run=0, killed=0)
    assert verdict.ok
    assert "nothing to plant" in verdict.reason


def test_a_module_with_no_subject_is_still_red_when_it_planted_nothing() -> None:
    assert not _verdict(subject=None, planted=0, run=0, killed=0).ok


def test_a_red_verdict_names_the_subject_and_the_arithmetic() -> None:
    reason = _verdict(killed=10).reason
    assert "src/x.py" in reason
    assert "10/20" in reason
    assert "75%" in reason


# --- the per-module ratchet (#244) ------------------------------------------


# A recorded rate of 18/20, the working example for the assertions below.
_RECORDED = smoke_tool.Row("src/x.py", "deadbeef", 18, 20)


def test_the_ratchet_floor_takes_one_kill_of_slack_off_the_recorded_rate() -> None:
    # 18/20 recorded, SLACK 1: the floor a module must re-clear is 17/20 = 85%,
    # not 18/20. Losing one kill to the ratchet is allowed; losing two is not.
    assert (
        smoke_tool.ratchet_floor(
            {"tests/unit/test_x.py": _RECORDED},
            "tests/unit/test_x.py",
            "src/x.py",
            "deadbeef",
            20,
        )
        == (18 - smoke_tool.SLACK) / 20
    )


@pytest.mark.parametrize(
    ("subject", "sha", "run"),
    [
        ("src/x.py", "different", 20),  # the subject's bytes changed
        ("src/other.py", "deadbeef", 20),  # the test now exercises a different file
        ("src/x.py", "deadbeef", 15),  # the budget cut this run short
    ],
)
def test_the_ratchet_releases_to_the_global_floor_when_the_pair_is_not_the_recorded_one(
    subject: str,
    sha: str,
    run: int,
) -> None:
    # None means "use FLOOR": the recorded rate is about a (test module, subject)
    # pair, and the moment that pair is not the one in front of the gate the
    # ratchet lets go rather than redding a tree its number no longer describes.
    assert (
        smoke_tool.ratchet_floor(
            {"tests/unit/test_x.py": _RECORDED},
            "tests/unit/test_x.py",
            subject,
            sha,
            run,
        )
        is None
    )


def test_a_module_with_no_recorded_rate_meets_the_global_floor() -> None:
    assert smoke_tool.ratchet_floor({}, "tests/unit/test_x.py", "src/x.py", "deadbeef", 20) is None


def test_the_ratchet_reds_only_after_two_lost_kills() -> None:
    # The same comparison the gate makes, via Verdict.ok: at the ratchet floor,
    # losing one kill (within slack) passes and losing two reds.
    floor = (18 - smoke_tool.SLACK) / 20
    assert _verdict(killed=18 - smoke_tool.SLACK, run=20, floor=floor, ratcheted=True).ok
    assert not _verdict(killed=18 - smoke_tool.SLACK - 1, run=20, floor=floor, ratcheted=True).ok


def test_a_ratcheted_verdict_marks_its_floor_so_a_reader_can_tell_it_apart() -> None:
    floor = (18 - smoke_tool.SLACK) / 20
    assert "(ratchet)" in str(_verdict(killed=18, run=20, floor=floor, ratcheted=True))
    assert "(ratchet)" not in str(_verdict(killed=18, run=20, floor=floor))


def test_a_recorded_rate_below_the_global_floor_does_not_lower_the_bar() -> None:
    # The effective floor in smoke() is max(FLOOR, ratchet), so a recorded rate
    # under FLOOR leaves the bar at FLOOR: the ratchet only ever tightens.
    # ratchet_floor itself still returns the low rate; the caller clamps it.
    low = smoke_tool.ratchet_floor(
        {"tests/unit/test_x.py": smoke_tool.Row("src/x.py", "deadbeef", 1, 20)},
        "tests/unit/test_x.py",
        "src/x.py",
        "deadbeef",
        20,
    )
    assert low is not None
    assert low < smoke_tool.FLOOR
    assert max(smoke_tool.FLOOR, low) == smoke_tool.FLOOR


def test_read_baseline_treats_a_missing_file_as_empty(tmp_path: Path) -> None:
    assert smoke_tool.read_baseline(tmp_path) == {}


def test_read_baseline_drops_a_row_that_is_not_a_full_record(tmp_path: Path) -> None:
    # A row missing a field, or carrying a bool where an int belongs, is dropped
    # rather than trusted: a malformed baseline row is not a ratchet.
    (tmp_path / "tools").mkdir()
    (tmp_path / smoke_tool.BASELINE).write_text(
        json.dumps(
            {
                "tests/unit/good.py": {
                    "subject": "src/x.py",
                    "subject_sha": "ab",
                    "killed": 5,
                    "run": 6,
                },
                "tests/unit/no_run.py": {
                    "subject": "src/x.py",
                    "subject_sha": "ab",
                    "killed": 5,
                },
                "tests/unit/bool_kills.py": {
                    "subject": "src/x.py",
                    "subject_sha": "ab",
                    "killed": True,
                    "run": 6,
                },
                "tests/unit/not_a_dict.py": "nope",
            }
        ),
        encoding="utf-8",
    )
    rows = smoke_tool.read_baseline(tmp_path)
    assert list(rows) == ["tests/unit/good.py"]
    assert rows["tests/unit/good.py"] == smoke_tool.Row("src/x.py", "ab", 5, 6)


def test_read_baseline_treats_unreadable_json_as_empty(tmp_path: Path) -> None:
    (tmp_path / "tools").mkdir()
    (tmp_path / smoke_tool.BASELINE).write_text("{not json", encoding="utf-8")
    assert smoke_tool.read_baseline(tmp_path) == {}


def test_write_baseline_round_trips_and_sorts_for_a_stable_diff(tmp_path: Path) -> None:
    rows = {
        "tests/unit/test_b.py": smoke_tool.Row("src/b.py", "bb", 3, 4),
        "tests/unit/test_a.py": smoke_tool.Row("src/a.py", "aa", 6, 6),
    }
    smoke_tool.write_baseline(tmp_path, rows)
    text = (tmp_path / smoke_tool.BASELINE).read_text(encoding="utf-8")
    # Sorted by module name, so test_a precedes test_b whatever order it was given.
    assert text.index("test_a.py") < text.index("test_b.py")
    assert smoke_tool.read_baseline(tmp_path) == {
        "tests/unit/test_a.py": smoke_tool.Row("src/a.py", "aa", 6, 6),
        "tests/unit/test_b.py": smoke_tool.Row("src/b.py", "bb", 3, 4),
    }


# --- what is in scope -------------------------------------------------------


def _repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)  # noqa: S607 — git is resolved off PATH, as everywhere in tools/
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=root, check=True)  # noqa: S607 — git is resolved off PATH, as everywhere in tools/
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True)  # noqa: S607 — git is resolved off PATH, as everywhere in tools/
    (root / "tests").mkdir(exist_ok=True)
    (root / "tests" / "test_old.py").write_text("def test_a():\n    assert True\n")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)  # noqa: S607 — git is resolved off PATH, as everywhere in tools/
    subprocess.run(["git", "commit", "-qm", "base"], cwd=root, check=True)  # noqa: S607 — git is resolved off PATH, as everywhere in tools/


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("tests/unit/test_x.py", True),
        ("tests/test_x.py", True),
        ("tests/unit/conftest.py", False),
        ("tests/fixtures/thing.json", False),
        ("tools/test_x.py", False),
        ("src/cti_daemon/test_x.py", False),
    ],
)
def test_what_counts_as_a_test_module(name: str, *, expected: bool) -> None:
    assert smoke_tool.is_test_module(name) is expected


def test_an_untracked_new_test_module_is_in_scope(tmp_path: Path) -> None:
    # The shape an agent has in the tree when running `just fast` after an edit.
    _repo(tmp_path)
    (tmp_path / "tests" / "test_new.py").write_text("def test_b():\n    assert True\n")
    assert smoke_tool.in_scope(tmp_path, "main") == ["tests/test_new.py"]


def test_a_rewritten_test_module_is_in_scope(tmp_path: Path) -> None:
    _repo(tmp_path)
    (tmp_path / "tests" / "test_old.py").write_text("def test_a():\n    assert 1\n")
    assert smoke_tool.in_scope(tmp_path, "main") == ["tests/test_old.py"]


def test_a_deleted_test_module_is_not_in_scope(tmp_path: Path) -> None:
    _repo(tmp_path)
    (tmp_path / "tests" / "test_old.py").unlink()
    assert smoke_tool.in_scope(tmp_path, "main") == []


def test_a_change_to_something_that_is_not_a_test_is_not_in_scope(tmp_path: Path) -> None:
    _repo(tmp_path)
    (tmp_path / "notes.md").write_text("hello\n")
    assert smoke_tool.in_scope(tmp_path, "main") == []


# --- the selection rung: a module nothing was written for (#370) --------------


def _branch_and_commit(root: Path) -> None:
    subprocess.run(["git", "checkout", "-q", "-b", "work"], cwd=root, check=True)  # noqa: S607 — git is resolved off PATH, as everywhere in tools/
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)  # noqa: S607 — git is resolved off PATH, as everywhere in tools/
    subprocess.run(["git", "commit", "-qm", "work"], cwd=root, check=True)  # noqa: S607 — git is resolved off PATH, as everywhere in tools/


def test_an_untracked_new_module_is_introduced(tmp_path: Path) -> None:
    _repo(tmp_path)
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "new.py").write_text("x = 1\n")
    assert smoke_tool.added(tmp_path, "main") == ["tools/new.py"]


def test_a_committed_new_module_is_introduced(tmp_path: Path) -> None:
    # The other half of the diff: what `tools/land.py` will push, rather than
    # what an agent has loose in the tree while running `just fast`.
    _repo(tmp_path)
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "new.py").write_text("x = 1\n")
    _branch_and_commit(tmp_path)
    assert smoke_tool.added(tmp_path, "main") == ["tools/new.py"]


def test_an_edited_module_is_not_introduced(tmp_path: Path) -> None:
    # The whole reason this rung asks about introductions and not about changes:
    # an edit keeps whatever test module the file always had.
    _repo(tmp_path)
    (tmp_path / "tests" / "test_old.py").write_text("def test_a():\n    assert 1\n")
    assert smoke_tool.added(tmp_path, "main") == []


def test_a_renames_destination_is_introduced(tmp_path: Path) -> None:
    _repo(tmp_path)
    moved = ["git", "mv", "tests/test_old.py", "tests/test_new.py"]
    subprocess.run(moved, cwd=tmp_path, check=True)  # noqa: S603 — argv is built from constants here
    assert smoke_tool.added(tmp_path, "main") == ["tests/test_new.py"]


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("tools/new.py", True),
        ("src/cti_daemon/new.py", True),
        (".claude/hooks/deny-new.py", True),
        ("src/cti_daemon/__init__.py", False),
        ("tests/unit/test_new.py", False),
        ("tools/new.json", False),
        ("spike/new.sh", False),
    ],
)
def test_what_counts_as_a_product_module(name: str, *, expected: bool) -> None:
    assert smoke_tool.is_product_module(name) is expected


def test_a_new_module_no_verdict_measured_is_unmeasured() -> None:
    assert smoke_tool.unmeasured(["tools/new.py"], set()) == ["tools/new.py"]


def test_a_new_module_a_verdict_planted_in_is_measured() -> None:
    assert smoke_tool.unmeasured(["tools/new.py"], {"tools/new.py"}) == []


def test_a_test_module_named_after_it_proves_nothing_when_the_run_measured_elsewhere() -> None:
    # #370: `tests/unit/test_new_cases.py` whose tests exercise only existing
    # code selects that other file as its subject, and the name alone used to
    # clear this check while no mutant was ever planted in the new module.
    assert smoke_tool.unmeasured(["tools/new.py"], {"src/cti_daemon/daemon.py"}) == ["tools/new.py"]


def test_the_escape_problems_name_the_list_and_the_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(smoke_tool, "NO_TEST_MODULE", {"tools/new.py": "   "})
    monkeypatch.setattr(smoke_tool, "NO_MUTABLE_SUBJECT", {"tests/unit/test_x.py": ""})
    joined = "\n".join(smoke_tool.escape_problems())
    assert "blank_escape_reason: NO_TEST_MODULE[tools/new.py]" in joined
    assert "blank_escape_reason: NO_MUTABLE_SUBJECT[tests/unit/test_x.py]" in joined


def test_argued_escapes_are_not_problems(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smoke_tool, "NO_TEST_MODULE", {"tools/new.py": "because"})
    assert smoke_tool.escape_problems() == []


def test_a_blank_reason_refuses_the_gate_before_anything_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,  # noqa: ANN001 — pytest's own fixture type adds nothing here
) -> None:
    # No repo is staged: the refusal fires before the tree is read at all.
    monkeypatch.setattr(smoke_tool, "NO_TEST_MODULE", {"tools/new.py": ""})
    assert smoke_tool.main(["--root", str(tmp_path), "--base", "main"]) == 2
    assert "blank_escape_reason: NO_TEST_MODULE[tools/new.py]" in capsys.readouterr().err


def test_something_that_is_not_a_product_module_is_never_unmeasured() -> None:
    assert smoke_tool.unmeasured(["docs/note.md", "spike/new.sh"], []) == []


def test_the_named_list_excuses_a_module(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smoke_tool, "NO_TEST_MODULE", {"tools/new.py": "because"})
    assert smoke_tool.unmeasured(["tools/new.py"], []) == []


def test_the_selection_report_names_the_class_and_both_remedies(
    monkeypatch: pytest.MonkeyPatch,
    capsys,  # noqa: ANN001 — pytest's own fixture type adds nothing here
) -> None:
    monkeypatch.setattr(smoke_tool, "NO_TEST_MODULE", {"tools/excused.py": "reads a document"})
    smoke_tool._report_selection(["tools/excused.py", "tools/new.py"], ["tools/new.py"])  # noqa: SLF001 — this module's own private half is what is under test
    out = capsys.readouterr().out
    assert "-- tools/excused.py exempt: reads a document" in out
    assert "RED tools/new.py no_test_module:" in out
    assert "tests/unit/test_new.py" in out
    assert "NO_TEST_MODULE" in out


def test_a_new_module_with_no_test_module_reds_the_gate(tmp_path: Path, capsys) -> None:  # noqa: ANN001 — pytest's own fixture type adds nothing here
    # The #324 shape end to end: before this rung the same tree printed "nothing
    # added or changed" and exited 0.
    _repo(tmp_path)
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "new.py").write_text("x = 1\n")
    assert smoke_tool.main(["--root", str(tmp_path), "--base", "main"]) == 1
    assert "RED tools/new.py no_test_module:" in capsys.readouterr().out


def test_the_named_list_clears_the_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smoke_tool, "NO_TEST_MODULE", {"tools/new.py": "because"})
    _repo(tmp_path)
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "new.py").write_text("x = 1\n")
    assert smoke_tool.main(["--root", str(tmp_path), "--base", "main"]) == 0


def test_the_survey_reports_an_unmeasured_module_and_still_exits_zero(
    tmp_path: Path,
    capsys,  # noqa: ANN001 — pytest's own fixture type adds nothing here
) -> None:
    _repo(tmp_path)
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "new.py").write_text("x = 1\n")
    assert smoke_tool.main(["--root", str(tmp_path), "--base", "main", "--report"]) == 0
    assert "RED tools/new.py no_test_module:" in capsys.readouterr().out


@pytest.mark.skipif(sys.platform == "win32", reason="the gate runs on the WSL2 side only")
def test_a_test_module_that_exercises_other_code_does_not_clear_the_new_module(
    tmp_path: Path,
    capsys,  # noqa: ANN001 — pytest's own fixture type adds nothing here
) -> None:
    # #370's critical finding, end to end. The diff introduces `tools/new.py`
    # beside `tests/test_new_cases.py`, whose name used to be enough: the check
    # matched a filename and never asked what the run measured. The tests
    # execute only the pre-existing subject, so the smoke plants every mutant
    # there and `tools/new.py` must still red.
    _repo(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "other.py").write_text(textwrap.dedent(SUBJECT).lstrip(), encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)  # noqa: S607 — git is resolved off PATH, as everywhere in tools/
    subprocess.run(["git", "commit", "-qm", "subject"], cwd=tmp_path, check=True)  # noqa: S607 — git is resolved off PATH, as everywhere in tools/
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "new.py").write_text("y = 2\n")
    (tmp_path / "tests" / "test_new_cases.py").write_text(
        textwrap.dedent(SOUND_TESTS)
        .lstrip()
        .replace("import subject", "import other")
        .replace("subject.toll", "other.toll"),
        encoding="utf-8",
    )
    assert smoke_tool.main(["--root", str(tmp_path), "--base", "main"]) == 1
    assert "RED tools/new.py no_test_module:" in capsys.readouterr().out


# --- in-place safety --------------------------------------------------------


def test_the_original_is_restored_even_when_the_body_raises(tmp_path: Path) -> None:
    target = tmp_path / "subject.py"
    target.write_text("original\n")

    def blow_up() -> None:
        with smoke_tool.grafted(tmp_path, "subject.py", "mutated\n"):
            assert target.read_text() == "mutated\n"
            raise RuntimeError

    with pytest.raises(RuntimeError):
        blow_up()
    assert target.read_text() == "original\n"
    assert not (tmp_path / smoke_tool.RESTORE).exists()


def test_the_sidecar_carries_the_original_while_the_mutant_is_in_place(tmp_path: Path) -> None:
    target = tmp_path / "subject.py"
    target.write_text("original\n")
    with smoke_tool.grafted(tmp_path, "subject.py", "mutated\n"):
        recorded = json.loads((tmp_path / smoke_tool.RESTORE).read_text())
    assert recorded == {"path": "subject.py", "text": "original\n"}


def test_a_stale_sidecar_stops_the_run_rather_than_guessing(tmp_path: Path, capsys) -> None:  # noqa: ANN001 — pytest's own fixture type adds nothing here
    (tmp_path / smoke_tool.RESTORE).write_text("{}")
    assert smoke_tool.main(["--root", str(tmp_path)]) == 2
    assert "interrupted mid-mutant" in capsys.readouterr().err


def test_restore_puts_back_the_file_the_sidecar_names(tmp_path: Path) -> None:
    target = tmp_path / "subject.py"
    target.write_text("mutated\n")
    (tmp_path / smoke_tool.RESTORE).write_text(
        json.dumps({"path": "subject.py", "text": "original\n"}),
    )
    assert smoke_tool.main(["--root", str(tmp_path), "--restore"]) == 0
    assert target.read_text() == "original\n"
    assert not (tmp_path / smoke_tool.RESTORE).exists()


def test_restore_with_nothing_to_restore_is_not_an_error(tmp_path: Path) -> None:
    assert smoke_tool.main(["--root", str(tmp_path), "--restore"]) == 0


def test_nothing_in_scope_is_a_pass_not_a_refusal(tmp_path: Path) -> None:
    _repo(tmp_path)
    assert smoke_tool.main(["--root", str(tmp_path), "--base", "main"]) == 0


# --- end to end, against a throwaway repo -----------------------------------

SUBJECT = '''
"""A subject with decisions in it to mutate."""


def toll(distance, heavy):
    if distance > 10 and heavy:
        return distance * 3
    if not heavy:
        return distance
    return 0
'''

SOUND_TESTS = """
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import subject


def test_a_long_heavy_haul_is_charged_triple():
    assert subject.toll(20, heavy=True) == 60


def test_a_short_heavy_haul_is_free():
    assert subject.toll(5, heavy=True) == 0


def test_a_light_haul_is_charged_by_distance():
    assert subject.toll(20, heavy=False) == 20
    assert subject.toll(5, heavy=False) == 5


def test_the_boundary_is_above_ten_not_at_it():
    assert subject.toll(10, heavy=True) == 0
    assert subject.toll(11, heavy=True) == 33
"""

VACUOUS_TESTS = """
def test_it_works():
    assert True


def test_arithmetic_still_holds():
    assert 1 + 1 == 2
"""

WEAK_TESTS = """
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import subject


def test_a_heavy_haul_is_priced():
    assert subject.toll(20, heavy=True) is not None


def test_a_light_haul_is_priced():
    assert subject.toll(20, heavy=False) is not None


def test_a_short_haul_is_priced():
    assert subject.toll(5, heavy=True) is not None


def test_a_price_is_a_number():
    assert isinstance(subject.toll(11, heavy=True), int)
"""

IMPORT_CRASH_SUBJECT = """
def validated(value):
    if value != 1:
        raise ValueError("invalid")


VALIDATED = validated(1)
"""

IMPORT_CRASH_TESTS = """
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import subject


def test_one_is_valid():
    assert subject.validated(1) is None
"""


def _throwaway(root: Path, tests: str) -> str:
    (root / "src").mkdir()
    (root / "src" / "subject.py").write_text(textwrap.dedent(SUBJECT).lstrip(), encoding="utf-8")
    (root / "tests").mkdir()
    name = "tests/test_subject.py"
    (root / name).write_text(textwrap.dedent(tests).lstrip(), encoding="utf-8")
    return name


@pytest.mark.skipif(sys.platform == "win32", reason="the gate runs on the WSL2 side only")
def test_a_sound_test_module_clears_the_floor(tmp_path: Path) -> None:
    name = _throwaway(tmp_path, SOUND_TESTS)
    verdict = smoke_tool.smoke(tmp_path, name, cap=8, budget=120.0, rows={})
    assert verdict.subject == "src/subject.py"
    assert verdict.ok, f"{verdict}: {[str(m) for m in verdict.survivors]}"


@pytest.mark.skipif(sys.platform == "win32", reason="the gate runs on the WSL2 side only")
def test_a_vacuous_test_module_is_red(tmp_path: Path) -> None:
    # #239's acceptance, as a test rather than as a demonstration quoted once.
    name = _throwaway(tmp_path, VACUOUS_TESTS)
    verdict = smoke_tool.smoke(tmp_path, name, cap=8, budget=120.0, rows={})
    assert not verdict.ok
    assert verdict.subject is None
    assert "no subject" in verdict.reason


@pytest.mark.skipif(sys.platform == "win32", reason="the gate runs on the WSL2 side only")
def test_a_module_that_only_asserts_shapes_is_red(tmp_path: Path) -> None:
    # The pair to the two above, and the one that keeps the whole gate honest:
    # this module runs every branch of the subject and asserts only `is not None`,
    # so mutants have to actually survive. Every draft in which the node ids
    # handed to pytest were wrong passed this subject 100% — a run that never
    # happened cannot produce a survivor.
    name = _throwaway(tmp_path, WEAK_TESTS)
    verdict = smoke_tool.smoke(tmp_path, name, cap=8, budget=120.0, rows={})
    assert verdict.subject == "src/subject.py"
    assert not verdict.ok
    assert verdict.survivors


@pytest.mark.skipif(sys.platform == "win32", reason="the gate runs on the WSL2 side only")
def test_a_mutant_that_breaks_import_after_a_green_preflight_is_killed(tmp_path: Path) -> None:
    name = _throwaway(tmp_path, IMPORT_CRASH_TESTS)
    (tmp_path / "src" / "subject.py").write_text(
        textwrap.dedent(IMPORT_CRASH_SUBJECT).lstrip(),
        encoding="utf-8",
    )
    verdict = smoke_tool.smoke(tmp_path, name, cap=8, budget=120.0, rows={})
    assert verdict.planted > 0
    assert verdict.killed == verdict.run == verdict.planted
    assert verdict.ok


@pytest.mark.skipif(sys.platform == "win32", reason="the gate runs on the WSL2 side only")
def test_a_module_that_is_not_green_still_refuses_before_mutation(tmp_path: Path) -> None:
    name = _throwaway(tmp_path, "def test_red():\n    assert False\n")
    with pytest.raises(smoke_tool.Refusal, match="is not green on its own"):
        smoke_tool.smoke(tmp_path, name, cap=8, budget=120.0, rows={})


# --- the ratchet, end to end (#244) -----------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="the gate runs on the WSL2 side only")
def test_record_writes_a_modules_rate_against_its_subject(tmp_path: Path) -> None:
    name = _throwaway(tmp_path, SOUND_TESTS)
    assert smoke_tool.main(["--root", str(tmp_path), "--paths", name, "--record"]) == 0
    row = smoke_tool.read_baseline(tmp_path)[name]
    assert row.subject == "src/subject.py"
    assert row.run > 0
    assert row.killed <= row.run
    # The row pins the subject's bytes, which is what makes a release path on a
    # refactor: the sha is the file as it is now, not a constant.
    assert row.subject_sha == smoke_tool.subject_sha(tmp_path, "src/subject.py")


@pytest.mark.skipif(sys.platform == "win32", reason="the gate runs on the WSL2 side only")
def test_the_gate_reds_when_a_module_falls_below_its_recorded_rate(tmp_path: Path) -> None:
    name = _throwaway(tmp_path, SOUND_TESTS)
    smoke_tool.main(["--root", str(tmp_path), "--paths", name, "--record"])
    row = smoke_tool.read_baseline(tmp_path)[name]
    # Inflate the recorded kills past what the tests achieve (beyond slack), so
    # the ratchet floor sits above this module's reach. The gate reads the
    # baseline, finds the row's pair still matches, and reds. This is the
    # read-side of the ratchet exercised end to end.
    inflated = smoke_tool.Row(
        row.subject,
        row.subject_sha,
        row.killed + smoke_tool.SLACK + 1,
        row.run,
    )
    smoke_tool.write_baseline(tmp_path, {name: inflated})
    assert smoke_tool.main(["--root", str(tmp_path), "--paths", name]) == 1


@pytest.mark.skipif(sys.platform == "win32", reason="the gate runs on the WSL2 side only")
def test_record_raises_a_row_when_the_tests_grow_stronger(tmp_path: Path) -> None:
    # The whole point of the ratchet: a strengthening becomes the new floor. The
    # subject is unchanged across both records, so the row's pair matches and the
    # kill count is the only thing that moves — upward.
    name = _throwaway(tmp_path, WEAK_TESTS)
    smoke_tool.main(["--root", str(tmp_path), "--paths", name, "--record"])
    weak = smoke_tool.read_baseline(tmp_path)[name]
    (tmp_path / name).write_text(textwrap.dedent(SOUND_TESTS).lstrip(), encoding="utf-8")
    smoke_tool.main(["--root", str(tmp_path), "--paths", name, "--record"])
    strong = smoke_tool.read_baseline(tmp_path)[name]
    assert strong.subject_sha == weak.subject_sha
    assert strong.killed > weak.killed
