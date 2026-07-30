"""The Funds ledger and the price table.

ADR-0012 puts strategic state in the daemon, where it is property-testable, and
ADR-0003 makes it snapshot-owned. Prices are authored data so playtest tuning is
an edit rather than a code change (docs/mvp-scope.md).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from cti_daemon import economy

REPO = Path(__file__).parents[2]


@pytest.fixture
def authored() -> dict[str, Any]:
    """Return the authored economy table as a mutable document."""
    return json.loads((REPO / "config" / "economy.json").read_text(encoding="utf-8"))


def test_the_authored_economy_table_is_valid() -> None:
    table = economy.load(REPO / "config" / "economy.json")
    assert table.starting_funds > 0
    assert {squad.id for squad in table.squads} >= {"rifle"}


def test_a_squad_price_is_looked_up_by_id() -> None:
    table = economy.load(REPO / "config" / "economy.json")
    assert table.price("rifle") == 100


def test_an_unknown_squad_type_has_no_price() -> None:
    table = economy.load(REPO / "config" / "economy.json")
    assert table.price("battleship") is None


def test_a_duplicated_squad_id_is_refused(authored: dict[str, Any]) -> None:
    broken = copy.deepcopy(authored)
    broken["squads"].append(copy.deepcopy(broken["squads"][0]))
    with pytest.raises(economy.EconomyError, match="duplicate"):
        economy.parse(broken)


def test_a_negative_price_is_refused(authored: dict[str, Any]) -> None:
    broken = copy.deepcopy(authored)
    broken["squads"][0]["price"] = -1
    with pytest.raises(economy.EconomyError, match="price"):
        economy.parse(broken)


def test_an_unknown_schema_version_is_refused(authored: dict[str, Any]) -> None:
    broken = copy.deepcopy(authored)
    broken["schema_version"] = 99
    with pytest.raises(economy.EconomyError, match="schema_version"):
        economy.parse(broken)


def test_both_sides_start_with_the_authored_balance() -> None:
    ledger = economy.Ledger(starting_funds=300)
    assert ledger.balance("WEST") == 300
    assert ledger.balance("EAST") == 300


def test_spending_reduces_only_the_spending_side() -> None:
    ledger = economy.Ledger(starting_funds=300)
    ledger.spend("WEST", 100)
    assert ledger.balance("WEST") == 200
    assert ledger.balance("EAST") == 300


def test_a_side_cannot_spend_what_it_does_not_have() -> None:
    ledger = economy.Ledger(starting_funds=300)
    assert ledger.can_afford("WEST", 300)
    assert not ledger.can_afford("WEST", 301)


def test_spending_more_than_the_balance_is_refused_rather_than_going_negative() -> None:
    # Funds are the whole economy; an overdraft would be a silent gift.
    ledger = economy.Ledger(starting_funds=300)
    with pytest.raises(economy.InsufficientFundsError):
        ledger.spend("WEST", 301)
    assert ledger.balance("WEST") == 300
