"""The Command Port entry function: the sole mutator of strategic state.

ADR-0012 makes the daemon the rules authority and this function the only door
into the campaign, for the human UI and the AI planner alike. The planner does
not cross the wire — it builds the same Command objects and calls this — so
Commander symmetry is one validator rather than two kept honest by convention.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cti_daemon import campaign, economy, manifest, port, squads
from cti_daemon.commands import Command
from cti_daemon.outbox import Outbox

REPO = Path(__file__).parents[2]


@pytest.fixture
def open_port() -> port.CommandPort:
    """Return a port over the authored map and economy, everything Neutral."""
    table = economy.load(REPO / "config" / "economy.json")
    return port.CommandPort(
        campaign=campaign.Campaign(
            map_manifest=manifest.load(REPO / "addons" / "main" / "manifests" / "stratis.json"),
            table=table,
            ledger=economy.Ledger(table.starting_funds),
            outbox=Outbox(),
        )
    )


def bought(open_port: port.CommandPort, side: str = "WEST") -> str:
    """Buy one rifle Squad for `side` and return the id it was minted with."""
    judgement = open_port.submit(
        Command("purchase", side, {"squad_type": "rifle"}), acting_side=side
    )
    return str(judgement.result["squad"])


def standing(open_port: port.CommandPort, squad_id: str, side: str = "WEST") -> squads.Order:
    """Return the Order that Squad is currently carrying."""
    squad = open_port.campaign.roster.of(squad_id, side)
    assert squad is not None
    return squad.order


def test_a_purchase_is_accepted_and_costs_its_price(open_port: port.CommandPort) -> None:
    judgement = open_port.submit(
        Command("purchase", "WEST", {"squad_type": "rifle"}), acting_side="WEST"
    )
    assert judgement.accepted
    assert open_port.ledger.balance("WEST") == 200


def test_an_accepted_purchase_reports_the_remaining_funds_and_what_it_bought(
    open_port: port.CommandPort,
) -> None:
    # Advisory only: the UI may show it, but the world is never mutated from a
    # reply (ADR-0012). The Squad id is there so a Commander can order what it
    # just bought without waiting for the next observation.
    judgement = open_port.submit(
        Command("purchase", "WEST", {"squad_type": "rifle"}), acting_side="WEST"
    )
    assert judgement.result == {"squad": "WEST-1", "funds": 200}


def test_an_accepted_purchase_queues_its_effect_rather_than_returning_it(
    open_port: port.CommandPort,
) -> None:
    # Every world effect rides the outbox, for both Commanders, so #19 has one
    # effect path to audit rather than two.
    open_port.submit(Command("purchase", "WEST", {"squad_type": "rifle"}), acting_side="WEST")
    (entry,) = open_port.outbox.pending()
    assert entry.message["effect"] == "squad_spawned"
    assert entry.message["side"] == "WEST"
    assert entry.message["args"]["squad_type"] == "rifle"


def test_a_purchase_beyond_the_balance_is_rejected_and_costs_nothing(
    open_port: port.CommandPort,
) -> None:
    for _ in range(3):
        open_port.submit(Command("purchase", "WEST", {"squad_type": "rifle"}), acting_side="WEST")
    judgement = open_port.submit(
        Command("purchase", "WEST", {"squad_type": "rifle"}), acting_side="WEST"
    )
    assert not judgement.accepted
    assert judgement.code == "insufficient_funds"
    assert open_port.ledger.balance("WEST") == 0
    assert len(open_port.outbox.pending()) == 3


def test_a_command_nobody_implements_is_rejected(open_port: port.CommandPort) -> None:
    judgement = open_port.submit(Command("bombard", "WEST", {}), acting_side="WEST")
    assert judgement.code == "unknown_command"


def test_a_purchase_of_something_not_sold_is_rejected(open_port: port.CommandPort) -> None:
    judgement = open_port.submit(
        Command("purchase", "WEST", {"squad_type": "battleship"}), acting_side="WEST"
    )
    assert judgement.code == "malformed_command"


def test_a_purchase_without_a_squad_type_is_rejected(open_port: port.CommandPort) -> None:
    judgement = open_port.submit(Command("purchase", "WEST", {}), acting_side="WEST")
    assert judgement.code == "malformed_command"


def test_commanding_a_side_that_is_not_yours_is_rejected(open_port: port.CommandPort) -> None:
    # The gateway stamps the acting side server-side; a Command claiming another
    # side is a caller reaching past its own authority.
    judgement = open_port.submit(
        Command("purchase", "EAST", {"squad_type": "rifle"}), acting_side="WEST"
    )
    assert judgement.code == "wrong_side"
    assert open_port.ledger.balance("EAST") == 300
    assert open_port.outbox.pending() == []


def test_the_rejection_codes_are_the_only_ones_the_port_issues() -> None:
    # The SQF side is generated from this set, so a code added without going
    # through here is one the game has never been told about.
    assert (
        frozenset(
            {
                "insufficient_funds",
                "unknown_command",
                "malformed_command",
                "wrong_side",
                "unknown_squad",
                "already_held",
            }
        )
        == port.REJECTION_CODES
    )


def test_an_order_is_recorded_against_the_squad_and_announced_as_an_effect(
    open_port: port.CommandPort,
) -> None:
    squad = bought(open_port)
    judgement = open_port.submit(
        Command("order", "WEST", {"squad": squad, "order": "capture", "objective": "agia_marina"}),
        acting_side="WEST",
    )
    assert judgement.accepted
    assert standing(open_port, squad) == squads.Order("capture", "agia_marina")
    assert {
        "effect": "order_issued",
        "side": "WEST",
        "args": {"squad": squad, "order": "capture", "objective": "agia_marina"},
    } in [entry.message for entry in open_port.outbox.pending()]


def test_a_later_order_supersedes_the_one_before_it(open_port: port.CommandPort) -> None:
    # Standing, not accumulating: a Squad carries one Order, and the newest one
    # is what the world is driven from.
    squad = bought(open_port)
    for kind in ("capture", "defend"):
        open_port.submit(
            Command("order", "WEST", {"squad": squad, "order": kind, "objective": "girna"}),
            acting_side="WEST",
        )
    assert standing(open_port, squad) == squads.Order("defend", "girna")


def test_reserve_needs_no_objective(open_port: port.CommandPort) -> None:
    squad = bought(open_port)
    judgement = open_port.submit(
        Command("order", "WEST", {"squad": squad, "order": "reserve", "objective": ""}),
        acting_side="WEST",
    )
    assert judgement.accepted
    assert judgement.result["objective"] == ""


def test_reserve_refuses_an_objective_rather_than_ignoring_it(open_port: port.CommandPort) -> None:
    # Dropping it silently would hide a UI bug behind an Order that looked
    # accepted and sent the Squad somewhere else.
    squad = bought(open_port)
    judgement = open_port.submit(
        Command("order", "WEST", {"squad": squad, "order": "reserve", "objective": "girna"}),
        acting_side="WEST",
    )
    assert judgement.code == "malformed_command"


def test_capturing_ground_your_own_side_holds_is_rejected(open_port: port.CommandPort) -> None:
    # Acceptance criterion 4 on #3: a nonsensical Order is refused rather than
    # quietly accepted as a no-op, so a Commander is told why.
    open_port.campaign.observe(30, {"agia_marina": ["WEST"]})
    squad = bought(open_port)
    judgement = open_port.submit(
        Command("order", "WEST", {"squad": squad, "order": "capture", "objective": "agia_marina"}),
        acting_side="WEST",
    )
    assert judgement.code == "already_held"
    assert "agia_marina" in judgement.detail
    assert standing(open_port, squad) == squads.RESERVE


def test_defending_ground_your_own_side_holds_is_the_point_of_defending(
    open_port: port.CommandPort,
) -> None:
    open_port.campaign.observe(30, {"agia_marina": ["WEST"]})
    squad = bought(open_port)
    judgement = open_port.submit(
        Command("order", "WEST", {"squad": squad, "order": "defend", "objective": "agia_marina"}),
        acting_side="WEST",
    )
    assert judgement.accepted


def test_capturing_ground_the_other_side_holds_is_allowed(open_port: port.CommandPort) -> None:
    open_port.campaign.observe(30, {"agia_marina": ["EAST"]})
    squad = bought(open_port)
    judgement = open_port.submit(
        Command("order", "WEST", {"squad": squad, "order": "capture", "objective": "agia_marina"}),
        acting_side="WEST",
    )
    assert judgement.accepted


def test_ordering_a_squad_that_was_never_bought_is_rejected(open_port: port.CommandPort) -> None:
    judgement = open_port.submit(
        Command("order", "WEST", {"squad": "WEST-9", "order": "reserve", "objective": ""}),
        acting_side="WEST",
    )
    assert judgement.code == "unknown_squad"


def test_ordering_the_other_sides_squad_is_rejected(open_port: port.CommandPort) -> None:
    squad = bought(open_port, "EAST")
    judgement = open_port.submit(
        Command("order", "WEST", {"squad": squad, "order": "reserve", "objective": ""}),
        acting_side="WEST",
    )
    assert judgement.code == "unknown_squad"
    assert standing(open_port, squad, "EAST") == squads.RESERVE


@pytest.mark.parametrize(
    ("args", "why"),
    [
        ({"squad": "WEST-1", "order": "advance"}, "no such Order"),
        ({"squad": "WEST-1"}, "no Order at all"),
        ({"order": "reserve"}, "no Squad named"),
        ({"squad": "", "order": "reserve"}, "an empty Squad id"),
        ({"squad": "WEST-1", "order": "capture"}, "Capture with no ground"),
        ({"squad": "WEST-1", "order": "capture", "objective": "narnia"}, "ground off the map"),
    ],
)
def test_an_order_the_rules_cannot_read_is_rejected(
    open_port: port.CommandPort, args: dict[str, object], why: str
) -> None:
    bought(open_port)
    judgement = open_port.submit(Command("order", "WEST", args), acting_side="WEST")
    assert judgement.code == "malformed_command", why


def test_an_order_for_a_side_that_is_not_yours_is_refused_before_the_squad_is_looked_up(
    open_port: port.CommandPort,
) -> None:
    squad = bought(open_port, "EAST")
    judgement = open_port.submit(
        Command("order", "EAST", {"squad": squad, "order": "reserve", "objective": ""}),
        acting_side="WEST",
    )
    assert judgement.code == "wrong_side"
