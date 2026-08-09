"""The mutation smoke's shell arm: what it plants, where it plants it, and what it reds on.

Three halves, and the middle one is the reason this arm exists at all.

The first is the mutator, which is pure — one line of shell in, mutants out. What
it refuses to touch is held here as regressions, because every equivalent mutant
that survives in the real corpus has to be paid for out of `SHELL_FLOOR`: a
comparison inside a message, a number inside a `${...}` default, a `<` that is a
redirection rather than a test.

The second is the stage. A shell mutant is written into a hardlinked copy of the
tree and never into `spike/` itself, because `spike/*.sh` is what a live Arma tier
reads and `just regress` may be holding a slot while `just land` runs `just fast`.
`test_a_graft_never_touches_the_real_script` asserts that against the real inode
rather than against the intention.

The third is two end-to-end runs against a throwaway repository: a sound
shell-subject module clears the floor and a vacuous one does not. That pair is
this arm's acceptance (#246), run every time `just unit` runs, rather than a
demonstration quoted once in a closing comment.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
import textwrap
from typing import TYPE_CHECKING, Any

import pytest
from conftest import load_tool

if TYPE_CHECKING:
    from pathlib import Path
    from types import ModuleType

# Both siblings first, and in this order: `tools/` holds scripts rather than a
# package, so `mutation_smoke`'s `import mutation_shell` resolves only because
# `load_tool` has already registered it in `sys.modules` under that name (the
# `timeline` / `telemetry_log` pattern `conftest.load_tool` documents).
shell_tool: ModuleType = load_tool("mutation_shell")
load_tool("mutation_rust")
smoke_tool: ModuleType = load_tool("mutation_smoke")


def _plant(line: str) -> list[Any]:
    return shell_tool.plant(line + "\n", lines=frozenset({1}))


def _afters(line: str) -> list[str]:
    return [edit.after for edit in _plant(line)]


def _operators(line: str) -> list[str]:
    return [edit.operator for edit in _plant(line)]


# --- what the mutator plants ------------------------------------------------


@pytest.mark.parametrize(
    ("expression", "flipped"),
    [
        ("[[ $a -eq $b ]]", "-ne"),
        ("[[ $a -ne $b ]]", "-eq"),
        ("[[ $a -lt $b ]]", "-ge"),
        ("[[ $a -le $b ]]", "-gt"),
        ("[[ $a -gt $b ]]", "-le"),
        ("[[ $a -ge $b ]]", "-lt"),
        ("[[ -n $a ]]", "-z"),
        ("[[ -z $a ]]", "-n"),
        ("[[ $a == $b ]]", "!="),
        ("[[ $a != $b ]]", "=="),
        ("(( a < b ))", ">="),
        ("(( a > b ))", "<="),
    ],
)
def test_every_test_operator_is_flipped_to_its_negation(expression: str, flipped: str) -> None:
    assert flipped in _afters(expression)


@pytest.mark.parametrize(
    ("expression", "shifted"),
    [
        ("[[ $a -lt $b ]]", "-le"),
        ("[[ $a -le $b ]]", "-lt"),
        ("[[ $a -gt $b ]]", "-ge"),
        ("[[ $a -ge $b ]]", "-gt"),
        ("(( a < b ))", "<="),
        ("(( a > b ))", ">="),
    ],
)
def test_an_ordering_operator_is_also_shifted_by_one(expression: str, shifted: str) -> None:
    # The boundary mutant is the one a suite asserting "it exited non-zero"
    # reaches over: a negated `-gt` usually breaks the script outright.
    assert shifted in _afters(expression)


def test_an_equality_has_no_boundary_to_shift() -> None:
    assert _operators("[[ $a -eq $b ]]") == ["compare"]


def test_a_list_operator_is_flipped_both_ways() -> None:
    assert "||" in _afters('[[ -n "$pid" ]] && kill "$pid"')
    assert "&&" in _afters("cmd || fail infra_unavailable")


def test_a_negation_is_dropped() -> None:
    assert "" in _afters("if ! guard_env=$(check); then")


def test_an_exit_status_becomes_success() -> None:
    # This arm's `return <expr>` -> `None`: a script's exit status is its return
    # value, and every module on this arm asserts on one.
    assert "exit 0" in _afters("    exit 1")
    assert "return 0" in _afters("    return 2")


def test_a_success_status_has_no_mutant() -> None:
    assert "status" not in _operators("    exit 0")
    assert "status" not in _operators("    return 0")


def test_a_number_inside_a_test_is_offset_by_one() -> None:
    assert "2" in _afters("(( count > 1 ))")


# --- what it deliberately refuses to plant ----------------------------------


def test_nothing_inside_a_quoted_string_is_touched() -> None:
    # A comparison inside a message is not a decision the script takes: mutating
    # one changes what the script *says* and nothing about what it does, so it
    # survives and would have to be paid for out of the floor.
    assert _plant('log "a == b and c -lt d"') == []


def test_nothing_after_an_unquoted_comment_is_touched() -> None:
    assert _plant("cmd # [[ $a == $b ]] && exit 1") == []


def test_an_assignment_is_never_read_as_a_comparison() -> None:
    # `=` is assignment outside a test, and `<` is a redirection. Mutating either
    # is a mutant about nothing, or a syntax error the budget was spent reaching.
    assert _plant('SERVER_DIR="$HOME/arma3server"') == []
    assert _plant("cmd <input.txt >output.txt") == []


def test_a_bare_flag_is_never_read_as_a_test_operator() -> None:
    # `sed -n` is not `[[ -n ... ]]`, and `head -1` is not a comparison.
    assert _plant('newest=$(ls -t "$dir" | head -1)') == []
    assert _plant("sed -n 's/^failure_detail=//p' <<<\"$guard_env\"") == []


def test_a_number_inside_a_parameter_default_is_never_touched() -> None:
    # `${CTI_HOLD_HC:-0}` is bash's spelling of `def f(hold_hc=0)`, and ADR-0064
    # has never let the Python arm touch a parameter default. Every one of these
    # measured here survived. The `1` beside it is a real arithmetic constant and
    # is still offered, so this is the freeze and not an empty walk.
    assert _afters("SKIP_HC=$(( 1 - ${CTI_HOLD_HC:-0} ))") == ["2"]


def test_a_number_inside_a_regular_expression_is_never_touched() -> None:
    assert "number" not in _operators('[[ "$UV_TIMEOUT" =~ ^[1-9][0-9]*$ ]]')


def test_only_executed_lines_are_planted() -> None:
    source = "[[ $a -eq 1 ]]\n[[ $b -eq 2 ]]\n"
    assert [edit.line for edit in shell_tool.plant(source, lines=frozenset({2}))] == [2, 2]


def test_planting_is_deterministic() -> None:
    source = '[[ -n "$a" ]] && exit 1\n'
    assert shell_tool.plant(source, lines=frozenset({1})) == shell_tool.plant(
        source,
        lines=frozenset({1}),
    )


def test_a_span_is_measured_in_bytes_not_characters() -> None:
    # The graft is a byte-slice, so a non-ASCII character before the mutation
    # site cuts the file in the wrong place if the offsets are counted in
    # characters. `spike/run.sh` really does log an em dash.
    source = 'log "FAILED: — —"\n[[ $a -eq $b ]]\n'
    edit = next(edit for edit in shell_tool.plant(source, lines=frozenset({2})) if edit.after)
    assert source.encode("utf-8")[edit.start : edit.end].decode("utf-8") == edit.before


# --- what bash will accept ---------------------------------------------------


def test_a_syntactically_valid_graft_is_kept() -> None:
    assert shell_tool.parses("if [[ $a != $b ]]; then exit 1; fi\n")


def test_a_graft_bash_cannot_parse_is_rejected() -> None:
    # `bash -n` is this arm's `compile()`: a span the mutator misreads is dropped
    # here rather than reaching the tests as a red that means nothing.
    assert not shell_tool.parses("if [[ $a != $b ]]; then exit 1\n")


# --- reading the xtrace ------------------------------------------------------


def _trace(directory: Path, node: str, rows: list[str]) -> None:
    traces = directory / "traces"
    traces.mkdir(exist_ok=True)
    digest = f"{abs(hash(node)):016x}"[:16]
    with (traces / "index.txt").open("a", encoding="utf-8") as index:
        index.write(f"{digest}\t{node}\n")
    (traces / f"{digest}.trace").write_text("\n".join(rows) + "\n", encoding="utf-8")


def test_a_traced_line_is_attributed_to_the_test_that_ran_it(tmp_path: Path) -> None:
    (tmp_path / "spike").mkdir()
    (tmp_path / "spike" / "bringup.sh").write_text("true\n")
    workspace = tmp_path / "work"
    workspace.mkdir()
    _trace(workspace, "tests/t.py::test_a", [f"+@{tmp_path}/spike/bringup.sh@12@ exit 1"])
    assert shell_tool.read_traces(workspace, tmp_path) == {
        "spike/bringup.sh": {12: ("tests/t.py::test_a",)},
    }


def test_a_nested_trace_line_is_read_at_any_depth(tmp_path: Path) -> None:
    # Bash replicates PS4's *first* character once per level of indirection, so a
    # line inside a function inside a sourced file starts with several `+`.
    (tmp_path / "spike").mkdir()
    (tmp_path / "spike" / "bringup.sh").write_text("true\n")
    workspace = tmp_path / "work"
    workspace.mkdir()
    _trace(workspace, "tests/t.py::test_a", [f"+++@{tmp_path}/spike/bringup.sh@7@ kill 1"])
    assert shell_tool.read_traces(workspace, tmp_path) == {
        "spike/bringup.sh": {7: ("tests/t.py::test_a",)},
    }


def test_a_script_outside_this_repo_is_never_a_subject(tmp_path: Path) -> None:
    # A stub the test wrote into its own `tmp_path` is somebody else's code,
    # however much of it ran.
    workspace = tmp_path / "work"
    workspace.mkdir()
    _trace(workspace, "tests/t.py::test_a", ["+@/tmp/elsewhere/tasklist.sh@1@ printf x"])
    assert shell_tool.read_traces(workspace, tmp_path) == {}


def test_a_repo_file_that_is_not_shell_is_never_a_subject(tmp_path: Path) -> None:
    (tmp_path / "spike").mkdir()
    (tmp_path / "spike" / "probe.sqf").write_text("true\n")
    workspace = tmp_path / "work"
    workspace.mkdir()
    _trace(workspace, "tests/t.py::test_a", [f"+@{tmp_path}/spike/probe.sqf@1@ x"])
    assert shell_tool.read_traces(workspace, tmp_path) == {}


def test_a_line_two_tests_ran_names_both(tmp_path: Path) -> None:
    (tmp_path / "spike").mkdir()
    (tmp_path / "spike" / "bringup.sh").write_text("true\n")
    workspace = tmp_path / "work"
    workspace.mkdir()
    for node in ("tests/t.py::test_b", "tests/t.py::test_a"):
        _trace(workspace, node, [f"+@{tmp_path}/spike/bringup.sh@3@ x"])
    assert shell_tool.read_traces(workspace, tmp_path)["spike/bringup.sh"][3] == (
        "tests/t.py::test_a",
        "tests/t.py::test_b",
    )


def test_a_collect_with_no_traces_at_all_reads_as_no_shell(tmp_path: Path) -> None:
    workspace = tmp_path / "work"
    workspace.mkdir()
    assert shell_tool.read_traces(workspace, tmp_path) == {}


def test_the_trace_environment_leaves_an_existing_pythonpath_in_place(tmp_path: Path) -> None:
    # The plugin has to be importable *and* whatever the caller was already
    # carrying has to keep working, or the collect pass fails for a reason that
    # has nothing to do with the module under measurement.
    environment = shell_tool.trace_environment(tmp_path)
    assert (tmp_path / "bash-env.sh").exists()
    assert (tmp_path / "cti_shell_trace.py").exists()
    existing = os.environ.get("PYTHONPATH")
    if existing:
        assert environment["PYTHONPATH"].endswith(existing)
    assert environment["PYTHONPATH"].startswith(str(tmp_path))


def test_the_preamble_writes_nothing_when_no_trace_is_asked_for(tmp_path: Path) -> None:
    # Every bash this repository starts for any other reason reads this file.
    # One that wrote a trace anyway would be a gate leaving litter in the tree.
    preamble = tmp_path / "bash-env.sh"
    preamble.write_text(shell_tool.TRACE_PREAMBLE, encoding="utf-8")
    script = tmp_path / "quiet.sh"
    script.write_text("#!/usr/bin/env bash\nprintf done\n", encoding="utf-8")
    done = subprocess.run(  # noqa: S603 — this test's own script
        ["bash", str(script)],  # noqa: S607 — bash off PATH, as everywhere in tests/
        env={**os.environ, "BASH_ENV": str(preamble), "CTI_SHELL_TRACE": ""},
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert done.stdout == "done"
    assert done.stderr == ""


def test_the_preamble_traces_to_its_own_descriptor_and_not_to_stderr(tmp_path: Path) -> None:
    # The load-bearing property: several of the modules on this arm assert on a
    # script's stderr, and an xtrace on stderr would red every one of them.
    preamble = tmp_path / "bash-env.sh"
    preamble.write_text(shell_tool.TRACE_PREAMBLE, encoding="utf-8")
    script = tmp_path / "loud.sh"
    script.write_text("#!/usr/bin/env bash\necho complaint >&2\n", encoding="utf-8")
    trace = tmp_path / "trace"
    done = subprocess.run(  # noqa: S603 — this test's own script
        ["bash", str(script)],  # noqa: S607 — bash off PATH, as everywhere in tests/
        env={**os.environ, "BASH_ENV": str(preamble), "CTI_SHELL_TRACE": str(trace)},
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert done.stderr == "complaint\n"
    assert shell_tool.TRACED.match(trace.read_text(encoding="utf-8").splitlines()[0])


# --- the stage ---------------------------------------------------------------


def _git_repo(root: Path) -> None:
    for argv in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.email", "t@t"],
        ["git", "config", "user.name", "t"],
    ):
        subprocess.run(argv, cwd=root, check=True)  # noqa: S603 — git off PATH, as everywhere in tools/


def test_the_stage_is_hardlinked_rather_than_copied(tmp_path: Path) -> None:
    _git_repo(tmp_path)
    (tmp_path / "spike").mkdir()
    (tmp_path / "spike" / "bringup.sh").write_text("exit 1\n", encoding="utf-8")
    with shell_tool.staged(tmp_path) as stage:
        assert (stage / "spike" / "bringup.sh").stat().st_ino == (
            tmp_path / "spike" / "bringup.sh"
        ).stat().st_ino


def test_the_stage_carries_a_new_untracked_test_module(tmp_path: Path) -> None:
    # The shape an agent has in the tree when running `just fast` after an edit:
    # a test module git has never seen. A stage built from tracked files alone
    # would not contain the module the gate was asked about.
    _git_repo(tmp_path)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_new.py").write_text("def test_a():\n    assert 1\n")
    with shell_tool.staged(tmp_path) as stage:
        assert (stage / "tests" / "test_new.py").exists()


def test_the_stage_leaves_out_what_git_ignores(tmp_path: Path) -> None:
    _git_repo(tmp_path)
    (tmp_path / ".gitignore").write_text("build/\n", encoding="utf-8")
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "artefact.bin").write_bytes(b"x")
    with shell_tool.staged(tmp_path) as stage:
        assert not (stage / "build").exists()


def test_a_graft_never_touches_the_real_script(tmp_path: Path) -> None:
    # The whole safety argument of this arm, asserted against the inode rather
    # than against the intention. Writing *through* a hardlink would edit
    # `spike/run.sh` while a live Arma tier is reading it.
    _git_repo(tmp_path)
    (tmp_path / "spike").mkdir()
    real = tmp_path / "spike" / "bringup.sh"
    real.write_text("exit 1\n", encoding="utf-8")
    real.chmod(real.stat().st_mode | stat.S_IXUSR)
    with shell_tool.staged(tmp_path) as stage:
        with shell_tool.graft(stage, "spike/bringup.sh", "exit 0\n"):
            assert (stage / "spike" / "bringup.sh").read_text(encoding="utf-8") == "exit 0\n"
            assert real.read_text(encoding="utf-8") == "exit 1\n"
            assert (stage / "spike" / "bringup.sh").stat().st_ino != real.stat().st_ino
        assert (stage / "spike" / "bringup.sh").read_text(encoding="utf-8") == "exit 1\n"
    assert real.read_text(encoding="utf-8") == "exit 1\n"


def test_a_graft_keeps_the_scripts_executable_bit(tmp_path: Path) -> None:
    # Unlink-and-recreate loses the mode unless it is put back, and a script the
    # tests run by path would then fail for a reason that is not the mutant.
    _git_repo(tmp_path)
    (tmp_path / "spike").mkdir()
    real = tmp_path / "spike" / "bringup.sh"
    real.write_text("exit 1\n", encoding="utf-8")
    real.chmod(real.stat().st_mode | stat.S_IXUSR)
    with (
        shell_tool.staged(tmp_path) as stage,
        shell_tool.graft(stage, "spike/bringup.sh", "exit 0\n"),
    ):
        assert (stage / "spike" / "bringup.sh").stat().st_mode & stat.S_IXUSR


def test_the_staged_original_comes_back_even_when_the_body_raises(tmp_path: Path) -> None:
    _git_repo(tmp_path)
    (tmp_path / "spike").mkdir()
    (tmp_path / "spike" / "bringup.sh").write_text("exit 1\n", encoding="utf-8")

    def blow_up(stage: Path) -> None:
        with shell_tool.graft(stage, "spike/bringup.sh", "exit 0\n"):
            raise RuntimeError

    with shell_tool.staged(tmp_path) as stage:
        with pytest.raises(RuntimeError):
            blow_up(stage)
        assert (stage / "spike" / "bringup.sh").read_text(encoding="utf-8") == "exit 1\n"


# --- the subject the evidence picks -----------------------------------------


def _reach(lines: dict[str, dict[int, tuple[str, ...]]]) -> Any:  # noqa: ANN401 — a `tools/` script's type is not nameable here
    return smoke_tool.Reach(lines, {})


def test_a_script_named_after_the_module_is_the_subject_despite_its_hyphen() -> None:
    # `spike/host-guard.sh` is what `tests/unit/test_host_guard.py` is named
    # after, and no Python module name can carry that hyphen.
    reach = _reach(
        {
            "spike/host-guard.sh": {1: ("a",)},
            "spike/regress.sh": {1: ("a",), 2: ("b",), 3: ("c",)},
        },
    )
    assert reach.subject("tests/unit/test_host_guard.py", weighted=True) == "spike/host-guard.sh"


def test_a_script_only_one_test_reached_does_not_out_score_the_one_they_all_drive() -> None:
    # Measured, on `tests/unit/test_bringup_guards.py`: `spike/run.sh` sources
    # three helpers and `tier-lock.sh` sources `slots.sh`, so one test that takes
    # a lock executes a whole script nobody was testing. Unweighted
    # discrimination chose `slots.sh` and the module killed 0 of 12.
    reach = _reach(
        {
            "spike/run.sh": dict.fromkeys(range(1, 30), ("a", "b", "c")),
            "spike/slots.sh": dict.fromkeys(range(1, 12), ("d",)),
        },
    )
    assert reach.subject("tests/unit/test_bringup_guards.py", weighted=True) == "spike/run.sh"
    # ...and the unweighted rule, which the Python arm still uses, does not.
    assert reach.subject("tests/unit/test_bringup_guards.py") == "spike/slots.sh"


def test_the_share_of_a_script_is_the_share_of_tests_that_reached_it() -> None:
    reach = _reach({"spike/a.sh": {1: ("x", "y")}, "spike/b.sh": {1: ("x",)}})
    assert reach.share("spike/a.sh") == 1.0
    assert reach.share("spike/b.sh") == 0.5


def test_a_declared_subject_the_tests_never_ran_is_a_refusal() -> None:
    # `SHELL_SUBJECT` is a tie-break among the scripts the tests executed, never
    # a way to nominate one they did not — the same limit the naming convention
    # carries in the Python arm.
    reach = _reach({"spike/regress.sh": {1: ("a",)}})
    module = next(iter(smoke_tool.SHELL_SUBJECT))
    with pytest.raises(smoke_tool.Refusal, match="never a way to nominate"):
        smoke_tool._declared_shell_subject(reach, module)  # noqa: SLF001 — the routing rule is what is under test


def test_every_declared_subject_names_a_script_that_exists() -> None:
    # A row naming a renamed or deleted script would refuse the module it was
    # meant to gate, which reads as a broken gate rather than as a stale row.
    root = smoke_tool.Path(__file__).resolve().parents[2]
    for module, script in smoke_tool.SHELL_SUBJECT.items():
        assert (root / script).exists(), f"{module} declares {script}, which is not in the tree"


def test_the_lines_a_mutant_may_go_on_can_be_narrowed_to_the_discriminating_ones() -> None:
    # Measured worse and therefore off (`SHELL_DISCRIMINATING`), but kept so the
    # next person can re-measure rather than re-argue.
    reach = _reach({"spike/a.sh": {1: ("x", "y"), 2: ("x",)}})
    assert smoke_tool._shell_lines(reach, "spike/a.sh", discriminating=True) == {  # noqa: SLF001 — the narrowing rule is what is under test
        2: ("x",),
    }
    assert smoke_tool._shell_lines(reach, "spike/a.sh", discriminating=False) == {  # noqa: SLF001 — as above
        1: ("x", "y"),
        2: ("x",),
    }


def test_narrowing_to_nothing_falls_back_to_every_line() -> None:
    # A script every one of its tests walks identically still has decisions in
    # it, and an empty plant would read as "nothing to plant" — a pass.
    reach = _reach({"spike/a.sh": {1: ("x", "y"), 2: ("x", "y")}})
    assert smoke_tool._shell_lines(reach, "spike/a.sh", discriminating=True) == {  # noqa: SLF001 — as above
        1: ("x", "y"),
        2: ("x", "y"),
    }


# --- end to end, against a throwaway repo -----------------------------------

TOLL = """\
#!/usr/bin/env bash
# A subject with decisions in it to mutate.
set -uo pipefail
distance=$1
heavy=$2
if (( distance > 10 )) && [[ "$heavy" == yes ]]; then
    printf '%s\\n' $(( distance * 3 ))
    exit 0
fi
if [[ "$heavy" != yes ]]; then
    printf '%s\\n' "$distance"
    exit 0
fi
printf '0\\n'
exit 3
"""

DRIVER = """
import subprocess
from pathlib import Path

TOLL = Path(__file__).resolve().parents[1] / "spike" / "toll.sh"


def toll(distance, heavy):
    return subprocess.run(
        ["bash", str(TOLL), str(distance), heavy],
        capture_output=True, text=True, check=False, timeout=60,
    )
"""

SOUND_TESTS = """
from driver import toll


def test_a_long_heavy_haul_is_charged_triple():
    done = toll(20, "yes")
    assert done.stdout == "60\\n"
    assert done.returncode == 0


def test_a_short_heavy_haul_is_free_and_says_so_in_its_status():
    done = toll(5, "yes")
    assert done.stdout == "0\\n"
    assert done.returncode == 3


def test_a_light_haul_is_charged_by_distance():
    assert toll(20, "no").stdout == "20\\n"
    assert toll(5, "no").stdout == "5\\n"


def test_the_boundary_is_above_ten_not_at_it():
    assert toll(10, "yes").stdout == "0\\n"
    assert toll(11, "yes").stdout == "33\\n"
"""

VACUOUS_TESTS = """
def test_it_works():
    assert True


def test_arithmetic_still_holds():
    assert 1 + 1 == 2
"""

WEAK_TESTS = """
from driver import toll


def test_a_heavy_haul_is_priced():
    assert toll(20, "yes").stdout is not None


def test_a_light_haul_is_priced():
    assert toll(20, "no").stdout is not None


def test_a_short_haul_is_priced():
    assert toll(5, "yes").stdout is not None


def test_a_boundary_haul_is_priced():
    assert toll(11, "yes").stdout is not None
"""


def _throwaway(root: Path, tests: str) -> str:
    """Build a repository with a shell subject, a driver, and one test module of `tests`."""
    _git_repo(root)
    (root / "spike").mkdir()
    script = root / "spike" / "toll.sh"
    script.write_text(TOLL, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    # A source root the Python arm can look at and find nothing in, which is what
    # sends these modules to the shell arm rather than to a coverage error.
    (root / "src").mkdir()
    (root / "src" / "unused.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "driver.py").write_text(textwrap.dedent(DRIVER).lstrip(), encoding="utf-8")
    name = "tests/test_toll.py"
    (root / name).write_text(textwrap.dedent(tests).lstrip(), encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)  # noqa: S607 — git off PATH, as everywhere in tools/
    return name


@pytest.mark.skipif(sys.platform == "win32", reason="the gate runs on the WSL2 side only")
def test_a_sound_shell_subject_module_clears_the_floor(tmp_path: Path) -> None:
    name = _throwaway(tmp_path, SOUND_TESTS)
    verdict = smoke_tool.smoke(tmp_path, name, shell_cap=8, shell_budget=180.0, rows={})
    assert verdict.arm == "shell"
    assert verdict.subject == "spike/toll.sh"
    assert verdict.ok, f"{verdict}: {[str(m) for m in verdict.survivors]}"


@pytest.mark.skipif(sys.platform == "win32", reason="the gate runs on the WSL2 side only")
def test_a_vacuous_shell_subject_module_is_red(tmp_path: Path) -> None:
    # #246's acceptance: a module that asserts nothing has no subject on either
    # arm, and "no subject" has been a red in its own right since ADR-0064.
    name = _throwaway(tmp_path, VACUOUS_TESTS)
    verdict = smoke_tool.smoke(tmp_path, name, shell_cap=8, shell_budget=180.0, rows={})
    assert not verdict.ok
    assert verdict.subject is None
    assert "no subject" in verdict.reason


@pytest.mark.skipif(sys.platform == "win32", reason="the gate runs on the WSL2 side only")
def test_a_module_that_drives_the_script_but_asserts_nothing_about_it_is_red(
    tmp_path: Path,
) -> None:
    # The harder half of #246's acceptance, and the one that sets `SHELL_FLOOR`:
    # this module runs every branch of the subject and asserts only that
    # something came back. It has a subject — it really does execute the script —
    # so the vacuity red above cannot catch it, and only the floor can.
    name = _throwaway(tmp_path, WEAK_TESTS)
    verdict = smoke_tool.smoke(tmp_path, name, shell_cap=8, shell_budget=180.0, rows={})
    assert verdict.arm == "shell"
    assert verdict.subject == "spike/toll.sh"
    assert not verdict.ok, f"{verdict}: killed {verdict.killed}/{verdict.run}"
