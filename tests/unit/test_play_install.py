"""Staging `@cti` into the human's own Arma install (issue #153).

`spike/run.sh` puts the built addon inside the real Steam install on the Windows
host, because `-mod=` resolves against the game directory. That folder is the one
the human's evening plays out of, so the failure this file is about is not a red
run: it is `rm -rf @cti` followed by a multi-second `cp` across the WSL/Windows
boundary, a run killed inside that window, and a person launching Arma hours
later into a mod that is half there and nothing automated that repairs it.

The property under test is #153's acceptance criterion, stated as an invariant:
at every instant the live `@cti` is either the previous good copy or a verified
new one. Two ways at it — the state machine, exhaustively and deterministically,
and one real SIGKILL during a real copy.

No Arma: this is `cp`, `mv` and `find` over a tmp_path.
"""

from __future__ import annotations

import os
import shutil
import signal
import stat
import subprocess
import time
from typing import TYPE_CHECKING

import pytest
from conftest import REPO

# Same directory, pytest's prepend import mode. `spike/run.sh` over a stub server
# and a stub client is that file's harness, and the two run.sh-level claims here
# are about the same world it already builds.
from test_run_verdict import run_with_lines

if TYPE_CHECKING:
    from pathlib import Path

PLAY_INSTALL_SH = REPO / "spike" / "play-install.sh"
BASH = shutil.which("bash") or "/bin/bash"

MOD = "@cti"


def play_eval(script: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    """Run a snippet with `spike/play-install.sh` sourced."""
    full = f'set -uo pipefail\nsource "{PLAY_INSTALL_SH}"\n{script}'
    # S603: this repo's own library, with a script this test wrote.
    return subprocess.run(  # noqa: S603
        [BASH, "-c", full], capture_output=True, text=True, check=False, timeout=timeout
    )


def tree(root: Path) -> dict[str, int]:
    """Every file under a tree, by relative path and size."""
    if not root.is_dir():
        return {}
    return {
        str(path.relative_to(root)): path.stat().st_size
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def addons(root: Path, files: dict[str, bytes]) -> Path:
    """Build a stand-in for HEMTT's output: `<root>/addons/*.pbo`."""
    built = root / "addons"
    built.mkdir(parents=True, exist_ok=True)
    for name, body in files.items():
        (built / name).write_bytes(body)
    return built


@pytest.fixture
def install(tmp_path: Path) -> Path:
    """Make a stand-in for the human's Steam install directory."""
    path = tmp_path / "windows-arma"
    path.mkdir()
    return path


# ------------------------------------------------------------------ the swap


def test_a_first_stage_lands_the_whole_addon(install: Path, tmp_path: Path) -> None:
    src = addons(tmp_path / "build", {"cti_main.pbo": b"one", "cti_ui.pbo": b"two"})
    result = play_eval(f'cti_play_install_stage "{install}" "{MOD}" "{src}"')
    assert result.returncode == 0, result.stdout + result.stderr
    assert tree(install / MOD / "addons") == tree(src)


def test_a_restage_replaces_the_previous_copy_and_leaves_nothing_beside_it(
    install: Path, tmp_path: Path
) -> None:
    """The litter matters: this folder is the human's, not the tier's.

    A `@cti.previous` or `@cti.staging` left behind is a second copy of the mod
    inside a Steam install, and Arma's own launcher lists every `@` folder it
    finds.
    """
    first = addons(tmp_path / "build-1", {"cti_main.pbo": b"old"})
    play_eval(f'cti_play_install_stage "{install}" "{MOD}" "{first}"')
    second = addons(tmp_path / "build-2", {"cti_main.pbo": b"newer", "cti_extra.pbo": b"x"})
    result = play_eval(f'cti_play_install_stage "{install}" "{MOD}" "{second}"')

    assert result.returncode == 0, result.stdout + result.stderr
    assert tree(install / MOD / "addons") == tree(second)
    assert sorted(p.name for p in install.iterdir()) == [MOD]


def test_a_copy_that_fails_leaves_the_previous_copy_in_place(install: Path, tmp_path: Path) -> None:
    """The whole point of staging beside rather than into.

    Under the old `rm -rf` then `cp`, a copy that failed left the play install
    with no mod at all and the run reporting `infra_unavailable` about it.
    """
    good = addons(tmp_path / "build", {"cti_main.pbo": b"the copy the human plays"})
    play_eval(f'cti_play_install_stage "{install}" "{MOD}" "{good}"')
    before = tree(install / MOD / "addons")

    broken = addons(tmp_path / "broken", {"cti_main.pbo": b"x"})
    (broken / "cti_main.pbo").chmod(0o000)
    result = play_eval(f'cti_play_install_stage "{install}" "{MOD}" "{broken}"')
    (broken / "cti_main.pbo").chmod(0o644)

    if result.returncode == 0:  # pragma: no cover - only when the tests run as root
        pytest.skip("this user can read a mode-000 file, so the copy cannot be made to fail")
    assert tree(install / MOD / "addons") == before, "a failed copy took the play install with it"
    assert result.stdout.strip(), "a failed stage told the caller nothing to type into its verdict"
    assert sorted(p.name for p in install.iterdir()) == [MOD]


@pytest.mark.parametrize(
    ("staged", "why"),
    [
        (
            {"cti_main.pbo": b"short", "b.pbo": b"bb"},
            "a copy that stopped early, or ran out of disk",
        ),
        ({"cti_main.pbo": b"the copy the human plays"}, "a file the copy never reached"),
    ],
)
def test_the_verifier_reads_a_short_or_missing_file_as_a_mismatch(
    tmp_path: Path, staged: dict[str, bytes], why: str
) -> None:
    """`cp` returning 0 is what the swap waits on; this is what it is checked against.

    Sizes rather than checksums, so what it has to catch is exactly this: a
    staged tree short of its source by a byte or by a file.
    """
    src = addons(tmp_path / "build", {"cti_main.pbo": b"the copy the human plays", "b.pbo": b"bb"})
    copy = addons(tmp_path / "staged", staged)
    result = play_eval(
        f'if [[ "$(cti_play_install_manifest "{src}")" == '
        f'"$(cti_play_install_manifest "{copy}")" ]]; then echo SAME; else echo DIFFERENT; fi'
    )
    assert result.stdout.strip() == "DIFFERENT", f"{why}: {result.stderr}"


# ------------------------------------------- every interruptible state, repaired


def test_a_run_killed_between_the_two_renames_is_repaired(install: Path) -> None:
    """The one instant in which the play install genuinely has no mod."""
    (install / f"{MOD}.previous" / "addons").mkdir(parents=True)
    (install / f"{MOD}.previous" / "addons" / "cti_main.pbo").write_bytes(b"previous good")
    assert not (install / MOD).exists()

    result = play_eval(f'cti_play_install_repair "{install}" "{MOD}"')

    assert result.returncode == 0, result.stderr
    assert (install / MOD / "addons" / "cti_main.pbo").read_bytes() == b"previous good"
    assert sorted(p.name for p in install.iterdir()) == [MOD]


def test_a_run_killed_mid_copy_leaves_the_live_folder_alone(install: Path) -> None:
    """A half-built staging tree is litter, not damage."""
    (install / MOD / "addons").mkdir(parents=True)
    (install / MOD / "addons" / "cti_main.pbo").write_bytes(b"previous good")
    (install / f"{MOD}.staging" / "addons").mkdir(parents=True)
    (install / f"{MOD}.staging" / "addons" / "cti_main.pbo").write_bytes(b"half a")

    result = play_eval(f'cti_play_install_repair "{install}" "{MOD}"')

    assert result.returncode == 0, result.stderr
    assert (install / MOD / "addons" / "cti_main.pbo").read_bytes() == b"previous good"
    assert sorted(p.name for p in install.iterdir()) == [MOD]


def test_a_run_killed_before_the_old_copy_was_collected_is_tidied(install: Path) -> None:
    """Killed after the swap: the new mod is live and the old one is litter."""
    (install / MOD / "addons").mkdir(parents=True)
    (install / MOD / "addons" / "cti_main.pbo").write_bytes(b"verified new")
    (install / f"{MOD}.previous" / "addons").mkdir(parents=True)
    (install / f"{MOD}.previous" / "addons" / "cti_main.pbo").write_bytes(b"previous good")

    result = play_eval(f'cti_play_install_repair "{install}" "{MOD}"')

    assert result.returncode == 0, result.stderr
    assert (install / MOD / "addons" / "cti_main.pbo").read_bytes() == b"verified new"
    assert sorted(p.name for p in install.iterdir()) == [MOD]


def test_repairing_a_healthy_install_changes_nothing(install: Path) -> None:
    """It runs on the way out of every run that staged, including green ones."""
    (install / MOD / "addons").mkdir(parents=True)
    (install / MOD / "addons" / "cti_main.pbo").write_bytes(b"fine")
    before = tree(install)
    assert play_eval(f'cti_play_install_repair "{install}" "{MOD}"').returncode == 0
    assert tree(install) == before


def test_repairing_an_install_that_never_had_the_mod_is_not_a_failure(install: Path) -> None:
    """A first stage on a fresh machine goes through the repair on its way in."""
    result = play_eval(f'cti_play_install_repair "{install}" "{MOD}"')
    assert result.returncode == 0, result.stderr
    assert not (install / MOD).exists()


# --------------------------------------------------- and one real SIGKILL


def test_a_real_kill_during_a_real_copy_never_leaves_a_half_staged_mod(
    install: Path, tmp_path: Path
) -> None:
    """#153's criterion, against the thing it is about rather than a model of it.

    Enough files that the copy is comfortably wider than the poll that watches
    for it; the kill goes in once the staging tree exists and is provably short
    of its source, so the process dies inside the window the old code was
    unsafe in. The claim afterwards is the criterion verbatim: previous-good or
    verified-new, never half-staged.

    The kill goes to the process *group*, which is what Ctrl-C and the OOM killer
    reach and what `spike/regress.sh`'s teardown was taught to reach on #151. A
    signal to the shell alone leaves its `cp` running as an orphan — still safe,
    because that `cp` only ever writes under `<mod>.staging` and its paths stop
    resolving the instant the swap renames that away, but it is a different claim
    from this one and it would race the repair this test asserts.
    """
    (install / MOD / "addons").mkdir(parents=True)
    (install / MOD / "addons" / "cti_main.pbo").write_bytes(b"previous good")
    previous_good = tree(install / MOD)

    src = addons(tmp_path / "build", {f"cti_{n:05d}.pbo": b"x" * 64 for n in range(6000)})
    new_addons = tree(src)

    # S603: this repo's own library, with paths this test just wrote.
    staging = subprocess.Popen(  # noqa: S603
        [
            BASH,
            "-c",
            (
                f'set -uo pipefail\nsource "{PLAY_INSTALL_SH}"\n'
                f'cti_play_install_stage "{install}" "{MOD}" "{src}"'
            ),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        partial = install / f"{MOD}.staging" / "addons"
        deadline = time.monotonic() + 60
        while True:
            copied = len(list(partial.iterdir())) if partial.is_dir() else 0
            if 0 < copied < len(new_addons):
                break
            missed = (
                "never observed the copy in progress, so this test did not exercise the window "
                f"it exists for (copied {copied} of {len(new_addons)})"
            )
            assert staging.poll() is None, missed
            assert time.monotonic() < deadline, missed
        os.killpg(os.getpgid(staging.pid), signal.SIGKILL)
    finally:
        staging.wait(timeout=60)

    live = tree(install / MOD)
    assert live in (previous_good, {f"addons/{k}": v for k, v in new_addons.items()}), (
        "the play install was left half-staged by a run killed mid-copy"
    )
    # And the next run puts the folder back to exactly one copy of the mod
    # without a human touching anything.
    assert play_eval(f'cti_play_install_repair "{install}" "{MOD}"').returncode == 0
    assert sorted(p.name for p in install.iterdir()) == [MOD]
    assert tree(install / MOD) == live


# ------------------------------------------------- through spike/run.sh itself


def client_run(tmp_path: Path, install: Path) -> dict[str, str]:
    """One `spike/run.sh` pass that sends the headed client, over stubs."""
    client = install / "arma3_x64.exe"
    client.write_text("#!/usr/bin/env bash\nsleep 600\n")
    client.chmod(client.stat().st_mode | stat.S_IXUSR)

    taskkill = tmp_path / "taskkill.sh"
    taskkill.write_text("#!/usr/bin/env bash\necho 'SUCCESS: sent'\n")
    taskkill.chmod(taskkill.stat().st_mode | stat.S_IXUSR)

    return run_with_lines(
        tmp_path,
        ["measurement thing=1"],
        extra_env={
            "CTI_WINDOWS_CLIENT": "1",
            "CTI_WINDOWS_ARMA_DIR": str(install),
            "CTI_WINDOWS_TASKKILL": str(taskkill),
            "CTI_WINDOWS_EXIT_TIMEOUT": "30",
        },
    )


def test_a_run_leaves_the_play_install_holding_exactly_one_copy_of_the_mod(
    tmp_path: Path, install: Path
) -> None:
    """What the human's Steam folder looks like once the harness has finished with it.

    Arma's launcher lists every `@` folder it finds, so a `@cti.previous` left
    beside the live one is a second entry in the human's mod list, and the
    staging tree is a duplicate of the whole addon inside a game install.
    """
    records = client_run(tmp_path, install)
    assert records["verdict"] == "PASS", (
        f"{records.get('failure_class')}: {records.get('failure_detail')}\n{records['_stderr']}"
    )
    assert (install / MOD / "addons" / "stub.pbo").exists()
    assert sorted(p.name for p in install.iterdir()) == [MOD, "arma3_x64.exe"]


def test_a_run_repairs_an_interrupted_swap_left_by_the_last_one(
    tmp_path: Path, install: Path
) -> None:
    """The way in, for the state a `kill -9` in the swap window leaves behind.

    Nobody has to notice: the next run through this path finds the play install
    without its mod and the previous copy beside it, and puts it back before it
    stages anything of its own.
    """
    (install / f"{MOD}.previous" / "addons").mkdir(parents=True)
    (install / f"{MOD}.previous" / "addons" / "old.pbo").write_bytes(b"previous good")

    records = client_run(tmp_path, install)

    assert records["verdict"] == "PASS", (
        f"{records.get('failure_class')}: {records.get('failure_detail')}\n{records['_stderr']}"
    )
    assert "restored the previous @cti" in records["_stderr"]
    # And then restaged over it, so what is left is this run's addon and nothing else.
    assert sorted(p.name for p in (install / MOD / "addons").iterdir()) == ["stub.pbo"]
    assert sorted(p.name for p in install.iterdir()) == [MOD, "arma3_x64.exe"]
