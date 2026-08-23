### Added

- **Non-dispatched session spend, reported per period and never per issue (#488).**
  The observatory store grows a session view over the status-line spool: one
  `session_period` row per (session, month) holding the period's consumption as
  deltas of the payload's session-lifetime running totals, and one `period_overhead`
  row per period holding the aggregate beside a fully-loaded figure — direct plus
  overhead over the period's landings, in the Claude lane's window points, null with
  a reason naming which half is missing where one is. Neither table carries an issue
  column, so apportioning overhead to an issue is not something the output can
  express. The spool's money column is Claude Code's client-side figure and is named
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
  entry; the fully-loaded figure carries the same warning as the overhead it derives
  from.
