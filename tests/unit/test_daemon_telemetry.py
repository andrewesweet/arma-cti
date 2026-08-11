"""Structured telemetry: observability only.

ADR-0003 makes the snapshot the authoritative campaign state, so telemetry is
never read back as state. That is what buys the third test: a telemetry failure
must cost a log line and nothing else, because nothing depends on it.

And what it costs is counted (#143). The promise and its price are separate
claims: the tests from `test_every_swallowed_write_is_counted` on hold that a
swallowed write still says so — to whoever reads the file next, and to whoever
asks `ping` — without any of them making a failed write reach the caller.
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


def test_every_swallowed_write_is_counted(tmp_path: Path) -> None:
    # #143: swallowing is right and stays right, but nothing counted what it
    # swallowed — a full disk truncated the Campaign's record, and the
    # end-screen summary read out of it, with no signal anywhere at all.
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("", encoding="utf-8")
    telemetry = Telemetry(blocker / "telemetry.jsonl")

    assert telemetry.dropped == 0
    telemetry.record("request", verb="ping")
    telemetry.record("request", verb="poll")

    assert telemetry.dropped == 2


def test_a_write_that_lands_says_how_many_went_missing_in_front_of_it(tmp_path: Path) -> None:
    # The reader of the file is the one who needs this: a hole in the record is
    # otherwise indistinguishable from a quiet stretch of the session.
    log = tmp_path / "later" / "telemetry.jsonl"
    telemetry = Telemetry(log)
    telemetry.record("request", verb="ping")
    telemetry.record("request", verb="poll")
    log.parent.mkdir()
    telemetry.record("request", verb="command")

    (landed,) = all_rows(log)
    assert landed["verb"] == "command"
    assert landed["dropped_before"] == 2


def test_the_next_write_after_that_carries_no_count_of_its_own(tmp_path: Path) -> None:
    # The field says what is missing immediately in front of this line, so a
    # line with nothing missing in front of it must not carry it — otherwise
    # every row for the rest of the session reports the same old hole.
    log = tmp_path / "later" / "telemetry.jsonl"
    telemetry = Telemetry(log)
    telemetry.record("request", verb="ping")
    log.parent.mkdir()
    telemetry.record("request", verb="poll")
    telemetry.record("request", verb="command")

    reported, quiet = all_rows(log)
    assert reported["dropped_before"] == 1
    assert "dropped_before" not in quiet


def test_the_lifetime_count_survives_a_write_that_lands(tmp_path: Path) -> None:
    # Two numbers because they answer two questions. What the next line reports
    # is cleared by that line; what `ping` reports is what this process has lost
    # altogether, and a recovery does not un-lose it.
    log = tmp_path / "later" / "telemetry.jsonl"
    telemetry = Telemetry(log)
    telemetry.record("request", verb="ping")
    log.parent.mkdir()
    telemetry.record("request", verb="poll")

    assert telemetry.dropped == 1


def test_a_row_the_count_could_not_ride_out_on_still_owes_it(tmp_path: Path) -> None:
    # The count is stamped before the encoding, so a write that fails while
    # carrying it must not take it with it. Otherwise one unencodable field
    # after an outage erases the record of the outage.
    cyclic: dict[str, object] = {}
    cyclic["self"] = cyclic
    log = tmp_path / "later" / "telemetry.jsonl"
    telemetry = Telemetry(log)
    telemetry.record("request", verb="ping")
    log.parent.mkdir()
    telemetry.record("request", loop=cyclic)
    telemetry.record("request", verb="poll")

    (landed,) = all_rows(log)
    assert landed["dropped_before"] == 2
