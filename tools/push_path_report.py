"""Read a run's push-path budget back off the daemon's telemetry (#17).

Two Commanders double the traffic on the path that carries work into the world,
and the numbers that bound it are both documented rather than guessed:

- **The drain.** `ExtensionCallback` is drained at most 100 times per frame
  (ADR-0004, `topics/Extensions.wiki`). Our effects ride a poll rather than a
  callback, but the ceiling is the same order and the same shape: how much one
  handover can carry before the world has to take it across frames. So the
  headroom is that cap against the *largest* single handover a run made, never
  the average — a quiet minute flatters an average and cannot flatter a peak.
- **The stall.** Both planners run inside the world's blocking `observe` call,
  which trips `EXECUTION_WARNING_TAKES_TOO_LONG` past 1000 ms and stalls the
  frame for the duration (ADR-0005). So the budget under load is the worst
  `observe` a run served, as a percentage of that cap.

Prints `key=value` lines, which is what `spike/run.sh` records into
`results.env`. A number nobody wrote down is one the next session re-measures.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Final

# tools/ holds standalone scripts rather than an importable package, so a
# sibling import needs the script's own directory on the path — the same device
# `export_command_schema.py` uses to reach `src/`. Placed before the import it
# enables, which is why the import below sits apart from the block above.
sys.path.insert(0, str(Path(__file__).parent))

from telemetry_log import rows

# What the engine drains per frame (ADR-0004).
DRAIN_CAP: Final = 100

# What a blocking `callExtension` may cost before the engine complains, in
# microseconds (ADR-0005).
STALL_CAP_US: Final = 1_000_000

# The sides a Campaign is played by. Named here rather than imported, because
# this reads a log rather than driving a daemon and must survive being pointed
# at telemetry from a run this checkout did not produce.
SIDES: Final = ("WEST", "EAST")


def _percentile(values: list[int], fraction: float) -> int:
    """Return the value at `fraction` through a sorted list, nearest-rank."""
    if not values:
        return 0
    ordered = sorted(values)
    rank = max(1, round(fraction * len(ordered)))
    return ordered[rank - 1]


def report(path: Path) -> list[str]:
    """Return the run's push-path numbers as `key=value` lines."""
    records = rows(path)

    handed = [int(row["handed"]) for row in records if row.get("event") == "outbox_handed"]
    biggest = max(handed, default=0)
    lines = [
        f"outbox_drains={len(handed)}",
        f"outbox_handed_total={sum(handed)}",
        f"outbox_max_handed={biggest}",
        # Unmeasured rather than infinite: a run that pushed nothing has not
        # demonstrated headroom, it has demonstrated nothing.
        f"push_path_headroom_x={round(DRAIN_CAP / biggest, 1) if biggest else 'unmeasured'}",
        f"push_path_drain_cap={DRAIN_CAP}",
    ]

    observes = [
        int(row["duration_us"])
        for row in records
        if row.get("event") == "request" and row.get("verb") == "observe"
    ]
    lines += [
        f"observe_calls={len(observes)}",
        f"observe_p50_us={_percentile(observes, 0.5)}",
        f"observe_p95_us={_percentile(observes, 0.95)}",
        f"observe_max_us={max(observes, default=0)}",
        f"observe_stall_budget_pct={round(100 * max(observes, default=0) / STALL_CAP_US, 2)}",
    ]

    for side in SIDES:
        for event, name in (("decision", "decisions"), ("command_issued", "commands")):
            counted = sum(
                1 for row in records if row.get("event") == event and row.get("side") == side
            )
            lines.append(f"{name}_{side}={counted}")
    lines.append(f"plan_refused={sum(1 for row in records if row.get('event') == 'plan_refused')}")
    return lines


def main(argv: list[str] | None = None) -> int:
    """Print one run's push-path numbers."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("telemetry", type=Path)
    args = parser.parse_args(argv)
    if not args.telemetry.exists():
        print(f"no telemetry at {args.telemetry}", file=sys.stderr)  # noqa: T201 — a CLI's output
        return 1
    for line in report(args.telemetry):
        print(line)  # noqa: T201 — the report IS this script's output
    return 0


if __name__ == "__main__":
    sys.exit(main())
