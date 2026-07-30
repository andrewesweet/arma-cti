"""The envelope the shim and the daemon exchange.

Newline-delimited JSON over TCP loopback, one persistent connection (ADR-0005).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


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


def encode(reply: Reply) -> str:
    """Serialise a reply to the one line that goes back over the socket."""
    return json.dumps(reply.envelope, separators=(",", ":"))
