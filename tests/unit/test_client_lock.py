"""The headed Windows client as a machine-wide resource (issue #127).

The pool schedules its client probes into a serial tail with every other slot
drained (#47), which orders them against each other and against nothing else.
Two agents gating from sibling worktrees each drained their own pool and then
both drove the one client on the one Windows host: while #125 was landing,
two corpus attempts were stopped `infra_unavailable` by a sibling's client
tripping the ownership-blind host guard.

`spike/client-lock.sh` is the missing serialisation — one `flock(2)` on
`~/.arma-cti/windows-client.lock`, outside every worktree, taken around the
client leg. What it buys is an ordering: a holder does not release until
`cti_windows_wait_gone` has watched its own client leave the process list, so
while a run holds the lock, a client in that list is the human's and the guard's
refusal is the right one. The guard itself learns nothing — `#119`'s rule that a
guard which can excuse ours can be talked into excusing the human's is asserted
still-standing in `tests/unit/test_host_guard.py`.

None of this needs Arma. The lock is `flock`, the queueing is a bounded wait, and
the two-runs-at-once case is two `regress.sh` processes over a stub `run.sh` —
the `CTI_RUN_SH` seam `tests/unit/test_pool_slots.py` uses and the substituted
Windows process list `tests/unit/test_bringup_guards.py` uses.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import stat
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from pathlib import Path

import pytest
from conftest import REPO

# Same directory, pytest's prepend import mode. The probes whose `env:` header
# drives the headed client are derived from those headers in one place; this
# file used to name two of them by hand, and by #157 there were six.
from test_probe_headers import HOST_PROBES

CLIENT_LOCK_SH = REPO / "spike" / "client-lock.sh"
REGRESS = REPO / "spike" / "regress.sh"
RUN = REPO / "spike" / "run.sh"
BASH = shutil.which("bash") or "/bin/bash"

EXIT_INFRA_UNAVAILABLE = 5

# How long the stub holds the whole contended leg open, and each probe's share
# of it. A slice rather than a fixed time each, so the window
# `test_two_concurrent_pools_never_hold_the_client_at_once` watches keeps its
# width as the corpus grows: the lock is taken around the tail rather than
# around a probe, so what makes an overlap visible is the tail's width against
# the fraction of a second the two pools start apart.
CLIENT_TAIL_SECONDS = 2.0
CLIENT_LEG_SECONDS = round(CLIENT_TAIL_SECONDS / len(HOST_PROBES), 3)

TASKLIST_FREE = "INFO: No tasks are running which match the specified criteria.\n"
TASKLIST_PRESENT = (
    "\n"
    "Image Name                     PID Session Name        Session#    Mem Usage\n"
    "========================= ======== ================ =========== ============\n"
    "arma3_x64.exe                24188 Console                    1  3,412,904 K\n"
)

# A stand-in for `spike/run.sh` that records *when* it held the client. The
# client leg is the interval this stub is inside; two runs that never overlap
# leave two disjoint intervals in the trace, which is the property under test.
STUB_RUN = r"""#!/usr/bin/env bash
set -uo pipefail
name="$(basename "${CTI_HARNESS_EXTRA:-unknown}" .sqf)"
out="$CTI_SPIKE_OUT"
printf 'client_lock_wait=%s\n' "${CTI_CLIENT_LOCK_WAIT:-unset}" >>"$out/results.env"
if [[ ",${CTI_STUB_HOST_PROBES:-}," == *",$name,"* ]]; then
    # The pool's tail must have told us it is holding the lock; a client leg
    # running without it is the bug this file exists for.
    printf '%s\t%s\t%s\t%s\n' "$CTI_STUB_TAG" "$name" open "$(date +%s%N)" >>"$CTI_STUB_TRACE"
    printf 'client_lock_held=%s\n' "${CTI_CLIENT_LOCK_HELD:-0}" >>"$out/results.env"
    sleep "$CTI_STUB_CLIENT_LEG_SECS"
    printf '%s\t%s\t%s\t%s\n' "$CTI_STUB_TAG" "$name" close "$(date +%s%N)" >>"$CTI_STUB_TRACE"
fi
printf 'server_version=2.20.152984\n' >>"$out/results.env"
printf 'verdict=PASS\n' >>"$out/results.env"
"""


def executable(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def tasklist(path: Path, listing: str) -> Path:
    return executable(path, f"#!/usr/bin/env bash\nprintf '%s' {listing!r}\n")


def flipping_tasklist(path: Path, flip: Path) -> Path:
    """Show a client in the list until `flip` appears, and not after.

    The sibling's client leaving the list and the sibling releasing the lock are
    then one event, which is the ordering every real holder gets from
    `cti_windows_wait_gone` — it does not let go until its own client is gone.
    """
    return executable(
        path,
        "#!/usr/bin/env bash\n"
        f'if [[ -e "{flip}" ]]; then printf "%s" {TASKLIST_FREE!r}; '
        f'else printf "%s" {TASKLIST_PRESENT!r}; fi\n',
    )


def lock_eval(script: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run a snippet with `spike/client-lock.sh` sourced."""
    full = f'source "{CLIENT_LOCK_SH}"\n{script}'
    # S603: this repo's own library, with a script this test wrote.
    return subprocess.run(  # noqa: S603
        [BASH, "-c", full],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, **(env or {})},
        timeout=120,
    )


def holding(
    state: Path, label: str, then: str = "sleep 120\n", **extra: str
) -> subprocess.Popen[str]:
    """Hold the client lock in a live process, ready by the time this returns."""
    script = (
        f'source "{CLIENT_LOCK_SH}"\n'
        f'cti_client_lock_acquire 0 "{label}" || exit 9\n'
        "printf ready\n" + then
    )
    # S603: this repo's own library.
    holder = subprocess.Popen(  # noqa: S603
        [BASH, "-c", script],
        env={**os.environ, "CTI_TIER_STATE": str(state), **extra},
        stdout=subprocess.PIPE,
        text=True,
    )
    assert holder.stdout is not None
    assert holder.stdout.read(5) == "ready"
    return holder


# ------------------------------------------------------------------- the lock


def test_the_lock_lives_outside_every_worktree(tmp_path: Path) -> None:
    """A repo-scoped lock serialises nobody: sibling worktrees hold their own."""
    got = lock_eval(
        "cti_client_lock_path", env={"CTI_TIER_STATE": str(tmp_path / "state")}
    ).stdout.strip()
    assert got == str(tmp_path / "state" / "windows-client.lock")
    # And by default it is beside the tier's own locks rather than in the repo.
    default = lock_eval("cti_client_lock_path", env={"CTI_TIER_STATE": ""}).stdout.strip()
    assert default == str(Path.home() / ".arma-cti" / "windows-client.lock")
    assert str(REPO) not in default


def test_a_second_taker_is_refused_and_told_whose_run_it_is_behind(tmp_path: Path) -> None:
    state = tmp_path / "state"
    env = {"CTI_TIER_STATE": str(state), "CTI_TIER_ISSUE": "127"}
    holder = holding(state, "the first run", CTI_TIER_ISSUE="127")
    try:
        second = lock_eval(
            'if cti_client_lock_acquire 0 "the second run"; then echo TOOK; else\n'
            "  echo REFUSED\n"
            "  cti_client_lock_holder\n"
            "fi",
            env=env,
        )
    finally:
        holder.kill()
    assert "TOOK" not in second.stdout, "two runs held the one Windows client"
    assert "REFUSED" in second.stdout
    assert "label=the first run" in second.stdout
    assert "issue=127" in second.stdout
    assert f"pid={holder.pid}" in second.stdout


def test_a_bounded_wait_queues_and_a_release_lets_it_through(tmp_path: Path) -> None:
    """#125's `--wait` precedent: waiting on a resource is a queue, not a retry."""
    state = tmp_path / "state"
    env = {"CTI_TIER_STATE": str(state)}
    holder = holding(state, "holder", then="sleep 2\ncti_client_lock_release\nsleep 30\n")
    try:
        waited = lock_eval('cti_client_lock_acquire 30 "queued" && echo TOOK', env=env)
    finally:
        holder.kill()
    assert "TOOK" in waited.stdout, waited.stderr


def test_a_dead_holders_lock_frees_itself(tmp_path: Path) -> None:
    """Use flock rather than a pidfile, for the reason ADR-0016 chose it."""
    state = tmp_path / "state"
    env = {"CTI_TIER_STATE": str(state)}
    holder = holding(state, "doomed", then="sleep 60\n")
    holder.kill()
    holder.wait(timeout=30)
    assert "TOOK" in lock_eval('cti_client_lock_acquire 0 "next" && echo TOOK', env=env).stdout


def test_our_own_lock_does_not_read_as_somebody_elses(tmp_path: Path) -> None:
    """A lock we hold ourselves is not somebody else's.

    `flock` conflicts between two open file descriptions of one process exactly
    as it does between two processes, so a naive busy check would read our own
    lock as a sibling's and queue the run behind itself.
    """
    env = {"CTI_TIER_STATE": str(tmp_path / "state")}
    result = lock_eval(
        'cti_client_lock_acquire 0 "ours" || exit 9\n'
        "cti_client_lock_busy && echo BUSY || echo FREE\n"
        "cti_client_lock_release\n",
        env=env,
    )
    assert result.stdout.strip() == "FREE", result.stderr


def test_release_takes_the_holder_metadata_with_it(tmp_path: Path) -> None:
    state = tmp_path / "state"
    env = {"CTI_TIER_STATE": str(state)}
    lock_eval('cti_client_lock_acquire 0 "ours" && cti_client_lock_release', env=env)
    assert not (state / "windows-client.lock.info").exists()
    stale = lock_eval("cti_client_lock_holder", env=env).stdout
    assert "no metadata" in stale


def test_a_child_that_outlives_the_run_does_not_keep_the_lock(tmp_path: Path) -> None:
    """The bug this lock arrived with, and the one that would outlast it.

    `flock` frees a lock only when the last open file description closes, and a
    background subshell inherits every descriptor. The first `just unit` after
    this lock landed went red: a stub server that outlived its `run.sh` was still
    holding `~/.arma-cti/windows-client.lock`, against a `.info` its dead parent
    had already deleted — a machine-wide stop with nobody to name.

    The child's stdio goes to `/dev/null` (#197). It used to inherit the pipes
    `capture_output` hands the parent, so this test did not end when its claim
    was settled — it ended sixty seconds later, when the child's `sleep` let go
    of a descriptor the claim is not about. The lock descriptor, which the claim
    *is* about, is still inherited and still disowned: the child outlives the
    run exactly as before, and the parent still releases and asks while it does.
    """
    state = tmp_path / "state"
    env = {"CTI_TIER_STATE": str(state)}
    leaked = tmp_path / "leaked.pid"
    result = lock_eval(
        'cti_client_lock_acquire 0 "the parent" || exit 9\n'
        "(\n"
        "  cti_client_lock_disown\n"
        f'  printf "%s" "$BASHPID" > "{leaked}"\n'
        "  exec sleep 60\n"
        ") >/dev/null 2>&1 &\n"
        f'while [[ ! -s "{leaked}" ]]; do sleep 0.05; done\n'
        "cti_client_lock_release\n"
        "cti_client_lock_busy && echo STILL-HELD || echo FREE\n",
        env=env,
    )
    try:
        assert result.stdout.strip() == "FREE", result.stderr
    finally:
        pid = int(leaked.read_text())
        with suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)


def test_the_holder_metadata_block_has_one_home() -> None:
    """#161: the `.info` block beside a lock was written in three places.

    Slot locks, the client lock and the hand-run tier lock each carried a
    near-copy of the seven-field block, so a field added to one drifted from
    the others. `spike/lock-info.sh` is the one writer now, and this holds
    spike/*.sh to it — the block's first line is the fingerprint, because every
    copy began by naming the holder's pid.
    """
    writers = [
        script.name
        for script in sorted((REPO / "spike").glob("*.sh"))
        if "printf 'pid=" in script.read_text()
    ]
    assert writers == ["lock-info.sh"], writers


def test_every_background_launch_in_run_sh_lets_go_of_the_lock() -> None:
    """A tripwire for the next launch somebody adds.

    The failure above is silent, machine-wide and outlives the run that caused
    it, so it is worth catching structurally rather than waiting for the next
    agent's corpus to be stopped by a process nobody can find.
    """
    text = (REPO / "spike" / "run.sh").read_text()
    launches = [line for line in text.splitlines() if line.rstrip().endswith(" &")]
    disowns = text.count("cti_client_lock_disown")
    assert disowns == len(launches), (
        f"{len(launches)} background launches in run.sh, {disowns} of them disown the "
        "client lock; a child that keeps it holds the Windows client for every later run"
    )


def test_no_unit_test_drives_these_scripts_against_the_real_lock() -> None:
    """The other tripwire, one level up: the no-Arma tier owns no machine state.

    `CTI_TIER_STATE` is what moves the tier and client locks out of
    `$HOME/.arma-cti` and into a `tmp_path`. A unit test that forgets it takes
    the machine-wide Windows client lock for real — stealing it from a live
    Arma-tier run, and being refused by one, which run.sh reports as an
    `infra_unavailable` before it launches anything. That is #132: one red in 26
    full-suite runs, and reproducible in the no-Arma tier alone by running two
    suites at once.
    """
    drivers = {'"run.sh"', '"regress.sh"', '"client-lock.sh"', '"slots.sh"', '"tier-lock.sh"'}
    # An assignment, not a mention: the first draft of this check looked for the
    # bare name, and the comment explaining the fix in `test_run_verdict.py` was
    # enough to satisfy it — the tripwire passed with the fix deleted. Caught by
    # mutating the fix and watching this stay green, which is the only way that
    # kind of vacuity shows up.
    isolated = re.compile(r"""CTI_TIER_STATE["'\]]*\s*[=:]""")
    offenders = [
        path.name
        for path in sorted(Path(__file__).parent.glob("test_*.py"))
        for text in [path.read_text()]
        if any(driver in text for driver in drivers) and not isolated.search(text)
    ]
    assert not offenders, (
        f"{offenders} drive the tier's scripts without setting CTI_TIER_STATE, so they take "
        "the real locks under $HOME/.arma-cti and collide with the Arma tier and with each other"
    )


# ------------------------------------------------- a staleness signal (#153)
#
# `flock` handles a holder that *dies*. A holder that is wedged — alive, holding,
# and getting nowhere — blocks the one Windows client for as long as it likes,
# and the block beside the lock said only when it started. So a queuer at 3 a.m.
# could say that somebody held the client and nothing about whether that somebody
# was working, and recovery meant a human going and finding the process.
#
# Two things answer it, both derived at the instant of asking rather than
# refreshed on a timer: how long the holder has had it, and whether the pid in
# the block still has the lock open. The reasoning against a heartbeat is in
# `spike/lock-info.sh` and it is about this lock in particular — a background
# refresher on a lock whose whole failure history is background processes
# outliving their parent would keep the timestamp fresh for a holder that no
# longer exists.


# The instant a hand-written block is dated against, and the instant `reading()`
# tells the reader to measure from — 2026-01-01T00:00:00Z, and nothing here
# depends on which instant it is. What matters is that the test states *both*
# ends of the subtraction (#222).
#
# It used to state only the older one: `backdated` wrote `started_at` as the wall
# clock less `seconds`, truncated to a whole second, and the reader took its own
# clock afterwards. So an age was right only while no second boundary fell
# between the write and the read, and a subprocess spawn is wide enough to cross
# one — about one red per full `just unit` under `-n auto`, on whichever
# parameter was unlucky, which is why eight recorded arrangements never named the
# same duration twice. Measured on this box before the fix: 20/20 red with the
# block written 0.99 of a second in, 14/20 at 0.97, 0/20 at 0.90 and below.
#
# Not a widened tolerance: the assertions below are exactly as strict as they
# were, and `age_seconds` is still asserted to the second. What moved is that
# there is no longer a clock running between the two ends of the subtraction.
# The wall-clock path is not left untested by this — the live-holder tests below
# and `run.sh`'s `failure_detail` still read the real clock, and assert on the
# shape of an age they cannot predict.
FROZEN_NOW = 1_767_225_600


def reading(state: Path, **extra: str) -> dict[str, str]:
    """Name both ends for a hand-written block's reader: whose state, and when now is."""
    return {"CTI_TIER_STATE": str(state), "CTI_LOCK_NOW": str(FROZEN_NOW), **extra}


def backdated(state: Path, seconds: int, **fields: str) -> Path:
    """Write a holder block by hand, as old as we like, against `FROZEN_NOW`."""
    info = state / "windows-client.lock.info"
    info.parent.mkdir(parents=True, exist_ok=True)
    written = time.gmtime(FROZEN_NOW - seconds)
    block = {
        "pid": str(os.getpid()),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", written),
        "worktree": str(REPO),
        "branch": "main",
        "issue": "153",
        "label": "a wedged corpus",
        **fields,
    }
    info.write_text("".join(f"{k}={v}\n" for k, v in block.items()))
    return info


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(7, "7s"), (63, "1m 03s"), (3600, "1h 00m"), (15120, "4h 12m"), (183600, "2d 3h")],
)
def test_a_holders_age_reads_as_a_duration_not_a_count_of_seconds(
    tmp_path: Path, seconds: int, expected: str
) -> None:
    """The question is "longer than the work it claims to be doing?" — 15120 is no answer."""
    state = tmp_path / "state"
    backdated(state, seconds)
    got = lock_eval("cti_client_lock_holder", env=reading(state)).stdout
    assert f"age={expected}\n" in got, got
    assert f"age_seconds={seconds}" in got


def test_an_age_is_measured_against_the_now_its_reader_was_given(tmp_path: Path) -> None:
    """The stated `now` is what the subtraction uses, not a clock beside it (#222).

    Read an hour later than the block was dated against and the age is an hour
    longer, to the second — which no wall clock could have been asked for.
    """
    state = tmp_path / "state"
    backdated(state, 7)
    got = lock_eval(
        "cti_client_lock_holder", env=reading(state, CTI_LOCK_NOW=str(FROZEN_NOW + 3600))
    ).stdout
    assert "age=1h 00m\n" in got, got
    assert "age_seconds=3607" in got, got


def test_a_now_that_is_not_an_instant_is_refused_rather_than_taken_from_the_clock(
    tmp_path: Path,
) -> None:
    """The fail-closed half, and the reason the seam is not a fallback.

    A caller that states a `now` and gets the machine's would read a wrong age as
    a right one — the very thing #222 was. So an unreadable one produces no age at
    all, and says which end of the subtraction it could not read.
    """
    state = tmp_path / "state"
    backdated(state, 7)
    got = lock_eval("cti_client_lock_holder", env=reading(state, CTI_LOCK_NOW="in a bit")).stdout
    assert "age=unknown (CTI_LOCK_NOW=in a bit" in got, got
    assert "age_seconds=" not in got, got
    # And the rest of the block is undamaged: an age it cannot compute is not a
    # reason to stop naming the holder, which is what a queuer came for.
    assert "label=a wedged corpus" in got, got
    assert "holder=" in got, got


def test_a_live_holder_is_reported_holding_with_its_age(tmp_path: Path) -> None:
    state = tmp_path / "state"
    holder = holding(state, "the first run", CTI_TIER_ISSUE="127")
    try:
        got = lock_eval("cti_client_lock_holder", env={"CTI_TIER_STATE": str(state)}).stdout
    finally:
        holder.kill()
    assert f"holder=holding (pid {holder.pid})" in got, got
    assert re.search(r"^age=\d+s$", got, re.MULTILINE), got
    # The block it always wrote is still all there.
    assert "label=the first run" in got
    assert "issue=127" in got
    # And nothing swept /proc for it: the metadata named a pid that has the lock.
    assert "lock_held_by=" not in got


def test_metadata_left_behind_by_a_dead_holder_says_so(tmp_path: Path) -> None:
    """The block outliving its run is exactly what makes "held since" a lie.

    A `.info` is deleted on release and survives a `kill -9`, so a stale one is
    the normal residue of a killed run. Read literally it claims a holder that no
    longer exists; read through `cti_client_lock_holder` it names the pid and
    says it has gone.
    """
    state = tmp_path / "state"
    backdated(state, 9000, pid="4194305")  # above /proc/sys/kernel/pid_max: never live
    got = lock_eval("cti_client_lock_holder", env=reading(state)).stdout
    assert "holder=gone (pid 4194305" in got, got
    assert "age=2h 30m" in got
    assert "lock_held_by=nobody" in got, got


def test_a_lock_held_by_an_orphan_with_no_metadata_names_the_pid_to_kill(tmp_path: Path) -> None:
    """The worst case this lock has: a machine-wide stop with nobody to name.

    A child that inherited the descriptor and outlived its parent holds the lock
    against a `.info` the parent deleted on the way out. `cti_client_lock_disown`
    is what stops the tier's own launches doing it, but anything can still be
    killed at the wrong instant — and when it happens, the only recovery is a
    human killing a process, so the refusal has to say which one.
    """
    state = tmp_path / "state"
    leaked = tmp_path / "leaked.pid"
    lock_eval(
        'cti_client_lock_acquire 0 "the parent" || exit 9\n'
        "(\n"
        f'  printf "%s" "$BASHPID" > "{leaked}"\n'
        "  exec sleep 120\n"
        ") >/dev/null 2>&1 &\n"
        f'while [[ ! -s "{leaked}" ]]; do sleep 0.05; done\n'
        "cti_client_lock_release\n",
        env={"CTI_TIER_STATE": str(state)},
    )
    orphan = int(leaked.read_text())
    try:
        got = lock_eval("cti_client_lock_holder", env={"CTI_TIER_STATE": str(state)}).stdout
        assert "holder=unnamed" in got, got
        assert f"lock_held_by={orphan}" in got, got
        # And it really is held, so the pid named is the pid to kill.
        assert (
            "TOOK"
            not in lock_eval(
                'cti_client_lock_acquire 0 "next" && echo TOOK',
                env={"CTI_TIER_STATE": str(state)},
            ).stdout
        )
    finally:
        with suppress(ProcessLookupError):
            os.kill(orphan, signal.SIGKILL)


def test_the_one_line_summary_carries_what_a_failure_detail_can_hold(tmp_path: Path) -> None:
    """`failure_detail=` is one key=value record and cannot carry a paragraph."""
    state = tmp_path / "state"
    backdated(state, 15120, label="just regress --slots 3")
    got = lock_eval("cti_client_lock_summary", env=reading(state)).stdout
    assert len(got.splitlines()) == 1, f"a failure_detail cannot hold this: {got!r}"
    assert "age 4h 12m" in got
    assert "label just regress --slots 3" in got
    assert "issue 153" in got


# --------------------------------------------------------------------- run.sh


def run_sh(tmp_path: Path, listing: str | Path, **extra: str) -> subprocess.CompletedProcess[str]:
    """`spike/run.sh` as far as the missing server install, and no further.

    An empty `CTI_SERVER_DIR` means the first thing after the pre-flight is a
    refusal of its own, which is what makes "it got past the lock" observable
    without a server.

    A `Path` for the listing is a process-list stub the caller wrote itself —
    `pool_env`'s own union, for the tests below that need the list to change
    its answer while the run is watching it.
    """
    tool = listing if isinstance(listing, Path) else tasklist(tmp_path / "tasklist.sh", listing)
    env = dict(
        os.environ,
        CTI_WINDOWS_TASKLIST=str(tool),
        CTI_SPIKE_OUT=str(tmp_path / "out"),
        CTI_SERVER_DIR=str(tmp_path / "no-server"),
        CTI_TIER_STATE=str(tmp_path / "state"),
        **extra,
    )
    # S603: this repo's own script, with paths this test just wrote.
    return subprocess.run(  # noqa: S603
        [BASH, str(RUN)], env=env, capture_output=True, text=True, check=False, timeout=120
    )


def results(tmp_path: Path) -> dict[str, str]:
    text = (tmp_path / "out" / "results.env").read_text()
    return dict(line.split("=", 1) for line in text.splitlines() if "=" in line)


def held_lock(tmp_path: Path) -> subprocess.Popen[str]:
    """Hold the client lock in `tmp_path`'s state directory."""
    return holding(tmp_path / "state", "a sibling agent")


def test_a_client_run_refuses_while_another_run_holds_the_client(tmp_path: Path) -> None:
    holder = held_lock(tmp_path)
    try:
        result = run_sh(tmp_path, TASKLIST_FREE, CTI_WINDOWS_CLIENT="1")
    finally:
        holder.kill()
    assert result.returncode != 0
    got = results(tmp_path)
    assert got["failure_class"] == "infra_unavailable"
    assert "another run holds the Windows client" in got["failure_detail"]
    # And whose run it is behind, so the caller can act on it.
    assert "label=a sibling agent" in result.stderr
    # In the *durable* record too, and as the holder's own words rather than a
    # path to them (#153): the `.info` file is deleted the instant the holder
    # releases, so a `failure_detail` naming it names a path that will not exist
    # by the time anyone reads this run's evidence (#147's finding, which was
    # fixed in regress.sh and left standing here). With the age, which is what
    # separates a run doing its work from one that is wedged.
    detail = got["failure_detail"]
    assert "label a sibling agent" in detail, detail
    assert f"holder holding (pid {holder.pid})" in detail, detail
    assert re.search(r"age \d+s", detail), detail
    assert ".info" not in detail, detail
    # Nothing launched, and the guard never even asked: the refusal is cheaper
    # than the process list.
    assert "windows_host_free" not in got


def test_a_run_that_sends_no_client_is_not_held_up_by_one(tmp_path: Path) -> None:
    """The lock is the client's, not the tier's — slots are what serialise those."""
    holder = held_lock(tmp_path)
    try:
        result = run_sh(tmp_path, TASKLIST_FREE)
    finally:
        holder.kill()
    assert result.returncode != 0
    got = results(tmp_path)
    assert got["windows_host_free"] == "true"
    assert "server binary missing" in got["failure_detail"]


def test_a_client_run_takes_the_lock_and_gives_it_back(tmp_path: Path) -> None:
    """The green branch, asserted at the *next* refusal rather than at a pass.

    Without it the lock could be a permanent stop and the test above would still
    be green — and a lock the teardown never released would stop every later run.
    """
    result = run_sh(tmp_path, TASKLIST_FREE, CTI_WINDOWS_CLIENT="1")
    assert result.returncode != 0
    got = results(tmp_path)
    assert got["windows_client_lock"] == "held"
    assert "server binary missing" in got["failure_detail"]
    took = lock_eval(
        'cti_client_lock_acquire 0 "after" && echo TOOK',
        env={"CTI_TIER_STATE": str(tmp_path / "state")},
    )
    assert "TOOK" in took.stdout, "run.sh exited still holding the client lock"


# ------------------------------------------------------------- two runs at once


def pool_env(tmp_path: Path, tag: str, *, listing: str | Path = TASKLIST_FREE) -> dict[str, str]:
    """Everything `regress.sh` needs to run without Arma, written once.

    Written by the caller before any concurrency starts: two threads writing one
    stub script would race the kernel's own "text file busy".
    """
    master = tmp_path / "arma3server"
    executable(master / "arma3server_x64", "#!/usr/bin/env bash\n")
    (master / "mpmissions").mkdir(exist_ok=True)
    tool = listing if isinstance(listing, Path) else tasklist(tmp_path / "tasklist.sh", listing)
    return {
        **os.environ,
        "CTI_TIER_STATE": str(tmp_path / "state"),
        # `test_pool_slots.py`'s reason, which this file's own pool runs had
        # missed (#132): the memory pre-flight reads the real host, so a test
        # about the client lock goes red about memory whenever the machine is
        # busy. It did — with a sibling agent's three-slot Arma run holding
        # 3.5 GiB, the queueing test queued correctly, took the lock, and then
        # stopped at the floor on 1729 MiB of real free memory.
        "CTI_SLOT_MEM_AVAILABLE_MB": "1000000",
        "CTI_SLOT_INSTALL_MASTER": str(master),
        "CTI_RUN_SH": str(executable(tmp_path / "stub-run.sh", STUB_RUN)),
        "CTI_WINDOWS_TASKLIST": str(tool),
        "CTI_STUB_TRACE": str(tmp_path / "trace.tsv"),
        "CTI_STUB_HOST_PROBES": ",".join(HOST_PROBES),
        "CTI_STUB_CLIENT_LEG_SECS": str(CLIENT_LEG_SECONDS),
        "CTI_STUB_TAG": tag,
    }


def pool_run(
    env: dict[str, str], *args: str, timeout: int = 300, delay: float = 0.0
) -> subprocess.CompletedProcess[str]:
    time.sleep(delay)
    # S603: this repo's own runner, against a stub this test wrote.
    return subprocess.run(  # noqa: S603
        [BASH, str(REGRESS), *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        timeout=timeout,
    )


def client_legs(tmp_path: Path) -> dict[str, list[tuple[int, int]]]:
    """Each run's client-leg intervals, in nanoseconds, keyed by its tag."""
    legs: dict[str, list[tuple[int, int]]] = {}
    opened: dict[tuple[str, str], int] = {}
    for line in (tmp_path / "trace.tsv").read_text().splitlines():
        tag, probe, edge, stamp = line.split("\t")
        if edge == "open":
            opened[(tag, probe)] = int(stamp)
        else:
            legs.setdefault(tag, []).append((opened.pop((tag, probe)), int(stamp)))
    assert not opened, f"a client leg opened and never closed: {opened}"
    return legs


def test_two_concurrent_pools_never_hold_the_client_at_once(tmp_path: Path) -> None:
    """The collision #125 met, run on purpose.

    Two pools, two slots, one machine — the shape of two agents gating from
    sibling worktrees. Each drains its own parallel phase and then wants the one
    headed client. With `--wait` they queue; the proof is that their client legs
    are disjoint in time rather than merely that both went green.
    """
    envs = {tag: pool_env(tmp_path, tag) for tag in ("a", "b")}
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {
            tag: pool.submit(
                pool_run,
                env,
                "--slots",
                "1",
                "--wait",
                "120",
                *HOST_PROBES,
                delay=delay,
            )
            for (tag, env), delay in zip(envs.items(), (0.0, 0.2), strict=True)
        }
        outcomes = {tag: f.result() for tag, f in futures.items()}

    for tag, result in outcomes.items():
        assert result.returncode == 0, f"pool {tag}: {result.stderr[-4000:]}"

    legs = client_legs(tmp_path)
    assert sorted(legs) == ["a", "b"], legs
    assert all(len(v) == len(HOST_PROBES) for v in legs.values()), legs
    for start_a, end_a in legs["a"]:
        for start_b, end_b in legs["b"]:
            assert end_a <= start_b or end_b <= start_a, (
                "two pools drove the Windows client at the same time: "
                f"a={start_a}..{end_a} b={start_b}..{end_b}"
            )


def test_a_client_leg_only_runs_under_the_lock(tmp_path: Path) -> None:
    """The tail tells its children it holds the lock.

    If it stopped doing so, `run.sh` would queue behind its own parent and the
    pool would hang rather than run.
    """
    result = pool_run(pool_env(tmp_path, "solo"), "--slots", "1", *HOST_PROBES)
    assert result.returncode == 0, result.stderr[-4000:]
    for evidence in (tmp_path / "state" / "runs").glob("*/results.env"):
        text = evidence.read_text()
        if "client_lock_held" in text:
            assert "client_lock_held=1" in text, evidence


def test_a_pool_whose_tail_is_locked_out_reports_it_rather_than_skipping(
    tmp_path: Path,
) -> None:
    """`not_run` carries no class, so a silently dropped tail exits green."""
    env = pool_env(tmp_path, "blocked")
    holder = held_lock(tmp_path)
    try:
        result = pool_run(env, "--slots", "1", *HOST_PROBES)
    finally:
        holder.kill()
    assert result.returncode == EXIT_INFRA_UNAVAILABLE, result.stderr[-4000:]
    assert "another run holds the Windows client" in result.stderr
    assert "label=a sibling agent" in result.stderr
    # #147 item 6: the lock's own `.info` is deleted when the holder releases,
    # so a blocked verdict that referenced it would durably name a path that
    # stops existing. The verdicts must point at evidence the pool owns.
    pools = sorted((tmp_path / "state" / "runs").glob("*-pool"))
    pool = json.loads((pools[-1] / "pool.json").read_text())
    blocked = [v for v in pool["verdicts"] if v["slot"] == "-"]
    assert sorted(v["probe"] for v in blocked) == sorted(HOST_PROBES)
    for verdict in blocked:
        evidence = Path(verdict["evidence"])
        assert evidence.parent == pools[-1], (
            f"the blocked verdict's evidence lives outside the pool: {evidence}"
        )
        # And it carries the holder's age (#153), because "somebody held the
        # client" is not on its own a diagnosis: a corpus takes tens of minutes,
        # and what a reader needs to know is whether the run in front of theirs
        # was working or wedged.
        text = evidence.read_text()
        assert "label=a sibling agent" in text
        assert f"holder=holding (pid {holder.pid})" in text, text
        assert re.search(r"^age=\d+s$", text, re.MULTILINE), text


# ------------------------------------------------------- the guard, still blind


def test_a_held_client_lock_lets_the_pool_queue_rather_than_refuse(tmp_path: Path) -> None:
    """A client in the list *while another run holds the lock* is that run's.

    The guard is not told this — it refuses exactly as before. The caller reads
    the lock and queues, which is the whole of #127's fix and the reason the
    ownership-blind property survives it.
    """
    # The list shows a client until the sibling's leg ends, and not afterwards.
    # The holder releases at the same moment, which is the ordering the real
    # teardown gets from waiting on `cti_windows_wait_gone` before releasing.
    flip = tmp_path / "flip"
    listing = flipping_tasklist(tmp_path / "tasklist-flip.sh", flip)
    env = pool_env(tmp_path, "queued", listing=listing)
    holder = holding(
        tmp_path / "state",
        "a sibling agent",
        then=f'sleep 3\ntouch "{flip}"\ncti_client_lock_release\nsleep 60\n',
    )
    try:
        result = pool_run(env, "--slots", "1", "--wait", "60", "contact-decay")
    finally:
        holder.kill()
    assert result.returncode == 0, result.stderr[-4000:]
    assert "queueing up to 60s" in result.stderr


def test_without_a_wait_a_client_in_the_list_still_stops_the_pool(tmp_path: Path) -> None:
    """The refusal is the default, and the lock does not weaken it."""
    env = pool_env(tmp_path, "refused", listing=TASKLIST_PRESENT)
    holder = held_lock(tmp_path)
    try:
        result = pool_run(env, "--slots", "1", "contact-decay")
    finally:
        holder.kill()
    assert result.returncode == EXIT_INFRA_UNAVAILABLE
    assert "play session may be live" in result.stderr
    # The pre-flight refusal writes to stderr and to a durable line (#147 item 7),
    # and the durable line now says which of the three reasons the box could
    # still tell apart (#153): the lock was held, by whom, and for how long. A
    # refusal that turns out to be somebody's wedged run is then diagnosable from
    # the refusal log alone, without the invoker having kept its output.
    refusals = (tmp_path / "state" / "runs" / "refusals.log").read_text()
    assert "the client lock was held" in refusals, refusals
    assert f"holder holding (pid {holder.pid})" in refusals, refusals
    assert re.search(r"age \d+s", refusals), refusals


def test_an_unheld_client_in_the_list_is_the_humans_however_long_we_wait(
    tmp_path: Path,
) -> None:
    """Nobody holds the lock, so the client in the list is not an agent's.

    Refuse, and do not queue: waiting out a play session is not what `--wait`
    is for.
    """
    env = pool_env(tmp_path, "human", listing=TASKLIST_PRESENT)
    started = time.monotonic()
    result = pool_run(env, "--slots", "1", "--wait", "600", "contact-decay")
    assert result.returncode == EXIT_INFRA_UNAVAILABLE
    assert time.monotonic() - started < 60, "the pool queued behind a play session"


def test_a_process_list_we_cannot_read_is_never_queued_on(tmp_path: Path) -> None:
    """A check that could not run is not a check that will pass in a minute."""
    unreadable = tmp_path / "there-is-no-tasklist-here.exe"
    env = pool_env(tmp_path, "blind", listing=unreadable)
    holder = held_lock(tmp_path)
    started = time.monotonic()
    try:
        result = pool_run(env, "--slots", "1", "--wait", "600", "contact-decay")
    finally:
        holder.kill()
    assert result.returncode == EXIT_INFRA_UNAVAILABLE
    assert "could not run is not a check that passed" in result.stderr
    assert time.monotonic() - started < 60, "the pool queued on a check it could not make"


@pytest.mark.parametrize("script", ["run.sh", "regress.sh"])
def test_every_path_that_drives_the_client_knows_about_the_lock(script: str) -> None:
    assert "client-lock.sh" in (REPO / "spike" / script).read_text()


# ---------------------------------------------- queueing behind more than one


def test_a_third_run_that_takes_the_client_in_the_gap_is_queued_behind_too(
    tmp_path: Path,
) -> None:
    """Issue #151: the wait establishes only that the lock was free when it looked.

    Between `cti_client_lock_wait_free` returning and the guard being re-asked,
    another agent's tail can take the client. The guard then refuses — correctly,
    it is ownership-blind — and a caller who had asked to queue for `--wait`
    seconds used to be turned away by the second contender it met, having waited
    for the first. Three agents gating at once is the ordinary case this pool was
    built for, so the queue has to survive meeting more than one of them.

    The stub process list is what makes the gap deterministic rather than a race
    to lose: the third run is launched *by* the ask that lands in the gap, and
    the list does not answer until it holds the lock.
    """
    client_there = tmp_path / "client-in-the-list"
    client_there.touch()
    first_gone = tmp_path / "first-released"
    third_started = tmp_path / "third-started"
    third_holds = tmp_path / "third-holds"

    third_run = executable(
        tmp_path / "third-run.sh",
        "#!/usr/bin/env bash\n"
        f'source "{CLIENT_LOCK_SH}"\n'
        'cti_client_lock_acquire 60 "a third agent" || exit 9\n'
        f'touch "{third_holds}"\n'
        "sleep 3\n"
        # The client leaves the list before the lock is dropped, which is the
        # ordering every real holder gets from `cti_windows_wait_gone`.
        f'rm -f "{client_there}"\n'
        "cti_client_lock_release\n",
    )
    listing = executable(
        tmp_path / "tasklist-gap.sh",
        "#!/usr/bin/env bash\n"
        f'if [[ -e "{first_gone}" && ! -e "{third_started}" ]]; then\n'
        f'    touch "{third_started}"\n'
        # Detached from this stub's stdout: the guard reads the list through a
        # command substitution, which does not return until every writer on the
        # pipe has closed it — a third run that kept it open would be waited
        # out rather than raced with, which is the opposite of the case here.
        f'    "{third_run}" >/dev/null 2>&1 &\n'
        f'    while [[ ! -e "{third_holds}" ]]; do sleep 0.1; done\n'
        "fi\n"
        f'if [[ -e "{client_there}" ]]; then printf "%s" {TASKLIST_PRESENT!r}; '
        f'else printf "%s" {TASKLIST_FREE!r}; fi\n',
    )

    env = pool_env(tmp_path, "queued-twice", listing=listing)
    holder = holding(
        tmp_path / "state",
        "a sibling agent",
        then=f'sleep 3\ncti_client_lock_release\ntouch "{first_gone}"\nsleep 60\n',
    )
    try:
        result = pool_run(env, "--slots", "1", "--wait", "120", "contact-decay")
    finally:
        holder.kill()

    assert result.returncode == 0, result.stderr[-4000:]
    assert third_holds.exists(), "the third run never took the client; the gap was not staged"
    # Said once however many runs are queued behind, so the pool's own log is
    # not buried under somebody else's schedule.
    assert result.stderr.count("queueing up to 120s") == 1, result.stderr[-4000:]


def test_the_queue_is_still_bounded_by_the_wait_that_was_asked_for(tmp_path: Path) -> None:
    """A loop that re-enters has to re-enter with what is left of the deadline.

    The holder never lets go, so every pass finds the client held and the wait
    must expire rather than renew: `--wait 10` gives up in about ten seconds.
    """
    env = pool_env(tmp_path, "bounded", listing=TASKLIST_PRESENT)
    holder = held_lock(tmp_path)
    started = time.monotonic()
    try:
        result = pool_run(env, "--slots", "1", "--wait", "10", "contact-decay")
    finally:
        holder.kill()
    assert result.returncode == EXIT_INFRA_UNAVAILABLE, result.stderr[-4000:]
    assert "waited 10s and the Windows client was still held" in result.stderr
    assert time.monotonic() - started < 90, "the queue outlived the wait it was given"


# ------------------------------------------ the per-probe guard, queued too (#196)
#
# The entry-time guard above is asked once, before a lock is taken. `run.sh`
# asks the same question again on every probe's bring-up, and that ask had no
# queue — so a pool already running when a sibling agent's client probe started
# met the ownership-blind guard, took the `infra_unavailable` stop, and the
# pool's bulkhead rule turned one probe's non-result into an abandoned corpus.
# Observed 2026-08-05 gating #172: four probes passed, `campaign-end` refused
# nineteen seconds into another worktree's `client-port`, nineteen probes never
# ran. #119 is the same shape one scope smaller and is fixed; this is the
# cross-run case, and the fix is the entry guard's queue at the second site.
#
# Same verdict vocabulary, only patience: every refusal below is one `run.sh`
# made before this change too, at the same class and with the same detail.


def guard_wait(
    tmp_path: Path, listing: str | Path, wait: str, **extra: str
) -> subprocess.CompletedProcess[str]:
    """Drive a probe's bring-up with `wait` seconds of patience for the machine."""
    return run_sh(tmp_path, listing, CTI_CLIENT_LOCK_WAIT=wait, **extra)


def test_a_probe_queues_behind_another_runs_client_rather_than_abandoning_the_pool(
    tmp_path: Path,
) -> None:
    """The nineteen abandoned probes, as one probe that waits instead.

    The green branch is asserted at the *next* refusal rather than at a pass:
    getting past the guard means reaching the missing server install, which is
    as far as any of these runs is meant to get.
    """
    flip = tmp_path / "flip"
    listing = flipping_tasklist(tmp_path / "tasklist-flip.sh", flip)
    holder = holding(
        tmp_path / "state",
        "a sibling agent",
        then=f'sleep 3\ntouch "{flip}"\ncti_client_lock_release\nsleep 60\n',
    )
    try:
        result = guard_wait(tmp_path, listing, "60")
    finally:
        holder.kill()
    got = results(tmp_path)
    assert result.returncode != 0
    assert got["windows_host_free"] == "true", got
    assert "server binary missing" in got["failure_detail"], got
    assert "queueing up to 60s" in result.stderr, result.stderr[-4000:]
    # And it named the run it was behind, so a wedged holder is diagnosable
    # from the queuer's own log rather than from the machine.
    assert "label=a sibling agent" in result.stderr


def test_without_a_wait_a_probe_still_stops_at_a_client_in_the_list(tmp_path: Path) -> None:
    """The refusal is the default, at this guard as at the entry one."""
    holder = held_lock(tmp_path)
    started = time.monotonic()
    try:
        result = run_sh(tmp_path, TASKLIST_PRESENT)
    finally:
        holder.kill()
    assert result.returncode != 0
    got = results(tmp_path)
    assert got["failure_class"] == "infra_unavailable"
    assert "that is a play session, not ours" in got["failure_detail"], got
    assert "windows_host_free" not in got
    assert time.monotonic() - started < 60, "a run given no wait waited anyway"
    # Told what it could have had, and whose run it would have been behind.
    assert "a wait would queue behind it" in result.stderr
    assert "label=a sibling agent" in result.stderr


def test_a_probe_never_queues_behind_a_play_session(tmp_path: Path) -> None:
    """Nobody holds the lock, so the client in the list is not an agent's.

    This is the guard's whole reason for existing, and no amount of patience
    may soften it: waiting out a person is not what a queue is for.
    """
    started = time.monotonic()
    result = guard_wait(tmp_path, TASKLIST_PRESENT, "600")
    assert result.returncode != 0
    got = results(tmp_path)
    assert got["failure_class"] == "infra_unavailable"
    assert "that is a play session, not ours" in got["failure_detail"], got
    assert time.monotonic() - started < 60, "a probe queued behind a play session"


def test_a_probe_never_queues_on_a_list_it_could_not_read(tmp_path: Path) -> None:
    """A check that could not run is not a check that will pass in a minute."""
    unreadable = tmp_path / "there-is-no-tasklist-here.exe"
    holder = held_lock(tmp_path)
    started = time.monotonic()
    try:
        result = guard_wait(tmp_path, unreadable, "600")
    finally:
        holder.kill()
    assert result.returncode != 0
    got = results(tmp_path)
    assert got["failure_class"] == "infra_unavailable"
    assert "refusing to take a machine I cannot check" in got["failure_detail"], got
    assert time.monotonic() - started < 60, "a probe queued on a check it could not make"


def test_a_probe_in_the_tail_does_not_queue_behind_its_own_pool(tmp_path: Path) -> None:
    """`CTI_CLIENT_LOCK_HELD=1` is our own parent holding the client.

    `flock` conflicts between a child's descriptor and its parent's exactly as
    it does between strangers, so a naive busy check reads the pool's own tail
    lock as a sibling agent's. A probe that queued on it would wait out the
    whole of `--wait` for a lock that cannot free until the probe returns —
    and would hold the machine-wide client for every second of it. What is in
    the list while our own pool holds the lock is the human's client.
    """
    holder = held_lock(tmp_path)  # stands in for the pool parent's hold
    started = time.monotonic()
    try:
        result = guard_wait(tmp_path, TASKLIST_PRESENT, "600", CTI_CLIENT_LOCK_HELD="1")
    finally:
        holder.kill()
    assert result.returncode != 0
    got = results(tmp_path)
    assert got["failure_class"] == "infra_unavailable"
    assert "that is a play session, not ours" in got["failure_detail"], got
    assert time.monotonic() - started < 60, "a probe queued behind its own pool"


def test_a_malformed_wait_is_refused_rather_than_read_as_a_busy_lock(tmp_path: Path) -> None:
    """A budget that is not a number is not a budget.

    Unchecked, it reaches `cti_client_lock_acquire`, which rejects it with the
    status it gives a *busy* lock — and the run would report somebody holding a
    client nobody holds.
    """
    result = guard_wait(tmp_path, TASKLIST_FREE, "a while", CTI_WINDOWS_CLIENT="1")
    assert result.returncode != 0
    got = results(tmp_path)
    assert got["failure_class"] == "infra_unavailable"
    assert "CTI_CLIENT_LOCK_WAIT must be a whole number of seconds" in got["failure_detail"], got


def test_the_pool_hands_its_wait_to_every_probe(tmp_path: Path) -> None:
    """The per-probe queue draws on the pool's `--wait`, not a budget of its own.

    ADR-0028's rule, applied to a value that crosses the launch: a boundary is
    only real where something reads it, so the assertion is on what the child
    received rather than on what the parent meant to send.
    """
    result = pool_run(pool_env(tmp_path, "budget"), "--slots", "1", "--wait", "90", "contact-decay")
    assert result.returncode == 0, result.stderr[-4000:]
    seen = {
        line.split("=", 1)[1]
        for evidence in (tmp_path / "state" / "runs").glob("*/results.env")
        for line in evidence.read_text().splitlines()
        if line.startswith("client_lock_wait=")
    }
    assert seen == {"90"}, seen


def test_the_guard_queue_has_one_home() -> None:
    """#161's shape, applied before the second copy exists rather than after.

    The entry-time loop and the per-probe one are the same decision about the
    same lock; two of them drift, and the drift's failure mode is a corpus
    thrown away. The bounded wait on the lock is the fingerprint — every
    version of this loop ends in one.
    """
    queuers = [
        script.name
        for script in sorted((REPO / "spike").glob("*.sh"))
        if "cti_client_lock_wait_free" in script.read_text()
    ]
    assert queuers == ["client-lock.sh"], queuers


@pytest.mark.parametrize("script", ["run.sh", "regress.sh"])
def test_every_host_guard_ask_in_a_runner_goes_through_the_queue(script: str) -> None:
    """The tripwire for the next ask somebody adds.

    `cti_host_guard` and `cti_guard_verdict` are still there and still correct —
    they are what the queue asks *with*, and `spike/host-guard.sh` runs one as a
    command. A runner reaching for either directly is a third site that stops a
    pool for a sibling's client, which is how this issue was filed.
    """
    text = (REPO / "spike" / script).read_text()
    asks = [
        line
        for line in text.splitlines()
        if not line.lstrip().startswith("#")
        if re.search(r"\bcti_guard_verdict\b|\bcti_host_guard\b(?!_or_queue)", line)
    ]
    assert asks == [], asks
    assert "cti_host_guard_or_queue" in text
