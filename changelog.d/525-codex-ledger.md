### Fixed

- Correct Codex ledger totals when a monotonic token series declares DELTA, retain
  `codex-auto-review` spend, and record per-series and per-model token evidence. Existing
  materialized rows remain on schema 4 until they are explicitly re-synced while their
  durable exports remain; sync preserves rows after those exports age out.
