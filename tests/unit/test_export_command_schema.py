"""The Command Port schema export.

The Command catalogue, the effect catalogue and the rejection codes live in
Python rather than in an authored file, so unlike the map manifests they cannot
simply be shipped — something has to write them out. What ADR-0017 changes is
the *rendering*: JSON the engine parses with `fromJSON`, not SQF literals this
tool has to escape by hand. So what is tested here is that the export is the
Python source and stays the Python source.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from cti_daemon import commands, economy, port, squads

if TYPE_CHECKING:
    from types import ModuleType

REPO = Path(__file__).parents[2]

# tools/ is a directory of standalone scripts rather than a package, loaded the
# way tests/unit/test_pack_pbo.py loads its subject.
_SPEC = importlib.util.spec_from_file_location(
    "export_command_schema", REPO / "tools" / "export_command_schema.py"
)
assert _SPEC is not None
assert _SPEC.loader is not None
export_command_schema: ModuleType = importlib.util.module_from_spec(_SPEC)
sys.modules["export_command_schema"] = export_command_schema
_SPEC.loader.exec_module(export_command_schema)


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
    assert exported["orders_needing_objective"] == list(squads.NEEDS_OBJECTIVE)


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
