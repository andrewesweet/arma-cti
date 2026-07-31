"""TCP transport for the daemon.

Newline-delimited JSON on 127.0.0.1, one persistent connection reused across
calls (ADR-0005: unix sockets do not cross the WSL2/Windows boundary, and
reconnecting per call costs about three times as much).
"""

from __future__ import annotations

import argparse
import socketserver
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Final

from cti_daemon import commands, planner
from cti_daemon.daemon import Daemon

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

DEFAULT_HOST: Final = "127.0.0.1"
DEFAULT_PORT: Final = 9099
DEFAULT_TELEMETRY: Final = Path(".spike-out/daemon-telemetry.jsonl")


def ready_line(host: str, port: int) -> str:
    """Build the line the Arma tier waits for instead of sleeping."""
    return f"CTI_DAEMON_READY {host}:{port}"


def _handler_for(daemon: Daemon) -> type[socketserver.StreamRequestHandler]:
    """Bind one daemon to a connection handler, one instance per connection."""

    class Handler(socketserver.StreamRequestHandler):
        def handle(self) -> None:
            for raw in self.rfile:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                self.wfile.write(daemon.handle_line(line).encode("utf-8") + b"\n")
                self.wfile.flush()

    return Handler


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def build(telemetry_path: Path, ai: Iterable[tuple[str, int]] | None) -> Daemon:
    """Build the daemon this process will serve, under command or not (#16, #17).

    `ai` is one `(side, seed)` per side an AI Commander plays — none, one, or
    both. A planner apiece rather than one asked twice: a planner holds its seed,
    and a pair of seeds is what a two-sided Campaign replays from (#17).

    The planners are built here rather than inside the daemon because they read
    the manifest and the economy table the daemon has just loaded, and loading
    them twice would be two answers to what the map is.
    """
    daemon = Daemon(telemetry_path=telemetry_path)
    for side, seed in ai or ():
        daemon.commanded_by(
            side,
            planner.UtilityPlanner(
                map_manifest=daemon.campaign.map_manifest,
                table=daemon.campaign.table,
                seed=seed,
            ),
        )
    return daemon


def serve(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    *,
    telemetry_path: Path = DEFAULT_TELEMETRY,
    on_ready: Callable[[int], None] | None = None,
    ai: Iterable[tuple[str, int]] | None = None,
) -> None:
    """Serve until interrupted. Calls `on_ready` with the bound port."""
    daemon = build(telemetry_path, ai)
    with _Server((host, port), _handler_for(daemon)) as server:
        if on_ready is not None:
            on_ready(int(server.server_address[1]))
        server.serve_forever()


def serve_in_thread(
    host: str = DEFAULT_HOST, port: int = 0, *, telemetry_path: Path = DEFAULT_TELEMETRY
) -> int:
    """Start the daemon on a background thread and return the bound port."""
    ready = threading.Event()
    bound: list[int] = []

    def _record(port_: int) -> None:
        bound.append(port_)
        ready.set()

    thread = threading.Thread(
        target=serve,
        args=(host, port),
        kwargs={"telemetry_path": telemetry_path, "on_ready": _record},
        daemon=True,
    )
    thread.start()
    ready.wait(timeout=5)
    return bound[0]


def commander(text: str) -> tuple[str, int]:
    """Read one `SIDE[:SEED]` bring-up flag, or refuse it.

    Side and seed travel together rather than as two parallel lists, because a
    seed belongs to the Commander it plays and a session that brought up two
    sides against one list of seeds would have to keep the order straight in its
    head. The seed is fixed rather than drawn: the same pair of seeds and the
    same reports have to produce the same Campaign, which is not a property a
    clock can hold.
    """
    side, _, seed = text.partition(":")
    side = side.upper()
    if side not in commands.SIDES:
        message = f"no side named {side!r} is playing; expected one of {list(commands.SIDES)}"
        raise argparse.ArgumentTypeError(message)
    if seed and not seed.lstrip("-").isdigit():
        message = f"{text!r}: a seed is a whole number, got {seed!r}"
        raise argparse.ArgumentTypeError(message)
    return side, int(seed or 0)


def main(argv: list[str] | None = None) -> int:
    """Run the daemon from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--telemetry", type=Path, default=DEFAULT_TELEMETRY)
    # One flag per side under AI command, each carrying its own seed (#17).
    # None of them, and nobody is under AI command — a world brought up for a
    # human Commander is not quietly played by one.
    parser.add_argument("--ai", type=commander, action="append", default=[], metavar="SIDE[:SEED]")
    args = parser.parse_args(argv)
    args.telemetry.parent.mkdir(parents=True, exist_ok=True)

    def announce(port: int) -> None:
        print(ready_line(args.host, port), flush=True)  # noqa: T201 — the harness reads stdout

    try:
        serve(
            args.host,
            args.port,
            telemetry_path=args.telemetry,
            on_ready=announce,
            ai=args.ai,
        )
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
