"""Reading the daemon's telemetry file back, for the tools that read runs.

One reader, shared by `timeline.py` and `push_path_report.py`, which had a
verbatim copy each (#87). Deliberately *not* shared with `cti_daemon.archive`:
that one is the daemon reading its own file inside its own process, and these
two are pointed at evidence from runs this checkout did not produce. The
isolation is the point — a tool that imported the daemon could not read an old
run's telemetry once the daemon moved on.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


def rows(path: Path) -> list[dict[str, Any]]:
    """Read a telemetry log, skipping anything that is not a record.

    A truncated last line is ordinary: telemetry is appended while the world
    runs, and a run that was killed mid-write is still a run worth reading.
    """
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records
