"""Answering a request the caller has already been answered.

The shim reuses one TCP connection and resends the payload on a fresh one when
an exchange on the cached one fails (ADR-0005). A write that succeeded before
the read failed has already been carried out here, so that resend is
at-least-once delivery onto a port that spends Funds: a Purchase executed twice,
attributed identically (#69).

Removing the resend would trade duplicate execution for lost Commands, and
teaching the shim which verbs are safe to resend would put the domain inside a
shim ADR-0005 keeps domain-agnostic. So the receiver is what makes the resend
safe: a request line identical to one already answered is answered from the
answer it was given, and never carried out again (ADR-0034).

Keyed on the whole line rather than on the id alone. A resend is byte-identical
by construction — the shim holds the payload and writes the same bytes — while
a line differing anywhere is a different request whose caller happened to reuse
an id, and refusing to carry that out would lose real work.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from hashlib import blake2b

#: How many answered requests are remembered. The shim resends only the request
#: whose exchange just failed, so one would do for the hazard as it exists; a
#: few hundred covers several connections doing it at once and still bounds a
#: session-long process to a few megabytes of replies.
WINDOW = 256


@dataclass(frozen=True, slots=True)
class Answer:
    """One reply, and enough of its request to write the replay down."""

    id: str | None
    verb: str | None
    reply: str


@dataclass(slots=True)
class Answered:
    """The recent past of the wire: which lines were answered, and with what."""

    window: int = WINDOW
    _answers: OrderedDict[bytes, Answer] = field(default_factory=OrderedDict)

    def recall(self, line: str) -> Answer | None:
        """Return the answer this exact line already had, or None if it is new."""
        return self._answers.get(_key(line))

    def remember(self, line: str, *, request_id: str | None, verb: str | None, reply: str) -> None:
        """Record what one line was answered, retiring the oldest if full."""
        key = _key(line)
        if key in self._answers:
            self._answers.move_to_end(key)
        else:
            self._answers[key] = Answer(id=request_id, verb=verb, reply=reply)
        while len(self._answers) > self.window:
            self._answers.popitem(last=False)

    def __len__(self) -> int:
        """How many answers are currently remembered."""
        return len(self._answers)


def _key(line: str) -> bytes:
    """Digest one request line.

    Digested rather than held: an `observe` line is kilobytes of report, and the
    window has no use for its contents.
    """
    return blake2b(line.encode("utf-8"), digest_size=16).digest()
