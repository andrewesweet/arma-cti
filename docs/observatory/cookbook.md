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
one per lane, each in its own meter. `landed` means the issue has a recovered landing
as observed through that lane's dispatch rows; it does not mean the lane produced it.
Never aggregate over this table's lanes.

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

## The compact history of landed issues

The rebuild also writes `docs/observatory/landed-issues.md`, one generated row per
landed issue. It is the diff-sized first read; the store remains the detailed source.
Costs stay in separate lane columns and in their own meters — there is no total to
add across lanes. `counted` includes a numeric zero, `unrecorded` carries the short
codes `U` (uncalibrated) or `A` (absent), while `C<number>` is a counted cost and `N`
is `none not_involved`. The full reason remains in the store's `costs` JSON, not in
every Markdown cell. Only issues that have landed get rows, so dispatches on issues
not yet landed do not churn the committed file. Later dispatches naming a landed issue
are folded into that row on regeneration.

This file is generated output. `check-observatory` rebuilds in memory; a clean stale
projection is reported as `observatory_summary=stale` and never written into a feature
branch. The orchestrator regenerates and commits it at landing. An uncommitted hand edit
stays red; a committed hand edit is indistinguishable from staleness. A source refusal
stays red. Never hand-edit the file.

```sql
SELECT issue, landed_sha, dispatches, review_rounds,
       lead_time_seconds, lanes, costs
FROM issue_summary
ORDER BY issue
```

The SQL `costs` column is the JSON object behind the Markdown lane cells. Read the
`state` before interpreting its `cost`: `counted` is a number in the named meter,
`unrecorded` is an unknown carrying `U` or `A`, and `none` is `N`. Code meanings and
full-reason semantics are in the schema reference.

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
SELECT profile, seat, dispatches, issues, rounds, landings, landings_reason,
       rounds_per_landing, ranked, measures
FROM profile_rework
ORDER BY ranked DESC, rounds_per_landing
```

Reading it: `rounds_per_landing` is `null` outside the implementer seat and for an
implementer with no landings — an undefined rate, with its rounds still visible in
`rounds`, never a division. `ranked` is `0` on every such row, and the reason column
distinguishes the five absences: no landing, lands-nothing-by-contract, the retro
seat's journal-only landing, a registry row that lands nothing, and a seat no registry
knows. `landings` credits only a dispatch with the issue's recovered produced landing
and an `ok` end state. `infra_unavailable`, `quota_exhausted` and `provider_refused`
are known not to contribute; `untyped_harness_failure` is excluded but undetermined
because its harness may have failed after the child finished. Another end state is
excluded and named in `landings_reason` when the available evidence cannot establish
contribution. The landing journal's author relation remains a potential-author set,
not exact production proof. The strata are `profile` and `seat` alone — both written on the
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

## Which stages are reached first time, and what the pipeline's yield is

The stage view (#490). Rolled throughput yield multiplies each stage's first-pass
rate, so five stages at ninety per cent each is fifty-nine — every stage can look
healthy while four items in ten need rework somewhere. The per-stage rates are a
grouping over each arrival's own recorded status; nothing here is reconstructed
from timestamps or review rounds.

```sql
SELECT stage, arrivals, first_time, after_rework, undetermined,
       first_pass_yield, first_pass_yield_reason, boundary
FROM stage_first_pass
ORDER BY stage
```

Reading it: `first_pass_yield` is `first_time` over `first_time + after_rework`,
and `undetermined` sits **beside** the yield, never inside its denominator — an
arrival whose history could not be read is stated as `undetermined`, never
defaulted to true, because one defaulted true inflates every stage after it and
the product with them. A stage with no determinable arrivals carries a `null`
yield with its reason rather than a perfect-looking one. **Rolled throughput
yield is the product of the `first_pass_yield` column across stages** — multiply
the six rates, and read the boundary column first: the stage journals begin at
#490, so arrivals before it are absent from this figure rather than counted as
rework, and the rebuild's `stages` line carries the journal and arrival counts
the product rests on.

## Whether every landing kept the never-alone rule, checked from the record

The landing view (#491). Every landing the review rung cleared now journals one
`cti.landing.reviewed` event naming the objects it touched and the role each
played: the issue as `subject`, the landed commit as `produced`, every profile the
records place on the work as `author` — a `dispatch` object per dispatched author,
an `authorship_declaration` object per interactive one (#398, the #524 and #548
shapes) — and the reviewing dispatch as `reviewer`. What this replaces is reading
the `gate_review=` line a landing prints about itself: the check below reads the
record, not the landing's own account of the landing.

The never-alone check itself — every landing whose reviewer profile is also an
author profile, which is the one arrangement ADR-0071 ruling 4 exists to refuse.
The block returns **findings**, and the two findings are different facts: a
`reviewer_is_author` row is the violation; an `unresolvable_reviewer` or
`unresolvable_author` row is a dispatch-typed relation whose object id names no
row in `dispatches` — the check could not look there, which is the absence of
evidence and never evidence of compliance. An empty answer over a populated
table is the rule holding **and** every relation resolved:

```sql
SELECT l.landing,
       'reviewer_is_author' AS finding,
       d.profile AS detail
FROM landings AS l
JOIN landing_relations AS rr ON rr.landing = l.landing AND rr.qualifier = 'reviewer'
JOIN dispatches AS d ON rr.object_type = 'dispatch' AND d.dispatch_id = rr.object_id
JOIN landing_relations AS ra ON ra.landing = l.landing AND ra.qualifier = 'author'
LEFT JOIN dispatches AS da ON ra.object_type = 'dispatch' AND da.dispatch_id = ra.object_id
WHERE COALESCE(da.profile,
               CASE WHEN ra.object_type = 'authorship_declaration' THEN ra.object_id END)
      = d.profile
UNION ALL
SELECT r.landing,
       'unresolvable_' || r.qualifier AS finding,
       r.object_id AS detail
FROM landing_relations AS r
LEFT JOIN dispatches AS d ON r.object_type = 'dispatch' AND d.dispatch_id = r.object_id
WHERE r.object_type = 'dispatch' AND d.dispatch_id IS NULL
ORDER BY landing, finding
```

Reading it: an author object resolves to its profile two ways — a `dispatch`
joins `dispatches` on the id, an `authorship_declaration`'s object id **is** the
profile — and the reviewer resolves the same way, so the declared author and the
dispatched one are both inside the check a record can run. The second arm exists
because the first cannot say what it did not see: its inner join to `dispatches`
drops an unresolvable reviewer exactly as an author join would drop an
unresolvable author, and a query that filters to the rows it can join answers
"no violations" about landings it could not look at — #491's own failure mode,
one level up (#491 round 2, finding 1). A landing whose relation set carries no
author cannot be checked at all; the rebuild names those in
`landings_without_authors`, names the landings carrying unresolvable dispatch
relations in `landings_with_unresolved_relations`, and counts both lists' union
as `uncheckable` — the boundary column repeats it, because a silently unchecked
landing is the thing this query exists to prevent reading as clear.

The gate-landing half, where the printed line's four values live as data — two of
the four causes rest on bars read live at landing time, which no later read of the
records can reproduce, so the event carries what the landing derived:

```sql
SELECT gate_cause, COUNT(*) AS landings
FROM landings
WHERE gate_cause IS NOT NULL
GROUP BY gate_cause
ORDER BY landings DESC
```

And the counting discipline the two-table shape exists for (#491's fifth
criterion): "how many landings" and "how many objects did this landing touch"
are different grains, and each is counted on its own table —

```sql
SELECT l.landing, COUNT(r.qualifier) AS objects_touched
FROM landings AS l LEFT JOIN landing_relations AS r ON r.landing = l.landing
GROUP BY l.landing
ORDER BY l.landing
```

`COUNT(*)` over the **joined** rows is relation rows, never landings — one landing
touching six objects counts once in `landings` and six times in the join, and
that ratio is the shape working, not a double count to repair. The rebuild's
`landings` line carries both denominators — raw `events` beside distinct
landings, so a recorder duplicate shows as the two disagreeing — plus
`uncheckable`, the union count behind `landings_without_authors` and
`landings_with_unresolved_relations` together.

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

## What is waiting right now, and for how long

The queue-depth view (#492). The newest sample per queue — the leading
indicator, taken at the top of every orchestrator turn by the sampler folded
into `just watch-report`'s queue rung:

```sql
SELECT q.queue, q.state, q.count, q.oldest, q.oldest_age_s, q.count_reason,
       strftime('%Y-%m-%dT%H:%M:%SZ', q.sampled_at, 'unixepoch') AS sampled
FROM queue_depth q
JOIN (
    SELECT queue, MAX(sampled_at) AS newest FROM queue_depth GROUP BY queue
) latest ON q.queue = latest.queue AND q.sampled_at = latest.newest
ORDER BY q.queue
```

Reading it: `count = 0` with `state = 'counted'` is an empty queue — a sample,
not an absence — while `state = 'unrecorded'` says no record anywhere carries
that queue's membership (the `slot_lock` queue today; its bash seam journals
nothing) and `state = 'unreadable'` says a source existed and that sample could
not read it. Where a candidate read refused, `count_reason` carries that
refusal's kind, such as `unrecorded: github_unreadable`. Neither non-counting
state is a zero, and quoting either as one is the exact defect this vocabulary
exists to prevent. The `human_ruling` row is narrower than it reads: it counts
the open above-Low findings of loops still running, so unadjudicated Low
findings and anything on a loop that reached its terminus sit outside it — a
smaller number than "every open finding", and never better news. Read it as
what blocks a running loop, not as the review backlog's size. `oldest_age_s`
is null beside
`oldest = 'unrecorded'` — for the ready queues the label instant lives in the
tracker's timeline, and for the landing queue the demand side is recorded
nowhere — so an age is only ever quoted where `oldest = 'measured'`. Before
trusting a quiet system, read the rebuild's `queue_depth` coverage line: a
journal the sampler stopped writing leaves these rows stale, and
`samples=0` names a store whose sampler never ran.

A queue's history — depth over time — is the same table grouped the other way;
the sampler's cadence is the orchestrator's turn, not a clock, so the sample
count over a window says how busy the seat was, and a depth trend is read
against that cadence rather than assumed even.
