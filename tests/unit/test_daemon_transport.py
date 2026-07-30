"""The transport contract the Rust shim depends on.

Newline-delimited JSON over TCP loopback, one connection reused across calls
(ADR-0005). These are the only tests that drive a real socket; everything else
about the daemon is tested at the module seams.
"""

from __future__ import annotations

import json
import socket
from typing import IO, TYPE_CHECKING, Any

from cti_daemon import transport

if TYPE_CHECKING:
    from pathlib import Path


def connect(tmp_path: Path) -> tuple[socket.socket, IO[bytes]]:
    """Start a daemon and open one connection to it."""
    port = transport.serve_in_thread(telemetry_path=tmp_path / "telemetry.jsonl")
    sock = socket.create_connection(("127.0.0.1", port), timeout=5)
    return sock, sock.makefile("rb")


def exchange(sock: socket.socket, stream: IO[bytes], line: str) -> dict[str, Any]:
    """Send one raw line and read one reply."""
    sock.sendall(line.encode("utf-8") + b"\n")
    return json.loads(stream.readline())


def test_a_reply_comes_back_under_the_id_it_was_asked_with(tmp_path: Path) -> None:
    sock, stream = connect(tmp_path)
    with sock, stream:
        reply = exchange(sock, stream, json.dumps({"id": "r-1", "verb": "ping"}))
    assert reply == {"id": "r-1", "status": "ok", "result": {"pong": True}}


def test_one_connection_serves_many_requests(tmp_path: Path) -> None:
    sock, stream = connect(tmp_path)
    with sock, stream:
        ids = [
            exchange(sock, stream, json.dumps({"id": f"r-{n}", "verb": "ping"}))["id"]
            for n in range(3)
        ]
    assert ids == ["r-0", "r-1", "r-2"]


def test_a_malformed_line_is_answered_and_the_connection_survives(tmp_path: Path) -> None:
    # A dropped connection would cost the shim its cached socket and every
    # queued reply behind it, so a bad line must cost exactly one reply.
    sock, stream = connect(tmp_path)
    with sock, stream:
        bad = exchange(sock, stream, "{not json")
        good = exchange(sock, stream, json.dumps({"id": "r-2", "verb": "ping"}))
    assert bad["status"] == "error"
    assert good["status"] == "ok"


def test_the_readiness_line_names_the_bound_address() -> None:
    # The Arma tier waits on this line rather than sleeping, so its shape is a
    # contract between the daemon and spike/run.sh.
    assert transport.ready_line("127.0.0.1", 9099) == "CTI_DAEMON_READY 127.0.0.1:9099"
