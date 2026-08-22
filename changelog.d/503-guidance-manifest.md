### Added

- New dispatches record a `guidance_manifest` at the dispatch boundary. Codex manifests are
  derived from the existing #502 delivery proof and retain its ordered expected sources,
  hashes, byte counts, loader outcome and launch context without storing instruction bodies.
- Claude Code dispatches record `unattributable` guidance because no bounded non-interactive
  loader surface establishes its active source chain. Historical records without a manifest
  are `unknown`; explicit missing and empty states remain typed, and malformed records are
  `unclassified` rather than becoming a successful empty manifest.
- `just ledger-sync` exposes the manifest as a materialized view, deriving the verified form
  from pre-#503 `instruction_delivery` proofs and never writing dispatch evidence or copying
  arbitrary record fields.
