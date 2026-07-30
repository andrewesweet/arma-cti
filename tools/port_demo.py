"""Issue Commands to a running daemon, the way the AI Commander eventually will.

#12's demo: run this against the daemon while the Arma tier is up, and a Squad
appears at that side's Base while the side's Funds drop. It speaks the same
envelope and the same Command format the human UI does — that is the point of
there being one wire format.

    uv run python tools/port_demo.py --side WEST --squad rifle
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
from typing import IO, Any


def send(sock: socket.socket, stream: IO[bytes], request: dict[str, Any]) -> dict[str, Any]:
    """Send one envelope and read its reply."""
    sock.sendall(json.dumps(request).encode("utf-8") + b"\n")
    return json.loads(stream.readline())


def main(argv: list[str] | None = None) -> int:
    """Issue one Purchase and report what the rules made of it."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9099)
    parser.add_argument("--side", default="WEST")
    parser.add_argument("--squad", default="rifle")
    parser.add_argument("--count", type=int, default=1, help="how many to buy in a row")
    args = parser.parse_args(argv)

    with (
        socket.create_connection((args.host, args.port), timeout=5) as sock,
        sock.makefile("rb") as stream,
    ):
        for index in range(args.count):
            reply = send(
                sock,
                stream,
                {
                    "id": f"demo-{index}",
                    "verb": "command",
                    "payload": {
                        "command": "purchase",
                        "side": args.side,
                        "args": {"squad_type": args.squad},
                    },
                },
            )
            status = reply.get("status")
            if status == "ok":
                funds = reply["result"]["funds"]
                line = f"accepted: {args.side} bought a {args.squad} squad, {funds} Funds left"
            else:
                reason = reply.get("reason") or reply.get("error") or {}
                code = reason.get("code") or reason.get("class")
                line = f"{status}: {code} — {reason.get('detail')}"
            print(line)  # noqa: T201 — this script's output is the demo
    return 0


if __name__ == "__main__":
    sys.exit(main())
