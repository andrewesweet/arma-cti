"""The freshness axes `spike/cycle/cycle.sh` owns (issue #81).

`spike/cycle/leg-b-fresh.sqf`'s header promises that every axis is an assertion
and that a missing reading fails rather than being skipped. Two of the five are
the runner's rather than the leg's — the PRNG streams and leg B's telemetry —
and both were *recorded* and never gated: a cycle whose PRNG stream carried over
reported PASS with the evidence of its own failure sitting in results.env. That
is the #44 false-green shape.

The gates are arithmetic over lines in a log and rows in a file, so they are
asserted here with a stub server printing what the world would have printed.
The daemon is the real one, because the runner waits on its readiness line and
restarting it is the thing the telemetry axis is about. Nothing here brings Arma
up.
"""

from __future__ import annotations

import os
import shutil
import socket
import stat
import subprocess
from typing import TYPE_CHECKING

import pytest
from conftest import REPO

if TYPE_CHECKING:
    from pathlib import Path

CYCLE = REPO / "spike" / "cycle" / "cycle.sh"
BASH = shutil.which("bash") or "/bin/bash"

MATCHING_DRAWS = "[314,159,265,358,979]"

# The engine lines cycle.sh waits on, in order. The leg-B block waits on the
# condition rather than dwelling — the same rule the legs themselves follow. The
# condition is leg B's telemetry file existing, because that is the runner
# having done its half of the switch either way: truncated by the restarted
# daemon, or copied from leg A's by the --no-daemon-restart run.
STUB_SERVER = """#!/usr/bin/env bash
echo "Arma 3 Console version 2.20 : port 2402"
echo "Dedicated host created"
echo "CTI|mission_running"
echo "CTI|cycle_prng leg=a seed=77777 draws=%(a_draws)s"
echo "CTI|cycle_state leg=a funds=900 squads=2 owners=[[agia_marina,WEST]]"
echo "CTI|cycle_a_probe_done"
echo "CTI|cycle_switch_requested to=ctycle1.Stratis"
deadline=$((SECONDS + 20))
while [[ ! -f "$STUB_OUT/telemetry-b.jsonl" ]]; do
    ((SECONDS > deadline)) && break
    sleep 0.1
done
echo "Mission ctycle1.Stratis read from bank"
echo "CTI|mission_running"
if [[ -n "${STUB_TELEMETRY_ROW:-}" ]]; then
    printf '%%s\\n' "$STUB_TELEMETRY_ROW" >>"$STUB_OUT/telemetry-b.jsonl"
fi
%(leg_b_prng)s
echo "CTI|cycle_state leg=b funds=1000 squads=0 owners=[]"
echo "CTI|cycle_b_probe_done"
sleep 600
"""


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def run_cycle(
    tmp_path: Path,
    *args: str,
    a_draws: str = MATCHING_DRAWS,
    b_draws: str | None = MATCHING_DRAWS,
    telemetry_row: str = "",
) -> dict[str, str]:
    """One pass of `cycle.sh` over a server that logs exactly what is asked."""
    server_dir = tmp_path / "server"
    server_dir.mkdir()
    leg_b_prng = (
        f'echo "CTI|cycle_prng leg=b seed=77777 draws={b_draws}"'
        if b_draws is not None
        else "# leg B never logged its draw"
    )
    stub = server_dir / "arma3server_x64"
    stub.write_text(STUB_SERVER % {"a_draws": a_draws, "leg_b_prng": leg_b_prng})
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)

    shim = tmp_path / "libcti_shim.so"
    shim.write_bytes(b"not a shared object; cycle.sh only checks that it exists")
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
        CTI_CYCLE_OUT=str(out),
        CTI_SERVER_DIR=str(server_dir),
        CTI_SHIM_SO=str(shim),
        CTI_BUILT_MOD=str(built_mod),
        CTI_WINDOWS_TASKLIST=str(tasklist),
        CTI_DAEMON_PORT=str(free_port()),
        CTI_SERVER_PORT=str(free_port()),
        STUB_OUT=str(out),
        STUB_TELEMETRY_ROW=telemetry_row,
    )
    # S603: this repo's own script, with paths this test just wrote.
    result = subprocess.run(  # noqa: S603
        [BASH, str(CYCLE), *args], env=env, capture_output=True, text=True, check=False, timeout=300
    )
    records = dict(
        line.split("=", 1) for line in (out / "results.env").read_text().splitlines() if "=" in line
    )
    records["_returncode"] = str(result.returncode)
    return records


CARRY_OVER_ROW = '{"id": "cycle-a-buy-1", "verb": "command"}'


def test_a_clean_cycle_still_passes(tmp_path: Path) -> None:
    """The gates below are only worth anything if this stays green."""
    records = run_cycle(tmp_path)
    assert records["verdict"] == "PASS", records
    assert records["prng_streams_match"] == "true"
    assert records["telemetry_leg_b_carries_leg_a_ids"] == "0"


def test_a_carried_over_prng_stream_fails(tmp_path: Path) -> None:
    records = run_cycle(tmp_path, b_draws="[1,2,3,4,5]")
    assert records["verdict"] == "FAIL"
    assert records["failure_class"] == "assertion_failed"
    assert records["prng_streams_match"] == "false"
    assert "PRNG stream carried over" in records["failure_detail"]


def test_a_prng_axis_that_was_never_read_fails(tmp_path: Path) -> None:
    """A missing reading fails rather than being skipped — the leg's own rule."""
    records = run_cycle(tmp_path, b_draws=None)
    assert records["verdict"] == "FAIL"
    assert records["prng_leg_b"] == "missing"
    assert records["prng_streams_match"] == "unread"
    assert "not an axis that passed" in records["failure_detail"]


def test_telemetry_carrying_leg_a_rows_across_a_restart_fails(tmp_path: Path) -> None:
    records = run_cycle(tmp_path, telemetry_row=CARRY_OVER_ROW)
    assert records["verdict"] == "FAIL"
    assert records["failure_class"] == "assertion_failed"
    assert records["telemetry_leg_b_carries_leg_a_ids"] == "1"
    assert "across a daemon restart" in records["failure_detail"]


def test_the_dishonest_cycle_records_carry_over_without_gating_on_it(tmp_path: Path) -> None:
    """`--no-daemon-restart` inherits leg A's daemon on purpose.

    Its leg B is served by leg A's telemetry file, so carry-over there is the
    finding the run exists to produce and not a failure of this axis. What that
    run goes red on is leg B's own assertions about the Campaign it inherited.
    """
    records = run_cycle(tmp_path, "--no-daemon-restart", telemetry_row=CARRY_OVER_ROW)
    assert int(records["telemetry_leg_b_carries_leg_a_ids"]) >= 1
    assert records["verdict"] == "PASS", records


@pytest.mark.parametrize("leg", ["leg-a-dirty", "leg-b-fresh"])
def test_the_legs_wait_on_the_world_rather_than_dwelling(leg: str) -> None:
    """#81's third bullet, asserted at the source: the prelude is staged now."""
    text = (REPO / "spike" / "cycle" / f"{leg}.sqf").read_text()
    assert "call cti_probe_fnc_worldReady" in text
    assert "diag_tickTime + 20" not in text
    assert 'cat "$PRELUDE"' in CYCLE.read_text()
