#### Fixed

- `run_dispatch` now makes one best-effort `result.json` closeout attempt whenever control
  reaches its outer Python boundary. A successfully written closeout releases dispatch-only
  WIP even when the harness raised a `BaseException`.

- Lifecycle status is reliable after child completion is marked. A failure after
  `subprocess.run` is invoked but before that mark records `child_state_unknown`, because
  the child may have run before the harness lost track of it; it no longer asserts
  `child_not_launched` and invites a duplicate dispatch. Raised failures also record their
  phase, exception type, and message.

- Closeout has no stronger durability guarantee: `result.json` exists only when control
  reaches the boundary and its single write succeeds. Result writes are not retried, and
  no recovery, lock, quarantine, dedupe, or temporary-file protocol is added.

- Tests interrupt real `subprocess.run` communication after its child starts, exercise
  failures on both sides of the completion mark, and check successful closeouts against
  `queue_policy.derive_in_flight`.
