"""The daemon's identity on the wire (#96, ADR-0036).

The daemon's whole strategic state is in memory, so a restart is a new Campaign
wearing the old world's clothes. The shim reconnects on failure and says nothing
(ADR-0005), so the world cannot tell a reconnect from a rebirth by transport
alone. These tests pin the one fact that makes it tellable: every reply carries
the identity of the process that answered it, and two processes never share one.
"""

from __future__ import annotations

import json
import socket
from typing import IO, TYPE_CHECKING, Any

import pytest

from cti_daemon import protocol, transport
from cti_daemon.transport import build_daemon

if TYPE_CHECKING:
    from pathlib import Path

    from cti_daemon.daemon import Daemon


def reply_to(daemon: Daemon, **envelope: object) -> dict[str, Any]:
    """Send one envelope through the whole line-handling path."""
    return json.loads(daemon.handle_line(json.dumps(envelope)))


def test_an_epoch_is_minted_per_process_not_per_request(tmp_path: Path) -> None:
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    epochs = {reply_to(daemon, id=f"r-{n}", verb="ping")["epoch"] for n in range(3)}
    assert epochs == {daemon.epoch}


def test_two_daemons_never_share_an_epoch(tmp_path: Path) -> None:
    # This is the whole point: a restarted daemon is a different daemon, and
    # nothing else on the wire says so.
    first = build_daemon(telemetry_path=tmp_path / "one.jsonl")
    second = build_daemon(telemetry_path=tmp_path / "two.jsonl")
    assert first.epoch != second.epoch


@pytest.mark.parametrize(
    ("line", "status"),
    [
        (json.dumps({"id": "r-1", "verb": "ping"}), "ok"),
        (json.dumps({"id": "r-2", "verb": "command", "payload": {"side": "WEST"}}), "rejected"),
        (json.dumps({"id": "r-3", "verb": "purchase"}), "error"),
        ("{not json", "error"),
    ],
)
def test_every_reply_carries_the_epoch_whatever_its_status(
    tmp_path: Path, line: str, status: str
) -> None:
    # A world that only learned the epoch from successful replies would go blind
    # exactly when the daemon was in trouble.
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    reply = json.loads(daemon.handle_line(line))
    assert reply["status"] == status
    assert reply["epoch"] == daemon.epoch


def test_a_replayed_line_is_answered_under_the_epoch_that_first_answered_it(
    tmp_path: Path,
) -> None:
    # The dedupe window hands back the bytes it stored (#69, ADR-0034), and those
    # bytes were stamped by this process. Stamping twice would be a second answer.
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    line = json.dumps({"id": "r-1", "verb": "ping"})
    first = json.loads(daemon.handle_line(line))
    replayed = json.loads(daemon.handle_line(line))
    assert replayed == first
    assert replayed["epoch"] == daemon.epoch


def test_a_restart_neither_remembers_the_answer_nor_reuses_the_epoch(tmp_path: Path) -> None:
    # The simulated restart: the same line, sent to the process before and to the
    # process after. The shim resends across a reconnect, so this is the exact
    # sequence a restart produces on the wire — and the world has to be able to
    # tell the second answer from a replay of the first.
    line = json.dumps({"id": "obs-1", "verb": "poll"})
    before = build_daemon(telemetry_path=tmp_path / "before.jsonl")
    before.outbox.push({"kind": "order"})
    first = json.loads(before.handle_line(line))

    after = build_daemon(telemetry_path=tmp_path / "after.jsonl")
    second = json.loads(after.handle_line(line))

    assert first["epoch"] != second["epoch"]
    # And the restart really is a fresh Campaign, which is the loss the epoch
    # exists to make visible rather than to prevent: the outbox is empty.
    assert first["result"]["messages"] != []
    assert second["result"]["messages"] == []


def test_the_epoch_is_recorded_against_every_request(tmp_path: Path) -> None:
    # One run's telemetry is appended to across a restart, so the epoch is what
    # separates two daemons' records in one file.
    log = tmp_path / "telemetry.jsonl"
    daemon = build_daemon(telemetry_path=log)
    daemon.handle_line(json.dumps({"id": "r-1", "verb": "ping"}))
    records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert [record["epoch"] for record in records] == [daemon.epoch]


def test_a_daemon_may_be_told_its_epoch_so_a_test_can_name_it(tmp_path: Path) -> None:
    daemon = build_daemon(telemetry_path=tmp_path / "telemetry.jsonl", epoch="epoch-under-test")
    assert reply_to(daemon, id="r-1", verb="ping")["epoch"] == "epoch-under-test"


def test_the_reply_envelope_contract_names_the_epoch_as_always_present() -> None:
    # What the exported schema publishes, and what cti_fnc_daemonCall branches
    # on. `status` and `epoch` are the two keys that must be there whatever
    # happened, because they are the two questions the world asks first.
    assert set(protocol.REPLY_ENVELOPE["always"]) == {"id", "epoch", "status"}


def connect(tmp_path: Path) -> tuple[socket.socket, IO[bytes]]:
    """Start a daemon on a socket and open one connection to it."""
    port = transport.serve_in_thread(telemetry_path=tmp_path / "telemetry.jsonl")
    sock = socket.create_connection(("127.0.0.1", port), timeout=5)
    return sock, sock.makefile("rb")


def test_the_epoch_reaches_the_wire(tmp_path: Path) -> None:
    sock, stream = connect(tmp_path)
    with sock, stream:
        sock.sendall(json.dumps({"id": "r-1", "verb": "ping"}).encode("utf-8") + b"\n")
        reply = json.loads(stream.readline())
    assert isinstance(reply["epoch"], str)
    assert reply["epoch"]


def test_the_readiness_line_names_the_epoch_the_run_is_about_to_get() -> None:
    # So that a harness restarting the daemon mid-run has the two epochs on
    # record rather than only the world's word for them.
    line = transport.ready_line("127.0.0.1", 9099, "e-1")
    assert line == "CTI_DAEMON_READY 127.0.0.1:9099 epoch=e-1"
