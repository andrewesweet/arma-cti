"""The checkpoint coordinator: dirty tracking, the 30-second bound, off-lock I/O (#290).

`cti_daemon.store` makes one snapshot durable; `cti_daemon.coordinator` decides
*when*, and these tests hold the timing and concurrency contract the issue's
criteria state:

- A persistent mutation marks the Campaign dirty, and a checkpoint becomes
  durable within 30 seconds of the **first** unsaved mutation — measured from
  the first, not the last, so a burst longer than the interval still checkpoints
  on time.
- Clean teardown forces a final checkpoint.
- The snapshot copy is taken under the daemon's narrow request lock; encoding,
  validation and disk I/O happen off it — a blocked writer does not block
  Command handling for its I/O duration.
- Concurrent save requests coalesce; interrupted work is not reported as success.
- Telemetry records the outcome without ever logging the snapshot's contents.
"""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

from conftest import all_rows, observe

from cti_daemon import transport
from cti_daemon.commands import SIDES
from cti_daemon.coordinator import (
    CHECKPOINT_INTERVAL_SECONDS,
    CheckpointCoordinator,
)
from cti_daemon.observation import INTACT
from cti_daemon.snapshot import Snapshot
from cti_daemon.store import SaveOutcome, SnapshotStore
from cti_daemon.telemetry import Telemetry

if TYPE_CHECKING:
    from pathlib import Path

# How long a test waits for the background worker to do something real. Not a
# gate timeout and never extended to make a test pass: it is the bound on the
# latency between a notification under the condition and the worker acting on
# it, which is microseconds in life and bounded here only against a stuck box.
_WAIT = 2.0


def _snap() -> Snapshot:
    """One snapshot the coordinator can write, with both sides' state in it."""
    return Snapshot(
        clock=120.0,
        owners={"agia_marina": "WEST", "girna": "NEUTRAL", "pyrgos": "NEUTRAL", "maxwell": "EAST"},
        hq={"base_west": INTACT, "base_east": INTACT},
        funds=dict.fromkeys(SIDES, 200),
        squads=(),
        loadouts={},
    )


class _Clock:
    """A fake monotonic clock a test advances by hand."""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _RecordingStore(SnapshotStore):
    """A real durable store that also counts its saves and signals each one."""

    def __init__(self, directory: Path) -> None:
        super().__init__(directory)
        self.count = 0
        self.saved: list[Snapshot] = []
        self._event = threading.Event()

    def save(self, snapshot: Snapshot) -> SaveOutcome:
        outcome = super().save(snapshot)
        self.saved.append(snapshot)
        self.count += 1
        self._event.set()
        return outcome

    def wait_for_save(self, timeout: float = _WAIT) -> None:
        if not self._event.wait(timeout=timeout):
            message = f"no save within {timeout}s"
            raise AssertionError(message)


class _FailingStore(SnapshotStore):
    """A store whose every save raises, counting the attempts and signalling."""

    def __init__(self, directory: Path) -> None:
        super().__init__(directory)
        self.attempts = 0
        self._event = threading.Event()

    def save(self, snapshot: Snapshot) -> SaveOutcome:  # noqa: ARG002 - name matches the
        # base override (ty checks it); this failure model ignores the value.
        self.attempts += 1
        self._event.set()
        message = "the disk refused the write"
        raise OSError(message)

    def wait_for_attempt(self, min_count: int = 1, timeout: float = _WAIT) -> None:
        deadline = time.monotonic() + timeout
        while self.attempts < min_count:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            self._event.wait(timeout=remaining)
            self._event.clear()
        if self.attempts < min_count:
            message = f"only {self.attempts} attempts in {timeout}s"
            raise AssertionError(message)


class _BlockingStore(SnapshotStore):
    """A store whose first save blocks until released, simulating a stalled fsync."""

    def __init__(self, directory: Path) -> None:
        super().__init__(directory)
        self.count = 0
        self.first_started = threading.Event()
        self.release = threading.Event()

    def save(self, snapshot: Snapshot) -> SaveOutcome:
        self.count += 1
        if not self.first_started.is_set():
            self.first_started.set()
            self.release.wait(timeout=_WAIT * 2.5)
        return super().save(snapshot)

    def wait_for_save_started(self, timeout: float = _WAIT) -> None:
        if not self.first_started.wait(timeout=timeout):
            message = f"no save started within {timeout}s"
            raise AssertionError(message)


# --- the 30-second bound, measured from the first mutation ----------------


def test_the_checkpoint_interval_constant_is_thirty_seconds() -> None:
    assert CHECKPOINT_INTERVAL_SECONDS == 30.0


def test_the_deadline_is_set_at_the_first_mutation_and_not_pushed_by_later_ones(
    tmp_path: Path,
) -> None:
    clock = _Clock(0.0)
    store = _RecordingStore(tmp_path / "snap")
    coord = CheckpointCoordinator(store, snapshot_source=_snap, interval=30.0, monotonic=clock)
    coord.start()
    try:
        coord.mark_dirty()  # first mutation: deadline fixed at clock=30
        assert store.count == 0  # not due at clock=0

        clock.advance(20.0)
        coord.mark_dirty()  # a second mutation: deadline must stay at 30, not become 50
        assert store.count == 0  # still not due at clock=20 — the deadline was not pushed

        clock.advance(11.0)  # clock=31, past the first mutation's deadline
        coord.mark_dirty()  # nudge the worker past its wait
        store.wait_for_save()
        assert store.count == 1  # one write, fired at the first mutation's deadline
    finally:
        coord.shutdown(timeout=_WAIT)


def test_concurrent_save_requests_coalesce_into_one_write(tmp_path: Path) -> None:
    clock = _Clock(0.0)
    store = _RecordingStore(tmp_path / "snap")
    coord = CheckpointCoordinator(store, snapshot_source=_snap, interval=10_000.0, monotonic=clock)
    coord.start()
    try:
        coord.mark_dirty()
        coord.mark_dirty()
        coord.mark_dirty()  # three mutations before any write
        coord.checkpoint_now(timeout=_WAIT)  # force, and wait for the write
        assert store.count == 1  # coalesced into one write of the latest state
    finally:
        coord.shutdown(timeout=_WAIT)


# --- clean teardown forces a final checkpoint -----------------------------


def test_clean_teardown_forces_a_final_checkpoint(tmp_path: Path) -> None:
    clock = _Clock(0.0)  # frozen: the deadline is never due on its own
    store = _RecordingStore(tmp_path / "snap")
    coord = CheckpointCoordinator(store, snapshot_source=_snap, interval=30.0, monotonic=clock)
    coord.start()
    coord.mark_dirty()
    assert store.count == 0  # nothing written yet

    coord.shutdown(timeout=_WAIT)  # clean teardown
    assert store.count == 1  # a final checkpoint was forced
    assert store.load().snapshot == _snap()  # and it landed durably


# --- an interrupted write is not reported as success ----------------------


def test_an_interrupted_write_is_not_reported_as_success_and_is_retried(
    tmp_path: Path,
) -> None:
    clock = _Clock(0.0)
    store = _FailingStore(tmp_path / "snap")
    coord = CheckpointCoordinator(store, snapshot_source=_snap, interval=30.0, monotonic=clock)
    coord.start()
    try:
        coord.mark_dirty()
        clock.advance(31.0)
        coord.mark_dirty()  # nudge: the worker writes and fails
        store.wait_for_attempt(min_count=1)

        assert isinstance(coord.last_outcome, Exception)
        assert not isinstance(coord.last_outcome, SaveOutcome)  # never reported as success

        # The Campaign stays dirty and the coordinator retries on the interval
        # rather than giving up: the failed write's deadline is re-armed.
        clock.advance(31.0)
        coord.mark_dirty()
        store.wait_for_attempt(min_count=2)
        assert store.attempts == 2
    finally:
        coord.shutdown(timeout=_WAIT)


# --- a forced checkpoint waits for the write ------------------------------


def test_checkpoint_now_forces_a_write_and_waits_for_it(tmp_path: Path) -> None:
    clock = _Clock(0.0)
    store = _RecordingStore(tmp_path / "snap")
    coord = CheckpointCoordinator(store, snapshot_source=_snap, interval=10_000.0, monotonic=clock)
    coord.start()
    try:
        coord.mark_dirty()
        coord.checkpoint_now(timeout=_WAIT)  # the interval is huge; only a force reaches it
        assert store.count == 1
    finally:
        coord.shutdown(timeout=_WAIT)


# --- a blocked writer does not block Command handling ---------------------


def test_a_blocked_writer_does_not_block_command_handling(tmp_path: Path) -> None:
    # The whole point of the coordinator's threading. The worker takes its
    # snapshot copy under the daemon's request lock and then writes with that
    # lock released, so a save whose I/O stalls holds a worker thread, not the
    # request path. A second request lands while the first save is still blocked.
    daemon = transport.build_daemon(telemetry_path=tmp_path / "telemetry.jsonl")
    blocked = _BlockingStore(tmp_path / "snap")
    coord = CheckpointCoordinator(blocked, snapshot_source=daemon.checkpoint_snapshot, interval=0.0)
    daemon.attach_checkpoint(coord)
    coord.start()
    try:
        observe(daemon, "r1")  # a mutating report marks the Campaign dirty; deadline is now
        blocked.wait_for_save_started()  # the worker is blocked inside the save

        started = time.monotonic()
        observe(daemon, "r2")  # a second request, while the save is still blocked
        elapsed = time.monotonic() - started
        # Served in well under the request-lock wait bound (250 ms): the worker
        # released the daemon lock before its I/O, so this request was not held.
        assert elapsed < 0.2, f"second request took {elapsed:.3f}s behind a blocked writer"

        blocked.release.set()
    finally:
        coord.shutdown(timeout=_WAIT)


# --- telemetry records the outcome without the snapshot's contents --------


def test_telemetry_records_the_outcome_without_logging_contents(tmp_path: Path) -> None:
    clock = _Clock(0.0)
    log = tmp_path / "telemetry.jsonl"
    telemetry = Telemetry(log)
    store = SnapshotStore(tmp_path / "snap")
    coord = CheckpointCoordinator(
        store,
        snapshot_source=_snap_with_a_loadout,
        interval=10_000.0,
        monotonic=clock,
        telemetry=telemetry,
    )
    coord.start()
    try:
        coord.mark_dirty()
        coord.checkpoint_now(timeout=_WAIT)
    finally:
        coord.shutdown(timeout=_WAIT)

    saved = [row for row in all_rows(log) if row["event"] == "snapshot_saved"]
    assert saved, "a checkpoint recorded a snapshot_saved row"
    keys = set(saved[0])
    assert {"duration_us", "bytes", "checksum", "version"} <= keys
    # No snapshot field and no player UID: the contents stay in the file.
    assert not (keys & {"clock", "owners", "hq", "funds", "squads", "loadouts"})
    body = str(saved[0])
    assert "rifleman" not in body
    assert "uid-1" not in body


def _snap_with_a_loadout() -> Snapshot:
    return Snapshot(
        clock=120.0,
        owners={"agia_marina": "WEST"},
        hq={"base_west": INTACT},
        funds=dict.fromkeys(SIDES, 200),
        squads=(),
        loadouts={"uid-1": "rifleman"},
    )
