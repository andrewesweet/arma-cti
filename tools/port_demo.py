"""Issue Commands to a running daemon, the way the AI Commander eventually will.

#12's demo: buy a Squad while the Arma tier is up and one appears at that side's
Base while the side's Funds drop. #14's: order it onto an Objective and watch it
go. Both speak the same envelope and the same Command format the human UI does —
that is the point of there being one wire format.

    uv run python tools/port_demo.py purchase --side WEST --squad-type rifle
    uv run python tools/port_demo.py order --side WEST --squad WEST-1 \
        --order capture --place agia_marina
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


def describe(reply: dict[str, Any]) -> str:
    """Say what the rules made of a Command, judgement or refusal alike."""
    if reply.get("status") == "ok":
        return f"accepted: {reply['result']}"
    reason = reply.get("reason") or reply.get("error") or {}
    code = reason.get("code") or reason.get("class")
    return f"{reply.get('status')}: {code} — {reason.get('detail')}"


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Build the one Command this run will issue."""
    # Shared as a parent rather than declared before the verb: `purchase --side`
    # reads the way the Command does, and `--side purchase` does not.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--host", default="127.0.0.1")
    common.add_argument("--port", type=int, default=9099)
    common.add_argument("--side", default="WEST")

    parser = argparse.ArgumentParser(description=__doc__)
    verbs = parser.add_subparsers(dest="verb", required=True)

    purchase = verbs.add_parser("purchase", parents=[common], help="buy a Squad at its Base")
    purchase.add_argument("--squad-type", default="rifle")
    purchase.add_argument("--count", type=int, default=1, help="how many to buy in a row")

    order = verbs.add_parser("order", parents=[common], help="give a Squad a standing Order")
    order.add_argument("--squad", required=True, help="the id a Purchase reported, e.g. WEST-1")
    order.add_argument(
        "--order", default="capture", choices=("capture", "defend", "assault", "reserve")
    )
    order.add_argument(
        "--place", default="", help="the Objective or Base it names; empty for Reserve"
    )

    return parser.parse_args(argv)


def payloads(args: argparse.Namespace) -> list[dict[str, Any]]:
    """Render the run as Command payloads, in the order they go out."""
    if args.verb == "purchase":
        return [
            {
                "command": "purchase",
                "side": args.side,
                "args": {"squad_type": args.squad_type},
            }
            for _ in range(args.count)
        ]
    return [
        {
            "command": "order",
            "side": args.side,
            "args": {
                "squad": args.squad,
                "order": args.order,
                "place": args.place,
            },
        }
    ]


def main(argv: list[str] | None = None) -> int:
    """Issue the Commands and report what the rules made of each."""
    args = parse_args(argv)
    with (
        socket.create_connection((args.host, args.port), timeout=5) as sock,
        sock.makefile("rb") as stream,
    ):
        for index, payload in enumerate(payloads(args)):
            reply = send(
                sock, stream, {"id": f"demo-{index}", "verb": "command", "payload": payload}
            )
            print(describe(reply))  # noqa: T201 — this script's output is the demo
    return 0


if __name__ == "__main__":
    sys.exit(main())
