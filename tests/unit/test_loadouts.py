"""The curated loadout menu, and which kit each player has chosen (#172).

Two things live in `cti_daemon.loadouts` and are pinned here. The authored
catalogue is validated the way `config/economy.json` is, because a kit naming a
side we do not play or a unit class that is not a string is a world with a
player in his underwear, discovered in an Arma run rather than in `just unit`.

And `Chosen` is the snapshot's carrier. ADR-0056 persists the *choice* — one
catalogue id per player UID — rather than the engine's loadout array, so the
round trip that has to hold is `restore(serialise(chosen)) == chosen`, which is
ADR-0003's property target arriving one field early: #4 has not built `save` or
`load` yet, and when it does, this is the shape it serialises.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from cti_daemon import loadouts
from cti_daemon.commands import SIDES

AUTHORED = Path(__file__).parents[2] / "addons" / "main" / "catalogue" / "loadouts.json"

# A UID is what `getPlayerUID` hands back: a non-empty string, and nothing else
# is assumed about it here — Steam's shape is not this module's business.
UIDS = st.text(min_size=1, max_size=24)


def _document(**overrides: Any) -> dict[str, Any]:  # noqa: ANN401 — one authored document,
    # whose values are whatever the caller is putting under test.
    """Return the authored catalogue, with fields overridden."""
    return json.loads(AUTHORED.read_text(encoding="utf-8")) | overrides


def _kit(**overrides: Any) -> dict[str, Any]:  # noqa: ANN401 — see `_document`.
    """One well-formed kit, with fields overridden."""
    base = {
        "id": "rifleman",
        "display_name": "Rifleman",
        "units": dict.fromkeys(SIDES, "B_Soldier_F"),
    }
    return base | overrides


def _catalogue(*kits: dict[str, Any]) -> loadouts.Catalogue:
    """Parse a catalogue of exactly these kits."""
    return loadouts.parse({"schema_version": 1, "kits": list(kits)})


# --- the authored document ------------------------------------------------


def test_the_shipped_catalogue_parses() -> None:
    catalogue = loadouts.load(AUTHORED)
    assert catalogue.ids()
    for kit in catalogue.kits:
        for side in SIDES:
            assert kit.unit(side), f"{kit.id} has no {side} unit class"


def test_the_shipped_catalogue_offers_a_kit_per_side_for_every_id() -> None:
    catalogue = loadouts.load(AUTHORED)
    for kit_id in catalogue.ids():
        offered = catalogue.offered(kit_id)
        assert offered is not None
        assert set(offered.units) == set(SIDES)


# --- validation -----------------------------------------------------------


def test_a_document_that_is_not_an_object_is_refused() -> None:
    with pytest.raises(loadouts.LoadoutError, match="must be an object"):
        loadouts.parse([])


def test_a_wrong_schema_version_is_refused() -> None:
    with pytest.raises(loadouts.LoadoutError, match="schema_version"):
        loadouts.parse(_document(schema_version=2))


def test_kits_must_be_a_list() -> None:
    with pytest.raises(loadouts.LoadoutError, match="kits must be a list"):
        loadouts.parse(_document(kits={}))


def test_an_empty_catalogue_is_refused() -> None:
    # A menu with nothing on it is a feature that shipped switched off, and the
    # world would offer an action that does nothing.
    with pytest.raises(loadouts.LoadoutError, match="at least one kit"):
        loadouts.parse(_document(kits=[]))


@pytest.mark.parametrize("missing", ["id", "display_name", "units"])
def test_a_kit_missing_a_required_key_is_refused(missing: str) -> None:
    kit = _kit()
    del kit[missing]
    with pytest.raises(loadouts.LoadoutError, match=missing):
        _catalogue(kit)


@pytest.mark.parametrize("empty", ["", 3])
def test_a_kit_id_must_be_a_non_empty_string(empty: object) -> None:
    with pytest.raises(loadouts.LoadoutError, match="kit id"):
        _catalogue(_kit(id=empty))


def test_a_kit_display_name_must_be_a_non_empty_string() -> None:
    with pytest.raises(loadouts.LoadoutError, match="display_name"):
        _catalogue(_kit(display_name=""))


def test_units_must_carry_exactly_the_playing_sides() -> None:
    with pytest.raises(loadouts.LoadoutError, match="exactly"):
        _catalogue(_kit(units={"WEST": "B_Soldier_F"}))


def test_units_must_not_be_keyed_by_a_side_that_is_not_playing() -> None:
    with pytest.raises(loadouts.LoadoutError, match="exactly"):
        _catalogue(_kit(units=dict.fromkeys(SIDES, "B_Soldier_F") | {"RESISTANCE": "I_Soldier_F"}))


@pytest.mark.parametrize("bad", ["", 7, None])
def test_a_unit_class_must_be_a_non_empty_string(bad: object) -> None:
    with pytest.raises(loadouts.LoadoutError, match="unit class"):
        _catalogue(_kit(units=dict.fromkeys(SIDES, bad)))


def test_units_must_be_an_object() -> None:
    with pytest.raises(loadouts.LoadoutError, match="units"):
        _catalogue(_kit(units=["B_Soldier_F"]))


def test_a_duplicate_kit_id_is_refused() -> None:
    # Two rows under one id is two answers to what a player asked for, and the
    # menu would show the same word twice.
    with pytest.raises(loadouts.LoadoutError, match="duplicate kit id: rifleman"):
        _catalogue(_kit(), _kit(display_name="Rifleman II"))


# --- the catalogue as a lookup -------------------------------------------


def test_a_kit_nobody_authored_is_not_offered() -> None:
    assert _catalogue(_kit()).offered("jetpack") is None


def test_a_kit_has_no_unit_class_for_a_side_that_is_not_playing() -> None:
    assert _catalogue(_kit()).kits[0].unit("RESISTANCE") == ""


def test_the_ids_come_back_in_authored_order() -> None:
    catalogue = _catalogue(_kit(id="a"), _kit(id="b"), _kit(id="c"))
    assert catalogue.ids() == ("a", "b", "c")


def test_an_empty_catalogue_offers_nothing() -> None:
    # The Campaign's default (`Catalogue.empty()`): a daemon wired without an
    # authored catalogue offers no kit rather than every kit.
    assert loadouts.Catalogue.empty().ids() == ()
    assert loadouts.Catalogue.empty().offered("rifleman") is None


# --- the record the snapshot carries -------------------------------------


def test_a_player_who_has_chosen_nothing_wears_nothing_in_particular() -> None:
    assert loadouts.Chosen(_catalogue(_kit())).of("76561198000000000") == ""


def test_a_choice_is_recorded_and_read_back() -> None:
    chosen = loadouts.Chosen(_catalogue(_kit(id="medic")))
    assert chosen.choose("uid-1", "medic")
    assert chosen.of("uid-1") == "medic"


def test_a_kit_the_catalogue_does_not_offer_is_refused_and_recorded_nowhere() -> None:
    chosen = loadouts.Chosen(_catalogue(_kit()))
    assert not chosen.choose("uid-1", "jetpack")
    assert chosen.of("uid-1") == ""


def test_a_choice_replaces_the_one_before_it() -> None:
    chosen = loadouts.Chosen(_catalogue(_kit(id="a"), _kit(id="b")))
    chosen.choose("uid-1", "a")
    chosen.choose("uid-1", "b")
    assert chosen.of("uid-1") == "b"
    assert chosen.serialise() == {"uid-1": "b"}


def test_a_player_without_a_uid_chooses_nothing() -> None:
    # `getPlayerUID` answers "" for a machine with no player unit, and a record
    # filed under the empty string would be one kit shared by every such machine.
    chosen = loadouts.Chosen(_catalogue(_kit()))
    assert not chosen.choose("", "rifleman")
    assert chosen.serialise() == {}


def test_each_player_wears_his_own_choice() -> None:
    chosen = loadouts.Chosen(_catalogue(_kit(id="a"), _kit(id="b")))
    chosen.choose("uid-1", "a")
    chosen.choose("uid-2", "b")
    assert chosen.serialise() == {"uid-1": "a", "uid-2": "b"}


# --- the round trip #4 will serialise ------------------------------------


@given(
    picks=st.dictionaries(UIDS, st.sampled_from(["rifleman", "medic", "marksman"]), max_size=8),
)
def test_a_restored_record_is_the_record_that_was_saved(picks: dict[str, str]) -> None:
    catalogue = _catalogue(_kit(id="rifleman"), _kit(id="medic"), _kit(id="marksman"))
    chosen = loadouts.Chosen(catalogue)
    for uid, kit in picks.items():
        chosen.choose(uid, kit)

    restored, dropped = loadouts.Chosen.restore(catalogue, chosen.serialise())

    assert dropped == ()
    assert restored.serialise() == chosen.serialise()
    for uid, kit in picks.items():
        assert restored.of(uid) == kit


def test_serialise_hands_back_a_copy_rather_than_the_record_itself() -> None:
    # A snapshot writer that mutated what it was given would edit the Campaign
    # it is meant to be photographing.
    chosen = loadouts.Chosen(_catalogue(_kit()))
    chosen.choose("uid-1", "rifleman")
    document = chosen.serialise()
    document["uid-1"] = "jetpack"
    assert chosen.of("uid-1") == "rifleman"


def test_a_saved_kit_the_catalogue_no_longer_offers_is_dropped_and_named() -> None:
    # ADR-0008's forward-compatibility rule: a field that no longer means
    # anything defaults sensibly rather than refusing the save. Retuning the
    # menu must not make last week's Campaign unloadable — but a player quietly
    # back in his default kit with nobody told is the silence this refuses.
    restored, dropped = loadouts.Chosen.restore(
        _catalogue(_kit(id="rifleman")), {"uid-1": "rifleman", "uid-2": "jetpack"}
    )
    assert dropped == ("uid-2",)
    assert restored.of("uid-1") == "rifleman"
    assert restored.of("uid-2") == ""


def test_restoring_nothing_is_a_record_of_nobody() -> None:
    restored, dropped = loadouts.Chosen.restore(_catalogue(_kit()), {})
    assert dropped == ()
    assert restored.serialise() == {}


@pytest.mark.parametrize("document", [[], "rifleman", None, 3])
def test_a_saved_record_that_is_not_an_object_is_refused(document: object) -> None:
    with pytest.raises(loadouts.LoadoutError, match="must be an object"):
        loadouts.Chosen.restore(_catalogue(_kit()), document)


@pytest.mark.parametrize("document", [{"uid-1": 3}, {"uid-1": None}, {"uid-1": ["rifleman"]}])
def test_a_saved_kit_that_is_not_a_string_is_refused(document: object) -> None:
    # Distinct from a kit the catalogue no longer offers: that is a menu that
    # moved, this is a document that was never written by us.
    with pytest.raises(loadouts.LoadoutError, match="kit id"):
        loadouts.Chosen.restore(_catalogue(_kit()), document)


@pytest.mark.parametrize("document", [{3: "rifleman"}, {"": "rifleman"}])
def test_a_saved_record_keyed_by_something_that_is_not_a_uid_is_refused(document: object) -> None:
    with pytest.raises(loadouts.LoadoutError, match="player UID"):
        loadouts.Chosen.restore(_catalogue(_kit()), document)
