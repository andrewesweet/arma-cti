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
  that tree is excluded from the level and counted beside it, so the level
  that remains is the known lower bound and no `at_setpoint` is claimed while
  the exclusions could still move it across the setpoint, and each damaged
  record is diagnosed.  The line names the basis every level's landing
  timestamps were read on, distinguishing a ledger-recorded landing time from
  a commit-timestamp stand-in, a mix of the two, and a level no landing
  participated in, and names the stand-in's own early-read bias wherever it
  is in play.  The level's error direction is not a single direction: the
  report states a mixed direction, claims no net direction, and names every
  path and the way it pushes — landings invisible for want of a materialised
  ledger row, issues closed without a landing, issues landed but not yet
  closed (including before `just land`'s own close step), issues reopened
  after landing, landings whose time cannot be read and, for a bounded
  window, hand-made trees with no dispatch behind them, trees created before
  their first dispatch (a record's `planned_at` bounds the tree's existence
  from below; it does not date its creation), trees removed again before the
  boundary and dispatch records whose `worktree` field cannot be read, which
  are diagnosed at read and contribute no tree.  The bounded read's unrepaired approximations — trees
  the records cannot place at the boundary — are emitted as their own
  parseable field rather than folded into a preceding value.  The line also
  carries the reconstruction's or sweep's registration total, the count
  excluded for carrying no issue name and the count excluded because its only
  candidate landing has no readable time.  A live sweep that cannot answer
  leaves the level `unrecorded`, never zero.
