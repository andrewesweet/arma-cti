"""The guard that protects the human's play session (issue #41).

`spike/host-guard.sh` decides whether the Arma tier may take the shared machine.
It was previously inline in `spike/regress.sh` behind `command -v tasklist.exe`,
which is false in an agent's shell — so the guard never ran and every run was
permitted by a check that had not happened.

The point of these tests is that both branches are exercised without Arma: a
Windows process list showing the game refuses, one showing it absent proceeds,
and every way of not getting an answer at all refuses too. The Windows tool is
substituted through `CTI_WINDOWS_TASKLIST`, which is the same seam the real
runners use to point at `/mnt/c/Windows/System32/tasklist.exe`.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
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


def _run(tasklist: Path | str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, CTI_WINDOWS_TASKLIST=str(tasklist))
    # S603: the argv is this repo's own script and a path this test just wrote.
    return subprocess.run(  # noqa: S603
        [BASH, str(GUARD)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
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


def test_bare_name_on_path_is_not_how_the_tool_is_found() -> None:
    """The regression #41 reports, asserted at its cause rather than its effect.

    `tasklist.exe` is not on an agent's PATH here, so any guard that resolves it
    by name is a guard that never runs. If this ever starts passing the guard is
    still correct — it resolves by absolute path — but the bug's own premise has
    changed and the comments explaining it should be reread.
    """
    # S603: a fixed literal command line with no input of any kind.
    probe = subprocess.run(  # noqa: S603
        [BASH, "-c", "command -v tasklist.exe"], capture_output=True, check=False
    )
    assert probe.returncode != 0, "tasklist.exe is on PATH now; #41's premise has changed"


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
