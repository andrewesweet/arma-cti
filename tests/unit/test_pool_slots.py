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

import json
import os
import re
import shutil
import stat
import subprocess
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

TASKLIST_FREE = (
    "#!/usr/bin/env bash\nprintf 'INFO: No tasks are running which match the criteria.\\n'\n"
)


def bash_eval(script: str, env: dict[str, str] | None = None) -> str:
    """Run a snippet with `spike/slots.sh` sourced, and give back its stdout."""
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
    return result.stdout.strip()


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


def test_a_dead_holders_lock_frees_itself(tmp_path: Path) -> None:
    """The property the whole design rests on: no reaper, no heartbeat, no pidfile."""
    state = tmp_path / "state"
    holder = executable(
        tmp_path / "holder.sh",
        f'#!/usr/bin/env bash\nsource "{SLOTS_SH}"\n'
        "cti_slot_acquire 2 dead && echo ready\nsleep 60\n",
    )
    # S603: a script this test wrote.
    proc = subprocess.Popen(  # noqa: S603
        [BASH, str(holder)],
        stdout=subprocess.PIPE,
        text=True,
        env={**os.environ, "CTI_TIER_STATE": str(state)},
    )
    assert proc.stdout is not None
    assert proc.stdout.readline().strip() == "ready"
    proc.kill()
    proc.wait(timeout=10)
    # S603: this repo's own library.
    after = subprocess.run(  # noqa: S603
        [BASH, "-c", f'source "{SLOTS_SH}"; cti_slot_acquire 2 next'],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "CTI_TIER_STATE": str(state)},
    )
    assert after.returncode == 0, after.stderr


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
    host = ["client-port", "human-commander"]
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
    would read it as a play session and stop the corpus. The two client probes
    therefore leave the parallel schedule entirely.
    """
    result = pool_run(tmp_path, "--slots", "3")
    schedule = re.search(r"^\[regress\] schedule: (.*)$", result.stderr, re.MULTILINE)
    tail = re.search(r"^\[regress\] windows-host tail[^:]*: (.*)$", result.stderr, re.MULTILINE)
    assert schedule is not None, result.stderr[-2000:]
    assert tail is not None, result.stderr[-2000:]
    assert sorted(tail.group(1).split()) == ["client-port", "human-commander"]
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
