"""Ownership by presence, and the income tick.

#13 requires these rules to be tested here rather than only observed in-game,
which is why they live in the daemon: the world reports who is standing where,
and the campaign decides what that means.

Time is supplied by the caller rather than read from a clock. In-game seconds
are the unit the rules are written in (they stop when the session does), and a
rule that takes time as an argument is a rule that can be tested.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cti_daemon import campaign, economy, manifest
from cti_daemon.outbox import Outbox

REPO = Path(__file__).parents[2]


@pytest.fixture
def live() -> campaign.Campaign:
    """Return a campaign on the authored Stratis map, everything Neutral."""
    return campaign.Campaign(
        map_manifest=manifest.load(REPO / "manifests" / "stratis.json"),
        table=economy.load(REPO / "config" / "economy.json"),
        ledger=economy.Ledger(300),
        outbox=Outbox(),
    )


def hold(live: campaign.Campaign, objective: str, sides: list[str], seconds: float) -> None:
    """Report `sides` standing on `objective` for `seconds` of in-game time."""
    live.observe(live.elapsed + seconds, {objective: sides})


def test_everything_starts_neutral(live: campaign.Campaign) -> None:
    assert live.owner("agia_marina") == "NEUTRAL"


def test_a_side_alone_in_the_radius_takes_the_objective(live: campaign.Campaign) -> None:
    hold(live, "agia_marina", ["WEST"], 30)
    assert live.owner("agia_marina") == "WEST"


def test_a_side_that_leaves_too_soon_takes_nothing(live: campaign.Campaign) -> None:
    hold(live, "agia_marina", ["WEST"], 29)
    assert live.owner("agia_marina") == "NEUTRAL"


def test_both_sides_present_makes_the_objective_contested(live: campaign.Campaign) -> None:
    # A real state, not a transient: Contested pays nobody and the AI Commander
    # has to be able to see it and react.
    hold(live, "agia_marina", ["WEST", "EAST"], 5)
    assert live.owner("agia_marina") == "CONTESTED"


def test_contesting_an_objective_interrupts_a_capture(live: campaign.Campaign) -> None:
    hold(live, "agia_marina", ["WEST"], 25)
    hold(live, "agia_marina", ["WEST", "EAST"], 1)
    hold(live, "agia_marina", ["WEST"], 25)
    assert live.owner("agia_marina") == "CONTESTED"


def test_an_empty_objective_keeps_its_owner(live: campaign.Campaign) -> None:
    # Holding ground you already took should not require standing on it forever.
    hold(live, "agia_marina", ["WEST"], 30)
    hold(live, "agia_marina", [], 300)
    assert live.owner("agia_marina") == "WEST"


def test_taking_an_objective_from_the_other_side_needs_the_same_hold(
    live: campaign.Campaign,
) -> None:
    hold(live, "agia_marina", ["WEST"], 30)
    hold(live, "agia_marina", ["EAST"], 29)
    assert live.owner("agia_marina") == "WEST"
    hold(live, "agia_marina", ["EAST"], 1)
    assert live.owner("agia_marina") == "EAST"


def test_a_capture_announces_itself_as_an_effect(live: campaign.Campaign) -> None:
    hold(live, "agia_marina", ["WEST"], 30)
    effects = [entry.message for entry in live.outbox.pending()]
    assert {
        "effect": "objective_captured",
        "side": "WEST",
        "args": {"objective": "agia_marina"},
    } in effects


def test_income_pays_the_sum_over_owned_objectives_plus_the_stipend(
    live: campaign.Campaign,
) -> None:
    hold(live, "agia_marina", ["WEST"], 30)
    hold(live, "girna", ["WEST"], 30)
    before = live.ledger.balance("WEST")
    live.observe(live.elapsed + 60, {})
    # Two Objectives at 10 each, plus the flat stipend of 5.
    assert live.ledger.balance("WEST") - before == 25


def test_a_side_holding_nothing_still_receives_the_stipend(live: campaign.Campaign) -> None:
    # No side can be economically locked out, so a losing campaign stays
    # recoverable.
    before = live.ledger.balance("EAST")
    live.observe(live.elapsed + 60, {})
    assert live.ledger.balance("EAST") - before == 5


def test_a_contested_objective_pays_nobody(live: campaign.Campaign) -> None:
    hold(live, "agia_marina", ["WEST"], 30)
    hold(live, "agia_marina", ["WEST", "EAST"], 1)
    before = {side: live.ledger.balance(side) for side in ("WEST", "EAST")}
    live.observe(live.elapsed + 60, {})
    assert live.ledger.balance("WEST") - before["WEST"] == 5
    assert live.ledger.balance("EAST") - before["EAST"] == 5


def test_income_does_not_arrive_early(live: campaign.Campaign) -> None:
    before = live.ledger.balance("WEST")
    live.observe(live.elapsed + 59, {})
    assert live.ledger.balance("WEST") == before


def test_a_long_gap_pays_every_tick_it_covers(live: campaign.Campaign) -> None:
    # Reports are not guaranteed regular; three minutes of them arriving late
    # is still three minutes of income, not one.
    before = live.ledger.balance("WEST")
    live.observe(live.elapsed + 180, {})
    assert live.ledger.balance("WEST") - before == 15


def test_time_going_backwards_is_a_new_session_rather_than_a_refund(
    live: campaign.Campaign,
) -> None:
    # In-game time restarts at zero on a mission restart. Treating that as a
    # negative interval would claw back Funds already paid.
    live.observe(600, {})
    paid = live.ledger.balance("WEST")
    live.observe(5, {})
    assert live.ledger.balance("WEST") == paid


def test_a_payout_is_reported_so_the_economy_can_be_watched(live: campaign.Campaign) -> None:
    # Paying in silence would leave the economy the one part of the campaign
    # nobody can observe.
    hold(live, "agia_marina", ["WEST"], 30)
    paid = live.observe(live.elapsed + 60, {})
    assert paid == [{"WEST": 15, "EAST": 5}]


def test_a_report_covering_no_tick_reports_no_payout(live: campaign.Campaign) -> None:
    assert live.observe(live.elapsed + 10, {}) == []
