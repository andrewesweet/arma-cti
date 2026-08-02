"""Delivery guarantees for messages the daemon pushes to the game.

ADR-0005: callback delivery is at-most-once across mission boundaries — a
callback fired before a handler exists sits in the engine buffer, and a mission
restart clears it. Nothing downstream can recover a message that was dropped
there, so the daemon holds every pushed message until the game says it arrived.
"""

from __future__ import annotations

import pytest

from cti_daemon.commands import Effect
from cti_daemon.outbox import Outbox, UnknownSequenceError


def order(n: int = 0) -> Effect:
    """One Effect, the domain object the outbox now holds (#77)."""
    return Effect(name="order_issued", side="WEST", args={"squad": f"WEST-{n}"})


def test_a_pushed_message_is_pending_until_it_is_acknowledged() -> None:
    outbox = Outbox()
    outbox.push(order())
    assert [entry.effect for entry in outbox.pending()] == [order()]


def test_sequence_numbers_are_issued_in_order_from_one() -> None:
    outbox = Outbox()
    assert [outbox.push(order(n)).sequence for n in range(3)] == [1, 2, 3]


def test_acknowledging_a_sequence_clears_it_and_everything_before_it() -> None:
    outbox = Outbox()
    for n in range(4):
        outbox.push(order(n))
    outbox.ack(through=2)
    assert [entry.sequence for entry in outbox.pending()] == [3, 4]


def test_an_unacknowledged_message_is_delivered_again() -> None:
    # The mission restarted, the engine buffer was cleared, and the game asks
    # again from where it last acknowledged. Nothing is lost.
    outbox = Outbox()
    outbox.push(order(1))
    outbox.push(order(2))
    outbox.ack(through=1)
    first_retry = [entry.sequence for entry in outbox.pending()]
    second_retry = [entry.sequence for entry in outbox.pending()]
    assert first_retry == second_retry == [2]


def test_acknowledging_twice_is_not_an_error() -> None:
    # At-most-once delivery means a duplicate ack is expected, not a fault.
    outbox = Outbox()
    outbox.push(order(1))
    assert outbox.ack(through=1) == 1
    assert outbox.ack(through=1) == 0


def test_acknowledging_a_sequence_that_was_never_issued_is_refused() -> None:
    outbox = Outbox()
    outbox.push(order(1))
    with pytest.raises(UnknownSequenceError):
        outbox.ack(through=9)
