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
import subprocess
import sys
import textwrap
from typing import TYPE_CHECKING, Any

import pytest
from conftest import load_tool

if TYPE_CHECKING:
    from pathlib import Path
    from types import ModuleType

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


def test_the_subject_is_the_file_the_tests_reach_most() -> None:
    reach = smoke_tool.read_reach(
        _report(
            {
                "src/small.py": {"1": ["t|run"]},
                "tools/big.py": {"1": ["t|run"], "2": ["t|run"], "3": ["t|run"]},
            },
        ),
    )
    assert reach.subject() == "tools/big.py"


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
        ("test_a_window_can_be_filled", "test_a_window_can_be_filled"),
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


def test_the_selection_stops_at_its_wall_clock_bound() -> None:
    # Three at 3.0s each would be 9s, past the 8s the selection may spend.
    reach = smoke_tool.read_reach({}, {f"t{i}": 3.0 for i in range(6)})
    assert reach.cheapest(tuple(f"t{i}" for i in range(6))) == ["t0", "t1"]


def test_an_unmeasured_test_is_assumed_free_rather_than_expensive() -> None:
    reach = smoke_tool.read_reach({}, {"known": 1.0})
    assert reach.cheapest(("known", "unknown")) == ["unknown", "known"]


def test_a_mutants_timeout_is_derived_from_what_its_tests_cost_unmutated() -> None:
    reach = smoke_tool.read_reach({}, {"slow": 30.0})
    assert reach.timeout(["slow"]) == 120.0
    assert reach.timeout([]) == smoke_tool.TIMEOUT_FLOOR_S


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
    assert "interrupted mid-mutation" in capsys.readouterr().err


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
    verdict = smoke_tool.smoke(tmp_path, name, cap=8, budget=120.0)
    assert verdict.subject == "src/subject.py"
    assert verdict.ok, f"{verdict}: {[str(m) for m in verdict.survivors]}"


@pytest.mark.skipif(sys.platform == "win32", reason="the gate runs on the WSL2 side only")
def test_a_vacuous_test_module_is_red(tmp_path: Path) -> None:
    # #239's acceptance, as a test rather than as a demonstration quoted once.
    name = _throwaway(tmp_path, VACUOUS_TESTS)
    verdict = smoke_tool.smoke(tmp_path, name, cap=8, budget=120.0)
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
    verdict = smoke_tool.smoke(tmp_path, name, cap=8, budget=120.0)
    assert verdict.subject == "src/subject.py"
    assert not verdict.ok
    assert verdict.survivors
