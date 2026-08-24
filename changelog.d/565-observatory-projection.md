### Fixed

- `check-observatory` now reports a clean stale landed-issue projection without writing it into a feature branch. The orchestrator regenerates and commits the projection at landing, so parallel branches retain their substantive diff identity and can rebase without a generated-row re-review.
