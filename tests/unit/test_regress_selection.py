"""Probe selection in `spike/regress.sh` (issue #36, ADR-0016).

Selection decides how much of the Arma tier's wall an agent spends, and the one
way it could lie is by quietly running nothing and exiting green. So it is built
as a path with nothing after it — `--list` resolves the filters, validates the
headers of what they chose, prints that and stops — and tested here, in the tier
that needs no Arma. What the runner does with the selection afterwards needs the
tier; which probes a filter picks does not.

Expectations are computed from the corpus's own headers rather than written out,
so these tests keep meaning something as probes are added.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

# Same directory, pytest's prepend import mode. The corpus and its header parser
# have one definition (`test_probe_headers`) and this module reuses it rather
# than growing a second reading of the same lines.
from test_probe_headers import PROBE_DIR, PROBES, header_block

REGRESS = Path(__file__).resolve().parents[2] / "spike" / "regress.sh"
BASH = shutil.which("bash") or "/bin/bash"

# `die` in the runner. Not a failure class — a refusal to run at all.
EXIT_REFUSED = 2


def issues_of(path: Path) -> set[str]:
    return {tok.strip() for tok in header_block(path).get("issues", "").split(",") if tok.strip()}


ALL_NAMES = sorted(p.stem for p in PROBES)
ALL_ISSUES = sorted({issue for p in PROBES for issue in issues_of(p)}, key=int)


def run(*args: str, tmp_path: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    if tmp_path is not None:
        env["CTI_TIER_STATE"] = str(tmp_path / "state")
    # S603: this repo's own script, with arguments this test wrote.
    return subprocess.run(  # noqa: S603
        [BASH, str(REGRESS), "--list", *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def selected(*args: str) -> list[str]:
    result = run(*args)
    assert result.returncode == 0, result.stderr
    return result.stdout.split()


def test_no_filter_selects_the_whole_corpus() -> None:
    assert selected() == ALL_NAMES


def test_list_is_a_dry_run_that_takes_no_lock(tmp_path: Path) -> None:
    """No lock, no port, no evidence — which is why it is safe in this tier."""
    result = run(tmp_path=tmp_path)
    assert result.returncode == 0
    assert not (tmp_path / "state").exists()


@pytest.mark.parametrize("issue", ALL_ISSUES)
def test_issue_selects_exactly_the_probes_whose_header_names_it(issue: str) -> None:
    expected = sorted(p.stem for p in PROBES if issue in issues_of(p))
    assert selected("--issues", issue) == expected


@pytest.mark.parametrize("issue", ALL_ISSUES)
def test_issue_matching_is_on_whole_numbers(issue: str) -> None:
    """`--issues 3` must never select a probe written for #32.

    Substring matching would be the quiet kind of wrong: a filter that selects
    too much still gates, but the reader believes a number that is not theirs.
    """
    for name in selected("--issues", issue):
        assert issue in issues_of(PROBE_DIR / f"{name}.sqf")


def test_unmatched_issue_is_an_error_not_an_empty_pass() -> None:
    unused = str(max(int(i) for i in ALL_ISSUES) + 10_000)
    result = run("--issues", unused)
    assert result.returncode == EXIT_REFUSED
    assert result.stdout.strip() == ""
    assert "not a pass" in result.stderr


def test_one_unmatched_issue_fails_a_spec_the_rest_of_which_matched() -> None:
    """Otherwise a typo silently shrinks the selection to the numbers that hit."""
    unused = str(max(int(i) for i in ALL_ISSUES) + 10_000)
    result = run("--issues", f"{ALL_ISSUES[0]},{unused}")
    assert result.returncode == EXIT_REFUSED
    assert unused in result.stderr


def test_names_and_issues_union_without_duplicates() -> None:
    issue = ALL_ISSUES[0]
    by_issue = selected("--issues", issue)
    other = next(name for name in ALL_NAMES if name not in by_issue)
    both = selected(other, "--issues", issue)
    assert both[0] == other, "a named probe keeps the caller's order, ahead of the filter's"
    assert sorted(both) == sorted({other, *by_issue})


def test_a_named_probe_is_not_repeated_by_an_issue_that_also_selects_it() -> None:
    name = selected("--issues", ALL_ISSUES[0])[0]
    both = selected(name, "--issues", ALL_ISSUES[0])
    assert len(both) == len(set(both))


def test_repeated_issue_flags_accumulate() -> None:
    first, second = ALL_ISSUES[0], ALL_ISSUES[1]
    assert selected("--issues", first, "--issues", second) == selected(
        "--issues", f"{first},{second}"
    )


@pytest.mark.parametrize("spec", ["", "abc", "#32", "32.5", "-4"])
def test_issues_takes_issue_numbers_and_nothing_else(spec: str) -> None:
    result = run("--issues", spec)
    assert result.returncode == EXIT_REFUSED


def test_unknown_probe_name_is_an_error() -> None:
    result = run("no-such-probe")
    assert result.returncode == EXIT_REFUSED
    assert "no such probe" in result.stderr


def test_list_reports_the_declared_window_budget() -> None:
    """A selection's cost is the reason to make one, so `--list` states it."""
    result = run("--issues", ALL_ISSUES[0])
    assert result.returncode == 0
    budget = sum(int(header_block(PROBE_DIR / f"{n}.sqf")["window"]) for n in result.stdout.split())
    assert re.search(rf"declared windows total {budget}s", result.stderr)
