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
from typing import TYPE_CHECKING

import pytest
from conftest import REPO

if TYPE_CHECKING:
    from pathlib import Path

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
    tmp_path: Path,
    lines: list[str],
    extra_env: dict[str, str] | None = None,
    server_stub: str | None = None,
    mode: str | None = None,
) -> dict[str, str]:
    """One pass of `spike/run.sh` over a server that logs exactly `lines`."""
    server_dir = tmp_path / "server"
    server_dir.mkdir()
    stub = server_dir / "arma3server_x64"
    stub.write_text(
        server_stub or STUB_SERVER % {"lines": "\n".join(f'echo "SPIKE|{ln}"' for ln in lines)}
    )
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
        # Its own state directory for the same reason, and this one is a lock
        # rather than a port (#132). The teardown test below sends a client, and
        # a client run takes the machine-wide Windows client lock — which lives
        # at $HOME/.arma-cti/windows-client.lock unless CTI_TIER_STATE moves it,
        # and which run.sh asks for with a non-blocking try. Left unmoved, this
        # file's no-Arma test both stole that lock from live Arma-tier runs and
        # was refused by them: the refusal is an infra_unavailable before the
        # launch, so the run records no windows_client_launched at all. That is
        # the one red in 26 full-suite runs #130 reported, and two concurrent
        # `just unit` runs in sibling worktrees reproduce it with no Arma in
        # sight. Every other unit test that drives these scripts already isolates
        # this; this one was the outlier.
        CTI_TIER_STATE=str(tmp_path / "state"),
        CTI_BASIC_CFG="",
        CTI_HC_TIMEOUT="20",
        CTI_HARNESS_TIMEOUT="60",
    )
    # Last word to the caller, so a test can substitute one of the defaults above
    # as well as add to them.
    env.update(extra_env or {})
    # S603: this repo's own script, with paths this test just wrote.
    command = [BASH, str(RUN), *([mode] if mode is not None else [])]
    result = subprocess.run(  # noqa: S603
        command, env=env, capture_output=True, text=True, check=False, timeout=300
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


def test_a_typoed_in_mission_class_is_caught_at_the_boundary(tmp_path: Path) -> None:
    """#147 item 4: `class=timout` used to flow through as an unknown class.

    It surfaced at the far end of the tier as an undocumented exit code rather
    than being caught where the line is first read, as the harness bug it is.
    The mapping is decided in the class table's own home (tools/pool_merge.py).
    """
    records = run_with_lines(tmp_path, ["FAIL class=timout probe_never_finished"])
    assert records["verdict"] == "FAIL"
    assert records["failure_class"] == "untyped_harness_failure"
    assert "timout" in records["failure_detail"]


def test_a_fail_line_cannot_declare_itself_a_pass(tmp_path: Path) -> None:
    """`FAIL class=pass` would read back as a green verdict downstream (#147)."""
    records = run_with_lines(tmp_path, ["FAIL class=pass smuggled"])
    assert records["verdict"] == "FAIL"
    assert records["failure_class"] == "untyped_harness_failure"


def test_a_run_with_no_fail_line_passes(tmp_path: Path) -> None:
    """The other half of the branch: this must not have become a permanent red."""
    records = run_with_lines(tmp_path, ["measurement thing=1"])
    assert records["verdict"] == "PASS"
    assert records["_returncode"] == "0"


def test_a_timeline_that_cannot_be_rendered_records_its_absence(tmp_path: Path) -> None:
    real_uv = shutil.which("uv")
    assert real_uv is not None
    shim_dir = tmp_path / "timeline-fails"
    shim_dir.mkdir()
    uv = shim_dir / "uv"
    uv.write_text(
        "#!/usr/bin/env bash\n"
        'if [[ " $* " == *" tools/timeline.py "* ]]; then\n'
        '  echo "timeline exploded" >&2\n'
        "  exit 17\n"
        "fi\n"
        f'exec "{real_uv}" "$@"\n'
    )
    uv.chmod(uv.stat().st_mode | stat.S_IXUSR)
    path = os.environ["PATH"]

    records = run_with_lines(
        tmp_path,
        ["measurement thing=1"],
        extra_env={"PATH": f"{shim_dir}:{path}"},
        mode="--regress",
    )

    assert records["verdict"] == "PASS"
    assert records["timeline"] == "unavailable: timeline.py failed: timeline exploded"


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
    # The verdict first, and only then the record the launch writes. A run that
    # refused before launching has written down why, and reading the launch
    # record first threw that away as a bare `KeyError: 'windows_client_launched'`
    # — which is precisely why #132 arrived undiagnosed. A failure here should
    # quote the harness's own reason.
    assert records["verdict"] == "PASS", (
        f"{records.get('failure_class')}: {records.get('failure_detail')}\n{records['_stderr']}"
    )
    assert records["windows_client_launched"] == "true"
    assert killed.exists(), "teardown never asked the client to stop"
    assert "has left the Windows process list" in records["_stderr"]
    assert int(asks.read_text()) >= 3, "teardown took the first answer and did not wait"


# ------------------------------- the daemon readiness poll counts once (#192)
def test_the_daemon_readiness_poll_writes_no_bash_error_while_it_waits(tmp_path: Path) -> None:
    r"""`$(grep -c … || echo 0)` handed bash's arithmetic two lines (#192).

    `grep -c` prints its count *and* exits 1 when it matches nothing, so the
    fallback fired on top of a substitution that had already produced a count,
    and the arithmetic saw `0\n0`:

        ./spike/run.sh: line 787: ((: 0
        0 >= daemon_starts: syntax error in expression

    One of those per turn of the poll, into the run's own stdout, until the
    daemon's readiness line appeared — an untyped bash error inside the harness,
    which is what the failure-class table calls a harness bug.

    Reproduces on every run rather than only slow ones: the first turn reads the
    log before the first sleep and before the daemon has written anything to it.
    Asserted on a green run, so the assertion is about the wait rather than
    about a failure, and on `((:` — bash's own prefix for an arithmetic
    diagnostic — so it covers the next such expression as well as this one.
    """
    records = run_with_lines(tmp_path, ["measurement thing=1"])
    assert records["verdict"] == "PASS", records["_stderr"][-2000:]
    assert "((:" not in records["_stderr"], records["_stderr"][-2000:]
    assert "syntax error in expression" not in records["_stderr"]


def test_a_daemon_log_the_harness_cannot_read_is_typed_as_such(tmp_path: Path) -> None:
    """The failure the discarded `|| echo 0` was masking (#192, and #41's rule).

    A `grep -c` that could not read the file is not a count of zero. Folded into
    one by the fallback, an unreadable log left the poll spinning to its 90 s
    deadline and reported as a daemon that never said it was ready — the right
    class for the wrong stated reason, with the 90 s spent finding it out.

    Staged by putting a directory where the log goes rather than by chmod, so
    the test does not depend on the uid it runs as. Both greps on this machine's
    PATH refuse it, and they disagree about how: GNU grep exits 2 having printed
    a count, ugrep exits 1 having printed nothing. The harness has to reject
    either, which is why it checks the status and the shape of what came back.
    """
    (tmp_path / "out" / "daemon.log").mkdir(parents=True)
    records = run_with_lines(tmp_path, ["measurement thing=1"])
    assert records["verdict"] == "FAIL"
    assert records["failure_class"] == "infra_unavailable"
    assert "could not read its own daemon log" in records["failure_detail"]


# ------------------------------ the harness's own deadlines fail closed (#144)
# A server that boots and then says nothing more. Every deadline test below needs
# a wait that will not be satisfied, which is exactly what a wedged world looks
# like from here.
STUB_SERVER_SILENT = """#!/usr/bin/env bash
for arg in "$@"; do
    [[ "$arg" == "-client" ]] && exit 0
done
echo "Arma 3 Console version 2.20 : port 2402"
echo "Dedicated host created"
echo "SPIKE|mission_running"
sleep 600
"""


def sabotaged_bc(tmp_path: Path) -> str:
    """Build a PATH whose `bc` errors, standing in for a machine that has none.

    The deadlines used to be `bc` arithmetic, and the failure was silent in the
    worst direction: `(($(echo ... | bc)))` over an empty operand is false, so
    the deadline simply never fired. A harness that no longer calls `bc` cannot
    tell this PATH from any other.
    """
    shim_dir = tmp_path / "no-bc"
    shim_dir.mkdir()
    shim = shim_dir / "bc"
    shim.write_text("#!/usr/bin/env bash\necho 'bc: not on this machine' >&2\nexit 127\n")
    shim.chmod(shim.stat().st_mode | stat.S_IXUSR)
    return f"{shim_dir}{os.pathsep}{os.environ['PATH']}"


def test_a_deadline_still_fires_with_no_working_bc(tmp_path: Path) -> None:
    """The timeout mechanism does not depend on an optional binary.

    Reproduction baseline: before this, the same run waited out the stub server's
    own 600 s `sleep` — in anger, the whole hold window and then some, with the
    slot lock held — and reported `node_crashed` when the process finally went,
    rather than the `timeout` the failure-class table sends the reader to
    synchronisation for.
    """
    records = run_with_lines(
        tmp_path,
        [],
        server_stub=STUB_SERVER_SILENT,
        extra_env={"CTI_HARNESS_TIMEOUT": "5", "PATH": sabotaged_bc(tmp_path)},
    )
    assert records["verdict"] == "FAIL"
    assert records["failure_class"] == "timeout", records["_stderr"][-2000:]
    assert "never logged done" in records["failure_detail"]


def test_a_window_that_is_not_a_number_is_a_refusal_not_an_endless_wait(
    tmp_path: Path,
) -> None:
    """A bound that cannot be computed is not a bound.

    The class is `infra_unavailable` rather than `timeout` on purpose: nothing
    was measured, so there is no synchronisation to investigate — the table's
    "stop, not a result" is the honest answer.
    """
    records = run_with_lines(
        tmp_path,
        [],
        server_stub=STUB_SERVER_SILENT,
        extra_env={"CTI_HARNESS_TIMEOUT": "soon"},
    )
    assert records["verdict"] == "FAIL"
    assert records["failure_class"] == "infra_unavailable"
    assert "CTI_HARNESS_TIMEOUT" in records["failure_detail"]


def test_a_run_that_cannot_bound_its_external_calls_refuses_up_front(
    tmp_path: Path,
) -> None:
    """`timeout 0` disables the deadline rather than setting one to zero.

    GNU `timeout` reads 0 as "no timeout", so the one value that looks strictest
    is the one that bounds nothing — the fail-open shape this issue is about,
    reachable through a variable. It is refused at the pre-flight instead.
    """
    records = run_with_lines(tmp_path, ["measurement thing=1"], extra_env={"CTI_UV_TIMEOUT": "0"})
    assert records["verdict"] == "FAIL"
    assert records["failure_class"] == "infra_unavailable"
    assert "CTI_UV_TIMEOUT" in records["failure_detail"]


def test_no_deadline_in_the_tier_is_computed_through_bc() -> None:
    """The cause, asserted where a regression would reintroduce it.

    The tests above cover the behaviour; this covers the shape, because the next
    deadline somebody writes is the one that would quietly bring the dependency
    back.
    """
    for script in sorted((REPO / "spike").glob("*.sh")):
        for number, line in enumerate(script.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue  # the comments name the bug on purpose
            assert "| bc" not in stripped, f"{script.name}:{number}: {stripped}"
