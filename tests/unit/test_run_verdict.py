"""What verdict `spike/run.sh` records for a run, and why (issues #23, #83, #116, #119).

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

The same stub world carries two later rules. #116's: a probe's optional leg
reports `LEG name=<leg> status=ran|unverified`, the verdict names the legs, and a
leg that did not run is `infra_unavailable` rather than green. And #119's:
teardown waits for a Windows process this run launched to leave the host's
process list before the run ends, because the host guard is ownership-blind on
purpose and will otherwise read our own exiting client as a play session.
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


def run_with_lines(
    tmp_path: Path, lines: list[str], extra_env: dict[str, str] | None = None
) -> dict[str, str]:
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
    # Last word to the caller, so a test can substitute one of the defaults above
    # as well as add to them.
    env.update(extra_env or {})
    # S603: this repo's own script, with paths this test just wrote.
    result = subprocess.run(  # noqa: S603
        [BASH, str(RUN)], env=env, capture_output=True, text=True, check=False, timeout=300
    )
    records = dict(
        line.split("=", 1) for line in (out / "results.env").read_text().splitlines() if "=" in line
    )
    records["_returncode"] = str(result.returncode)
    records["_stderr"] = result.stderr
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


# ----------------------------------------------- optional legs (#116, ADR-0037)
def test_a_leg_that_did_not_run_is_not_a_pass(tmp_path: Path) -> None:
    """The whole of #116, at the seam that scores it.

    `human-commander` reported exactly this shape — one line saying the client
    leg had not run — and finished green, because nothing read the line.
    """
    records = run_with_lines(
        tmp_path,
        ["LEG name=human_commander_client status=unverified reason=run_sent_no_headed_client"],
    )
    assert records["verdict"] == "FAIL"
    assert records["failure_class"] == "infra_unavailable"
    assert "human_commander_client" in records["failure_detail"]
    assert records["legs"] == "human_commander_client:unverified"


def test_a_pass_names_the_legs_it_ran(tmp_path: Path) -> None:
    """The other half: a green verdict says which legs it is green about."""
    records = run_with_lines(
        tmp_path,
        ["LEG name=client_port_caller status=ran", "LEG name=client_port_accepted status=ran"],
    )
    assert records["verdict"] == "PASS"
    assert records["legs"] == "client_port_caller:ran client_port_accepted:ran"


def test_a_probe_with_no_optional_legs_records_none(tmp_path: Path) -> None:
    """Most of the corpus has no optional leg, and must not grow a field for it."""
    records = run_with_lines(tmp_path, ["measurement thing=1"])
    assert records["verdict"] == "PASS"
    assert "legs" not in records


def test_a_declared_red_outranks_an_unverified_leg(tmp_path: Path) -> None:
    """A probe that failed produced a result, and keeps the class it declared.

    An unverified leg is only the story when there is no other one; classifying
    this run infra_unavailable would send the reader to "stop, not a result"
    when the world had already said what went wrong.
    """
    records = run_with_lines(
        tmp_path,
        [
            "FAIL class=timeout client_port_probe_client_silent step=accepted",
            "LEG name=client_port_accepted status=unverified reason=client_never_acked_the_step",
        ],
    )
    assert records["failure_class"] == "timeout"


# -------------------------------------- teardown owns its own processes (#119)
def test_teardown_waits_for_the_windows_client_it_launched_to_be_gone(tmp_path: Path) -> None:
    """#119: the run releases the tier only once its own client has left the list.

    The stubbed process list reports the client present for two asks after
    `taskkill` returns — the shutdown lag that made the next probe's pre-flight
    call our own exiting client a play session and abandon the corpus.
    """
    host = tmp_path / "windows-arma"
    host.mkdir()
    launched = tmp_path / "launched"
    killed = tmp_path / "killed"
    asks = tmp_path / "asks"

    client = host / "arma3_x64.exe"
    client.write_text(f"#!/usr/bin/env bash\ntouch {launched}\nsleep 600\n")
    client.chmod(client.stat().st_mode | stat.S_IXUSR)

    taskkill = tmp_path / "taskkill.sh"
    taskkill.write_text(f"#!/usr/bin/env bash\ntouch {killed}\necho 'SUCCESS: sent'\n")
    taskkill.chmod(taskkill.stat().st_mode | stat.S_IXUSR)

    present = (
        "\nImage Name                     PID Session Name        Session#    Mem Usage\n"
        "arma3_x64.exe                24188 Console                    1  3,412,904 K\n"
    )
    absent = "INFO: No tasks are running which match the specified criteria.\n"
    tasklist = tmp_path / "lagging-tasklist.sh"
    tasklist.write_text(
        "#!/usr/bin/env bash\n"
        f"if [[ -e {killed} ]]; then\n"
        f"  n=$(cat {asks} 2>/dev/null || echo 0); echo $((n + 1)) > {asks}\n"
        f"  if ((n < 2)); then printf '%s' {present!r}; else printf '%s' {absent!r}; fi\n"
        f"elif [[ -e {launched} ]]; then printf '%s' {present!r}\n"
        f"else printf '%s' {absent!r}\n"
        "fi\n"
    )
    tasklist.chmod(tasklist.stat().st_mode | stat.S_IXUSR)

    records = run_with_lines(
        tmp_path,
        ["measurement thing=1"],
        extra_env={
            "CTI_WINDOWS_CLIENT": "1",
            "CTI_WINDOWS_ARMA_DIR": str(host),
            "CTI_WINDOWS_TASKLIST": str(tasklist),
            "CTI_WINDOWS_TASKKILL": str(taskkill),
            "CTI_WINDOWS_EXIT_TIMEOUT": "30",
        },
    )
    assert records["windows_client_launched"] == "true"
    assert records["verdict"] == "PASS", records["_stderr"]
    assert killed.exists(), "teardown never asked the client to stop"
    assert "has left the Windows process list" in records["_stderr"]
    assert int(asks.read_text()) >= 3, "teardown took the first answer and did not wait"
