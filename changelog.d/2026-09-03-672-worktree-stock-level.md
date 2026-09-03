# Changed

- `just loop-metrics` now derives `stock worktrees_owing_done` locally instead
  of reporting it permanently `unrecorded`: every non-main registration in
  `git worktree list` whose name carries an issue number (`issue-N`,
  `review-N…`) counts when a ledger row attests `gate=landed` for that issue
  at or before the window's end. The level under-counts the tracker's answer —
  a landing whose ledger row was never materialised is invisible to it — and
  the report line carries `bias=under_counts`, the swept registration total,
  the count excluded for carrying no issue name, and
  `registration_basis=current_snapshot`. A registration sweep that cannot
  answer leaves the level `unrecorded`, never zero.
