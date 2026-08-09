"""The durable snapshot store: atomic save, last-known-good load (#290).

`cti_daemon.snapshot` is the pure document (#289); `cti_daemon.store` is the
bytes-on-disk half — the part ADR-0003 names and ADR-0069 fixes the ordering for.
These tests hold the durability contract the issue's criteria state, and the
seam's contract the daemon's control handlers reach through:

- A save writes a temp file, makes its bytes durable, atomically renames, makes
  the directory durable, and only then promotes a verified snapshot.
- The previous verified snapshot stays recoverable until the replacement is
  fully durable and revalidated; a failed save destroys neither generation.
- Kill-mid-write and fault injection cover every durability edge, and boot
  selects either the new complete snapshot or the previous verified one, never
  torn data.
- An invalid newest snapshot is preserved for diagnosis; load falls back with a
  structured warning, and refuses (creating nothing) when no generation
  validates. A fresh Campaign is never reached through an error fallback.
- The seam's contract — what the control handlers delegate to — is `Store`, and
  `FakeStore` honours it: a save returns the version, checksum and generation
  and nothing of the document; a load runs the document through `restore` and
  hands the snapshot back, refusing typed when it will not.
- Paths, permissions, checksums, versions, generations and rollback source are
  observable without the snapshot's contents leaving the file.
"""

from __future__ import annotations

import contextlib
import inspect
import json
import stat
from typing import TYPE_CHECKING

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from cti_daemon import snapshot
from cti_daemon.commands import SIDES
from cti_daemon.observation import INTACT
from cti_daemon.snapshot import CURRENT_VERSION, Snapshot, SquadRecord
from cti_daemon.squads import Order
from cti_daemon.store import (
    CHECKSUM_ALGORITHM,
    CURRENT,
    DIR_MODE,
    FILE_MODE,
    FRAME_VERSION,
    INCOMING,
    INCOMING_TMP,
    MAX_REJECTED,
    PREVIOUS,
    REASON_CORRUPT,
    REJECTED_GLOB,
    FakeStore,
    LoadOutcome,
    NothingToLoadError,
    NoValidSnapshotError,
    RefusedSnapshotError,
    SaveFailedError,
    SaveOutcome,
    SnapshotStore,
    Store,
    StoreError,
    _checksum,
)

if TYPE_CHECKING:
    from pathlib import Path


def _snap(
    *,
    clock: float = 120.0,
    funds: dict[str, int] | None = None,
    squads: tuple[SquadRecord, ...] = (),
    loadouts: dict[str, str] | None = None,
) -> Snapshot:
    """One well-formed snapshot, with the fields a test varies under test."""
    return Snapshot(
        clock=clock,
        owners={"agia_marina": "WEST", "girna": "NEUTRAL", "pyrgos": "NEUTRAL", "maxwell": "EAST"},
        hq={"base_west": INTACT, "base_east": INTACT},
        funds=funds or dict.fromkeys(SIDES, 200),
        squads=squads,
        loadouts=loadouts or {},
    )


def _framed(snapshot_value: Snapshot, *, version: int | None = None) -> bytes:
    """Render a framed document, optionally at a forged snapshot version.

    Reuses the store's own checksum so a forged version reads as an unsupported
    version rather than as a torn frame — the distinction the load fallback has
    to tell apart to refuse with the right typed reason. No envelope generation:
    a missing one reads as 0, which is the store's pre-numbering state, so a
    test-built frame round-trips through the same gate a real write does.
    """
    document = snapshot.serialise(snapshot_value)
    if version is not None:
        document["version"] = version
    frame: dict[str, object] = {
        "frame": FRAME_VERSION,
        "algorithm": CHECKSUM_ALGORITHM,
        "checksum": _checksum(document),
        "snapshot": document,
    }
    return json.dumps(frame, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"


snapshots = st.builds(
    Snapshot,
    clock=st.floats(min_value=0, allow_nan=False, allow_infinity=False),
    owners=st.just({"agia_marina": "WEST"}),
    hq=st.just({"base_west": INTACT}),
    funds=st.just(dict.fromkeys(SIDES, 200)),
    squads=st.just(
        (
            SquadRecord(
                id="w1",
                side="WEST",
                squad_type="rifle",
                size=8,
                order=Order(kind="defend", place="agia_marina"),
                at="agia_marina",
            ),
        )
    ),
    loadouts=st.just({"uid-1": "rifleman"}),
)


# --- the seam: the Protocol, the fake, and the operational-facts contract -----


def test_the_fake_store_satisfies_the_protocol() -> None:
    assert isinstance(FakeStore(), Store)


def test_a_concrete_store_satisfies_the_protocol(tmp_path: Path) -> None:
    assert isinstance(SnapshotStore(tmp_path / "snap"), Store)


def test_a_save_outcome_carries_integers_not_contents(tmp_path: Path) -> None:
    # The record a save returns is what telemetry and the coordinator observe.
    # It carries the version, the checksum, the generation, the byte count and
    # the duration — and nothing that is in the snapshot.
    assert set(inspect.signature(SaveOutcome).parameters) == {
        "version",
        "checksum",
        "generation",
        "bytes_written",
        "duration_us",
    }
    store = SnapshotStore(tmp_path / "snap")
    outcome = store.save(_snap(loadouts={"uid-1": "rifleman"}))
    assert outcome.version == CURRENT_VERSION
    assert outcome.checksum
    assert outcome.generation == 1
    assert outcome.bytes_written > 0
    serialised = repr(outcome)
    assert "rifleman" not in serialised
    assert "uid-1" not in serialised


def test_the_fake_store_returns_the_same_operational_facts() -> None:
    outcome = FakeStore().save(_snap(clock=30.0))
    assert outcome.version == CURRENT_VERSION
    assert outcome.generation == 1
    assert outcome.checksum


def test_each_save_advances_the_generation() -> None:
    keeper = FakeStore()
    first = keeper.save(_snap(clock=1.0))
    second = keeper.save(_snap(clock=2.0))
    assert (first.generation, second.generation) == (1, 2)


def test_each_concrete_save_advances_the_generation_across_a_restart(tmp_path: Path) -> None:
    directory = tmp_path / "snap"
    first = SnapshotStore(directory).save(_snap(clock=1.0))
    # A new store over the same directory reads the trusted slot's generation,
    # so the counter survives a restart rather than resetting to 1.
    second = SnapshotStore(directory).save(_snap(clock=2.0))
    assert (first.generation, second.generation) == (1, 2)


def test_a_load_hands_back_what_was_saved_at_its_generation() -> None:
    keeper = FakeStore()
    saved = keeper.save(_snap(clock=30.0))
    loaded = keeper.load()

    assert isinstance(loaded, LoadOutcome)
    assert loaded.snapshot == _snap(clock=30.0)
    assert loaded.generation == saved.generation
    assert loaded.checksum == saved.checksum


def test_a_load_off_an_empty_store_is_a_typed_refusal() -> None:
    with pytest.raises(NothingToLoadError):
        FakeStore().load()


def test_the_load_refusals_are_store_refusals() -> None:
    assert issubclass(NothingToLoadError, StoreError)
    assert issubclass(NoValidSnapshotError, StoreError)


# --- the round trip, and the durable modes --------------------------------


@given(value=snapshots)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_a_saved_snapshot_loads_back_as_the_same_value(tmp_path: Path, value: Snapshot) -> None:
    store = SnapshotStore(tmp_path / "snap")
    store.save(value)
    assert store.load().snapshot == value


def test_a_save_makes_the_trusted_file_mode_0600_in_a_mode_0700_dir(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path / "snap")
    store.save(_snap())

    file_mode = stat.S_IMODE((tmp_path / "snap" / CURRENT).stat().st_mode)
    dir_mode = stat.S_IMODE((tmp_path / "snap").stat().st_mode)
    assert file_mode == FILE_MODE
    assert dir_mode == DIR_MODE


# --- two generations, and the rotation between them -----------------------


def test_two_saves_rotate_generations_keeping_the_previous_one(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path / "snap")
    first, second = _snap(clock=1.0), _snap(clock=2.0)

    store.save(first)
    assert [p.name for p in store.generations()] == [CURRENT]

    store.save(second)
    names = {p.name for p in store.generations()}
    assert names == {CURRENT, PREVIOUS}
    assert store.load().snapshot == second


def test_the_previous_generation_survives_until_the_next_is_verified(tmp_path: Path) -> None:
    # The trusted slot is only rotated once the candidate is revalidated, so a
    # save that fails at the gate leaves the previous trusted generation whole.
    store = SnapshotStore(tmp_path / "snap")
    store.save(_snap(clock=1.0))
    store.save(_snap(clock=2.0))  # current=2, previous=1

    names_before = {p.name for p in store.generations()}
    assert names_before == {CURRENT, PREVIOUS}

    # A third save that fails revalidation must not touch either generation.
    faulty = _FaultyStore(store.directory, fail_revalidation=True)
    with pytest.raises(SaveFailedError):
        faulty.save(_snap(clock=3.0))
    names_after = {p.name for p in SnapshotStore(store.directory).generations()}
    assert CURRENT in names_after
    assert PREVIOUS in names_after
    # The failed candidate was preserved for diagnosis rather than dropped.
    assert any(name.startswith("snapshot.rejected-") for name in names_after)


# --- boot falls back to the previous verified generation ------------------


@pytest.mark.parametrize(
    ("corrupt", "reason"),
    [
        (b"", "empty"),
        (b"not json at all", "corrupt"),
        (b"{", "corrupt"),
    ],
)
def test_an_unreadable_newest_falls_back_to_the_previous_verified_one(
    tmp_path: Path, corrupt: bytes, reason: str
) -> None:
    store = SnapshotStore(tmp_path / "snap")
    store.save(_snap(clock=1.0))
    store.save(_snap(clock=2.0))  # current=2, previous=1

    (tmp_path / "snap" / CURRENT).write_bytes(corrupt)
    outcome = store.load()

    assert outcome.snapshot == _snap(clock=1.0)
    assert outcome.rolled_back is True
    assert outcome.recovered is False
    assert len(outcome.refusals) == 1
    assert outcome.refusals[0].reason == reason
    assert outcome.refusals[0].preserved is not None


def test_a_newest_with_a_tampered_checksum_falls_back(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path / "snap")
    store.save(_snap(clock=1.0))
    store.save(_snap(clock=2.0))

    current = tmp_path / "snap" / CURRENT
    frame = json.loads(current.read_bytes())
    frame["checksum"] = "0" * 64  # a checksum that matches nothing
    current.write_bytes(json.dumps(frame).encode())

    outcome = store.load()
    assert outcome.rolled_back is True
    assert outcome.refusals[0].reason == "corrupt"


def test_a_newest_at_an_unsupported_version_falls_back_and_keeps_the_reason(
    tmp_path: Path,
) -> None:
    store = SnapshotStore(tmp_path / "snap")
    store.save(_snap(clock=1.0))
    store.save(_snap(clock=2.0))

    # Replace the trusted slot with a validly-framed snapshot at a version no
    # migration reaches — the torn-write family's sibling, refused typed.
    (tmp_path / "snap" / CURRENT).write_bytes(
        _framed(_snap(clock=9.0), version=CURRENT_VERSION + 1)
    )

    outcome = store.load()
    assert outcome.rolled_back is True
    assert outcome.refusals[0].reason == "unsupported_version"


def test_a_byte_rotted_field_is_caught_by_the_checksum(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path / "snap")
    store.save(_snap(clock=1.0))
    store.save(_snap(clock=2.0))

    current = tmp_path / "snap" / CURRENT
    frame = json.loads(current.read_bytes())
    # Flip a byte inside the snapshot payload, leaving the frame's checksum
    # claiming the untampered bytes: the mismatch is what catches it.
    frame["snapshot"]["clock"] = 999.0
    current.write_bytes(json.dumps(frame).encode())

    outcome = store.load()
    assert outcome.rolled_back is True
    assert outcome.refusals[0].reason == "corrupt"


# --- load refuses and creates nothing when no generation validates --------


def test_no_valid_snapshot_refuses_and_creates_nothing(tmp_path: Path) -> None:
    directory = tmp_path / "snap"
    directory.mkdir()
    (directory / CURRENT).write_bytes(b"torn")
    (directory / PREVIOUS).write_bytes(b"also torn")
    store = SnapshotStore(directory)

    with pytest.raises(NoValidSnapshotError) as exc:
        store.load()
    assert {refusal.generation for refusal in exc.value.refusals} == {CURRENT, PREVIOUS}
    # Nothing was promoted into the trusted slot: a fresh Campaign stays the
    # caller's explicit act, never an error fallback.
    assert not (directory / CURRENT).exists() or _is_unreadable(directory / CURRENT)
    assert any(p.name.startswith("snapshot.rejected-") for p in directory.iterdir())


def test_an_empty_store_raises_nothing_to_load_and_creates_nothing(tmp_path: Path) -> None:
    directory = tmp_path / "snap"
    directory.mkdir()
    store = SnapshotStore(directory)

    with pytest.raises(NothingToLoadError):
        store.load()
    assert list(directory.iterdir()) == []


def test_a_refusal_is_never_a_fresh_campaign(tmp_path: Path) -> None:
    # Every fault path raises rather than returns, so neither an empty store nor
    # a corrupt one can become a fresh Campaign through the store.
    empty = SnapshotStore(tmp_path / "empty")
    empty.directory.mkdir()
    corrupt = SnapshotStore(tmp_path / "corrupt")
    corrupt.directory.mkdir()
    (corrupt.directory / CURRENT).write_bytes(b"torn")
    for store in (empty, corrupt):
        with pytest.raises((NothingToLoadError, NoValidSnapshotError)):
            store.load()


# --- a save that crashed is recovered, or leaves nothing readable ---------


def test_a_crash_after_staging_recovers_the_incoming_snapshot(tmp_path: Path) -> None:
    # A save that wrote and revalidated the candidate but crashed before
    # rotating it into the trusted slot leaves it as `incoming`. Boot reads
    # newest-first, recovers it, and the previous trusted generation survives.
    store = SnapshotStore(tmp_path / "snap")
    store.save(_snap(clock=1.0))  # current=1
    # Simulate the mid-promotion crash: stage a second candidate, demote the
    # trusted slot to the fallback, and leave no trusted slot.
    (tmp_path / "snap" / INCOMING).write_bytes(_framed(_snap(clock=2.0)))
    (tmp_path / "snap" / CURRENT).replace(tmp_path / "snap" / PREVIOUS)

    outcome = store.load()
    assert outcome.recovered is True
    assert outcome.rolled_back is False
    assert outcome.snapshot == _snap(clock=2.0)
    names = {p.name for p in store.generations()}
    assert CURRENT in names
    assert INCOMING not in names  # promoted out of the staging slot


def test_a_crash_after_the_durable_write_before_the_rename_leaves_nothing_readable(
    tmp_path: Path,
) -> None:
    # Bytes durable in the temp file but never renamed are never visible under
    # a trusted name. Boot removes the temp and finds nothing — never torn data.
    store = _CrashStore(tmp_path / "snap")
    with pytest.raises(OSError, match="killed after the durable write"):
        store.save(_snap())

    reader = SnapshotStore(tmp_path / "snap")
    with pytest.raises(NothingToLoadError):
        reader.load()
    assert not (tmp_path / "snap" / INCOMING_TMP).exists()  # cleared
    assert not (tmp_path / "snap" / CURRENT).exists()  # nothing trusted


# --- rejected generations are bounded -------------------------------------


def test_rejected_generations_are_pruned_to_the_newest_few(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path / "snap")
    a, b = _snap(clock=1.0), _snap(clock=2.0)
    store.save(a)
    store.save(b)  # current=b, previous=a

    # Each round corrupts the trusted slot, load refuses it and heals from the
    # fallback, then two saves re-establish two live generations. Every refusal
    # preserves a rejected slot, and the bound keeps only the newest few.
    for _ in range(MAX_REJECTED + 3):
        (tmp_path / "snap" / CURRENT).write_bytes(b"torn")
        with contextlib.suppress(NoValidSnapshotError):
            store.load()
        store.save(a)
        store.save(b)

    rejected = list((tmp_path / "snap").glob(REJECTED_GLOB))
    assert len(rejected) <= MAX_REJECTED


# --- helpers ---------------------------------------------------------------


def _is_unreadable(path: Path) -> bool:
    """Return True when a generation file still will not validate as a snapshot."""
    try:
        SnapshotStore(path.parent).load()
    except (NoValidSnapshotError, NothingToLoadError):
        return True
    return False


class _FaultyStore(SnapshotStore):
    """A store whose revalidation of the staged candidate fails on demand.

    The candidate's bytes are written and staged exactly as a real save leaves
    them; only the independent revalidation is forced to refuse, which is the
    path a torn write that passed framing but failed a deeper check would take.
    """

    def __init__(self, directory: Path, *, fail_revalidation: bool) -> None:
        super().__init__(directory)
        self._fail_revalidation = fail_revalidation

    def _read_valid(self, path: Path) -> tuple[Snapshot, str, int]:
        if self._fail_revalidation and path.name == INCOMING:
            raise RefusedSnapshotError(REASON_CORRUPT, "injected torn write")
        return super()._read_valid(path)


class _CrashStore(SnapshotStore):
    """A store killed after the durable write, before the atomic rename.

    Models the process dying with the temp file's bytes on disk but the rename
    into the staging slot never issued — the window a torn write lives in.
    """

    def _write_durable(self, path: Path, payload: bytes) -> None:
        super()._write_durable(path, payload)
        message = "killed after the durable write, before the rename"
        raise OSError(message)
