"""The probe corpus's machine-readable headers (issue #23, ADR-0016).

`spike/regress.sh` refuses to bring a world up if a selected probe's header does
not parse. That refusal costs a run to discover; this costs a second, and it is
the only tier that can say "every probe in the corpus", not just the selected
ones. The parsing rules here and in the runner's `header_of` are the same rules,
deliberately duplicated: bash is what has to read them in-world, and Python is
what can gate them before anyone runs anything.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROBE_DIR = Path(__file__).resolve().parents[2] / "spike" / "probes"
PROBES = sorted(PROBE_DIR.glob("*.sqf"))
# The scaffolding staged ahead of every probe. Not a probe — it asserts nothing
# and corpus membership is by directory — but since #193 it writes two of the
# lines the runner scores, so the tests about those lines have to read it too.
PRELUDE = Path(__file__).resolve().parents[2] / "spike" / "probe-prelude.sqf"

KNOWN_KEYS = {"probe", "issues", "window", "env", "expect", "quarantined"}

# The classes a probe may declare itself red against, from CLAUDE.md's table.
FAILURE_CLASSES = {
    "assertion_failed",
    "timeout",
    "node_crashed",
    "oracle_disagreement",
    "infra_unavailable",
    "engine_drift",
    "schema_stale",
    "flake_quarantine",
}


def header_block(path: Path) -> dict[str, str]:
    """Read the leading comment block's `key: value` lines.

    Leading block only. A `window:` quoted deeper in a probe's prose is
    discussion, not declaration, and the runner reads it the same way.
    """
    found: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("//"):
            break
        stripped = line[2:].strip()
        match = re.match(r"^([a-z]+):\s*(.*)$", stripped)
        if match and match.group(1) in KNOWN_KEYS and match.group(1) not in found:
            found[match.group(1)] = match.group(2).strip()
    return found


# The probes that drive the one headed client on the one Windows host, read off
# the `env:` header the way `spike/regress.sh` reads it (`host_probe`). Here
# because this module is where the corpus's headers are parsed, and its two
# consumers — the pool's serial tail and the machine-wide client lock — then
# have one derived home rather than a list each. `test_pool_slots` already
# derived it and `test_client_lock` named two probes by hand; by the time #157
# looked there were six, which is the drift a second declaration produces (#123,
# #172, #188, #189 each added one).
HOST_PROBES = sorted(
    path.stem for path in PROBES if "CTI_WINDOWS_CLIENT=1" in header_block(path).get("env", "")
)


def test_corpus_is_not_empty() -> None:
    assert PROBES, f"no probes found under {PROBE_DIR}"


@pytest.mark.parametrize("path", PROBES, ids=lambda p: p.stem)
def test_probe_declares_its_own_name(path: Path) -> None:
    assert header_block(path).get("probe") == path.stem


@pytest.mark.parametrize("path", PROBES, ids=lambda p: p.stem)
def test_probe_declares_a_numeric_window(path: Path) -> None:
    window = header_block(path).get("window", "")
    assert window.isdigit(), f"{path.name}: window: must be whole seconds, got {window!r}"
    assert int(window) > 0


@pytest.mark.parametrize("path", PROBES, ids=lambda p: p.stem)
def test_probe_names_the_issues_that_motivated_it(path: Path) -> None:
    issues = header_block(path).get("issues", "")
    assert re.fullmatch(r"\d+(\s*,\s*\d+)*", issues), (
        f"{path.name}: issues: must be a comma list of issue numbers, got {issues!r}"
    )


@pytest.mark.parametrize("path", PROBES, ids=lambda p: p.stem)
def test_expected_class_is_one_the_table_knows(path: Path) -> None:
    expect = header_block(path).get("expect")
    if expect is not None:
        assert expect in FAILURE_CLASSES


@pytest.mark.parametrize("path", PROBES, ids=lambda p: p.stem)
def test_quarantine_names_an_issue(path: Path) -> None:
    """A quarantine line without an issue number is out of policy (ADR-0016).

    The enforcement is that it does not parse — here, and in the runner.
    """
    quarantined = header_block(path).get("quarantined")
    if quarantined is not None:
        assert re.fullmatch(r"#\d+", quarantined), (
            f"{path.name}: quarantined: must name an open issue as #N, got {quarantined!r}"
        )


# The line itself, from the quote the log call opens it with — not the closing
# one, since several probes carry fields after the token. A probe that only
# mentions `probe_done` in its prose has not logged one, and the loose substring
# this replaces could not tell the two apart.
DONE_LINE = re.compile(r'"CTI\|\w*probe_done')


@pytest.mark.parametrize("path", PROBES, ids=lambda p: p.stem)
def test_probe_ends_by_logging_its_completion(path: Path) -> None:
    """The runner waits on `probe_done`; a probe that never logs it is a timeout.

    Two ways to log it since #193. A probe writes the line itself, or it ends
    through `cti_probe_fnc_done` — the prelude's shared ending, which reports
    every leg the probe never reached and then writes the line under the prefix
    the probe declared. The prefix is what makes the shared line this probe's, so
    a probe that takes the shared ending has to have named itself.
    """
    body = path.read_text(encoding="utf-8")
    if "cti_probe_fnc_done" in body:
        assert "cti_probe_fnc_legsOwed" in body, (
            f"{path.name} ends through the shared ending without naming itself: "
            "cti_probe_fnc_legsOwed is what sets the prefix its done line is written under"
        )
        return
    assert DONE_LINE.search(body), f"{path.name} logs no probe_done line for the runner to wait on"


def test_the_shared_ending_writes_the_line_the_runner_waits_on() -> None:
    """The other half of the test above, where the line now lives (#193).

    Six probes hand their completion to the prelude, so a typo in this one format
    string is six probes the runner waits out to their windows.
    """
    assert re.search(r'"CTI\|%1_probe_done"', PRELUDE.read_text(encoding="utf-8")), (
        "cti_probe_fnc_done no longer writes a line CTI_HARNESS_AWAIT=probe_done matches"
    )


@pytest.mark.parametrize("path", PROBES, ids=lambda p: p.stem)
def test_a_probe_with_a_client_leg_turns_it_on_in_the_corpus(path: Path) -> None:
    """ADR-0037's vacuity rule at the one place it can be gated cheaply (#116).

    A probe that reads `CTI_PROBE_CLIENT` has a leg only a headed client can
    exercise, and the corpus run must supply one. `human-commander` left it at
    the zero default and went green in every corpus run with the only leg that
    crosses the machine boundary never run. Optional legs default on, or they
    are legs nobody runs.
    """
    body = path.read_text(encoding="utf-8")
    if 'getVariable ["CTI_PROBE_CLIENT"' not in body:
        return
    settings = dict(
        assignment.split("=", 1) for assignment in header_block(path).get("env", "").split()
    )
    assert settings.get("CTI_WINDOWS_CLIENT") == "1", (
        f"{path.name} drives a headed client but its env: header does not ask for one"
    )
    assert int(settings.get("CTI_PROBE_CLIENT", "0")) > 0, (
        f"{path.name} leaves its client leg off by default; the corpus would run it vacuously"
    )


LEG_LINE = re.compile(r"CTI\|LEG name=\S+ status=(ran|unverified)")


@pytest.mark.parametrize("path", [*PROBES, PRELUDE], ids=lambda p: p.stem)
def test_leg_lines_use_the_grammar_the_runner_parses(path: Path) -> None:
    """`spike/run.sh` scores these lines; a typo in one is a leg it cannot see.

    The prelude is read alongside the corpus because six probes' leg lines are
    written there now (#193), and a test that only read `spike/probes/` would
    have gone quietly green over the move.
    """
    for line in path.read_text(encoding="utf-8").splitlines():
        if "CTI|LEG" not in line:
            continue
        assert LEG_LINE.search(line), f"{path.name}: unparseable leg line: {line.strip()}"


@pytest.mark.parametrize("path", PROBES, ids=lambda p: p.stem)
def test_env_header_is_assignments(path: Path) -> None:
    env = header_block(path).get("env")
    if env is not None:
        for assignment in env.split():
            assert re.fullmatch(r"[A-Z_][A-Z0-9_]*=\S*", assignment), (
                f"{path.name}: env: must be KEY=VALUE pairs, got {assignment!r}"
            )
