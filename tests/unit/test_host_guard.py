"""The guard that protects the human's play session (issue #41).

`spike/host-guard.sh` decides whether the Arma tier may take the shared machine.
It was previously inline in `spike/regress.sh` behind `command -v tasklist.exe`,
which was false in the shells #41's runs got — so the guard never ran and every
run was permitted by a check that had not happened. Whether the WSL interop
PATH append reaches a given session varies with how the session was entered
(#180: mosh/ssh-descended shells lack it, wsl.exe-descended shells carry it),
which is the deeper reason resolution is by absolute path: a check keyed on
PATH is keyed on session ancestry.

The point of these tests is that both branches are exercised without Arma: a
Windows process list showing the game refuses, one showing it absent proceeds,
and every way of not getting an answer at all refuses too. The Windows tool is
substituted through `CTI_WINDOWS_TASKLIST`, which is the same seam the real
runners use to point at `/mnt/c/Windows/System32/tasklist.exe`.

The same seam covers `cti_windows_wait_gone` (issue #119), the teardown-side
counterpart: the guard stays ownership-blind, so the run that launched a client
waits for it to leave the process list before handing the tier on.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import time
from pathlib import Path

import pytest

GUARD = Path(__file__).resolve().parents[2] / "spike" / "host-guard.sh"
# Absolute, because the guard's whole subject is a tool resolved by name that
# was not on PATH. Interpreting these tests would be harder if they had the bug.
BASH = shutil.which("bash") or "/bin/bash"

# The number `spike/tier-lock.sh` and `spike/regress.sh` already use for
# infra_unavailable. A caller reads one value for "not a result".
EXIT_INFRA_UNAVAILABLE = 5

# What real tasklist.exe prints. Captured from
# `/mnt/c/Windows/System32/tasklist.exe /FI "IMAGENAME eq arma3_x64.exe"`.
TASKLIST_ABSENT = "INFO: No tasks are running which match the specified criteria.\n"
TASKLIST_PRESENT = (
    "\n"
    "Image Name                     PID Session Name        Session#    Mem Usage\n"
    "========================= ======== ================ =========== ============\n"
    "arma3_x64.exe                24188 Console                    1  3,412,904 K\n"
)


def _stub(tmp_path: Path, name: str, body: str, *, executable: bool = True) -> Path:
    path = tmp_path / name
    path.write_text(f"#!/usr/bin/env bash\n{body}\n")
    if executable:
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _run(tasklist: Path | str, **extra_env: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, CTI_WINDOWS_TASKLIST=str(tasklist), **extra_env)
    # S603: the argv is this repo's own script and a path this test just wrote.
    return subprocess.run(  # noqa: S603
        [BASH, str(GUARD)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        # The guard's own bound is the subject of the interop tests below; this
        # one is the test's, so a regression is a red rather than a hung suite.
        timeout=60,
    )


def _wait_gone(tasklist: Path | str, timeout: str = "5") -> subprocess.CompletedProcess[str]:
    """`cti_windows_wait_gone` sourced, which is how the runners use it."""
    env = dict(os.environ, CTI_WINDOWS_TASKLIST=str(tasklist))
    # S603: this repo's own script, sourced by a fixed one-liner.
    return subprocess.run(  # noqa: S603
        [BASH, "-c", f"source {GUARD}; cti_windows_wait_gone arma3_x64.exe {timeout}"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def test_no_client_running_proceeds(tmp_path: Path) -> None:
    """The list came back and the game is not in it — the one green branch."""
    tasklist = _stub(tmp_path, "tasklist.sh", f"printf '%s' {TASKLIST_ABSENT!r}")
    result = _run(tasklist)
    assert result.returncode == 0, result.stderr
    assert "is not in the Windows process list" in result.stderr


def test_human_client_running_refuses(tmp_path: Path) -> None:
    """A client on the host is the human's. Stop, not kill."""
    tasklist = _stub(tmp_path, "tasklist.sh", f"printf '%s' {TASKLIST_PRESENT!r}")
    result = _run(tasklist)
    assert result.returncode == EXIT_INFRA_UNAVAILABLE
    assert "failure_class=infra_unavailable" in result.stderr
    assert "Nothing was launched" in result.stderr


def test_missing_tool_refuses_rather_than_failing_open(tmp_path: Path) -> None:
    """#41 itself: the tool absent must not read as "no client is running"."""
    result = _run(tmp_path / "there-is-no-tasklist-here.exe")
    assert result.returncode == EXIT_INFRA_UNAVAILABLE
    assert "failure_class=infra_unavailable" in result.stderr
    assert "no executable Windows process list" in result.stderr


def test_bare_name_on_path_is_not_how_the_tool_is_found(tmp_path: Path) -> None:
    """The regression #41 reports, asserted on the guard rather than the shell.

    The first draft asserted the premise itself — that `tasklist.exe` is not on
    an agent's PATH — and went red the day a session's shell carried the WSL
    interop PATH append (#180). Whether that append is in effect varies with how
    a session was entered, so a test gating on it could go red with nothing in
    the tree having changed. What must hold in both worlds is behavioural: PATH
    is not how the guard finds the tool, in either direction. This is the first
    direction — the bare name resolves, to a decoy answering "absent", the exact
    answer that fails open — while the configured absolute path is missing. A
    guard that reaches for PATH proceeds; the real one refuses.
    """
    bindir = tmp_path / "on-path"
    bindir.mkdir()
    invoked = tmp_path / "decoy-was-invoked"
    _stub(bindir, "tasklist.exe", f"touch '{invoked}'\nprintf '%s' {TASKLIST_ABSENT!r}")
    env = dict(
        os.environ,
        PATH=f"{bindir}:{os.environ.get('PATH', '')}",
        CTI_WINDOWS_TASKLIST=str(tmp_path / "there-is-no-tasklist-here.exe"),
    )
    # The staging must have taken effect: the bare name resolves, to the decoy.
    # S603: a fixed literal command line with no input of any kind.
    probe = subprocess.run(  # noqa: S603
        [BASH, "-c", "command -v tasklist.exe"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert probe.stdout.strip() == str(bindir / "tasklist.exe"), probe.stdout
    # S603: the argv is this repo's own script.
    result = subprocess.run(  # noqa: S603
        [BASH, str(GUARD)], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == EXIT_INFRA_UNAVAILABLE
    assert "no executable Windows process list" in result.stderr
    assert not invoked.exists(), "the guard executed the PATH-resolved decoy"


def test_guard_runs_with_no_bare_name_to_resolve(tmp_path: Path) -> None:
    """The other direction: #41's original world, rebuilt rather than assumed.

    No `tasklist.exe` is reachable by name anywhere on this PATH, and the guard
    still runs to a verdict — the absolute-path seam is the only resolution it
    has. The guard that #41 replaced, wrapped in `command -v tasklist.exe`,
    silently skips itself here.

    The rebuilt PATH keeps `uv`'s own directory: since #161 the answer→verdict
    mapping is a bounded `uv run` (ADR-0049), so the *proceed* branch needs the
    mapper reachable. That is not the #41 shape creeping back — a missing
    mapper fails closed to a stop (asserted below), where the missing tasklist
    failed open to a pass — and the tier cannot run without uv anywhere else
    either.
    """
    tasklist = _stub(tmp_path, "tasklist.sh", f"printf '%s' {TASKLIST_ABSENT!r}")
    uv_dir = Path(shutil.which("uv") or "/usr/bin/uv").parent
    env = dict(os.environ, PATH=f"/usr/bin:/bin:{uv_dir}", CTI_WINDOWS_TASKLIST=str(tasklist))
    # The staging must have taken effect: the rebuilt PATH resolves no bare name.
    # S603: a fixed literal command line with no input of any kind.
    probe = subprocess.run(  # noqa: S603
        [BASH, "-c", "command -v tasklist.exe"], env=env, capture_output=True, check=False
    )
    assert probe.returncode != 0, "the rebuilt PATH still resolves tasklist.exe"
    # S603: the argv is this repo's own script and a path this test just wrote.
    result = subprocess.run(  # noqa: S603
        [BASH, str(GUARD)], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert "is not in the Windows process list" in result.stderr


def test_non_executable_tool_refuses(tmp_path: Path) -> None:
    tasklist = _stub(tmp_path, "tasklist.sh", f"printf '%s' {TASKLIST_ABSENT!r}", executable=False)
    result = _run(tasklist)
    assert result.returncode == EXIT_INFRA_UNAVAILABLE


def test_tool_that_errors_refuses(tmp_path: Path) -> None:
    """An interop binary that cannot start is not an answer about the host."""
    tasklist = _stub(tmp_path, "tasklist.sh", "echo 'Access is denied.' >&2\nexit 1")
    result = _run(tasklist)
    assert result.returncode == EXIT_INFRA_UNAVAILABLE
    assert "exited 1" in result.stderr


def test_tool_that_says_nothing_refuses(tmp_path: Path) -> None:
    """Silence is not a negative. Real tasklist always prints something."""
    tasklist = _stub(tmp_path, "tasklist.sh", "exit 0")
    result = _run(tasklist)
    assert result.returncode == EXIT_INFRA_UNAVAILABLE
    assert "answered nothing" in result.stderr


@pytest.mark.parametrize("image", ["ARMA3_X64.EXE", "Arma3_x64.exe"])
def test_image_match_is_case_insensitive(tmp_path: Path, image: str) -> None:
    """Windows does not care about the case and neither may the guard."""
    listing = TASKLIST_PRESENT.replace("arma3_x64.exe", image)
    tasklist = _stub(tmp_path, "tasklist.sh", f"printf '%s' {listing!r}")
    assert _run(tasklist).returncode == EXIT_INFRA_UNAVAILABLE


# ------------------------------------- teardown waits for its own exit (#119)
def test_wait_gone_returns_once_the_image_leaves_the_list(tmp_path: Path) -> None:
    """The whole of #119: a client that is still exiting is not yet gone.

    The stub answers "present" for the first two asks and "absent" after, which
    is the shutdown lag that made a corpus run stop on its own client.
    """
    counter = tmp_path / "asks"
    tasklist = _stub(
        tmp_path,
        "tasklist.sh",
        f"n=$(cat {counter} 2>/dev/null || echo 0)\n"
        f"echo $((n + 1)) > {counter}\n"
        f"if ((n < 2)); then printf '%s' {TASKLIST_PRESENT!r}; "
        f"else printf '%s' {TASKLIST_ABSENT!r}; fi",
    )
    result = _wait_gone(tasklist, timeout="20")
    assert result.returncode == 0, result.stderr
    assert "has left the Windows process list" in result.stderr
    assert int(counter.read_text()) >= 3, "it answered before it had asked again"


def test_wait_gone_gives_up_loudly_rather_than_waiting_forever(tmp_path: Path) -> None:
    """A deadline on a shutdown, reported rather than extended.

    A process that never goes leaves the next run's guard to refuse — and that
    refusal is the correct one, which is why this returns non-zero rather than
    escalating here.
    """
    tasklist = _stub(tmp_path, "tasklist.sh", f"printf '%s' {TASKLIST_PRESENT!r}")
    result = _wait_gone(tasklist, timeout="1")
    assert result.returncode != 0
    assert "still in the Windows process list" in result.stderr


def test_wait_gone_does_not_read_an_unreadable_list_as_gone(tmp_path: Path) -> None:
    """The same fail-closed stance as the guard, on the way out."""
    result = _wait_gone(tmp_path / "there-is-no-tasklist-here.exe", timeout="1")
    assert result.returncode != 0
    assert "cannot tell whether" in result.stderr


def test_the_guard_itself_gained_no_ownership_exemption(tmp_path: Path) -> None:
    """#119's rejected fix, asserted as still rejected.

    The wait above exists because the guard must not learn to excuse a process
    it recognises: a guard that can excuse ours can be talked into excusing the
    human's. `cti_human_client_state` takes an image and nothing else, and a
    client in the list is a stop whatever pid the caller thinks it owns.
    """
    tasklist = _stub(tmp_path, "tasklist.sh", f"printf '%s' {TASKLIST_PRESENT!r}")
    env = dict(
        os.environ,
        CTI_WINDOWS_TASKLIST=str(tasklist),
        # Every shape an "it's ours" exemption could plausibly arrive in.
        CTI_WINDOWS_CLIENT_PID="24188",
        CTI_OUR_CLIENT_PID="24188",
    )
    # S603: this repo's own script.
    result = subprocess.run(  # noqa: S603
        [BASH, str(GUARD)], env=env, capture_output=True, text=True, check=False, timeout=60
    )
    assert result.returncode == EXIT_INFRA_UNAVAILABLE
    assert "24188" not in result.stderr


# ------------------------------------------- every interop call is bounded (#144)
# Reproduction baseline for all three: before the bound, each of these stubs held
# its caller for the full 60 s of `sleep` — in anger, for as long as WSL interop
# stayed wedged, with the run's slot lock and the machine-wide client lock held
# and no verdict of any class ever produced.
HANGS = "sleep 60"


def test_a_wedged_process_list_is_unavailable_rather_than_a_hang(tmp_path: Path) -> None:
    """A tool that never answers is a check that could not run, on a deadline.

    #41's rule with #144's teeth: the guard already refused a `tasklist.exe` it
    could not execute, and would have waited forever for one that started and
    never returned — which is the failure mode WSL interop actually has.
    """
    tasklist = _stub(tmp_path, "wedged-tasklist.sh", HANGS)
    started = time.monotonic()
    result = _run(tasklist, CTI_WINDOWS_INTEROP_TIMEOUT="2")
    elapsed = time.monotonic() - started

    assert result.returncode == EXIT_INFRA_UNAVAILABLE
    assert "did not answer within 2s" in result.stderr
    assert "failure_class=infra_unavailable" in result.stderr
    assert elapsed < 30, f"the guard waited {elapsed:.1f}s on a bound of 2s"


def test_a_wedged_taskkill_does_not_hang_teardown(tmp_path: Path) -> None:
    """Teardown's half. It runs while the run still holds every lock it took."""
    taskkill = _stub(tmp_path, "wedged-taskkill.sh", HANGS)
    env = dict(os.environ, CTI_WINDOWS_TASKKILL=str(taskkill), CTI_WINDOWS_INTEROP_TIMEOUT="2")
    started = time.monotonic()
    # S603: this repo's own script, sourced by a fixed one-liner.
    result = subprocess.run(  # noqa: S603
        [BASH, "-c", f"source {GUARD}; cti_windows_taskkill arma3_x64.exe"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    elapsed = time.monotonic() - started

    assert result.returncode != 0
    assert "did not return within 2s" in result.stderr
    assert "may still be running" in result.stderr
    assert elapsed < 30, f"teardown waited {elapsed:.1f}s on a bound of 2s"


def test_wait_gone_bounds_each_ask_as_well_as_the_whole_wait(tmp_path: Path) -> None:
    """The loop had a deadline; the call inside it did not.

    `cti_windows_wait_gone` polls the same list the guard reads, so one wedged
    ask hung the whole wait however short its window was.
    """
    tasklist = _stub(tmp_path, "wedged-tasklist.sh", HANGS)
    env = dict(os.environ, CTI_WINDOWS_TASKLIST=str(tasklist), CTI_WINDOWS_INTEROP_TIMEOUT="2")
    started = time.monotonic()
    # S603: this repo's own script, sourced by a fixed one-liner.
    result = subprocess.run(  # noqa: S603
        [BASH, "-c", f"source {GUARD}; cti_windows_wait_gone arma3_x64.exe 5"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    elapsed = time.monotonic() - started

    assert result.returncode != 0
    assert "cannot tell whether" in result.stderr
    assert elapsed < 30, f"the wait took {elapsed:.1f}s with a 2s bound on each ask"


def test_wait_gone_refuses_a_window_that_is_not_a_number(tmp_path: Path) -> None:
    """An unparsable window used to produce an empty deadline and an endless loop."""
    tasklist = _stub(tmp_path, "tasklist.sh", f"printf '%s' {TASKLIST_PRESENT!r}")
    result = _wait_gone(tasklist, timeout="soon")
    assert result.returncode != 0
    assert "not a number of seconds" in result.stderr


def test_an_unreachable_verdict_mapper_fails_closed_not_open(tmp_path: Path) -> None:
    """#161's new dependency, held to #41's rule at the call site.

    The answer→verdict mapping is a `uv run` since ADR-0049 put the ladder in
    Python. A mapper that cannot be invoked must be a stop even when the process
    list read "free" — the one direction the old inline ladders could never get
    wrong, and therefore the one this migration has to pin. `CTI_UV_TIMEOUT` set
    to a non-number makes `timeout` refuse before `uv` launches, which is the
    cheapest stand-in for every way the mapper can fail to run.
    """
    tasklist = _stub(tmp_path, "tasklist.sh", f"printf '%s' {TASKLIST_ABSENT!r}")
    result = _run(tasklist, CTI_UV_TIMEOUT="banana")
    assert result.returncode == EXIT_INFRA_UNAVAILABLE
    assert "could not be decided" in result.stderr
    assert "failing closed" in result.stderr
    assert "A check that could not run is not a check that passed" in result.stderr


def test_runners_do_not_resolve_the_windows_tools_by_bare_name() -> None:
    """No caller may reintroduce the fail-open form the issue is about."""
    spike = GUARD.parent
    for script in sorted(spike.glob("*.sh")):
        text = script.read_text()
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue  # the comments name the bug on purpose
            assert not stripped.startswith(("tasklist.exe", "taskkill.exe")), (
                f"{script.name}: {stripped}"
            )
            assert "command -v tasklist.exe" not in stripped, f"{script.name}: {stripped}"
