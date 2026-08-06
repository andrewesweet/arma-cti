"""Carry this repository's hooks onto the Codex lane, and prove they still deny (#243).

ADR-0061 Decision 4 makes a lane's authority the enforcement it *demonstrably* runs: all
hooks proven means full subagent authority, some hooks missing means worktree and commit
only. The ADR called parity "reachable but not proven" on both candidate substrates and
named the specific way such a claim goes wrong — "the suite asserting on its own mock
rather than the lane's real denial path".

So this module is deliberately thin, and the thing it is thin *around* is the real hook
script. It translates `.claude/settings.json`'s hook table into the `[hooks]` table Codex
reads, and it does not reimplement a single hook. The suite that consumes it
(`tests/unit/test_hook_parity.py`) feeds Codex-shaped payloads to the actual committed
scripts and asserts the actual exit code 2. A mock would have proven nothing.

**Why this is a translation and not a copy.** Measured against Codex CLI 0.146.1 (#243,
`docs/research/codex-lane-live-findings.md` §4), three things are already identical and
one is not:

- The event names match: `PreToolUse` and `PostToolUse` are spelled the same.
- The payload matches. Codex sends `tool_name`, `tool_input`, `hook_event_name`, `cwd`,
  `session_id`, `transcript_path` and `permission_mode` on stdin — and it sends
  `tool_name: "Bash"`, Claude Code's tool name, not its own internal `shell`. Every hook
  in `.claude/hooks/` reads exactly those two keys, so **not one of them needed editing.**
- The denial convention matches: exit code 2 blocks the call and the script's stderr
  reaches the model. Proven in-world, not inferred — a probe hook denied
  `echo blocked > TRIPWIRE.txt` and the file did not appear.
- What does *not* carry is `$CLAUDE_PROJECT_DIR`. The command strings in
  `.claude/settings.json` interpolate it, and Codex has no such variable. Two ways to fix
  that; this takes the second. Setting `CLAUDE_PROJECT_DIR` in the child environment would
  work, but it would put a Claude Code variable on a lane that is not Claude Code and make
  a reader wonder which harness is running. Instead the path is resolved *here*, once, into
  an absolute command — so what Codex is handed names a real file, and a missing hook
  script is a translation-time error rather than a silent no-op at denial time.

**The failure mode this module is built to make impossible** is the one that matters:
a hook table that loads but matches nothing. A matcher Codex does not understand, or a
regex that silently matches no tool name, produces a lane that runs with no enforcement
and says nothing about it. `translate` therefore refuses to emit an empty hook list for an
event that had one, and `missing_scripts` names any command whose script is not on disk.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Mapping

# The events worth carrying. Codex 0.146.1 accepts nine — `PreToolUse`,
# `PermissionRequest`, `PostToolUse`, `PreCompact`, `PostCompact`, `SessionStart`,
# `SessionEnd`, `SubagentStart`, `SubagentStop`, plus `UserPromptSubmit` — and this
# repository configures two. Translating only what exists is the point: an event this
# repository does not use has no enforcement to prove.
CARRIED_EVENTS: Final = ("PreToolUse", "PostToolUse")

# The variable Claude Code sets and Codex does not. Resolved at translation time.
PROJECT_DIR_VAR: Final = "$CLAUDE_PROJECT_DIR"
PROJECT_DIR_BRACED: Final = "${CLAUDE_PROJECT_DIR}"


class HookCommand(NamedTuple):
    """One hook: the event it fires on, the tools it matches, the command it runs."""

    event: str
    matcher: str
    command: str

    def script(self) -> Path | None:
        """Return the hook script this command runs, for a plain `python3 <path>` call.

        Returns `None` for a command shaped in any other way, because guessing which
        token of an arbitrary shell line is the program is how a check starts passing on
        commands it never understood.
        """
        found = re.search(r'python3\s+"?([^"\s]+\.py)"?', self.command)
        return Path(found.group(1)) if found else None


class Translation(NamedTuple):
    """A translated hook table, and everything a caller must be able to check about it."""

    commands: tuple[HookCommand, ...]
    toml: str

    def missing_scripts(self) -> tuple[Path, ...]:
        """Name every hook script a command points at that is not on disk.

        A lane whose hook command points at nothing does not fail loudly at denial time —
        the shell exits non-zero for the wrong reason, or zero, and the call proceeds. So
        this is checked before a dispatch, not discovered by one.
        """
        absent = []
        for command in self.commands:
            script = command.script()
            if script is not None and not script.exists():
                absent.append(script)
        return tuple(absent)


def read_settings(settings: Path) -> Mapping[str, object]:
    """Read `.claude/settings.json`, which is the single source for what this repo enforces."""
    return json.loads(settings.read_text(encoding="utf-8"))


def hook_commands(settings: Mapping[str, object], project_dir: Path) -> tuple[HookCommand, ...]:
    """Flatten the settings hook table into one row per command, paths resolved.

    Claude Code's shape is two levels deep — a list of matcher groups per event, each
    carrying a list of hooks — and this flattens it, because the only structure Codex
    needs is the same two levels and the only thing that changes is the command string.
    """
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return ()
    rows: list[HookCommand] = []
    for event in CARRIED_EVENTS:
        groups = hooks.get(event)
        if not isinstance(groups, list):
            continue
        for group in groups:
            if not isinstance(group, dict):
                continue
            matcher = group.get("matcher", "")
            entries = group.get("hooks")
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict) or entry.get("type") != "command":
                    continue
                command = entry.get("command")
                if not isinstance(command, str):
                    continue
                rows.append(
                    HookCommand(
                        event=event,
                        matcher=matcher if isinstance(matcher, str) else "",
                        command=resolve_project_dir(command, project_dir),
                    )
                )
    return tuple(rows)


def resolve_project_dir(command: str, project_dir: Path) -> str:
    """Replace `$CLAUDE_PROJECT_DIR` with the real path, both spellings.

    Codex sets no such variable, so an unresolved command would run `python3
    "/.claude/hooks/..."` and fail for a reason that reads nothing like "the hook is
    missing". Resolving here means the command Codex is handed is checkable before it runs.
    """
    return command.replace(PROJECT_DIR_BRACED, str(project_dir)).replace(
        PROJECT_DIR_VAR, str(project_dir)
    )


def toml_string(value: str) -> str:
    """Quote a string for TOML, escaping what a basic string may not carry literally."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def translate(settings: Mapping[str, object], project_dir: Path) -> Translation:
    """Render the settings hook table as the `[hooks]` table Codex reads.

    Emitted as a single-line inline table per event because it travels on `codex exec`'s
    `-c` argv — per invocation, never written to `~/.codex/config.toml`. A dispatch's
    enforcement is then a property of the dispatch, and a Codex session the human starts by
    hand is unaffected by anything this repository configures. The same reasoning that
    keeps `ANTHROPIC_BASE_URL` off the shell profile keeps this off the box.
    """
    commands = hook_commands(settings, project_dir)
    by_event: dict[str, list[HookCommand]] = {}
    for command in commands:
        by_event.setdefault(command.event, []).append(command)

    lines = []
    for event in CARRIED_EVENTS:
        rows = by_event.get(event)
        if not rows:
            continue
        groups = []
        for row in rows:
            handler = f'{{ type = "command", command = {toml_string(row.command)} }}'
            matcher = f"matcher = {toml_string(row.matcher)}, " if row.matcher else ""
            groups.append(f"{{ {matcher}hooks = [{handler}] }}")
        lines.append(f"hooks.{event}=[{', '.join(groups)}]")
    return Translation(commands=commands, toml="\n".join(lines))


def config_overrides(settings: Mapping[str, object], project_dir: Path) -> tuple[str, ...]:
    """Build the `-c` arguments that put this repo's hooks on a `codex exec` invocation."""
    translation = translate(settings, project_dir)
    return tuple(line for line in translation.toml.split("\n") if line)
