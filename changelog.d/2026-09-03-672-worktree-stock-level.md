# Changed

- `just loop-metrics` now derives `stock worktrees_owing_done` locally instead
  of reporting it permanently `unrecorded`: every registration whose name
  carries an issue number (`issue-N`, `review-N`, and its `-r2`, bare-letter
  `review-Nb` and word-suffix `review-N-note` variants, and `audit-N`) counts
  when **any** ledger row attests `gate=landed` for that issue at or before
  the window's end, so an issue that landed twice straddling a window still
  counts.  A window with no end sweeps the registration table live; a window
  with an end reconstructs the registration half as of the boundary from the
  dispatch records' `worktree` and `planned_at` fields, so both halves of a
  bounded read honour the boundary and a registration created after it no
  longer moves the level.  A landing whose time cannot be read is not an
  absent landing: where it is a registered issue's only candidate landing,
  the level is reported `unrecorded` rather than zero and each damaged
  record is diagnosed.  The line names the basis every level's landing
  timestamps were read on, distinguishing a ledger-recorded landing time from
  a commit-timestamp stand-in, a mix of the two, and a level no landing
  participated in, and names the stand-in's own early-read bias wherever it
  is in play.  The level's error direction is not a single direction: the
  report states a mixed direction, claims no net direction, and names every
  path and the way it pushes — landings invisible for want of a materialised
  ledger row, issues closed without a landing, issues landed but not yet
  closed (including before `just land`'s own close step), issues reopened
  after landing and, for a bounded window, hand-made trees with no dispatch
  behind them, trees created before their first dispatch (a record's
  `planned_at` bounds the tree's existence from below; it does not date its
  creation) and trees removed again before the boundary.  The bounded read's
  unrepaired approximations — trees the records cannot place at the boundary
  — are emitted as their own parseable field rather than folded into a
  preceding value.  The line also carries the reconstruction's or sweep's
  registration total and the count excluded for carrying no issue name.  A
  live sweep that cannot answer leaves the level `unrecorded`, never zero,
  and a dispatch record whose `worktree` field cannot be read is diagnosed
  and contributes no tree.
