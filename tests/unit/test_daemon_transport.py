"""The transport contract the Rust shim depends on.

Newline-delimited JSON over TCP loopback, one connection reused across calls
(ADR-0005). These are the only tests that drive a real socket; everything else
about the daemon is tested at the module seams.
"""

from __future__ import annotations

import argparse
import json
import socket
import threading
import time
from typing import IO, TYPE_CHECKING, Any

import pytest
from conftest import rows

from cti_daemon import economy, manifest, transport
from cti_daemon.daemon import Daemon

if TYPE_CHECKING:
    from collections.abc import Callable
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
        # The authored files come from the composition root (#76), which is what
        # `build_daemon` does for everything that is not a subclass.
        super().__init__(
            telemetry_path=telemetry_path,
            table=economy.load(transport.DEFAULT_ECONOMY),
            map_manifest=manifest.load_all(transport.DEFAULT_MANIFESTS)[transport.DEFAULT_MAP],
        )
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
                            "acting_side": "WEST",
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


def _ask(port: int, line: str) -> dict[str, Any]:
    """Send one line down a connection of its own and close it again.

    A fresh connection per call because that is what the shim does when a call
    times out on its cached one (ADR-0034), which is the traffic the pileup was
    made of.
    """
    sock = socket.create_connection(("127.0.0.1", port), timeout=30)
    with sock, sock.makefile("rb") as stream:
        return exchange(sock, stream, line)


class _Wedged(Daemon):
    """A daemon whose handler sticks until it is let go (#142).

    The finding's shape: `_answer` is the body the request lock holds, so a
    handler stuck anywhere inside it — a filesystem stall in `archive.write`, a
    planner bug — holds the lock against every other connection.
    """

    def __init__(self, *, telemetry_path: Path) -> None:
        super().__init__(
            telemetry_path=telemetry_path,
            table=economy.load(transport.DEFAULT_ECONOMY),
            map_manifest=manifest.load_all(transport.DEFAULT_MANIFESTS)[transport.DEFAULT_MAP],
        )
        self.wedged = threading.Event()
        self.released = threading.Event()

    def _answer(self, line: str) -> str:
        if not self.wedged.is_set():
            self.wedged.set()
            # Bounded so a failing test ends rather than hangs the tier. The
            # subject is what happens to *other* callers while this one sticks,
            # and they are unblocked by the release below, not by this expiring.
            self.released.wait(timeout=30)
        return super()._answer(line)


def _wedged_daemon(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[_Wedged, int]:
    """Serve a wedgeable daemon and stick it, returning it and its port."""
    daemon = _Wedged(telemetry_path=tmp_path / "telemetry.jsonl")
    monkeypatch.setattr(transport, "build", lambda *_, **__: daemon)
    port = transport.serve_in_thread(telemetry_path=tmp_path / "unused.jsonl")

    def _stick() -> None:
        sock = socket.create_connection(("127.0.0.1", port), timeout=30)
        with sock, sock.makefile("rb") as stream:
            exchange(sock, stream, json.dumps({"id": "stuck", "verb": "ping"}))

    threading.Thread(target=_stick, daemon=True).start()
    assert daemon.wedged.wait(timeout=5), "the daemon never took the wedged request"
    return daemon, port


def test_a_wedged_handler_sheds_later_calls_rather_than_parking_their_threads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # #142: `handle_line` used to wait on the lock with no deadline while the
    # transport spawned a thread per connection with no bound, so a wedged
    # handler collected a blocked thread per shim retry for the rest of the
    # session. Every one of these calls must come back — the count is arbitrary,
    # the property is that none of them is still parked.
    daemon, port = _wedged_daemon(tmp_path, monkeypatch)
    log = tmp_path / "telemetry.jsonl"

    replies: list[dict[str, Any]] = []
    _in_parallel(
        lambda tag: replies.append(_ask(port, json.dumps({"id": tag, "verb": "ping"}))),
        ("a", "b", "c", "d", "e"),
    )
    daemon.released.set()

    assert [reply["status"] for reply in replies] == ["error"] * 5
    assert {reply["error"]["class"] for reply in replies} == {"busy"}
    assert {reply["id"] for reply in replies} == {"a", "b", "c", "d", "e"}
    assert {reply["epoch"] for reply in replies} == {daemon.epoch}, (
        "a shed reply says who refused it, like every other reply (#96, ADR-0036)"
    )
    assert len(rows(log, "request_shed")) == 5


def test_a_shed_request_is_carried_out_when_it_is_asked_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Nothing was judged and nothing was spent, so the shim's resend of the
    # identical line must be carried out rather than answered from the refusal
    # it got (#69, ADR-0034 remembers answers, not refusals to answer).
    daemon, port = _wedged_daemon(tmp_path, monkeypatch)
    line = json.dumps(
        {
            "id": "resent",
            "verb": "command",
            "payload": {
                "command": "purchase",
                "side": "WEST",
                "acting_side": "WEST",
                "args": {"squad_type": "rifle"},
            },
        }
    )

    shed = _ask(port, line)
    daemon.released.set()
    again = _ask(port, line)

    assert shed["error"]["class"] == "busy"
    assert again["status"] == "ok", "a shed Purchase must still be buyable"
    assert again["result"]["squad"] == "WEST-1"


def test_a_healthy_daemon_answers_exactly_as_it_did_before_the_bound(tmp_path: Path) -> None:
    # The bound sheds nothing a healthy daemon does, so the wire is unchanged:
    # no `busy` reply, no `request_shed` row, and the reply to a request that
    # waited its turn is the reply it always was.
    log = tmp_path / "telemetry.jsonl"
    port = transport.serve_in_thread(telemetry_path=log)

    replies: list[list[dict[str, Any]]] = []
    _in_parallel(lambda tag: replies.append(_hammer(port, tag, 8)), ("a", "b"))

    flat = [reply for batch in replies for reply in batch]
    assert flat, "the connections answered nothing"
    assert not [reply for reply in flat if reply["status"] == "error"]
    assert not rows(log, "request_shed")


def test_a_connection_that_stops_talking_is_closed_server_side(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # #73's last bullet, folded in here: a half-open peer used to park a handler
    # thread until process exit. Shortened to keep the test quick — the subject
    # is that the bound exists and fires, not how long it is.
    monkeypatch.setattr(transport, "IDLE_SECONDS", 0.2)
    port = transport.serve_in_thread(telemetry_path=tmp_path / "telemetry.jsonl")

    sock = socket.create_connection(("127.0.0.1", port), timeout=10)
    with sock, sock.makefile("rb") as stream:
        # Answered first, so this is an established connection going silent
        # rather than one that never spoke.
        assert exchange(sock, stream, json.dumps({"id": "r-1", "verb": "ping"}))["status"] == "ok"
        assert stream.readline() == b"", "the daemon held a silent connection open"


def test_a_connection_that_keeps_talking_is_not_closed_under_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The bound is on silence, not on connection age: the shim caches one
    # connection for the life of a session (ADR-0005) and must keep it. The
    # gaps below are the subject rather than a wait for anything to settle —
    # five of them add to more than the bound while none of them reaches it,
    # which is the whole distinction under test.
    monkeypatch.setattr(transport, "IDLE_SECONDS", 0.2)
    port = transport.serve_in_thread(telemetry_path=tmp_path / "telemetry.jsonl")

    sock = socket.create_connection(("127.0.0.1", port), timeout=10)
    with sock, sock.makefile("rb") as stream:
        for n in range(5):
            assert exchange(sock, stream, json.dumps({"id": f"r-{n}", "verb": "ping"}))["id"] == (
                f"r-{n}"
            )
            time.sleep(0.05)


def test_the_readiness_line_names_the_bound_address() -> None:
    # The Arma tier waits on this line rather than sleeping, so its shape is a
    # contract between the daemon and spike/run.sh.
    assert transport.ready_line("127.0.0.1", 9099, "e-1").startswith(
        "CTI_DAEMON_READY 127.0.0.1:9099"
    )


def test_a_daemon_that_never_binds_says_so_rather_than_indexing_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A bind failure used to surface as a bare IndexError out of `bound[0]`,
    # which says nothing about a daemon (#88). Provoked by a `serve` that never
    # calls back, which is what a bind that raised on the worker thread looks
    # like from here.
    monkeypatch.setattr(transport, "serve", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(transport, "BRING_UP_SECONDS", 0.05)

    with pytest.raises(transport.DaemonNeverCameUpError, match="never came up"):
        transport.serve_in_thread(telemetry_path=tmp_path / "telemetry.jsonl")


def test_the_daemon_refuses_to_listen_anywhere_but_this_machine() -> None:
    # The socket carries no authentication and ADR-0044 decides it will not
    # grow any, which makes the bind address the whole of the boundary. A
    # widened one is not a smaller guarantee, it is none — so it is refused
    # rather than warned about (ADR-0033, fail closed).
    for host in ("0.0.0.0", "192.168.1.10", "::", "not-an-address"):  # noqa: S104 — the address under refusal
        with pytest.raises(transport.NonLoopbackBindError):
            transport.check_loopback(host)


def test_the_loopback_addresses_the_tier_actually_uses_are_allowed() -> None:
    for host in ("127.0.0.1", "localhost", "::1"):
        transport.check_loopback(host)


def test_a_non_loopback_bind_is_refused_before_anything_is_written(tmp_path: Path) -> None:
    # On stderr with a non-zero exit rather than a traceback, and without
    # creating the telemetry directory: a run that will not start leaves
    # nothing behind for the next one to read as evidence.
    telemetry = tmp_path / "evidence" / "telemetry.jsonl"
    code = transport.main(["--host", "0.0.0.0", "--telemetry", str(telemetry)])  # noqa: S104 — the address under refusal
    assert code == 2
    assert not telemetry.parent.exists()


@pytest.mark.parametrize("seed", ["--5", "5-", "-", "- 5", "+5", "5.0", "0x5", "five"])
def test_a_seed_that_is_not_a_whole_number_draws_this_modules_own_refusal(seed: str) -> None:
    # `"--5"` used to pass a sign-stripping digit check and reach `int()`, which
    # raised argparse's generic "invalid value" instead of the sentence that
    # says what a seed is (#155). The refusal is the contract, not the failure.
    with pytest.raises(argparse.ArgumentTypeError, match="a seed is a whole number"):
        transport.parse_commander_flag(f"WEST:{seed}")


@pytest.mark.parametrize(("text", "expected"), [("WEST:-5", -5), ("WEST:5", 5), ("WEST", 0)])
def test_the_seeds_a_session_actually_brings_up_with_are_read(text: str, expected: int) -> None:
    assert transport.parse_commander_flag(text) == ("WEST", expected)


def test_an_unknown_side_is_refused_by_name() -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="no side named 'EAST_OF_HERE'"):
        transport.parse_commander_flag("east_of_here:5")
