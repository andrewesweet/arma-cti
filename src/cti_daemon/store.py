"""The durable snapshot store: bytes on disk, atomically replaced (#290).

`cti_daemon.snapshot` is the pure document — `serialise` and `restore` over an
in-memory value, with no file, no socket, no clock (#289). This module is the
other half ADR-0003 names: those bytes made durable, so a Campaign that dies
between saves resumes from a complete snapshot rather than a torn one.

Atomicity is the whole issue and the failure is silent. A snapshot half-written
when the process dies must be **unreadable**, not readable-and-wrong: a Campaign
that resumes from a torn snapshot continues into a corrupted world rather than
stopping. So a save never edits the trusted file in place. It writes a fresh
candidate to a temp file, makes the candidate's bytes durable, atomically renames
it into a staging slot, re-reads and revalidates it, and only then rotates the
trusted generation. The durability ordering is the one ADR-0069 fixes:

  write temporary file -> make the file durable -> atomic replacement ->
  make the directory entry durable -> promote a verified snapshot to last-known-good.

"Verified" is load-bearing, and it is why this store owns the schema gate rather
than handing a raw document back for a handler to `restore`. The staged candidate
is read back and put through the same checksum-and-`restore` gate a boot uses,
and a candidate that fails it is never promoted. That gate is also what makes
ADR-0069 Ruling 1's cross-generation fallback work: when the newest generation is
at a schema version no migration reaches, boot falls back to the previous
*verified* generation rather than refusing — and deciding that requires reading
each generation through `restore`, which only the layer that owns the generations
can do. A store that returned a raw document and left `restore` to a handler
could not fall back on a schema refusal, because the handler sees one document,
not the generations behind it. The typed distinction the control lane surfaces
(`no_valid_generation` / `unsupported_schema` / `corrupt`) is preserved — but it
is read off the store's typed refusals rather than re-run at the handler.

Two generations are kept on purpose. `snapshot.json` is the verified
last-known-good — what boot trusts. `snapshot.prev.json` is the one before it,
recoverable as a fallback. Boot reads newest-first and falls back to the previous
verified snapshot when the newest is corrupt, torn, or at an unsupported version,
preserving the invalid one for diagnosis rather than silently dropping it. If no
generation validates, load refuses and creates nothing: a fresh Campaign is an
explicit act the caller owns, never an error fallback (ADR-0069 Ruling 1).

Integrity is a checksum, not faith in the filesystem. Each file is a framed
document — the snapshot plus a SHA-256 over its canonical encoding — so a torn
write, a truncated tail, or a byte-rotted field is detected before `restore` ever
sees it. The checksum covers the snapshot payload alone, recomputed on read, so a
frame whose bytes were damaged in flight refuses rather than half-loading. The
frame also carries a monotonic `generation` counter (which save this was) so a
load's acknowledgement can name the generation it landed on without naming what
was in it; generation is store envelope metadata, not part of the snapshot
document whose schema is a sign-off gate.

Nothing here knows what a Campaign is. The store takes `Snapshot` values (via
`snapshot.serialise`) and hands back `Snapshot` values (via `snapshot.restore`),
so the document boundary #289 drew stays clean: the durability mechanics are not a
sign-off gate, the snapshot semantics are, and a semantic question — what counts
as "good", what a resume barrier refuses — is left for the gate rather than
invented in code.

The on-disk files carry a player UID (the loadout record, ADR-0056) and nothing
secret, but they are written mode 0o600 in a mode 0o700 directory anyway: a
personal account of who picked which kit is not for the next user on this box,
and restrictive modes cost nothing. Paths, permissions, checksums, versions,
generations and the rollback source are observable through the outcome records
these methods return and through telemetry — never the snapshot's contents and
never a credential (there is none to log).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol, runtime_checkable

from cti_daemon import snapshot as snapshot_module
from cti_daemon.snapshot import (
    CURRENT_VERSION,
    Snapshot,
    SnapshotError,
    UnsupportedSnapshotVersionError,
    serialise,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

# The framed document's version. Independent of the snapshot's own `version`:
# this is the envelope's shape (where the checksum lives, what keys it carries),
# and a frame at a version other than this is refused as unreadable rather than
# guessed at. It moves only when the envelope itself changes, which is rare and
# deliberate.
FRAME_VERSION: Final = 1

# The one integrity algorithm the store reads or writes. Named in the frame so a
# future change is additive (a frame names what it was checksummed with) rather
# than a silent reinterpretation of bytes an old save laid down.
CHECKSUM_ALGORITHM: Final = "sha256"

# The generation files, in the one directory a store owns. Names rather than
# derived paths so a test pins them and an operator recognises them on disk:
#
# - ``snapshot.json``        the verified last-known-good (what boot trusts).
# - ``snapshot.prev.json``   the previous verified generation (the fallback).
# - ``snapshot.incoming.json`` a staged candidate: durable as bytes, written and
#   revalidated, but not yet rotated into the trusted slot. Present only across a
#   save that crashed between staging and promotion; boot recovers it.
# - ``snapshot.incoming.tmp`` the temp file a save writes before its atomic
#   rename. Transient: a save that crashed before the rename leaves one behind,
#   and boot removes it because it was never visible under a trusted name.
# - ``snapshot.rejected-<n>.json`` a generation that failed validation, preserved
#   for diagnosis. Bounded: the store keeps the newest few and prunes the rest.
CURRENT: Final = "snapshot.json"
PREVIOUS: Final = "snapshot.prev.json"
INCOMING: Final = "snapshot.incoming.json"
INCOMING_TMP: Final = "snapshot.incoming.tmp"
REJECTED_GLOB: Final = "snapshot.rejected-*.json"

# How many rejected generations to keep for diagnosis. A save or a load that
# refuses a generation sets it aside under a monotonic name; without a bound a
# store on a failing disk would grow them without end. The newest few are enough
# to diagnose a corruption, and a healthy store keeps none.
MAX_REJECTED: Final = 4

# File and directory modes for the durable store. Restrictive on purpose: the
# loadout record is a personal account, and a permissive mode on a shared box is
# a leak that costs nothing to avoid.
DIR_MODE: Final = 0o700
FILE_MODE: Final = 0o600

# The typed reasons a generation is refused (ADR-0069 Ruling 1). A closed
# vocabulary named once so a refusal site names its reason rather than re-spelling
# the string, and a test or an operator matches on the value. `corrupt` covers the
# torn, truncated and byte-rotted family — anything the checksum or the frame gate
# catches; `malformed` is a document that framed and checksummed but `restore`
# refused for its shape.
REASON_EMPTY: Final = "empty"
REASON_CORRUPT: Final = "corrupt"
REASON_UNSUPPORTED_VERSION: Final = "unsupported_version"
REASON_MALFORMED: Final = "malformed"


class StoreError(Exception):
    """A base for the store's typed refusals, in the spirit of `SnapshotError`."""


class NothingToLoadError(StoreError):
    """The store holds no snapshot at all.

    The ordinary first-boot state: no Campaign was ever saved here, so there is
    nothing to resume. Distinct from `NoValidSnapshotError` because nothing went
    wrong — the caller starts a fresh Campaign as an explicit act, knowing the
    store is empty rather than corrupted. The control lane surfaces this as
    `no_valid_generation`.
    """


class NoValidSnapshotError(StoreError):
    """Every generation the store holds is unreadable, so load refuses.

    The data-loss shape: generations exist and none validates. Load creates
    nothing and the caller decides what to do — which is the explicit-fresh-start
    act, never an error fallback (ADR-0069 Ruling 1). The refused attempts are
    carried on the exception so the operator can see what was found and why each
    was refused, and so the control lane can tell `unsupported_schema` (every
    refusal was an unsupported version) from `corrupt` (anything else).
    """

    def __init__(self, directory: Path, refusals: tuple[Refusal, ...]) -> None:
        """Record where nothing validated and what each generation was refused for."""
        seen = ", ".join(f"{r.generation}={r.reason}" for r in refusals) or "no generations"
        super().__init__(f"no valid snapshot in {directory}: {seen}")
        self.directory = directory
        self.refusals = refusals


class SaveFailedError(StoreError):
    """A save could not promote a verified snapshot, and nothing was promoted.

    The candidate was written and staged but failed its independent revalidation,
    or the filesystem refused a step the durability ordering requires. Either way
    both trusted generations are untouched — the property the criteria name — and
    the failed candidate is preserved for diagnosis. Raised rather than returned
    because a save that reports success has to mean a new generation is durable.
    """

    def __init__(self, candidate: Path, reason: str, preserved: Path | None) -> None:
        """Record the candidate that failed and where its bytes were preserved."""
        where = f", preserved at {preserved}" if preserved is not None else ""
        super().__init__(f"snapshot save failed at {candidate}: {reason}{where}")
        self.candidate = candidate
        self.reason = reason
        self.preserved = preserved


class RefusedSnapshotError(Exception):
    """One generation's file would not validate, with a typed reason.

    The reason vocabulary is what distinguishes the cases ADR-0069 Ruling 1 names
    without re-parsing a message: ``empty`` (no bytes), ``corrupt`` (not JSON, a
    wrong frame, or a checksum mismatch — the torn/truncated/rotted family),
    ``unsupported_version`` (a version with no migration path) and ``malformed``
    (a document that parsed and checksummed but `restore` refused).
    """

    def __init__(self, reason: str, detail: str) -> None:
        """Record the typed reason and the human-readable detail."""
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True, slots=True)
class Refusal:
    """One generation that load refused, preserved for diagnosis.

    Carried on a `LoadOutcome` (and on `NoValidSnapshotError`) so the operator can
    see which newer generation was set aside and why, without the snapshot's
    contents leaving the store.
    """

    generation: str
    reason: str
    detail: str
    preserved: Path | None


@dataclass(frozen=True, slots=True)
class SaveOutcome:
    """What a successful save made durable, observable without its contents.

    The version, checksum and generation an acknowledgement carries (which schema
    was saved, a digest of what, and which save number), plus the byte count and
    duration the coordinator's telemetry records. No snapshot fields, no
    credentials — the contents stay in the file.
    """

    version: int
    checksum: str
    generation: int
    bytes_written: int
    duration_us: int


@dataclass(frozen=True, slots=True)
class LoadOutcome:
    """What boot loaded, and what it had to refuse to get there.

    ``snapshot`` is the chosen generation, already put through `restore` by the
    store's validation gate. ``generation`` is the save counter that frame
    carries, so a load ack names which save it landed on. ``rolled_back`` is true
    when the newest generation was refused and an older verified one was loaded
    instead; ``recovered`` is true when a save that crashed mid-promotion was
    completed at boot (a newer generation recovered, not a fall to an older one).
    ``refusals`` carries every newer generation that was set aside for diagnosis.
    """

    snapshot: Snapshot
    generation: int
    rolled_back: bool
    recovered: bool
    checksum: str
    version: int
    refusals: tuple[Refusal, ...]


@runtime_checkable
class Store(Protocol):
    """Durability for one Campaign's saves: write atomically, read back the latest.

    `save` delegates durability — the store is what fsyncs and what keeps the
    last-known-good safe across a crash mid-write — and owns the schema gate that
    decides whether a generation is loadable, because that gate is what a
    cross-generation fallback turns on (ADR-0069 Ruling 1). `load` hands back the
    newest generation the store can recover as an already-validated `Snapshot`,
    raising `NothingToLoadError` (empty) or `NoValidSnapshotError` (every
    generation unreadable). The snapshot never crosses this seam towards the
    transport; it crosses only to reach the daemon's apply step.
    """

    def save(self, snapshot: Snapshot) -> SaveOutcome:
        """Persist a snapshot atomically, returning the operational facts."""
        ...

    def load(self) -> LoadOutcome:
        """Return the newest recoverable generation, or raise if none validates."""
        ...


def checksum(document: Mapping[str, object]) -> str:
    """Return a stable hex digest of a snapshot document, for an ack to carry.

    Canonical — sorted keys, tight separators — so the same document digests the
    same across the save that wrote it and the load that read it, and a
    generation's checksum is comparable rather than merely recorded. The frame's
    checksum is this digest of the snapshot payload, recomputed on read.
    """
    serialised = json.dumps(document, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialised.encode("utf-8")).hexdigest()


def _canonical(document: dict[str, object]) -> bytes:
    """Render a snapshot document as the stable bytes a checksum is taken over.

    Sorted keys and tight separators, so the same document is the same bytes on
    every write and every read regardless of dict insertion order. The snapshot
    carries floats (the clock); Python's JSON renders a float deterministically,
    so a value round-trips to the same checksum.
    """
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _checksum(document: dict[str, object]) -> str:
    """Return the hex SHA-256 over a snapshot document's canonical encoding."""
    return hashlib.sha256(_canonical(document)).hexdigest()


def _frame(snapshot: Snapshot, generation: int) -> bytes:
    """Render a snapshot as the framed document a durable write stores.

    The checksum is over the snapshot payload alone, recomputed on read, so a
    frame whose envelope or payload was damaged in flight refuses at the gate
    rather than half-loading. ``generation`` rides in the envelope — which save
    this was — outside the checksummed payload, because it is store metadata, not
    part of the snapshot document whose schema is a sign-off gate. A trailing
    newline keeps the file friendly to tools that expect one and is outside the
    payload.
    """
    document = serialise(snapshot)
    frame: dict[str, object] = {
        "frame": FRAME_VERSION,
        "algorithm": CHECKSUM_ALGORITHM,
        "checksum": _checksum(document),
        "generation": generation,
        "snapshot": document,
    }
    return json.dumps(frame, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"


def _fsync_directory(directory: Path) -> None:
    """Make a directory's entry changes durable.

    The rename that promotes a snapshot is durable in the file's bytes once the
    file is fsynced, but the directory entry that names it is not until the
    directory itself is fsynced. Skipping this is the classic "rename returned but
    the new name was lost on power loss" gap, and closing it is one of the steps
    ADR-0069's ordering names. A directory fsync needs the directory's fd, not a
    file inside it.
    """
    fd = os.open(str(directory), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class SnapshotStore:
    """The durable snapshot store: atomic save, last-known-good load (#290)."""

    def __init__(self, directory: Path) -> None:
        """Record the one directory this store owns. Created on first save."""
        self.directory = directory

    # --- save: the durability ordering ADR-0069 fixes ----------------------

    def save(self, snapshot: Snapshot) -> SaveOutcome:
        """Make one snapshot the verified last-known-good, atomically.

        Never edits the trusted file in place. The candidate is written to a temp
        file, made durable, atomically renamed into the staging slot, made durable
        as a directory entry, independently revalidated, and only then rotated
        into the trusted slot — with the prior trusted generation kept as the
        fallback. A failure at any step after staging preserves the candidate for
        diagnosis and leaves both trusted generations untouched.

        Raises `SaveFailedError` when the candidate could not be made the verified
        last-known-good; on that path nothing is promoted.
        """
        started = time.perf_counter_ns()
        # mode=DIR_MODE at creation: owner-only bits are umask-proof (umask can
        # only clear group/other bits, which are already absent), so the directory
        # the snapshot lives in is restrictive on a shared box rather than at the
        # process umask's mercy. exist_ok leaves an existing dir's mode untouched.
        self.directory.mkdir(parents=True, exist_ok=True, mode=DIR_MODE)
        generation = self._next_generation()
        payload = _frame(snapshot, generation)

        tmp = self.directory / INCOMING_TMP
        incoming = self.directory / INCOMING

        # write temporary file, then make the file's bytes durable.
        self._write_durable(tmp, payload)
        # atomic replacement into the staging slot, then make that entry durable.
        tmp.replace(incoming)
        _fsync_directory(self.directory)

        # independently revalidate the staged candidate before it is trusted.
        try:
            _snapshot, checksum_value, _version = self._read_valid(incoming)
        except RefusedSnapshotError as refusal:
            preserved = self._set_aside(incoming)
            raise SaveFailedError(incoming, refusal.reason, preserved) from refusal

        # promote: the prior trusted generation becomes the fallback, the verified
        # candidate becomes the trusted slot. Each rename is followed by a
        # directory fsync so the rotation survives a crash at any point.
        current = self.directory / CURRENT
        previous = self.directory / PREVIOUS
        if current.exists():
            current.replace(previous)
            _fsync_directory(self.directory)
        incoming.replace(current)
        _fsync_directory(self.directory)

        return SaveOutcome(
            version=CURRENT_VERSION,
            checksum=checksum_value,
            generation=generation,
            bytes_written=len(payload),
            duration_us=(time.perf_counter_ns() - started) // 1_000,
        )

    def _next_generation(self) -> int:
        """Return the next monotonic save number, one above the trusted slot's.

        Read off the current file's frame so the counter survives a restart: a
        daemon that saved generation 5, died, and boots into a save mints 6, not
        1. A store with no trusted file yet starts at 1.
        """
        current = self.directory / CURRENT
        if not current.exists():
            return 1
        previous = self._generation_of(current)
        return previous + 1 if previous > 0 else 1

    def _write_durable(self, path: Path, payload: bytes) -> None:
        """Create a file at mode 0o600, write, flush, and fsync its bytes.

        Opened through `os.open` so the mode is set at creation rather than
        narrowed after a briefly permissive file exists. `os.fdopen` takes
        ownership of the descriptor and closes it with the file.
        """
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, FILE_MODE)
        with os.fdopen(fd, "wb", closefd=True) as sink:
            sink.write(payload)
            sink.flush()
            os.fsync(sink.fileno())

    # --- load: newest-first, fall back, refuse if none ----------------------

    def load(self) -> LoadOutcome:
        """Return the newest valid generation, falling back to the previous one.

        Newest-first over the staged candidate, the trusted slot, and the
        fallback. The first generation that validates — through the frame, the
        checksum and `restore` — is loaded; any newer generation that was refused
        is set aside for diagnosis. If none validates, raise
        `NoValidSnapshotError`; if the store is empty, raise `NothingToLoadError`.
        Either refusal creates nothing — a fresh Campaign is the caller's explicit
        act (ADR-0069 Ruling 1).

        A load that falls back or recovers also heals the store: the chosen
        generation is rotated into the trusted slot and any invalid newer one is
        preserved, so the next save promotes over a consistent trusted file
        rather than over corruption.
        """
        self._clear_transient()
        candidates = [
            (name, self.directory / name)
            for name in (INCOMING, CURRENT, PREVIOUS)
            if (self.directory / name).exists()
        ]
        if not candidates:
            raise NothingToLoadError(self.directory)

        refusals: list[tuple[str, Path, RefusedSnapshotError]] = []
        chosen: tuple[str, Snapshot, str, int] | None = None
        for name, path in candidates:
            try:
                snapshot, checksum_value, version = self._read_valid(path)
            except RefusedSnapshotError as refusal:
                refusals.append((name, path, refusal))
                continue
            chosen = (name, snapshot, checksum_value, version)
            break

        if chosen is None:
            preserved = tuple(self._set_aside(path) for _n, path, _refusal in refusals)
            raise NoValidSnapshotError(
                self.directory,
                tuple(
                    Refusal(name, refusal.reason, refusal.detail, kept)
                    for (name, _p, refusal), kept in zip(refusals, preserved, strict=True)
                ),
            )

        chosen_name, snapshot, checksum_value, version = chosen
        # Every refusal precedes the chosen generation in precedence, so each is a
        # newer generation boot refused — preserve them for diagnosis.
        preserved_refusals = tuple(
            Refusal(name, refusal.reason, refusal.detail, self._set_aside(path))
            for name, path, refusal in refusals
        )
        rolled_back = chosen_name == PREVIOUS
        recovered = chosen_name == INCOMING
        self._recover_to_current(chosen_name)
        return LoadOutcome(
            snapshot=snapshot,
            generation=self._generation_of(self.directory / CURRENT),
            rolled_back=rolled_back,
            recovered=recovered,
            checksum=checksum_value,
            version=version,
            refusals=preserved_refusals,
        )

    def _read_valid(self, path: Path) -> tuple[Snapshot, str, int]:
        """Read and fully validate one generation file, or refuse it typed.

        The single validation gate both save's revalidation and load use, so the
        candidate a save just wrote is held to the same standard boot holds a
        stored file to. Returns the snapshot, its checksum, and the version it
        restored to; raises `RefusedSnapshotError` with a typed reason otherwise.
        An unreadable file is refused as corrupt rather than crashing boot — one
        bad generation must not sink a Campaign that has a fallback.
        """
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise RefusedSnapshotError(
                REASON_CORRUPT, f"{path.name} could not be read: {exc}"
            ) from exc
        if not raw:
            raise RefusedSnapshotError(REASON_EMPTY, f"{path.name} is empty")

        document, actual = self._validated_payload(raw, path.name)

        try:
            snapshot = snapshot_module.restore(document)
        except UnsupportedSnapshotVersionError as exc:
            raise RefusedSnapshotError(REASON_UNSUPPORTED_VERSION, str(exc)) from exc
        except SnapshotError as exc:
            raise RefusedSnapshotError(REASON_MALFORMED, str(exc)) from exc
        return snapshot, actual, CURRENT_VERSION

    def _generation_of(self, path: Path) -> int:
        """Return the generation counter a frame carries, or 0 when it does not.

        Generation is advisory envelope metadata: a missing or unreadable value
        reads as 0 (the store's pre-numbering state) rather than refusing the
        whole generation, because a load's correctness turns on the snapshot, not
        on which save number it was.
        """
        try:
            frame = json.loads(path.read_bytes())
        except (json.JSONDecodeError, OSError):
            return 0
        if not isinstance(frame, dict):
            return 0
        generation = frame.get("generation")
        if isinstance(generation, int) and not isinstance(generation, bool):
            return generation
        return 0

    def _validated_payload(self, raw: bytes, name: str) -> tuple[dict[str, object], str]:
        """Validate a framed document's envelope and checksum, returning its payload.

        The frame structure (its version and algorithm) and the checksum over the
        snapshot payload are checked here, separate from the read and from
        `restore`, so the same gate sits between the bytes and `restore` whether
        they came from a save's revalidation or from boot. Returns the snapshot
        document and its recomputed checksum; raises `RefusedSnapshotError`
        (reason `corrupt`) when the bytes are not the framed document they claim
        to be.
        """
        try:
            frame = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RefusedSnapshotError(REASON_CORRUPT, f"{name} is not valid JSON: {exc}") from exc
        if not isinstance(frame, dict):
            raise RefusedSnapshotError(REASON_CORRUPT, f"{name} frame is not an object")

        if frame.get("frame") != FRAME_VERSION:
            raise RefusedSnapshotError(
                REASON_CORRUPT, f"{name} frame version is {frame.get('frame')!r}"
            )
        if frame.get("algorithm") != CHECKSUM_ALGORITHM:
            raise RefusedSnapshotError(
                REASON_CORRUPT, f"{name} algorithm is {frame.get('algorithm')!r}"
            )
        document = frame.get("snapshot")
        if not isinstance(document, dict):
            raise RefusedSnapshotError(REASON_CORRUPT, f"{name} carries no snapshot object")

        expected = frame.get("checksum")
        actual = _checksum(document)
        if not isinstance(expected, str) or not hmac.compare_digest(actual, expected):
            raise RefusedSnapshotError(
                REASON_CORRUPT, f"{name} checksum mismatch: torn, truncated, or corrupted"
            )
        return document, actual

    # --- generation management ----------------------------------------------

    def _set_aside(self, path: Path) -> Path:
        """Rename an invalid generation to a bounded diagnosis slot.

        The rejected file keeps its bytes for diagnosis under a monotonic name,
        and the store prunes to the newest few so a failing disk does not grow
        them without end. The directory is fsynced so the rename survives a
        crash; the path returned is where the bytes now live.
        """
        if path.parent != self.directory or not path.exists():
            # Already moved (load may consider a generation twice across its
            # preserve and recover steps), or gone — nothing to set aside.
            return path
        rejected = self._next_rejected_path()
        path.replace(rejected)
        _fsync_directory(self.directory)
        self._prune_rejected()
        return rejected

    def _next_rejected_path(self) -> Path:
        """Return the next monotonic rejected-slot path, never colliding with one held."""
        highest = 0
        for existing in self._rejected_files():
            stem = existing.stem  # "snapshot.rejected-<n>"
            _, _, number = stem.rpartition("-")
            highest = max(highest, int(number) if number.isdigit() else 0)
        return self.directory / REJECTED_GLOB.replace("*", str(highest + 1))

    def _rejected_files(self) -> list[Path]:
        """Existing rejected slots, ordered by their monotonic number."""
        files = sorted(self.directory.glob(REJECTED_GLOB))

        def slot_number(path: Path) -> int:
            _, _, number = path.stem.rpartition("-")
            return int(number) if number.isdigit() else 0

        return sorted(files, key=slot_number)

    def _prune_rejected(self) -> None:
        """Keep only the newest `MAX_REJECTED` diagnosis slots, removing older."""
        files = self._rejected_files()
        for stale in files[:-MAX_REJECTED]:
            stale.unlink(missing_ok=True)

    def _clear_transient(self) -> None:
        """Remove a temp file a crashed save left behind.

        `snapshot.incoming.tmp` is never visible under a trusted name: a save
        writes it, then atomically renames it into the staging slot. A crash
        before that rename leaves it behind, and boot removes it because nothing
        ever read from it. Missing is the ordinary case.
        """
        (self.directory / INCOMING_TMP).unlink(missing_ok=True)

    def _recover_to_current(self, chosen_name: str) -> None:
        """Rotate the chosen valid generation into the trusted slot.

        After load's preserve step has set aside every invalid newer generation,
        the chosen file is the one boot trusts. If it is not already the trusted
        slot, rotate it in — completing a save that crashed mid-promotion
        (``incoming``) or promoting the fallback after the newest was refused
        (``previous``). Each rename is followed by a directory fsync.
        """
        if chosen_name == CURRENT:
            return
        current = self.directory / CURRENT
        previous = self.directory / PREVIOUS
        incoming = self.directory / INCOMING
        if chosen_name == INCOMING:
            # A save staged and revalidated the candidate but crashed before
            # rotating. The trusted slot may still hold the prior generation;
            # demote it to the fallback, then promote the candidate.
            if current.exists():
                current.replace(previous)
                _fsync_directory(self.directory)
            incoming.replace(current)
        elif chosen_name == PREVIOUS:
            # The newest was refused and set aside; promote the fallback so the
            # trusted slot holds a verified generation again.
            previous.replace(current)
        _fsync_directory(self.directory)

    # --- inspection ---------------------------------------------------------

    def generations(self) -> Iterator[Path]:
        """Yield every file this store holds, for tests and diagnosis.

        Not used on the load path: it is a read on the directory's contents for a
        caller that wants to see what is there without parsing it.
        """
        if self.directory.exists():
            yield from sorted(self.directory.iterdir())


@dataclass(slots=True)
class FakeStore:
    """An in-memory `Store` for tests: what was last saved, loadable as written.

    Honours the same contract as the atomic store — `save` takes a `Snapshot`,
    `load` runs it through `restore` and returns a `LoadOutcome`, and a held
    document that `restore` refuses comes back as a typed `NoValidSnapshotError` —
    so the daemon's control handlers test against a store that is deterministic
    and in process. Not a substitute for the atomic store: no fsync, no crash
    safety, no on-disk last-known-good. A test wanting a refused load injects the
    bad document straight onto ``_document``, which is what a real store's
    unreadable bytes look like to the handler once the durability layer has handed
    them back through `restore`.
    """

    _document: dict[str, object] | None = None
    _generation: int = 0
    _checksum: str = ""

    def save(self, snapshot: Snapshot) -> SaveOutcome:
        """Record the snapshot's document as the latest generation, returning the facts."""
        self._document = serialise(snapshot)
        self._generation += 1
        self._checksum = checksum(self._document)
        return SaveOutcome(
            version=CURRENT_VERSION,
            checksum=self._checksum,
            generation=self._generation,
            bytes_written=len(_canonical(self._document)),
            duration_us=0,
        )

    def load(self) -> LoadOutcome:
        """Return the last snapshot saved, or raise if the document will not restore.

        Runs `restore` the way the atomic store does, so a held document at an
        unsupported version or a malformed one refuses with the same typed
        `NoValidSnapshotError` a real store raises when every generation is
        unreadable — which is what lets a control-handler test inject a bad
        document and read the typed refusal off the seam.
        """
        if self._document is None:
            message = "the store holds no saved generation"
            raise NothingToLoadError(message)
        try:
            snapshot = snapshot_module.restore(self._document)
        except UnsupportedSnapshotVersionError as exc:
            refusal = Refusal("(fake)", REASON_UNSUPPORTED_VERSION, str(exc), None)
            raise NoValidSnapshotError(Path(), (refusal,)) from exc
        except SnapshotError as exc:
            refusal = Refusal("(fake)", REASON_MALFORMED, str(exc), None)
            raise NoValidSnapshotError(Path(), (refusal,)) from exc
        return LoadOutcome(
            snapshot=snapshot,
            generation=self._generation,
            rolled_back=False,
            recovered=False,
            checksum=self._checksum,
            version=CURRENT_VERSION,
            refusals=(),
        )


__all__ = [
    "CHECKSUM_ALGORITHM",
    "CURRENT",
    "DIR_MODE",
    "FILE_MODE",
    "FRAME_VERSION",
    "INCOMING",
    "INCOMING_TMP",
    "MAX_REJECTED",
    "PREVIOUS",
    "REASON_CORRUPT",
    "REASON_EMPTY",
    "REASON_MALFORMED",
    "REASON_UNSUPPORTED_VERSION",
    "REJECTED_GLOB",
    "FakeStore",
    "LoadOutcome",
    "NoValidSnapshotError",
    "NothingToLoadError",
    "Refusal",
    "RefusedSnapshotError",
    "SaveFailedError",
    "SaveOutcome",
    "SnapshotStore",
    "Store",
    "StoreError",
    "checksum",
]
