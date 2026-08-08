"""Tests for the dispatched-session background guard (#279).

A dispatched session is single-shot: run_in_background ends the turn with no
second turn to read the completion. This hook refuses only backgrounding inside
a dispatched session -- never waiting, which is what #218 sanctioned a dispatched
session to hold -- and leaves the orchestrator and an ordinary subagent entirely
alone.
"""

from __future__ import annotations

import io
import json
import subprocess
from typing import TYPE_CHECKING

from conftest import REPO, load_hook

if TYPE_CHECKING:
    import pytest

hook = load_hook("deny-dispatched-background")

AGENT = "agent_01ABCdefGHIjklMNOpqrST"
MARKER = "CTI_DISPATCH_ID"


def call(monkeypatch: pytest.MonkeyPatch, stdin: str) -> int:
    """Run the hook's stdin contract and return the exit code it would use."""
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    return hook.main()


def event(command: str = "just fast", *, agent: str | None = None, background: bool = False) -> str:
    """Build the hook input for one Bash call."""
    tool_input: dict[str, object] = {"command": command}
    if background:
        tool_input["run_in_background"] = True
    data: dict[str, object] = {"tool_name": "Bash", "tool_input": tool_input}
    if agent is not None:
        data["agent_id"] = agent
    return json.dumps(data)


# --- should_deny: every combination of the three sessions ---------------------


def test_a_dispatched_session_backgrounding_is_denied() -> None:
    assert hook.should_deny(dispatched=True, agent=None, background=True)


def test_a_dispatched_session_foreground_is_allowed() -> None:
    assert not hook.should_deny(dispatched=True, agent=None, background=False)


def test_the_orchestrator_may_background() -> None:
    assert not hook.should_deny(dispatched=False, agent=None, background=True)


def test_a_subagent_keeps_its_behaviour_even_inside_a_dispatch() -> None:
    assert not hook.should_deny(dispatched=True, agent=AGENT, background=True)


# --- main: the marker gate, both directions ----------------------------------


def test_backgrounding_in_a_dispatched_session_is_denied(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(MARKER, "d-20260808-070905-da0b28")
    assert call(monkeypatch, event(background=True)) == 2
    assert "foreground" in capsys.readouterr().err


def test_a_known_long_gate_in_the_foreground_is_allowed_in_a_dispatched_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#218's sanctioned waiter: a foreground just regress passes both hooks."""
    monkeypatch.setenv(MARKER, "d-x")
    assert call(monkeypatch, event("just regress", background=False)) == 0


def test_backgrounding_without_the_marker_is_the_orchestrator_and_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(MARKER, raising=False)
    assert call(monkeypatch, event(background=True)) == 0


def test_a_subagent_backgrounding_passes_even_with_the_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(MARKER, "d-x")
    assert call(monkeypatch, event(background=True, agent=AGENT)) == 0


# --- fail closed, inside a dispatched session only (#41/#94) ------------------


def test_an_unreadable_payload_in_a_dispatched_session_is_denied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(MARKER, "d-x")
    assert call(monkeypatch, "not json") == 2


def test_an_unreadable_payload_outside_a_dispatched_session_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The orchestrator keeps its backgrounding; unreadable there is not this hook's concern."""
    monkeypatch.delenv(MARKER, raising=False)
    assert call(monkeypatch, "not json") == 0


def test_a_non_object_payload_in_a_dispatched_session_is_denied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(MARKER, "d-x")
    assert call(monkeypatch, '["just", "fast"]') == 2


# --- the Codex inert direction (criterion 6) ----------------------------------


def test_a_codex_shaped_payload_with_no_background_field_is_inert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codex's captured Bash payload carries no `run_in_background` field.

    With the marker set it still passes, which is the family-specific boundary
    rather than a parity claim.
    """
    monkeypatch.setenv(MARKER, "d-x")
    codex = json.dumps({"tool_name": "Bash", "tool_input": {"command": "just fast"}})
    assert call(monkeypatch, codex) == 0


# --- the wiring (#168, #183) --------------------------------------------------


def wired_commands() -> list[str]:
    settings = json.loads((REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))
    return [
        wired["command"]
        for entry in settings["hooks"]["PreToolUse"]
        for wired in entry["hooks"]
        if "deny-dispatched-background" in wired["command"]
    ]


def test_the_hook_is_wired_on_bash_once() -> None:
    assert len(wired_commands()) == 1


def test_the_wiring_denies_when_the_interpreter_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(MARKER, "d-x")
    for command in wired_commands():
        completed = subprocess.run(  # noqa: S603 - repo's own settings.json wiring, verbatim
            ["/bin/sh", "-c", command],
            input=event(background=True),
            env={"PATH": "/nonexistent", MARKER: "d-x", "CLAUDE_PROJECT_DIR": str(REPO)},
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        assert completed.returncode == 2
