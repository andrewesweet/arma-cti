#### Fixed

- A dispatch always identifies `~/.arma-cti/gate-clock` as canonical, independent
  of `CTI_GATE_CLOCK_DIR`. Its recorder fsyncs the row to the dispatch outbox
  before attempting the selected directory, then fsyncs each containing directory
  entry; dispatch setup also fsyncs the stable root after creating an outbox. A
  crash between the outbox and selected writes can omit the selected copy, but
  leaves the row recoverable for canonical collection. A failed enqueue skips the
  selected write. A read-only canonical path uses that same outbox.

- Every new row has a delivery id. Canonical collection holds a file lock, flushes
  each new id before deleting its outbox, and skips an id already present, so retry
  cannot duplicate a sample. Active dispatches hold an outbox lock; the next
  dispatch retries every unlocked orphan remaining in the stable per-history temp
  root. An ordinary exception while reading or appending canonical history is
  reported against that history and leaves the already-readable outbox unmarked.
  The collector does not repair or quarantine poisoned canonical history: eligible
  recovery attempts keep reporting it and pending outboxes can accumulate until the
  history is repaired. A retry deduplicates any row whose append reached canonical
  history before the failure was raised.

- Gate-clock setup, orphan recovery, post-child collection and lock cleanup now
  sit behind an instrumentation boundary. Any `Exception` raised inside those
  steps is reported in one line while child launch and `result.json` continue.
  Malformed outboxes and failures opening or acquiring their active locks enter the
  same quarantine path, choosing recorded-and-skipped over parsing-shape enumeration.
  The marker is written and fsynced under a temporary name before atomic publication;
  only a regular file with the complete marker body counts, so a failed
  pre-publication write or sync leaves the outbox eligible and a dangling symlink is
  replaced. Readable rows in a marked outbox are not subsequently recovered, so any
  not already canonical are lost with the malformed one. An outbox whose marker path
  cannot be replaced remains eligible and can be retried and reported again. A
  directory sync failure after atomic publication reports `quarantine=failed`, but the
  complete visible marker still suppresses later recovery; only a completed directory
  sync makes that entry durable across power loss.

- `just gate-clock-history` now states that coverage is unknowable because failed
  recording attempts are not durably counted. A successfully queued dispatch row
  remains recoverable while host temp storage survives; this does not reconstruct
  rows already lost or claim a denominator the instrument never recorded. A death
  before or during the initial outbox append can still lose the row without a
  failure line; no durable copy yet exists from which the harness could recover it.
  Process termination, power loss outside the filesystem's completed `fsync`
  guarantees, and `BaseException` subclasses remain outside the boundary.
