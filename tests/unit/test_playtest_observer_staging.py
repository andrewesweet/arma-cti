"""When `spike/run.sh` stages the playtest observer, and when it must not (#178).

Playtest 0001 asked for a Zeus-style observer so feedback could reach past what
the Commander's map shows. The observer rides staging, not a boot-line knob: a
harness extra from `spike/playtest/` is what marks a session as a human one, so
that is exactly when `spike/playtest/observer.sqf` is appended to the generated
harness — and #178's boundary is the other half: the regression corpus stages
probes from `spike/probes/`, and a curator must not be present in anything the
corpus boots.

Asserted here rather than in the Arma tier because the rule is the harness's own
arithmetic over a path — which file gets appended to `harness.sqf` — and a
dedicated server is not needed to read a staged file. Same stub world as
`test_run_verdict`, whose helper this borrows.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from conftest import REPO
from test_run_verdict import run_with_lines

if TYPE_CHECKING:
    from pathlib import Path

OBSERVER = REPO / "spike" / "playtest" / "observer.sqf"

# The line the observer logs when its sweep is up — grepping the staged harness
# for it is grepping for the observer itself, not for a lookalike comment.
OBSERVER_MARK = "playtest_observer_watching"


def staged_harness(tmp_path: Path) -> str:
    """Return the harness the run staged, whichever mission it staged it into."""
    harnesses = list((tmp_path / "out" / "mission").glob("*/harness.sqf"))
    assert len(harnesses) == 1, f"expected one staged mission, found {harnesses}"
    return harnesses[0].read_text(encoding="utf-8")


def test_a_playtest_fixture_brings_the_observer_with_it(tmp_path: Path) -> None:
    """A human session gets the observer without a second thing to remember."""
    records = run_with_lines(
        tmp_path,
        ["measurement thing=1"],
        extra_env={"CTI_HARNESS_EXTRA": str(REPO / "spike" / "playtest" / "session-hold.sqf")},
    )
    assert records["verdict"] == "PASS", (
        f"{records.get('failure_class')}: {records.get('failure_detail')}"
    )
    assert records["playtest_observer"] == "staged"
    assert OBSERVER_MARK in staged_harness(tmp_path)


def test_a_probe_stages_no_observer(tmp_path: Path) -> None:
    """#178's boundary: nothing the regression corpus boots contains a curator.

    The corpus hands `run.sh` extras from `spike/probes/`, so a probe-shaped
    extra arriving without an observer is that boundary holding at the seam
    where it is enforced.
    """
    records = run_with_lines(
        tmp_path,
        ["measurement thing=1"],
        extra_env={"CTI_HARNESS_EXTRA": str(REPO / "spike" / "probes" / "bareworld.sqf")},
    )
    assert records["verdict"] == "PASS", (
        f"{records.get('failure_class')}: {records.get('failure_detail')}"
    )
    assert "playtest_observer" not in records
    assert OBSERVER_MARK not in staged_harness(tmp_path)


def test_a_run_with_no_extra_stages_no_observer(tmp_path: Path) -> None:
    """A bare world is a join test, not a human session; it gets no curator."""
    records = run_with_lines(tmp_path, ["measurement thing=1"])
    assert records["verdict"] == "PASS"
    assert "playtest_observer" not in records
    assert OBSERVER_MARK not in staged_harness(tmp_path)


def test_the_observer_guards_against_being_staged_twice(tmp_path: Path) -> None:
    """Naming observer.sqf as the fixture itself stays harmless.

    The path rule would stage it once as the extra and once as the observer;
    the file's own `isNil` latch is what makes the second copy inert, and this
    pins that the latch exists and that the double-staging is the shape it
    guards.
    """
    records = run_with_lines(
        tmp_path,
        ["measurement thing=1"],
        extra_env={"CTI_HARNESS_EXTRA": str(OBSERVER)},
    )
    assert records["verdict"] == "PASS"
    assert records["playtest_observer"] == "staged"
    harness = staged_harness(tmp_path)
    assert harness.count(OBSERVER_MARK) == 2, "expected the extra copy and the staged copy"
    assert 'isNil "cti_playtest_observer"' in OBSERVER.read_text(encoding="utf-8")
