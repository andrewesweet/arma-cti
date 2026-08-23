# The observatory's hazards list

The traps that cost an analyst an hour each, seeded with the ones already known.
Each names its mechanism, because the second occurrence of a trap is always wearing a
different issue number.

## 1. The two spend encodings

Claude emits per-request token counts as attributes on `claude_code.api_request` log
records. Codex emits `codex.turn.token_usage` as a **histogram metric** whose
datapoints carry a `token_type` attribute — no `asInt`/`asDouble` at all; the count
stands in the datapoint's `sum`.

**A reader that understands only one encoding returns rows, looks correct, and books
an entire lane at zero.** That is #458's most-repeated defect in a new place, and
nothing downstream notices, because there is no independent figure to disagree with.

The store reads both (`spend_encoding` names which one a row read) and selects rather
than sums when a dispatch carries both. Two corollaries:

- A lane reading zero is not evidence the lane was cheap — check `spend_encoding` and
  `spend_encoding_reason` first. Absent and cheap are different facts.
- Codex's `total` and `reasoning_output` token types are non-disjoint subsets and are
  excluded, exactly as `tools/ledger.py` excludes them; bucketing either would inflate
  every Codex row and nothing would notice.

## 2. Truncated lines in the archive

The export files are appended while agents run, and a writer killed mid-line leaves a
truncated JSON line behind — four exist in the archive today. A reader that skips
unparseable lines silently is indistinguishable from a reader that read everything
(#496), and the parse boundary took six rounds to get reported rather than swallowed
(#503).

The rebuild counts every unparseable line, names its file, completes, and prints the
count in its coverage line. **If `malformed_lines` grows between rebuilds, that is a
finding about the writers, not noise to absorb** — and a dispatch whose spend was read
despite malformed lines read only the lines that parsed, so its figure is a floor.

## 3. The export directory is pruned

`just ledger-sync prune --apply` deletes an export file older than thirty days once a
ledger row materialised from that file exists. **A rebuild over a pruned directory
returns rows, looks complete, and silently loses whatever only the raw file carried**
— the store's sources are durable, but only one of them is immutable.

The store falls back to the dispatch's materialised `ledger.json` and names that in
`telemetry_source=ledger_row` and the coverage line's `from_ledger_rows=`. What the
fallback cannot recover: the log-record encoding (the row's reader never read it) and
any distinction between a true zero and a silence. Both render as an absence with a
reason, never as zero. **If `from_ledger_rows` grows between rebuilds, your spend
history for those dispatches is now only as good as the row** — a `log_records`
figure for a pruned dispatch is gone for good.

## 4. A percentile without a named method is not a number

Nearest-rank picks a member of the sample; linear interpolation invents a value
between two. On a four-item sample they disagree at every percentile worth quoting,
and this store's windows will often be that small. A percentile whose method is not
stated is not reproducible: the next reader re-derives it their way, the two figures
carry the same name, and nothing disagrees out loud.

The method is nearest-rank, stated in the schema reference and pinned by a test on a
sample where the two methods differ — so a change of method is a red rather than a
silent drift. Its twin: the distribution is right-skewed, and quoting its **mean**
would summarise it by a number above its own 70th percentile. The one rendering path
for lead time, the `flow_lead_time` view, holds percentiles and a sample size and
nothing else — a mean cannot be emitted in that slot without the column-list test
going red. And an open item's `age` is only as current as the as-of instant the query
names: a stale as-of is a stale age, quietly.

## Standing rules beside the traps

- **Never sum spend across lanes** — the negative test in `tests/unit/test_observatory.py`
  exists because this is enforced mechanically or not at all.
- **Absent, uncalibrated and zero are three different facts, and each renders
  differently**: a number, `uncalibrated`, `absent`. A lane with no calibration
  renders `uncalibrated`, never zero, never a smaller number; a calibrated lane whose
  spend could not be derived renders `absent` — it is not cheap and it is not
  uncalibrated. This session has already conflated absence with a value four separate
  times (#502 twice, #503, #527), and #482's own summary line did it a fifth.
