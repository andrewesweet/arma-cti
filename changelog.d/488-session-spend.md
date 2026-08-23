### Added

- **Non-dispatched session spend, reported per period and never per issue (#488).**
  The observatory store grows a session view over the status-line spool: one
  `session_period` row per (session, month) holding the period's consumption as
  deltas of the payload's session-lifetime running totals — cost, duration and the
  two line counters; the payload's token keys are context-window gauges rather than
  counters, so the output-token column is null on every row with a reason naming
  that, never a gauge delta. One `period_overhead` row per period holds the
  aggregate in list-price dollars beside a fully-loaded column that is null on
  every row: the direct half is five-hour-window points, the overhead half has no
  output-token counter to convert it, and the reason names that incommensurability
  rather than adding across meters. Neither table carries an issue column, so
  apportioning overhead to an issue is not something the output can express. The
  spool's money column is Claude Code's client-side figure and is named
  `cost_usd_list_price` — list price, not spend — and no rendering path calls it a
  cost.

- **Every spooled status-line render carries a timestamp (#488).** `tools/quota_tap.sh`
  writes each payload under a `ts`/`payload` envelope, so the spool is placeable in
  time rather than ordered only by line position. The tap stays fail-open — a `date`
  that fails leaves an empty `ts`, counted as untimestamped by the reader, never an
  error the session sees — and the generational rollover is unchanged. Renders older
  than the timestamps are excluded from every period and counted in coverage, never
  summed; periods derive from the timestamps and never from the spool's generation
  boundaries, whose unserialised rollover can drop a generation early.

- **The session view states its boundary in every rendering path (#488).** The spool
  is a record of interactive sessions: the tap fires on a status-line render and the
  orchestrator seat renders none, so the view omits the orchestrator's own turns —
  the largest non-dispatched consumer it claims to cover — while counting the human's
  interactive sessions alone. That absence is a `boundary` column on every row of
  both tables, `orchestrator=absent` on the rebuild's summary line, and a hazards
  entry; the period aggregate and its fully-loaded column carry the same warning as
  the overhead they derive from.
