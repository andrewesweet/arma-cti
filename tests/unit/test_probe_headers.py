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


@pytest.mark.parametrize("path", PROBES, ids=lambda p: p.stem)
def test_probe_ends_by_logging_its_completion(path: Path) -> None:
    """The runner waits on `probe_done`; a probe that never logs it is a timeout."""
    body = path.read_text(encoding="utf-8")
    assert "probe_done" in body, f"{path.name} logs no probe_done line for the runner to wait on"


@pytest.mark.parametrize("path", PROBES, ids=lambda p: p.stem)
def test_env_header_is_assignments(path: Path) -> None:
    env = header_block(path).get("env")
    if env is not None:
        for assignment in env.split():
            assert re.fullmatch(r"[A-Z_][A-Z0-9_]*=\S*", assignment), (
                f"{path.name}: env: must be KEY=VALUE pairs, got {assignment!r}"
            )
