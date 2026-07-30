"""The Command Port entry function: the sole mutator of strategic state.

ADR-0012 makes the daemon the rules authority and this function the only door
into the campaign, for the human UI and the AI planner alike. The planner does
not cross the wire — it builds the same Command objects and calls this — so
Commander symmetry is one validator rather than two kept honest by convention.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cti_daemon import economy, port
from cti_daemon.commands import Command
from cti_daemon.outbox import Outbox

REPO = Path(__file__).parents[2]


@pytest.fixture
def open_port() -> port.CommandPort:
    """Return a port with the authored economy and an empty outbox."""
    table = economy.load(REPO / "config" / "economy.json")
    return port.CommandPort(
        table=table, ledger=economy.Ledger(table.starting_funds), outbox=Outbox()
    )


def test_a_purchase_is_accepted_and_costs_its_price(open_port: port.CommandPort) -> None:
    judgement = open_port.submit(
        Command("purchase", "WEST", {"squad_type": "rifle"}), acting_side="WEST"
    )
    assert judgement.accepted
    assert open_port.ledger.balance("WEST") == 200


def test_an_accepted_purchase_reports_the_remaining_funds(open_port: port.CommandPort) -> None:
    # Advisory only: the UI may show it, but the world is never mutated from a
    # reply (ADR-0012).
    judgement = open_port.submit(
        Command("purchase", "WEST", {"squad_type": "rifle"}), acting_side="WEST"
    )
    assert judgement.result == {"funds": 200}


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


def test_the_four_rejection_codes_are_the_only_ones_the_port_issues() -> None:
    # ADR-0012 fixes the set for #12. A fifth code would be a schema change the
    # SQF side has not been told about.
    assert (
        frozenset({"insufficient_funds", "unknown_command", "malformed_command", "wrong_side"})
        == port.REJECTION_CODES
    )
