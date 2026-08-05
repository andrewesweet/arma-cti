"""Structured telemetry: observability only.

ADR-0003 makes the snapshot the authoritative campaign state, so telemetry is
never read back as state. That is what buys the third test: a telemetry failure
must cost a log line and nothing else, because nothing depends on it.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from conftest import all_rows

from cti_daemon.telemetry import Telemetry

if TYPE_CHECKING:
    from pathlib import Path


def test_an_event_lands_as_one_json_line(tmp_path: Path) -> None:
    log = tmp_path / "telemetry.jsonl"
    Telemetry(log).record("request", verb="ping", outcome="ok")

    (line,) = log.read_text(encoding="utf-8").splitlines()
    assert json.loads(line) | {"at_ns": 0} == {
        "at_ns": 0,
        "event": "request",
        "verb": "ping",
        "outcome": "ok",
    }


def test_events_are_appended_in_order_and_timestamped(tmp_path: Path) -> None:
    log = tmp_path / "telemetry.jsonl"
    telemetry = Telemetry(log)
    telemetry.record("request", n=1)
    telemetry.record("request", n=2)

    records = all_rows(log)
    assert [record["n"] for record in records] == [1, 2]
    assert records[0]["at_ns"] <= records[1]["at_ns"]


def test_a_telemetry_failure_is_swallowed(tmp_path: Path) -> None:
    # The log path is inside a file rather than a directory, so every write
    # fails. Recording must still be a no-op for the caller.
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("", encoding="utf-8")
    Telemetry(blocker / "telemetry.jsonl").record("request", verb="ping")


def test_a_field_that_cannot_be_encoded_is_swallowed_like_any_other_failure(
    tmp_path: Path,
) -> None:
    # "Never raises" is a promise over the whole write, encoding included (#88).
    # A cycle is the one shape `default=repr` cannot rescue, and it used to
    # escape as a ValueError from outside the try and fail the request the row
    # was merely describing.
    cyclic: dict[str, object] = {}
    cyclic["self"] = cyclic
    log = tmp_path / "telemetry.jsonl"
    Telemetry(log).record("request", loop=cyclic)

    assert not log.exists() or log.read_text(encoding="utf-8") == ""
