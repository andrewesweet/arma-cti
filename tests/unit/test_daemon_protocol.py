"""Envelope contract between the shim and the daemon.

One line of JSON in, one line of JSON out (ADR-0005). These tests pin what the
SQF side is allowed to depend on: the id it sent comes back, and success,
domain rejection and error are three things it can tell apart.
"""

from __future__ import annotations

import json

import pytest

from cti_daemon import protocol


def test_a_request_carries_an_id_a_verb_and_a_payload() -> None:
    request = protocol.decode('{"id": "r-1", "verb": "ping", "payload": {"n": 2}}')
    assert (request.id, request.verb, request.payload) == ("r-1", "ping", {"n": 2})


def test_a_successful_reply_echoes_the_id_and_carries_the_result() -> None:
    line = protocol.encode(protocol.accepted("r-1", {"pong": True}))
    assert json.loads(line) == {"id": "r-1", "status": "ok", "result": {"pong": True}}


def test_a_domain_rejection_is_a_reply_not_a_failure() -> None:
    # The daemon understood the request and refused it on the rules. That is a
    # different thing from the daemon being unable to answer.
    line = protocol.encode(protocol.rejected("r-2", "unknown_sequence", "never issued seq 9"))
    assert json.loads(line) == {
        "id": "r-2",
        "status": "rejected",
        "reason": {"code": "unknown_sequence", "detail": "never issued seq 9"},
    }


@pytest.mark.parametrize(
    "line",
    [
        pytest.param("{not json", id="not JSON at all"),
        pytest.param("[]", id="a JSON array is not an envelope"),
        pytest.param('"r-1"', id="a bare string is not an envelope"),
        pytest.param('{"verb": "ping"}', id="no id to reply against"),
        pytest.param('{"id": "r-1"}', id="no verb to dispatch on"),
        pytest.param('{"id": 7, "verb": "ping"}', id="an id that is not a string"),
        pytest.param(
            '{"id": "r-1", "verb": "ping", "payload": 3}', id="a payload that is not an object"
        ),
    ],
)
def test_a_line_that_is_not_a_request_is_refused_at_decode(line: str) -> None:
    with pytest.raises(protocol.MalformedRequestError):
        protocol.decode(line)


def test_measure_prices_a_document_exactly_as_encode_renders_it_nested() -> None:
    # `Daemon._poll` prices a drain incrementally with this (#156): a reply
    # grows by the message's own measure, plus one comma once it has a
    # neighbour, so the sum must be the encoding it stands in for — not close
    # to it. The non-ASCII place pins that escaping cannot split the two.
    first = {"sequence": 1, "message": {"effect": "order_issued", "args": {}}}
    second = {"sequence": 2, "message": {"effect": "order_issued", "args": {"place": "café"}}}
    empty = len(protocol.encode(protocol.accepted("r-3", {"messages": []})))
    one = len(protocol.encode(protocol.accepted("r-3", {"messages": [first]})))
    both = len(protocol.encode(protocol.accepted("r-3", {"messages": [first, second]})))
    assert one == empty + protocol.measure(first)
    assert both == one + 1 + protocol.measure(second)


def test_an_error_reply_names_the_failure_class_and_tolerates_an_unknown_id() -> None:
    line = protocol.encode(protocol.failed(None, "malformed_request", "not JSON: bad token"))
    assert json.loads(line) == {
        "id": None,
        "status": "error",
        "error": {"class": "malformed_request", "detail": "not JSON: bad token"},
    }


def test_every_reply_carries_a_status_so_a_transport_failure_cannot_be_mistaken_for_one() -> None:
    # A transport failure never reaches this module: the shim answers SQF with
    # its own {"error": "connect: ..."} and no status. Keying on `status` is
    # therefore total, which is what makes the three outcomes three.
    replies = [
        protocol.accepted("r", {}),
        protocol.rejected("r", "code", "detail"),
        protocol.failed("r", "internal", "detail"),
    ]
    statuses = [json.loads(protocol.encode(reply))["status"] for reply in replies]
    assert statuses == ["ok", "rejected", "error"]
