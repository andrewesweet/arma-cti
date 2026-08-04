"""Acknowledged delivery for Effects pushed from the daemon to the game.

It holds `Effect` objects rather than wire documents (#77). Clean Architecture's
rule is that data crossing a boundary is in the form most convenient for the
inner circle and is serialised at the edge; queueing `serialise_effect(...)` here
had the domain constructing the wire's format, so every effect producer was
coupled to the rendering and a change to it touched three modules. The rendering
now happens once, in `Daemon._poll`, which is where effects actually leave.

`push` is also where the effect catalogue binds (#145). Every world effect
leaves through here whoever produced it, so refusing an Effect the catalogue
does not declare binds every producer, present and future, and every producer's
unit test exercises the check. It is not on `Effect` construction, because that
also serves `parse_effect` — the codec's decode half, which deliberately
validates envelope shape and nothing more.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from cti_daemon.commands import EFFECTS, Effect


class UnknownSequenceError(Exception):
    """An acknowledgement named a sequence number the outbox never issued."""


@dataclass(frozen=True, slots=True)
class Entry:
    """One pushed Effect and the sequence number it was issued under."""

    sequence: int
    effect: Effect


@dataclass(slots=True)
class Outbox:
    """Holds pushed Effects until the game acknowledges them."""

    _entries: list[Entry] = field(default_factory=list)
    _issued: int = 0

    def push(self, effect: Effect) -> Entry:
        """Queue an Effect for delivery and return the entry it was issued as.

        Refuses one the catalogue does not declare (#145): an out-of-catalogue
        Effect is a producer's bug, not a rejection the world is owed, so it is
        raised — in the same spirit as the port refusing a rejection code off
        its own list — and a producer drifting from `commands.EFFECTS` is a red
        `just unit` rather than an in-world discovery.
        """
        declared = EFFECTS.get(effect.name)
        if declared is None:
            message = f"{effect.name!r} is not an effect the catalogue declares"
            raise ValueError(message)
        if set(effect.args) != set(declared):
            message = (
                f"a {effect.name} effect carries exactly {sorted(declared)}, "
                f"got {sorted(effect.args)}"
            )
            raise ValueError(message)
        self._issued += 1
        entry = Entry(self._issued, effect)
        self._entries.append(entry)
        return entry

    def pending(self) -> list[Entry]:
        """Everything not yet acknowledged, oldest first."""
        return list(self._entries)

    @property
    def depth(self) -> int:
        """How many Effects are waiting to be acknowledged.

        A count rather than `len(pending())`, which copies the whole list: the
        depth is read on every request now that its growth is gauged (#142), and
        the one moment the number matters — a pump that has stopped draining
        while income keeps paying — is the moment the list is longest.
        """
        return len(self._entries)

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
