"""The envelope the shim and the daemon exchange.

Newline-delimited JSON over TCP loopback, one persistent connection (ADR-0005).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Final

#: The key every reply carries the answering process's identity under (#96,
#: ADR-0036). Named rather than spelled out at each site because the world
#: latches it and the exported schema publishes it.
EPOCH_KEY: Final = "epoch"

#: What a reader of a reply may count on, by status. Exported to the addon
#: (`addons/main/generated/command-schema.json`) so that the SQF side's branch
#: and the daemon's envelope cannot drift: `status` and `epoch` are present
#: whatever happened, and the payload key follows from the status.
#:
#: A shim transport failure is `{"error": "..."}` with no `status` at all, which
#: is why absence of `status` — not presence of `error` — is how the world tells
#: a dead daemon from a daemon saying no.
REPLY_ENVELOPE: Final[dict[str, tuple[str, ...]]] = {
    "always": ("id", EPOCH_KEY, "status"),
    "ok": ("result",),
    "rejected": ("reason",),
    "error": ("error",),
}


@dataclass(frozen=True, slots=True)
class Request:
    """One decoded request line."""

    id: str
    verb: str
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class Reply:
    """One reply, ready to serialise."""

    envelope: dict[str, Any]


class MalformedRequestError(Exception):
    """The line was not a request. There may be no id to reply against."""

    def __init__(self, detail: str, request_id: str | None = None) -> None:
        """Record what was wrong and, when the line carried one, the id."""
        super().__init__(detail)
        self.detail = detail
        self.request_id = request_id


def decode(line: str) -> Request:
    """Parse one request line, or raise `MalformedRequestError`."""
    try:
        envelope: Any = json.loads(line)
    except json.JSONDecodeError as exc:
        detail = f"not JSON: {exc.msg}"
        raise MalformedRequestError(detail) from exc
    if not isinstance(envelope, dict):
        detail = f"envelope must be an object, got {type(envelope).__name__}"
        raise MalformedRequestError(detail)

    # The id is read first and carried onto the failure: a reply the caller
    # cannot match to its request is barely better than no reply at all.
    request_id = envelope.get("id")
    if not isinstance(request_id, str):
        detail = "`id` must be a string"
        raise MalformedRequestError(detail)
    verb = envelope.get("verb")
    if not isinstance(verb, str):
        detail = "`verb` must be a string"
        raise MalformedRequestError(detail, request_id)
    payload = envelope.get("payload", {})
    if not isinstance(payload, dict):
        detail = "`payload` must be an object"
        raise MalformedRequestError(detail, request_id)
    return Request(id=request_id, verb=verb, payload=payload)


def accepted(request_id: str, result: dict[str, Any]) -> Reply:
    """Report that the request was understood and carried out."""
    return Reply({"id": request_id, "status": "ok", "result": result})


def rejected(request_id: str, code: str, detail: str) -> Reply:
    """Report that the request was understood and refused by the rules."""
    return Reply(
        {"id": request_id, "status": "rejected", "reason": {"code": code, "detail": detail}}
    )


def failed(request_id: str | None, error_class: str, detail: str) -> Reply:
    """Report that the daemon could not answer the request as asked."""
    return Reply(
        {
            "id": request_id,
            "status": "error",
            "error": {"class": error_class, "detail": detail},
        }
    )


def stamped(reply: Reply, epoch: str) -> Reply:
    """Carry the answering process's epoch on a reply, whatever its status.

    Applied once, at the edge, rather than by each of the three constructors
    above: the epoch is a fact about the process, not about the judgement, and
    a constructor that had to be told it would be a constructor that could be
    told the wrong one.
    """
    return Reply({**reply.envelope, EPOCH_KEY: epoch})


def mint_epoch() -> str:
    """Mint the identity of one daemon process.

    Start time and pid. The property that matters is that a restarted daemon
    never mints the epoch its predecessor did, and start time alone does not
    give it: two processes can start inside one clock tick. Nanoseconds and the
    pid together are enough, and both are facts about this process rather than
    draws from a generator ADR-0016 would want seeded.

    Deliberately not a counter or anything persisted: a daemon that could
    recover its predecessor's epoch would be a daemon claiming to be it, and
    what it holds is a factory-fresh Campaign.
    """
    return f"{time.time_ns():x}-{os.getpid():x}"


def encode(reply: Reply) -> str:
    """Serialise a reply to the one line that goes back over the socket."""
    return json.dumps(reply.envelope, separators=(",", ":"))
