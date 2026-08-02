"""The host handle the tier runs through (issue #51, ADR-0032).

ADR-0032 adopts a second machine whose plumbing cannot be built before the metal
exists, and commissions the *seam* now: every host-touching operation names a
handle rather than this machine, `verdict.json` carries the host from day one,
and the play-session guard is asked per host and only of hosts a human plays on.

What can be asserted without a second machine is exactly what the seam claims:
that the handle exists, that it is *read* by the things that touch a host, that
an unknown host is refused rather than quietly run here, and that the guard's
gate is the host's role rather than a global. The last one matters most —
guarding the tier's own client against the tier would stop every run that used
it, and a seam whose gate nobody reads is decoration whose failure mode is a
green run on the wrong machine (ADR-0028's rule, one level up).

The pool's own rig is reused rather than rebuilt: the host seam is threaded
through the pool runner, so the honest place to watch it is a pool run.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import TYPE_CHECKING

from conftest import REPO
from test_pool_slots import EXIT_INFRA_UNAVAILABLE, executable, pool_json, pool_run

if TYPE_CHECKING:
    from pathlib import Path

HOSTS_SH = REPO / "spike" / "hosts.sh"
RUN_SH = REPO / "spike" / "run.sh"
BASH = shutil.which("bash") or "/bin/bash"

# A Windows process list with the human's game in it: the guard's stop case. It
# records that it was asked, because half of what is under test here is a guard
# that must *not* be asked of a host the tier owns.
TASKLIST_RUNNING = """#!/usr/bin/env bash
printf 'asked\\n' >>"$CTI_TEST_TASKLIST_CALLS"
printf 'arma3_x64.exe    1234 Console    1    2,000 K\\n'
"""


def hosts_sh(script: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run a snippet with `spike/hosts.sh` sourced."""
    # S603: this repo's own library, with a script this test wrote.
    return subprocess.run(  # noqa: S603
        [BASH, "-c", f'source "{HOSTS_SH}"\n{script}'],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, **(env or {})},
    )


# ------------------------------------------------------------------- the table


def test_the_tier_knows_one_host_and_it_is_the_humans() -> None:
    """One value today, and the role that decides whether the guard applies.

    Machine B becomes a second row here rather than a rewrite of the runner —
    which is the whole claim the seam makes.
    """
    result = hosts_sh('cti_host_role local; cti_host_transport local; echo "${!CTI_HOST_ROLE[*]}"')
    assert result.stdout.split() == ["human", "null", "local"], result.stderr


def test_an_unknown_host_is_refused_by_the_handle() -> None:
    result = hosts_sh("cti_host_resolve", env={"CTI_TIER_HOST": "bravo"})
    assert result.returncode == EXIT_INFRA_UNAVAILABLE
    assert "no host named 'bravo'" in result.stderr


def test_no_transport_is_built_and_the_seam_says_so_rather_than_running_here() -> None:
    """The one failure the seam exists to make impossible.

    A `cti_host_exec` that fell back to this machine for a host it cannot reach
    would run machine B's work here and report it as machine B's. So the
    fallback is a refusal, asserted against a host injected past the registry.
    """
    marker = "ran-here"
    result = hosts_sh(
        "CTI_HOST_ROLE[bravo]=tier; CTI_HOST_TRANSPORT[bravo]=ssh\n"
        f'cti_host_exec bravo echo "{marker}"'
    )
    assert result.returncode == EXIT_INFRA_UNAVAILABLE
    assert marker not in result.stdout
    assert "no transport to 'bravo'" in result.stderr


# -------------------------------------------------------------------- the guard


def test_the_guard_is_asked_of_a_host_a_human_plays_on(tmp_path: Path) -> None:
    """Unchanged behaviour for the one host that exists: a live game is a stop."""
    calls = tmp_path / "calls"
    result = hosts_sh(
        "cti_host_guard local",
        env={
            "CTI_WINDOWS_TASKLIST": str(executable(tmp_path / "tasklist.sh", TASKLIST_RUNNING)),
            "CTI_TEST_TASKLIST_CALLS": str(calls),
        },
    )
    assert result.returncode == EXIT_INFRA_UNAVAILABLE
    assert "failure_class=infra_unavailable host=local" in result.stderr
    assert calls.read_text().strip() == "asked"


def test_a_host_the_tier_owns_is_not_guarded_against_the_tier(tmp_path: Path) -> None:
    """ADR-0032's gate: the guard protects a person, and runs only where one is.

    Machine B's headed client belongs to the tier. Asking "is a game running on
    that host?" of it would answer yes on every run that used it and stop the
    corpus — guarding the tier's own client against the tier. So the guard is
    gated on the role, and a host whose role is not `human` is never asked.
    """
    calls = tmp_path / "calls"
    result = hosts_sh(
        "CTI_HOST_ROLE[bravo]=tier; CTI_HOST_TRANSPORT[bravo]=null; cti_host_guard bravo",
        env={
            "CTI_WINDOWS_TASKLIST": str(executable(tmp_path / "tasklist.sh", TASKLIST_RUNNING)),
            "CTI_TEST_TASKLIST_CALLS": str(calls),
        },
    )
    assert result.returncode == 0, result.stderr
    assert not calls.exists(), "the tier's own host was asked whether a human was playing on it"


# --------------------------------------------------------------- the pool runner


def test_a_pool_run_aimed_at_an_unknown_host_launches_nothing(tmp_path: Path) -> None:
    """Refused before a lock, a port or a world — and refused as not-a-result."""
    result = pool_run(tmp_path, "--slots", "3", extra_env={"CTI_TIER_HOST": "bravo"})
    assert result.returncode == EXIT_INFRA_UNAVAILABLE, result.stderr[-4000:]
    assert "failure_class=infra_unavailable" in result.stderr
    assert "host=bravo" in result.stderr
    assert not (tmp_path / "trace.tsv").exists(), "a probe ran on a host the tier cannot reach"
    assert not sorted((tmp_path / "state").rglob("*-pool")), "evidence was written for a non-run"


def test_the_host_reaches_the_run_that_executes_on_it(tmp_path: Path) -> None:
    """#44's rule, one level up: a host boundary is only real where something reads it.

    A `host` field written by the parent out of its own variable would say
    `local` whatever machine the world came up on. What makes it a boundary is
    that the handle travels to the launch and the run records what it received.
    """
    pool_run(tmp_path, "--slots", "2")
    assert pool_json(tmp_path)["host"] == "local"
    checked = 0
    for results in (tmp_path / "state" / "runs").glob("*/results.env"):
        recorded = dict(
            line.split("=", 1) for line in results.read_text().splitlines() if "=" in line
        )
        if "tier_host" not in recorded:
            continue
        verdict = json.loads((results.parent / "verdict.json").read_text())
        assert recorded["tier_host"] == verdict["host"] == "local"
        checked += 1
    assert checked > 0, "no run recorded the host it ran on"


def test_a_run_refused_by_the_guard_still_names_the_host(tmp_path: Path) -> None:
    """The first question asked of an `infra_unavailable` is which machine refused.

    `run.sh` recorded the host well after the guard, so the verdicts most about a
    host — the ones that never got past it — were the ones that did not name it.
    """
    out = tmp_path / "out"
    out.mkdir()
    env = {
        **os.environ,
        "CTI_SPIKE_OUT": str(out),
        "CTI_WINDOWS_TASKLIST": str(executable(tmp_path / "tasklist.sh", TASKLIST_RUNNING)),
        "CTI_TEST_TASKLIST_CALLS": str(tmp_path / "calls"),
        "CTI_TIER_SLOT": "2",
    }
    # S603: this repo's own harness, against a stub this test wrote.
    subprocess.run(  # noqa: S603
        [BASH, str(RUN_SH), "--regress"], capture_output=True, text=True, check=False, env=env
    )
    recorded = dict(
        line.split("=", 1) for line in (out / "results.env").read_text().splitlines() if "=" in line
    )
    assert recorded["verdict"] == "FAIL"
    assert recorded["failure_class"] == "infra_unavailable"
    assert recorded["tier_host"] == "local"
    assert recorded["tier_slot"] == "2"


def test_an_unknown_host_is_refused_by_the_harness_too(tmp_path: Path) -> None:
    """`just probe` reaches `run.sh` directly, so the handle is checked there too."""
    out = tmp_path / "out"
    out.mkdir()
    env = {
        **os.environ,
        "CTI_SPIKE_OUT": str(out),
        "CTI_TIER_HOST": "bravo",
        "CTI_WINDOWS_TASKLIST": str(executable(tmp_path / "tasklist.sh", TASKLIST_RUNNING)),
        "CTI_TEST_TASKLIST_CALLS": str(tmp_path / "calls"),
    }
    # S603: this repo's own harness.
    subprocess.run(  # noqa: S603
        [BASH, str(RUN_SH), "--regress"], capture_output=True, text=True, check=False, env=env
    )
    recorded = dict(
        line.split("=", 1) for line in (out / "results.env").read_text().splitlines() if "=" in line
    )
    assert recorded["failure_class"] == "infra_unavailable"
    assert "bravo" in recorded["failure_detail"]
    assert not (tmp_path / "calls").exists(), "a run aimed at an unreachable host touched a host"
