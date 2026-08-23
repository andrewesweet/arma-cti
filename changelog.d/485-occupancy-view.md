## Added

- **The observatory's occupancy view: capacity, used, lost, mean concurrency, the
  concurrency distribution and the idle gaps, over any window the reader names
  (#485).** Occupied time is the count of live dispatches at each whole minute of the
  window, summed — the method `tools/occupancy.py` published (#295), restated as
  three cookbook queries whose window literals the reader replaces; the bounds are
  columns of the output, so no figure is quotable without its denominator. A span is
  attested only by the run's own records: the dispatches table gains `ended_at` and
  `terminal_state` (each null with its reason, the terminal state read from #489's
  block on the materialised row and never re-derived from timestamps or an absence
  of landing), a dispatch that started and did not complete is named by that block,
  and a closeout the stop sweep wrote (`stopped_by`) or a result that recorded no
  start of its own attests no span — both render `ended_at` null with their reason
  and contribute no occupied time, counted instead in the coverage block's
  `dispatches_unbounded`, the rebuild line's `unbounded=` and the headline query's
  `unbounded_dispatches`. Round 1 took the sweep's clock as a genuine end and so
  inflated the live store's `used` by 58% over the research document's window;
  the research document's §1 figures stood up, and its one internal disagreement —
  two idle figures, 247.5 hours by awake-minus-total against 251.8 by its own gap
  list — is resolved in the gap list's favour by the corrected store. The gaps
  partition the histogram's level-0 row, each listed with start, end and duration;
  minute boundaries are sampled rather than rounded, pinned by a test on a dispatch
  whose forty seconds cross no minute boundary; `used` counts live dispatches at
  their own level, so a window that overran the ruled limit can show `lost` below
  zero — the overrun made visible. The store's schema is now `cti.observatory/5`.
