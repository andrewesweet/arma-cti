"""Structured telemetry, written as JSON lines.

Observability only. ADR-0003 makes the snapshot the authoritative campaign
state, so nothing here is ever read back as state — which is precisely why a
failure to write is swallowed: a telemetry bug must not be able to fail a
request, let alone corrupt a Campaign.

Swallowed, and counted (#143). Keeping the promise and making its cost visible
are not in tension: the counter is in memory, costs a request nothing, and is
what turns "the log has a hole in it" from a thing to infer into a thing the
next line and `ping` both say out loud.
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
        # What swallowing costs, counted rather than merely promised (#143). The
        # promise below is right and stays right, but nothing counted what it
        # swallowed: a full disk truncated the Campaign's record — and the
        # end-screen summary `archive.summarise` reads out of it — with no
        # signal anywhere at all. Two numbers, because they answer two
        # questions. `_pending` is how many events are missing immediately
        # before the next line that lands, which is the fact a reader of the
        # file needs and is therefore reset by that line. `_dropped` is what
        # this process has lost altogether, which is the fact an operator
        # needs, so it is never reset and is what `ping` reports.
        self._pending = 0
        self._dropped = 0

    @property
    def dropped(self) -> int:
        """How many events this process has failed to write, all told.

        Read without the lock: a monotone counter of `int`, and a reader racing
        a write in flight learns the count from a moment ago rather than a wrong
        one. Taking the lock here would put a `ping` behind whatever filesystem
        stall is producing the number it came to ask about.
        """
        return self._dropped

    def record(self, event: str, **fields: object) -> None:
        """Append one event. Never raises.

        The promise is kept over the whole of the write, encoding included (#88).
        It used to catch `OSError` alone, with the `json.dumps` outside the
        `try` — so a field `default=repr` could not rescue, a non-string key or
        a cycle, escaped as a `TypeError` or `ValueError` and failed the request
        it was merely describing.

        A write that lands after failures says how many went missing in front of
        it, under `dropped_before` (#143). The encoding moved inside the lock to
        buy it: the count stamped on a line and the count that line clears have
        to be one read and one write of the same field, or two threads recording
        at once would either double-report a loss or lose the report of one. It
        costs a `json.dumps` of a small record inside a lock nothing contends —
        the daemon serialises whole requests behind its own (#98), and the
        checkpoint coordinator's thread records once per checkpoint.
        """
        record: dict[str, object] = {"at_ns": time.time_ns(), "event": event, **fields}
        with self._lock:
            if self._pending:
                record["dropped_before"] = self._pending
            try:
                line = json.dumps(record, separators=(",", ":"), default=repr)
                with self._path.open("a", encoding="utf-8") as sink:
                    sink.write(line + "\n")
            except Exception:  # noqa: BLE001 — the docstring's promise is the whole point:
                # observability must never be able to fail a request (ADR-0003), and a
                # narrower catch is a list of the failures somebody thought of. The
                # counters are the only thing that changes: this event is gone, and the
                # loss it was going to report is still owed to whichever line lands next.
                self._pending += 1
                self._dropped += 1
                return
            self._pending = 0
