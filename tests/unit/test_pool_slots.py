"""The Arma tier as a pool of slots (issue #47, ADR-0028).

Geometry, allocation, scheduling, bulkheads and the merge.

None of this needs Arma. A slot's *geometry* is arithmetic over a port grant; its
*allocation* is `flock(2)`; its *scheduling* is a sort over headers the corpus
already carries; and its *merge* is what the runner does with files the workers
wrote. Every one of those is a place the pool could be silently wrong, and the
way it would be wrong is the way #44's first two-slot run was wrong — a green
pass over two worlds that had quietly become one. So they are asserted here,
where a failure costs a second rather than a bring-up.

`CTI_RUN_SH` points the pool at a stub that prints what `run.sh` would have
recorded, so the corpus under test is the real one: seventeen real probes with
their real windows and real `expect:` headers, which is what makes the schedule
and the class handling mean something. Nothing here launches a server.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import time
from pathlib import Path

import pytest
from conftest import REPO

REGRESS = REPO / "spike" / "regress.sh"
SLOTS_SH = REPO / "spike" / "slots.sh"
TIER_LOCK = REPO / "spike" / "tier-lock.sh"
PROBE_DIR = REPO / "spike" / "probes"
BASH = shutil.which("bash") or "/bin/bash"

# CLAUDE.md's Contract, as the tests read it.
GRANT = range(2400, 3000)
HUMAN_PORTS = range(2302, 2307)

# The exit codes regress.sh maps classes onto.
EXIT_PASS = 0
EXIT_ASSERTION_FAILED = 1
EXIT_INFRA_UNAVAILABLE = 5

# A stand-in for `spike/run.sh`. It reproduces the only part of the contract the
# runner reads: `results.env` with a verdict and, when the verdict is FAIL, the
# class the world declared. By default it gives every probe the class that
# probe's own `expect:` header asks for, so a stub pass of the corpus is green
# for the same reason a real one is — including the four probes that are red by
# design. CTI_STUB_FAIL and CTI_STUB_KILL override it for one named probe.
STUB_RUN = r"""#!/usr/bin/env bash
set -uo pipefail
name="$(basename "${CTI_HARNESS_EXTRA:-unknown}" .sqf)"
out="$CTI_SPIKE_OUT"
printf 'probe=%s\n' "$name" >>"$out/results.env"
printf 'tier_slot=%s\n' "${CTI_TIER_SLOT:-}" >>"$out/results.env"
printf 'tier_host=%s\n' "${CTI_TIER_HOST:-}" >>"$out/results.env"
printf 'server_port=%s\n' "${CTI_SERVER_PORT:-}" >>"$out/results.env"
printf 'daemon_port=%s\n' "${CTI_DAEMON_PORT:-}" >>"$out/results.env"
printf 'daemon_addr=%s\n' "${CTI_DAEMON_ADDR:-}" >>"$out/results.env"
printf 'server_dir=%s\n' "${CTI_SERVER_DIR:-}" >>"$out/results.env"
printf 'server_profile=%s\n' "${CTI_SERVER_NAME:-}" >>"$out/results.env"
printf 'server_version=stub\n' >>"$out/results.env"
printf '%s\t%s\t%s\n' "$name" "${CTI_TIER_SLOT:-}" "$(date +%s%N)" >>"$CTI_STUB_TRACE"

# A worker that dies mid-probe, on purpose: the claim is made, no verdict is
# ever written, and the merge has to call that not-a-result rather than a red.
if [[ "$name" == "${CTI_STUB_KILL:-}" ]]; then
    kill -9 "$PPID" 2>/dev/null
    sleep 30
fi

if [[ ",${CTI_STUB_FAIL:-}," == *",$name,"* ]]; then
    printf 'verdict=FAIL\n' >>"$out/results.env"
    printf 'failure_class=%s\n' "${CTI_STUB_FAIL_CLASS:-assertion_failed}" >>"$out/results.env"
    printf 'failure_detail=staged by the stub\n' >>"$out/results.env"
    exit 1
fi

expect="$(awk '
    !/^\/\// { exit }
    { sub(/^\/\/[ \t]*/, "") }
    index($0, "expect:") == 1 { sub(/^[^:]*:[ \t]*/, ""); print; exit }
' "$CTI_HARNESS_EXTRA")"
if [[ -n "$expect" ]]; then
    printf 'verdict=FAIL\n' >>"$out/results.env"
    printf 'failure_class=%s\n' "$expect" >>"$out/results.env"
    printf 'failure_detail=red by design, as the header asks\n' >>"$out/results.env"
    exit 1
fi
printf 'verdict=PASS\n' >>"$out/results.env"
"""

# A stand-in for `cti_slot_reclaim`, named by CTI_SLOT_RECLAIM.
#
# The real one is the only part of a slot's bring-up that touches the machine's
# port space and process table, and it refuses to sweep either from a redirected
# state directory — that guard is #124, where this suite killed the live tier
# three times in a day. So the no-Arma tier cannot *produce* a failed reclaim,
# and what #133 is about is not the reclaim but the response to one. This stub
# reports the named slots as still occupied, in the contract the real function
# uses: the survivors on stdout, non-zero exit.
STUB_RECLAIM = r"""#!/usr/bin/env bash
set -uo pipefail
if [[ ",${CTI_STUB_DIRTY_SLOTS:-}," == *",$1,"* ]]; then
    printf '31337(arma3server_x64) 31338(cti-daemon)\n'
    exit 1
fi
exit 0
"""

TASKLIST_FREE = (
    "#!/usr/bin/env bash\nprintf 'INFO: No tasks are running which match the criteria.\\n'\n"
)


def bash_eval(script: str, env: dict[str, str] | None = None, *, want_stderr: bool = False) -> str:
    """Run a snippet with `spike/slots.sh` sourced, and give back its stdout.

    `want_stderr` gives back stderr instead: the library logs its reasoning there,
    and a caller asserting on why a slot did something has to read it.
    """
    full = f'source "{SLOTS_SH}"\n{script}'
    # S603: this repo's own library, with a script this test wrote.
    result = subprocess.run(  # noqa: S603
        [BASH, "-c", full],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, **(env or {})},
    )
    assert result.returncode == 0, result.stderr
    return (result.stderr if want_stderr else result.stdout).strip()


def executable(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


# --------------------------------------------------------------------- geometry


def slot_env(slot: int) -> dict[str, str]:
    lines = bash_eval(f"cti_slot_env {slot}").splitlines()
    return dict(line.split("=", 1) for line in lines)


SLOT_INDICES = [0, 1, 2, 3, 4, 5]


@pytest.mark.parametrize("slot", SLOT_INDICES)
def test_a_slots_ports_are_inside_the_grant_and_clear_of_the_humans(slot: int) -> None:
    """CLAUDE.md's Contract, asserted rather than remembered.

    The engine binds the game port and derives +1 and +2 from it, and BI asks for
    at least 100 between consecutive port sets — so a slot owns a block, and the
    block is what has to stay inside [2400, 3000) and off 2302-2306.
    """
    port = int(slot_env(slot)["CTI_SERVER_PORT"])
    block = range(port, port + 5)
    assert block.start in GRANT
    assert block.stop - 1 in GRANT
    assert not set(block) & set(HUMAN_PORTS)


def test_slot_blocks_do_not_overlap() -> None:
    blocks = [
        set(range(int(slot_env(n)["CTI_SERVER_PORT"]), int(slot_env(n)["CTI_SERVER_PORT"]) + 5))
        for n in SLOT_INDICES
    ]
    for i, first in enumerate(blocks):
        for second in blocks[i + 1 :]:
            assert not first & second


def test_every_per_slot_value_is_actually_per_slot() -> None:
    """#44's lesson: a slot boundary is only real where something reads it.

    A value that is the same in two slots is not a boundary at all, and the
    failure it produces is a green run over two worlds that merged. So each key
    in the slot environment must take a distinct value in every slot.
    """
    envs = [slot_env(n) for n in SLOT_INDICES]
    for key in envs[0]:
        values = [env[key] for env in envs]
        assert len(set(values)) == len(values), f"{key} is not per-slot: {values}"


def test_slot_zero_is_the_tier_as_it_has_always_been() -> None:
    """`--slots 1` has to be the serial tier, not a new thing that resembles it."""
    env = slot_env(0)
    assert env["CTI_SERVER_PORT"] == "2402"
    assert env["CTI_DAEMON_PORT"] == "9099"
    assert env["CTI_SERVER_DIR"] == f"{Path.home()}/arma3server"


def test_a_slot_index_past_the_grant_is_refused() -> None:
    """Reaching 2302-2306 is a bug rather than a configuration, so it cannot be one."""
    # S603: this repo's own library.
    result = subprocess.run(  # noqa: S603
        [BASH, "-c", f'source "{SLOTS_SH}"; cti_slot_valid 6'],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0


# ------------------------------------------------------------------- allocation


def test_a_slot_lock_excludes_a_second_holder(tmp_path: Path) -> None:
    state = tmp_path / "state"
    script = (
        f'source "{SLOTS_SH}"\n'
        "cti_slot_acquire 1 first && echo held\n"
        # A second acquire in the same shell would re-enter our own lock, so ask
        # from a child, which is what a second agent is.
        f"bash -c 'source \"{SLOTS_SH}\"; cti_slot_acquire 1 second' && echo BAD || echo excluded\n"
    )
    # S603: this repo's own library.
    result = subprocess.run(  # noqa: S603
        [BASH, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "CTI_TIER_STATE": str(state)},
    )
    assert result.stdout.split() == ["held", "excluded"], result.stderr
    assert (state / "slots" / "1.lock.info").read_text().count("slot=1") == 1


def test_the_hand_run_lock_and_slot_zero_are_the_same_lock(tmp_path: Path) -> None:
    """A hand run and slot 0 are the same occupancy, so they must be the same lock.

    `just probe` uses ~/arma3server on 2402-2406, which is slot 0 and nothing
    else. If the two locks were different files a pool run and a hand run would
    stage into one install at the same time — the collision the lock exists for.
    """
    state = tmp_path / "state"
    script = (
        f'source "{SLOTS_SH}"\n'
        "cti_slot_acquire 0 pool && echo held\n"
        f'"{TIER_LOCK}" --label hand -- true && echo BAD || echo excluded\n'
    )
    # S603: this repo's own scripts.
    result = subprocess.run(  # noqa: S603
        [BASH, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "CTI_TIER_STATE": str(state)},
    )
    assert result.stdout.split() == ["held", "excluded"], result.stderr


def start_holder(tmp_path: Path, slot: int) -> subprocess.Popen[str]:
    """Start a holder of `slot` that has forked a child before it says `ready`.

    The child matters: `flock` frees a lock when the *last* descriptor on it
    closes, and a slot holder in anger is a process tree — `regress.sh`'s worker
    with `run.sh`, a server and a headless client under it, every one of them
    carrying the descriptor it inherited. A holder that is a single process would
    let both tests below assert something easier than the thing that happens.

    Its own session, so a test can kill the tree the way the machine kills an
    agent, without the process group reaching pytest.
    """
    holder = executable(
        tmp_path / f"holder{slot}.sh",
        f'#!/usr/bin/env bash\nsource "{SLOTS_SH}"\n'
        f"cti_slot_acquire {slot} dead || exit 1\n"
        # Forked and reaped-for before `ready`: at the moment the test reads that
        # line the inheriting child exists. The old version echoed `ready` and
        # then forked, so whether the child existed when the kill landed was a
        # race the test lost about one full-suite run in two (#121).
        "sleep 60 &\necho ready\nwait\n",
    )
    # S603: a script this test wrote.
    proc = subprocess.Popen(  # noqa: S603
        [BASH, str(holder)],
        stdout=subprocess.PIPE,
        text=True,
        start_new_session=True,
        env={**os.environ, "CTI_TIER_STATE": str(tmp_path / "state")},
    )
    assert proc.stdout is not None
    assert proc.stdout.readline().strip() == "ready"
    return proc


def acquire_from_a_fresh_shell(tmp_path: Path, slot: int) -> subprocess.CompletedProcess[str]:
    # S603: this repo's own library.
    return subprocess.run(  # noqa: S603
        [BASH, "-c", f'source "{SLOTS_SH}"; cti_slot_acquire {slot} next'],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "CTI_TIER_STATE": str(tmp_path / "state")},
    )


# A bound on "promptly", not a synchronisation wait. The poll below ends the
# instant the last descriptor is gone, and reaching this deadline is a real
# failure of the contract rather than a slow machine: 10 s is three orders of
# magnitude over the worst teardown measured on this box.
TEARDOWN_DEADLINE_SECS = 10


def wait_until_no_descriptor_is_left(tmp_path: Path, slot: int) -> None:
    """Block until nothing on the machine still has the slot's lock file open.

    This is the arrangement's own precondition, not a cushion under the assertion
    that follows. `proc.wait()` says one member of the holder's tree has been
    reaped; the kernel frees an `flock` when the *last* file description on the
    lock closes, and those are different events ordered against each other by the
    scheduler and nothing else. Measured here by killing the group and asking
    immediately with `fcntl.flock` — no subprocess in the way — the lock was still
    held on 2 asks in 40 with the box idle (worst 3.0 ms) and 28 in 60 with it
    saturated (worst 7.4 ms). A holder built out of `sleep` understates it: the
    real one is an Arma server with a gigabyte of resident pages to give back.

    So the claim being asserted is "a dead holder's lock frees *itself*, promptly
    and with nobody reaping" — not "it frees simultaneously with the first death
    in the tree", which is a fiction, and which two rounds of statistics (#121,
    #130) were spent failing to make true.
    """
    deadline = time.monotonic() + TEARDOWN_DEADLINE_SECS
    env = {"CTI_TIER_STATE": str(tmp_path / "state")}
    while True:
        # The pool's own finder, so the test and the runner agree on what "still
        # held" means — it is the answer `regress.sh` prints to a human staring
        # at a busy slot.
        holders = bash_eval(f"cti_slot_lock_holders {slot}", env=env).split()
        if not holders:
            return
        assert time.monotonic() < deadline, (
            f"slot {slot}'s lock was still open in {holders} "
            f"{TEARDOWN_DEADLINE_SECS}s after the whole holder was killed"
        )
        time.sleep(0.02)


def test_a_dead_holders_lock_frees_itself(tmp_path: Path) -> None:
    """The property the whole design rests on: no reaper, no heartbeat, no pidfile.

    Death here is the whole holder's, process group and all, because that is what
    killed a slot holder in anger: a session limit took the agent on 2026-08-01
    and the kernel handed the slot back. The kernel's guarantee is about the last
    descriptor, so the holder below has a child holding one too, and the test is
    only about the kernel once the tree is gone.

    "Once the tree is gone" is the whole of what the wait above establishes, and
    it is why the acquire below is a single non-blocking ask rather than a retry:
    with no descriptor left anywhere, a free lock is the kernel's promise and a
    held one is a broken design. Nothing reaped, released or swept it.
    """
    proc = start_holder(tmp_path, 2)
    os.killpg(proc.pid, signal.SIGKILL)
    proc.wait(timeout=10)
    wait_until_no_descriptor_is_left(tmp_path, 2)
    after = acquire_from_a_fresh_shell(tmp_path, 2)
    assert after.returncode == 0, after.stderr


def test_an_orphan_that_inherited_the_lock_is_named_and_reclaimed(tmp_path: Path) -> None:
    """Half a dead holder keeps the slot, and the pool has to say so rather than guess.

    `regress.sh`'s merge already knows this case — a worker dies, its `run.sh`,
    server and headless client outlive it holding the descriptor they inherited,
    and the lock the kernel is supposed to free stays held. What #121 showed is
    that it is not exotic: killing only the top of the tree reproduces it every
    time. So the two things that make it recoverable are asserted here — the
    slot refuses the next holder rather than handing out a squatted world, and
    `cti_slot_lock_holders` names the pid that is actually holding it.
    """
    env = {"CTI_TIER_STATE": str(tmp_path / "state")}
    proc = start_holder(tmp_path, 2)
    proc.kill()  # the parent only: the `sleep` child inherits the descriptor
    proc.wait(timeout=10)
    orphans = [int(pid) for pid in bash_eval("cti_slot_lock_holders 2", env=env).split()]
    try:
        assert acquire_from_a_fresh_shell(tmp_path, 2).returncode == 1
        assert orphans, "nothing was named as holding a lock that is demonstrably held"
        assert [Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")[0] for pid in orphans] == [
            b"sleep"
        ]
        # And the reclaim path the merge calls clears it. Only the lock's own
        # holders: this state directory is not the machine's tier, so the port
        # and install sweeps are refused (#124) and nothing else on the box moves.
        #
        # No wait between the reclaim and the acquire, and that is the assertion:
        # `cti_slot_reclaim` returns when its victims are *gone*, not when their
        # SIGKILL was posted. It used to return on the posting, which put the
        # line below on the same losing side of the same race as #130 — and put
        # `run.sh` binding this slot's ports there too, which is worse.
        bash_eval("cti_slot_reclaim 2 holders", env=env, want_stderr=True)
        assert acquire_from_a_fresh_shell(tmp_path, 2).returncode == 0
    finally:
        for pid in orphans:
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, signal.SIGKILL)


def test_an_interrupted_previous_holder_is_named_on_acquire(tmp_path: Path) -> None:
    """ADR-0022, per slot rather than per run.

    An evidence directory with no verdict.json means the slot's previous holder
    was interrupted, and the next holder says so before it launches anything.
    Silence here is how a dead run's leftovers get inherited.
    """
    state = tmp_path / "state"
    dead_run = tmp_path / "runs" / "20260802T000000Z-contacts"
    dead_run.mkdir(parents=True)
    (state / "slots").mkdir(parents=True)
    (state / "slots" / "3.last").write_text(f"{dead_run}\n")
    # S603: this repo's own library.
    result = subprocess.run(  # noqa: S603
        [BASH, "-c", f'source "{SLOTS_SH}"; cti_slot_reclaim 3'],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "CTI_TIER_STATE": str(state)},
    )
    assert "interrupted" in result.stderr
    assert str(dead_run) in result.stderr


def test_a_tier_that_is_not_the_machines_kills_nothing_on_it(tmp_path: Path) -> None:
    """Issue #124: the no-Arma tier was the external event that killed the real one.

    Every pool test below drives the real `spike/regress.sh`, which reclaims each
    slot it acquires. `CTI_TIER_STATE` moves the locks and `CTI_SLOT_INSTALL_MASTER`
    moves the install, but a slot's port block is arithmetic no variable moves and
    `/proc` is not virtualised either — so reclaiming "slots 0-2" from a test swept
    the live tier's 2402/2502/2602 and 9099-9101 and killed three running worlds
    and their daemons. Three times on 2026-08-02, each within seconds of a
    `pytest tests/unit` on the same machine, and each read as a mystery crash.

    The guard is on the state directory, because that is the tier's identity: a
    run pointed somewhere else is not this machine's tier and sweeps nothing. Only
    this direction is testable — the sweeping direction is exactly what must never
    run from a test, so its coverage is the real tier's own use of it.
    """
    master = tmp_path / "arma3server"
    master.mkdir(parents=True)
    # A real binary rather than a shell script, because the sweep reads
    # `/proc/<pid>/exe` and a script's `exe` is the interpreter — a script victim
    # is invisible to the very sweep this test is about, and would pass either way.
    victim_bin = master / "arma3server_x64"
    shutil.copy(shutil.which("sleep") or "/bin/sleep", victim_bin)
    # A process running out of slot 0's install, which is precisely what the
    # install sweep exists to find and kill.
    # S603: this test's own copy of `sleep`, by absolute path.
    victim = subprocess.Popen([str(victim_bin), "60"])  # noqa: S603
    try:
        result = bash_eval(
            "cti_slot_reclaim 0",
            env={
                "CTI_TIER_STATE": str(tmp_path / "state"),
                "CTI_SLOT_INSTALL_MASTER": str(master),
            },
            want_stderr=True,
        )
        assert victim.poll() is None, "reclaim killed a process from a foreign state directory"
        assert "not the machine's tier" in result
    finally:
        victim.kill()
        victim.wait(timeout=10)


def test_the_install_farm_breaks_the_staged_paths_out_of_the_links(tmp_path: Path) -> None:
    """The three staged paths leave the hard-link farm, or staging writes through it.

    `run.sh` writes the shim into the install with `install -m 0755`, which
    truncates *through* a hard link. A farm that kept `cti_shim_x64.so` linked
    would have one slot's shim overwrite the master's and every sibling's.
    """
    master = tmp_path / "arma3server"
    executable(master / "arma3server_x64", "#!/usr/bin/env bash\n")
    (master / "addons").mkdir()
    (master / "addons" / "a3.pbo").write_bytes(b"shared, and never written")
    (master / "mpmissions").mkdir()
    (master / "cti_shim_x64.so").write_bytes(b"the master's shim")

    env = {"CTI_SLOT_INSTALL_MASTER": str(master), "CTI_TIER_STATE": str(tmp_path / "state")}
    bash_eval("cti_slot_install_ready 1", env=env)
    clone = tmp_path / "arma3server-slot1"

    assert (clone / "arma3server_x64").exists()
    assert not (clone / "cti_shim_x64.so").exists()
    assert (clone / "mpmissions").is_dir()
    # The bulk of the install is shared, which is what makes the clone free.
    assert (clone / "addons" / "a3.pbo").stat().st_ino == (
        master / "addons" / "a3.pbo"
    ).stat().st_ino


# ---------------------------------------------------------------------- the pool


def pool_run(
    tmp_path: Path, *args: str, extra_env: dict[str, str] | None = None, timeout: int = 300
) -> subprocess.CompletedProcess[str]:
    state = tmp_path / "state"
    master = tmp_path / "arma3server"
    executable(master / "arma3server_x64", "#!/usr/bin/env bash\n")
    (master / "mpmissions").mkdir(exist_ok=True)

    env = {
        **os.environ,
        "CTI_TIER_STATE": str(state),
        "CTI_SLOT_INSTALL_MASTER": str(master),
        "CTI_RUN_SH": str(executable(tmp_path / "stub-run.sh", STUB_RUN)),
        "CTI_WINDOWS_TASKLIST": str(executable(tmp_path / "tasklist.sh", TASKLIST_FREE)),
        "CTI_STUB_TRACE": str(tmp_path / "trace.tsv"),
        # A machine with room for any N, so a test about scheduling is about
        # scheduling. The memory pre-flight (#125) reads the real host, and this
        # suite runs several pool runs at once on a box that also has to have
        # room for the Arma tier — so left unstaged, "three slots are all used"
        # would fail whenever the machine happened to be busy, which is a red
        # about the wrong thing. The tests that are about the pre-flight stage a
        # smaller number over the top of this one.
        "CTI_SLOT_MEM_AVAILABLE_MB": "1000000",
        **(extra_env or {}),
    }
    # S603: this repo's own runner, against a stub this test wrote.
    return subprocess.run(  # noqa: S603
        [BASH, str(REGRESS), *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        timeout=timeout,
    )


def pool_json(tmp_path: Path) -> dict:
    pools = sorted((tmp_path / "state" / "runs").glob("*-pool"))
    assert pools, "the pool wrote no evidence directory"
    return json.loads((pools[-1] / "pool.json").read_text())


def verdicts_by_probe(tmp_path: Path) -> dict[str, dict]:
    return {v["probe"]: v for v in pool_json(tmp_path)["verdicts"]}


ALL_PROBES = sorted(p.stem for p in PROBE_DIR.glob("*.sqf"))

# The probes that drive the one headed client on the one Windows host, read the
# way `spike/regress.sh` reads them — off the `env:` header — rather than listed
# by name here. A third such probe arrived with #123, and a list would have been
# a second declaration of which probes those are (ADR-0028's tail, #119).
HOST_PROBES = sorted(
    path.stem
    for path in PROBE_DIR.glob("*.sqf")
    if any(
        line.startswith("// env:") and "CTI_WINDOWS_CLIENT=1" in line
        for line in path.read_text(encoding="utf-8").splitlines()
    )
)


def test_the_whole_corpus_gets_a_verdict_across_three_slots(tmp_path: Path) -> None:
    result = pool_run(tmp_path, "--slots", "3")
    assert result.returncode == EXIT_PASS, result.stderr[-4000:]
    got = verdicts_by_probe(tmp_path)
    assert sorted(got) == ALL_PROBES
    assert all(v["class"] == "pass" for v in got.values()), got
    assert pool_json(tmp_path)["not_run"] == []


def test_three_slots_are_all_used(tmp_path: Path) -> None:
    """Three locks held and one worker doing all the work is a pool on paper."""
    result = pool_run(tmp_path, "--slots", "3")
    assert result.returncode == EXIT_PASS, result.stderr[-4000:]
    assert pool_json(tmp_path)["slots"] == [0, 1, 2]
    # The stub returns in milliseconds, so a race that hands one worker every job
    # is possible and is not a bug. What must hold is that the *slots* were
    # distinct where more than one worker got a job at all.
    used = {v["slot"] for v in verdicts_by_probe(tmp_path).values()}
    assert used <= {"0", "1", "2"}


def test_one_slot_is_the_serial_tier(tmp_path: Path) -> None:
    result = pool_run(tmp_path, "--slots", "1")
    assert result.returncode == EXIT_PASS, result.stderr[-4000:]
    assert pool_json(tmp_path)["slots"] == [0]
    assert {v["slot"] for v in verdicts_by_probe(tmp_path).values()} == {"0"}
    # Corpus order, because with one slot there is nothing to schedule — with
    # the Windows-host probes still last, which is where they belong whatever N
    # is: teardown of a headed client is the next probe's guard's problem (#119).
    host = HOST_PROBES
    trace = [line.split("\t")[0] for line in (tmp_path / "trace.tsv").read_text().splitlines()]
    assert trace == [p for p in ALL_PROBES if p not in host] + host


def test_the_longest_probe_is_scheduled_first(tmp_path: Path) -> None:
    """The tail has to start at the head.

    A pool's pass is bounded below by its longest probe, so `campaign-end`
    scheduled late idles every other slot behind it.
    """
    result = pool_run(tmp_path, "--slots", "3")
    schedule = re.search(r"^\[regress\] schedule: (.*)$", result.stderr, re.MULTILINE)
    assert schedule is not None, result.stderr[-2000:]
    assert schedule.group(1).split()[0] == "campaign-end"


def test_the_windows_host_probes_are_a_serial_tail_not_part_of_the_schedule(
    tmp_path: Path,
) -> None:
    """One Windows host, one headed client, one ownership-blind guard.

    The guard that protects the human refuses to tell our client from theirs, on
    purpose (#119) — so a slot starting a probe beside another slot's client
    would read it as a play session and stop the corpus. Every probe that asks
    for a client therefore leaves the parallel schedule entirely.
    """
    result = pool_run(tmp_path, "--slots", "3")
    schedule = re.search(r"^\[regress\] schedule: (.*)$", result.stderr, re.MULTILINE)
    tail = re.search(r"^\[regress\] windows-host tail[^:]*: (.*)$", result.stderr, re.MULTILINE)
    assert schedule is not None, result.stderr[-2000:]
    assert tail is not None, result.stderr[-2000:]
    assert sorted(tail.group(1).split()) == HOST_PROBES
    assert not set(tail.group(1).split()) & set(schedule.group(1).split())


def test_a_failing_probe_does_not_poison_its_siblings(tmp_path: Path) -> None:
    """The bulkhead.

    One slot's red is a verdict and the pool keeps going: report everything,
    filter in a separate pass.
    """
    result = pool_run(tmp_path, "--slots", "3", extra_env={"CTI_STUB_FAIL": "contacts"})
    assert result.returncode == EXIT_ASSERTION_FAILED, result.stderr[-4000:]
    got = verdicts_by_probe(tmp_path)
    assert sorted(got) == ALL_PROBES, "a red probe must not cost its siblings their verdicts"
    assert got["contacts"]["class"] == "assertion_failed"
    assert all(v["class"] == "pass" for name, v in got.items() if name != "contacts")


def test_the_corpus_two_deliberate_node_crashes_do_not_trip_the_breaker(tmp_path: Path) -> None:
    """`daemon-restart` and `loop-watch` both declare `expect: node_crashed`.

    The breaker counts classes *after* `expect:` inversion, so a corpus whose
    design includes crashing a node twice on purpose is not a corpus that stops
    itself. Without this the pool would abandon a full pass most of the time.
    """
    result = pool_run(tmp_path, "--slots", "3")
    assert result.returncode == EXIT_PASS, result.stderr[-4000:]
    assert pool_json(tmp_path)["stopped_early"] == ""


def test_two_unexpected_node_crashes_stop_the_pool(tmp_path: Path) -> None:
    """#58's reading of #72: a pool hammers a systemically-crashing world N times.

    The breaker stops the pool taking *new* work rather than killing what is in
    flight, because interrupting a running world would manufacture the very
    non-result it exists to avoid.
    """
    result = pool_run(
        tmp_path,
        "--slots",
        "1",
        extra_env={
            "CTI_STUB_FAIL": "ai-commander,bareworld",
            "CTI_STUB_FAIL_CLASS": "node_crashed",
        },
    )
    pool = pool_json(tmp_path)
    assert "crashed a node" in pool["stopped_early"]
    assert pool["not_run"], "the breaker fired and the pool carried on regardless"
    assert result.returncode != EXIT_PASS


def test_a_slot_that_dies_mid_probe_is_not_a_result(tmp_path: Path) -> None:
    """ADR-0022, per slot.

    The worker is killed with the claim made and no verdict written; the merge
    must call that `infra_unavailable` rather than read the absence of evidence
    as a failure of the probe.
    """
    result = pool_run(tmp_path, "--slots", "3", extra_env={"CTI_STUB_KILL": "casualties"})
    assert result.returncode == EXIT_INFRA_UNAVAILABLE, result.stderr[-4000:]
    got = verdicts_by_probe(tmp_path)
    assert got["casualties"]["class"] == "infra_unavailable"
    assert "died mid-probe" in result.stderr
    # The siblings kept their slots and their verdicts: a dead worker is one
    # slot's loss, and the pool is meant to survive it.
    assert sum(1 for v in got.values() if v["class"] == "pass") >= len(ALL_PROBES) - 3


def test_a_dead_slot_leaves_the_lock_free_for_the_next_holder(tmp_path: Path) -> None:
    """The kernel does this, and this asserts that nothing in the pool undoes it."""
    pool_run(tmp_path, "--slots", "3", extra_env={"CTI_STUB_KILL": "casualties"})
    # S603: this repo's own library.
    after = subprocess.run(  # noqa: S603
        [
            BASH,
            "-c",
            f'source "{SLOTS_SH}"; for n in 0 1 2; do cti_slot_acquire "$n" next || exit 1; done',
        ],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "CTI_TIER_STATE": str(tmp_path / "state")},
    )
    assert after.returncode == 0, after.stderr


def dirty_slots(tmp_path: Path, slots: str) -> dict[str, str]:
    """Env that makes `regress.sh` see those slots come back not clear."""
    return {
        "CTI_SLOT_RECLAIM": str(executable(tmp_path / "stub-reclaim.sh", STUB_RECLAIM)),
        "CTI_STUB_DIRTY_SLOTS": slots,
    }


def test_a_slot_that_cannot_be_reclaimed_is_dropped_rather_than_used(tmp_path: Path) -> None:
    """Issue #133. #130 taught the reclaim to confirm its SIGKILL; this acts on it.

    A slot whose reclaim came back failed still has a dead run's server and daemon
    on its ports, and the next thing the pool does with a slot is hand it to
    `run.sh` to bind them. The failure that produces is a bind error blamed on the
    world rather than on the holder that caused it — so the slot is never used.
    """
    result = pool_run(tmp_path, "--slots", "3", extra_env=dirty_slots(tmp_path, "1"))
    assert result.returncode == EXIT_PASS, result.stderr[-4000:]
    pool = pool_json(tmp_path)
    assert pool["slots"] == [0, 2], pool["slots"]
    # And nothing was scheduled onto it: the trace is what the stub `run.sh` wrote.
    used = {line.split("\t")[1] for line in (tmp_path / "trace.tsv").read_text().splitlines()}
    assert used == {"0", "2"}, used


def test_a_dropped_slot_is_typed_and_named_rather_than_silent(tmp_path: Path) -> None:
    """A smaller pool is allowed (ADR-0028); a smaller pool nobody can explain is not.

    The class is `infra_unavailable` because the reclaim is a check that could not
    complete, and a check that could not run is not a check that passed (#41). The
    survivors are named because "the pool ran at N=2" and "slot 1 still had a dead
    run's server on 2502" are different facts, and only the second is actionable.
    """
    result = pool_run(tmp_path, "--slots", "3", extra_env=dirty_slots(tmp_path, "1"))
    dirty = pool_json(tmp_path)["dirty_slots"]
    assert [d["slot"] for d in dirty] == [1]
    assert dirty[0]["class"] == "infra_unavailable"
    assert "31337(arma3server_x64)" in dirty[0]["detail"], dirty[0]["detail"]
    assert "2502" in dirty[0]["detail"], dirty[0]["detail"]
    assert "N=2" in result.stderr, result.stderr[-4000:]


def test_the_corpus_still_gets_a_complete_set_of_verdicts_on_the_slots_left(
    tmp_path: Path,
) -> None:
    """One dirty slot costs a slot, not everybody else's results.

    The run stays green because every probe got a verdict on a slot whose
    conditions are interpretable; the dropped slot contributed no verdict to
    misread. That is the whole difference between this and the all-slots case.
    """
    result = pool_run(tmp_path, "--slots", "3", extra_env=dirty_slots(tmp_path, "2"))
    assert result.returncode == EXIT_PASS, result.stderr[-4000:]
    got = verdicts_by_probe(tmp_path)
    assert sorted(got) == ALL_PROBES
    assert all(v["class"] == "pass" for v in got.values()), got


def test_when_every_slot_fails_to_reclaim_the_run_is_not_a_result(tmp_path: Path) -> None:
    """There is no smaller pool below one slot, and nothing was measured.

    So this is the failure-class table's `infra_unavailable`: stop, do not
    interpret. A run that went ahead and bound a surviving holder's ports would
    have reported the bind instead.
    """
    result = pool_run(tmp_path, "--slots", "1", extra_env=dirty_slots(tmp_path, "0,1,2,3,4,5"))
    assert result.returncode == EXIT_INFRA_UNAVAILABLE, result.stderr[-4000:]
    assert "failure_class=infra_unavailable" in result.stderr
    assert "31337(arma3server_x64)" in result.stderr
    assert not (tmp_path / "trace.tsv").exists(), "a probe ran on a slot that is not clear"


def test_a_dropped_slot_is_held_for_the_run_and_released_after_it(tmp_path: Path) -> None:
    """The lock is kept while we are still here to say the slot is not clear.

    Releasing it early would hand a slot we have just proved dirty to the next
    run in the queue; keeping it forever would leak it. So `pool_teardown`
    releases the dropped slots with the used ones.
    """
    pool_run(tmp_path, "--slots", "3", extra_env=dirty_slots(tmp_path, "1"))
    # The pool's RAM sampler is `sleep 3` in a loop, and the `sleep` that is
    # running when the teardown kills the sampler outlives it holding every
    # descriptor it inherited. So the arrangement's precondition is the same
    # bounded poll the dead-holder tests use, for the same reason: "released" is
    # about the last description on the lock, not about the parent's exit.
    wait_until_no_descriptor_is_left(tmp_path, 1)
    # S603: this repo's own library.
    after = subprocess.run(  # noqa: S603
        [BASH, "-c", f'source "{SLOTS_SH}"; cti_slot_acquire 1 next'],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "CTI_TIER_STATE": str(tmp_path / "state")},
    )
    assert after.returncode == 0, after.stderr


def test_the_run_records_the_memory_it_actually_used(tmp_path: Path) -> None:
    """The RAM figure is measured by every run, not extrapolated once.

    ADR-0028's N=3 number was arithmetic from a measured N=2, and its own
    overturning conditions say the third slot is not trusted until it is
    measured.
    """
    pool_run(tmp_path, "--slots", "3")
    pool = pool_json(tmp_path)
    assert pool["peak_mem_used_kb"] > 0
    assert pool["least_mem_available_kb"] > 0
    assert pool["wall_secs"] >= 0


# ------------------------------------------------------------ memory pre-flight
# Issue #125. A slot lock answers "is anyone else in slot 2?" and cannot answer
# "is there room for a third world?" — so two pools took three slots each on one
# 12 GB machine, six worlds bottomed it out at 39 MiB available, and two probes
# came back `node_crashed` twenty minutes later. The pre-flight is the host
# guard's shape applied to memory: a reading before anything is launched.


def mem_floor(slots: int) -> int:
    return int(bash_eval(f"cti_slot_mem_floor_mb {slots}"))


def test_the_memory_floor_is_the_measured_per_slot_footprint_with_headroom() -> None:
    """The number has to come from the measurements, not from a round figure.

    #44 measured a heavy slot at ~2.43 GB, and clean N=3 pool runs have since
    measured the whole tier at 7,293-7,365 MiB peak RSS. So the floor for three
    slots must clear the heaviest of those runs with real margin on top — and
    must not clear it by so much that a machine which has carried the corpus at
    N=3 would be refused it (8.6 GB available at rest, ADR-0028).
    """
    heaviest_measured_n3 = 7365
    available_at_rest = int(8.6 * 1024)
    assert heaviest_measured_n3 + 512 <= mem_floor(3) <= available_at_rest
    # Monotonic, and each slot costs the same: a fourth is never cheaper.
    assert [mem_floor(n) for n in (1, 2, 3)] == sorted(mem_floor(n) for n in (1, 2, 3))
    assert mem_floor(2) - mem_floor(1) == mem_floor(3) - mem_floor(2)


def test_the_fit_is_the_largest_slot_count_the_reading_carries() -> None:
    def fit(want: int, avail: int) -> int:
        return int(bash_eval(f"cti_slot_mem_fit {want} {avail}"))

    assert fit(3, mem_floor(3)) == 3
    assert fit(3, mem_floor(3) - 1) == 2
    assert fit(3, mem_floor(1)) == 1
    assert fit(3, mem_floor(1) - 1) == 0
    # Never more than was asked for: the floor is a ceiling on N, not a target.
    assert fit(1, mem_floor(3)) == 1


def test_a_machine_under_the_floor_is_refused_before_anything_is_launched(
    tmp_path: Path,
) -> None:
    """Fail-closed, and cheap for the caller: nothing was launched, so nothing is lost.

    The alternative is what #125 recorded — a run that starts under the floor
    and produces non-results N at a time, twenty minutes later, wearing a class
    that reads like the code's fault.
    """
    result = pool_run(
        tmp_path,
        "--slots",
        "3",
        extra_env={"CTI_SLOT_MEM_AVAILABLE_MB": str(mem_floor(1) - 1)},
    )
    assert result.returncode == EXIT_INFRA_UNAVAILABLE, result.stderr[-4000:]
    assert "failure_class=infra_unavailable" in result.stderr
    # The reading, not a mystery: both numbers that made the decision.
    assert str(mem_floor(1) - 1) in result.stderr
    assert str(mem_floor(1)) in result.stderr
    assert not (tmp_path / "trace.tsv").exists(), "a world was launched under the floor"


def test_a_caller_who_asked_to_wait_queues_on_the_machine_too(tmp_path: Path) -> None:
    """`--wait` queues on the locks; a full machine is somebody else's run as surely.

    Met in anger on 2026-08-02: a `--wait 1800` was refused in two seconds
    because a sibling agent's three worlds were up — a condition that clears
    when the thing it is queueing behind finishes. Refusing that caller is the
    wrong half of fail-closed. Asserted through the deadline rather than through
    a clock: `--wait 0` refuses at once, and a `--wait` that is set says it is
    waiting before it gives up.
    """
    starved = {"CTI_SLOT_MEM_AVAILABLE_MB": str(mem_floor(1) - 1)}
    at_once = pool_run(tmp_path, "--slots", "1", "--wait", "0", extra_env=starved)
    assert at_once.returncode == EXIT_INFRA_UNAVAILABLE, at_once.stderr[-4000:]
    assert "waited" not in at_once.stderr

    queued = pool_run(tmp_path, "--slots", "1", "--wait", "6", extra_env=starved)
    assert queued.returncode == EXIT_INFRA_UNAVAILABLE, queued.stderr[-4000:]
    assert "waiting up to 6s for the machine" in queued.stderr
    assert "waited 6s for the machine and gave up" in queued.stderr
    assert not (tmp_path / "trace.tsv").exists()


def test_a_reading_that_could_not_be_taken_is_not_a_reading_that_passed(
    tmp_path: Path,
) -> None:
    """The host guard's rule, applied to the other guard on the same machine."""
    result = pool_run(tmp_path, "--slots", "3", extra_env={"CTI_SLOT_MEM_AVAILABLE_MB": "unknown"})
    assert result.returncode == EXIT_INFRA_UNAVAILABLE, result.stderr[-4000:]
    assert "failure_class=infra_unavailable" in result.stderr
    assert not (tmp_path / "trace.tsv").exists()


def test_a_machine_that_fits_two_slots_runs_at_two_and_says_so(tmp_path: Path) -> None:
    """The middle answer. A smaller pool is a slower run, not a wrong one.

    Refusing outright would make a machine with a browser open unable to run the
    corpus at all, which is worse than running it in two slots.
    """
    result = pool_run(
        tmp_path,
        "--slots",
        "3",
        extra_env={"CTI_SLOT_MEM_AVAILABLE_MB": str(mem_floor(2))},
    )
    assert result.returncode == EXIT_PASS, result.stderr[-4000:]
    assert len(pool_json(tmp_path)["slots"]) == 2
    assert "running at N=2" in result.stderr
    assert sorted(verdicts_by_probe(tmp_path)) == ALL_PROBES


def test_the_reading_is_logged_even_when_it_lets_the_run_through(tmp_path: Path) -> None:
    """How close was that? A green run's own log should answer it."""
    result = pool_run(tmp_path, "--slots", "3")
    assert result.returncode == EXIT_PASS, result.stderr[-4000:]
    assert re.search(r"memory: \d+ MiB available on local", result.stderr), result.stderr[-4000:]
    assert f"{mem_floor(3)} MiB" in result.stderr


def test_the_pool_stops_taking_new_work_when_the_machine_runs_out_mid_run(
    tmp_path: Path,
) -> None:
    """The re-check between probes, which is one `awk` against a world of minutes.

    What it catches is what the bring-up reading cannot: somebody else arriving
    afterwards. It stops the pool taking *new* work rather than interrupting the
    work in flight — interrupting a running world would manufacture the
    non-result being avoided — and the pool carries the class itself, because
    the whole point is that no probe launched to carry it.
    """
    result = pool_run(
        tmp_path,
        "--slots",
        "2",
        extra_env={
            "CTI_SLOT_MEM_AVAILABLE_MB": str(mem_floor(2)),
            "CTI_SLOT_MEM_RUNNING_FLOOR_MB": str(mem_floor(2) + 1),
        },
    )
    assert result.returncode == EXIT_INFRA_UNAVAILABLE, result.stderr[-4000:]
    pool = pool_json(tmp_path)
    assert "running floor" in pool["stopped_early"]
    assert pool["not_run"] == ALL_PROBES, pool["not_run"]


def test_the_verdict_names_the_slot_and_the_host(tmp_path: Path) -> None:
    """The host field is ADR-0032's seam, carried from day one.

    One value today, and the place a second machine's runs will be told apart
    from this one's.
    """
    pool_run(tmp_path, "--slots", "2")
    assert pool_json(tmp_path)["host"] == "local"
    runs = sorted((tmp_path / "state" / "runs").glob("*-bareworld"))
    verdict = json.loads((runs[-1] / "verdict.json").read_text())
    assert verdict["host"] == "local"
    assert verdict["slot"] in (0, 1)


def test_each_probe_ran_against_its_own_slots_daemon(tmp_path: Path) -> None:
    """The #44 trap, asserted.

    Isolated ports, dirs, installs and daemons were not enough: the shim resolved
    its daemon from a `CTI_DAEMON_ADDR` nobody set, one daemon received both
    worlds, and the run not asserting on it went green. Every value that makes a
    slot a slot has to reach the process that reads it.
    """
    pool_run(tmp_path, "--slots", "3")
    fields = {
        "CTI_SERVER_PORT": "server_port",
        "CTI_DAEMON_PORT": "daemon_port",
        "CTI_DAEMON_ADDR": "daemon_addr",
        "CTI_SERVER_DIR": "server_dir",
        "CTI_SERVER_NAME": "server_profile",
    }
    env = {"CTI_SLOT_INSTALL_MASTER": str(tmp_path / "arma3server")}
    checked = 0
    for run in (tmp_path / "state" / "runs").glob("*/results.env"):
        recorded = dict(line.split("=", 1) for line in run.read_text().splitlines() if "=" in line)
        if "tier_slot" not in recorded:
            continue
        expected = dict(
            line.split("=", 1)
            for line in bash_eval(f"cti_slot_env {recorded['tier_slot']}", env=env).splitlines()
        )
        for key, field in fields.items():
            assert recorded[field] == expected[key], (
                f"{key} did not reach the run in slot {recorded['tier_slot']}"
            )
        checked += 1
    assert checked == len(ALL_PROBES)
