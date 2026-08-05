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
  a poll loop's wait is set by its condition, not by its number;
* a **known-long gate**: a command whose measured p90 wall exceeds the TTL. Today
  the list holds one entry, the unfiltered full regression corpus, in both its
  spellings (`just regress` and the `spike/regress.sh` it wraps).

#205 widens the second rule past the `until` and `while true` spellings #203
counted (150 and 2 inside subagents), because `while ! nc -z localhost 2402; do
sleep 1; done` is an `until` loop written the other way round and blocks a turn
just the same. #204's decision 6 adds the third: an agent cannot see its own cache
economics, so what counts as a *foreseeably* long wait is this list rather than a
judgement in the moment. A gate that overruns an expectation off the list is bad
luck, not a policy breach, and the agent continues.

**Where the p90 comes from, and when.** Measured 2026-08-04/05 over the nine
unfiltered pools then in `~/.arma-cti/runs/`, at corpus sizes 22 → 26: walls of
793, 826, 877, 990, 1074, 1103, 1123, 1139, 1204 and 1342 s, **p90 ≈ 1,230 s**,
minimum 793 s. Every recorded unfiltered run is more than twice the TTL, and the
corpus grows. The earlier census agrees at a smaller sample (eight `just regress`
calls at or over five minutes, mean 523 s: `docs/research/token-efficiency.md` §2).

That provenance is load-bearing, because **a gate that speeds up leaves a stale
denial behind**. `just fast` was on this shape's shortlist until #197 took it from
6:32 to 1:02, and `just unit` followed it; both pass now, and neither would have
before. Re-measure before adding an entry, and drop one at a retro when its p90
falls under the TTL rather than leaving the denial to be discovered as wrong.

**What is not the target, and passes on purpose.** The rule is the *turn-blocking
wait shape*, not the word `sleep` and not the word `regress`:

* a bounded short sleep — `sleep 5` in a fixture, `sleep 0.2` between two writes;
* `just regress --list`, which runs nothing: no lock, no port, no world, no Arma;
* a named or `--issues`-filtered selection, which can finish in 25 s
  (`ai-reinforce`, #150/#191);
* a `timeout`-wrapped command whose subject is not on the list: `timeout 900 just
  fast` is a bound on something already under the TTL;
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
* `timeout 1800 just regress` is denied, reversing what this docstring promised
  before #204 landed. A bound on a twenty-minute wait is still a twenty-minute
  wait held inside the turn, and leaving the wrapper as a bypass would put the
  bypass in the file that forbids the thing (#207's finding, one hook over).

**Known under-blocks**, in the safe direction — the rule in CLAUDE.md is the
primary layer and this hook is the mechanical floor, so a miss costs a rule
followed by hand where a false denial costs #120's price:

* an exotic `just` flag before the recipe name hides it. The flags that take a
  value are enumerated in `_JUST_FLAG_VALUES`; one that is not there makes the
  hook read the flag's value as the recipe name and pass.
* a filtered selection is not *always* short — eight probes took 826 s in the
  record above. It is off the list by #204's ruling because it is not foreseeably
  long, not because it is guaranteed brief.

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

# `just`'s own options, and how many words each consumes, so the recipe name can
# be found behind them. Incomplete by design — see the under-blocks above.
_JUST_FLAG_VALUES = {
    "-f": 1,
    "--justfile": 1,
    "-d": 1,
    "--working-directory": 1,
    "-E": 1,
    "--dotenv-path": 1,
    "--color": 1,
    "--shell": 1,
    "--shell-arg": 1,
    "--set": 2,
}

# `timeout`'s options that take a word, so its duration operand can be skipped.
_TIMEOUT_FLAG_VALUES = {"-k": 1, "--kill-after": 1, "-s": 1, "--signal": 1}

# `just regress` options that take a word, so a probe name can be told from a value.
_REGRESS_FLAG_VALUES = {"--slots": 1, "--wait": 1, "--issues": 1}

# Selecting fewer than everything, or nothing at all: off the known-long list.
_REGRESS_SELECTORS = frozenset({"--list", "--issues"})

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

CORPUS_DENIAL = (
    "The unfiltered regression corpus is a known-long gate: measured p90 about"
    " 1,230 s, minimum 793 s over the runs recorded on 2026-08-04/05, against a"
    " five-minute cache. It is denied in a subagent's foreground, not denied"
    " outright — dispatch it and end (#204, decision 6).\n"
    "`just regress --list` runs nothing and passes; a named or `--issues`"
    f" selection passes.\n{ALTERNATIVES}"
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


def _skip_flags(words: list[str], taking: dict[str, int]) -> list[str]:
    """Drop the leading options of one command, and the words they consume.

    `--flag=value` is self-contained, so only the separate-word form consumes.
    """
    index = 0
    while index < len(words) and words[index].startswith("-"):
        consumed = 0 if "=" in words[index] else taking.get(words[index], 0)
        index += 1 + consumed
    return words[index:]


def _unwrap_timeout(words: list[str]) -> list[str]:
    """Strip a leading `timeout [opts] <duration>` wrapper, so its subject can be read."""
    while words and PurePosixPath(words[0]).name == "timeout":
        rest = _skip_flags(words[1:], _TIMEOUT_FLAG_VALUES)
        if not rest:
            return []
        words = rest[1:]  # the duration operand
    return words


def _corpus_arguments(words: list[str]) -> list[str] | None:
    """Return the corpus runner's arguments if this command runs it, else `None`.

    Both spellings count: the `just regress` recipe and the `spike/regress.sh` it
    is a one-line wrapper over.
    """
    if not words:
        return None
    name = PurePosixPath(words[0]).name
    if name == "regress.sh":
        return words[1:]
    if name != "just":
        return None
    recipe = _skip_flags(words[1:], _JUST_FLAG_VALUES)
    if recipe and recipe[0] == "regress":
        return recipe[1:]
    return None


def _runs_the_whole_corpus(arguments: list[str]) -> bool:
    """Report whether these `regress` arguments select everything and run it."""
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if not argument.startswith("-"):
            return False  # a named probe: a selection, not the corpus
        flag = argument.split("=", 1)[0]
        if flag in _REGRESS_SELECTORS:
            return False  # `--list` runs nothing; `--issues` filters
        index += 1 + (0 if "=" in argument else _REGRESS_FLAG_VALUES.get(flag, 0))
    return True


def _gate_denial(tokens: list[str]) -> str | None:
    """Return why this one command is a known-long gate, or `None`."""
    _, words = _split_keywords(without_assignments(tokens))
    arguments = _corpus_arguments(_unwrap_timeout(words))
    if arguments is not None and _runs_the_whole_corpus(arguments):
        return CORPUS_DENIAL
    return None


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
    for tokens in segments:
        reason = _gate_denial(tokens)
        if reason is not None:
            return reason
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
