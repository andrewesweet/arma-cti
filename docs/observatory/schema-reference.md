# The observatory store's schema reference

`just observatory` rebuilds `~/.arma-cti/observatory/store.json` in full on every run,
from its sources — the per-dispatch OTel export under
`/var/log/claude-otel/dispatches/`, the dispatch records under `~/.arma-cti/dispatches/`,
the review journal under `~/.arma-cti/review/`, and git. The store is a cache and never
a source of truth: a schema change is a re-run, not a migration, and a number you
distrust is a number you rebuild.

The rebuild is deterministic. Nothing in the document reads the wall clock, every list
is sorted, and two runs over the same inputs produce the same bytes.

## Retention: the raw export is not immutable

`just ledger-sync prune --apply` deletes an export file older than thirty days once a
ledger row materialised from that file exists (`tools/ledger.py`, `RETENTION_DAYS`).
Where the file is gone, the store reads the dispatch's materialised `ledger.json`
instead, and names that in `telemetry_source` — a rebuild after a prune never looks
like a rebuild before one. The row carries the metric and span encodings' numbers, so
a pruned dispatch's spend survives; what does not survive is the log-record encoding,
which the row's reader never read, and any distinction between a true zero and a
silence. Both render as an absence with a reason, never as zero.

## The document

| Key | Shape | Meaning |
|---|---|---|
| `schema` | string | `cti.observatory/3` |
| `inputs` | object | The four paths the rebuild read: `dispatch_root`, `export_dir`, `review_root`, `repo` |
| `coverage` | object | The rebuild's own denominators — see below |
| `malformed` | array | One entry per export file with unparseable lines: `file`, `lines` |
| `dispatches` | array | One row per dispatch record — the `dispatches` table |
| `issue_cost` | array | One row per (issue, lane) — the `issue_cost` table |
| `work_items` | array | One row per issue — the `work_items` table |
| `issue_rework` | array | One row per issue — the `issue_rework` table |
| `profile_rework` | array | One row per (profile, seat) — the `profile_rework` table |

### `coverage`

| Column | Meaning |
|---|---|
| `dispatches` | Dispatch records seen |
| `dispatches_with_telemetry` | Of those, how many were read from their OTel export file |
| `dispatches_from_ledger_rows` | Of those, how many were read from a materialised `ledger.json` — the file was pruned |
| `dispatches_with_spend` | Of those, how many carried derivable spend |
| `dispatches_without_telemetry` | The ids with neither an export file nor a ledger row, named |
| `issues` | Distinct issues named by a usable record |
| `issues_with_landings` | Of those, how many have a landing on `origin/main` |
| `work_items` | Work items — issues — in the store, one per issue |
| `work_items_landed` | Of those, how many landed |
| `work_items_open` | Of those, how many have a dispatch still running |
| `work_items_abandoned` | Of those, how many ended on a not-a-result class without landing |
| `work_items_stopped` | Of those, the terminal residue — ended, never landed, no failure class |
| `review_loops` | Issue loops read from the review journal, any round count |
| `review_loops_round_zero` | Of those, how many sit at round zero — the key's own spread |
| `review_loops_unreadable` | The issues whose `loop.json` exists but would not parse, named |
| `malformed_lines` | Total unparseable export lines, across all files |

## The rule every table obeys

**Every nullable column carries a reason for its null.** A column named `x` is `null`
exactly when its sibling `x_reason` is a non-null string saying why. An absence is
never a zero, and the reason sibling is what keeps a lane with no calibration from
being read as a lane that is cheap.

## The `dispatches` table

One row per dispatch record under the dispatch root.

| Column | Null? | Meaning |
|---|---|---|
| `dispatch_id` | never | The dispatch's id, and the table's identity |
| `lane` | + `lane_reason` | The lane the record names |
| `profile` | + `profile_reason` | The profile the record names |
| `seat` | + `seat_reason` | The seat the record names |
| `issue` | + `issue_reason` | The issue the record names |
| `telemetry_source` | never | `ledger_export`, `ledger_row`, or `absent` |
| `telemetry_path` | + `telemetry_path_reason` | The export file's name, when one exists |
| `spend_encoding` | + `spend_encoding_reason` | Which of the two spend encodings was read — see below |
| `input_tokens` | + `input_tokens_reason` | Input tokens, in the provider's own units |
| `output_tokens` | + `output_tokens_reason` | Output tokens — the Claude meter's basis |
| `cache_read_tokens` | + `cache_read_tokens_reason` | Cache reads |
| `cache_creation_tokens` | + `cache_creation_tokens_reason` | Cache writes |
| `landed_sha` | + `landed_sha_reason` | The commit this dispatch landed, bounded as `tools/ledger.py` bounds it |
| `started_at` | + `started_at_reason` | When this dispatch began — the result's `started_at`, else the plan's `planned_at` (`ledger.dispatch_start`'s rule) |
| `end_state_class` | + `end_state_class_reason` | How this dispatch ended, in `tools/ledger.py`'s own vocabulary; null only where a pruned row's `end_state` block is gone |
| `gate_outcome` | + `gate_outcome_reason` | `gate_outcome`'s vocabulary: `landed`, `running`, `not_a_result`, `lands_nothing`, `not_landed` |

`spend_encoding` is `metric` (token metrics or token-bearing spans, including the
histogram body Codex uses), `log_records` (token counts as attributes on log records,
which is how Claude Code reports per-request spend), or `null` with a reason. A row
read from a materialised `ledger.json` can only ever read `metric` — the row's reader
never read the log-record encoding — so `telemetry_source` is what says whether a
`log_records` figure was even possible for this dispatch.

## The `issue_cost` table

One row per (issue, lane). **There is no row that joins lanes, and no column that sums
across them** — the three lanes' meters do not convert (ADR-0061 Decision 5), so the
shape has nowhere to put such a number. The one sum this table performs is within a
single lane and a single issue: one meter, one currency.

| Column | Null? | Meaning |
|---|---|---|
| `issue` | never | The issue |
| `lane` | never | The lane — every other column is in this lane's own meter |
| `landed` | never | Whether any dispatch of this pair landed |
| `landed_sha` | + `landed_sha_reason` | The landing commit, or which of the three tests answered |
| `dispatches` | never | Dispatches of this issue on this lane |
| `spend_dispatches` | never | Of those, how many carried spend records — partial reads stay visible |
| `spend_encoding` | + `spend_encoding_reason` | As the dispatches table; `mixed` where the lane's dispatches disagreed |
| `input_tokens` | + `input_tokens_reason` | Summed within the lane, over the dispatches that carried spend |
| `output_tokens` | + `output_tokens_reason` | As above |
| `cache_read_tokens` | + `cache_read_tokens_reason` | As above |
| `cache_creation_tokens` | + `cache_creation_tokens_reason` | As above |
| `meter` | never | `claude_five_hour_window_points`, or `uncalibrated_provider_tokens` |
| `calibration_id` | + `calibration_id_reason` | The Claude calibration `tools/ledger.py` carries, or why none exists |
| `cost` | + `cost_reason` | Five-hour-window points on the Claude lane; `null` elsewhere — see below |

A Claude-lane `cost` is the exact quotient of `output_tokens` over the calibration's
measured tokens-per-point, unrounded, and its accuracy is the calibration's (±8%,
#218). An uncalibrated lane's counters are its provider's own and no conversion to
any other lane's meter exists; the row says so rather than printing a number. A
calibrated lane whose spend could not be derived — a pruned source, or no token
records — carries `null` with the reason that names which. **Absent, uncalibrated
and zero are three different facts**, and the summary line renders each differently:
a number, `uncalibrated`, `absent`.

## The `work_items` table

One row per issue (#486). Time is the one quantity commensurable across lanes, so the
work item is per issue and never per lane.

| Column | Null? | Meaning |
|---|---|---|
| `issue` | never | The issue |
| `state` | never | `landed`, `open`, `abandoned`, or `stopped` — see below |
| `clock_start` | + `clock_start_reason` | The issue's earliest dispatch `started_at` |
| `clock_end` | + `clock_end_reason` | The committer date of the newest commit the issue's dispatches landed |
| `lead_time_seconds` | + `lead_time_seconds_reason` | `clock_end` minus `clock_start`, exact integer seconds |

**The clock's two points are named, not implied.** It starts at the issue's earliest
dispatch start — a planner dispatch that preceded the implementer counts, because the
clock measures the work system, not one seat — and it ends at the landing commit's
committer date, the moment the work became visible on `origin/main`. Both picks
compare instants, never ISO strings, so timestamps carrying different UTC offsets
order by time.

**`state` is derived from the dispatch rows' own `gate_outcome`, in preference order.**
`landed` where any dispatch of the issue landed; else `open` while any dispatch is
still running; else `abandoned` where any dispatch ended `not_a_result`; else
`stopped`. The boundary on `abandoned` is deliberate and narrow: it reuses the failure
classes `gate_outcome` already names, read from the records at rebuild time, and
excludes such items from the lead-time distribution while counting them separately in
the coverage block. **#489 will widen it** — its recorded terminal state puts the
failure class on the record itself — and `stopped` holds the terminal residue (ended,
never landed, no failure class) until then. An issue dispatched only to seats that
land nothing by construction reads `stopped` for the same reason: a fact about the
seat is not a fact about this issue's completion.

## The `flow_lead_time` view

Lead time's one rendering path: `p50_seconds`, `p70_seconds`, `p85_seconds`,
`p95_seconds`, `items` — percentiles and the sample size, and nothing else. **No mean
can be emitted in this slot**, because the column list is the view's whole definition;
the distribution is right-skewed and its mean would sit above its own 70th percentile.

**The percentile method is nearest-rank and it is part of the contract.** The p-th
percentile is the value at rank `ceil(p·n/100)` in the ascending sort — a member of
the sample, never an interpolation between two. Nearest-rank because it is exact
integer arithmetic in the standard library's SQL, so the shipped store answers it
without a custom function. The tests pin the view's values on a sample where
nearest-rank and linear interpolation disagree at every percentile, so a change of
method is a red rather than a silent drift.

**An empty landed sample states itself.** The view's one row then carries null
percentiles — no member exists to read — with `items` `0`, because an empty sample is
a stated fact and not an unknown size: a null there would read as a sample the view
could not count.

## The `issue_rework` table

One row per issue (#487). Dispatches per issue is the rework view's companion measure —
a rework proxy with real spread, and the measure most likely to move under an
intervention — and it is **explicitly unranked**: a different ranking key would be a
ruling, not a preference (ADR-0071 ruling 6).

| Column | Null? | Meaning |
|---|---|---|
| `issue` | never | The issue |
| `dispatches` | never | Every dispatch that named it, across every seat and lane |
| `review_rounds` | + `review_rounds_reason` | The issue's fix-round count from the review journal |
| `ranked` | never | Always `0` — this table ranks nothing |
| `measures` | never | The marker naming these outcome measures as description, never strata |

An issue with no loop carries `null` rounds with the reason that names it — an absence
is never zero rounds. A loop that would not parse is counted in the coverage block's
`review_loops_unreadable` and rendered as `unreadable loop` by the rebuild, never read
as zero.

## The `profile_rework` table

One row per (profile, seat) (#487). Fix rounds per landing is ADR-0071 ruling 6's
ranking key, and this table is where it lives: computed for implementer-seat profiles
and no others, read as **where rework appears**, never as who caused it — rounds are
booked to the implementer while the ADR's own second escalation condition says a
repeated three-round state can mean the item was under-specified upstream.

| Column | Null? | Meaning |
|---|---|---|
| `profile` | never | The profile — a stratum, written on the dispatch record before the work started |
| `seat` | never | The seat — a stratum, written on the dispatch record before the work started |
| `dispatches` | never | The row's dispatch count — an outcome measure |
| `issues` | never | Distinct issues the row dispatched on — an outcome measure |
| `rounds` | never | Fix rounds over those issues, from the review journal — an outcome measure |
| `landings` | never | The row's dispatches that landed — an outcome measure |
| `rounds_per_landing` | + `rounds_per_landing_reason` | The ruled key: `rounds` over `landings` |
| `ranked` | never | `1` only where the key exists; every other row is reported and unranked |
| `measures` | never | The marker naming the outcome columns as description, never strata |

**The stratification is pre-work only.** The grouping key is the dispatch record's own
`profile` and `seat`, both written before the child ran. Nothing known only after the
work finished — rounds, landing time, whether it landed at all — enters a stratum, and
the `measures` column says so in the output itself.

**The ranked seat set is derived, never named.** `dispatch.SEATS`' `lands` column
crossed with `ledger`'s `seat_shape` answers which seats may rank: a seat ranks when it
both reaches `just land` and lands work rather than a journal. Today that is exactly
`implementer`; a new seat joins by its registry rows and not by an edit to the store.

**Three absences, three reasons.** A ranked seat with no landings is an undefined rate —
rounds visible, `ranked` `0`, never a division. A seat that lands nothing by contract
(`review`, `recon`, `planner`) reports its rework unranked with a reason naming the
contract, and the `retro` seat's journal landings are named not-an-implementer's-
denominator by the same derivation. A seat no registry knows is unranked because
whether it may rank is not derivable, not because it was judged.

**Rounds are attributed, not partitioned.** The same issue's rounds legitimately appear
on several rows — the implementer's and the reviewer's among them — because the
attribution is where rework appeared, never who caused it. Quoting one row's `rounds`
as a total across profiles double-counts.

**The sample is small and the store says so.** Most issues sit at round zero, so the
key barely varies; the rebuild's `rework` line carries `round_zero` against `loops`,
states `key_varies=no` when the ranked key does not vary, and marks the sample limit
`estimate_not_measurement` — the ADR's own account of its "20 to 30 landings" figure:
no power calculation, base rate or effect size stands behind it.

## Querying

The store is SQL-queryable through the standard library:

```
just observatory query "SELECT * FROM issue_cost WHERE landed = 1"
```

**A store of another schema refuses at open.** The `schema` the store carries is read
before any table: a store naming any other version — a `/1` store predates
`work_items` — refuses by name, `schema_mismatch`, naming the version found and the
version needed, rather than raising on a table that version never had. The remedy is
the store's own first rule: rebuild it.

The tables and columns above are the SQL schema verbatim. The cookbook
(`docs/observatory/cookbook.md`) carries the queries this project has already asked,
and every query in it runs against the shipped store in a test.
