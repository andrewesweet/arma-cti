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


@pytest.mark.parametrize("ask", ["balance", "can_afford", "deposit", "spend"])
def test_a_side_this_campaign_is_not_played_by_holds_no_funds_at_all(ask: str) -> None:
    # Minting a starting balance for any string it was handed made a typo into a
    # fortune, and left the "only playing sides hold Funds" invariant to be
    # remembered at a call site (#66).
    ledger = economy.Ledger(starting_funds=300)
    with pytest.raises(economy.UnknownSideError, match="RESISTANCE"):
        getattr(ledger, ask)("RESISTANCE", *([] if ask == "balance" else [1]))


def test_asking_a_balance_does_not_create_one() -> None:
    # A query that mutates is why the refusal above had to live elsewhere.
    ledger = economy.Ledger(starting_funds=300)
    with pytest.raises(economy.UnknownSideError):
        ledger.balance("WESt")
    assert sorted(ledger.holdings()) == ["EAST", "WEST"]


def test_a_ledger_can_be_built_for_the_sides_it_is_told_about() -> None:
    ledger = economy.Ledger(starting_funds=50, sides=("WEST",))
    assert ledger.balance("WEST") == 50
    with pytest.raises(economy.UnknownSideError):
        ledger.balance("EAST")
