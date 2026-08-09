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
from test_run_verdict import run_with_lines, why

if TYPE_CHECKING:
    from pathlib import Path

OBSERVER = REPO / "spike" / "playtest" / "observer.sqf"

# The line the observer logs when its sweep is up — grepping the staged harness
# for it is grepping for the observer itself, not for a lookalike comment.
OBSERVER_MARK = "playtest_observer_watching"

# The same, for the half of the observer that takes the human's body out of the
# world while he flies (#190). Asserted separately from OBSERVER_MARK because
# the boundary #178 draws is about what the corpus boots, and a body watcher
# that arrived in a probe's world by some other route would be inside that
# boundary while the mark above stayed clean.
BODY_MARK = "playtest_observer_body_watching"


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
    assert records["verdict"] == "PASS", why(records)
    assert records["playtest_observer"] == "staged"
    harness = staged_harness(tmp_path)
    assert OBSERVER_MARK in harness
    assert BODY_MARK in harness


def test_the_flight_fixture_brings_the_observer_with_it(tmp_path: Path) -> None:
    """#190's own fixture is a playtest file, so it gets the thing it exercises.

    `spike/playtest/observer-flight.sqf` opens and closes the curator camera on
    the client to read the body out of the world on both edges. It can only do
    that if the observer is staged beside it, and it is staged beside it for the
    same reason `session-hold.sqf` is: the directory, not a boot-line knob.
    """
    records = run_with_lines(
        tmp_path,
        ["measurement thing=1"],
        extra_env={
            "CTI_HARNESS_EXTRA": str(REPO / "spike" / "playtest" / "observer-flight.sqf"),
        },
    )
    assert records["verdict"] == "PASS", why(records)
    assert records["playtest_observer"] == "staged"
    harness = staged_harness(tmp_path)
    assert OBSERVER_MARK in harness
    assert BODY_MARK in harness


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
    assert records["verdict"] == "PASS", why(records)
    assert "playtest_observer" not in records
    harness = staged_harness(tmp_path)
    assert OBSERVER_MARK not in harness
    assert BODY_MARK not in harness


def test_a_run_with_no_extra_stages_no_observer(tmp_path: Path) -> None:
    """A bare world is a join test, not a human session; it gets no curator."""
    records = run_with_lines(tmp_path, ["measurement thing=1"])
    assert records["verdict"] == "PASS", why(records)
    assert "playtest_observer" not in records
    harness = staged_harness(tmp_path)
    assert OBSERVER_MARK not in harness
    assert BODY_MARK not in harness


def test_a_probe_world_ends_at_the_probe(tmp_path: Path) -> None:
    """The corpus's world, whatever the playtest path grows next.

    The assertions above name the two marks this issue knows about, and a mark
    is only ever as good as somebody having thought to add it. This one names
    nothing: after the shared prelude, a probe's staged harness is that probe's
    own text and nothing else. Anything a later hand appends for a human session
    — this observer, its body watcher, or whatever comes after them — fails here
    without a mark being invented for it.
    """
    probe = REPO / "spike" / "probes" / "bareworld.sqf"
    records = run_with_lines(
        tmp_path, ["measurement thing=1"], extra_env={"CTI_HARNESS_EXTRA": str(probe)}
    )
    assert records["verdict"] == "PASS", why(records)

    prelude = (REPO / "spike" / "probe-prelude.sqf").read_text(encoding="utf-8")
    generated, separator, after_prelude = staged_harness(tmp_path).partition(prelude)
    assert separator, "the shared prelude is not in the staged harness"
    assert after_prelude == probe.read_text(encoding="utf-8")
    assert "playtest" not in generated


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
    # #233's flake fired on this line and left nothing behind but `'FAIL' ==
    # 'PASS'`. The staging assertions below it are arithmetic over a file this
    # run wrote, so a red here is the *run* having stopped, and its class is the
    # whole of what a reader needs.
    assert records["verdict"] == "PASS", why(records)
    assert records["playtest_observer"] == "staged"
    harness = staged_harness(tmp_path)
    assert harness.count(OBSERVER_MARK) == 2, "expected the extra copy and the staged copy"
    assert 'isNil "cti_playtest_observer"' in OBSERVER.read_text(encoding="utf-8")
