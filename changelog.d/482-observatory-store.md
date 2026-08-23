## Added

- **`just observatory` rebuilds the observatory store and answers what a landed issue
  cost, per lane, in that lane's own meter (#482).** The store is a cache and never a
  source of truth: every run rebuilds `~/.arma-cti/observatory/store.json` in full from
  the per-dispatch OTel export, the dispatch records and git, deterministically — two
  runs over the same inputs produce identical bytes. It reads both spend encodings,
  Claude's per-request token counts on log records and Codex's histogram metric with a
  `token_type` attribute, and names in each row which one it read, because a reader
  that models only one books an entire lane at zero while looking correct. The raw
  export is pruned after thirty days once a ledger row exists, so where the file is
  gone the store reads the dispatch's materialised ledger row instead — visibly, in
  `telemetry_source` and the coverage line — and where even the row cannot answer (a
  log-record-only dispatch, or a row that reads zero) the spend is absent with a
  reason rather than zero: a rebuild after a prune never looks like a rebuild before
  one. Spend is reported per lane and never summed; the Claude lane's cost is
  five-hour-window points via the ledger's measured calibration, and every other lane
  reports its provider's own counters marked `uncalibrated` — absent, uncalibrated
  and zero are three different facts, and the summary line renders each differently.
  Every nullable column carries a reason sibling for its null, a truncated export
  line is counted and named while the rebuild completes, a dispatch with no telemetry
  at all is a row with a reason rather than a dropped row, and a source directory the
  process cannot read is a named refusal rather than a partial rebuild. The store is
  queryable with SQL through the standard library (`just observatory query "<SQL>"`),
  and the analyst's contract — schema reference, cookbook and hazards list, seeded
  with the three known traps — ships in `docs/observatory/` with its first query
  proven against the shipped store in a test.
