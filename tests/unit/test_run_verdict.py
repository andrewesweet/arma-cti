"""What class `spike/run.sh` gives an in-mission FAIL (issues #23, #83).

The world writes `FAIL class=timeout ...` as well as plain assertions, and the
failure-class table sends the reader somewhere different for each. `run.sh` has
two verdict paths — the hold/regress one and the plain one — and only the first
read the class the world declared; the other called every red an
`assertion_failed`, which is the #23 fix surviving in one of the two places that
need it.

Asserted here rather than in the Arma tier because the classification is the
harness's own arithmetic over lines in a log, and a dedicated server is not
needed to produce a line in a log. `CTI_SERVER_DIR` points at a stub that prints
what the engine would have printed; the daemon is the real one, because
`run.sh` waits on its readiness line and a stub of that would be a test of the
stub. Nothing here brings Arma up, so it belongs in `just unit`.
"""

from __future__ import annotations

import os
import shutil
import socket
import stat
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
RUN = REPO / "spike" / "run.sh"
BASH = shutil.which("bash") or "/bin/bash"

# The engine lines run.sh waits on, in the order it waits for them. The stub
# prints them and then idles until teardown, exactly as a server does.
STUB_SERVER = """#!/usr/bin/env bash
for arg in "$@"; do
    # The headless client is this same binary with -client. It has nothing to
    # join, so it exits, which run.sh reads as "the process died" and records.
    [[ "$arg" == "-client" ]] && exit 0
done
echo "Arma 3 Console version 2.20 : port 2402"
echo "Dedicated host created"
echo "SPIKE|mission_running"
%(lines)s
echo "SPIKE|done"
sleep 600
"""


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def run_with_lines(tmp_path: Path, lines: list[str]) -> dict[str, str]:
    """One pass of `spike/run.sh` over a server that logs exactly `lines`."""
    server_dir = tmp_path / "server"
    server_dir.mkdir()
    stub = server_dir / "arma3server_x64"
    stub.write_text(STUB_SERVER % {"lines": "\n".join(f'echo "SPIKE|{ln}"' for ln in lines)})
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)

    shim = tmp_path / "libcti_shim.so"
    shim.write_bytes(b"not a shared object; run.sh only checks that it exists")
    built_mod = tmp_path / "build"
    (built_mod / "addons").mkdir(parents=True)
    (built_mod / "addons" / "stub.pbo").write_bytes(b"")

    tasklist = tmp_path / "tasklist.sh"
    tasklist.write_text(
        "#!/usr/bin/env bash\nprintf 'INFO: No tasks are running which match the criteria.\\n'\n"
    )
    tasklist.chmod(tasklist.stat().st_mode | stat.S_IXUSR)

    out = tmp_path / "out"
    env = dict(
        os.environ,
        CTI_SERVER_DIR=str(server_dir),
        CTI_SHIM_SO=str(shim),
        CTI_BUILT_MOD=str(built_mod),
        CTI_SPIKE_OUT=str(out),
        CTI_WINDOWS_TASKLIST=str(tasklist),
        # Its own daemon on its own port: the tier is shared, and a test that
        # took 9099 would collide with whatever else is on this machine.
        CTI_DAEMON_PORT=str(free_port()),
        CTI_SERVER_PORT=str(free_port()),
        CTI_BASIC_CFG="",
        CTI_HC_TIMEOUT="20",
        CTI_HARNESS_TIMEOUT="60",
    )
    # S603: this repo's own script, with paths this test just wrote.
    result = subprocess.run(  # noqa: S603
        [BASH, str(RUN)], env=env, capture_output=True, text=True, check=False, timeout=300
    )
    records = dict(
        line.split("=", 1) for line in (out / "results.env").read_text().splitlines() if "=" in line
    )
    records["_returncode"] = str(result.returncode)
    return records


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("FAIL class=timeout probe_never_finished", "timeout"),
        ("FAIL class=oracle_disagreement telemetry_disagrees", "oracle_disagreement"),
        ("FAIL class=node_crashed the_node_went", "node_crashed"),
        # No class declared is still an assertion — the old behaviour, kept.
        ("FAIL nothing_matched expected=3 got=0", "assertion_failed"),
    ],
)
def test_an_in_mission_fail_keeps_the_class_the_world_declared(
    tmp_path: Path, line: str, expected: str
) -> None:
    records = run_with_lines(tmp_path, [line])
    assert records["verdict"] == "FAIL"
    assert records["failure_class"] == expected
    assert records["_returncode"] == "1"


def test_a_run_with_no_fail_line_passes(tmp_path: Path) -> None:
    """The other half of the branch: this must not have become a permanent red."""
    records = run_with_lines(tmp_path, ["measurement thing=1"])
    assert records["verdict"] == "PASS"
    assert records["_returncode"] == "0"


def test_the_first_fail_is_the_one_reported(tmp_path: Path) -> None:
    records = run_with_lines(
        tmp_path, ["FAIL class=timeout first_one", "FAIL class=assertion_failed second_one"]
    )
    assert records["failure_class"] == "timeout"
    assert "first_one" in records["failure_detail"]
