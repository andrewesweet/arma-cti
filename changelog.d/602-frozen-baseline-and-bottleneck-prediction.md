### Added

- **A frozen pre-pipeline baseline for the self-review experiment (#588, #602).** The baseline
  records return rate, λ, the rework loop's geometric fit and its residual, cycle time and process
  cycle efficiency from dispatch records, and stock levels from dispatch, worktree and ledger
  state, all dated 2026-08-26. Recorded as an act with a timestamp rather than as figures in a
  spec, because the corpus moved from 691 dispatches to 938 and the return rate from 0.642 to
  0.572 while those figures were being quoted.
- **A falsifiable prediction about bottleneck migration.** Clearing the worktree stock frees WIP
  and the constraint moves; the prediction is lane capacity, then human attention, then gate
  wall-clock, recorded before the observation rather than after it.
