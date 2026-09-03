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
  record one it reads `landing_basis=ledger_landed_at`.  The level's error
  direction is not a single direction, and the report states that rather than
  picking one: it carries `bias=mixed net_direction=undetermined` and names
  each path with the way it pushes — `unmaterialised_ledger_landings:
  under_counts` (a landing whose ledger row was never materialised is
  invisible to the level) and `issue_reopened_after_landing:over_counts`
  always, joined for a window whose end lies in the past by
  `registrations_removed_since_boundary:under_counts` and
  `registrations_added_since_boundary:over_counts`, because the registration
  half is a live sweep.  The landing half alone honours the boundary; the
  registration half cannot, since no durable record replays the registration
  table, so a level for a past window names
  `live_registration_sweep_not_as_of_window_end` in its reason and is not an
  as-of answer.  The line also carries the swept registration total, the
  count excluded for carrying no issue name, and
  `registration_basis=current_snapshot`.  A registration sweep that cannot
  answer leaves the level `unrecorded`, never zero.
