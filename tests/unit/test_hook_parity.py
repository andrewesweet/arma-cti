"""ADR-0061 Decision 4's hook-parity suite for the Codex lane (#243).

Decision 4 makes a lane's authority the enforcement it demonstrably runs, and names the
way such a suite goes wrong: "the suite asserting on its own mock rather than the lane's
real denial path". So every denial test here runs the **actual committed hook script** as
a subprocess, feeds it the payload **Codex actually sends** — captured from a live Codex
turn, not invented — and asserts the exit code Codex actually reads as a denial.

What is proven elsewhere and relied on here, because a pytest cannot reach it: that Codex
honours exit code 2 by blocking the call. That is an in-world fact and it was measured in
world (#243, `docs/research/codex-lane-live-findings.md` §4): a probe hook returned 2 on
`echo blocked > TRIPWIRE.txt`, Codex logged "Command blocked by PreToolUse hook", and the
file did not exist afterwards. This suite proves the other half — that our scripts return
2 for the right payloads and 0 for the wrong ones — which is the half that can regress on
an ordinary edit.
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest
from conftest import REPO, load_tool

if TYPE_CHECKING:
    from pathlib import Path

hook_parity = load_tool("hook_parity")

HOOKS = REPO / ".claude" / "hooks"
SETTINGS = REPO / ".claude" / "settings.json"

# The denial Codex reads. Anything else — including 1 — is approval, on both harnesses.
DENY = 2


def codex_payload(tool_name: str, tool_input: dict[str, object]) -> str:
    """Build a PreToolUse payload in the shape Codex 0.146.1 sends.

    Every key is one a live Codex turn was observed to send (#243); none is invented.
    `tool_name` really is Claude Code's spelling on Codex too — the CLI reports `Bash`,
    not its internal `shell` — which is the single fact that lets our hooks run unedited.
    """
    return json.dumps(
        {
            "session_id": "019fd51b-835f-7732-8855-a73841a75d4c",
            "turn_id": "019fd51b-83ef-7353-857d-48fa291cb290",
            "transcript_path": "/home/andre/.codex/sessions/2026/08/06/rollout.jsonl",
            "cwd": str(REPO),
            "hook_event_name": "PreToolUse",
            "model": "gpt-5.6-terra",
            "permission_mode": "acceptEdits",
            "tool_name": tool_name,
            "tool_input": tool_input,
            "tool_use_id": "exec-ae6f66c0-b4d3-4d56-b153-bbb1ba2c5d16",
        }
    )


def run_hook(script: str, payload: str) -> subprocess.CompletedProcess[str]:
    """Run one committed hook script on a payload, exactly as a harness would."""
    return subprocess.run(  # noqa: S603 - argv is this repo's own hook script and a literal
        [sys.executable, str(HOOKS / script)],
        input=payload,
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO,
    )


class TestGatedPathsDenyOnCodexPayloads:
    """`protect-gated-paths.py` must refuse a gated write however Codex phrases it."""

    @pytest.mark.parametrize(
        ("tool_name", "tool_input"),
        [
            ("Write", {"file_path": "tests/specs/whatever.feature"}),
            ("Edit", {"file_path": "addons/generated/thing.hpp"}),
            ("Bash", {"command": "echo x > tests/specs/whatever.feature"}),
            ("Bash", {"command": "sed -i s/a/b/ addons/generated/thing.hpp"}),
        ],
    )
    def test_denies(self, tool_name: str, tool_input: dict[str, object]) -> None:
        """Deny a gated write however Codex phrases it."""
        done = run_hook("protect-gated-paths.py", codex_payload(tool_name, tool_input))
        assert done.returncode == DENY, done.stdout + done.stderr

    @pytest.mark.parametrize(
        ("tool_name", "tool_input"),
        [
            ("Write", {"file_path": "tools/dispatch.py"}),
            ("Bash", {"command": "cat tests/specs/whatever.feature"}),
        ],
    )
    def test_allows_what_is_not_a_gated_write(
        self, tool_name: str, tool_input: dict[str, object]
    ) -> None:
        """Let through what is not a write to a gated path."""
        done = run_hook("protect-gated-paths.py", codex_payload(tool_name, tool_input))
        assert done.returncode != DENY, done.stdout + done.stderr


class TestNoVerifyDeniesOnCodexPayloads:
    """`block-no-verify.py` must refuse a hook-skipping commit from the Codex lane too."""

    def test_denies_no_verify(self) -> None:
        """Refuse a hook-skipping commit from the Codex lane."""
        payload = codex_payload("Bash", {"command": "git commit --no-verify -m x"})
        done = run_hook("block-no-verify.py", payload)
        assert done.returncode == DENY, done.stdout + done.stderr

    def test_allows_an_ordinary_commit(self) -> None:
        """Let an ordinary commit through."""
        payload = codex_payload("Bash", {"command": "git commit -m x"})
        done = run_hook("block-no-verify.py", payload)
        assert done.returncode != DENY, done.stdout + done.stderr


class TestTranslation:
    """The `[hooks]` table handed to Codex must carry this repo's real enforcement."""

    def test_every_configured_command_is_carried(self) -> None:
        """Carry every configured hook command, dropping none."""
        settings = hook_parity.read_settings(SETTINGS)
        commands = hook_parity.hook_commands(settings, REPO)
        configured = sum(
            len(group["hooks"])
            for event in hook_parity.CARRIED_EVENTS
            for group in settings["hooks"].get(event, [])
        )
        assert len(commands) == configured
        assert configured > 0

    def test_project_dir_is_resolved_to_a_real_script(self) -> None:
        """Resolve the project-dir variable to scripts that exist."""
        translation = hook_parity.translate(hook_parity.read_settings(SETTINGS), REPO)
        assert hook_parity.PROJECT_DIR_VAR not in translation.toml
        assert translation.missing_scripts() == ()

    def test_a_missing_script_is_named(self, tmp_path: Path) -> None:
        """Name a hook script that is configured but absent."""
        settings = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [
                            {"type": "command", "command": 'python3 "$CLAUDE_PROJECT_DIR/nope.py"'}
                        ],
                    }
                ]
            }
        }
        translation = hook_parity.translate(settings, tmp_path)
        assert translation.missing_scripts() == (tmp_path / "nope.py",)

    def test_matcher_survives_translation(self) -> None:
        """Keep the matcher, which is what aims a hook at a tool."""
        settings = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Edit|Write",
                        "hooks": [{"type": "command", "command": "/bin/true"}],
                    }
                ]
            }
        }
        overrides = hook_parity.config_overrides(settings, REPO)
        assert len(overrides) == 1
        assert 'matcher = "Edit|Write"' in overrides[0]
        assert overrides[0].startswith("hooks.PreToolUse=[")

    def test_post_tool_use_is_carried_under_its_own_event(self) -> None:
        """Emit PostToolUse hooks under PostToolUse."""
        settings = {
            "hooks": {
                "PostToolUse": [
                    {"matcher": "Edit", "hooks": [{"type": "command", "command": "/bin/true"}]}
                ]
            }
        }
        overrides = hook_parity.config_overrides(settings, REPO)
        expected = (
            'hooks.PostToolUse=[{ matcher = "Edit", '
            'hooks = [{ type = "command", command = "/bin/true" }] }]'
        )
        assert overrides == (expected,)

    def test_a_group_with_no_matcher_emits_no_matcher_key(self) -> None:
        """Omit the matcher key when a group has none."""
        settings = {
            "hooks": {"PreToolUse": [{"hooks": [{"type": "command", "command": "/bin/x"}]}]}
        }
        overrides = hook_parity.config_overrides(settings, REPO)
        assert "matcher" not in overrides[0]

    def test_non_command_hook_types_are_dropped(self) -> None:
        """Drop a hook type Codex's command handler cannot run."""
        settings = {
            "hooks": {
                "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "prompt", "prompt": "hi"}]}]
            }
        }
        assert hook_parity.config_overrides(settings, REPO) == ()

    def test_an_uncarried_event_is_not_emitted(self) -> None:
        """Emit nothing for an event this repo does not carry."""
        settings = {
            "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "/bin/true"}]}]}
        }
        assert hook_parity.config_overrides(settings, REPO) == ()

    def test_quotes_in_a_command_are_escaped(self) -> None:
        """Escape quotes so the emitted TOML parses."""
        settings = {
            "hooks": {"PreToolUse": [{"hooks": [{"type": "command", "command": 'echo "hi"'}]}]}
        }
        overrides = hook_parity.config_overrides(settings, REPO)
        assert r"\"hi\"" in overrides[0]

    def test_settings_without_hooks_translate_to_nothing(self) -> None:
        """Translate hookless settings to no overrides."""
        assert hook_parity.config_overrides({}, REPO) == ()

    def test_script_is_none_for_a_command_that_is_not_a_python_call(self) -> None:
        """Return no script for a command that is not a python3 call."""
        command = hook_parity.HookCommand("PreToolUse", "Bash", "/usr/bin/env true")
        assert command.script() is None
