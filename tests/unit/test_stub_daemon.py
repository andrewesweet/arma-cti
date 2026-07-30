"""Wire-contract tests for the phase-0 stub daemon."""

from __future__ import annotations

import json
import socket

from cti_daemon.stub import handle_request, serve_in_thread


def test_valid_json_is_echoed() -> None:
    reply = handle_request('{"cmd": "ping", "n": 1}')
    assert reply["ok"] is True
    assert reply["echo"] == {"cmd": "ping", "n": 1}
    assert reply["sent_ns"] >= reply["received_ns"]


def test_malformed_json_is_reported_not_raised() -> None:
    reply = handle_request("{not json")
    assert reply["ok"] is False
    assert "bad json" in reply["error"]


def test_round_trip_over_a_real_socket() -> None:
    port, _ = serve_in_thread()
    with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
        sock.sendall(b'{"cmd":"echo","payload":"hello"}\n')
        with sock.makefile("rb") as stream:
            reply = json.loads(stream.readline())
    assert reply["ok"] is True
    assert reply["echo"]["payload"] == "hello"


def test_one_connection_serves_many_requests() -> None:
    port, _ = serve_in_thread()
    with socket.create_connection(("127.0.0.1", port), timeout=5) as sock, sock.makefile("rb") as f:
        for i in range(3):
            sock.sendall(json.dumps({"n": i}).encode() + b"\n")
            assert json.loads(f.readline())["echo"]["n"] == i
