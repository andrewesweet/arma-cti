#### Fixed

- `run_dispatch` now makes one best-effort `result.json` closeout attempt whenever control
  reaches its outer Python boundary. A successfully written closeout releases dispatch-only
  WIP even when the harness raised a `BaseException`.

- Lifecycle status is reliable after child completion is marked. A failure after
  `subprocess.run` is invoked but before that mark records `child_state_unknown`, because
  the child may have run before the harness lost track of it; it no longer asserts
  `child_not_launched` and invites a duplicate dispatch. Raised failures also record their
  phase, exception type, and message. An unknown-state result tells its reader to inspect
  the log, process, and worktree, reconcile any work, and re-dispatch only after verifying
  that another run cannot duplicate it.

- Closeout is staged beside `result.json`, flushed, and renamed onto it. On filesystems
  honouring atomic same-directory replacement, readers see a complete result or no result;
  a failed write or rename does not publish a partial result as dispatch completion. Result
  writes are not retried, and no recovery, lock, quarantine, or dedupe is added.

- Tests interrupt real `subprocess.run` communication after its child starts, exercise
  failures on both sides of the completion mark, and check successful closeouts against
  `queue_policy.derive_in_flight`.
