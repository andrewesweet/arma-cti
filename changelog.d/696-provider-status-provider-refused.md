### Fixed

- A provider-side HTTP status that ends a dispatched child's run — Codex's
  `ERROR: unexpected status 404 Not Found` or Claude Code's `API Error: <code>`
  — is typed by what the status means instead of reading `unclassified`:
  a 4xx status other than 429 classifies as `provider_refused`, so the lane
  breaker counts it and three consecutive refusals trip the quality rule, hold
  the lane, and escalate; a 5xx (500-599) classifies as `provider_error`, a
  transient that must never count as a refusal; a `429` still classifies
  `quota_exhausted`. Classification reads only the run's last non-empty line,
  so a provider-shaped line the run survived — a retried warning, or a
  provider-shaped string inside the child's own failure output — never takes
  the child's failure over; and the numeric free-text markers match whole
  numbers only, so `API Error: 4290` and `API Error: 1500` do not read as
  `429` and `500`. Any other status — a 3xx redirect, a code outside those
  bands, or a longer digit run where a status would sit — and a child's own
  failure output still read `unclassified` and move no streak.
