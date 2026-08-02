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

# tools/ holds standalone scripts rather than an importable package, and the
# daemon lives under src/. This is what lets `uv run python tools/...` reach it
# without the package being installed.
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from cti_daemon import (
    budget,
    commands,
    contacts,
    economy,
    observation,
    planner,
    port,
    protocol,
    report,
    squads,
)


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
        # And what goes back out: the Observation document a Commander plans
        # against, field by field (#163). The last wire family that was mirrored
        # by hand — `observation.serialise` named the keys and the map UI read
        # them as literals, so a rename failed in-world on the human's own path
        # and nowhere earlier. Declared here, the SQF literals have something to
        # be tested against without Arma.
        "observation": observation.exported(),
        # The engine's own return cap, and where the world refuses to go quietly
        # (#78). `cti_fnc_daemonCall` reads the guard from here rather than
        # carrying a literal held equal to the Python one by a source-grep test:
        # a change to the budget is a `just generate` away from the SQF that
        # enforces it, and `just check` fails a stale export as `schema_stale`.
        "return_cap_bytes": budget.RETURN_CAP_BYTES,
        "reply_guard_bytes": budget.REPORT_GUARD_BYTES,
        # How a sighting count becomes a band, and how a band becomes a number
        # of Squads (#110). Exported for the same reason the catalogue is, and
        # the reason is a probe: `spike/probes/massed-assault.sqf` asserted
        # against 4/9/25 and a ceiling of 4 written out in SQF, under a comment
        # claiming there was no path from a Python table into a mission. There
        # is — this file is it, and it has been since ADR-0017. A copy costs
        # nothing until the table is retuned, and then the probe goes red (or
        # worse, stays green) about a rule it is no longer reading.
        #
        # `echelons` keeps the source's own descending order, because the table
        # is a cascade and the first floor a count clears is the band it is in.
        "echelons": [[floor, name] for floor, name in contacts.ECHELONS],
        "assault_mass": dict(planner.ASSAULT_MASS),
        "commands": {name: list(args) for name, args in commands.CATALOGUE.items()},
        "effects": {name: list(args) for name, args in commands.EFFECTS.items()},
        "sides": list(commands.SIDES),
        "orders": list(squads.ORDERS),
        "orders_needing_place": list(squads.NEEDS_PLACE),
        "rejection_codes": sorted(port.REJECTION_CODES),
        "starting_funds": table.starting_funds,
        # The price table the UI displays, and — since #79 — the roster each
        # Squad type is spawned from. `fn_effectApply` used to hold the two
        # classnames itself and ignore the `squad_type` it was sold; the
        # composition travels with the price now, so the table the daemon
        # charges against and the men the world puts on the ground are one
        # authored document rather than two that agree by coincidence.
        "squads": {
            squad.id: {
                "display_name": squad.display_name,
                "price": squad.price,
                "size": squad.size,
                "composition": {side: list(squad.roster(side)) for side in commands.SIDES},
            }
            for squad in table.squads
        },
    }
    return json.dumps(document, indent=2, ensure_ascii=True) + "\n"


def _verify(output: Path, rendered: str) -> int:
    """Compare the file on disk against what the source would write."""
    current = output.read_text(encoding="utf-8") if output.exists() else ""
    if current != rendered:
        message = f"schema_stale: {output} is not what the schema source would write."
        print(f"{message} Run `just generate`.", file=sys.stderr)  # noqa: T201 — the gate's channel
        return 1
    return 0


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
        return _verify(args.output, rendered)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
