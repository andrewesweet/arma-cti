"""The free transport ladder a Squad is issued from (#170).

`cti_daemon.motorpool` runs nowhere during a Campaign — the truck costs no
Funds, so it never crosses the wire (ADR-0059). What it exists for is the check
neither authored document can make alone: `config/economy.json` owns how many
men a Squad is bought at (#159), `addons/main/catalogue/transport.json` owns how
many a vehicle carries, and a ladder that seats no Squad the economy sells is a
Squad walking to Agia Marina with men left behind — discovered in a Play Session
rather than here.

So the shipped pair is asserted against itself, and the parser is held to the
same standard `economy.py` and `loadouts.py` are held to: a row with no vehicle
class, a fleet authored out of order, a duplicate id.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from cti_daemon import economy, motorpool

REPO = Path(__file__).parents[2]
AUTHORED = REPO / "addons" / "main" / "catalogue" / "transport.json"
ECONOMY = REPO / "config" / "economy.json"


def _document(**overrides: Any) -> dict[str, Any]:  # noqa: ANN401 — one authored document,
    # whose values are whatever the caller is putting under test.
    """Return the authored catalogue, with fields overridden."""
    return json.loads(AUTHORED.read_text(encoding="utf-8")) | overrides


def _row(**overrides: Any) -> dict[str, Any]:  # noqa: ANN401 — see `_document`.
    """One well-formed transport row, with fields overridden."""
    base = {
        "id": "open_truck",
        "display_name": "Civilian Truck",
        "seats": 17,
        "vehicle": "C_Truck_02_transport_F",
    }
    return base | overrides


def _pool(*fleet: dict[str, Any]) -> motorpool.Motorpool:
    """Parse a motorpool of exactly these rows."""
    return motorpool.parse({"schema_version": 1, "fleet": list(fleet)})


def _issued(pool: motorpool.Motorpool, men: int) -> motorpool.Transport:
    """Return the rung a Squad of `men` is issued, failing if it is issued none.

    The "nothing seats them" answer has tests of its own below; this is for the
    ones about *which* rung, where an unwrapped `weakest_for` would report a
    missing attribute rather than a missing vehicle.
    """
    rung = pool.weakest_for(men)
    assert rung is not None
    return rung


# --- the authored documents, against each other ---------------------------


def test_the_shipped_catalogue_parses() -> None:
    pool = motorpool.load(AUTHORED)

    assert pool.ids() == ("offroad", "open_truck")


def test_every_squad_the_shipped_economy_sells_has_a_ride() -> None:
    # The whole reason this module exists. Both authored files, as they ship.
    pool = motorpool.load(AUTHORED)
    table = economy.load(ECONOMY)

    assert motorpool.capacity_covers(pool, table) == ()


def test_a_squad_no_rung_seats_is_named_rather_than_squeezed_in() -> None:
    # The failure the check is for, staged from the economy's side: a Squad
    # bigger than anything on the ladder is reported by name, not rounded down
    # into the largest vehicle available.
    pool = _pool(_row(seats=6, id="offroad", vehicle="C_Offroad_01_F"))
    table = economy.load(ECONOMY)

    assert motorpool.capacity_covers(pool, table) == ("rifle", "weapons")


# --- the first-match rule -------------------------------------------------


def test_the_weakest_rung_that_seats_the_squad_wins() -> None:
    pool = _pool(
        _row(id="small", seats=4, vehicle="C_Hatchback_01_F"),
        _row(id="middle", seats=6, vehicle="C_Offroad_01_F"),
        _row(id="large", seats=17, vehicle="C_Truck_02_transport_F"),
    )

    # Exactly seated counts as seated: a rung that carries six carries six.
    assert _issued(pool, 6).id == "middle"
    assert _issued(pool, 7).id == "large"
    assert _issued(pool, 1).id == "small"


def test_a_squad_nothing_seats_gets_nothing_rather_than_the_biggest() -> None:
    # None rather than the last rung: men left standing at the Base is a menu to
    # fix, and returning the largest vehicle would hide it.
    pool = _pool(_row(seats=6, vehicle="C_Offroad_01_F"))

    assert pool.weakest_for(8) is None


def test_the_shipped_ladder_puts_an_eight_man_squad_in_the_open_truck() -> None:
    # The human's own concrete ("a civilian open truck perhaps?"), for the Squad
    # size the shipped economy sells: the Offroad is the more basic rung and does
    # not seat eight, so the rule reaches past it.
    pool = motorpool.load(AUTHORED)

    assert _issued(pool, 8).vehicle == "C_Truck_02_transport_F"


def test_an_empty_motorpool_offers_nothing() -> None:
    assert motorpool.Motorpool.empty().weakest_for(1) is None
    assert motorpool.Motorpool.empty().ids() == ()


# --- what the parser refuses ----------------------------------------------


def test_a_document_that_is_not_an_object_is_refused() -> None:
    with pytest.raises(motorpool.MotorpoolError, match="must be an object"):
        motorpool.parse([])


def test_a_schema_version_from_another_era_is_refused() -> None:
    with pytest.raises(motorpool.MotorpoolError, match="schema_version"):
        motorpool.parse(_document(schema_version=99))


def test_a_catalogue_with_no_fleet_key_is_refused() -> None:
    document = _document()
    del document["fleet"]

    with pytest.raises(motorpool.MotorpoolError, match="must carry 'fleet'"):
        motorpool.parse(document)


def test_a_fleet_that_is_not_a_list_is_refused() -> None:
    with pytest.raises(motorpool.MotorpoolError, match="fleet must be a list"):
        motorpool.parse(_document(fleet={}))


def test_an_empty_fleet_is_refused() -> None:
    with pytest.raises(motorpool.MotorpoolError, match="at least one transport"):
        motorpool.parse(_document(fleet=[]))


@pytest.mark.parametrize("bad", ["", 7, None])
def test_a_row_without_a_usable_id_is_refused(bad: object) -> None:
    with pytest.raises(motorpool.MotorpoolError, match="transport id"):
        _pool(_row(id=bad))


def test_a_row_with_no_display_name_is_refused() -> None:
    with pytest.raises(motorpool.MotorpoolError, match="display_name"):
        _pool(_row(display_name=""))


def test_a_row_with_no_vehicle_class_is_refused() -> None:
    # The one a Play Session would meet as a Squad standing beside nothing.
    with pytest.raises(motorpool.MotorpoolError, match="non-empty classname"):
        _pool(_row(vehicle=""))


@pytest.mark.parametrize("bad", [0, -1, 2.5, "8"])
def test_a_row_that_seats_nobody_is_refused(bad: object) -> None:
    with pytest.raises(motorpool.MotorpoolError, match="seats must be"):
        _pool(_row(seats=bad))


def test_a_boolean_does_not_pass_for_a_seat_count() -> None:
    # `isinstance(True, int)` is true, and `True` would author a one-seat truck.
    with pytest.raises(motorpool.MotorpoolError, match="seats must be"):
        _pool(_row(seats=True))


def test_a_duplicate_transport_id_is_refused() -> None:
    with pytest.raises(motorpool.MotorpoolError, match="duplicate transport id: van"):
        _pool(_row(id="van", seats=6), _row(id="van", seats=17))


def test_a_fleet_authored_out_of_order_is_refused() -> None:
    # `weakest_for` is a first-match scan, so an unsorted file would answer the
    # ruling's "weakest sufficient" with whatever the author happened to type
    # first. Checked rather than sorted on load, because the order is a design
    # statement and silently reordering it would hide an authoring mistake.
    with pytest.raises(motorpool.MotorpoolError, match="weakest first"):
        _pool(_row(id="large", seats=17), _row(id="small", seats=6))


def test_two_rungs_of_equal_size_may_be_authored_in_either_order() -> None:
    # Which of two equally-seated vehicles is the more basic is not a fact about
    # seats, so it stays the author's and the check does not have an opinion.
    pool = _pool(
        _row(id="van", seats=6, vehicle="C_Van_01_transport_F"),
        _row(id="offroad", seats=6, vehicle="C_Offroad_01_F"),
    )

    assert _issued(pool, 6).id == "van"
