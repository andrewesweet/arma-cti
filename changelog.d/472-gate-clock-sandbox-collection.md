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
  root. The collector does not repair or quarantine poisoned canonical history;
  repairing that history remains an operator action. If a canonical append succeeds
  but removing `records.jsonl`, `.active.lock`, or the outbox directory fails, the row
  is canonical and the outbox remains eligible. Recovery retries and reports cleanup;
  if the records remain, the delivery id makes their append a duplicate rather than a
  second sample.

- Gate-clock collection is best-effort instrumentation. Within its `Exception`
  boundary, failures are reported and never block a dispatch: child launch and
  `result.json` continue. Collection has no retention bound; while a fault persists,
  outboxes and repeated failure reports accumulate without bound until it is repaired.
  Malformed outboxes use a quarantine marker, choosing recorded-and-skipped over
  parsing-shape enumeration. Failures opening or acquiring an active lock use the
  same path.
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
