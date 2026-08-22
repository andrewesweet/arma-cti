### Added

- New dispatches record a `guidance_manifest` at the dispatch boundary. Codex manifests are
  derived from the existing #502 delivery proof and retain its ordered expected sources,
  hashes, byte counts, loader outcome and launch context without storing instruction bodies.
- Claude Code dispatches record `unattributable` guidance because no bounded non-interactive
  loader surface establishes its active source chain. This is a current harness boundary,
  not a permanent limitation: bounded loader or source evidence can make Claude attributable
  later. Records with neither manifest nor legacy proof are `unknown`; valid pre-#503
  `instruction_delivery` proofs derive `verified`. Explicit missing and empty states remain
  typed, while malformed or contradictory records are `unclassified`.
- `just ledger-sync` exposes the manifest as a materialized view, deriving the verified form
  from pre-#503 `instruction_delivery` proofs and never writing dispatch evidence or copying
  invalid or arbitrary record fields.
