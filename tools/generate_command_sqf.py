"""Generate the SQF side of the Command Port schema.

ADR-0012 wants one schema source and SQF constructors derived from it, so a
Command the game can build and a Command the daemon accepts cannot drift.
Python is that source (`cti_daemon.commands`, plus the authored price table);
this writes what SQF needs to construct and validate Commands, and to show
prices in the UI.

`--check` compares against the file on disk, so a stale copy is a
`schema_stale` failure in `just check` rather than a surprise mid-session.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from cti_daemon import commands, economy, port

BANNER = (
    "// Generated from src/cti_daemon/commands.py and config/economy.json by\n"
    "// tools/generate_command_sqf.py. Do not edit by hand: change the source\n"
    "// and run `just generate`.\n"
)
HEADER = (
    "/*\n"
    " * Author: arma-cti (generated)\n"
    " * The Command Port schema, as SQF sees it: which Commands exist and what\n"
    " * each needs, which sides command, the rejection codes the daemon can\n"
    " * return, and the Squad price table for display.\n"
    " *\n"
    " * Read through cti_fnc_command rather than called directly.\n"
    " *\n"
    " * Arguments: none\n"
    " *\n"
    " * Return Value: schema <HASHMAP>\n"
    " */\n"
)
INDENT = "    "


def _string(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _array(values: list[str]) -> str:
    return "[" + ", ".join(values) + "]"


def _pairs(pairs: list[tuple[str, str]], depth: int) -> str:
    pad = INDENT * depth
    inner = ",\n".join(f"{pad}{INDENT}[{_string(key)}, {value}]" for key, value in pairs)
    return f"createHashMapFromArray [\n{inner}\n{pad}]"


def render(table: economy.EconomyTable) -> str:
    """Build the generated SQF file."""
    catalogue = _pairs(
        [
            (name, _array([_string(arg) for arg in args]))
            for name, args in commands.CATALOGUE.items()
        ],
        1,
    )
    effects = _pairs(
        [(name, _array([_string(arg) for arg in args])) for name, args in commands.EFFECTS.items()],
        1,
    )
    squads = _pairs(
        [
            (
                squad.id,
                _pairs(
                    [
                        ("display_name", _string(squad.display_name)),
                        ("price", str(squad.price)),
                        ("size", str(squad.size)),
                    ],
                    3,
                ),
            )
            for squad in table.squads
        ],
        1,
    )
    body = _pairs(
        [
            ("commands", catalogue),
            ("effects", effects),
            ("sides", _array([_string(side) for side in commands.SIDES])),
            ("rejection_codes", _array([_string(code) for code in sorted(port.REJECTION_CODES)])),
            ("starting_funds", str(table.starting_funds)),
            ("squads", squads),
        ],
        0,
    )
    return BANNER + HEADER + body + "\n"


def main(argv: list[str] | None = None) -> int:
    """Write the generated schema, or check the one on disk is current."""
    repo = Path(__file__).parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--economy", type=Path, default=repo / "config/economy.json")
    parser.add_argument(
        "--output", type=Path, default=repo / "addons/main/generated/fn_commandSchema.sqf"
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    rendered = render(economy.load(args.economy))
    if args.check:
        current = args.output.read_text(encoding="utf-8") if args.output.exists() else ""
        if current != rendered:
            message = f"schema_stale: {args.output} is not what the schema source would write."
            print(f"{message} Run `just generate`.", file=sys.stderr)  # noqa: T201 — the gate's channel
            return 1
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
