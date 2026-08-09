"""The control lane over a real socket — its own connection, replayed across drops (#291).

`test_daemon_control` pins the handlers at the module seam; this pins the
transport that carries them: a second listener on its own port, served serially,
that answers save and load the way the command listener answers a verb. What this
holds is the lane's transport contract rather than its semantics:

- A save and a load round-trip over the control socket, carrying the epoch.
- A request dropped mid-exchange is answered from the record when the connection
  reopens (ADR-0034 replay, on the control lane).
- The control lane is its own connection: a slow save on it does not head-of-line
  block a Command on the command lane, and the lane serves one connection at a
  time so its replay window needs no lock of its own.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from typing import TYPE_CHECKING, Any

from cti_daemon import transport
from cti_daemon.store import FakeStore

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from cti_daemon.store import SaveOutcome


def _save(request_id: str) -> str:
    return json.dumps({"id": request_id, "verb": "save", "payload": {}})


def _load(request_id: str) -> str:
    return json.dumps({"id": request_id, "verb": "load", "payload": {}})


def _ask(port: int, line: str) -> dict[str, Any]:
    """Send one line down a fresh connection to `port` and read one reply.

    A fresh connection each call because that is the shape of a transport
    interruption: the shim drops the cached socket and reopens to resend.
    """
    sock = socket.create_connection(("127.0.0.1", port), timeout=10)
    with sock, sock.makefile("rb") as stream:
        sock.sendall(line.encode("utf-8") + b"\n")
        return json.loads(stream.readline())


def _both(tmp_path: Path, store: FakeStore | None = None) -> tuple[int, int]:
    """Serve a daemon with a control lane, returning (command_port, control_port)."""
    return transport.serve_control_in_thread(
        telemetry_path=tmp_path / "telemetry.jsonl", store=store or FakeStore()
    )


class _SlowStore(FakeStore):
    """A FakeStore whose save blocks until released, to wedge the control lane."""

    def __init__(self) -> None:
        super().__init__()
        self.in_save = threading.Event()
        self.release = threading.Event()

    def save(self, document: Mapping[str, object]) -> SaveOutcome:
        self.in_save.set()
        self.release.wait(timeout=30)
        return super().save(document)


# --- the control lane round-trips over its own socket ---------------------


def test_the_control_lane_round_trips_save_and_load_over_a_socket(tmp_path: Path) -> None:
    _command, control = _both(tmp_path)
    save = _ask(control, _save("s-1"))
    load = _ask(control, _load("l-1"))

    assert save["status"] == "ok"
    assert set(save["result"]) == {"saved", "version", "checksum", "generation"}
    assert load["status"] == "ok"
    assert load["result"]["loaded"] is True
    # Every reply carries the epoch (#96); a load mints a new one (criterion 6),
    # so the load's reply carries a different identity from the save's.
    assert save["epoch"]
    assert load["epoch"] != save["epoch"]


def test_the_command_lane_is_unaffected_by_the_control_lane_existing(tmp_path: Path) -> None:
    # A daemon brought up with a store answers its command lane exactly as one
    # without: the control lane is additive, not a change to the verbs the game
    # speaks. #289's guard holds at the socket too — there is no `save` verb on
    # the command port.
    command, _control = _both(tmp_path)
    ping = _ask(command, json.dumps({"id": "p-1", "verb": "ping"}))
    refused = _ask(command, _save("s-1"))
    assert ping["status"] == "ok"
    assert refused["status"] == "error"
    assert refused["error"]["class"] == "unknown_verb"


# --- a dropped control connection is answered from the record ------------


def test_a_control_request_survives_a_transport_interruption_by_replay(
    tmp_path: Path,
) -> None:
    # Each `_ask` opens a fresh connection and closes it. The identical line on
    # the second connection is a resend after a dropped exchange (ADR-0005/
    # ADR-0034), answered from the record rather than saved a second time.
    _command, control = _both(tmp_path)
    line = _save("s-1")
    first = _ask(control, line)
    again = _ask(control, line)
    assert again == first, "a resent control line was not answered from the record"
    assert first["result"]["generation"] == 1


# --- the control lane does not head-of-line block the command lane -------


def test_a_slow_save_on_the_control_lane_does_not_block_a_command(tmp_path: Path) -> None:
    store = _SlowStore()
    command, control = _both(tmp_path, store=store)

    thread = threading.Thread(target=lambda: _ask(control, _save("s-1")), daemon=True)
    thread.start()
    assert store.in_save.wait(timeout=5), "the save never reached the slow store"

    # The save is wedged in its slow durability write, off the lock, on the
    # control port. A Command on the command port must go through regardless.
    started = time.perf_counter()
    reply = _ask(command, json.dumps({"id": "c-1", "verb": "ping"}))
    elapsed = time.perf_counter() - started

    assert reply["status"] == "ok", "a wedged control save blocked a Command"
    assert elapsed < 1.0, f"a Command waited {elapsed:.3f}s behind a control save"

    store.release.set()
    thread.join(timeout=30)
    assert not thread.is_alive()


# --- the control lane serves one connection at a time -------------------


def test_the_control_lane_serves_one_connection_at_a_time(tmp_path: Path) -> None:
    # The lane's replay window is the command lane's `Answered` without an
    # internal lock, so the lane serialises structurally: a `_ControlServer`
    # accepts one connection at a time. A second control connection wedged on
    # the first's slow save proves it never ran concurrently.
    store = _SlowStore()
    _command, control = _both(tmp_path, store=store)

    threading.Thread(target=lambda: _ask(control, _save("s-1")), daemon=True).start()
    assert store.in_save.wait(timeout=5), "the first save never wedged the lane"

    second: list[dict[str, Any]] = []

    def _second() -> None:
        second.append(_ask(control, _save("s-2")))

    thread = threading.Thread(target=_second, daemon=True)
    thread.start()
    thread.join(timeout=1.0)
    assert thread.is_alive(), "a second control connection ran alongside the first"

    store.release.set()
    thread.join(timeout=30)
    assert not thread.is_alive()
    assert second[0]["status"] == "ok"
    assert second[0]["result"]["generation"] == 2
