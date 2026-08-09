"""The persistence seam a Phase-2 save/load delegates durability to (#291).

#290 lands the concrete atomic store — last-known-good, the checkpoint
coordinator, fsync. This is the contract that store satisfies and the daemon's
control handlers reach for, so #291 builds against a `Protocol` and a fake
rather than against a store that is not on this branch yet. Both sides of the
seam agree on operational facts alone: a save's version, checksum and
generation; a load's document and where it came from. The snapshot document
crosses the seam daemon-internal and never reaches the transport, which is what
"the transport never learns snapshot shape" comes to mechanically (#288).

A refusal is typed rather than messaged, because a load's three failure modes
call for three answers and a string the caller re-parses is the thing this
exists not to be:

- `NoValidGenerationError` — the store holds nothing it can hand back. The store's
  own finding (#290's last-known-good is empty or unreadable), raised here.
- `UnsupportedSnapshotVersionError` — the store handed a document back, and the
  daemon's `snapshot.restore` refused it for a version with no migration. The
  schema's finding, raised by `snapshot` and mapped by the handler.
- `SnapshotError` — same path, a document that is shaped wrong. The schema's
  finding again, mapped to a distinct refusal so corruption stays tellable from
  a version this build is merely too old for.

Decoupled from `snapshot` on purpose. This module knows a document is a mapping
that carries a `version` and that it can checksum; it does not know the
document's shape, so the seam moves when #290 lands without dragging the schema
with it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, cast, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Mapping


class StoreError(Exception):
    """A store refused a save or a load. Typed subclasses name the mode."""


class NoValidGenerationError(StoreError):
    """The store holds no generation it can hand back to a load.

    The store's own finding: nothing was ever saved, or every generation it held
    is unreadable at the durability layer (#290's last-known-good is empty).
    Typed apart from a document the schema refuses, because the answer differs —
    "there is no save to load" is not "the save there is will not parse", and a
    caller that conflated them could not tell a fresh Campaign from a broken one.
    """


@dataclass(frozen=True, slots=True)
class SaveOutcome:
    """What a save's acknowledgement carries: operational facts, never the document.

    `version` is the snapshot version observed in the document written, `checksum`
    a hex digest of the bytes the store persisted, and `generation` the store's
    own monotonic counter for this save. None of the three is the snapshot
    itself, so an ack built from this says the save landed without saying what
    was in it (#291's acknowledgement-only rule).
    """

    version: int
    checksum: str
    generation: int


@dataclass(frozen=True, slots=True)
class Loaded:
    """What a load brings back across the seam: the document, and where it came from.

    The document is the schema's to validate and migrate — `snapshot.restore`
    runs on it at the handler, not in the store — so the store's job on the way
    back is to hand the bytes it durably held and the generation they were saved
    at. `checksum` is the digest of those bytes, carried so a load's ack can
    name what was read without naming what was in it.
    """

    document: dict[str, object]
    generation: int
    checksum: str


@runtime_checkable
class Store(Protocol):
    """Durability for one Campaign's saves: write atomically, read back the latest.

    `save` delegates durability — the store is what fsyncs and what keeps the
    last-known-good safe across a crash mid-write. `load` hands back the latest
    generation the store can recover, raising `NoValidGeneration` when it has
    none. Neither method returns the snapshot to the transport; the document
    crosses this seam only to reach the daemon's own validate/migrate step
    (ADR-0008, #291).
    """

    def save(self, document: Mapping[str, object]) -> SaveOutcome:
        """Persist a snapshot document atomically, returning the operational facts."""
        ...

    def load(self) -> Loaded:
        """Return the latest recoverable generation, or raise `NoValidGenerationError`."""
        ...


def checksum(document: Mapping[str, object]) -> str:
    """Return a stable hex digest of a snapshot document, for an ack to carry.

    Canonical — sorted keys, tight separators — so the same document digests the
    same across the save that wrote it and the load that read it, and a
    generation's checksum is comparable rather than merely recorded. The real
    store (#290) digests the bytes it writes; this is the form the seam agrees
    on until that lands, and a digest of the canonical serialisation is what a
    correct write would produce.
    """
    serialised = json.dumps(document, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialised.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class FakeStore:
    """An in-memory `Store` for tests: what was last saved, loadable as written.

    Not a substitute for the atomic store — no fsync, no crash safety, no
    last-known-good — only a stand-in that honours the seam's contract so the
    daemon's control handlers test against a store that is deterministic and in
    process. A test wanting a corrupt or unsupported document injects one
    straight onto `_document`, which is what a real store's unreadable bytes
    look like to the handler once the durability layer has handed them back.
    """

    _document: dict[str, object] | None = None
    _generation: int = 0
    _checksum: str = ""

    def save(self, document: Mapping[str, object]) -> SaveOutcome:
        """Record the document as the latest generation, returning the facts."""
        self._document = dict(document)
        self._generation += 1
        self._checksum = checksum(document)
        return SaveOutcome(
            version=cast("int", document.get("version", 0)),
            checksum=self._checksum,
            generation=self._generation,
        )

    def load(self) -> Loaded:
        """Return the last document saved, or raise `NoValidGeneration` if none."""
        if self._document is None:
            message = "the store holds no saved generation"
            raise NoValidGenerationError(message)
        return Loaded(
            document=dict(self._document),
            generation=self._generation,
            checksum=self._checksum,
        )
