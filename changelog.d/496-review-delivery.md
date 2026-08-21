#### Fixed

- Dispatched reviews were intended to post their own findings: project permissions allowed
  `gh issue`, the review brief ordered `gh issue comment`, and the dispatcher did not strip
  GitHub credentials. Eleven completed reviews then failed to leave a comment through Claude
  plan-mode control flow, cancelled Codex connector calls, invalid sandbox-side `gh`
  authentication, and network failure. Those paths were delivery defects, not intended
  read-only containment.

- The review brief now requires the complete report, including a clean verdict, in final
  stdout. The unsandboxed dispatcher captures that stdout through an anonymous temporary file
  it opened, so the child needs neither GitHub credentials nor a writable body-file path.
  After a zero child exit, the dispatcher makes one bounded
  `gh issue comment --body-file -` call with its parent environment. Success records
  `review_delivery=posted` in the run's output and `result.json`.

- Empty review output, an unavailable or timed-out `gh`, and a non-zero `gh` exit now end in
  the named refusal `review_delivery_failed`; the result preserves the child's return code and
  records `harness_failed_after_child`. The captured report is emitted to `dispatch.log` before
  posting. There is no automatic retry, recovery scan, lock, quarantine or dedupe. Abrupt
  dispatcher death can still lose a report without a refusal, a finding omitted from final
  stdout remains unavailable to the harness, a timed-out call may already have posted, and a
  host authentication or network failure still requires deliberate manual relay from the log.
