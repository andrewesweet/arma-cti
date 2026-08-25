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

## 5. The ranking key barely varies, and its rounds are attributed, not caused

Most issues sit at round zero, so fix rounds per landing — the ruled key — barely
moves, and an order over near-identical values reads as a verdict no sample supports.
The "20 to 30 landings" figure behind any confidence in it is an estimate, not a
measurement: no power calculation, base rate or effect size stands behind it
(ADR-0071 ruling 6). **The rebuild's `rework` line states both** — `round_zero`
against `loops`, `key_varies=no` when the key does not vary, and
`sample_limit=estimate_not_measurement` — so read the line before quoting the order.

Two more traps in the same table. Rounds are booked to every (profile, seat) row that
touched an issue, so **summing `rounds` across rows double-counts**: the attribution
is where rework appeared, never who caused it, and the ADR itself says a repeated
three-round state can mean the item was under-specified upstream. And `null` in
`rounds_per_landing` is one of five different facts — no landing, lands-nothing-by-
contract, journal-only landing, a registry row that lands nothing, unknown seat —
which is why the reason column exists; a reader who flattens them has turned a
contract into a score. The denominator has its own boundary: an issue-level produced
landing is not automatically a dispatch contribution. A dispatch typed as
`infra_unavailable`, `quota_exhausted`, `provider_refused` or
`untyped_harness_failure` is excluded from `landings`, even when its base and start
window see the same landing as another dispatch. A candidate with any other end state
than `ok` is also excluded because its contribution cannot be established;
`landings_reason` names the excluded dispatch and reason. The `issue_cost.landed` flag
remains an issue outcome at its `(issue, lane)` grain, not a lane-contribution flag. The
landing journal's `author` relation is a potential-author set, so the observatory does
not relabel it as exact dispatch production evidence.

## 6. The session view's source is interactive sessions, and its history has silent holes

The status-line spool records what renders a status line — interactive sessions. The
orchestrator seat renders none, so **the largest non-dispatched consumer is absent
from the session figures while they present themselves as the overhead number**: a
reader who skips the `boundary` column takes the human's interactive spend for the
system's overhead, an understatement in the direction that flatters the system. The
boundary is a column on every row of both tables and `orchestrator=absent` sits on the
rebuild's `sessions` line; quoting a session figure without its boundary is the trap.

Four more in the same source. The payload's token keys are **gauges, not counters**:
every one lives under `context_window` and measures the current window — across the
live spool the output gauge falls 2,678 times and rises 2,145 times between
consecutive renders of one session — so a reader that deltas one produces routinely
negative noise and presents it in the meter the direct half fills with genuinely
billed tokens. The store reads none of them; `session_period.output_tokens` and both
`period_overhead` window-point columns are absences whose reason names the gauge. Its
consequence: **the fully-loaded figure is absent, not small** — the overhead half
converts only to list-price dollars, the direct half is window points, and dollars do
not commensurate across lanes either, so `fully_loaded_window_points` is null with
the reason naming that incommensurability; a reader who wants "direct plus overhead"
must quote two numbers in two meters, never one. The rollover is **not serialised**
(#464's review): two
simultaneous rolls can drop the oldest generation one roll early, nothing in the
surviving files records it, and a period whose lines were lost reads short with no
signal — which is why no period anywhere in the store derives from a generation
boundary, only from render timestamps. Renders older than the timestamps (everything
spooled before #488) carry no instant, cannot be placed in a period, and are counted in
`session_renders_untimestamped` — excluded, never summed. And the money column is
Claude Code's client-side figure, **list price, not spend** (#220): it is named
`cost_usd_list_price`, and no rendering path calls it a cost.

## Standing rules beside the traps

- **Never sum spend across lanes** — the negative test in `tests/unit/test_observatory.py`
  exists because this is enforced mechanically or not at all.
- **Never apportion session overhead to an issue** — neither session table carries an
  issue column, so the output cannot express it; that shape is the rule's mechanical
  form, and widening it is a schema change, not a query.
- **Never quote a session figure without its `boundary`** — the orchestrator's absence
  is the one omission a reader quoting one number would otherwise never meet.
- **Absent, uncalibrated and zero are three different facts, and each renders
  differently**: a number, `uncalibrated`, `absent`. A lane with no calibration
  renders `uncalibrated`, never zero, never a smaller number; a calibrated lane whose
  spend could not be derived renders `absent` — it is not cheap and it is not
  uncalibrated. This session has already conflated absence with a value four separate
  times (#502 twice, #503, #527), and #482's own summary line did it a fifth.

## 7. Occupancy counts spans the run's own records attest, and its floor is a named list

A span needs both its bounds from the run itself. The current stop sweep writes an
explicit `terminal_state: {"state": "stopped"}` and no `ended_at`, because it closes
the dispatch record without observing the run's end. Eleven legacy `result.json`
files still carry `stopped_by` and the sweep's own `ended_at` — a fact about when the
sweep ran, never about when the work stopped, which may be any instant between the
plan and the sweep. The reader guard remains load-bearing for those records. A result
that recorded no `started_at` of its own likewise would pair its end with the plan's
`planned_at`, opening a span at a launch attempt rather than at work — the
never-launched refusal and the child-state-unknown failure both carry that shape.
**Either legacy shape renders `ended_at` null with its reason and contributes no
occupied time, however long the dispatch may have run.** Until #485 round 2 the store
took the sweep's clock as a genuine end and inflated its `used` by 58% over the research
window — eleven swept closeouts, the worst a week between plan and sweep with no
process left to kill — while §1 of the research document stood up: a reader comparing
the corrected store against §1 should find `used` and mean concurrency within single-
digit percent, and a disagreement beyond that is a red to report with both figures,
never a rounding note. The dispatches no window's `used` could bound are listed in the
coverage block's `dispatches_unbounded` and counted in the query's
`unbounded_dispatches`, so `used` reads as the floor it is. Work that started and did
not complete is read from #489's `terminal_state` block — bounded abandoned work
occupies its own real span; never re-derive the fact from timestamps or from an absence
of landing, which is #542's whole subject.

Three more in the same view. **Minute boundaries are sampled, not rounded**: a
dispatch live for forty seconds across no minute boundary contributes zero minutes,
and duration rounding would say one — the two methods disagree on exactly that
dispatch, which is why the test pins it. **`lost` can go negative**: `used` counts
every live dispatch at its own level, so a window whose concurrency ran above the
ruled limit shows a negative loss — that is the overrun made visible, not a broken
formula. And §1's own two idle figures do not agree with each other (7,510 awake of
22,361 minutes implies 247.5 idle hours; the gap list claims 251.8), because the
throwaway pass computed its gaps by a method it states nowhere — the corrected store
sides with the gap list to within one percent, so the awake-minus-total arithmetic
is the document's error, not a third method. The store's own gaps partition the
histogram's level-0 row, so gap total and idle minutes are one number by
construction, never two.

## 8. `undetermined` can spike globally, from one record it never names

The recorder grants an absent journal a clean past only after scanning the
pipeline dispatch records for the issue — and a record that exists but will not
read is taken as history seen, because the seat inside it cannot be known
(`tools/attribute_registry.py`'s `_pipeline_history_seen`). That pessimism is
**global, not per-issue**: one corrupt `dispatch.json` anywhere under the records
root makes every absent-journal issue's first arrival record `undetermined`,
whichever issue the corrupt record names. So a spike in
`stage_arrivals_undetermined` can be damage to one unrelated record rather than
a finding about the issues it appears on — check the records directory before
reading the spike as history the issues actually have. It fires once per issue at
most: the undetermined arrival founds the journal, and arrivals after it read
against that (#490 round 2, finding 1; the global scope recorded by #552, whose
reviewer accepted the direction as the safe one).

## 9. A fallback can converge on the truth after being wrong

The Git referencing-commit fallback cannot distinguish a bare issue list from a
landing attribution. A false row can therefore become accidentally true when that issue
lands later — the row's SHA changes or the issue's state changes, but neither proves
that the earlier fallback was right. `just observatory backfill` never uses the current
row as evidence: it accepts only an exact `just land` audit SHA, bounds it against
`origin/main` and a landing-capable dispatch window, and records the result as
`cti.relation.produced`. A closed issue without that evidence gets a reasoned,
subject-only marker; an open issue gets no marker. The dispatch window is deliberately
one-sided: its base is an ancestry floor and its start is a committer-date floor, with
no end ceiling, inheriting `ledger.landed`'s #245 limit. Thus a verbatim audit line pasted
without a blockquote from another issue could still pass if its SHA is on `origin/main` and
after this issue's earliest dispatch start; this command does not claim two-sided window
provenance. Read `landing_source` and the `journal_coverage` line before treating a
converged row as recovered.
