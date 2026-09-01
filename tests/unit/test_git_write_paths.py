"""Tests for the positive Git write-target reader (#673)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from conftest import load_tool

git_write_paths = load_tool("git_write_paths")

ROOT = Path("/assigned/worktree")
OTHER = Path("/other/checkout")
HOOK_INTEGRATION_FIXTURE = Path(__file__).parents[1] / "fixtures" / "673-hook-integration.diff"
HOOK_INTEGRATION_BASE = "80aa12b7^"


@pytest.mark.parametrize(
    "words",
    [
        ["git", "status"],
        ["git", "-C", str(OTHER), "log", "--oneline"],
        ["git", "diff"],
        ["git", "grep", "Campaign"],
        ["git", "--version"],
        ["git", "apply", "--check", "candidate.diff"],
        ["git", "apply", "--check", "--", "candidate.diff"],
    ],
)
def test_known_local_reads_have_no_write_target(words: list[str]) -> None:
    assert git_write_paths.git_write_paths(words, ROOT) == ()


def test_read_command_output_is_a_target_when_it_has_a_file_output_flag() -> None:
    assert git_write_paths.git_write_paths(
        ["git", "diff", "--output", "reports/diff.txt"], ROOT
    ) == (str(ROOT / "reports/diff.txt"),)
    assert git_write_paths.git_write_paths(["git", "diff", "--output=reports/other.txt"], ROOT) == (
        str(ROOT / "reports/other.txt"),
    )


def test_push_is_explicitly_non_local() -> None:
    assert (
        git_write_paths.git_write_paths(
            ["git", "-C", str(OTHER), "push", "-o", "remote-option"], ROOT
        )
        == ()
    )


@pytest.mark.parametrize(
    "words",
    [
        ["git", "add", "tools/land.py"],
        ["git", "commit", "-m", "message"],
        ["git", "rebase", "origin/main"],
        ["git", "fetch", "origin"],
        ["git", "merge", "origin/main"],
        ["git", "stash", "push"],
    ],
)
def test_common_repository_writes_target_the_assigned_location(words: list[str]) -> None:
    assert git_write_paths.git_write_paths(words, ROOT) == (str(ROOT),)


def test_explicit_locations_are_all_write_targets() -> None:
    assert git_write_paths.git_write_paths(
        ["git", "-C", str(OTHER), "restore", "tools/land.py"], ROOT
    ) == (str(OTHER), str(OTHER / "tools/land.py"))
    assert git_write_paths.git_write_paths(
        ["git", "--work-tree", str(OTHER), "restore", "tools/land.py"], ROOT
    ) == (str(OTHER), str(OTHER / "tools/land.py"))
    assert git_write_paths.git_write_paths(
        [
            "git",
            f"--git-dir={OTHER / '.git'}",
            f"--work-tree={OTHER}",
            "restore",
            "tools/land.py",
        ],
        ROOT,
    ) == (str(OTHER), str(OTHER / ".git"), str(OTHER / "tools/land.py"))


def test_explicit_c_can_be_attached_to_the_flag() -> None:
    assert git_write_paths.git_write_paths(
        ["git", f"-C{OTHER}", "restore", "tools/land.py"], ROOT
    ) == (str(OTHER), str(OTHER / "tools/land.py"))


@pytest.mark.parametrize(
    "words",
    [
        ["git", "restore", "tools/land.py"],
        ["git", "restore", "--source", "HEAD", "tools/land.py"],
        ["git", "checkout", "--", "tools/land.py"],
        ["git", "clean", "-df", "build"],
        ["git", "reset", "--hard", "HEAD", "--", "tools/land.py"],
        ["git", "mv", "old.txt", "new.txt"],
        ["git", "rm", "old.txt", "other.txt"],
        ["git", "switch", "feature"],
    ],
)
def test_path_writes_include_the_work_tree_and_explicit_paths(words: list[str]) -> None:
    targets = git_write_paths.git_write_paths(words, ROOT)
    assert targets is not None
    assert str(ROOT) in targets
    assert all(not target.startswith(str(OTHER)) for target in targets)


def test_staged_restore_only_writes_git_state() -> None:
    assert git_write_paths.git_write_paths(
        ["git", "restore", "--staged", "docs/adr/0077.md"], ROOT
    ) == (str(ROOT),)


def test_dry_run_clean_and_move_are_non_writes() -> None:
    assert git_write_paths.git_write_paths(["git", "clean", "-n", "build"], ROOT) == ()
    assert git_write_paths.git_write_paths(["git", "mv", "-n", "old", "new"], ROOT) == ()
    assert git_write_paths.git_write_paths(["git", "rm", "--dry-run", "old"], ROOT) == ()


@pytest.mark.parametrize(
    "words",
    [
        ["git", "restore", "*.py"],
        ["git", "restore", ":(exclude)tools/land.py"],
        ["git", "restore", "--pathspec-from-file=-"],
        ["git", "--unsupported-option", "restore", "tools/land.py"],
        ["git", "-C", "$OTHER", "restore", "tools/land.py"],
        ["git", "-c", "core.worktree=/other/checkout", "checkout", "--", "tools/land.py"],
        ["git", "-ccore.worktree=/other/checkout", "checkout", "--", "tools/land.py"],
        ["git", "--config-env", "core.worktree=WORKTREE", "checkout", "--", "tools/land.py"],
        ["git", "--config-env=core.worktree=WORKTREE", "checkout", "--", "tools/land.py"],
        ["git", "apply", "candidate.diff"],
        ["git", "apply", "--check", "--unknown", "candidate.diff"],
    ],
)
def test_unproven_git_shapes_are_unreadable(words: list[str]) -> None:
    assert git_write_paths.git_write_paths(words, ROOT) is None


def test_rebase_exec_and_unscoped_config_are_unreadable() -> None:
    assert (
        git_write_paths.git_write_paths(["git", "rebase", "--exec", "echo", "origin/main"], ROOT)
        is None
    )
    assert (
        git_write_paths.git_write_paths(["git", "config", "--global", "user.name", "agent"], ROOT)
        is None
    )
    assert (
        git_write_paths.git_write_paths(
            ["git", "config", "--file", "external-config", "user.name", "agent"], ROOT
        )
        is None
    )


@pytest.mark.parametrize(
    ("words", "expected"),
    [
        (["git", "config", "--get", "user.name"], ()),
        (["git", "config", "user.name", "agent"], (str(ROOT),)),
        (["git", "tag", "--list"], ()),
        (["git", "tag", "release"], (str(ROOT),)),
        (["git", "branch", "--show-current"], ()),
        (["git", "branch", "feature"], (str(ROOT),)),
        (["git", "remote", "-v"], ()),
        (["git", "remote", "add", "origin", "url"], (str(ROOT),)),
    ],
)
def test_conditional_git_commands_have_explicit_defaults(
    words: list[str], expected: tuple[str, ...]
) -> None:
    assert git_write_paths.git_write_paths(words, ROOT) == expected


def test_directory_changes_are_resolved_as_the_shell_resolves_them() -> None:
    assert git_write_paths.changed_directory([], ROOT) == ROOT
    assert git_write_paths.changed_directory(["echo", "x"], ROOT) == ROOT
    assert git_write_paths.changed_directory(["cd", str(OTHER)], ROOT) == OTHER
    assert git_write_paths.changed_directory(["cd", "-P", "--", str(OTHER)], ROOT) == OTHER


@pytest.mark.parametrize(
    "words",
    [["cd"], ["cd", "-"], ["cd", "~"], ["cd", "$OTHER", "extra"], ["pushd", str(OTHER)]],
)
def test_unsupported_directory_changes_are_unreadable(words: list[str]) -> None:
    assert git_write_paths.changed_directory(words, ROOT) is None


def test_hook_fixture_reconstructs_the_committed_hook(tmp_path: Path) -> None:
    baseline = subprocess.run(  # noqa: S603 — the fixture's fixed Git read
        [  # noqa: S607 — Git is the fixed fixture reader
            "git",
            "show",
            f"{HOOK_INTEGRATION_BASE}:.claude/hooks/protect-gated-paths.py",
        ],
        cwd=Path(__file__).parents[2],
        capture_output=True,
        check=False,
    )
    assert baseline.returncode == 0, baseline.stderr.decode()

    target = tmp_path / ".claude" / "hooks" / "protect-gated-paths.py"
    target.parent.mkdir(parents=True)
    target.write_bytes(baseline.stdout)
    checked = subprocess.run(  # noqa: S603 — the fixture's fixed Git read
        ["git", "apply", "--check", str(HOOK_INTEGRATION_FIXTURE)],  # noqa: S607
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert checked.returncode == 0, checked.stderr
    applied = subprocess.run(  # noqa: S603 — the fixture's fixed Git patch
        ["git", "apply", str(HOOK_INTEGRATION_FIXTURE)],  # noqa: S607
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert applied.returncode == 0, applied.stderr
    assert (
        target.read_bytes()
        == (Path(__file__).parents[2] / ".claude/hooks/protect-gated-paths.py").read_bytes()
    )


def test_hook_fixture_pins_public_reader_wiring() -> None:
    fixture = HOOK_INTEGRATION_FIXTURE.read_text(encoding="utf-8")
    for wiring in (
        "from git_write_paths import changed_directory, git_write_paths",
        "git_targets = git_write_paths(words, cwd)",
        "cwd = changed_directory(words, cwd)",
    ):
        assert wiring in fixture

    assert git_write_paths.git_write_paths(["git", "status"], ROOT) == ()
    assert git_write_paths.git_write_paths(["git", "add", "tools/land.py"], ROOT) == (str(ROOT),)
    assert git_write_paths.git_write_paths(["git", "future-subcommand"], ROOT) is None
