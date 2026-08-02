"""How a Campaign ends: Domination and Decapitation (#35).

Both conditions are rules, so they live in the daemon and are tested here rather
than only witnessed in a world (ADR-0012). Time is an argument, as everywhere
else in the campaign: ten in-game minutes of sustained ownership is a number of
seconds handed to `observe`, which is what makes a condition whose real subject
takes ten minutes testable in milliseconds.

`docs/mvp-scope.md` fixes both, decided 2026-07-30: Domination is owning every
Objective simultaneously for ten sustained in-game minutes within one Play
Session, its timer not persisted; Decapitation is the enemy Base's HQ structure
destroyed, with a mutual destruction resolved by whichever came first in
telemetry order.
"""

from __future__ import annotations

import pytest
from conftest import live

from cti_daemon import campaign, contacts, economy, squads
from cti_daemon.outbox import Outbox


@pytest.fixture(name="live")
def live_campaign() -> campaign.Campaign:
    """Return a Campaign on the authored Stratis map, everything Neutral."""
    return live()


def everywhere(live: campaign.Campaign, side: str) -> dict[str, list[str]]:
    """One side standing in every Objective's capture radius."""
    return {objective.id: [side] for objective in live.map_manifest.objectives}


def take_the_island(live: campaign.Campaign, side: str) -> None:
    """Hold every Objective long enough for `side` to own the lot, and check it did.

    The assert is the arrangement's own postcondition, stated here so that a
    Campaign that failed to reach the state under test fails as that rather
    than as whatever the test went on to measure.
    """
    live.observe(live.elapsed + 1, everywhere(live, side))
    live.observe(live.elapsed + live.table.capture_seconds, everywhere(live, side))
    assert set(live.owners().values()) == {side}


# --------------------------------------------------------------- Domination


def test_owning_every_objective_does_not_win_on_its_own(live: campaign.Campaign) -> None:
    # Total ownership is the start of the clock, not the end of the Campaign.
    take_the_island(live, "WEST")
    assert live.outcome is None


def test_holding_every_objective_for_ten_in_game_minutes_wins(live: campaign.Campaign) -> None:
    take_the_island(live, "WEST")
    live.observe(live.elapsed + live.table.domination_seconds, {})

    assert live.outcome is not None
    assert (live.outcome.winner, live.outcome.condition) == ("WEST", campaign.DOMINATION)


def test_a_minute_short_of_ten_wins_nothing(live: campaign.Campaign) -> None:
    take_the_island(live, "WEST")
    live.observe(live.elapsed + live.table.domination_seconds - 60, {})
    assert live.outcome is None


def test_losing_one_objective_restarts_the_ten_minutes(live: campaign.Campaign) -> None:
    # Sustained means sustained: a Campaign that banked its nine minutes and
    # cashed them a quarter of an hour later would be won on arithmetic.
    take_the_island(live, "WEST")
    live.observe(live.elapsed + live.table.domination_seconds - 60, {})

    # Contested is not owned, so the run is broken here and not merely paused.
    live.observe(live.elapsed + 5, {"agia_marina": ["WEST", "EAST"]})
    take_the_island(live, "WEST")
    live.observe(live.elapsed + 60, {})
    assert live.outcome is None

    live.observe(live.elapsed + live.table.domination_seconds, {})
    assert live.outcome is not None
    assert live.outcome.condition == campaign.DOMINATION


def test_the_other_side_taking_the_island_starts_its_own_clock(live: campaign.Campaign) -> None:
    take_the_island(live, "WEST")
    live.observe(live.elapsed + 300, {})
    take_the_island(live, "EAST")
    # WEST's 300 seconds are not EAST's.
    live.observe(live.elapsed + 400, {})
    assert live.outcome is None

    live.observe(live.elapsed + 300, {})
    assert live.outcome is not None
    assert live.outcome.winner == "EAST"


def test_the_domination_timer_starts_again_on_a_fresh_campaign(live: campaign.Campaign) -> None:
    # Not persisted and reset on boot (docs/mvp-scope.md). A Campaign is built
    # here rather than resumed, so what proves it is that a new one holding the
    # same island has to wait the full ten minutes again.
    take_the_island(live, "WEST")
    live.observe(live.elapsed + live.table.domination_seconds - 60, {})

    reborn = campaign.Campaign(
        map_manifest=live.map_manifest,
        table=live.table,
        ledger=economy.Ledger(300),
        outbox=Outbox(),
    )
    take_the_island(reborn, "WEST")
    reborn.observe(reborn.elapsed + live.table.domination_seconds - 60, {})
    assert reborn.outcome is None


def test_a_won_campaign_stops_paying_and_stops_changing_hands(live: campaign.Campaign) -> None:
    # Complete means complete: a Campaign that kept accruing income and flipping
    # Objectives after its end screen would archive a state nobody played to.
    take_the_island(live, "WEST")
    live.observe(live.elapsed + live.table.domination_seconds, {})
    funds = live.ledger.balance("EAST")

    assert live.observe(live.elapsed + 600, everywhere(live, "EAST")) == []
    assert live.ledger.balance("EAST") == funds
    assert set(live.owners().values()) == {"WEST"}


# ------------------------------------------------------------ Decapitation


def test_every_hq_starts_intact(live: campaign.Campaign) -> None:
    assert live.headquarters() == {"nato_airbase": campaign.INTACT, "csat_kamino": campaign.INTACT}


def test_destroying_the_enemy_hq_wins_the_campaign(live: campaign.Campaign) -> None:
    assert live.raze("csat_kamino", at_time=90) is True

    assert live.headquarters()["csat_kamino"] == campaign.DESTROYED
    assert live.outcome is not None
    assert (live.outcome.winner, live.outcome.condition, live.outcome.at_time) == (
        "WEST",
        campaign.DECAPITATION,
        90,
    )


def test_the_side_that_loses_is_the_one_whose_base_fell(live: campaign.Campaign) -> None:
    # `by` is attribution, not the rule. An HQ brought down by its own side's
    # ordnance is still that side's Base destroyed, and the enemy still wins.
    live.raze("csat_kamino", at_time=5)
    assert live.outcome is not None
    assert live.outcome.winner == "WEST"


def test_an_hq_already_down_stays_down_and_is_not_a_second_event(live: campaign.Campaign) -> None:
    # The world reports rubble as rubble on every report, so the once-only rule
    # is what keeps telemetry order meaning first destruction.
    assert live.raze("csat_kamino", at_time=90) is True
    assert live.raze("csat_kamino", at_time=95) is False


def test_a_mutual_decapitation_goes_to_whichever_was_reported_first(
    live: campaign.Campaign,
) -> None:
    # docs/mvp-scope.md: first destruction event in telemetry order wins, and
    # deterministically. Both HQs fall in the same report here; the first one
    # the daemon reads is the one that ended the Campaign.
    live.raze("csat_kamino", at_time=200)
    live.raze("nato_airbase", at_time=200)

    assert live.outcome is not None
    assert live.outcome.winner == "WEST"
    assert live.headquarters() == {
        "nato_airbase": campaign.DESTROYED,
        "csat_kamino": campaign.DESTROYED,
    }


def test_the_reverse_order_gives_the_reverse_winner(live: campaign.Campaign) -> None:
    live.raze("nato_airbase", at_time=200)
    live.raze("csat_kamino", at_time=200)

    assert live.outcome is not None
    assert live.outcome.winner == "EAST"


def test_a_decapitation_after_a_domination_does_not_rewrite_the_winner(
    live: campaign.Campaign,
) -> None:
    take_the_island(live, "WEST")
    live.observe(live.elapsed + live.table.domination_seconds, {})
    live.raze("nato_airbase", at_time=live.elapsed)

    assert live.outcome is not None
    assert (live.outcome.winner, live.outcome.condition) == ("WEST", campaign.DOMINATION)


def test_razing_ground_that_is_no_base_is_refused(live: campaign.Campaign) -> None:
    with pytest.raises(KeyError):
        live.raze("agia_marina", at_time=1)


# ------------------------------------------- What a won Campaign will not take
#
# #60: the root is where "a won Campaign is no longer being played" is stated,
# so every way strategic state can move is asked here rather than each caller
# remembering. A Command is *refused* — somebody asked for something the rules
# will not do, and the port has a code for that — while a world report is
# ignored, the way `observe` already ignores one: the world does not know the
# Campaign is over and goes on reporting until the effect reaches it.


def win(live: campaign.Campaign) -> None:
    """End the Campaign the way the world ends one: WEST takes EAST's HQ."""
    live.raze("csat_kamino", at_time=90)
    assert live.complete


def test_a_won_campaign_musters_no_further_squad(live: campaign.Campaign) -> None:
    funds = live.ledger.balance("WEST")
    win(live)

    with pytest.raises(campaign.CampaignOverError):
        live.purchase("WEST", "rifle")

    assert live.ledger.balance("WEST") == funds
    assert live.roster.roll("WEST") == ()
    assert live.outbox.pending() == []


def test_a_won_campaign_issues_no_further_order(live: campaign.Campaign) -> None:
    squad, _ = live.purchase("WEST", "rifle")
    win(live)

    with pytest.raises(campaign.CampaignOverError):
        live.issue(squad.id, "WEST", squads.Order("capture", "girna"))

    assert squad.order == squads.RESERVE


def test_a_won_campaign_takes_no_more_of_the_worlds_account_of_its_squads(
    live: campaign.Campaign,
) -> None:
    squad, _ = live.purchase("WEST", "rifle")
    win(live)

    assert live.reconcile({}) == ()
    assert live.roster.of(squad.id, "WEST") is not None


def test_a_won_campaign_takes_no_more_sightings(live: campaign.Campaign) -> None:
    win(live)
    live.sight(
        "WEST",
        at_time=95,
        seen=(contacts.Sighting(at="girna", kind="Infantry", age=0.0),),
        observed=("girna",),
    )
    assert live.contacts.of("WEST", 95) == ()
