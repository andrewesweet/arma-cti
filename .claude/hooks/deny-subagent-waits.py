#!/usr/bin/env python3
"""PreToolUse hook (Bash): deny a turn-blocking wait inside a subagent's turn.

A subagent's prompt cache lives five minutes; the orchestrator's lives an hour.
#203 measured both on this project's own transcripts — 100% of 15,805 subagent
cache writes at the five-minute TTL against 100% of 2,907 main-session writes at
the one-hour one — and priced the difference: a subagent turn held open past the
TTL pays a mean 161,061 tokens to rebuild the prefix (201,326 input-equivalents)
where ending the turn and letting a successor start cold costs 24,554. The same
wait in the orchestrator is nearly free, so this hook must leave it alone.

**The gate.** Hook input carries `agent_id` only inside a subagent
(https://code.claude.com/docs/en/hooks.md, Common Input Fields). No `agent_id`
means the orchestrator, and the hook returns 0 without looking at the command.

**What is denied**, and only inside a subagent:

* a `sleep` asking for `THRESHOLD` seconds or more in total — GNU's `s`/`m`/`h`/`d`
  suffixes are honoured and multiple operands summed, and an operand that cannot
  be read counts as unbounded;
* a `while`/`until` loop whose command also runs a `sleep`, at any duration —
  a poll loop's wait is set by its condition, not by its number.

#205 widens the second rule past the `until` and `while true` spellings #203
counted (150 and 2 inside subagents), because `while ! nc -z localhost 2402; do
sleep 1; done` is an `until` loop written the other way round and blocks a turn
just the same.

**What is not the target, and passes on purpose.** The rule is the *turn-blocking
wait shape*, not the word `sleep`:

* a bounded short sleep — `sleep 5` in a fixture, `sleep 0.2` between two writes;
* a `timeout`-wrapped command: `timeout 900 just regress` is a bound, not a wait,
  and a recipe's runtime is not inspectable anyway. That half is the dispatch
  rule's (#204), not this hook's;
* a `for`/`select` loop with a short sleep — its iteration count is written in the
  command, so its total is inspectable, and the first rule sees it if it is long;
* the same shapes as prose. Heredoc bodies and quoted bodies are text, which the
  shared reader in `shell_reading.py` removes (its docstring carries the #120/#167
  history);
* anything the Bash tool is running detached (`run_in_background`), which does not
  hold the turn open at all and is one of the sanctioned alternatives.

**Deliberate over-blocks**, stated rather than discovered:

* a backgrounded `sleep 600 &` is denied with the foreground one, because the
  reader does not report which separator followed a segment. `run_in_background`
  is the shape that means it, and it passes.
* `sleep "$interval"` is denied: an operand the reader cannot resolve is unbounded.
* a `while`/`until` and a `sleep` in one command are read as one poll loop even
  when the sleep sits outside the loop body. The reader gives a flat list of
  commands, and a hook too clever to audit is worse than a blunt one.
* a hand-counted `while [ $i -lt 3 ]; do sleep 1; ...` is denied as a poll loop.

Fail-closed, per #41 and #94: a call that cannot be read is not a call that
passed, and PreToolUse reads any exit other than 2 as approval — so the
`.claude/settings.json` wiring maps every failure to 2 with `|| exit 2` (#168,
#183) and this file returns 2 rather than 0 on anything it could not read.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import PurePosixPath

from shell_reading import read_command, without_assignments

# Seconds. Long enough to leave the turn's own work headroom inside the
# five-minute TTL, short enough that nothing under it can cross the cliff alone.
THRESHOLD = 240

# GNU sleep: `NUMBER[SUFFIX]`, suffix s/m/h/d, several operands summed.
_DURATION = re.compile(r"(\d+(?:\.\d+)?|\.\d+)([smhd]?)\Z")
_SUFFIX_SECONDS = {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}

# Shell keywords that can precede a command word inside one reader segment.
_LEADING_KEYWORDS = frozenset(
    {
        "if",
        "then",
        "elif",
        "else",
        "fi",
        "while",
        "until",
        "do",
        "done",
        "for",
        "select",
        "time",
        "!",
        "{",
    }
)
_LOOP_KEYWORDS = frozenset({"while", "until"})

ALTERNATIVES = (
    "A subagent's prompt cache lives five minutes: a turn held open past it pays a"
    " measured ~201,000 input-equivalents to rebuild, against ~24,000 for a fresh"
    " agent to start cold (#203). Take one of these instead:\n"
    "  - end this turn now, reporting the SHA, the worktree and where the result"
    " will land, so a successor reads it cold and cheap;\n"
    "  - `just watch <name> <worktree>` to arm a detached watcher, then return;\n"
    "  - run the long thing with the Bash tool's run_in_background and let the"
    " notification wake you.\n"
    "The orchestrator is on the one-hour TTL and may wait; a subagent may not."
)

UNREADABLE = (
    "Could not read this Bash command to check it for a turn-blocking wait."
    " Simplify the quoting and retry."
)

LOOP_DENIAL = (
    "A `while`/`until` poll loop with a `sleep` in it holds this subagent's turn"
    f" open for as long as its condition takes.\n{ALTERNATIVES}"
)


def _sleep_denial(seconds: float | None) -> str:
    """Say why a `sleep` this long is blocked."""
    asked = "an unreadable duration" if seconds is None else f"{seconds:g} s"
    return (
        f"A `sleep` for {asked} inside a subagent's turn is blocked: at or above"
        f" {THRESHOLD} s it outlives the turn's prompt cache.\n{ALTERNATIVES}"
    )


def _split_keywords(tokens: list[str]) -> tuple[list[str], list[str]]:
    """Split one segment into the shell keywords it opens with and the command after them.

    `do sleep 10` is one reader segment, and its command word is `sleep`.
    """
    index = 0
    while index < len(tokens) and tokens[index] in _LEADING_KEYWORDS:
        index += 1
    return tokens[:index], tokens[index:]


def _opens_a_loop(tokens: list[str]) -> bool:
    """Report whether this one segment opens a `while` or `until` loop."""
    keywords, _ = _split_keywords(without_assignments(tokens))
    return any(keyword in _LOOP_KEYWORDS for keyword in keywords)


def _seconds(operand: str) -> float | None:
    """Read one `sleep` operand in seconds, or `None` if it cannot be read."""
    match = _DURATION.fullmatch(operand)
    if match is None:
        return None
    return float(match.group(1)) * _SUFFIX_SECONDS[match.group(2)]


def _total_seconds(operands: list[str]) -> float | None:
    """Sum a `sleep`'s operands, or `None` if any of them could not be read.

    An unresolved variable or an arithmetic expression is an unbounded wait, not
    a short one, so it is `None` rather than zero.
    """
    total = 0.0
    for operand in operands:
        if operand.startswith("-"):
            continue  # --help / --version: not a wait
        seconds = _seconds(operand)
        if seconds is None:
            return None
        total += seconds
    return total


def _waits(segments: list[list[str]]) -> list[float | None]:
    """Return one entry per `sleep` the command runs, in seconds; `None` where unbounded."""
    found: list[float | None] = []
    for tokens in segments:
        _, words = _split_keywords(without_assignments(tokens))
        if words and PurePosixPath(words[0]).name == "sleep":
            found.append(_total_seconds(words[1:]))
    return found


def denial(command: str) -> str | None:
    """Return why this Bash command is denied inside a subagent, or `None` to allow it."""
    segments = read_command(command)
    if segments is None:
        return UNREADABLE
    waits = _waits(segments)
    if waits and any(_opens_a_loop(tokens) for tokens in segments):
        return LOOP_DENIAL
    for seconds in waits:
        if seconds is None or seconds >= THRESHOLD:
            return _sleep_denial(seconds)
    return None


def main() -> int:
    """Read the tool call on stdin and deny a turn-blocking wait in a subagent."""
    try:
        data = json.load(sys.stdin)
        agent = data.get("agent_id")
    except (json.JSONDecodeError, TypeError, AttributeError):
        # #41/#94: a check that could not run is not a check that passed.
        print(UNREADABLE, file=sys.stderr)
        return 2
    if not (isinstance(agent, str) and agent.strip()):
        return 0  # the orchestrator: one-hour TTL, and waiting there is the pattern
    try:
        tool_input = data["tool_input"]
        command = tool_input["command"]
        detached = bool(tool_input.get("run_in_background"))
    except (TypeError, KeyError, AttributeError):
        print(UNREADABLE, file=sys.stderr)
        return 2
    if detached:
        return 0  # nothing is held open; this is one of the sanctioned shapes
    reason = denial(command)
    if reason is not None:
        print(reason, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
