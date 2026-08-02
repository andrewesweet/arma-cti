"""The Funds ledger and the price table.

ADR-0012 puts strategic state in the daemon, where it is property-testable, and
ADR-0003 makes it snapshot-owned. Prices are authored data so playtest tuning is
an edit rather than a code change (docs/mvp-scope.md).
"""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest
from conftest import REPO

from cti_daemon import economy


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


def test_replacements_cost_the_missing_fraction_of_the_price_discounted() -> None:
    # docs/mvp-scope.md: missing fraction x price x ~0.8 discount. A rifle Squad
    # is 8 men at 100, so half of it back at 0.8 is 40 — and cheaper than the 50
    # the same four men cost as a fraction of a fresh Squad, which is the whole
    # point of the discount.
    table = economy.load(REPO / "config" / "economy.json")
    assert table.reinforce_cost("rifle", 4) == 40
    assert table.reinforce_cost("rifle", 8) == 80


def test_replacing_one_man_is_never_free() -> None:
    # Rounded up: one of eight at 100 and 0.8 is 10 exactly, but the rule is what
    # is under test — a price that rounded down would let a Squad be refilled a
    # man at a time for nothing, which is the one way a fraction is exploitable
    # rather than merely mistuned.
    table = economy.parse(
        {
            "schema_version": economy.SCHEMA_VERSION,
            "starting_funds": 300,
            "stipend": 5,
            "income_tick_seconds": 60,
            "capture_seconds": 30,
            "domination_seconds": 600,
            "reinforce_discount": 0.1,
            "squads": [{"id": "rifle", "display_name": "Rifle", "price": 10, "size": 8}],
        }
    )
    assert table.reinforce_cost("rifle", 1) == 1


def test_a_squad_at_strength_costs_nothing_to_reinforce() -> None:
    # The rules refuse this at the port; the table answering 0 rather than a
    # negative price is what keeps a refusal from depending on one.
    table = economy.load(REPO / "config" / "economy.json")
    assert table.reinforce_cost("rifle", 0) == 0
    assert table.reinforce_cost("rifle", -3) == 0


def test_replacements_for_something_not_sold_have_no_price() -> None:
    table = economy.load(REPO / "config" / "economy.json")
    assert table.reinforce_cost("battleship", 4) is None


@pytest.mark.parametrize("discount", [0, -0.5, 1.5, True, "0.8"])
def test_a_reinforce_discount_that_is_not_a_discount_is_refused(
    authored: dict[str, Any], discount: object
) -> None:
    # Above the price it is not a discount, at zero it is a gift, and `True` is
    # an `int` to `isinstance` and would author a full-price refill.
    broken = copy.deepcopy(authored)
    broken["reinforce_discount"] = discount
    with pytest.raises(economy.EconomyError, match="reinforce_discount"):
        economy.parse(broken)


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


@pytest.mark.parametrize(
    "missing",
    [
        "squads",
        "starting_funds",
        "stipend",
        "income_tick_seconds",
        "capture_seconds",
        "reinforce_discount",
    ],
)
def test_an_economy_table_missing_a_required_key_is_refused_in_its_own_words(
    authored: dict[str, Any], missing: str
) -> None:
    # A bare KeyError names the key and nothing else, and escapes the one error
    # type every caller of this module catches (#88).
    broken = copy.deepcopy(authored)
    del broken[missing]
    with pytest.raises(economy.EconomyError, match=missing):
        economy.parse(broken)


@pytest.mark.parametrize("missing", ["id", "display_name", "price", "size"])
def test_a_squad_missing_a_required_key_is_refused_in_its_own_words(
    authored: dict[str, Any], missing: str
) -> None:
    broken = copy.deepcopy(authored)
    del broken["squads"][0][missing]
    with pytest.raises(economy.EconomyError, match=missing):
        economy.parse(broken)


def test_a_squad_id_that_is_not_a_string_is_refused_rather_than_sorted() -> None:
    # The duplicate check built and sorted the id list before anything checked
    # the ids were strings, so a numeric id died in `sorted` with a TypeError
    # about int and str (#88).
    broken = {
        "schema_version": economy.SCHEMA_VERSION,
        "starting_funds": 300,
        "stipend": 5,
        "income_tick_seconds": 60,
        "capture_seconds": 30,
        "domination_seconds": 600,
        "reinforce_discount": 0.8,
        "squads": [
            {"id": 7, "display_name": "Seven", "price": 100, "size": 8},
            {"id": "rifle", "display_name": "Rifle", "price": 100, "size": 8},
        ],
    }
    with pytest.raises(economy.EconomyError, match=economy.IDENTIFIER_ERROR):
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
