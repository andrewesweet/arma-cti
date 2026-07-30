"""Phase-0 spike stub daemon.

Newline-delimited JSON over TCP loopback (ADR-0005). Echoes each request back
with the daemon's own receive/send timestamps so the shim round trip can be
attributed between transport and daemon time. Throwaway: the real daemon
(planner + snapshot store) replaces it in Phase 1.
"""

from __future__ import annotations

import argparse
import json
import socketserver
import sys
import threading
import time
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Callable

DEFAULT_HOST: Final = "127.0.0.1"
DEFAULT_PORT: Final = 9099


def handle_request(payload: str) -> dict[str, Any]:
    """Build the reply for one request line.

    Pure: no I/O, so the wire contract is unit-testable without a socket.
    """
    received = time.monotonic_ns()
    try:
        request: Any = json.loads(payload)
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"bad json: {exc.msg}", "received_ns": received}
    return {
        "ok": True,
        "echo": request,
        "received_ns": received,
        "sent_ns": time.monotonic_ns(),
    }


class _Handler(socketserver.StreamRequestHandler):
    """One instance per connection; loops until the peer closes."""

    def handle(self) -> None:
        for raw in self.rfile:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            reply = json.dumps(handle_request(line), separators=(",", ":"))
            self.wfile.write(reply.encode("utf-8") + b"\n")
            self.wfile.flush()


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def serve(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    *,
    on_ready: Callable[[int], None] | None = None,
) -> None:
    """Serve until interrupted. Calls `on_ready` with the bound port."""
    with _Server((host, port), _Handler) as server:
        bound = server.server_address[1]
        if on_ready is not None:
            on_ready(int(bound))
        server.serve_forever()


def serve_in_thread(host: str = DEFAULT_HOST, port: int = 0) -> tuple[int, threading.Event]:
    """Start the daemon on a background thread. Returns (bound port, ready flag)."""
    ready = threading.Event()
    bound: list[int] = []

    def _record(port_: int) -> None:
        bound.append(port_)
        ready.set()

    thread = threading.Thread(
        target=serve, args=(host, port), kwargs={"on_ready": _record}, daemon=True
    )
    thread.start()
    ready.wait(timeout=5)
    return bound[0], ready


def main(argv: list[str] | None = None) -> int:
    """Run the stub daemon from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)

    def announce(port: int) -> None:
        # The spike harness greps for this line to know the daemon is up.
        print(f"CTI_STUB_DAEMON_READY {args.host}:{port}", flush=True)  # noqa: T201

    try:
        serve(args.host, args.port, on_ready=announce)
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
