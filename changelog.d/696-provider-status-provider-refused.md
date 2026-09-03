### Fixed

- A provider-side HTTP status that ends a dispatched child's run — Codex's
  `ERROR: unexpected status 404 Not Found` or Claude Code's `API Error: <code>`
  — is typed by what the status means instead of reading `unclassified`. The
  status is parsed once, from a provider shape anchored to the run's last
  non-empty line, and every status-based class is decided from that one parsed
  value: a `429` classifies `quota_exhausted`; a 401, 402, 403 or 408
  classifies `provider_error`, the availability family, so an expired OAuth
  token no longer counts against a profile's quality; every other 4xx
  classifies `provider_refused`, so the lane breaker counts it and three
  consecutive refusals trip the quality rule, hold the lane, and escalate; a
  5xx (500-599) classifies `provider_error`, a transient that must never count
  as a refusal. Because the parsed status is the one decision site, a
  status-like digit run inside a response id on the same line (`resp_a429b`)
  can no longer read as a `429`, and the run's terminal line is only read
  where a provider shape begins — so a provider-shaped string inside the
  child's own terminal failure output reads `unclassified`. Any other status —
  a 3xx redirect, a code outside those bands, or a longer digit run where a
  status would sit — still reads `unclassified` and moves no streak.
