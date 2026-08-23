## Added

- **The observatory's occupancy view: capacity, used, lost, mean concurrency, the
  concurrency distribution and the idle gaps, over any window the reader names
  (#485).** Occupied time is the count of live dispatches at each whole minute of the
  window, summed — the method `tools/occupancy.py` published (#295), restated as
  three cookbook queries whose window literals the reader replaces; the bounds are
  columns of the output, so no figure is quotable without its denominator. A span
  needs both its bounds: the dispatches table gains `ended_at` and `terminal_state`
  (each null with its reason, the terminal state read from #489's block on the
  materialised row and never re-derived from timestamps or an absence of landing),
  a dispatch that started and did not complete is named by that block, and a
  dispatch with no recorded end contributes no occupied time — counted instead in
  the coverage block's `dispatches_unbounded`, the rebuild line's `unbounded=` and
  the headline query's `unbounded_dispatches`, because counting it to the window's
  end is the inflation the issue forbids. The gaps partition the histogram's
  level-0 row, each listed with start, end and duration; minute boundaries are
  sampled rather than rounded, pinned by a test on a dispatch whose forty seconds
  cross no minute boundary; `used` counts live dispatches at their own level, so a
  window that overran the ruled limit can show `lost` below zero — the overrun made
  visible. The store's schema is now `cti.observatory/5`. The research document's
  §1 figures are a dated observation, not a baseline: its used figure counted
  unbounded dispatches to the window's end and its two idle figures disagree with
  each other, so a live comparison is expected to name both — the hazards entry
  records which side is wrong where.
