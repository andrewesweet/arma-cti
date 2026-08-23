# The observatory cookbook

The queries this project has already asked, in the form that answers them. Every
query here runs against the shipped store in `tests/unit/test_observatory.py` — a
cookbook that does not run is worse than none — and the tables and columns are those
of `docs/observatory/schema-reference.md`, verbatim.

Rebuild first; the store is a cache and never a source of truth:

```
just observatory
```

## What a landed issue cost, per lane, in that lane's own meter

The store's first question (#482). Spend is per lane and never summed — the three
meters do not convert (ADR-0061 Decision 5) — so the answer is always a set of rows,
one per lane, each in its own meter. Never aggregate over this table's lanes.

```sql
SELECT issue, lane, dispatches, spend_dispatches, output_tokens, meter, cost, cost_reason
FROM issue_cost
WHERE landed = 1
ORDER BY issue, lane
```

Reading it: the Claude lane's `cost` is five-hour-window points; every other lane's
`cost` is `null` with an `uncalibrated` `cost_reason`, and its `output_tokens` is the
provider's own counter — the number to read, not a substitute cost.

Before quoting any figure, read its denominator in the rebuild's coverage line: how
many dispatches were seen, how many carried spend, how many were read from a
materialised row because their export file was pruned (`from_ledger_rows`), how many
issues landed. A lane whose rows rest on three dispatches out of forty is a lane
whose cost is a floor, and a lane whose dispatches were pruned is a lane whose
log-record spend is gone for good.

## How long work takes, how much finishes, and which open item to act on now

The flow view (#486). A work item is one issue; its clock starts at the issue's
earliest dispatch start and ends at the committer date of its landing commit — both
points are columns on `work_items`, named `clock_start` and `clock_end`. Lead time is
reported as **nearest-rank percentiles** through the one view that renders them,
`flow_lead_time`, whose columns are percentiles and the sample size and nothing else:
the distribution is right-skewed, and its mean would sit above its own 70th percentile.

```sql
SELECT * FROM flow_lead_time
```

Reading it: `p50_seconds` through `p95_seconds` are exact members of the landed
sample, never interpolations between two (the schema reference states the method).
`items` is the sample size — a percentile off four items is a floor, and the coverage
line's `work_items_landed` beside `work_items` says how much of the population the
distribution excludes.

Throughput is an exact count of landed work items over a window — a calendar month
here; widen or narrow the window to the question:

```sql
SELECT strftime('%Y-%m', clock_end) AS month,
       COUNT(*) AS items
FROM work_items
WHERE state = 'landed'
GROUP BY month
ORDER BY month
```

And the one leading indicator: every open item's age, computed against an instant you
name, read against the same historical percentiles. Cycle time is only known after the
work finished — after intervention was possible — so the age of open work against the
band is where acting early lives. Replace the literal instant with your own:

```sql
SELECT w.issue AS issue,
       CAST((julianday('2026-08-06T12:00:00') - julianday(w.clock_start)) * 86400 AS INTEGER) AS age_seconds,
       b.p50_seconds AS p50_seconds,
       b.p70_seconds AS p70_seconds,
       b.p85_seconds AS p85_seconds
FROM work_items AS w CROSS JOIN flow_lead_time AS b
WHERE w.state = 'open'
ORDER BY w.issue
```

An item whose age sits above the band's 85th percentile is an item that will set the
next record if nothing intervenes. `state` is `open` only while a dispatch of the
issue is still running; `abandoned` items (a dispatch terminal on a not-a-result
class, on work that started, from a seat that lands work — a review-seat death never
brands its item) are counted separately and never enter the lead-time
distribution, and `stopped` holds the terminal residue — ended, never landed, no
not-a-result class on started work of a seat that lands work, including every
dispatch refusing before the child launched.

## Where rework appears, and how many dispatches an issue took

The rework view (#487). Fix rounds per landing is ADR-0071 ruling 6's ranking key:
ranked for implementer-seat profiles and no others — a set derived from the seat
registries, never named — and read as **where rework appears, never as who caused it**.
Rounds are booked to the implementer while the ADR's own second escalation condition
says a repeated three-round state can mean the item was under-specified upstream, so a
bad row is a place to look and never a verdict on a profile.

```sql
SELECT profile, seat, dispatches, issues, rounds, landings,
       rounds_per_landing, ranked, measures
FROM profile_rework
ORDER BY ranked DESC, rounds_per_landing
```

Reading it: `rounds_per_landing` is `null` outside the implementer seat and for an
implementer with no landings — an undefined rate, with its rounds still visible in
`rounds`, never a division. `ranked` is `0` on every such row, and the reason column
distinguishes the five absences: no landing, lands-nothing-by-contract, the retro
seat's journal-only landing, a registry row that lands nothing, and a seat no registry
knows. `landings` itself counts a dispatch whenever its issue landed while it was open
— not that the dispatch produced the landing — so the key's denominator is
over-inclusive in a known, bounded way; the schema reference states the limit and #542
carries the fix. The strata are `profile` and `seat` alone — both written on the
dispatch record before the work started — and the `measures` column names every other
column as description, so a number quoted from this table arrives already marked as
descriptive.

The companion, reported beside the key and explicitly unranked — `ranked` is `0` on
every row, because a different ranking key would be a ruling:

```sql
SELECT issue, dispatches, review_rounds, ranked, measures
FROM issue_rework
ORDER BY issue
```

Before quoting an order, read the rebuild's `rework` line: `round_zero` against
`loops` is the key's own spread, `key_varies=no` says the ranked key does not vary and
therefore cannot rank, and `sample_limit=estimate_not_measurement` carries the ADR's
own account of its "20 to 30 landings" figure — no power calculation stands behind it.
The same issue's rounds appear on every profile-and-seat row that touched it, so
summing `rounds` across rows double-counts; dispatches per issue is the measure with
the real spread, and it stays beside the key.

## What the sessions no dispatch covers spent, per period — and what that figure cannot see

The session view (#488). Its source is the status-line spool, and the spool is a
record of **interactive sessions**: the tap fires on a status-line render and the
orchestrator seat renders none, so this figure omits the orchestrator's own turns —
the largest non-dispatched consumer it claims to cover — while counting the human's
interactive sessions alone. **Read the `boundary` column before quoting anything from
these tables**; it carries that warning on every row, and the rebuild's `sessions`
line carries `orchestrator=absent` beside it. A number quoted without the boundary is
the human's interactive spend presented as the overhead number.

```sql
SELECT session_id, period, renders, cost_usd_list_price, output_tokens,
       output_tokens_reason, boundary
FROM session_period
ORDER BY period, session_id
```

Reading it: the counters are period **deltas** of the payload's session-lifetime
running totals, never the totals themselves. `cost_usd_list_price` is Claude Code's
client-side figure — list price, not spend (#220) — named so in the column and never
as a cost. `output_tokens` is null on every row: the payload's token keys are
context-window gauges, not session-lifetime counters, and the reason says so — never
a gauge delta, and never a small number.

The period aggregate and the fully-loaded column — direct plus overhead over the
period's landings, named but never computed. Never attach either to an issue: neither
table carries an issue column, so apportioning is not something the output can
express, and a session-grain record names no issue to divide across.

```sql
SELECT period, landings, direct_landings, direct_window_points,
       cost_usd_list_price, overhead_window_points, fully_loaded_window_points,
       fully_loaded_window_points_reason, boundary
FROM period_overhead
ORDER BY period
```

Reading it: `fully_loaded_window_points` is null on every row, and its reason names
the incommensurability — the direct half is five-hour-window points, the overhead
half converts only to list-price dollars, and no meter holds both. Quote the two
halves as two numbers in two meters, never as one; a sum of points and dollars is a
number in no meter at all. The overhead half's sound figure is
`cost_usd_list_price` — the period's overhead in list-price dollars. `direct_landings`
beside `landings` is the partial-read visibility: a landing whose
cost could not be derived is counted in `landings` and absent from the direct figure,
never folded in as zero. The direct half is the Claude lane's meter alone; every other
lane's direct spend stays in its own unconverted meter outside this figure, and the
`boundary` column says so. Before quoting, read the rebuild's `sessions` line:
`untimestamped` counts renders older than the tap's timestamps — excluded and counted,
never summed into a period — and `without_session` counts timestamped renders
carrying no session id; an untimestamped line without one belongs to the first
counter, never the second.

## How much of the ruled capacity a window used, and where the loss sits

The occupancy view (#485). Capacity is the ruled work-in-progress limit times the
window's minutes; `used` is the count of live dispatches at each whole minute of the
window, summed — the method `tools/occupancy.py` published (#295), restated here over
the store so any window is one query. The window below is the research document's
observed one (`docs/research/system-of-work-observability.md` §1, ruled WIP 3);
**replace the two instants and the limit with your own** — a figure is only quotable
with the window it was computed over, which is why the bounds are columns of the
output and not prose around it.

```sql
WITH RECURSIVE
bounds(since_iso, until_iso, ruled) AS (
    VALUES ('2026-08-05T17:28:00+00:00', '2026-08-21T06:09:00+00:00', 3)
),
spans AS (
    SELECT CAST(strftime('%s', started_at) AS INTEGER) AS s,
           CAST(strftime('%s', ended_at) AS INTEGER) AS e
    FROM dispatches
    WHERE started_at IS NOT NULL AND ended_at IS NOT NULL
),
minutes(t) AS (
    SELECT CAST(strftime('%s', since_iso) AS INTEGER) FROM bounds
    UNION ALL
    SELECT minutes.t + 60 FROM minutes CROSS JOIN bounds
    WHERE minutes.t + 60 < CAST(strftime('%s', until_iso) AS INTEGER)
),
series AS (
    SELECT minutes.t AS t, COUNT(spans.s) AS level
    FROM minutes LEFT JOIN spans ON spans.s <= minutes.t AND minutes.t < spans.e
    GROUP BY minutes.t
)
SELECT (SELECT since_iso FROM bounds) AS window_since,
       (SELECT until_iso FROM bounds) AS window_until,
       (SELECT ruled FROM bounds) AS ruled_wip,
       COUNT(*) AS minutes,
       SUM(level) AS used_minutes,
       (SELECT ruled FROM bounds) * COUNT(*) AS capacity_minutes,
       (SELECT ruled FROM bounds) * COUNT(*) - SUM(level) AS lost_minutes,
       ROUND(CAST(SUM(level) AS REAL) / COUNT(*), 4) AS mean_concurrency,
       SUM(CASE WHEN level = 0 THEN 1 ELSE 0 END) AS idle_minutes,
       (SELECT COUNT(*) FROM dispatches d CROSS JOIN bounds b
         WHERE d.started_at IS NOT NULL AND d.ended_at IS NULL
           AND strftime('%s', d.started_at) < CAST(strftime('%s', b.until_iso) AS INTEGER)
       ) AS unbounded_dispatches
FROM series
```

Reading it: a span is `started_at` to `ended_at`, and a non-null `ended_at` exists
only where the run's own records attest both bounds — a closeout the stop sweep
wrote (`stopped_by`) or a result with no start of its own renders `ended_at` null
with its reason and contributes **no** occupied time, however long the dispatch may
have run. Work that started and did not complete is named by the
`terminal_state` column (#489's block, never re-derived from timestamps or an absence
of landing), and the dispatches a window's `used` could not bound are counted in
`unbounded_dispatches`, so `used` reads as the floor it is. `used` counts every live
dispatch at its own level, so a window whose concurrency ran above the ruled limit can
show `lost_minutes` below zero — that is the overrun made visible, not a broken
formula.

The concurrency distribution, because a mean of 0.48 can hide five minutes at level
three as easily as it hides sixteen idle hours:

```sql
WITH RECURSIVE
bounds(since_iso, until_iso, ruled) AS (
    VALUES ('2026-08-05T17:28:00+00:00', '2026-08-21T06:09:00+00:00', 3)
),
spans AS (
    SELECT CAST(strftime('%s', started_at) AS INTEGER) AS s,
           CAST(strftime('%s', ended_at) AS INTEGER) AS e
    FROM dispatches
    WHERE started_at IS NOT NULL AND ended_at IS NOT NULL
),
minutes(t) AS (
    SELECT CAST(strftime('%s', since_iso) AS INTEGER) FROM bounds
    UNION ALL
    SELECT minutes.t + 60 FROM minutes CROSS JOIN bounds
    WHERE minutes.t + 60 < CAST(strftime('%s', until_iso) AS INTEGER)
),
series AS (
    SELECT minutes.t AS t, COUNT(spans.s) AS level
    FROM minutes LEFT JOIN spans ON spans.s <= minutes.t AND minutes.t < spans.e
    GROUP BY minutes.t
)
SELECT level AS concurrency, COUNT(*) AS minutes
FROM series
GROUP BY level
ORDER BY level
```

And the idle gaps themselves, listed with their start, end and duration — many small
stalls and a few long sleeps are different problems, and only the list tells them
apart. A gap is a maximal run of idle minutes, so its bounds are the first idle
minute and the end of the last one:

```sql
WITH RECURSIVE
bounds(since_iso, until_iso, ruled) AS (
    VALUES ('2026-08-05T17:28:00+00:00', '2026-08-21T06:09:00+00:00', 3)
),
spans AS (
    SELECT CAST(strftime('%s', started_at) AS INTEGER) AS s,
           CAST(strftime('%s', ended_at) AS INTEGER) AS e
    FROM dispatches
    WHERE started_at IS NOT NULL AND ended_at IS NOT NULL
),
minutes(t) AS (
    SELECT CAST(strftime('%s', since_iso) AS INTEGER) FROM bounds
    UNION ALL
    SELECT minutes.t + 60 FROM minutes CROSS JOIN bounds
    WHERE minutes.t + 60 < CAST(strftime('%s', until_iso) AS INTEGER)
),
series AS (
    SELECT minutes.t AS t, COUNT(spans.s) AS level
    FROM minutes LEFT JOIN spans ON spans.s <= minutes.t AND minutes.t < spans.e
    GROUP BY minutes.t
),
zeros AS (
    SELECT t, ROW_NUMBER() OVER (ORDER BY t) AS rn
    FROM series
    WHERE level = 0
)
SELECT strftime('%Y-%m-%dT%H:%M:%SZ', MIN(t), 'unixepoch') AS gap_start,
       strftime('%Y-%m-%dT%H:%M:%SZ', MAX(t) + 60, 'unixepoch') AS gap_end,
       COUNT(*) * 60 AS duration_seconds
FROM zeros
GROUP BY t - rn * 60
ORDER BY MIN(t)
```

Reading it: the gaps partition the histogram's `concurrency = 0` row, so their total
is the window's idle minutes and never a second measure of it. Over §1's own window,
a disagreement between these figures and §1's is a red and not a rounding note —
report it with both figures rather than tuning either side. §1's `used` and mean
concurrency stood up against the corrected store (within six percent on the window
the review measured); its two idle figures do not agree with each other (7,510 awake
of 22,361 minutes implies 247.5 idle hours; the gap list claims 251.8), and the
corrected store sides with the gap list, so the awake-minus-total arithmetic is the
document's error, not the store's.
