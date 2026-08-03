"""What a finished Campaign leaves behind (#35, ADR-0023).

`docs/mvp-scope.md` says a won Campaign is marked complete, gets an end screen
summarising from telemetry, is archived, and is followed by a fresh Campaign next
session. ADR-0023 fixes what "archived" means: a **record of what happened**,
never a state to resume. Nothing here is ever read back — not by the daemon, not
by a later session — which is what makes "a fresh Campaign next boot" a property
of there being nothing to load rather than a rule somebody has to remember.

The summary is read off the telemetry file rather than assembled from campaign
state, and that is the point rather than an implementation detail: an end screen
built from live state could say something the log does not, and then there would
be two accounts of one Campaign. Reading telemetry here does not cross ADR-0003 —
that decision keeps the snapshot authoritative for *campaign state*, and a
summary is not state: no rule consults it, and no Campaign resumes from it.

Counts rather than rows, deliberately. The summary rides the `campaign_won`
effect to the world, and a `callExtension` return truncates past 10,240 bytes in
silence (ADR-0004), so a summary whose size tracked the length of the Campaign
would fail on exactly the long Campaigns worth summarising.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from cti_daemon.campaign import Outcome


def _is_command(row: dict[str, Any]) -> bool:
    """Whether one row is a Command that was accepted, from either Commander.

    Two rows say that, because there are two Commanders and one of them does not
    cross the wire: an AI-issued Command is written down as `command_issued` from
    inside the planning cycle, and a human-issued one arrives as a `request` and
    is written down as one. Counting only the first would report a human
    Commander as having done nothing all Campaign.
    """
    if row.get("event") == "command_issued":
        return True
    return (
        row.get("event") == "request" and row.get("verb") == "command" and row.get("status") == "ok"
    )


def _telemetry_rows(telemetry_path: Path) -> Iterator[dict[str, Any]]:
    """Every telemetry row written so far, skipping any the writer cut short.

    Telemetry is appended under a lock and never rewritten, so a partial line is
    only possible at the very end of a file being written as it is read. One
    unreadable line loses a number off a summary; raising here would lose the
    archive of a Campaign that had genuinely been won.

    Streamed a line at a time rather than read whole (#103). This runs inside the
    `observe` the world is blocked on, and the file has grown for the length of a
    Campaign: holding the whole of a long session's telemetry in memory to count
    five kinds of row is a cost that rises with exactly the Campaigns worth
    summarising, and the frame behind the call waits for all of it.
    """
    if not telemetry_path.exists():
        return
    with telemetry_path.open(encoding="utf-8") as sink:
        for line in sink:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                yield row


def summarise(telemetry_path: Path, outcome: Outcome) -> dict[str, Any]:
    """Build the end screen's summary of one finished Campaign."""
    rows = _telemetry_rows(telemetry_path)

    commands: dict[str, int] = {}
    squads_lost = 0
    income: dict[str, int] = {}
    owners: dict[str, str] = {}
    headquarters: list[dict[str, Any]] = []

    for row in rows:
        event = row.get("event")
        if _is_command(row):
            side = str(row.get("side") or "")
            commands[side] = commands.get(side, 0) + 1
        elif event == "squad_lost":
            squads_lost += 1
        elif event == "income":
            for side, amount in (row.get("paid") or {}).items():
                income[side] = income.get(side, 0) + int(amount)
        elif event == "observation":
            # The last picture written is the last one that moved, which is the
            # board as it stood when the Campaign ended.
            owners = dict(row.get("owners") or {})
        elif event == "hq_destroyed":
            headquarters.append(
                {
                    "base": row.get("base"),
                    "side": row.get("side"),
                    "by": row.get("by"),
                    "at": row.get("at"),
                }
            )

    return {
        "winner": outcome.winner,
        "condition": outcome.condition,
        "at": outcome.at_time,
        "base": outcome.base,
        "owners": owners,
        "income": income,
        "headquarters": headquarters,
        "commands": commands,
        "squads_lost": squads_lost,
    }


def write(directory: Path, summary: dict[str, Any]) -> Path:
    """Archive one finished Campaign and return where it landed.

    Named for the in-game moment it ended rather than for a wall clock: that is
    the number every other row of the run is stamped with, so an archive and the
    telemetry beside it can be lined up without a translation.

    That name is not unique, though, and nothing above makes it so: two
    Campaigns ending on the same condition in the same whole second — one
    directory serving a pool slot's repeated runs, most plausibly — write the
    same filename, and a plain write would let the second silently replace the
    first. So the name is claimed rather than assumed: created exclusively, and
    a taken one steps to `-2`, `-3` and so on. An archive that only ever exists
    to be read afterwards loses nothing by being the second file; it loses
    everything by not being written down (#155).
    """
    directory.mkdir(parents=True, exist_ok=True)
    document = json.dumps(summary, indent=2, ensure_ascii=True) + "\n"
    stem = f"campaign-{summary['condition']}-{int(summary['at'])}"
    attempt = 1
    while True:
        suffix = "" if attempt == 1 else f"-{attempt}"
        path = directory / f"{stem}{suffix}.json"
        try:
            with path.open("x", encoding="utf-8") as sink:
                sink.write(document)
        except FileExistsError:
            attempt += 1
            continue
        return path
