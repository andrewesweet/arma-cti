"""Reconstruct what happened in a run from the daemon's telemetry alone (#39).

The #35 demo ended `timeout` with a Squad 3.8 km short of its target and three
of eight alive, and nothing in the evidence said where the other five died. The
telemetry now carries a row per death; this reads the file back as the sequence
those rows describe, so a failed run is diagnosed by reading rather than by
guessing.

Two jobs, because they are the same reading:

- with no `--expect`, print the timeline for a human;
- with `--expect`, check it against what a probe says it staged, and exit
  non-zero when the record does not contain what the world claims it did. That
  is what makes an in-world casualty test an assertion instead of a screenshot.

Reads a telemetry file that this checkout did not have to produce: nothing here
imports the daemon, so an old run's evidence stays readable.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

# tools/ holds standalone scripts rather than an importable package, so a
# sibling import needs the script's own directory on the path — the same device
# `export_command_schema.py` uses to reach `src/`. Placed before the import it
# enables, which is why the import below sits apart from the block above.
sys.path.insert(0, str(Path(__file__).parent))

from telemetry_log import rows

if TYPE_CHECKING:
    from collections.abc import Callable

# The events that tell the story, in the sense that an operator asking "what
# happened" wants them. Deliberately not every row: `observation`, `request`,
# `income` and `decision` are the run's breathing, and burying five deaths under
# nine hundred heartbeats is the state this tool exists to leave behind.
NARRATED: Final = (
    "squad_spawned",
    "command_issued",
    "plan_refused",
    "casualty",
    "casualties_dropped",
    "squad_lost",
    "hq_destroyed",
    "campaign_won",
    "campaign_archived",
)

# What the probe writes into the server log for each death it staged, and what
# a matching `casualty` row must therefore agree with. A prefix rather than a
# whole grammar: the probe states only the fields it actually controls.
STAGED: Final = "casualty_staged"


def _who(row: dict[str, Any], squad: str, side: str, kind: str) -> str:
    """Name a party to an event the way a person would: Squad, else side, else type."""
    named = row.get(squad) or row.get(side) or row.get(kind) or "?"
    return str(named)


def _casualty(row: dict[str, Any]) -> str:
    """One death, as a sentence: who, where, and by whom."""
    where = row.get("place") or "open ground"
    position = row.get("pos") or []
    at = ",".join(str(round(float(axis))) for axis in position) if position else "?"
    killer = _who(row, "by_squad", "by_side", "by_type")
    vehicle = row.get("by_vehicle")
    weapon = f" from {vehicle}" if vehicle else ""
    return (
        f"{_who(row, 'squad', 'side', 'type')} ({row.get('type', '?')}) "
        f"died at {where} [{at}], killed by {killer}{weapon}"
    )


# How each narrated event reads. A table rather than a ladder of branches: the
# events are a list that grows, and the shape of the code should be that list.
_WORDS: Final[dict[str, Callable[[dict[str, Any]], str]]] = {
    "casualty": _casualty,
    "casualties_dropped": (
        lambda row: f"{row.get('count')} deaths were never recorded — the buffer overflowed"
    ),
    "squad_lost": lambda row: f"{row.get('squad')} is gone from the roster",
    "hq_destroyed": (
        lambda row: f"{row.get('base')}'s HQ ({row.get('side')}) destroyed by {row.get('by')}"
    ),
    "command_issued": lambda row: f"{row.get('side')} {row.get('command')} {row.get('args')}",
    "plan_refused": (
        lambda row: f"{row.get('side')} {row.get('command')} refused: {row.get('code')}"
    ),
}


def _narrate(row: dict[str, Any]) -> str:
    """Put one row into whatever words that event deserves."""
    said = _WORDS.get(str(row.get("event")))
    if said is not None:
        return said(row)
    # An event with no words of its own still gets its fields, because a row
    # nobody wrote a sentence for is exactly the one worth seeing raw.
    return " ".join(f"{key}={value}" for key, value in row.items() if key not in ("event", "at"))


def timeline(records: list[dict[str, Any]]) -> list[str]:
    """Render the narrated rows in the order the run produced them.

    File order, not sorted by `at`: telemetry order is what resolves a mutual
    Decapitation (`docs/mvp-scope.md`), and a reader who cannot trust the two to
    agree is better served by the one the rest of the system already trusts. A
    death's own clock reading is printed beside it, so a re-order is visible.
    """
    return [
        f"{float(row.get('at', 0)):9.1f}  {row.get('event')!s:<18}  {_narrate(row)}"
        for row in records
        if row.get("event") in NARRATED
    ]


def staged(log: Path) -> list[dict[str, str]]:
    """Read the deaths a probe says it staged out of the server log."""
    claims: list[dict[str, str]] = []
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        if STAGED not in line:
            continue
        fields = line.split(STAGED, 1)[1].split()
        claims.append(dict(field.split("=", 1) for field in fields if "=" in field))
    return claims


def unmatched(records: list[dict[str, Any]], claims: list[dict[str, str]]) -> list[dict[str, str]]:
    """Which staged deaths the telemetry does not account for.

    A claim is met by any `casualty` row agreeing with every field the probe
    named — one row per claim, consumed as it matches, so two staged deaths
    cannot both be satisfied by one recorded one.
    """
    deaths = [row for row in records if row.get("event") == "casualty"]
    missing: list[dict[str, str]] = []
    for claim in claims:
        found = next(
            (
                row
                for row in deaths
                if all(str(row.get(field, "")) == value for field, value in claim.items())
            ),
            None,
        )
        if found is None:
            missing.append(claim)
        else:
            deaths.remove(found)
    return missing


def main(argv: list[str] | None = None) -> int:
    """Print a run's timeline, and check it against what a probe staged."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("telemetry", type=Path)
    parser.add_argument(
        "--expect",
        type=Path,
        help="a server log whose casualty_staged lines the timeline must account for",
    )
    args = parser.parse_args(argv)
    if not args.telemetry.exists():
        print(f"no telemetry at {args.telemetry}", file=sys.stderr)  # noqa: T201 — a CLI's output
        return 1

    records = rows(args.telemetry)
    for line in timeline(records):
        print(line)  # noqa: T201 — the timeline IS this script's output

    if args.expect is None:
        return 0

    claims = staged(args.expect)
    if not claims:
        # Nothing claimed is not the same as everything found. A probe that
        # meant to stage deaths and staged none would otherwise pass here.
        print(f"no {STAGED} lines in {args.expect}", file=sys.stderr)  # noqa: T201
        return 1
    missing = unmatched(records, claims)
    for claim in missing:
        print(f"staged but never recorded: {claim}", file=sys.stderr)  # noqa: T201
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
