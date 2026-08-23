# The observatory store's schema reference

`just observatory` rebuilds `~/.arma-cti/observatory/store.json` in full on every run,
from its sources — the per-dispatch OTel export under
`/var/log/claude-otel/dispatches/`, the dispatch records under `~/.arma-cti/dispatches/`,
and git. The store is a cache and never a source of truth: a schema change is a re-run,
not a migration, and a number you distrust is a number you rebuild.

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
| `schema` | string | `cti.observatory/1` |
| `inputs` | object | The three paths the rebuild read: `dispatch_root`, `export_dir`, `repo` |
| `coverage` | object | The rebuild's own denominators — see below |
| `malformed` | array | One entry per export file with unparseable lines: `file`, `lines` |
| `dispatches` | array | One row per dispatch record — the `dispatches` table |
| `issue_cost` | array | One row per (issue, lane) — the `issue_cost` table |

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

## Querying

The store is SQL-queryable through the standard library:

```
just observatory query "SELECT * FROM issue_cost WHERE landed = 1"
```

The tables and columns above are the SQL schema verbatim. The cookbook
(`docs/observatory/cookbook.md`) carries the queries this project has already asked,
and every query in it runs against the shipped store in a test.
