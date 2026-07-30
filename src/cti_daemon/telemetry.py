"""Structured telemetry, written as JSON lines.

Observability only. ADR-0003 makes the snapshot the authoritative campaign
state, so nothing here is ever read back as state — which is precisely why a
failure to write is swallowed: a telemetry bug must not be able to fail a
request, let alone corrupt a Campaign.
"""

from __future__ import annotations

import json
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


class Telemetry:
    """Appends one JSON object per event to a file."""

    def __init__(self, path: Path) -> None:
        """Record where events go. The file is created on first write."""
        self._path = path
        self._lock = threading.Lock()

    def record(self, event: str, **fields: object) -> None:
        """Append one event. Never raises."""
        record = {"at_ns": time.time_ns(), "event": event, **fields}
        line = json.dumps(record, separators=(",", ":"), default=repr)
        try:
            with self._lock, self._path.open("a", encoding="utf-8") as sink:
                sink.write(line + "\n")
        except OSError:
            # Observability must never be able to fail a request (ADR-0003).
            return
