#### Fixed

- A dispatched gate run now writes its gate-clock rows to a writable,
  session-local temporary file. Immediately after the child exits, the
  unsandboxed dispatcher appends that file once to the canonical
  `~/.arma-cti/gate-clock/records.jsonl`. If that append fails, the dispatcher
  reports one `gate_clock_collection=failed` line, preserves the child's exit
  result, and still writes `result.json`. Canonical collection runs only after
  child exit, takes no lock, and no later dispatch scans its file, so it cannot
  block child launch or another dispatch.

- Collection is deliberately lossy. If the dispatcher dies after the child
  exits but before the append completes, that row can be lost without a
  failure line because no dispatcher remains to report it. There is no
  recovery, retry, delivery-id dedupe, orphan scan, or quarantine. While the
  dispatcher remains alive, a failed append is reported once and the dispatch
  carries on. The reduced path performs no file or directory `fsync`.

- Historical coverage remains unknowable because failed recording attempts and
  the accepted dispatcher-death window are not durably counted. This change
  does not reconstruct rows already lost, including #455's missing 74.22 s to
  27.22 s improvement.
