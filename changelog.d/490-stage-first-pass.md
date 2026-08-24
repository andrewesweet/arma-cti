## Added

- Each stage of the work-item pipeline — brief, implementation, own gate,
  exchange, review, land — now records its arrivals in a per-issue stage
  journal with a first-pass status of `first_time`, `after_rework` or
  `undetermined`; an undeterminable status is recorded as `undetermined` and
  never defaulted to true (#490). An issue with no journal yet records
  `first_time` only where its review directory and its pipeline dispatch
  records hold no prior act — an issue that predates the recorder records its
  first journalled arrival as `undetermined` rather than a clean past the
  absent journal never supported — and a `just fast` run or a landing from a
  dispatched seat the pipeline does not map (retro, recon, planner, fable,
  orchestrator) records no own-gate or land arrival, because the dispatcher
  exports the seat to every child and those seats' work is not a pass through
  the pipeline.
- The observatory store gains a `stage_first_pass` view — one row per stage
  with arrival counts by status and the first-pass yield derived from the
  arrivals' own statuses — so rolled throughput yield is a grouping over the
  record, never a correlation of timestamps and rounds.
