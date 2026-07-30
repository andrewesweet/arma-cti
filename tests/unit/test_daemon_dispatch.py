"""What the daemon does with one request line."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from cti_daemon.daemon import Daemon

if TYPE_CHECKING:
    from pathlib import Path


def reply_to(daemon: Daemon, **envelope: object) -> dict[str, Any]:
    """Send one request and return its decoded reply."""
    return json.loads(daemon.handle_line(json.dumps(envelope)))


def test_ping_is_answered_with_the_id_it_was_asked_under(tmp_path: Path) -> None:
    daemon = Daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    assert reply_to(daemon, id="r-1", verb="ping") == {
        "id": "r-1",
        "status": "ok",
        "result": {"pong": True},
    }


def test_a_verb_the_daemon_does_not_know_is_an_error_not_a_rejection(tmp_path: Path) -> None:
    # Rejection means "understood and refused"; this was not understood.
    daemon = Daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    reply = reply_to(daemon, id="r-2", verb="purchase")
    assert reply["id"] == "r-2"
    assert reply["status"] == "error"
    assert reply["error"]["class"] == "unknown_verb"


def test_a_malformed_line_is_answered_rather_than_dropped(tmp_path: Path) -> None:
    daemon = Daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    reply = json.loads(daemon.handle_line("{not json"))
    assert reply["id"] is None
    assert reply["status"] == "error"
    assert reply["error"]["class"] == "malformed_request"


def test_a_malformed_line_that_still_carried_an_id_is_answered_under_it(tmp_path: Path) -> None:
    daemon = Daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    reply = json.loads(daemon.handle_line('{"id": "r-3", "verb": 7}'))
    assert reply["id"] == "r-3"
    assert reply["error"]["class"] == "malformed_request"


def test_poll_hands_over_pending_messages_with_their_sequences(tmp_path: Path) -> None:
    daemon = Daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    daemon.outbox.push({"kind": "order"})

    reply = reply_to(daemon, id="r-4", verb="poll")
    assert reply["result"] == {"messages": [{"sequence": 1, "message": {"kind": "order"}}]}


def test_polling_twice_without_acknowledging_delivers_the_same_messages(tmp_path: Path) -> None:
    daemon = Daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    daemon.outbox.push({"kind": "order"})

    first = reply_to(daemon, id="r-5", verb="poll")["result"]
    second = reply_to(daemon, id="r-6", verb="poll")["result"]
    assert first == second


def test_acknowledging_clears_the_messages_from_the_next_poll(tmp_path: Path) -> None:
    daemon = Daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    daemon.outbox.push({"kind": "order"})

    acked = reply_to(daemon, id="r-7", verb="ack", payload={"through": 1})
    assert acked["status"] == "ok"
    assert reply_to(daemon, id="r-8", verb="poll")["result"] == {"messages": []}


def test_acknowledging_a_sequence_never_issued_is_a_domain_rejection(tmp_path: Path) -> None:
    # The request was well formed and the daemon understood it. It is refused
    # on the rules, which is the third outcome, not an error.
    daemon = Daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    reply = reply_to(daemon, id="r-9", verb="ack", payload={"through": 9})
    assert reply["status"] == "rejected"
    assert reply["reason"]["code"] == "unknown_sequence"


def test_an_acknowledgement_without_a_sequence_is_malformed(tmp_path: Path) -> None:
    daemon = Daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    reply = reply_to(daemon, id="r-10", verb="ack", payload={"through": "soon"})
    assert reply["status"] == "error"
    assert reply["error"]["class"] == "malformed_request"


def test_a_failure_inside_the_daemon_is_answered_as_an_internal_error(tmp_path: Path) -> None:
    # A message that cannot be serialised is the shape of bug a later ticket
    # will produce. The connection must survive it and say what happened.
    daemon = Daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    daemon.outbox.push({"unserialisable": object()})

    reply = reply_to(daemon, id="r-11", verb="poll")
    assert reply["id"] == "r-11"
    assert reply["status"] == "error"
    assert reply["error"]["class"] == "internal"


def test_every_request_is_recorded_in_telemetry(tmp_path: Path) -> None:
    log = tmp_path / "telemetry.jsonl"
    daemon = Daemon(telemetry_path=log)
    daemon.handle_line(json.dumps({"id": "r-12", "verb": "ping"}))
    daemon.handle_line("{not json")

    records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert [(record["id"], record["verb"], record["status"]) for record in records] == [
        ("r-12", "ping", "ok"),
        (None, None, "error"),
    ]
    assert all(record["duration_us"] >= 0 for record in records)
