#!/usr/bin/env python3
"""PreToolUse hook (Bash): refuse backgrounding work inside a dispatched session.

A dispatched session is single-shot: it has no second turn for a background
completion or a question (#279). This guard is the mechanical half for the
backgrounding shape: when CTI_DISPATCH_ID is in the environment -- which
tools/dispatch.py's assemble_environment sets for every dispatch -- a Bash call
with run_in_background is refused, and the agent is told to run the awaited work
in the foreground instead.

This is NOT the subagent long-wait denial, and conflating them is the trap.
deny-subagent-waits sanctions run_in_background for an ordinary subagent, whose
parent reads the result. A dispatched session has no parent reading -- a detached
claude -p is a top-level session, and the completion notification has nowhere to
land. But a dispatched session IS #218's sanctioned waiter: holding a long
foreground wait is what it was dispatched for, and deny-subagent-waits returns 0
for it (no agent_id). This hook refuses only backgrounding, never waiting. That
distinction is in the denial message so an agent that meets it knows which way
to go.

The marker, and the three sessions it separates. Hook input carries no lane
field and carries agent_id only inside an Agent-tool subagent. The environment
is what tells them apart:

* the orchestrator has no CTI_DISPATCH_ID and no agent_id -- it backgrounds
  freely, which is what drives the dispatch edge;
* an ordinary Agent-tool subagent has agent_id and may inherit CTI_DISPATCH_ID
  from a session dispatched around it -- it keeps its current behaviour, governed
  by deny-subagent-waits, and this hook returns 0 for it;
* a dispatched top-level session has CTI_DISPATCH_ID and no agent_id -- and this
  is the one a backgrounded completion cannot wake.

Codex is inert here, not a claimed parity. tools/hook_parity.py carries this
hook onto the Codex lane, so it runs there too, and CTI_DISPATCH_ID is set for a
Codex dispatch as well. But the Bash payload Codex 0.146.1 sends (codex-lane-
live-findings.md §4, mirrored in test_hook_parity.py's codex_payload) carries
tool_input with a command and no run_in_background field, and codex exec is
non-interactive by construction. So the guard returns 0 on Codex because the
field it reads is absent -- the family-specific boundary, stated, not a false
claim that Codex background work is covered.

Fail-closed, per #41/#94: a call that cannot be read is not a call that passed,
and PreToolUse reads any exit other than 2 as approval. This file returns 2
rather than 0 on anything it could not read inside a dispatched session; outside
one an unreadable payload is the other Bash hooks' concern.
"""

from __future__ import annotations

import json
import os
import sys

DISPATCH_MARKER = "CTI_DISPATCH_ID"

DENIAL = (
    "This Bash call is marked run_in_background inside a dispatched session (env "
    f"{DISPATCH_MARKER} is set), and a dispatched session is single-shot: it has no second"
    " turn, so the background completion's notification would never be read and the work it"
    " was running would end the turn uncommitted.\n"
    "Run the awaited work in the foreground. This refuses only backgrounding, never"
    " waiting: holding a long foreground wait is exactly what a dispatched session is for"
    " (#218), and a session with no agent_id is left alone by deny-subagent-waits. If you"
    " also asked a question, decide it yourself or finish the unambiguous part and state"
    " what remains -- no caller is listening for an answer."
)

UNREADABLE = (
    "Could not read this Bash call to check it for background work inside a dispatched"
    " session. Simplify the quoting and retry."
)


def is_dispatched() -> bool:
    """Whether this hook is running inside a dispatched session."""
    return bool(os.environ.get(DISPATCH_MARKER, "").strip())


def should_deny(*, dispatched: bool, agent: object, background: bool) -> bool:
    """Whether a Bash call's backgrounding is refused, given the session it runs in.

    Pure, so the unit tier covers every (dispatched, subagent, background)
    combination without spawning the hook. The orchestrator and an ordinary
    subagent both pass; only a dispatched top-level session is refused a
    backgrounded completion.
    """
    if isinstance(agent, str) and agent.strip():
        return False  # a subagent: deny-subagent-waits governs it and sanctions backgrounding
    if not dispatched:
        return False  # the orchestrator: backgrounding drives its completion edge
    return background


def main() -> int:
    """Read the tool call on stdin and refuse backgrounding in a dispatched session."""
    dispatched = is_dispatched()
    try:
        data = json.load(sys.stdin)
        agent = data.get("agent_id") if isinstance(data, dict) else None
        tool_input = data["tool_input"]
        background = bool(tool_input.get("run_in_background"))
    except (json.JSONDecodeError, TypeError, KeyError, AttributeError, ValueError):
        # Fail closed inside a dispatched session only (#41/#94). Outside one, the
        # orchestrator keeps its backgrounding and the other Bash hooks own unreadable
        # payloads there.
        if dispatched:
            print(UNREADABLE, file=sys.stderr)
            return 2
        return 0
    if should_deny(dispatched=dispatched, agent=agent, background=background):
        print(DENIAL, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
