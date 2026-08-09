"""Read the paths a file-editing tool call writes, on either harness (#273).

Claude Code's `Edit` and `Write` name their target in `tool_input.file_path`, and every
hook in `.claude/hooks/` has read exactly that key since the first one was written. Codex's
editing tool does not name a path at all: it hands the hook a **V4A patch envelope**, and
the paths it writes live inside the patch text.

**The diagnosis this module encodes, because #273's title records a different one.** The
issue was filed as "Codex file edits miss the `Edit|Write` PostToolUse formatter and linter
hooks", which reads as a matcher defect. It is not one, and this repository's own evidence
rules it out. On 2026-08-07 dispatch `d-20260807-204151-09d57f` was refused by
`protect-gated-paths.py` — "it could not inspect the patch tool call for gated-path
checking", which is that hook's fail-closed branch, the one reached when
`tool_input["file_path"]` raises. **A hook cannot refuse a call it was never selected
for**, so the `Edit|Write` matcher did fire on a Codex edit. The PostToolUse formatter and
linter are wired on that same matcher string, so they fired too, read `""` for the path,
matched no extension, and exited 0 having formatted nothing. One root, two symptoms, and
widening the matcher fixes neither.

**Why this keys on the patch text rather than on a tool name.** No live Codex edit payload
has been captured here — see `docs/research/codex-lane-live-findings.md` §4.1 for what is
measured, what is vendor-documented, and what is neither — and a reader keyed on a guessed
`tool_name` would stack a second assumption on the first. `*** Begin Patch` is the patch
format's own opening line: it is in the payload whatever the tool is called and whichever
key carries it. So this searches the call's string values for that sentinel and parses what
follows, and it is correct for any tool name Codex turns out to use.

**Unreadable is not empty.** `edited_paths` returns `None` for a call it cannot read and an
empty tuple only for one it read as writing nothing. A gate that conflates the two turns
"I could not tell" into "nothing to check", which is #94 findings 1-2 exactly. A caller
that denies must deny on `None`; a caller that merely formats must do nothing on it.
"""

from __future__ import annotations

from typing import Final

# The V4A envelope's opening line. Its presence is what marks a string as a patch.
SENTINEL: Final = "*** Begin Patch"

# The action lines that name a path. `Move to` is the rename half of an update and it names
# the destination, which is a path that ends up written; the `Update File` line above it
# names the one that ends up gone. Both are writes, so both are collected.
TARGET_MARKERS: Final = (
    "*** Add File:",
    "*** Update File:",
    "*** Delete File:",
    "*** Move to:",
)

# Where a patch envelope has been seen or documented to travel. Tried first, in this order;
# every other string value of the call is tried after, which is what keeps this tuple an
# optimisation rather than a load-bearing assumption about the payload's shape.
ENVELOPE_KEYS: Final = ("command", "input", "patch", "content", "text")


def patch_targets(text: str) -> tuple[str, ...] | None:
    """Return the paths a V4A patch writes, or `None` if this is not a readable patch.

    `None` covers both "no patch envelope here" and "an envelope whose targets could not be
    read". A patch that opens and names nothing is a shape this parser does not understand,
    and reporting it as writing nothing would be the fail-open answer to it.
    """
    if SENTINEL not in text:
        return None
    targets = []
    for line in text.splitlines():
        for marker in TARGET_MARKERS:
            # A patch body line is prefixed with a space, `-` or `+`, so an unprefixed
            # marker is the action line rather than patch content that quotes one.
            if line.startswith(marker):
                path = line[len(marker) :].strip()
                if path:
                    targets.append(path)
                break
    return tuple(targets) if targets else None


def candidate_strings(tool_input: dict[str, object]) -> list[str]:
    """Return every string in the call that could carry a patch, likeliest key first."""
    ordered: list[object] = [tool_input[key] for key in ENVELOPE_KEYS if key in tool_input]
    ordered += [value for key, value in tool_input.items() if key not in ENVELOPE_KEYS]
    found: list[str] = []
    for value in ordered:
        if isinstance(value, str):
            found.append(value)
        elif isinstance(value, list):
            # Codex's shell form is `["apply_patch", "*** Begin Patch\n…"]`, so one level
            # of list is flattened. Deeper nesting is not guessed at: it would be read as
            # unreadable, which denies rather than approves.
            found += [item for item in value if isinstance(item, str)]
    return found


def edited_paths(tool_input: object) -> tuple[str, ...] | None:
    """Return the paths this tool call writes, or `None` if the call cannot be read.

    Two shapes, in the order a payload is likely to carry them: Claude Code's `file_path`,
    and a patch envelope somewhere among the call's strings.
    """
    if not isinstance(tool_input, dict):
        return None
    path = tool_input.get("file_path")
    if isinstance(path, str) and path:
        return (path,)
    for text in candidate_strings(tool_input):
        targets = patch_targets(text)
        if targets is not None:
            return targets
    return None
