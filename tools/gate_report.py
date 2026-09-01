"""Carry an implementer's issue-thread gate report into a review brief (#641).

The review seat is deliberately forced into ``plan`` mode, so it cannot ask ``gh`` for the
thread it is reviewing. The dispatcher reads the thread before launch and gives the reviewer
the selected comment instead. A cleanly scanned thread, an unreadable thread and a carried
comment are different facts; collapsing the first two recreates the false finding this module
exists to prevent.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final, NamedTuple

import handoff_fetch

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    Fetch = Callable[[int], str]


# The implementer's required marker is the selector, not a loose search for ``just check``:
# review prose can quote a report without becoming the report. Selection accepts this literal at
# the body's first line, with optional whitespace and a descriptive suffix after it.
MARKER: Final = "### Implementer gate report"

# The issue thread is untrusted prompt input. Keep a carried report from consuming an unbounded
# review brief, and make any omitted tail visible so it cannot read as a complete report.
CARRIED_CAP: Final = 8_000
CARRIED_TRUNCATION_MARKER: Final = (
    "[GATE REPORT TRUNCATED — comment continued beyond carried bound; "
    "remaining comment content was not carried.]"
)
# CommonMark permits up to three spaces before a fence. Runs elsewhere on a line are inline
# delimiters and do not change fenced-block state.
_FENCE_START: Final = re.compile(r"(?m)^ {0,3}(`{3,})")

CARRIED: Final = "carried"
ABSENT: Final = "absent"
UNAVAILABLE: Final = "unavailable"


class GateReport(NamedTuple):
    """The newest marked report, a successful marker miss, or why the thread could not be read."""

    state: str
    body: str = ""
    detail: str = ""


def _starts_with_marker(body: str) -> bool:
    """Say whether the comment's first line begins with the shared marker."""
    first_line = body.partition("\n")[0].removesuffix("\r")
    return first_line == MARKER or first_line.startswith((f"{MARKER} ", f"{MARKER}\t"))


def select(comments: Iterable[str]) -> str | None:
    """Return the newest comment whose first line begins with the implementer's marker."""
    carried = [body for body in comments if _starts_with_marker(body)]
    return carried[-1] if carried else None


def fetch(issue: int, fetch_comments: Fetch = handoff_fetch.fetch_comments) -> GateReport:
    """Read one issue's comments and preserve carried, marker-absent and unavailable states."""
    try:
        report = select(handoff_fetch.bodies(fetch_comments(issue)))
    except handoff_fetch.FetchError as failure:
        return GateReport(UNAVAILABLE, detail=str(failure))
    if report is None:
        return GateReport(ABSENT)
    return GateReport(CARRIED, body=report)


HEADING: Final = "## Implementer's gate report — supplied by the dispatcher"


def _closing_fence(prefix: str) -> str:
    """Return a closer when ``prefix`` leaves a backtick fence open."""
    opener_width: int | None = None
    for run in _FENCE_START.finditer(prefix):
        width = len(run.group(1))
        if opener_width is None:
            opener_width = width
        elif width >= opener_width:
            opener_width = None

    if opener_width is None:
        return ""
    return "\n" + "`" * opener_width


def _bounded_body(body: str) -> str:
    """Bound a carried body and close a cut-open fenced block before the marker."""
    if len(body) <= CARRIED_CAP:
        return body
    suffix = f"\n\n{CARRIED_TRUNCATION_MARKER}"
    prefix_limit = CARRIED_CAP - len(suffix)
    prefix = body[:prefix_limit]
    closing_fence = _closing_fence(prefix)
    if closing_fence:
        prefix_limit -= len(closing_fence)
        prefix = body[:prefix_limit]
        closing_fence = _closing_fence(prefix)
    return prefix + closing_fence + suffix


def render(issue: int, report: GateReport) -> list[str]:
    """Render one report state without turning unavailable into absent.

    A carried body is bounded and a thin carried body remains carried so the reviewer can identify
    missing fields as a finding under the existing review gate contract.
    """
    if report.state == CARRIED:
        return [
            HEADING,
            "",
            (
                "The dispatcher read this comment from the issue thread; its bounded body follows"
                " verbatim, with a closing fence added if truncation cut one open. A truncation"
                " marker means the comment continued beyond the bound."
            ),
            "",
            _bounded_body(report.body),
        ]
    if report.state == ABSENT:
        return [
            "## Implementer's gate report",
            (
                f"**GATE REPORT ABSENT — no comment carrying the required marker `{MARKER}` was "
                f"found on #{issue}'s issue thread.**"
            ),
            (
                "The thread was read successfully; an unmarked report may exist on the thread. "
                "This is not confirmation that no report exists."
            ),
        ]
    if report.state == UNAVAILABLE:
        return [
            "## Implementer's gate report",
            (
                f"**GATE REPORT UNAVAILABLE — the dispatcher could not obtain #{issue}'s issue "
                "thread.**"
            ),
            f"Reason: {report.detail or 'the thread read returned no usable result'}",
            (
                "This is an inability to obtain the record, not evidence that the report is "
                "absent. Report that inability distinctly."
            ),
        ]
    # No caller should be able to make an unknown state look like either negative result.
    return [
        "## Implementer's gate report",
        f"**GATE REPORT UNAVAILABLE — the dispatcher returned an unknown state for #{issue}.**",
        "The record cannot be classified as present or absent; report the inability to obtain it.",
    ]
