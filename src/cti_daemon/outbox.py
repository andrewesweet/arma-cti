"""Acknowledged delivery for messages pushed from the daemon to the game."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class UnknownSequenceError(Exception):
    """An acknowledgement named a sequence number the outbox never issued."""


@dataclass(frozen=True, slots=True)
class Entry:
    """One pushed message and the sequence number it was issued under."""

    sequence: int
    message: dict[str, Any]


@dataclass(slots=True)
class Outbox:
    """Holds pushed messages until the game acknowledges them."""

    _entries: list[Entry] = field(default_factory=list)
    _issued: int = 0

    def push(self, message: dict[str, Any]) -> Entry:
        """Queue a message for delivery and return the entry it was issued as."""
        self._issued += 1
        entry = Entry(self._issued, message)
        self._entries.append(entry)
        return entry

    def pending(self) -> list[Entry]:
        """Everything not yet acknowledged, oldest first."""
        return list(self._entries)

    def ack(self, *, through: int) -> int:
        """Drop every entry up to and including `through`; return how many went.

        Acknowledging the same sequence twice drops nothing and is not a fault:
        at-most-once delivery makes a repeated acknowledgement ordinary.
        """
        if through > self._issued:
            detail = f"acknowledged {through}, highest issued is {self._issued}"
            raise UnknownSequenceError(detail)
        before = len(self._entries)
        self._entries = [entry for entry in self._entries if entry.sequence > through]
        return before - len(self._entries)
