"""Tests for the commit-hook bypass guard, `.claude/hooks/block-no-verify.py`.

The hook exists to stop the bypass being *run*. Its whole difficulty is telling
a command position from prose, so that is what these tests pin: the three
reproductions from #120 that were wrongly denied, and every spelling of the real
bypass that must still be denied. Anything the hook cannot read is denied — the
fail-safe direction is the one the hook was already right about.
"""

from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING

from conftest import load_hook

if TYPE_CHECKING:
    import pytest

hook = load_hook("block-no-verify")

FLAG = "--no-verify"
BYPASS = f"git commit {FLAG}"


def call(monkeypatch: pytest.MonkeyPatch, stdin: str) -> int:
    """Run the hook's stdin contract and return the exit code it would use."""
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    return hook.main()


# --- #120: prose about the rule is not a use of it --------------------------


def test_a_heredoc_body_quoting_the_phrase_is_not_a_bypass() -> None:
    """Reproduction 1 (2026-07-30 retro): the blocked phrase inside heredoc text."""
    command = f"cat > docs/note.md <<'EOF'\nAgents must never run {BYPASS}.\nEOF"
    assert not hook.blocks(command)


def test_an_issue_comment_body_quoting_the_flag_is_not_a_bypass() -> None:
    """Reproduction 2 (2026-08-02 review burn-down): the flag as prose in --body."""
    command = f'gh issue comment 120 --body "The hook denies `{BYPASS}` in prose."'
    assert not hook.blocks(command)


def test_an_issue_body_naming_the_flag_over_several_lines_is_not_a_bypass() -> None:
    """Reproduction 3: filing #120 itself was denied by its own subject matter."""
    command = (
        'gh issue create --title "hook denies prose" --body "The hook matches\n'
        f"git ... commit plus {FLAG} anywhere in the command string, so it cannot\n"
        'tell a command position from quoted text."'
    )
    assert not hook.blocks(command)


def test_an_escaped_quote_inside_a_body_does_not_confuse_the_reader() -> None:
    command = f'gh issue comment 120 --body "it says \\"{FLAG}\\" in prose"'
    assert not hook.blocks(command)


def test_a_shell_comment_about_the_flag_is_not_a_bypass() -> None:
    assert not hook.blocks(f"# never run {BYPASS}\ngit status")


def test_a_heredoc_body_is_prose_even_when_it_reads_as_a_command() -> None:
    command = f"cat <<'EOF' >> README.md\n{BYPASS} -m 'wip'\nEOF\ngit status"
    assert not hook.blocks(command)


def test_an_ordinary_commit_is_not_a_bypass() -> None:
    assert not hook.blocks('git commit -m "feat: put one side under a Commander"')


def test_a_commit_message_may_mention_the_flag() -> None:
    assert not hook.blocks(f'git commit -m "fix: stop denying prose that says {FLAG}"')


# --- the real bypass, in every spelling -------------------------------------


def test_the_bare_flag_is_denied() -> None:
    assert hook.blocks(BYPASS)


def test_the_short_flag_is_denied() -> None:
    assert hook.blocks("git commit -n")


def test_a_short_flag_cluster_is_denied() -> None:
    assert hook.blocks('git commit -an -m "wip"')


def test_the_flag_after_the_message_is_denied() -> None:
    assert hook.blocks(f'git commit -m "wip" {FLAG}')


def test_the_flag_before_the_subcommand_is_denied() -> None:
    assert hook.blocks(f"git -C /tmp/repo commit {FLAG}")


def test_a_chained_command_is_denied() -> None:
    assert hook.blocks(f"cd addons/main && {BYPASS} -m 'wip'")


def test_a_bypass_on_a_later_line_is_denied() -> None:
    assert hook.blocks(f"git add -A\n{BYPASS}")


def test_a_bypass_split_across_a_line_continuation_is_denied() -> None:
    assert hook.blocks(f"git commit \\\n  {FLAG} -m 'wip'")


def test_a_bypass_after_a_comment_is_denied() -> None:
    assert hook.blocks(f"# stage everything\ngit add -A ; {BYPASS}")


def test_a_bypass_after_a_heredoc_body_is_denied() -> None:
    assert hook.blocks(f"cat <<'EOF' > note.md\nsome prose\nEOF\n{BYPASS}")


def test_a_quoted_flag_is_still_a_flag() -> None:
    assert hook.blocks(f"git commit '{FLAG}'")


def test_the_flag_with_a_value_is_denied() -> None:
    assert hook.blocks(f"git commit {FLAG}=true")


def test_an_absolute_path_to_git_is_denied() -> None:
    assert hook.blocks(f"/usr/bin/git commit {FLAG}")


def test_an_environment_prefix_does_not_hide_the_command() -> None:
    assert hook.blocks(f"GIT_EDITOR=true git commit {FLAG}")


def test_a_command_substitution_is_denied() -> None:
    assert hook.blocks(f"echo $({BYPASS})")


# --- uncertainty is denied --------------------------------------------------


def test_an_unbalanced_quote_is_denied() -> None:
    assert hook.blocks("git status 'unclosed")


def test_an_unterminated_heredoc_is_denied() -> None:
    assert hook.blocks("cat <<'EOF' > note.md\nno end marker follows")


def test_a_heredoc_whose_end_cannot_be_named_is_denied() -> None:
    assert hook.blocks("cat << $DELIM\nbody\n")


# --- the stdin contract (#94 finding 2: it used to fail open) ---------------


def test_a_denied_command_exits_two_and_says_why(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert call(monkeypatch, json.dumps({"tool_input": {"command": BYPASS}})) == 2
    assert "ADR-0010" in capsys.readouterr().err


def test_an_allowed_command_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    assert call(monkeypatch, json.dumps({"tool_input": {"command": "git status"}})) == 0


def test_a_call_without_a_command_is_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    assert call(monkeypatch, json.dumps({"tool_input": {}})) == 2


def test_unreadable_stdin_is_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    assert call(monkeypatch, "not json") == 2
