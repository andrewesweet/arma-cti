"""The checkpoint coordinator: dirty tracking, the 30-second bound, off-lock I/O (#290).

`cti_daemon.store` makes one snapshot durable; this module decides *when*. A
persistent strategic change marks the Campaign dirty, and a checkpoint becomes
durable within 30 seconds of the **first** unsaved change — measured from the
first, not the last, so a burst that runs longer than the interval still
checkpoints on time rather than pushing the deadline out one change at a time
(#288). Clean teardown forces a final checkpoint, so a session that ends
gracefully leaves nothing unsaved.

The whole point of the coordinator's threading is one rule the criteria name
flatly: a blocked writer does not block Command handling for its I/O duration.
So the snapshot copy is taken under the daemon's narrow request lock — the same
lock every `handle_line` mutation is serialised under — and then encoding,
validation and every byte of disk I/O happen on a background thread with that
lock released. A save whose `fsync` stalls holds a worker thread, not the
request path; `handle_line` acquires the lock the worker released and answers.

Coalescing is a generation counter rather than a queue. Every mutation advances
one monotonic generation; the worker captures the generation when it begins a
write and marks the Campaign clean only if no mutation arrived while the bytes
were on their way to disk. A mutation that arrives mid-write advances the
generation, leaves the Campaign dirty, and the worker writes again — so a burst
of changes is one write of the latest state, never a parallel write per change,
and a write that is interrupted (the store raises) is never reported as success.

The Campaign-to-snapshot projection lives in `campaign.to_snapshot` (#291) and
reaches the coordinator through the daemon: `snapshot_source` is
`Daemon.checkpoint_snapshot`, which takes the copy under the request lock via the
report cycle. The coordinator never reads the aggregate itself, so it owns *when*
to persist and not *what* a snapshot is — and there is one projection rather than
the two a per-coordinator copy would make.
"""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Callable

    from cti_daemon.snapshot import Snapshot
    from cti_daemon.store import SaveOutcome, SnapshotStore
    from cti_daemon.telemetry import Telemetry

# A checkpoint becomes durable within this many seconds of the first unsaved
# persistent change (#288). Not the last change: a burst longer than the interval
# still checkpoints on time, because the deadline is fixed when the Campaign first
# goes dirty and a later change does not move it.
CHECKPOINT_INTERVAL_SECONDS: Final = 30.0


class CoordinatorStoppedError(Exception):
    """An operation was requested after the coordinator's worker had stopped.

    A stopped coordinator has run its final checkpoint and will not run another,
    so a `checkpoint_now` against one is a caller's mistake rather than a wait.
    """

    def __init__(self) -> None:
        """Carry the one fixed message a stopped-coordinator refusal always has."""
        super().__init__("the checkpoint coordinator has stopped")


class CheckpointCoordinator:
    """Marks the Campaign dirty and durably checkpoints it on a background thread."""

    def __init__(
        self,
        store: SnapshotStore,
        *,
        snapshot_source: Callable[[], Snapshot],
        interval: float = CHECKPOINT_INTERVAL_SECONDS,
        monotonic: Callable[[], float] = time.monotonic,
        telemetry: Telemetry | None = None,
    ) -> None:
        """Wire the coordinator to its store, its snapshot source and its clock.

        ``snapshot_source`` acquires the daemon's request lock and returns a
        consistent `Snapshot` — the narrow lock the criteria name, held only for
        the in-memory copy. ``monotonic`` is injected so a test fixes the deadline
        without waiting thirty seconds. ``telemetry``, when given, records
        checkpoint outcomes without ever the snapshot's contents.
        """
        self._store = store
        self._snapshot_source = snapshot_source
        self._interval = interval
        self._monotonic = monotonic
        self._telemetry = telemetry

        self._cond = threading.Condition()
        # Whether a persistent change is unsaved, and the deadline it must be
        # saved by. The deadline is fixed when the Campaign first goes dirty and
        # is not pushed by later changes (#288).
        self._dirty = False
        self._deadline: float | None = None
        # A monotonic generation advanced by every mutation. The worker captures
        # it per write and marks clean only if it is unchanged afterwards, which
        # is how a mid-write mutation is neither lost nor written twice.
        self._generation = 0
        self._completed = 0
        # A checkpoint forced through `checkpoint_now`, satisfied by the next
        # write whatever the deadline. Coalesces: one write clears every force.
        self._force = False
        self._stopped = False
        self._started = False
        self._last_outcome: SaveOutcome | Exception | None = None

        self._thread = threading.Thread(target=self._run, daemon=True, name="cti-checkpoint")

    def start(self) -> None:
        """Start the background worker. Idempotent."""
        with self._cond:
            if self._started:
                return
            self._started = True
        self._thread.start()

    def mark_dirty(self) -> None:
        """Record a persistent change: the Campaign has unsaved state.

        The deadline is set when the Campaign first goes dirty and left alone by
        every later change, so a burst checkpoints within one interval of its
        first change rather than its last. Cheap and non-blocking: a mutation
        path holds the daemon lock, not this condition, for long.
        """
        with self._cond:
            self._generation += 1
            if not self._dirty:
                self._deadline = self._monotonic() + self._interval
                self._dirty = True
            self._cond.notify_all()

    def checkpoint_now(self, timeout: float | None = None) -> None:
        """Force a checkpoint of the current state and wait for it to be durable.

        Satisfied by the worker's next write, whatever the deadline. Must not be
        called from a thread holding the daemon's request lock: the worker needs
        that lock to take its consistent copy, and holding it here would deadlock
        the final write. Raises `CoordinatorStoppedError` if the worker has already
        shut down, and `TimeoutError` if the write does not complete in time.
        """
        with self._cond:
            if self._stopped:
                raise CoordinatorStoppedError
            target = self._generation
            self._force = True
            self._cond.notify_all()
            wait_deadline = None if timeout is None else self._monotonic() + timeout
        with self._cond:
            while self._completed < target and not self._stopped:
                if wait_deadline is None:
                    self._cond.wait()
                    continue
                remaining = wait_deadline - self._monotonic()
                if remaining <= 0:
                    message = "a forced checkpoint did not complete within the timeout"
                    raise TimeoutError(message)
                self._cond.wait(timeout=remaining)
            if self._completed < target:
                message = "the coordinator stopped before the forced checkpoint completed"
                raise TimeoutError(message)

    def shutdown(self, timeout: float | None = None) -> None:
        """Stop the worker after one final checkpoint, if anything is unsaved.

        The clean-teardown path (#288): a session that ends gracefully leaves
        nothing unsaved. The worker finishes any write in flight, then writes once
        more for state that changed during it, then exits. Blocks until the worker
        has joined (or the timeout), so a caller knows the final checkpoint is
        durable when this returns. Must not be called under the daemon lock.
        """
        with self._cond:
            if not self._started or self._stopped:
                self._stopped = True
                return
            self._stopped = True
            self._cond.notify_all()
        self._thread.join(timeout)

    @property
    def last_outcome(self) -> SaveOutcome | Exception | None:
        """The most recent save's outcome, or the exception that ended it.

        Observability without contents: a `SaveOutcome` carries the checksum,
        version and byte count of what landed, never the snapshot itself.
        """
        return self._last_outcome

    def _run(self) -> None:
        """Wait for a due deadline or a force, then write, until stopped."""
        while True:
            gen = self._await_write_or_stop()
            if gen is None:
                break
            self._write(gen)
        # Clean teardown: one final checkpoint if anything remains unsaved.
        with self._cond:
            final = self._generation if self._dirty or self._generation > self._completed else None
        if final is not None:
            self._write(final)

    def _await_write_or_stop(self) -> int | None:
        """Block until a write is due or forced, or return None when stopped.

        Returns the generation to write at, capturing it under the condition so
        the clean/clean race is decided against the same counter the writer uses.
        """
        with self._cond:
            while True:
                if self._stopped:
                    return None
                now = self._monotonic()
                due = self._dirty and self._deadline is not None and now >= self._deadline
                if self._force or due:
                    self._force = False
                    return self._generation
                if self._dirty and self._deadline is not None:
                    self._cond.wait(timeout=max(0.0, self._deadline - now))
                else:
                    self._cond.wait()

    def _write(self, gen: int) -> None:
        """Take one consistent copy and make it durable, marking clean if unraced.

        The snapshot copy and the disk write both happen off the coordinator's
        condition: the worker holds neither while the bytes cross the disk, which
        is what keeps `mark_dirty` and `handle_line` responsive to a stalled
        `fsync`. Clean is marked only when no mutation advanced the generation
        during the write — otherwise the Campaign stays dirty and the worker
        writes again, so a mid-write change is lost to neither the timing nor a
        second writer.
        """
        try:
            snapshot = self._snapshot_source()
            outcome = self._store.save(snapshot)
        except Exception as exc:  # noqa: BLE001 — a save failure is recorded, not
            # raised past the worker: the coordinator keeps the Campaign dirty and
            # retries on the interval, so a transient disk fault does not kill
            # checkpointing and a persistent one is observable on the outcome.
            with self._cond:
                self._last_outcome = exc
                if self._telemetry is not None:
                    self._telemetry.record(
                        "snapshot_save_failed", error=f"{type(exc).__name__}: {exc}"
                    )
                if self._deadline is not None:
                    self._deadline = self._monotonic() + self._interval
                self._cond.notify_all()
            return
        with self._cond:
            self._last_outcome = outcome
            if self._telemetry is not None:
                self._telemetry.record(
                    "snapshot_saved",
                    duration_us=outcome.duration_us,
                    bytes=outcome.bytes_written,
                    checksum=outcome.checksum,
                    version=outcome.version,
                )
            if self._generation == gen:
                self._dirty = False
                self._deadline = None
            self._completed = max(self._completed, gen)
            self._cond.notify_all()
