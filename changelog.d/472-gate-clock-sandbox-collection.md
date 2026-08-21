#### Fixed

- A dispatched gate run whose canonical gate-clock path is read-only now writes
  its row to a per-dispatch temporary outbox, and the unsandboxed dispatcher
  attempts to append that row to the canonical history after the session exits.
  A failed host append is reported and leaves the outbox in place. A dispatched
  `CTI_GATE_CLOCK_DIR` override keeps its selected copy and queues the same row
  for canonical collection, so either the row reaches the shared history or the
  collection failure is visible. The recorder reports a failed primary write once
  in the run's own output, naming the recipe and operating-system error, while
  returning success so recording cannot fail the gate.

- `just gate-clock-history` now states that coverage is unknowable because failed
  recording attempts are not durably counted. The new dispatch collection prevents
  the known sandbox-selected misses; it does not reconstruct the rows already lost
  or claim a denominator the instrument never recorded.
