"""Compute seat occupancy over a window of real dispatches (#295).

`just queue state` answers "how many are in flight *now*". That number cannot
show a sawtooth, and a sawtooth is what #295 filed: occupancy at the WIP limit
for a few minutes after a refill burst, then a long trough nobody was awake to
see. This program answers the other question — how much of the ruled capacity a
window actually used — from the dispatch records alone.

It reads `~/.arma-cti/dispatches/*/dispatch.json` and `result.json` and never
writes to them, on the same view-not-writer reasoning as the ledger. A dispatch
with no `result.json` is still running and is counted as occupied to the end of
the window; that is the honest reading of the record, and it is stated in the
output as `running=` rather than left to be inferred. A closeout carrying the
stop sweep's `terminal_state`, or one with no run-owned `started_at`, attests no
span and contributes no occupancy.

The output is agent-minutes, not a percentage, because the loss is what the
intervention has to move: `lost=` is capacity the seat was entitled to under the
human's WIP ruling and did not use. It carries no verdict — a block may be
legitimately short of eligible work, and this program cannot see the queue.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

DEFAULT_DISPATCH_DIR = Path.home() / ".arma-cti" / "dispatches"
EXIT_REFUSED = 2
SECONDS_PER_MINUTE = 60


def parse_moment(text: str) -> datetime:
    """Read one ISO-8601 instant, accepting both the `Z` and `+00:00` spellings."""
    normalised = text.replace("Z", "+00:00")
    moment = datetime.fromisoformat(normalised)
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def read_spans(dispatch_dir: Path) -> tuple[tuple[datetime, datetime | None, str], ...]:
    """Read spans with run-owned bounds; a missing result means still running."""
    spans: list[tuple[datetime, datetime | None, str]] = []
    for record_path in sorted(dispatch_dir.expanduser().glob("*/dispatch.json")):
        record: dict[str, Any] = json.loads(record_path.read_text(encoding="utf-8"))
        result_path = record_path.parent / "result.json"
        ended: datetime | None = None
        if result_path.is_file():
            result: dict[str, Any] = json.loads(result_path.read_text(encoding="utf-8"))
            if "terminal_state" in result or "stopped_by" in result:
                continue
            started = result.get("started_at")
            if not started:
                continue
            if result.get("ended_at"):
                ended = parse_moment(str(result["ended_at"]))
        else:
            started = record.get("started_at") or record.get("planned_at")
            if not started:
                continue
        spans.append((parse_moment(str(started)), ended, str(record.get("dispatch_id", ""))))
    return tuple(spans)


def occupancy_series(
    spans: Iterable[tuple[datetime, datetime | None, str]],
    since: datetime,
    until: datetime,
) -> tuple[int, ...]:
    """Count, for each whole minute of the window, how many dispatches were live."""
    minutes = int((until - since).total_seconds() // SECONDS_PER_MINUTE)
    materialised = tuple(spans)
    series: list[int] = []
    for index in range(minutes):
        moment = since.timestamp() + index * SECONDS_PER_MINUTE
        live = sum(
            1
            for started, ended, _ in materialised
            if started.timestamp() <= moment and (ended is None or moment < ended.timestamp())
        )
        series.append(live)
    return tuple(series)


def running_ids(
    spans: Iterable[tuple[datetime, datetime | None, str]],
    since: datetime,
    until: datetime,
) -> tuple[str, ...]:
    """Name the dispatches counted as occupied only because they had not finished."""
    return tuple(
        dispatch_id
        for started, ended, dispatch_id in spans
        if ended is None and started < until and started >= since
    )


def report_lines(
    series: Sequence[int],
    limit: int,
    since: datetime,
    until: datetime,
    running: Sequence[str],
) -> tuple[str, ...]:
    """Render the window's agent-minutes without turning them into a verdict."""
    used = sum(series)
    capacity = limit * len(series)
    mean = used / len(series) if series else 0.0
    return (
        f"window={since.isoformat()}/{until.isoformat()}",
        f"minutes={len(series)}",
        f"limit={limit}",
        f"capacity={capacity}",
        f"used={used}",
        f"lost={capacity - used}",
        f"mean_occupancy={mean:.2f}",
        f"running={','.join(running) if running else 'none'}",
        f"series={''.join(str(min(value, 9)) for value in series)}",
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the window, the ruled limit, and the record directory to read."""
    parser = argparse.ArgumentParser(prog="occupancy", description=__doc__)
    parser.add_argument("--since", required=True)
    parser.add_argument("--until", required=True)
    parser.add_argument("--limit", type=int, required=True)
    parser.add_argument("--dispatch-dir", type=Path, default=DEFAULT_DISPATCH_DIR)
    return parser.parse_args(argv)


def emit(lines: tuple[str, ...], code: int) -> int:
    """Print a report to stdout and a refusal to stderr."""
    stream = sys.stdout if code == 0 else sys.stderr
    for line in lines:
        print(line, file=stream)
    return code


def main(argv: list[str] | None = None) -> int:
    """Report one window's occupancy, or refuse by name without inventing a number."""
    args = parse_args(argv)
    if args.limit <= 0:
        return emit(("refusal=limit_not_positive", f"limit={args.limit}"), EXIT_REFUSED)
    try:
        since = parse_moment(args.since)
        until = parse_moment(args.until)
    except ValueError as error:
        return emit(("refusal=window_unreadable", f"detail={error}"), EXIT_REFUSED)
    if until <= since:
        return emit(("refusal=window_not_forward", f"since={since}"), EXIT_REFUSED)
    try:
        spans = read_spans(args.dispatch_dir)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return emit(("refusal=records_unreadable", f"detail={error}"), EXIT_REFUSED)
    series = occupancy_series(spans, since, until)
    running = running_ids(spans, since, until)
    return emit(report_lines(series, args.limit, since, until, running), 0)


if __name__ == "__main__":
    sys.exit(main())
