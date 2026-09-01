"""Tests for the fail-closed GitHub body guard (#675)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import load_tool

gh_body_guard = load_tool("gh_body_guard")
REPO = Path(__file__).parents[2]
HOOK_INTEGRATION_FIXTURE = Path(__file__).parents[1] / "fixtures" / "675-hook-integration.diff"
HOOK_INTEGRATION_BASE = "a67980f9"


def test_backticked_body_is_literal_when_sent_through_a_body_file(tmp_path: Path) -> None:
    """A backticked fragment is data in a body file, never shell syntax."""
    marker = tmp_path / "executed"
    body = tmp_path / "comment.md"
    literal = f"A literal shell fragment: `touch {marker}`\n"
    body.write_text(literal, encoding="utf-8")
    received = tmp_path / "received.md"
    fake_gh = tmp_path / "fake-gh.py"
    fake_gh.write_text(
        "import os\n"
        "import sys\n"
        "from pathlib import Path\n"
        "body = Path(sys.argv[sys.argv.index('--body-file') + 1])\n"
        "Path(os.environ['RECEIVED']).write_text(\n"
        "    body.read_text(encoding='utf-8'), encoding='utf-8'\n"
        ")\n",
        encoding="utf-8",
    )

    unsafe = f'gh issue comment 675 --body "A literal shell fragment: `touch {marker}`"'
    denial = gh_body_guard.denial(unsafe)
    assert denial is not None

    safe = f'"{sys.executable}" "{fake_gh}" issue comment 675 --body-file "{body}"'
    completed = subprocess.run(  # noqa: S603 — the shell is the reproduction boundary under test
        ["/bin/bash", "-c", safe],
        env={"PATH": os.environ.get("PATH", ""), "RECEIVED": str(received)},
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert received.read_text(encoding="utf-8") == literal
    assert not marker.exists()


@pytest.mark.parametrize(
    "command",
    [
        'gh issue comment 675 --body "plain body"',
        'gh issue create --title title --body "plain body"',
        'gh pr comment 12 --body "plain body"',
        'gh pr create --title title --body="plain body"',
        "gh future-command --body plain",
    ],
)
def test_inline_body_is_refused_without_enumerating_gh_subcommands(command: str) -> None:
    denial = gh_body_guard.denial(command)
    assert denial == gh_body_guard.INLINE_BODY


@pytest.mark.parametrize(
    "command",
    [
        "gh issue comment 675 --body-file comment.md",
        "gh issue comment 675 --body-file=-",
        "gh pr create --title title --body-file /tmp/comment.md",
    ],
)
def test_complete_body_file_forms_are_allowed(command: str) -> None:
    assert gh_body_guard.denial(command) is None


@pytest.mark.parametrize(
    "command",
    [
        "gh issue comment 675 --body",
        "gh issue comment 675 --body-file",
        "gh issue comment 675 --body-file=",
        'gh issue comment 675 --body "unterminated',
    ],
)
def test_incomplete_body_commands_are_refused_fail_closed(command: str) -> None:
    assert gh_body_guard.denial(command) == gh_body_guard.UNREADABLE


@pytest.mark.parametrize(
    "command",
    [
        'GH_TOKEN=secret gh issue comment 675 --body "plain body"',
        'env GH_TOKEN=secret gh issue comment 675 --body "plain body"',
        'command gh issue comment 675 --body "plain body"',
        'exec gh issue comment 675 --body "plain body"',
    ],
)
def test_common_wrappers_cannot_hide_an_inline_body(command: str) -> None:
    assert gh_body_guard.denial(command) == gh_body_guard.INLINE_BODY


def test_a_gh_phrase_inside_another_command_is_not_an_invocation() -> None:
    assert gh_body_guard.denial('printf "%s" "gh issue comment --body prose"') is None


def test_hook_fixture_reconstructs_the_committed_hook(tmp_path: Path) -> None:
    """The reserved hook's external integration diff rebuilds its intended bytes."""
    baseline = subprocess.run(  # noqa: S603 — the fixture's fixed Git read
        [  # noqa: S607 — Git is the fixed fixture reader
            "git",
            "show",
            f"{HOOK_INTEGRATION_BASE}:.claude/hooks/protect-gated-paths.py",
        ],
        cwd=REPO,
        capture_output=True,
        check=False,
    )
    assert baseline.returncode == 0, baseline.stderr.decode()

    target = tmp_path / ".claude" / "hooks" / "protect-gated-paths.py"
    target.parent.mkdir(parents=True)
    target.write_bytes(baseline.stdout)
    checked = subprocess.run(  # noqa: S603 — the fixture's fixed Git patch check
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

    expected = baseline.stdout.replace(
        b"from gated_paths import hook_denial\n",
        b"from gated_paths import hook_denial\n"
        b"from gh_body_guard import denial as gh_body_denial\n",
        1,
    ).replace(
        b'    """Return why this Bash command is denied, or `None` to allow it."""\n'
        b"    segments = read_command(command)\n",
        b'    """Return why this Bash command is denied, or `None` to allow it."""\n'
        b"    body_reason = gh_body_denial(command)\n"
        b"    if body_reason is not None:\n"
        b"        return body_reason\n"
        b"    segments = read_command(command)\n",
        1,
    )
    assert target.read_bytes() == expected
