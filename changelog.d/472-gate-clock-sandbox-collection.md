#### Fixed

- A dispatched gate run now writes its gate-clock rows to a writable,
  session-local temporary file. Immediately after the child exits, the
  unsandboxed dispatcher appends that file once to the canonical
  `~/.arma-cti/gate-clock/records.jsonl`. An unterminated canonical tail is
  separated before the new rows so `load_records` cannot merge and skip them.
  A prior valid row survives; a prior malformed row is dropped when the
  collected row is rescued. If that append fails, the dispatcher reports one
  `gate_clock_collection=failed` line, preserves the child's exit result, and
  still writes `result.json`. Canonical collection runs only after child exit,
  takes no lock, and no later dispatch scans its file, so it cannot block child
  launch or another dispatch.

- Collection is deliberately lossy. If the dispatcher dies after the child
  exits but before the append completes, that row can be lost without a
  failure line because no dispatcher remains to report it. There is no
  recovery, retry, delivery-id dedupe, orphan scan, or quarantine. While the
  dispatcher remains alive, a failed append is reported once and the dispatch
  carries on. `load_records` decodes each row strictly and silently drops a
  whole row containing undecodable UTF-8; valid rows before and after it remain
  readable. Thus an undecodable prior tail is lost when a collected row is
  rescued. The reduced path performs no file or directory `fsync`.

- Historical coverage remains unknowable because failed recording attempts and
  the accepted dispatcher-death window are not durably counted. This change
  does not reconstruct rows already lost, including #455's missing 74.22 s to
  27.22 s improvement.
