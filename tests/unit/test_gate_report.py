"""The issue-thread gate-report transport keeps presence and read failure distinct (#641)."""

from __future__ import annotations

import json

from conftest import load_tool

handoff_fetch = load_tool("handoff_fetch")
gate_report = load_tool("gate_report")


REPORT = (
    "### Implementer gate report — issue 641 at deadbee\n\n"
    "just check: 22 passed\n"
    "just unit: 6061 passed\n"
    "just mutation: 20/20 killed\n"
    "mutation smoke: run was exhaustive\n"
)


def payload(*comments: str) -> str:
    """Encode bodies as the JSON Lines projection returned by the comments transport."""
    return "".join(json.dumps(comment) + "\n" for comment in comments)


def test_select_returns_the_newest_exactly_marked_report() -> None:
    quoted = "> ### Implementer gate report — quoted prose\n"
    newer = REPORT.replace("deadbee", "cafebabe")
    assert gate_report.select([REPORT, quoted, newer]) == newer


def test_select_requires_the_heading_on_the_body_first_line() -> None:
    later_heading = "Reviewer prose\n### Implementer gate report — quoted prose\n"
    assert gate_report.select([REPORT, later_heading]) == REPORT


def test_fetch_carries_the_selected_body_verbatim() -> None:
    report = gate_report.fetch(641, fetch_comments=lambda _issue: payload("noise", REPORT))
    assert report == gate_report.GateReport(gate_report.CARRIED, body=REPORT)


def test_fetch_marks_a_successfully_read_thread_without_a_report_absent() -> None:
    report = gate_report.fetch(641, fetch_comments=lambda _issue: payload("noise"))
    assert report.state == gate_report.ABSENT
    assert report.body == ""


def test_fetch_marks_a_thread_read_failure_unavailable() -> None:
    detail = "comments endpoint refused"

    def refusing(_issue: int) -> str:
        raise handoff_fetch.FetchError(detail)

    report = gate_report.fetch(641, fetch_comments=refusing)
    assert report == gate_report.GateReport(gate_report.UNAVAILABLE, detail=detail)


def test_render_keeps_carried_absent_and_unavailable_states_distinct() -> None:
    carried = "\n".join(
        gate_report.render(641, gate_report.GateReport(gate_report.CARRIED, REPORT))
    )
    absent = "\n".join(gate_report.render(641, gate_report.GateReport(gate_report.ABSENT)))
    unavailable = "\n".join(
        gate_report.render(641, gate_report.GateReport(gate_report.UNAVAILABLE, detail="offline"))
    )

    assert carried.count(REPORT) == 1
    assert "GATE REPORT ABSENT" in absent
    assert "GATE REPORT UNAVAILABLE" not in absent
    assert "GATE REPORT UNAVAILABLE" in unavailable
    assert "GATE REPORT ABSENT" not in unavailable
    assert "offline" in unavailable
