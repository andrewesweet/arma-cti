### Fixed

- A provider-side HTTP status from a dispatched child — Codex's
  `ERROR: unexpected status 404 Not Found` or Claude Code's `API Error: <code>`
  with a 4xx status other than 429 — now classifies as `provider_refused`
  instead of `unclassified`, so the lane breaker counts it: three consecutive
  refusals trip the quality rule, hold the lane, and escalate. A `429` still
  classifies `quota_exhausted` and a `5xx` still classifies `provider_error`;
  a child's own failure output still reads `unclassified` and moves no streak.
