"""The Command Port schema export.

The Command catalogue, the effect catalogue and the rejection codes live in
Python rather than in an authored file, so unlike the map manifests they cannot
simply be shipped — something has to write them out. What ADR-0017 changes is
the *rendering*: JSON the engine parses with `fromJSON`, not SQF literals this
tool has to escape by hand. So what is tested here is that the export is the
Python source and stays the Python source.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

import pytest
from conftest import REPO, load_tool

from cti_daemon import commands, contacts, economy, planner, port, squads

if TYPE_CHECKING:
    from pathlib import Path

export_command_schema = load_tool("export_command_schema")


@pytest.fixture
def exported() -> dict[str, object]:
    """Return the schema as the tool would write it, parsed back."""
    table = economy.load(REPO / "config" / "economy.json")
    return json.loads(export_command_schema.render(table))


def test_the_export_is_json_the_engine_can_parse(exported: dict[str, object]) -> None:
    # fromJSON takes a JSON object to a HashMap; anything else and the addon's
    # type guard fires instead of the schema loading.
    assert isinstance(exported, dict)


def test_the_command_catalogue_is_the_python_catalogue(exported: dict[str, object]) -> None:
    assert exported["commands"] == {name: list(args) for name, args in commands.CATALOGUE.items()}


def test_the_effect_catalogue_is_the_python_catalogue(exported: dict[str, object]) -> None:
    assert exported["effects"] == {name: list(args) for name, args in commands.EFFECTS.items()}


def test_the_rejection_codes_are_the_ports_own(exported: dict[str, object]) -> None:
    assert exported["rejection_codes"] == sorted(port.REJECTION_CODES)


def test_the_sides_and_orders_are_the_domains_own(exported: dict[str, object]) -> None:
    assert exported["sides"] == list(commands.SIDES)
    assert exported["orders"] == list(squads.ORDERS)
    assert exported["orders_needing_place"] == list(squads.NEEDS_PLACE)


def test_the_price_table_carries_what_the_ui_displays(exported: dict[str, object]) -> None:
    table = economy.load(REPO / "config" / "economy.json")
    assert exported["starting_funds"] == table.starting_funds
    prices = cast("dict[str, object]", exported["squads"])
    for squad in table.squads:
        assert prices[squad.id] == {
            "display_name": squad.display_name,
            "price": squad.price,
            "size": squad.size,
        }


def test_the_echelon_cascade_is_the_registers_own(exported: dict[str, object]) -> None:
    # Order carries meaning here: the table is a cascade, so the first floor a
    # count clears is the band it is in, and a re-sorted export would band
    # everything as a team.
    assert exported["echelons"] == [[floor, name] for floor, name in contacts.ECHELONS]


def test_the_assault_mass_table_is_the_planners_own(exported: dict[str, object]) -> None:
    assert exported["assault_mass"] == dict(planner.ASSAULT_MASS)


def test_the_probes_two_numbers_are_derivable_from_the_export(
    exported: dict[str, object],
) -> None:
    """#110's actual requirement, stated as the probe reads it.

    `spike/probes/massed-assault.sqf` wants two numbers: the sighting count at
    which a Contact first bands above a team, and the heaviest mass the doctrine
    table can ask for. Both used to be written out in SQF. Asserted here in the
    same shape the probe computes them, so a change to either Python table that
    the probe could not survive fails in this tier first.
    """
    echelons = cast("list[list[object]]", exported["echelons"])
    mass = cast("dict[str, int]", exported["assault_mass"])
    squad_floor = next(floor for floor, name in echelons if name == "squad")
    assert squad_floor == 4
    assert mass["squad"] == 2
    assert max(mass.values()) == 4


def test_a_retuned_echelon_table_is_a_stale_export(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The deliberate mismatch #110 asks for, on the fields it added.

    `just check` runs `--check`, so this is the `schema_stale` gate biting on a
    Python table the probe reads. Written against the export rather than against
    the shipped file because the shipped file is regenerated, never hand-edited.
    """
    path = tmp_path / "command-schema.json"
    assert export_command_schema.main(["--output", str(path)]) == 0
    assert export_command_schema.main(["--check", "--output", str(path)]) == 0

    monkeypatch.setattr(contacts, "ECHELONS", ((30, "company"), (9, "platoon"), (1, "team")))
    assert export_command_schema.main(["--check", "--output", str(path)]) == 1


def test_a_retuned_assault_mass_table_is_a_stale_export(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "command-schema.json"
    assert export_command_schema.main(["--output", str(path)]) == 0
    monkeypatch.setattr(planner, "ASSAULT_MASS", {"team": 1, "squad": 3})
    assert export_command_schema.main(["--check", "--output", str(path)]) == 1


def test_the_file_the_addon_ships_is_current() -> None:
    # The one thing the SQF side cannot check: the schema source moved and the
    # exported copy did not. `just check` runs exactly this.
    assert export_command_schema.main(["--check"]) == 0


def test_a_stale_export_fails_the_check(tmp_path: Path) -> None:
    stale = tmp_path / "command-schema.json"
    stale.write_text('{"commands": {}}\n', encoding="utf-8")
    assert export_command_schema.main(["--check", "--output", str(stale)]) == 1


def test_a_missing_export_fails_the_check(tmp_path: Path) -> None:
    assert export_command_schema.main(["--check", "--output", str(tmp_path / "absent.json")]) == 1


def test_writing_makes_the_check_pass(tmp_path: Path) -> None:
    path = tmp_path / "command-schema.json"
    assert export_command_schema.main(["--output", str(path)]) == 0
    assert export_command_schema.main(["--check", "--output", str(path)]) == 0
