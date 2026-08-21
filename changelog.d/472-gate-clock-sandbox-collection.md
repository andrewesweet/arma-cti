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
  root. Failed canonical appends remain eligible for recovery.

- Gate-clock setup, orphan recovery, post-child collection and lock cleanup now
  sit behind an instrumentation boundary. Any `Exception` raised inside those
  steps is reported in one line while child launch and `result.json` continue.
  Malformed outboxes are retained with a fsynced `.quarantined` marker and skipped
  on later recovery, choosing recorded-and-skipped over parsing-shape enumeration.
  Readable rows in a marked outbox are not subsequently recovered, so any not
  already canonical are lost with the malformed one. If the marker itself cannot
  be written, the outbox can be retried and reported again; the boundary still
  contains that failure.

- `just gate-clock-history` now states that coverage is unknowable because failed
  recording attempts are not durably counted. A successfully queued dispatch row
  remains recoverable while host temp storage survives; this does not reconstruct
  rows already lost or claim a denominator the instrument never recorded. A death
  before or during the initial outbox append can still lose the row without a
  failure line; no durable copy yet exists from which the harness could recover it.
  Process termination, power loss outside the filesystem's completed `fsync`
  guarantees, and `BaseException` subclasses remain outside the boundary.
