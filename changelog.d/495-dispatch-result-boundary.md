#### Fixed

- `run_dispatch` now reaches one `result.json` write attempt after every body return or
  raised `BaseException`. When the closeout document can be constructed and written, its
  `status` distinguishes a returned child
  (`child_finished`), a refusal or failure before a child result
  (`child_not_launched`), and a harness failure after the child returned
  (`harness_failed_after_child`). Raised failures also record their phase, exception
  type, and message. A child return is marked before gate-clock collection, so a
  `BaseException` during collection is recorded as post-child rather than as a launch
  failure.

- A result-write failure is reported once on stderr. It is not retried and no recovery,
  lock, quarantine, dedupe, or temporary-file protocol is added. Consequently
  `result.json` can still be absent when its own write fails, when the record directory
  does not exist, when resource exhaustion prevents closeout construction, or when
  process, interpreter, kernel, or host termination prevents the Python `finally`
  boundary from running.

- Tests inject `subprocess.run`, child-launch, and breaker-journal failures, including
  `KeyboardInterrupt` and `MemoryError`. Each checks the recorded status and checks the
  resulting file against `queue_policy.derive_in_flight`, proving that these completed
  failure paths no longer occupy dispatch-only WIP forever.
