# Changed

- `just loop-metrics` now derives `stock worktrees_owing_done` locally instead
  of reporting it permanently `unrecorded`.  Every registration whose name
  carries an issue number counts when any ledger row attests `gate=landed`
  for that issue at or before the window's end, so an issue that landed twice
  straddling a window still counts.  A window with no end sweeps the
  registration table live; a window with an end reconstructs the registration
  half as of the boundary from the dispatch records, so both halves honour
  the boundary.  A landing whose time or SHA cannot be read, and a bounded
  record that cannot place a tree, are excluded from the level and counted
  beside it: the level stays the known lower bound, and `at_setpoint` is
  derived from those exclusions rather than claimed off them.  The line names
  its landing-time basis, its registration basis, and every error path with
  the direction it pushes, claiming no net direction; a sweep that cannot
  answer leaves the level `unrecorded`, never zero.  The behaviour catalogue
  has one home — `_worktree_stock`'s docstring in `tools/loop_metrics.py`,
  beside the report's own fields — and this fragment does not restate it.
