#### Fixed

- A dispatch always identifies `~/.arma-cti/gate-clock` as canonical, independent
  of `CTI_GATE_CLOCK_DIR`. Its recorder fsyncs the row to the dispatch outbox
  before attempting the selected directory. A crash between those writes can omit
  the selected copy, but leaves the row recoverable for canonical collection; a
  failed enqueue skips the selected write. A read-only canonical path uses that
  same outbox. Caught write failures are reported while returning success, so
  recording cannot fail the gate.

- Every new row has a delivery id. Canonical collection holds a file lock, flushes
  each new id before deleting its outbox, and skips an id already present, so retry
  cannot duplicate a sample. Active dispatches hold an outbox lock; the next
  dispatch retries every unlocked orphan remaining in the stable per-history temp
  root. An unreadable outbox or failed host append remains there and is reported.
  Host temp cleanup is outside that recovery guarantee.

- `just gate-clock-history` now states that coverage is unknowable because failed
  recording attempts are not durably counted. A successfully queued dispatch row
  remains recoverable while host temp storage survives; this does not reconstruct
  rows already lost or claim a denominator the instrument never recorded. A death
  before or during the initial outbox append can still lose the row without a
  failure line; no durable copy yet exists from which the harness could recover it.
