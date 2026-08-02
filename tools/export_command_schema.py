"""Export the SQF side of the Command Port schema as JSON.

ADR-0012 wants one schema source and SQF constructors derived from it, so a
Command the game can build and a Command the daemon accepts cannot drift.
Python is that source (`cti_daemon.commands`, `cti_daemon.port`, plus the
authored price table), and unlike the map manifests it is not a file that can
simply be shipped — something has to write it out.

ADR-0017 changes what that something writes. The engine has parsed JSON since
2.18 (`fromJSON`), so this exports a JSON document the addon reads with
`loadFile` rather than rendering SQF literals it would have to escape by hand.
The escaping-prone half of the old generator is gone; the export itself stays,
because there is no authored file here to ship in its place.

`--check` compares against the file on disk, so a stale copy is a
`schema_stale` failure in `just check` rather than a surprise mid-session.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from cti_daemon import commands, economy, port, protocol, report, squads


def render(table: economy.EconomyTable) -> str:
    """Build the exported schema document."""
    document = {
        # A note the engine will read back as data rather than as a comment:
        # JSON has no comment syntax, and `loadFile` does not preprocess, so
        # the warning has to live in the document itself.
        "_generated_by": (
            "tools/export_command_schema.py. Do not edit by hand: "
            "change the Python source and run `just generate`"
        ),
        # What a reply is allowed to be read as, by status (#96/#97,
        # ADR-0036). Exported beside the Command catalogue for the same reason
        # the catalogue is: `cti_fnc_daemonCall` branches on these keys, and a
        # branch derived from the daemon's own module cannot drift from it.
        "reply_envelope": {
            outcome: list(keys) for outcome, keys in protocol.REPLY_ENVELOPE.items()
        },
        # What the world reports back, shape by shape (#74). The outbound
        # catalogue's counterpart: `cti_fnc_reportObject` builds every named
        # object in the observe report against these names, so the document the
        # samplers assemble and the document `cti_daemon.report` reads are one
        # declaration rather than two that agree by convention.
        "observe_report": report.exported(),
        "commands": {name: list(args) for name, args in commands.CATALOGUE.items()},
        "effects": {name: list(args) for name, args in commands.EFFECTS.items()},
        "sides": list(commands.SIDES),
        "orders": list(squads.ORDERS),
        "orders_needing_place": list(squads.NEEDS_PLACE),
        "rejection_codes": sorted(port.REJECTION_CODES),
        "starting_funds": table.starting_funds,
        "squads": {
            squad.id: {
                "display_name": squad.display_name,
                "price": squad.price,
                "size": squad.size,
            }
            for squad in table.squads
        },
    }
    return json.dumps(document, indent=2, ensure_ascii=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Write the exported schema, or check the one on disk is current."""
    repo = Path(__file__).parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--economy", type=Path, default=repo / "config/economy.json")
    parser.add_argument(
        "--output", type=Path, default=repo / "addons/main/generated/command-schema.json"
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
