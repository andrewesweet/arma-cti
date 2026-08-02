"""Every path that brings the Arma tier up asks the two guards first (issue #68).

The tier is single-occupancy on a machine the human also plays on, and two
things protect that: `spike/tier-lock.sh` serialises agents, and
`spike/host-guard.sh` refuses to load the machine underneath a live play
session. Both were asked by `just regress` and by neither `just probe` nor `just
spike` — the guard because `spike/run.sh` only asked it when it meant to *drive*
the Windows host, the lock because the `spike` recipe called `run.sh` bare.

Tested here rather than in the Arma tier because a guard is only worth having if
its refusal is exercised, and its refusal is the one branch no in-world run
takes. The Windows tool is substituted through `CTI_WINDOWS_TASKLIST`, the same
seam `tests/unit/test_host_guard.py` uses.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
from typing import TYPE_CHECKING

import pytest
from conftest import REPO

if TYPE_CHECKING:
    from pathlib import Path

RUN = REPO / "spike" / "run.sh"
TIER_LOCK = REPO / "spike" / "tier-lock.sh"
JUSTFILE = REPO / "justfile"
BASH = shutil.which("bash") or "/bin/bash"

EXIT_INFRA_UNAVAILABLE = 5

TASKLIST_ABSENT = "INFO: No tasks are running which match the specified criteria.\n"
TASKLIST_PRESENT = (
    "\n"
    "Image Name                     PID Session Name        Session#    Mem Usage\n"
    "========================= ======== ================ =========== ============\n"
    "arma3_x64.exe                24188 Console                    1  3,412,904 K\n"
)


def _tasklist(tmp_path: Path, listing: str) -> Path:
    path = tmp_path / "tasklist.sh"
    path.write_text(f"#!/usr/bin/env bash\nprintf '%s' {listing!r}\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _run_spike(tmp_path: Path, listing: str, *args: str) -> subprocess.CompletedProcess[str]:
    """`spike/run.sh` far enough to see the pre-flight, and no further.

    `CTI_SERVER_DIR` points at an empty directory, so the first thing after the
    guard is a refusal of its own — which is what makes "it got past the guard"
    observable without a server install.
    """
    env = dict(
        os.environ,
        CTI_WINDOWS_TASKLIST=str(_tasklist(tmp_path, listing)),
        CTI_SPIKE_OUT=str(tmp_path / "out"),
        CTI_SERVER_DIR=str(tmp_path / "no-server"),
    )
    # S603: this repo's own script, with paths this test just wrote.
    return subprocess.run(  # noqa: S603
        [BASH, str(RUN), *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def _results(tmp_path: Path) -> dict[str, str]:
    text = (tmp_path / "out" / "results.env").read_text()
    return dict(line.split("=", 1) for line in text.splitlines() if "=" in line)


@pytest.mark.parametrize("mode", ["", "--hold", "--regress"])
def test_a_live_play_session_stops_every_bringup_mode(tmp_path: Path, mode: str) -> None:
    """#68: the probe and spike paths took the machine without asking."""
    args = [mode] if mode else []
    result = _run_spike(tmp_path, TASKLIST_PRESENT, *args)
    assert result.returncode != 0
    results = _results(tmp_path)
    assert results["verdict"] == "FAIL"
    assert results["failure_class"] == "infra_unavailable"
    assert "play session" in results["failure_detail"]


def test_the_refusal_happens_before_anything_is_launched(tmp_path: Path) -> None:
    result = _run_spike(tmp_path, TASKLIST_PRESENT)
    assert result.returncode != 0
    out = tmp_path / "out"
    assert not (out / "server.stdout.log").exists()
    assert not (out / "daemon.log").exists()
    assert not (out / "mission").exists()


def test_a_process_list_that_cannot_be_read_stops_too(tmp_path: Path) -> None:
    """A check that could not run is not a check that passed."""
    env = dict(
        os.environ,
        CTI_WINDOWS_TASKLIST=str(tmp_path / "there-is-no-tasklist-here.exe"),
        CTI_SPIKE_OUT=str(tmp_path / "out"),
        CTI_SERVER_DIR=str(tmp_path / "no-server"),
    )
    # S603: this repo's own script, with paths this test just wrote.
    result = subprocess.run(  # noqa: S603
        [BASH, str(RUN)], env=env, capture_output=True, text=True, check=False, timeout=120
    )
    assert result.returncode != 0
    results = _results(tmp_path)
    assert results["failure_class"] == "infra_unavailable"
    assert "cannot check" in results["failure_detail"]


def test_a_free_host_gets_past_the_guard(tmp_path: Path) -> None:
    """The green branch, asserted at the *next* refusal rather than at a pass.

    Without this the guard could be a permanent stop and the tests above would
    all still be green.
    """
    result = _run_spike(tmp_path, TASKLIST_ABSENT)
    assert result.returncode != 0
    results = _results(tmp_path)
    assert results["windows_host_free"] == "true"
    assert results["failure_class"] == "infra_unavailable"
    assert "server binary missing" in results["failure_detail"]


# ------------------------------------------------------------------- the lock
def recipe_body(name: str) -> str:
    """One recipe out of the justfile, comments and dependencies included."""
    text = JUSTFILE.read_text()
    match = re.search(rf"^{name}(?: [^\n]*)?:[^\n]*\n((?:[ \t]+[^\n]*\n|\n)*)", text, re.MULTILINE)
    assert match is not None, f"no recipe named {name} in the justfile"
    return match.group(1)


@pytest.mark.parametrize("recipe", ["spike", "probe", "cycle-spike"])
def test_every_bringup_recipe_serialises_on_the_tier_lock(recipe: str) -> None:
    assert "tier-lock.sh" in recipe_body(recipe), (
        f"`just {recipe}` brings the tier up without taking the lock"
    )


def test_regress_takes_its_locks_in_the_script_rather_than_the_recipe() -> None:
    """The one exemption, and the reason it is one: selection runs first.

    Since #47 the runner takes one lock per slot rather than the single tier
    lock, so what the recipe must not do is wrap it in `tier-lock.sh` — that
    would take slot 0 for the whole pool and reduce N to one.
    """
    assert "tier-lock.sh" not in recipe_body("regress")
    assert "cti_slot_acquire" in (REPO / "spike" / "regress.sh").read_text()


def test_a_held_lock_is_infra_unavailable_and_runs_nothing(tmp_path: Path) -> None:
    """The collision `just spike` used to walk straight through.

    The lock a hand run takes is slot 0's (#47): a hand run uses ~/arma3server on
    2402-2406, which *is* slot 0, so a pool holding that slot and a `just probe`
    have to exclude each other on the same file rather than on two.
    """
    state = tmp_path / "state"
    env = dict(os.environ, CTI_TIER_STATE=str(state))
    ran = tmp_path / "ran"
    holder_script = (
        f"exec 9>{state}/slots/0.lock\n"
        "flock -x -n 9 || exit 3\n"
        "read -r _ < /dev/stdin\n"  # holds until this test closes stdin
    )
    (state / "slots").mkdir(parents=True)
    # S603: fixed argv, paths this test wrote.
    with subprocess.Popen(  # noqa: S603
        [BASH, "-c", holder_script], env=env, stdin=subprocess.PIPE, text=True
    ) as holder:
        try:
            # S603: this repo's own script.
            result = subprocess.run(  # noqa: S603
                [BASH, str(TIER_LOCK), "--label", "test", "--", BASH, "-c", f"touch {ran}"],
                env=env,
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )
        finally:
            assert holder.stdin is not None
            holder.stdin.close()
    assert result.returncode == EXIT_INFRA_UNAVAILABLE
    assert "failure_class=infra_unavailable" in result.stderr
    assert not ran.exists(), "the lock let a second occupant run"
