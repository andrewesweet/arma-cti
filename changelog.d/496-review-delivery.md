#### Fixed

- Dispatched reviews were intended to post their own findings: project permissions allowed
  `gh issue`, the review brief ordered `gh issue comment`, and the dispatcher did not strip
  GitHub credentials. Eleven completed reviews then failed to leave a comment through Claude
  plan-mode control flow, cancelled Codex connector calls, invalid sandbox-side `gh`
  authentication, and network failure. Those paths were delivery defects, not intended
  read-only containment.

- The review brief now requires the report, including a clean verdict, between two exact marker
  lines in final stdout. The unsandboxed dispatcher captures stdout through an anonymous
  temporary file it opened, so the child needs neither GitHub credentials nor a writable
  body-file path. It posts only the marked section, prefaced by a notice that output outside
  those markers or on another stream was not captured as the report. Missing, duplicated or
  reversed markers and an empty marked section cause a refusal without a post.

- After a zero child exit, delivery runs before outcome classification and breaker journaling,
  so failures in that bookkeeping cannot prevent the post attempt. #495's outer closeout also
  preserves the delivery verdict if later bookkeeping raises. Success records
  `review_delivery=posted`; an unavailable or timed-out `gh` and a non-zero `gh` exit record
  `review_delivery_failed` while preserving the child's return code.

- `dispatch-follow` reads that delivery verdict. A posted review remains a completion and names
  `review_delivery=posted`; an undelivered review prints `review_delivery_failed` as a refusal
  and exits non-zero instead of treating any `result.json` as success.

- There is no automatic retry, recovery scan, lock, quarantine or dedupe. Captured stdout is
  emitted to `dispatch.log` before posting. Host authentication and network failures remain
  undeliverable until deliberate manual relay; findings outside the marked stdout section or on
  another stream remain unidentified by the harness; abrupt dispatcher death can still lose a
  report without a delivery refusal; and a timed-out call may already have posted.
