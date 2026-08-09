"""The mutation smoke's Rust rung: when it runs, and how it reads a verdict (#246).

Two things are worth testing here and one is not.

Worth testing: **when** the rung runs, because it is gated on the diff and a rung
that ran on every landing would cost 52.7 s each time for a crate that changes in
one commit in seventy; and **how** a `cargo-mutants` run is read back, because
that reading deliberately disagrees with the engine in two places — a timeout is
a kill here rather than a problem, and an unviable mutant is excluded from the
count rather than scored. Both are read out of the outcome files rather than off
the exit code, and the fixtures below are those files.

Not worth testing here: that `cargo-mutants` mutates Rust correctly. That is the
engine's job, it is pinned by `just prereqs tools`, and a test asserting it would
take 52.7 s to say what the engine's own suite says. The measurement that it
catches a real weakening — gutting two `assert_eq!`s in the shim leaves
`replace match guard (c as u32) < 0x20 with false in escape_json` alive — is in
`docs/research/mutation-shell-arm.md` §6, with the numbers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from conftest import load_tool

if TYPE_CHECKING:
    from pathlib import Path
    from types import ModuleType

rust_tool: ModuleType = load_tool("mutation_rust")


def _outcome_dir(root: Path, **files: str) -> Path:
    out = root / "mutants.out"
    out.mkdir(parents=True)
    for name, body in files.items():
        (out / f"{name}.txt").write_text(body, encoding="utf-8")
    return root


# --- when the rung runs ------------------------------------------------------


@pytest.mark.parametrize(
    ("changed", "expected"),
    [
        (["extension/src/lib.rs"], True),
        (["extension/Cargo.toml"], True),
        (["src/cti_daemon/daemon.py", "extension/src/lib.rs"], True),
        (["src/cti_daemon/daemon.py"], False),
        ([], False),
        # Not a prefix match on the name: `extensions/` is not `extension/`.
        (["extensions/other.rs"], False),
    ],
)
def test_the_rung_runs_only_when_the_shim_changed(changed: list[str], *, expected: bool) -> None:
    assert rust_tool.in_scope(changed) is expected


# --- reading a verdict -------------------------------------------------------


def test_a_run_with_nothing_missed_is_green(tmp_path: Path) -> None:
    output = _outcome_dir(tmp_path, caught="a\nb\n", missed="", timeout="", unviable="c\n")
    outcome = rust_tool.read_outcome(output, 52.7)
    assert outcome.ok
    assert outcome.run == 2


def test_a_missed_mutant_is_red_and_named(tmp_path: Path) -> None:
    output = _outcome_dir(tmp_path, caught="a\n", missed="src/lib.rs:266: replace guard\n")
    outcome = rust_tool.read_outcome(output, 1.0)
    assert not outcome.ok
    assert outcome.missed == ("src/lib.rs:266: replace guard",)
    assert "src/lib.rs:266" in rust_tool.report(outcome)


def test_a_timeout_counts_as_a_kill_rather_than_a_problem(tmp_path: Path) -> None:
    # cargo-mutants exits 3 on this and calls it a problem. This project's rule is
    # the opposite and is unchanged from the Python arm: the mutant changed what
    # the code does so plainly that the tests could not finish saying so. The
    # shim has exactly one — removing `Connection::arm`'s read deadline.
    output = _outcome_dir(tmp_path, caught="a\n", missed="", timeout="src/lib.rs:192: arm\n")
    outcome = rust_tool.read_outcome(output, 1.0)
    assert outcome.ok
    assert outcome.run == 2


def test_an_unviable_mutant_is_left_out_of_the_count_entirely(tmp_path: Path) -> None:
    # 18 of the shim's 53 do not compile. Scoring them as kills would inflate the
    # verdict; scoring them as survivors would red a tree nobody weakened.
    output = _outcome_dir(tmp_path, caught="a\n", missed="", unviable="b\nc\nd\n")
    outcome = rust_tool.read_outcome(output, 1.0)
    assert outcome.run == 1
    assert outcome.unviable == 3
    assert outcome.ok


def test_a_survivor_on_the_named_list_is_not_a_finding(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001 — pytest's own fixture type adds nothing here
    # The escape, and deliberately the only one: a named mutant with its reason
    # beside it, in the diff. It ships empty because nothing survives today.
    monkeypatch.setattr(rust_tool, "SURVIVES_BY_DESIGN", {"src/lib.rs:1: x": "a reason"})
    output = _outcome_dir(tmp_path, caught="a\n", missed="src/lib.rs:1: x\n")
    assert rust_tool.read_outcome(output, 1.0).ok


def test_the_shipped_escape_list_is_empty() -> None:
    # A measurement rather than an aspiration: 0 of 35 viable mutants survived on
    # the tree this landed against, so there was nothing to excuse.
    assert rust_tool.SURVIVES_BY_DESIGN == {}


def test_a_run_that_wrote_no_outcome_at_all_is_a_refusal_not_a_pass(tmp_path: Path) -> None:
    # A check that could not run is not a check that passed (#41), and an empty
    # `missed.txt` that never existed reads identically to a clean sweep.
    with pytest.raises(rust_tool.Refusal, match="did not get as far as a verdict"):
        rust_tool.read_outcome(tmp_path, 1.0)


def test_a_blank_line_in_an_outcome_file_is_not_a_mutant(tmp_path: Path) -> None:
    output = _outcome_dir(tmp_path, caught="a\n\n", missed="\n")
    outcome = rust_tool.read_outcome(output, 1.0)
    assert outcome.caught == 1
    assert outcome.ok


def test_the_verdict_line_names_the_arm_and_the_arithmetic(tmp_path: Path) -> None:
    output = _outcome_dir(tmp_path, caught="a\nb\n", missed="c\n", unviable="d\n")
    line = str(rust_tool.read_outcome(output, 52.7))
    assert line.startswith("RED ")
    assert "arm=rust" in line
    assert "killed=2/3" in line
    assert "unviable=1" in line


def test_a_green_verdict_says_nothing_further(tmp_path: Path) -> None:
    output = _outcome_dir(tmp_path, caught="a\n", missed="")
    assert rust_tool.report(rust_tool.read_outcome(output, 1.0)) == ""


def test_the_json_rendering_carries_the_numbers(tmp_path: Path) -> None:
    output = _outcome_dir(tmp_path, caught="a\n", missed="b\n", timeout="c\n", unviable="d\n")
    rendered = rust_tool.outcome_json(rust_tool.read_outcome(output, 12.34))
    assert '"caught": 1' in rendered
    assert '"ok": false' in rendered
    assert '"seconds": 12.3' in rendered
