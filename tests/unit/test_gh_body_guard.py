"""Tests for the fail-closed GitHub body guard (#675)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import load_tool

gh_body_guard = load_tool("gh_body_guard")
REPO = Path(__file__).parents[2]
HOOK_INTEGRATION_FIXTURE = Path(__file__).parents[1] / "fixtures" / "675-hook-integration.diff"
HOOK_INTEGRATION_BASE = "a67980f9"


def stage_integrated_hook(tmp_path: Path) -> tuple[Path, Path, bytes]:
    """Apply the reserved hook fixture to a runnable scratch copy."""
    scratch = tmp_path / "scratch-repo"
    shutil.copytree(REPO / ".claude", scratch / ".claude")
    shutil.copytree(REPO / "tools", scratch / "tools")

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

    target = scratch / ".claude" / "hooks" / "protect-gated-paths.py"
    target.write_bytes(baseline.stdout)
    checked = subprocess.run(  # noqa: S603 — the fixture's fixed Git patch check
        ["git", "apply", "--check", str(HOOK_INTEGRATION_FIXTURE)],  # noqa: S607
        cwd=scratch,
        capture_output=True,
        text=True,
        check=False,
    )
    assert checked.returncode == 0, checked.stderr
    applied = subprocess.run(  # noqa: S603 — the fixture's fixed Git patch
        ["git", "apply", str(HOOK_INTEGRATION_FIXTURE)],  # noqa: S607
        cwd=scratch,
        capture_output=True,
        text=True,
        check=False,
    )
    assert applied.returncode == 0, applied.stderr
    return scratch, target, baseline.stdout


def run_integrated_hook(scratch: Path, command: str) -> subprocess.CompletedProcess[str]:
    """Run the fixture-applied hook through its JSON Bash boundary."""
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    return subprocess.run(  # noqa: S603 — argv is the scratch hook and fixed interpreter
        [sys.executable, str(scratch / ".claude" / "hooks" / "protect-gated-paths.py")],
        cwd=scratch,
        env={"PATH": os.environ.get("PATH", "")},
        input=payload,
        capture_output=True,
        text=True,
        check=False,
    )


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

    unsafe = f'gh issue comment 675 -b "A literal shell fragment: `touch {marker}`"'
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
        'gh issue comment 675 -b "plain body"',
        "gh issue comment 675 -b=plain",
        "gh issue comment 675 -bplain",
        'gh issue create --title title --body "plain body"',
        'gh pr comment 12 --body "plain body"',
        'gh pr create --title title --body="plain body"',
        'gh issue close 675 --comment "plain body"',
        'gh issue close 675 -c "plain body"',
        "gh issue close 675 -c=plain",
        "gh issue close 675 -cplain",
        "gh issue close 675 --comment=plain",
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
        "gh issue comment 675 -F comment.md",
        "gh issue comment 675 -Fcomment.md",
        "gh issue close 675 --comment-file comment.md",
        "gh pr create --title title --body-file /tmp/comment.md",
    ],
)
def test_complete_body_file_forms_are_allowed(command: str) -> None:
    assert gh_body_guard.denial(command) is None


@pytest.mark.parametrize(
    "command",
    [
        "gh issue comment 675 --body-template template.md",
        "gh issue close 675 --comment-template template.md",
        "gh issue close 675 --commentary template.md",
        "gh issue comment 675 --body-from-stdin",
        "gh issue comment 675 -Z body",
    ],
)
def test_unknown_body_options_are_refused_fail_closed(command: str) -> None:
    assert gh_body_guard.denial(command) == gh_body_guard.UNREADABLE


@pytest.mark.parametrize(
    "command",
    [
        "gh issue comment 675 --body",
        "gh issue comment 675 --body-file",
        "gh issue comment 675 --body-file=",
        "gh issue close 675 --comment",
        "gh issue close 675 --comment-file",
        "gh issue close 675 --comment-file=",
        "gh issue comment 675 -F",
        "gh issue comment 675 -F=",
        'gh issue comment 675 --body "unterminated',
    ],
)
def test_incomplete_body_commands_are_refused_fail_closed(command: str) -> None:
    assert gh_body_guard.denial(command) == gh_body_guard.UNREADABLE


def test_inline_body_wins_over_a_file_backed_body_option() -> None:
    command = "gh issue comment 675 --body-file comment.md --body inline"
    assert gh_body_guard.denial(command) == gh_body_guard.INLINE_BODY


def test_comment_output_option_is_not_a_body_option() -> None:
    assert gh_body_guard.denial("gh issue view 675 --comments") is None


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


@pytest.mark.parametrize(
    "command",
    [
        "env --unknown gh issue comment 675 --body-file comment.md",
        "command --unknown gh issue comment 675 --body-file comment.md",
        "exec --unknown gh issue comment 675 --body-file comment.md",
    ],
)
def test_unreadable_known_wrappers_are_refused(command: str) -> None:
    assert gh_body_guard.denial(command) == gh_body_guard.UNREADABLE


def test_a_gh_phrase_inside_another_command_is_not_an_invocation() -> None:
    assert gh_body_guard.denial('printf "%s" "gh issue comment --body prose"') is None


def test_hook_fixture_reconstructs_the_committed_hook(tmp_path: Path) -> None:
    """The reserved hook's external integration diff rebuilds its intended bytes."""
    _scratch, target, baseline = stage_integrated_hook(tmp_path)

    expected = baseline.replace(
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


def test_integrated_hook_refuses_inline_body_with_file_remedy(tmp_path: Path) -> None:
    """The fixture-applied hook refuses inline bodies at the Bash entry point."""
    scratch, _target, _baseline = stage_integrated_hook(tmp_path)
    done = run_integrated_hook(
        scratch,
        'gh issue comment 168 -b "never sed -i tests/specs/campaign.yaml by hand"',
    )
    assert done.returncode == 2
    assert "--body-file" in done.stderr


def test_integrated_hook_allows_a_complete_body_file_at_the_bash_entry_point(
    tmp_path: Path,
) -> None:
    """The fixture-applied hook lets a complete file-backed body through."""
    scratch, _target, _baseline = stage_integrated_hook(tmp_path)
    done = run_integrated_hook(scratch, "gh issue comment 168 --body-file comment.md")
    assert done.returncode == 0, done.stderr
