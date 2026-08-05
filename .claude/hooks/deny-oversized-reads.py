#!/usr/bin/env python3
"""PreToolUse hook (Read): deny a `Read` that would deliver an oversized payload.

A tool result is not paid once. It enters the conversation prefix and is re-read
on every later turn of that agent's life, so a 200,000-character file read at the
start of a task is charged again at every turn after it. #203 measured the tail
on this project's own transcripts: 28 results exceed 50,000 characters — 0.13% of
all 21,179 results but **5.0% of every tool-result byte**, about 463,000 tokens
and 0.50% of the bill once amplified — and every one of the 28 is a `Read`.
Denying the read up front is lossless where truncating the result afterwards is
not: the agent gets the same bytes, in the pieces it asks for, and knows it did.

**The rule, in one sentence.** A `Read` is denied when the window it asks for
would deliver more than `THRESHOLD` characters.

**The threshold, and why 40,000.** Measured over the 2,549 `Read` results in this
project's history: mean 6,220 characters, median 3,169, p90 15,373, p95 24,828,
p99 53,376. 40,000 sits at the 98th percentile — 6.4× the mean and 12.6× the
median, so nothing resembling a working read comes near it — and the 50 reads
above it carry 2.69 M characters, 46% more than the 50,000 line #203 took its
measurement at, while leaving 98% of all reads untouched.

**The window, not the file.** `Read` returns at most 2,000 lines by default (its
own documented default), or the `offset`/`limit` slice when the call names one,
so what matters is the payload the call would deliver rather than the file's size
on disk. The distinction is not academic here: `Western_Sahara_classNames.wiki`
is 572,976 bytes and its first 2,000 lines are 39,256 — a stat-sized gate would
deny a read that costs less than the threshold and would name a number six times
larger than the one the agent would have paid. The denial has to be able to state
a true size, so the hook measures the lines the call would actually receive.

This is where the hook departs from #207's letter, deliberately: the issue would
permit any call carrying `offset`/`limit` regardless of size. Measuring the
window instead closes the hole in that rule's own advice — an agent told to "use
`offset`/`limit`" can comply with `limit: 999999` and land the identical payload
— and costs nothing, because every ordinary bounded read is far under the
threshold and passes exactly as the issue intends.

**What is exempt, and why the exemption is not a loophole.** `.png`, `.jpg`,
`.pdf` and their kin are not line-addressable: `Read` renders an image visually
and takes `pages` for a PDF, so `offset`/`limit` is not a remedy that exists for
them. A denial whose remedy does not exist is a hard block rather than a
redirect, so these pass — this repo has two playtest screenshots above the
threshold and reading them is the point of them. Nothing else is exempt. The
vendored wiki was checked and needs none: not one of the historical oversized
reads was a wiki page, and CLAUDE.md's INDEX.md-first rule already points an
agent away from the 95 wiki files that would trip this.

**Stated over-blocks.** A file of very long lines can exceed the threshold in a
handful of them, and the suggested line count in the denial will then be small
but honest. A `Read` the agent means to pay for in full has no override; the
remedy is several bounded reads, which is the same bytes and a smaller resident
prefix only if it stops early — that is the trade, and it is deliberate.

**Stated permits.** A path that does not exist, is a directory, or cannot be
opened at all passes: `Read` raises its own error there and no bytes reach the
context, so there is nothing for this hook to prevent. Only a path whose size
cannot be established for some *other* reason is denied as unmeasurable.

Fail-closed, per #41 and #94: a call that cannot be read is not a call that
passed, and PreToolUse reads any exit other than 2 as approval — so the
`.claude/settings.json` wiring maps every failure to 2 with `|| exit 2` (#168,
#183) and this file returns 2 rather than 0 on anything it could not read.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import NamedTuple

# Characters. The 98th percentile of every `Read` this project has made; see the
# module docstring for the distribution it was picked from.
THRESHOLD = 40_000

# `Read`'s own documented default when the call names no `limit`.
DEFAULT_LIMIT = 2_000

# Suffixes whose `Read` is not a line-addressable text read, so `offset`/`limit`
# is not a remedy that exists for them.
NOT_LINE_ADDRESSABLE = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".pdf", ".ipynb"}
)

# Opening the path failed in a way that means `Read` will fail on it too, and
# nothing reaches the context. Not this hook's business.
DELIVERS_NOTHING = (FileNotFoundError, NotADirectoryError, IsADirectoryError, PermissionError)

UNREADABLE = (
    "Could not read this Read call to check its size. It needs a `file_path`,"
    " and `offset`/`limit` must be whole numbers."
)

UNMEASURABLE = "Could not measure this file to check the size of the read. Name it another way."


class Window(NamedTuple):
    """The slice of a file one `Read` call asks for, in lines."""

    skip: int
    count: int


class Delivered(NamedTuple):
    """What that slice would actually put into the context."""

    chars: int
    lines: int


def _is_count(value: object) -> bool:
    """Report whether this is a whole non-negative number of lines."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _window(tool_input: dict[str, object]) -> Window | None:
    """Read the call's `offset`/`limit` as a line window, or `None` if it cannot be read.

    `offset` is a line number, so the first line is 1 and skipping starts one
    below it; 0 and 1 both mean the top of the file.
    """
    offset = tool_input.get("offset")
    limit = tool_input.get("limit")
    if offset is None:
        offset = 0
    if limit is None:
        limit = DEFAULT_LIMIT
    if not (_is_count(offset) and _is_count(limit)):
        return None
    return Window(skip=max(int(offset) - 1, 0), count=int(limit))


def _delivered(target: Path, window: Window) -> Delivered | None:
    """Measure the payload `window` would deliver from `target`, or `None` if unmeasurable.

    Bytes rather than decoded characters: the two differ only on non-ASCII text,
    and by less than the line-number prefix `Read` adds to every line, which is
    not counted either. Both errors are conservative — the real result is a
    little larger than the number named.
    """
    chars = lines = 0
    try:
        with target.open("rb") as handle:
            for _ in range(window.skip):
                if not handle.readline():
                    break
            for _ in range(window.count):
                line = handle.readline()
                if not line:
                    break
                chars += len(line)
                lines += 1
    except DELIVERS_NOTHING:
        return Delivered(chars=0, lines=0)
    except OSError:
        return None
    return Delivered(chars=chars, lines=lines)


def _too_big(target: Path, delivered: Delivered) -> str:
    """Say how big this read is, and name the pieces it could be taken in instead."""
    fits = max(delivered.lines * THRESHOLD // delivered.chars, 1)
    return (
        f"Reading {target.name} would put {delivered.chars:,} characters into context over"
        f" {delivered.lines:,} lines, above this project's {THRESHOLD:,}-character limit for a"
        " single read.\nA tool result is re-read on every later turn of this agent's life, so"
        " that cost is paid again on each of them (#203: 28 such reads carried 5.0% of every"
        " tool-result byte in this project's history). Take the piece you need instead:\n"
        f"  - `Read` again with `offset`/`limit` — about {fits:,} lines at a time stays under"
        " the limit here;\n"
        "  - `Grep` for the symbol with `-n`, then read around the line it reports;\n"
        "  - `mcp__semble__search` when you know the intent but not the line."
    )


def denial(tool_input: object) -> str | None:
    """Return why this Read call is denied, or `None` to allow it."""
    if not isinstance(tool_input, dict):
        return UNREADABLE
    path = tool_input.get("file_path")
    window = _window(tool_input)
    if not (isinstance(path, str) and path.strip()) or window is None:
        return UNREADABLE
    target = Path(path)
    if target.suffix.lower() in NOT_LINE_ADDRESSABLE:
        return None
    delivered = _delivered(target, window)
    if delivered is None:
        return UNMEASURABLE
    if delivered.chars <= THRESHOLD:
        return None
    return _too_big(target, delivered)


def main() -> int:
    """Read the tool call on stdin and deny an oversized Read."""
    try:
        data = json.load(sys.stdin)
        tool_name = data.get("tool_name")
        tool_input = data.get("tool_input")
    except (json.JSONDecodeError, TypeError, AttributeError):
        # #41/#94: a check that could not run is not a check that passed.
        print(UNREADABLE, file=sys.stderr)
        return 2
    if isinstance(tool_name, str) and tool_name != "Read":
        # The matcher routes only `Read` here; if it ever routes more, this hook
        # has nothing to say about it and must not deny an unrelated call.
        return 0
    reason = denial(tool_input)
    if reason is not None:
        print(reason, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
