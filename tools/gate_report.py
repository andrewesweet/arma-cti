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


# The implementer's required heading is the selector, not a loose search for ``just check``:
# review prose can quote a report without becoming the report. It is anchored to a line so a
# block quote or an inline mention cannot accidentally satisfy it.
MARKER: Final = re.compile(r"^### Implementer gate report(?:[ \t]|$)", re.MULTILINE)

CARRIED: Final = "carried"
ABSENT: Final = "absent"
UNAVAILABLE: Final = "unavailable"


class GateReport(NamedTuple):
    """The newest report, a confirmed absence, or why the thread could not be read."""

    state: str
    body: str = ""
    detail: str = ""


def select(comments: Iterable[str]) -> str | None:
    """Return the newest comment beginning with the implementer's report heading."""
    carried = [body for body in comments if MARKER.search(body)]
    return carried[-1] if carried else None


def fetch(issue: int, fetch_comments: Fetch = handoff_fetch.fetch_comments) -> GateReport:
    """Read one issue's comments and preserve carried, absent and unavailable states."""
    try:
        report = select(handoff_fetch.bodies(fetch_comments(issue)))
    except handoff_fetch.FetchError as failure:
        return GateReport(UNAVAILABLE, detail=str(failure))
    if report is None:
        return GateReport(ABSENT)
    return GateReport(CARRIED, body=report)


HEADING: Final = "## Implementer's gate report — supplied by the dispatcher"


def render(issue: int, report: GateReport) -> list[str]:
    """Render one report state without turning unavailable into absent.

    A carried body is inserted unchanged. A thin carried body remains carried so the reviewer
    can identify the missing fields as a finding under the existing review gate contract.
    """
    if report.state == CARRIED:
        return [
            HEADING,
            "",
            "The dispatcher read this comment from the issue thread; its body follows verbatim.",
            "",
            report.body,
        ]
    if report.state == ABSENT:
        return [
            "## Implementer's gate report",
            f"**GATE REPORT ABSENT — no marked report was found on #{issue}'s issue thread.**",
            (
                "The thread was read successfully; this is a confirmed missing record, not an "
                "unavailable read."
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
