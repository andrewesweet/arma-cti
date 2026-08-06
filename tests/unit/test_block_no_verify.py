"""Tests for the commit-hook bypass guard, `.claude/hooks/block-no-verify.py`.

The hook exists to stop the bypass being *run*. Its whole difficulty is telling
a command position from prose, so that is what these tests pin: the three
reproductions from #120 that were wrongly denied, and every spelling of the real
bypass that must still be denied. Anything the hook cannot read is denied — the
fail-safe direction is the one the hook was already right about.

What the hook *says* when it denies is pinned here too, because #254 is what a
denial that named the wrong finding cost. Three commands were reported as
false positives of the bypass pattern; all three were the unreadable branch of
a stale worktree copy of the pre-#167 hook (ADR-0042), wearing the ADR-0010
bypass accusation. The accusation is what made the diagnosis wrong, so the two
findings now carry two messages and each is asserted on.
"""

from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING

from conftest import REPO, load_hook

if TYPE_CHECKING:
    import pytest

hook = load_hook("block-no-verify")

FLAG = "--no-verify"
BYPASS = f"git commit {FLAG}"

# The three commands #254 reported, vendored verbatim from the transcripts that
# were denied. They are the shapes agents really write long bodies in, and the
# class has now been reintroduced twice (#120, #167) and misdiagnosed once.
SIGHTINGS = REPO / "tests" / "fixtures" / "block-no-verify"


def sighting(name: str) -> str:
    """One vendored command, as the Bash tool received it.

    The file carries a trailing newline the tool call did not; nothing else
    about it is edited.
    """
    return (SIGHTINGS / name).read_text(encoding="utf-8").rstrip("\n")


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


# --- #167: the same class again, in the shape agents really write bodies in ---


def commented(prose: str) -> str:
    """Build the shape a review agent posts a body in: heredoc inside `"$(...)"`."""
    return f"gh issue comment 167 --body \"$(cat <<'EOF'\n{prose}\nEOF\n)\""


def test_a_heredoc_inside_a_quoted_substitution_is_still_prose() -> None:
    """Reproduction 4 (2026-08-03 Clean Architecture review), post-#120-rewrite.

    A heredoc opened inside `"$(...)"` was not seen as a heredoc, so its body was
    parsed as shell; the stray `"` in the prose then put the code span that
    follows it in command position.
    """
    assert not hook.blocks(commented(f'The reviewer wrote "the flag `{BYPASS}` is prose here.'))


def test_such_a_body_naming_neither_the_flag_nor_a_commit_is_not_a_bypass() -> None:
    """The live denial that reopened this: the body mentions no git command at all.

    The pre-fix hook could not read the command — the heredoc opened inside
    `"$(...)"` went unseen, the body's lone `"` unbalanced the quoting, and
    `_shell_code` returned `None`. Denial then came from the fail-safe path
    rather than from any match, so nothing in the text had to resemble the
    bypass for a plain review comment to be blocked.
    """
    assert not hook.blocks(
        commented(
            "The reviewer's note said \"the guard is fail-safe here.\n"
            "Nothing in this paragraph is a command at all."
        )
    )


def test_an_odd_quote_in_such_a_body_does_not_leak_into_command_position() -> None:
    assert not hook.blocks(
        commented(
            f'The hook printed "Bypassing the commit-msg hook is blocked.\n'
            f"Nothing in this body is a {BYPASS} invocation."
        )
    )


def test_an_apostrophe_in_such_a_body_is_not_an_unbalanced_quote() -> None:
    assert not hook.blocks(
        commented(f"It said \"blocked and the agent's command carried {FLAG} as text.")
    )


def test_a_substitution_inside_a_body_is_still_a_command_position() -> None:
    """The context stack must not become a licence: `"$(...)"` really does run."""
    assert hook.blocks(f'gh issue comment 167 --body "$({BYPASS} -m wip)"')


def test_an_unclosed_substitution_is_denied() -> None:
    assert hook.blocks('gh issue comment 167 --body "$(cat notes.md"')


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


# --- #254: the three sightings, verbatim ------------------------------------


def test_the_241_commit_body_is_not_a_bypass() -> None:
    """Sighting 1: a `git commit -m "$(cat <<'EOF' … )"` whose body is English.

    Reported as the short-flag pattern matching `line-anchored` and
    `ready-for-agent`. It was not: the reader that denied it was a stale copy
    predating #167, which could not see a heredoc opened inside a quoted
    substitution and so failed to read the command at all.
    """
    assert not hook.blocks(sighting("241-commit-with-a-heredoc-body.txt"))


def test_the_245_comment_body_is_not_a_bypass() -> None:
    """Sighting 2: `gh issue comment --body "$(cat <<'EOF' … )"`, 4.7 kB of prose."""
    assert not hook.blocks(sighting("245-issue-comment-with-a-heredoc-body.txt"))


def test_the_249_close_comment_is_not_a_bypass() -> None:
    """Sighting 3: `gh issue close --comment "$(cat <<'EOF' … )"` — not a git command."""
    assert not hook.blocks(sighting("249-issue-close-with-a-heredoc-comment.txt"))


def test_a_hyphenated_word_is_not_a_short_flag_cluster() -> None:
    """The pattern #254 named: `-anchored` and `-agent` matched `-[A-Za-z]*n[A-Za-z]*`.

    A cluster is a cluster only when every letter in it is one git commit takes.
    Post-#167 the reader keeps prose out of argument position, so this is the
    pattern's own contract rather than a live reproduction — and the pattern is
    what the reader falls back on each time that guarantee has broken.
    """
    assert not hook.blocks("git commit -m wip -anchored")
    assert not hook.blocks("git commit -m wip -agent")
    assert not hook.blocks("git commit -m wip -brand")


# --- the real bypass, in every spelling -------------------------------------


def test_the_bare_flag_is_denied() -> None:
    assert hook.blocks(BYPASS)


def test_the_short_flag_is_denied() -> None:
    assert hook.blocks("git commit -n")


def test_a_short_flag_cluster_is_denied() -> None:
    assert hook.blocks('git commit -an -m "wip"')


def test_every_cluster_of_git_commits_own_short_options_is_denied() -> None:
    """The under-blocking edge of #254's tightening, in both orders and at length."""
    assert hook.blocks("git commit -anv")
    assert hook.blocks("git commit -vna")
    assert hook.blocks("git commit -nqse")
    assert hook.blocks("git commit -ion")
    assert hook.blocks("git commit -nF /tmp/msg.txt")


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


def test_an_unreadable_command_is_not_accused_of_a_bypass(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """#254 sighting 3: a parse failure on a non-git command cited ADR-0010.

    The command is the one that was denied — a `git commit -F -` whose heredoc
    body never arrived — but the shape is the general one, and what it is not
    allowed to say is the point: nothing in it bypasses anything.
    """
    truncated = "git add -A && git commit -q -F - <<'EOF' && git log --oneline -3"
    assert call(monkeypatch, json.dumps({"tool_input": {"command": truncated}})) == 2
    said = capsys.readouterr().err
    assert "ADR-0010" not in said
    assert "Bypassing" not in said


def test_an_unreadable_command_is_told_what_happened_and_what_to_do(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The denial names the reading failure and the two file-shaped remedies (#254)."""
    assert call(monkeypatch, json.dumps({"tool_input": {"command": "gh issue view 'x"}})) == 2
    said = capsys.readouterr().err
    assert "could not be read" in said
    assert "--body-file" in said
    assert "git commit -F" in said


def test_a_real_bypass_still_names_the_gate_it_defeats(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The two findings stay two messages: the accusation belongs to this one only."""
    assert call(monkeypatch, json.dumps({"tool_input": {"command": BYPASS}})) == 2
    said = capsys.readouterr().err
    assert "ADR-0010" in said
    assert "--body-file" not in said


def test_an_allowed_command_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    assert call(monkeypatch, json.dumps({"tool_input": {"command": "git status"}})) == 0


def test_a_call_without_a_command_is_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    assert call(monkeypatch, json.dumps({"tool_input": {}})) == 2


def test_unreadable_stdin_is_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    assert call(monkeypatch, "not json") == 2
