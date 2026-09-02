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
import shlex
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


# The registry `hosts.sh` reads is machine state — `$HOME/.arma-cti/hosts.toml`,
# shared by every worktree on the box and written when a machine is commissioned.
# A test that reads it is asserting on this machine rather than on the seam, and
# a second row silently unmakes the premise of every test whose subject is an
# *unknown* host: commissioning Machine B on 2026-08-12 turned `bravo` from the
# canonical unknown into a resolvable one and reddened four tests here in every
# tree (#356). So every test below names its own registry, and this module
# writes three: the local-only one, the two-host one, and the invalid one
# `test_an_invalid_registry_refuses_every_host` derives from the second — which
# is the registry the seam has to be most right about, since it must refuse
# every host rather than fall back to any. The same coupling survives elsewhere —
# every test reaching `regress.sh` or `run.sh` without `CTI_HOSTS_FILE` still
# reads the machine's registry, which is #362.
#
# `server_slots = 5` is load-bearing and not a detail: `host_registry.load()`
# falls back to `default_hosts()` when its path does not exist, and that default
# is a single `local` row otherwise identical to this one. A fixture registry
# indistinguishable from the fallback proves no isolation at all — a mistyped
# fixture path passes every test in this module.
#
# Five is a choice; the constraints are two, and they are what a later edit must
# preserve. It must differ from `default_hosts()`'s count — that difference is
# the whole canary, and `test_the_fixture_registry_differs_from_the_fallback`
# asserts the difference itself, on neither side's literal, so it reds whichever
# side moves. And it must be at least 2: `regress.sh` refuses a pool wider than
# the host's slots, and the widest pool that reaches that comparison is the
# `--slots 2` of `test_the_host_reaches_the_run_that_executes_on_it`. The
# `--slots 3` test below never reaches it — it sets `CTI_TIER_HOST=nosuchhost`
# and `regress.sh` refuses at `cti_host_resolve` first, long before the host's
# slot count is read.
LOCAL_ROW = """version = 1
[hosts.local]
ssh_target = ""
server_slots = 5
headed_client = true
human = true
client_driver = "windows"
remote_root = ""
"""

BRAVO_ROW = """[hosts.bravo]
ssh_target = "bravo-lan"
server_slots = 3
headed_client = true
human = false
client_driver = "proton"
remote_root = "/home/cti/.arma-cti/staging"
"""


def local_only_registry(tmp_path: Path) -> str:
    """Write a registry holding the one host that existed before Machine B, and nothing else.

    Its point is what it *lacks*: `nosuchhost` is unknown here whatever this
    machine has been commissioned with, which is the premise the refusal tests
    assert on. The name is deliberately one no machine can ever be commissioned
    as — `bravo` was a real machine's name a day after these tests were written,
    which is how #356 happened.
    """
    path = tmp_path / "hosts-local-only.toml"
    path.write_text(LOCAL_ROW, encoding="utf-8")
    return str(path)


# ------------------------------------------------------------------- the table


def test_the_fixture_registry_differs_from_the_fallback(tmp_path: Path) -> None:
    """The canary's premise, asserted as the difference rather than as two numbers.

    Every isolation claim in this module rests on the fixture registry being
    distinguishable from the no-registry fallback: `host_registry.load()` falls
    back to a one-row `local` default when its path does not exist, so a
    mistyped `CTI_HOSTS_FILE` silently reads that default, and a fallback
    indistinguishable from the fixture passes every test here while proving
    nothing.

    Pinning the two counts separately does not close that. The first pin
    compared `default_hosts()`'s output against `MAX_SLOTS` — the symbol
    `default_hosts()` is written from — so it was a tautology with respect to
    the value it guarded: lowering `MAX_SLOTS` to the fixture's 5 left it green
    with the canary dead. This asserts the difference itself, which rests on no
    third value and so reds however either side moves (#356).

    The difference is read *through the seam* rather than through a Python
    import of the registry, for two reasons. It is the stronger claim: the same
    `cti_host_slots local` under the fixture and under a path that does not
    exist also reds if `hosts.sh` ever stops honouring `CTI_HOSTS_FILE`, which
    is the mistyped-path failure this canary exists to catch and which the
    Python-side version cannot see. And it keeps this module free of any
    repo-Python import: `tools/mutation_smoke.py` routes a test module to its
    Python subject wherever one exists and only reaches the shell arm when there
    is none, so importing `host_registry` here silently costs `spike/hosts.sh` —
    the script this module's other tests exist to drive, and the subject
    `SHELL_SUBJECT` names for it — its mutation arm on any gate (#356).
    """
    fixture = hosts_sh(
        "cti_host_slots local",
        env={"CTI_HOSTS_FILE": local_only_registry(tmp_path)},
    )
    fallback = hosts_sh(
        "cti_host_slots local",
        env={"CTI_HOSTS_FILE": str(tmp_path / "no-such-registry.toml")},
    )
    assert fixture.returncode == 0, fixture.stderr
    assert fallback.returncode == 0, fallback.stderr
    assert fixture.stdout.split() != fallback.stdout.split(), (
        "the fixture registry is indistinguishable from the no-registry fallback, "
        "so no test in this module proves it is being read"
    )


def test_a_one_host_registry_is_the_humans_row(tmp_path: Path) -> None:
    """What the seam derives from a one-row registry: role, transport, slots, key set.

    A claim about the derivation, not about this machine — no test here watches
    the real registry any more, by design (#356). The slot count is the assertion
    that carries the isolation: it is the one value differing from the
    no-registry fallback, so it fails if the registry this test wrote is unread.
    """
    result = hosts_sh(
        "cti_host_role local; cti_host_transport local; cti_host_slots local; "
        'echo "${!CTI_HOST_ROLE[*]}"',
        env={"CTI_HOSTS_FILE": local_only_registry(tmp_path)},
    )
    assert result.stdout.split() == ["human", "null", "5", "local"], result.stderr


def test_an_unknown_host_is_refused_by_the_handle(tmp_path: Path) -> None:
    result = hosts_sh(
        "cti_host_resolve",
        env={"CTI_HOSTS_FILE": local_only_registry(tmp_path), "CTI_TIER_HOST": "nosuchhost"},
    )
    assert result.returncode == EXIT_INFRA_UNAVAILABLE
    assert "no host named 'nosuchhost'" in result.stderr


def test_an_unknown_transport_refuses_instead_of_running_here(tmp_path: Path) -> None:
    """A bad registry state cannot silently fall through to local execution."""
    marker = "ran-here"
    result = hosts_sh(
        "CTI_HOST_ROLE[bravo]=tier; CTI_HOST_TRANSPORT[bravo]=unknown\n"
        f'cti_host_exec bravo echo "{marker}"',
        env={"CTI_HOSTS_FILE": local_only_registry(tmp_path)},
    )
    assert result.returncode == EXIT_INFRA_UNAVAILABLE
    assert marker not in result.stdout
    assert "no transport to 'bravo'" in result.stderr


def registry(tmp_path: Path) -> Path:
    path = tmp_path / "hosts.toml"
    path.write_text(LOCAL_ROW + BRAVO_ROW, encoding="utf-8")
    return path


def test_registry_adds_bravo_with_one_primary_transport(tmp_path: Path) -> None:
    result = hosts_sh(
        "cti_host_resolve; cti_host_transport bravo; cti_host_slots bravo; "
        "cti_host_client_driver bravo; cti_host_remote_root bravo",
        env={"CTI_HOSTS_FILE": str(registry(tmp_path)), "CTI_TIER_HOST": "bravo"},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "bravo",
        "ssh",
        "3",
        "proton",
        "/home/cti/.arma-cti/staging",
    ]


def test_ssh_transport_is_batch_bounded_and_uses_only_the_declared_alias(tmp_path: Path) -> None:
    calls = tmp_path / "ssh-calls"
    ssh = executable(
        tmp_path / "ssh",
        """#!/usr/bin/env bash
printf '%s\\n' "$@" >"$CTI_TEST_SSH_CALLS"
""",
    )
    result = hosts_sh(
        "cti_host_exec bravo true",
        env={
            "CTI_HOSTS_FILE": str(registry(tmp_path)),
            "CTI_TEST_SSH_CALLS": str(calls),
            "PATH": f"{ssh.parent}:{os.environ['PATH']}",
        },
    )
    assert result.returncode == 0, result.stderr
    argv = calls.read_text(encoding="utf-8").splitlines()
    assert "-oBatchMode=yes" in argv
    assert "-oStrictHostKeyChecking=yes" in argv
    assert "-oConnectTimeout=8" in argv
    assert "-oClearAllForwardings=yes" in argv
    assert argv[-3:] == ["--", "true"] or argv[-2:] == ["--", "true"]


def test_ssh_transport_preserves_build_id_sed_argv_across_remote_shell(tmp_path: Path) -> None:
    """OpenSSH joins remote argv; the seam must quote it before that boundary."""
    manifest = tmp_path / "appmanifest_233780.acf"
    manifest.write_text('    "buildid"        "24610432"\n', encoding="utf-8")
    bin_dir = tmp_path / "bin"
    executable(
        bin_dir / "ssh",
        """#!/usr/bin/env bash
while (($#)); do
    case "$1" in
    -T|-o*) shift ;;
    bravo-lan) shift; break ;;
    *) printf 'unexpected ssh argument: %s\\n' "$1" >&2; exit 64 ;;
    esac
done
[[ "${1:-}" == -- ]] && shift
remote_command="$*"
exec /bin/bash -c "$remote_command"
""",
    )
    sed_program = r's/^[[:space:]]*"buildid"[[:space:]]*"\([0-9]*\)".*/\1/p'
    result = hosts_sh(
        f"cti_host_exec bravo sed -n {shlex.quote(sed_program)} {shlex.quote(str(manifest))}",
        env={
            "CTI_HOSTS_FILE": str(registry(tmp_path)),
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
        },
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "24610432"


def test_an_invalid_registry_refuses_every_host(tmp_path: Path) -> None:
    path = registry(tmp_path)
    path.write_text(
        path.read_text(encoding="utf-8").replace("server_slots = 3", "server_slots = 30")
    )
    result = hosts_sh("cti_host_resolve", env={"CTI_HOSTS_FILE": str(path)})
    assert result.returncode == EXIT_INFRA_UNAVAILABLE
    assert "registry could not be read" in result.stderr


def test_remote_whole_pass_preserves_the_callers_selection(tmp_path: Path) -> None:
    home = tmp_path / "home"
    manifest = home / "arma3server" / "steamapps" / "appmanifest_233780.acf"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('"buildid" "123"\n', encoding="utf-8")
    calls = tmp_path / "ssh-calls"
    bin_dir = tmp_path / "bin"
    executable(
        bin_dir / "ssh",
        """#!/usr/bin/env bash
printf 'CALL' >>"$CTI_TEST_SSH_CALLS"
printf '\t%s' "$@" >>"$CTI_TEST_SSH_CALLS"
printf '\n' >>"$CTI_TEST_SSH_CALLS"
if [[ "$*" == *appmanifest_233780.acf* ]]; then printf '123\n'; fi
""",
    )
    executable(bin_dir / "rsync", "#!/usr/bin/env bash\nexit 0\n")
    result = hosts_sh(
        f'cti_host_remote_regress bravo "{REPO}" --host bravo --slots 2 client-port',
        env={
            "CTI_HOSTS_FILE": str(registry(tmp_path)),
            "CTI_TEST_SSH_CALLS": str(calls),
            "HOME": str(home),
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
        },
    )
    assert result.returncode == 0, result.stderr
    main_call = next(
        line for line in calls.read_text(encoding="utf-8").splitlines() if "regress.sh" in line
    )
    assert "\t--host\tbravo\t--slots\t2\tclient-port" in main_call


def git_repo(path: Path) -> Path:
    """Return a committed, clean repository — the state the dirty flag reads as clean."""
    path.mkdir(parents=True)
    for args in (
        ("init", "-q", "-b", "main"),
        ("config", "user.email", "t@example.invalid"),
        ("config", "user.name", "t"),
    ):
        subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)  # noqa: S603, S607
    (path / "README.md").write_text("t\n", encoding="utf-8")
    for args in (("add", "-A"), ("commit", "-qm", "t")):
        subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)  # noqa: S603, S607
    return path


def remote_pass_env(tmp_path: Path) -> tuple[dict[str, str], Path]:
    """Stage one whole remote pass over stubs, exit status under the test's hand.

    Same shape as `test_remote_whole_pass_preserves_the_callers_selection`'s
    arrangement, factored because two more tests drive it: an `ssh` that answers
    the build probe, records every call, and exits `$CTI_TEST_SSH_MAIN_EXIT`
    when the call is the pass itself (`regress.sh`), and an `rsync` that always
    succeeds so a dead main channel is the only failure in the arrangement.
    """
    home = tmp_path / "home"
    manifest = home / "arma3server" / "steamapps" / "appmanifest_233780.acf"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('"buildid" "123"\n', encoding="utf-8")
    calls = tmp_path / "ssh-calls"
    bin_dir = tmp_path / "bin"
    executable(
        bin_dir / "ssh",
        """#!/usr/bin/env bash
printf 'CALL' >>"$CTI_TEST_SSH_CALLS"
printf '\\t%s' "$@" >>"$CTI_TEST_SSH_CALLS"
printf '\\n' >>"$CTI_TEST_SSH_CALLS"
if [[ "$*" == *appmanifest_233780.acf* ]]; then printf '123\\n'; fi
if [[ "$*" == *regress.sh* ]]; then exit "${CTI_TEST_SSH_MAIN_EXIT:-0}"; fi
""",
    )
    executable(bin_dir / "rsync", "#!/usr/bin/env bash\nexit 0\n")
    return (
        {
            "CTI_HOSTS_FILE": str(registry(tmp_path)),
            "CTI_TEST_SSH_CALLS": str(calls),
            "HOME": str(home),
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
        },
        calls,
    )


def main_ssh_call(calls: Path) -> str:
    """Return the newest recorded call that was the pass itself.

    Newest, not first, because the dirty-flag test drives the pass twice over
    one shared call log and asserts on each run's own transmission.
    """
    return [
        line for line in calls.read_text(encoding="utf-8").splitlines() if "regress.sh" in line
    ][-1]


def test_a_dead_ssh_channel_is_infra_unavailable_not_a_verdict(tmp_path: Path) -> None:
    """SSH's own failure code is never a verdict on the code under test (#363).

    OpenSSH exits 255 when it cannot reach, authenticate to, or hold a channel
    to the remote host — the transport died, not the pass. That is
    `((status == 255)) && return "$CTI_EXIT_INFRA_UNAVAILABLE"` in
    `cti_host_remote_regress`, and until #363 nothing tested it: move the
    constant and a dead channel returns SSH's own 255 to a caller that reads it
    as the exit status of `regress.sh` — exactly the misreading the
    failure-class table exists to prevent, on a classification with no test on
    it.

    Which refusal this is, is asserted rather than assumed: the function has
    three other `infra_unavailable` stops with words of their own (unbounded
    target, build disagreement, evidence pull-back), so their absence is pinned
    alongside the exit status. And from the other side, a status that is *not*
    255 passes through unmapped — the mapping is of one code, not a blanket,
    and a remote pass's own verdict must arrive as itself.
    """
    env, calls = remote_pass_env(tmp_path)
    dead = hosts_sh(
        f'cti_host_remote_regress bravo "{REPO}" --host bravo --slots 2 client-port',
        env={**env, "CTI_TEST_SSH_MAIN_EXIT": "255"},
    )
    assert "regress.sh" in calls.read_text(encoding="utf-8"), (
        "the pass never reached its main channel"
    )
    assert dead.returncode == EXIT_INFRA_UNAVAILABLE, dead.stderr
    for other_stop in ("no bounded SSH target", "engine build disagreement", "evidence copy"):
        assert other_stop not in dead.stderr, (
            f"the refusal was {other_stop!r}, not the dead channel"
        )

    verdict = hosts_sh(
        f'cti_host_remote_regress bravo "{REPO}" --host bravo --slots 2 client-port',
        env={**env, "CTI_TEST_SSH_MAIN_EXIT": "3"},
    )
    assert verdict.returncode == 3, verdict.stderr


def test_the_remote_pass_carries_the_worktrees_dirty_flag(tmp_path: Path) -> None:
    """The dirty flag is a decision the pass transmits, so it is tested (#363).

    `cti_host_remote_regress` reads `git status --porcelain` of the tree it is
    shipping and forwards the answer as `CTI_REMOTE_GIT_DIRTY`, which
    `regress.sh` adopts as the run's own `GIT_DIRTY` — the provenance a remote
    verdict carries, answered on the machine that owns the repository rather
    than guessed on the one that runs the pass. Until #363 nothing asserted
    either direction: flipping the `[[ -n … ]]` inverts the flag and the pass
    ships clean trees as dirty and dirty trees as clean, unrecorded by any
    assertion. Both directions are pinned here, on a repository the test built
    for the purpose — never the worktree this test runs in, whose dirt is
    whichever agent's, and whose state no test may assert on.
    """
    repo = git_repo(tmp_path / "repo")
    env, calls = remote_pass_env(tmp_path)
    clean = hosts_sh(
        f'cti_host_remote_regress bravo "{repo}" --host bravo --slots 2 client-port', env=env
    )
    assert clean.returncode == 0, clean.stderr
    assert "\tCTI_REMOTE_GIT_DIRTY=false" in main_ssh_call(calls)

    (repo / "uncommitted").write_text("dirty\n", encoding="utf-8")
    dirty = hosts_sh(
        f'cti_host_remote_regress bravo "{repo}" --host bravo --slots 2 client-port', env=env
    )
    assert dirty.returncode == 0, dirty.stderr
    assert "\tCTI_REMOTE_GIT_DIRTY=true" in main_ssh_call(calls)


# -------------------------------------------------------------------- the guard


def test_the_guard_is_asked_of_a_host_a_human_plays_on(tmp_path: Path) -> None:
    """Unchanged behaviour for the one host that exists: a live game is a stop."""
    calls = tmp_path / "calls"
    result = hosts_sh(
        "cti_host_guard local",
        env={
            "CTI_HOSTS_FILE": local_only_registry(tmp_path),
            "CTI_WINDOWS_TASKLIST": str(executable(tmp_path / "tasklist.sh", TASKLIST_RUNNING)),
            "CTI_TEST_TASKLIST_CALLS": str(calls),
        },
    )
    assert result.returncode == EXIT_INFRA_UNAVAILABLE
    assert "failure_class=infra_unavailable failure_reason=play_session host=local" in result.stderr
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
            "CTI_HOSTS_FILE": local_only_registry(tmp_path),
            "CTI_WINDOWS_TASKLIST": str(executable(tmp_path / "tasklist.sh", TASKLIST_RUNNING)),
            "CTI_TEST_TASKLIST_CALLS": str(calls),
        },
    )
    assert result.returncode == 0, result.stderr
    assert not calls.exists(), "the tier's own host was asked whether a human was playing on it"


# --------------------------------------------------------------- the pool runner


def test_a_pool_run_aimed_at_an_unknown_host_launches_nothing(tmp_path: Path) -> None:
    """Refused before a lock, a port or a world — and refused as not-a-result."""
    result = pool_run(
        tmp_path,
        "--slots",
        "3",
        extra_env={
            "CTI_HOSTS_FILE": local_only_registry(tmp_path),
            "CTI_TIER_HOST": "nosuchhost",
        },
    )
    assert result.returncode == EXIT_INFRA_UNAVAILABLE, result.stderr[-4000:]
    assert "failure_class=infra_unavailable" in result.stderr
    assert "host=nosuchhost" in result.stderr
    assert not (tmp_path / "trace.tsv").exists(), "a probe ran on a host the tier cannot reach"
    assert not sorted((tmp_path / "state").rglob("*-pool")), "evidence was written for a non-run"


def test_the_host_reaches_the_run_that_executes_on_it(tmp_path: Path) -> None:
    """#44's rule, one level up: a host boundary is only real where something reads it.

    A `host` field written by the parent out of its own variable would say
    `local` whatever machine the world came up on. What makes it a boundary is
    that the handle travels to the launch and the run records what it received.
    """
    pool_run(tmp_path, "--slots", "2", extra_env={"CTI_HOSTS_FILE": local_only_registry(tmp_path)})
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

    Which refusal this is, is asserted rather than assumed. `run.sh` has several
    `infra_unavailable` stops after this one, and which one comes next depends
    on the box: in source order it is the server binary
    (`${CTI_SERVER_DIR:-$HOME/arma3server}/arma3server_x64`, machine state
    outside the worktree), then the pre-flight, and only then the unbuilt shim a
    fresh worktree stops on. The four host fields hold on every one of them, so
    a test reading only those
    would go green on a run the guard never touched. It did: flipping the
    fixture's role to `tier` skips the guard entirely and the shim check refuses
    a few lines later, with the same class and the same host. So the guard's own
    words are pinned, and so is the tasklist actually having been asked.
    """
    out = tmp_path / "out"
    out.mkdir()
    calls = tmp_path / "calls"
    env = {
        **os.environ,
        "CTI_HOSTS_FILE": local_only_registry(tmp_path),
        "CTI_SPIKE_OUT": str(out),
        "CTI_WINDOWS_TASKLIST": str(executable(tmp_path / "tasklist.sh", TASKLIST_RUNNING)),
        "CTI_TEST_TASKLIST_CALLS": str(calls),
        "CTI_TIER_SLOT": "2",
        # No test of this tier owns machine state (#132): the locks under
        # $HOME/.arma-cti belong to runs that have Arma in front of them.
        "CTI_TIER_STATE": str(tmp_path / "state"),
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
    assert recorded["failure_detail"] == (
        "failure_reason=play_session; arma3_x64.exe is in the Windows process list — "
        "that is a play session, not ours"
    )
    assert calls.read_text().split() == ["asked"], "the guard was not the thing that refused"


def test_an_unknown_host_is_refused_by_the_harness_too(tmp_path: Path) -> None:
    """`just probe` reaches `run.sh` directly, so the handle is checked there too."""
    out = tmp_path / "out"
    out.mkdir()
    env = {
        **os.environ,
        "CTI_HOSTS_FILE": local_only_registry(tmp_path),
        "CTI_SPIKE_OUT": str(out),
        "CTI_TIER_HOST": "nosuchhost",
        "CTI_WINDOWS_TASKLIST": str(executable(tmp_path / "tasklist.sh", TASKLIST_RUNNING)),
        "CTI_TEST_TASKLIST_CALLS": str(tmp_path / "calls"),
        "CTI_TIER_STATE": str(tmp_path / "state"),
    }
    # S603: this repo's own harness.
    subprocess.run(  # noqa: S603
        [BASH, str(RUN_SH), "--regress"], capture_output=True, text=True, check=False, env=env
    )
    recorded = dict(
        line.split("=", 1) for line in (out / "results.env").read_text().splitlines() if "=" in line
    )
    assert recorded["failure_class"] == "infra_unavailable"
    assert "nosuchhost" in recorded["failure_detail"]
    assert not (tmp_path / "calls").exists(), "a run aimed at an unreachable host touched a host"
