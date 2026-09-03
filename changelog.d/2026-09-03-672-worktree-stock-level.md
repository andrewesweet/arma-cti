# Changed

- `just loop-metrics` now derives `stock worktrees_owing_done` locally instead
  of reporting it permanently `unrecorded`: every non-main registration in
  `git worktree list` whose name carries an issue number (`issue-N`,
  `review-N`, and its `-r2`, bare-letter `review-Nb` and word-suffix
  `review-N-note` variants, and `audit-N`) counts when **any** ledger row
  attests `gate=landed` for that issue at or before the window's end, so an
  issue that landed twice straddling a window still counts.  The line names
  the basis every level's landing timestamps were read on, distinguishing a
  ledger-recorded landing time from a commit-timestamp stand-in, a mix of
  the two, and a level no landing participated in, and names the stand-in's
  own early-read bias wherever it is in play.  The level's error direction is
  not a single direction: the report states a mixed direction, claims no net
  direction, and names every path and the way it pushes — landings invisible
  for want of a materialised ledger row, issues closed without a landing,
  issues landed but not yet closed (including before `just land`'s own close
  step), issues reopened after landing, and, for a window whose end lies in
  the past, registrations removed and added since that boundary.  That past
  boundary also makes the registration half a live sweep the landing half
  does not share, and the report emits that split as its own parseable field
  rather than folding it into the preceding value.  The line also carries the
  swept registration total, the count excluded for carrying no issue name,
  and a current-snapshot registration basis.  A registration sweep that
  cannot answer leaves the level `unrecorded`, never zero.
