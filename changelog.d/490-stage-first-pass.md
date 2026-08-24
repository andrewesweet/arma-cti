## Added

- Each stage of the work-item pipeline — brief, implementation, own gate,
  exchange, review, land — now records its arrivals in a per-issue stage
  journal with a first-pass status of `first_time`, `after_rework` or
  `undetermined`; an undeterminable status is recorded as `undetermined` and
  never defaulted to true (#490).
- The observatory store gains a `stage_first_pass` view — one row per stage
  with arrival counts by status and the first-pass yield derived from the
  arrivals' own statuses — so rolled throughput yield is a grouping over the
  record, never a correlation of timestamps and rounds.
