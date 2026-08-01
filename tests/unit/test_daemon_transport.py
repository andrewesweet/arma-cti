"""The transport contract the Rust shim depends on.

Newline-delimited JSON over TCP loopback, one connection reused across calls
(ADR-0005). These are the only tests that drive a real socket; everything else
about the daemon is tested at the module seams.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from typing import IO, TYPE_CHECKING, Any

from cti_daemon import transport
from cti_daemon.daemon import Daemon

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import pytest


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
    # The epoch is the answering process's own (#96, ADR-0036), so it is checked
    # for shape here and pinned by name in test_daemon_epoch.py.
    assert reply.pop("epoch")
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


class _Watched(Daemon):
    """A daemon that records how many requests were ever inside it at once.

    Wraps `_answer`, the body the request lock holds, rather than `handle_line`
    — outside the lock every server is concurrent and the count would say
    nothing.
    """

    def __init__(self, *, telemetry_path: Path) -> None:
        super().__init__(telemetry_path=telemetry_path)
        self.most_inside = 0
        self._inside = 0
        self._counter = threading.Lock()

    def _answer(self, line: str) -> str:
        with self._counter:
            self._inside += 1
            self.most_inside = max(self.most_inside, self._inside)
        # Yield the interpreter to whatever else is on the wire. This is not a
        # wait for something to become true: it is what makes an unlocked
        # daemon show two requests inside itself on nearly every run instead of
        # only when CPython happened to switch threads mid-mutation.
        time.sleep(0)
        try:
            return super()._answer(line)
        finally:
            with self._counter:
                self._inside -= 1


def _hammer(port: int, tag: str, count: int) -> list[dict[str, Any]]:
    """Buy a rifle Squad `count` times down one connection of its own."""
    sock = socket.create_connection(("127.0.0.1", port), timeout=5)
    with sock, sock.makefile("rb") as stream:
        return [
            exchange(
                sock,
                stream,
                json.dumps(
                    {
                        "id": f"{tag}-{n}",
                        "verb": "command",
                        "payload": {
                            "command": "purchase",
                            "side": "WEST",
                            "args": {"squad_type": "rifle"},
                        },
                    }
                ),
            )
            for n in range(count)
        ]


def _in_parallel(job: Callable[[str], None], tags: tuple[str, ...]) -> None:
    """Run `job` once per tag, all of them at the same time."""
    threads = [threading.Thread(target=job, args=(tag,)) for tag in tags]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert not [thread for thread in threads if thread.is_alive()], "a connection never finished"


def test_two_connections_are_never_inside_the_daemon_at_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # #98: the transport gives every connection a thread and the Campaign has
    # no lock of its own, so serialisation has to come from the daemon. The
    # shim's resend opens a second connection while the first request may still
    # be running (#69), which is exactly this shape.
    watched = _Watched(telemetry_path=tmp_path / "telemetry.jsonl")
    monkeypatch.setattr(transport, "build", lambda *_, **__: watched)
    port = transport.serve_in_thread(telemetry_path=tmp_path / "unused.jsonl")

    results: list[list[dict[str, Any]]] = []
    _in_parallel(lambda tag: results.append(_hammer(port, tag, 8)), ("a", "b"))

    assert len(results) == 2, "both connections must have been answered"
    assert watched.most_inside == 1, (
        f"{watched.most_inside} requests were inside the daemon at once; "
        "the Campaign is mutated with no other lock, so this is a race"
    )


def test_concurrent_connections_cannot_spend_the_same_funds_twice(tmp_path: Path) -> None:
    # The mutation the race would corrupt, asserted end to end: 300 starting
    # Funds buys exactly three 100-Funds rifle Squads, however many connections
    # ask at once, and each accepted Purchase sees the balance the one before
    # it left.
    port = transport.serve_in_thread(telemetry_path=tmp_path / "telemetry.jsonl")

    replies: list[dict[str, Any]] = []
    _in_parallel(lambda tag: replies.extend(_hammer(port, tag, 5)), ("a", "b"))

    bought = [reply["result"] for reply in replies if reply["status"] == "ok"]
    assert sorted(entry["funds"] for entry in bought) == [0, 100, 200]
    assert sorted(entry["squad"] for entry in bought) == ["WEST-1", "WEST-2", "WEST-3"]


def test_the_readiness_line_names_the_bound_address() -> None:
    # The Arma tier waits on this line rather than sleeping, so its shape is a
    # contract between the daemon and spike/run.sh.
    assert transport.ready_line("127.0.0.1", 9099, "e-1").startswith(
        "CTI_DAEMON_READY 127.0.0.1:9099"
    )
