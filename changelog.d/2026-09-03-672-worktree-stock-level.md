# Changed

- `just loop-metrics` now derives `stock worktrees_owing_done` locally instead
  of reporting it permanently `unrecorded`: every non-main registration in
  `git worktree list` whose name carries an issue number (`issue-N`,
  `review-N`, and its `-r2`, bare-letter `review-Nb` and word-suffix
  `review-N-note` variants, and `audit-N`) counts when **any** ledger row
  attests `gate=landed` for that issue at or before the window's end, so an
  issue that landed twice straddling a window still counts.  Where no ledger
  row recorded a landing time — the canonical schema has none — the commit
  timestamp stands in and the report line names that basis and its error
  direction (`landing_basis=commit_timestamp
  proxy_bias=reads_early_over_counts_near_boundary`); where the ledger row did
  record one it reads `landing_basis=ledger_landed_at`.  The level
  under-counts the tracker's answer — a landing whose ledger row was never
  materialised is invisible to it — and the report line carries
  `bias=under_counts`, the swept registration total, the count excluded for
  carrying no issue name, and `registration_basis=current_snapshot`.  A
  registration sweep that cannot answer leaves the level `unrecorded`, never
  zero.
