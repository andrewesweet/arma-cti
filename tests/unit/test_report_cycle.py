"""The report cycle: what one report does to a Campaign, and in what order.

#75 moved this out of `Daemon`, so the order the cycle runs in is asserted here,
against the use case, rather than through a socket. What the Daemon does with a
line is `test_daemon_dispatch.py`'s subject and stays there.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pytest

from cti_daemon.daemon import Daemon
from cti_daemon.report import HqSeen, Report, SideContacts
from cti_daemon.report_cycle import ReportCycle, UnknownPlaceError
from cti_daemon.telemetry import Telemetry

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from cti_daemon import campaign as campaign_module


class _Recording:
    """A Campaign that writes down what the cycle asked of it, in order."""

    #: The calls the cycle's order is made of. Anything else — `based`, the
    #: outcome, the roster — is a question rather than a step, and recording it
    #: would bury the sequence under the reads that support it.
    WATCHED = ("reconcile", "sight", "raze", "observe", "observation")

    def __init__(self, campaign: campaign_module.Campaign) -> None:
        self.campaign = campaign
        self.calls: list[str] = []

    def __getattr__(self, name: str) -> Any:  # noqa: ANN401 — it stands in for a
        # Campaign, whose members are of every type it has.
        attribute = getattr(self.campaign, name)
        if name not in self.WATCHED:
            return attribute
        watched = cast("Callable[..., Any]", attribute)

        def recorded(*args: Any, **named: Any) -> Any:  # noqa: ANN401 — as above
            self.calls.append(name)
            return watched(*args, **named)

        return recorded


def _cycle(tmp_path: Path) -> tuple[ReportCycle, _Recording]:
    """Build a cycle over a real Campaign that records what it is asked."""
    log = tmp_path / "telemetry.jsonl"
    # A real Campaign, built the way the daemon builds one: the order under test
    # is an order of real calls, not of a double's expectations.
    daemon = Daemon(telemetry_path=log)
    recording = _Recording(daemon.campaign)
    return (
        ReportCycle(
            campaign=cast("campaign_module.Campaign", recording),
            port=daemon.port,
            telemetry=Telemetry(log),
            telemetry_path=log,
            archive_path=tmp_path / "campaigns",
        ),
        recording,
    )


def _report(**named: Any) -> Report:  # noqa: ANN401 — a report is a document
    return Report(
        at_time=named.get("at_time", 10.0),
        presence=named.get("presence", {}),
        squads=named.get("squads"),
        contacts=named.get("contacts"),
        hq=named.get("hq"),
        casualties=named.get("casualties"),
    )


def test_the_cycle_runs_in_the_order_the_campaign_depends_on(tmp_path: Path) -> None:
    # What the world has lost is reconciled and what its leaders saw is folded
    # in *before* the Campaign is given the report, because income is paid on
    # what a side holds and Contacts age against the clock the report carries.
    # The picture is taken last, so what goes back is the board after the whole
    # report rather than part way through it.
    cycle, recording = _cycle(tmp_path)
    cycle.fold(
        _report(squads={}, contacts={"WEST": SideContacts(seen=(), observed=())}, presence={})
    )

    assert recording.calls[:3] == ["reconcile", "sight", "observe"]
    assert recording.calls[-1] == "observation"


def test_a_report_that_says_nothing_about_squads_asks_nothing_of_the_roster(
    tmp_path: Path,
) -> None:
    cycle, recording = _cycle(tmp_path)
    cycle.fold(_report())

    assert "reconcile" not in recording.calls
    assert "sight" not in recording.calls


def test_ground_this_map_does_not_have_is_refused_in_the_campaigns_language(
    tmp_path: Path,
) -> None:
    # Not a `MalformedRequestError`: the cycle knows nothing of requests, and
    # the Daemon is what turns this into a reply.
    cycle, _ = _cycle(tmp_path)
    with pytest.raises(UnknownPlaceError, match="nowhere"):
        cycle.fold(_report(hq={"nowhere": HqSeen(destroyed=True, by="EAST")}))


def test_a_side_is_played_by_one_commander_at_a_time(tmp_path: Path) -> None:
    cycle, _ = _cycle(tmp_path)
    assert cycle.commanders == ()
    assert not cycle.commanded("WEST")
    with pytest.raises(ValueError, match="no side named"):
        cycle.commanded_by("SOUTH", cast("Any", object()))
