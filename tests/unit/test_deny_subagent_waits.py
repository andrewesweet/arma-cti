"""Tests for the subagent wait guard, `.claude/hooks/deny-subagent-waits.py`.

The hook denies a turn-blocking wait inside a subagent's turn, because an agent
that has ended cannot stall — #218's A/B retired the token arithmetic the rule
used to be argued from and left the stall record standing. Three things need
pinning, and #120's lesson — that an over-eager hook costs more than the rule it
guards — is why the second and third get as many tests as the first:

* the wait shapes are denied, in every spelling, and the denial names the four
  sanctioned routes and argues from the stall record rather than a retired price;
* the known-long gates are denied (#204's decision 6), and the selections that
  are not foreseeably long pass;
* what is *not* the target passes: a bounded short sleep, a fast gate recipe, a
  `for` loop, and any of them written as prose;
* the gate. The orchestrator is on the one-hour TTL and is left entirely alone,
  and everything the hook cannot read is denied (#41, #94).
"""

from __future__ import annotations

import io
import json
import os
import subprocess
from typing import TYPE_CHECKING

from conftest import REPO, load_hook

if TYPE_CHECKING:
    from collections.abc import Iterable

    import pytest

hook = load_hook("deny-subagent-waits")

AGENT = "agent_01ABCdefGHIjklMNOpqrST"


def call(monkeypatch: pytest.MonkeyPatch, stdin: str) -> int:
    """Run the hook's stdin contract and return the exit code it would use."""
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    return hook.main()


def event(command: str, *, agent: str | None = AGENT, background: bool = False) -> str:
    """Build the hook input for one Bash call, from a subagent unless told otherwise."""
    tool_input: dict[str, object] = {"command": command}
    if background:
        tool_input["run_in_background"] = True
    data: dict[str, object] = {"tool_name": "Bash", "tool_input": tool_input}
    if agent is not None:
        data["agent_id"] = agent
        data["agent_type"] = "general-purpose"
    return json.dumps(data)


def wired_commands() -> Iterable[str]:
    """Every `.claude/settings.json` PreToolUse entry that runs this hook."""
    settings = json.loads((REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))
    return [
        wired["command"]
        for entry in settings["hooks"]["PreToolUse"]
        for wired in entry["hooks"]
        if "deny-subagent-waits" in wired["command"]
    ]


# --- the wait shapes are denied ---------------------------------------------


def test_a_long_bare_sleep_is_denied() -> None:
    """#205's headline acceptance criterion."""
    assert hook.denial("sleep 600") is not None


def test_the_denial_names_the_watcher_and_the_end_before_wait_pattern() -> None:
    reason = hook.denial("sleep 600")
    assert reason is not None
    assert "just watch" in reason
    assert "end this turn" in reason
    assert "run_in_background" in reason


def test_the_denial_argues_from_the_stall_record_not_the_superseded_token_price() -> None:
    """#218's decision 4: the A/B priced that argument at ~0.0015 plan points.

    A denial that argues from a superseded cost model teaches the wrong model to every
    agent it denies, and denials are read at the moment of the decision.
    """
    reason = hook.denial("sleep 600")
    assert reason is not None
    assert "stall" in reason
    assert "201,000" not in reason
    assert "input-equivalents" not in reason


def test_the_denial_offers_the_dispatched_session_with_its_condition() -> None:
    """#218 sanctioned the session fallback; a session nobody watches is not the shape."""
    reason = hook.denial("sleep 600")
    assert reason is not None
    assert "just dispatch" in reason
    assert "claude-native" in reason
    assert "just watch" in reason


def test_the_denial_says_who_may_wait_and_who_may_not() -> None:
    """A dispatched session may hold a wait too, so the one-hour sentence gains a clause."""
    reason = hook.denial("sleep 600")
    assert reason is not None
    assert "orchestrator" in reason
    assert "session" in reason
    assert "subagent" in reason


def test_the_threshold_is_unchanged_at_the_ttl() -> None:
    """#218 moved the stated reason and kept the number, explicitly and for two reasons."""
    assert hook.THRESHOLD == 240


def test_the_corpus_denial_keeps_its_measured_p90() -> None:
    """That figure is a duration, and it is still true."""
    assert "1,230" in hook.CORPUS_DENIAL


def test_a_sleep_exactly_at_the_threshold_is_denied() -> None:
    assert hook.denial(f"sleep {hook.THRESHOLD}") is not None


def test_a_sleep_in_minutes_is_denied() -> None:
    assert hook.denial("sleep 10m") is not None


def test_a_sleep_in_hours_is_denied() -> None:
    assert hook.denial("sleep 1h") is not None


def test_a_fractional_sleep_over_the_threshold_is_denied() -> None:
    assert hook.denial("sleep 0.5h") is not None


def test_summed_operands_over_the_threshold_are_denied() -> None:
    """GNU sleep sums its operands, so three minutes twice is six."""
    assert hook.denial("sleep 3m 3m") is not None


def test_a_long_sleep_behind_a_chain_is_denied() -> None:
    assert hook.denial("just build && sleep 900 && just verdict") is not None


def test_a_long_sleep_on_a_later_line_is_denied() -> None:
    assert hook.denial("just regress --slots 3\nsleep 600") is not None


def test_an_absolute_path_to_sleep_is_denied() -> None:
    assert hook.denial("/bin/sleep 600") is not None


def test_an_unreadable_duration_is_denied() -> None:
    """An operand the reader cannot resolve is an unbounded wait, not a short one."""
    assert hook.denial("sleep $WAIT") is not None


def test_the_unreadable_duration_denial_says_so() -> None:
    reason = hook.denial('sleep "$interval"')
    assert reason is not None
    assert "unreadable duration" in reason


def test_an_until_poll_loop_is_denied() -> None:
    assert hook.denial("until [ -f /tmp/done ]; do sleep 10; done") is not None


def test_a_while_true_poll_loop_is_denied() -> None:
    assert hook.denial("while true; do sleep 30; just watch-report; done") is not None


def test_a_while_loop_polling_a_condition_is_denied() -> None:
    """#205 widens #203's two spellings: this is an `until` loop written backwards."""
    assert hook.denial("while ! nc -z localhost 2402; do sleep 1; done") is not None


def test_a_poll_loop_is_denied_however_short_its_sleep() -> None:
    """A poll loop's wait is set by its condition, not by its number."""
    assert hook.denial("until test -e /tmp/verdict.json; do sleep 0.5; done") is not None


def test_the_poll_loop_denial_names_the_shape() -> None:
    reason = hook.denial("until test -e /tmp/done; do sleep 5; done")
    assert reason is not None
    assert "poll loop" in reason
    assert "just watch" in reason


def test_a_poll_loop_written_over_several_lines_is_denied() -> None:
    assert hook.denial("until just verdict\ndo\n  sleep 20\ndone") is not None


def test_a_time_prefixed_poll_loop_is_denied() -> None:
    assert hook.denial("time while true; do sleep 5; done") is not None


def test_a_hand_counted_while_loop_is_denied_as_a_poll_loop() -> None:
    """A stated over-block: the shape is a poll and the fix is the same one."""
    assert hook.denial("i=0; while [ $i -lt 3 ]; do sleep 1; i=$((i+1)); done") is not None


def test_a_backgrounded_long_sleep_is_denied() -> None:
    """A stated over-block: the reader does not say which separator followed a segment.

    `run_in_background` is the shape that means a detached wait, and it passes —
    see the gate tests below.
    """
    assert hook.denial("sleep 600 &") is not None


# --- the known-long gates are denied (#204, decision 6) ----------------------


def test_the_unfiltered_full_corpus_is_denied() -> None:
    """#204's decision 6: a gate with a measured p90 over five minutes."""
    assert hook.denial("just regress") is not None


def test_the_full_corpus_denial_names_the_detached_path() -> None:
    reason = hook.denial("just regress")
    assert reason is not None
    assert "run_in_background" in reason
    assert "just watch" in reason


def test_the_full_corpus_is_denied_however_many_slots() -> None:
    assert hook.denial("just regress --slots 3") is not None
    assert hook.denial("just regress --slots 1") is not None
    assert hook.denial("just regress --slots=3") is not None


def test_a_queued_full_corpus_is_denied() -> None:
    """`--wait` bounds the queue for a slot; it does not shorten the run."""
    assert hook.denial("just regress --wait 600 --slots 2") is not None


def test_the_full_corpus_behind_a_chain_is_denied() -> None:
    assert hook.denial("git rebase origin/main && just regress") is not None


def test_the_full_corpus_under_a_timeout_wrapper_is_denied() -> None:
    """The wrapper bounds the wait; it does not move it out of the turn."""
    assert hook.denial("timeout 1800 just regress --slots 3") is not None
    assert hook.denial("timeout -k 30 1800 just regress") is not None


def test_the_full_corpus_behind_a_just_flag_is_denied() -> None:
    """`just -f <path> regress` is the same run; the recipe name is not the first word."""
    assert hook.denial("just -f /repo/justfile -d /repo regress") is not None


def test_the_corpus_runner_called_directly_is_denied() -> None:
    """The recipe is a one-line wrapper over this script, so both spellings are the gate."""
    assert hook.denial("./spike/regress.sh --slots 3") is not None


def test_listing_the_selection_is_allowed() -> None:
    """`--list` runs nothing, takes no lock and needs no Arma — stated in #204's ruling."""
    assert hook.denial("just regress --list") is None
    assert hook.denial("just regress --list --issues 28") is None
    assert hook.denial("./spike/regress.sh --list") is None


def test_a_named_selection_is_allowed() -> None:
    """A named probe can finish in 25 s (`ai-reinforce`, #150/#191)."""
    assert hook.denial("just regress ai-reinforce") is None
    assert hook.denial("just regress --slots 3 ai-reinforce massed-assault") is None


def test_an_issue_filtered_selection_is_allowed() -> None:
    assert hook.denial("just regress --issues 28") is None
    assert hook.denial("just regress --issues=28,150") is None


def test_a_fast_gate_recipe_is_allowed() -> None:
    """#197 took `just fast` from 6:32 to 1:02, which is what keeps it off the list."""
    assert hook.denial("just fast") is None
    assert hook.denial("just unit") is None
    assert hook.denial("just check") is None


def test_a_timeout_wrapped_fast_gate_is_allowed() -> None:
    """The wrapper is a bound, not a wait, and the thing it bounds is under the TTL."""
    assert hook.denial("timeout 900 just fast") is None


def test_the_orchestrator_may_run_the_full_corpus(monkeypatch: pytest.MonkeyPatch) -> None:
    """The one-hour TTL: a ~20-minute pool in the orchestrator's turn is nearly free."""
    assert call(monkeypatch, event("just regress", agent=None)) == 0


def test_the_full_corpus_is_allowed_detached(monkeypatch: pytest.MonkeyPatch) -> None:
    """The remedy the denial names must itself pass."""
    assert call(monkeypatch, event("just regress --slots 3", background=True)) == 0


# --- what is not the target passes ------------------------------------------


def test_a_short_sleep_is_allowed() -> None:
    """#205's third acceptance criterion: `sleep 5` is permitted everywhere."""
    assert hook.denial("sleep 5") is None


def test_a_sub_second_sleep_in_a_fixture_is_allowed() -> None:
    assert hook.denial("sleep 0.2 && cat /tmp/daemon.log") is None


def test_a_sleep_just_under_the_threshold_is_allowed() -> None:
    assert hook.denial(f"sleep {hook.THRESHOLD - 1}") is None


def test_summed_operands_under_the_threshold_are_allowed() -> None:
    assert hook.denial("sleep 1m 30") is None


def test_an_unmeasured_recipe_is_allowed() -> None:
    """The list is measured p90s, not "recipes that might be slow": nothing else is on it."""
    assert hook.denial("just build") is None
    assert hook.denial("just probe spike/probes/contact-decay.sqf 300") is None


def test_arming_the_detached_watcher_is_allowed() -> None:
    """The hook must never deny the alternative it recommends."""
    assert hook.denial("just watch issue-205 .claude/worktrees/issue-205") is None


def test_a_for_loop_with_a_short_sleep_is_allowed() -> None:
    """Its iteration count is written in the command, so its total is inspectable."""
    assert hook.denial("for probe in a b c; do just probe $probe; sleep 2; done") is None


def test_a_while_read_loop_without_a_sleep_is_allowed() -> None:
    assert hook.denial("while read -r line; do echo $line; done < /tmp/verdicts") is None


def test_a_git_log_until_flag_is_not_a_loop() -> None:
    assert hook.denial("git log --until=2026-08-01 --oneline") is None


def test_the_word_sleep_as_an_argument_is_not_a_sleep() -> None:
    assert hook.denial("grep -rn sleep spike/probes/") is None


def test_prose_about_a_long_sleep_in_a_quoted_body_is_allowed() -> None:
    assert hook.denial('gh issue comment 205 --body "the hook denies sleep 600 now"') is None


def test_prose_about_a_poll_loop_in_a_heredoc_body_is_allowed() -> None:
    command = (
        "cat > /tmp/note.md <<'EOF'\n"
        "Never write `until test -e /tmp/done; do sleep 10; done` in a subagent.\n"
        "EOF"
    )
    assert hook.denial(command) is None


def test_a_poll_loop_written_into_a_script_file_is_allowed() -> None:
    """The hook reads the command, not the file it writes: a script is not this turn's wait."""
    command = (
        "cat > /tmp/wait.sh <<'SH'\n"
        "until [ -f /tmp/done ]; do sleep 30; done\n"
        "SH\n"
        "chmod +x /tmp/wait.sh"
    )
    assert hook.denial(command) is None


def test_an_ordinary_command_is_allowed() -> None:
    assert hook.denial("just fast") is None


# --- the subagent gate ------------------------------------------------------


def test_the_orchestrator_may_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    """#205's second acceptance criterion. No `agent_id` means the one-hour TTL."""
    assert call(monkeypatch, event("sleep 600", agent=None)) == 0


def test_the_orchestrator_may_run_a_poll_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    assert call(monkeypatch, event("until just verdict; do sleep 60; done", agent=None)) == 0


def test_an_empty_agent_id_is_read_as_the_orchestrator(monkeypatch: pytest.MonkeyPatch) -> None:
    assert call(monkeypatch, event("sleep 600", agent="")) == 0


def test_a_subagent_is_denied_and_told_why(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert call(monkeypatch, event("sleep 600")) == 2
    assert "just watch" in capsys.readouterr().err


def test_a_subagent_running_short_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    assert call(monkeypatch, event("sleep 5")) == 0


def test_a_detached_run_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """`run_in_background` holds no turn open, and is one of the sanctioned shapes."""
    assert call(monkeypatch, event("just regress --slots 3", background=True)) == 0


def test_even_a_long_sleep_is_allowed_detached(monkeypatch: pytest.MonkeyPatch) -> None:
    assert call(monkeypatch, event("sleep 600", background=True)) == 0


# --- the stdin contract fails closed (#41, #94) ------------------------------


def test_unreadable_stdin_is_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    assert call(monkeypatch, "not json") == 2


def test_a_non_object_payload_is_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    assert call(monkeypatch, '["sleep", "600"]') == 2


def test_a_subagent_call_without_a_command_is_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    assert call(monkeypatch, json.dumps({"agent_id": AGENT, "tool_input": {}})) == 2


def test_a_subagent_call_without_tool_input_is_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    assert call(monkeypatch, json.dumps({"agent_id": AGENT})) == 2


def test_an_unbalanced_quote_is_denied() -> None:
    assert hook.denial("echo 'unclosed") is not None


def test_an_unterminated_heredoc_is_denied() -> None:
    assert hook.denial("cat <<'EOF' > /tmp/note.md\nno end marker") is not None


# --- the wiring itself (#168, #183) -----------------------------------------


def test_the_hook_is_wired_on_bash_once() -> None:
    assert len(list(wired_commands())) == 1


def test_the_wiring_denies_when_the_interpreter_is_missing() -> None:
    """A missing python3 must deny, and only exit 2 blocks a PreToolUse hook.

    A bare `python3 hook.py` exits 127 with no interpreter on PATH, Claude Code
    reads any exit other than 2 as non-blocking, and the wait runs — #168's
    finding, one layer further out than the hook's own code can reach. So the
    settings.json wiring maps every hook failure to 2, and this test runs that
    wiring, verbatim, with an empty PATH.
    """
    for command in wired_commands():
        completed = run_wiring(command, stdin="{}", path="/nonexistent")
        assert completed.returncode == 2


def test_the_wiring_still_permits_an_allowed_call() -> None:
    """The other direction of `|| exit 2`: it must not turn every call into a denial."""
    for command in wired_commands():
        completed = run_wiring(command, stdin=event("just fast"), path=os.environ["PATH"])
        assert completed.returncode == 0, completed.stderr


def test_the_wiring_denies_a_long_subagent_sleep() -> None:
    """End to end through the wiring: the shape #205 exists to stop."""
    for command in wired_commands():
        completed = run_wiring(command, stdin=event("sleep 600"), path=os.environ["PATH"])
        assert completed.returncode == 2
        assert "just watch" in completed.stderr


def test_the_wiring_denies_the_unfiltered_corpus_in_a_subagent() -> None:
    """End to end through the wiring: the shape #204's decision 6 exists to stop."""
    for command in wired_commands():
        completed = run_wiring(command, stdin=event("just regress"), path=os.environ["PATH"])
        assert completed.returncode == 2
        assert "run_in_background" in completed.stderr


def run_wiring(command: str, *, stdin: str, path: str) -> subprocess.CompletedProcess[str]:
    """Run one settings.json hook command verbatim under a chosen PATH."""
    # S603: the repo's own settings.json wiring, quoted verbatim.
    return subprocess.run(  # noqa: S603
        ["/bin/sh", "-c", command],
        input=stdin,
        env={"PATH": path, "CLAUDE_PROJECT_DIR": str(REPO)},
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
