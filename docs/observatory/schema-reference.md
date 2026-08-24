# The observatory store's schema reference

`just observatory` rebuilds `~/.arma-cti/observatory/store.json` in full on every run,
from its sources — the per-dispatch OTel export under
`/var/log/claude-otel/dispatches/`, the dispatch records under `~/.arma-cti/dispatches/`,
the review journal under `~/.arma-cti/review/`, the status-line spool under
`~/.arma-cti/quota/` with its rolled generations, and git. The store is a cache and
never a source of truth: a schema change is a re-run, not a migration, and a number
you distrust is a number you rebuild.

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
| `schema` | string | `cti.observatory/9` |
| `inputs` | object | The six paths the rebuild read: `dispatch_root`, `export_dir`, `review_root`, `spool`, `repo`, `queue_root` |
| `coverage` | object | The rebuild's own denominators — see below |
| `malformed` | array | One entry per source file with unparseable lines — export, spool, stage, landing or queue journal: `file`, `lines` |
| `dispatches` | array | One row per dispatch record — the `dispatches` table |
| `issue_cost` | array | One row per (issue, lane) — the `issue_cost` table |
| `issue_summary` | array | One row per landed issue — the committed `landed-issues.md` projection |
| `work_items` | array | One row per issue — the `work_items` table |
| `issue_rework` | array | One row per issue — the `issue_rework` table |
| `profile_rework` | array | One row per (profile, seat) — the `profile_rework` table |
| `stage_first_pass` | array | One row per stage of the closed set — the `stage_first_pass` table |
| `landings` | array | One row per distinct landing — the `landings` table |
| `landing_relations` | array | One row per relation a landing's event carried — the `landing_relations` table |
| `session_period` | array | One row per (session, month) — the `session_period` table |
| `period_overhead` | array | One row per period with overhead or a landing — the `period_overhead` table |

### `coverage`

| Column | Meaning |
|---|---|
| `dispatches` | Dispatch records seen |
| `dispatches_with_telemetry` | Of those, how many were read from their OTel export file |
| `dispatches_from_ledger_rows` | Of those, how many were read from a materialised `ledger.json` — the file was pruned |
| `dispatches_with_spend` | Of those, how many carried derivable spend |
| `dispatches_unbounded` | Of those, the ids that carry a start and no end, named — the dispatches whose span the occupancy view cannot bound, so any window's `used` is a floor over this list |
| `dispatches_without_telemetry` | The ids with neither an export file nor a ledger row, named |
| `issues` | Distinct issues named by a usable record |
| `issues_with_landings` | Of those, how many have a landing on `origin/main` |
| `work_items` | Work items — issues — in the store, one per issue |
| `work_items_landed` | Of those, how many landed |
| `work_items_open` | Of those, how many have a dispatch still running |
| `work_items_abandoned` | Of those, how many ended on a not-a-result class, on work that started, from a dispatch of a seat that lands work, without landing |
| `work_items_stopped` | Of those, the terminal residue — ended, never landed, no not-a-result class on started work of a seat that lands work |
| `review_loops` | Issue loops read from the review journal, any round count |
| `review_loops_round_zero` | Of those, how many sit at round zero — the key's own spread |
| `review_loops_unreadable` | The issues whose `loop.json` exists but would not parse, named |
| `stage_journals` | Issue stage journals read, any arrival count |
| `stage_arrivals` | Stage arrivals those journals hold, across every stage |
| `stage_arrivals_undetermined` | Of those, how many carry an `undetermined` first-pass status — counted beside the yield, never inside its denominator |
| `landing_journals` | Issue landings journals read, any event count |
| `landing_events` | Raw landing events those journals hold — beside `landings`, so a recorder duplicate shows as the two counts disagreeing, visibly |
| `landings` | Of those, distinct landings — one per (issue, produced commit), the journal's newest event for the pair |
| `landing_relations` | Relation rows those winning events carried |
| `landings_without_authors` | The landings whose relation set carries no author, named — the landings the never-alone check cannot run over, a stated gap never a silent clearance |
| `landings_with_unresolved_relations` | The landings carrying a dispatch-typed relation whose object id names no dispatch row, named — the check could not look there, and `uncheckable` counts this list's union with `landings_without_authors` |
| `session_renders` | Status-line renders the session view read — timestamped, with a session id |
| `session_renders_untimestamped` | Renders the view could not place in a period — pre-#488 bare lines — counted, never summed |
| `session_renders_without_session_id` | Timestamped renders carrying no session id, counted and never attributed — an untimestamped line without one counts as untimestamped, never here |
| `session_spend_sessions` | Distinct sessions the view holds |
| `session_spend_periods` | Distinct months those sessions span |
| `malformed_lines` | Total unparseable lines, export and spool together, across all files |

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
| `ended_at` | + `ended_at_reason` | When this dispatch ended — the run's own closeout, a pruned dispatch's from its row's `gate` block; the current stop sweep writes no end, while a legacy closeout carrying `stopped_by` is rejected as a sweep clock, and a run that recorded no start of its own also attests no span; null means unbounded, never "to the window's end" |
| `terminal_state` | + `terminal_state_reason` | `stopped` where the stop closeout's explicit block says so, or `abandoned` where #489's block carries a not-a-result class; the null reason names which of the remaining facts it is — completed, still running, never started — and the fact is never re-derived from timestamps or an absence of landing (#542) |
| `end_state_class` | + `end_state_class_reason` | How this dispatch ended, in `tools/ledger.py`'s own vocabulary; null only where a pruned row's `end_state` block is gone |
| `gate_outcome` | + `gate_outcome_reason` | `gate_outcome`'s vocabulary: `landed`, `running`, `not_a_result`, `never_started`, `lands_nothing`, `not_landed` |

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

## The `issue_summary` table and committed projection

One row per `work_items` row whose state is `landed`. The rebuild writes the same
rows to `docs/observatory/landed-issues.md`; that file is a generated projection,
not a second source of truth. Work on issues not yet landed — including in-flight,
abandoned and stopped work — is deliberately outside it. Dispatches on issues not
yet landed therefore cannot make the committed file stale; later dispatches naming a
landed issue are included in that row and can make the check red until the orchestrator
regenerates it.

| Column | Null? | Meaning |
|---|---|---|
| `issue` | never | The landed issue |
| `landed_sha` | + `landed_sha_reason` | The newest landed commit the issue's records identify |
| `dispatches` | never | All dispatch records naming the issue, across seats and lanes |
| `review_rounds` | + `review_rounds_reason` | The issue's review-loop fix rounds |
| `lead_time_seconds` | + `lead_time_seconds_reason` | Earliest dispatch start to the landing commit's committer date |
| `lanes` | never | Comma-separated lanes involved in the issue, or `none` where no lane was recorded |
| `costs` | never | JSON object keyed by lane; each value is one of the summary cost cells below |

Each `costs` value carries a state, rather than using a null or zero as a state:
`counted` has a numeric `cost` and that lane's `meter` (including a real zero),
`unrecorded` has `cost: null`, a rendering of `uncalibrated` or `absent`, and a
non-empty `cost_reason`, and `none` has `rendering: not_involved` because no
dispatch of the issue used that lane. The Markdown projection renders the same
facts as `C<number>`, `U`, `A`, and `N`; it has no cross-lane total. `C<number>` is a
counted cost in the lane column's own meter, including `C0` for a real zero. `U` is
an unrecorded uncalibrated cost, `A` is an unrecorded absent cost, and `N` is no
involvement (`none not_involved`). The full `cost_reason` remains in the store's
JSON and is not repeated in every Markdown cell. The projection also uses `R` in
`review_rounds` for the known absence of a review loop. Every other nullable summary
field uses its `*_reason` sibling under the store's null law.

`just observatory` writes this projection from live sources. `just check-observatory`
performs a fresh rebuild in a temporary store and compares the generated bytes with
the committed file. A dispatched implementer may repair a `summary_mismatch` when
Git reports the canonical projection itself is unmodified; the repair writes the
in-memory bytes into the worktree, so the harness can commit them without persisting
the external cache. An uncommitted hand edit remains a refusal; a committed hand edit
is indistinguishable from staleness and may be overwritten by the repair. An unreadable
source or any other seat remains a refusal. The check intentionally ignores dispatches
on issues not yet landed, but does compare later dispatches naming landed issues because
those mutate an existing row.

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
`stopped`. The boundary on `abandoned` is deliberate and narrow: it reuses the
failure classes of `attribute_registry.NOT_A_RESULT_CLASSES` — all four, including
`untyped_harness_failure`, which outranks the rest (#184) and joined with #489 —
read from the records at rebuild time, and the same widening is what
`just ledger-sync` records as a `terminal_state` block on the dispatch's own ledger
row, so abandoned and completed work are distinguishable by the record alone. It is
also **weighed by seat**: only a dispatch of a seat that lands work (`ledger`'s
`seat_shape` "work") may brand its item abandoned, so a not-a-result on a
review-seat dispatch — its own review harness died — never abandons an issue whose
implementer dispatches all succeeded and are merely unlanded (#524 read abandoned
on exactly that shape); the dispatch row keeps its `not_a_result` outcome either
way, and the item reads from its work-bearing dispatches alone. A record carrying
no seat, or a seat no registry knows, reads as work-bearing by `seat_shape`'s
default, so a historical dispatch still brands its item. A
dispatch that refused before the child launched carries `never_started`, not
`not_a_result`, because work that never started is not work that started and did
not finish; its item departs to the residue. Abandoned items are excluded from the
lead-time distribution while counting separately in the coverage block. `stopped`
holds the terminal residue — ended, never landed, no not-a-result class on started
work of a seat that lands work. An issue dispatched only to seats that land nothing
by construction
reads `stopped` for the same reason: a fact about the seat is not a fact about this
issue's completion.

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
is never zero rounds — and an issue whose loop exists but would not parse carries a
different reason saying exactly that, so a reader querying the table meets two
different absences as two different strings rather than one flattened "no loop". A
loop that would not parse is also counted in the coverage block's
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
| `landings` | never | The row's dispatches whose issue landed at or after their own start — an outcome measure, bounded as described below |
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

**The denominator is over-inclusive, and says so here.** `landings` is not "the row's
dispatches that landed". A dispatch's `landed_sha` is derived by `tools/ledger.py`'s
landing detection — commits referencing the issue that descend from the dispatch's base
and postdate its start — so a dispatch counts whenever its issue landed at or after
its start, whether or not that dispatch produced the landing. The tests bound the start
and never the end, so a commit landing after the dispatch finished still counts; a
degenerate record, one carrying no base SHA or no start time, clears none of the tests
and never counts. Every dispatch an issue
carried while it landed shares in that landing, superseded ones included. ADR-0071
ruling 6 makes this column the key's denominator and says an implementer whose work
never lands is a zero denominator; the code gives such a row a denominator wherever the
issue landed at or after the start of any of its dispatches. A number wrong in that
known, bounded way
and saying so is honest; the same number silently is not. The semantics fix is filed
separately as #542 and this view deliberately does not reach for it.

**Five absences, five reasons.** A ranked seat with no landings is an undefined rate —
rounds visible, `ranked` `0`, never a division. A seat that lands nothing by contract
(`review`, `recon`, `planner`) reports its rework unranked with a reason naming the
contract, and the `retro` seat's journal landings are named not-an-implementer's-
denominator by a reason of their own, not the contract one. A seat whose registry row
says it lands nothing while its ledger shape says it lands work (`fable`,
`orchestrator`) carries the registry-row reason, and a seat no registry knows is
unranked because whether it may rank is not derivable, not because it was judged — a
dispatch record carrying no seat at all meets that same reason rendered against an
unnamed seat. The companion table's `review_rounds_reason` adds its own pair: no loop
recorded, and a loop recorded that would not parse — never one absence flattened into
another.

**Rounds are attributed, not partitioned.** The same issue's rounds legitimately appear
on several rows — the implementer's and the reviewer's among them — because the
attribution is where rework appeared, never who caused it. Quoting one row's `rounds`
as a total across profiles double-counts.

**The sample is small and the store says so.** Most issues sit at round zero, so the
key barely varies; the rebuild's `rework` line carries `round_zero` against `loops`,
states `key_varies=no` when the ranked key does not vary, and marks the sample limit
`estimate_not_measurement` — the ADR's own account of its "20 to 30 landings" figure:
no power calculation, base rate or effect size stands behind it.

## The `stage_first_pass` table

One row per stage of the closed set in `tools/attribute_registry.py`'s `STAGES`
(#490) — zeros included, so a stage no journal names states itself rather than
vanishing. The source is the per-issue stage journals under the review root, and
every figure is a grouping over the arrivals' own recorded first-pass statuses:
a reader never reconstructs first-pass yield by correlating timestamps, counting
review rounds or re-deriving dispatch order.

| Column | Null? | Meaning |
|---|---|---|
| `stage` | never | The pipeline stage — `attribute_registry.STAGES`' own key |
| `arrivals` | never | Arrivals journalled at this stage, every status |
| `first_time` | never | Of those, arrivals on the item's first pass |
| `after_rework` | never | Of those, arrivals that follow rework |
| `undetermined` | never | Of those, arrivals whose history could not be read — stated, never guessed |
| `first_pass_yield` | + `first_pass_yield_reason` | `first_time` over `first_time + after_rework`; `undetermined` sits beside the yield, never inside its denominator |
| `boundary` | never | The marker, like `measures`: the figure covers journalled arrivals only |

**Rolled throughput yield is the product of the `first_pass_yield` column across
stages**, read as a grouping over this table. The product multiplies the per-stage
rates, which is exactly why an undeterminable status is recorded as `undetermined`
rather than defaulted to true: five stages at ninety per cent is fifty-nine, and a
single defaulted true turns a real fifty-nine into a reported sixty-six with
nothing in the output saying so.

**The boundary column is the view's largest omission.** The stage journals begin
at #490, so every arrival before it — every brief, dispatch, gate run, exchange,
review and landing in the store's dispatch history — is absent from this figure
rather than counted as rework. An issue that predates the recorder does not
borrow a clean past from that absence: its first journalled arrival records
`undetermined`, because the recorder checks the issue's review directory and its
pipeline dispatch records before granting a `first_time` no journal supports —
and arrivals after that first one read against the journal it founded.
`undetermined` arrivals are the recorder's own
statement that an arrival's history had a hole in it, and a journal line that is
wrong on its face (unparseable, or naming a stage or status outside the closed
vocabularies) is malformed and counted in `malformed`, never bucketed as
`undetermined`: damage to the record and an undeterminable status are different
facts.

## The `landings` and `landing_relations` tables

One landing row per distinct landing, one relation row per object its event
touched (#491). The source is the per-issue landings journals under the review
root — `landings.jsonl`, beside each issue's stage journal — and a landing's
identity is (issue, produced commit): where a journal holds several events for
one pair the newest wins, the recorder already deduplicates on the commit, and
the counts `landing_events` beside `landings` state any duplicate the recorder's
fail-open left behind rather than collapsing it silently.

| Column | Null? | Meaning |
|---|---|---|
| `landing` | never | The landing's identity, `issue/commit` |
| `issue` | never | The issue, from the event's own `cti.issue` |
| `produced_commit` | + `produced_commit_reason` | The commit the event named as produced — full SHA. The column is `produced_commit` and not `commit` because COMMIT is SQL's own keyword and this store's names are its SQL schema verbatim |
| `gate_cause` | + `gate_cause_reason` | Which of the four gate-review causes a gate landing rode (ADR-0073 Amendment A2), carried because two causes rest on transient bars no later read reproduces; null where the diff touched no routing-class-6 path |
| `at` | never | When the event was journalled, epoch seconds |
| `relations` | never | How many objects the event touched — the count on this grain, never a substitute for counting rows in `landing_relations` |
| `boundary` | never | The marker: journalled landings only, and authorless ones named, never silently cleared |

`landing_relations` is the second grain, and the two are counted separately on
purpose — that separation is the criterion the pair exists for:

| Column | Meaning |
|---|---|
| `landing` | The landing the relation belongs to — the join key to `landings` |
| `qualifier` | The role the object played, always one of the closed qualifier set in `tools/attribute_registry.py`'s `RELATION_QUALIFIERS` |
| `object_type` | The kind of object, always one of `OBJECT_TYPES` — `dispatch` for a dispatched author, `authorship_declaration` for a declared one (#398) |
| `object_id` | The dispatch id, profile, SHA or issue number the relation names |

**Counting one event over several objects multiplies nothing.** `SELECT COUNT(*)
FROM landings` is landings; counting over a join with `landing_relations` is
relation rows; one landing touching six objects is one row there and six here,
and a reader who wants "how many objects did this landing touch" counts the
second table grouped by `landing`. An unqualified log models #329's 23 dispatches
as a loop that never existed; this pair is the shape that does not.

**The qualifier set is what makes never-alone checkable.** Author and reviewer
are distinguishable by qualifier alone, so the check is a join: reviewer profile
from `dispatches` by the reviewer relation's dispatch id, author profiles the
same way for `dispatch` objects and directly for `authorship_declaration` ones,
whose object id *is* the profile. The cookbook carries the query. A landing with
no author relation cannot be checked; it is named in the coverage block's
`landings_without_authors` and in the `boundary` column, never read as clear. A
dispatch-typed relation whose object id names no row in `dispatches` cannot be
joined to a profile either — the check could not look there, which is the
absence of evidence and never compliance (#491 round 2, finding 1) — so the
cookbook's query returns it as an `unresolvable_*` finding rather than dropping
it, and the coverage block names its landing in
`landings_with_unresolved_relations`.

**Malformed is damage, not absence.** A line that will not parse, is not this
family's event, carries a relation token whose type is outside the closed set, or
a gate cause outside the closed cause set, is counted in `malformed` and its
surviving siblings still load — the stage reader's line, one family over. A
pre-#491 line carrying no relation attributes at all parses with an empty
relation set; there are none yet, and the day one appears it reads as an absence
it is.

## The `session_period` table

One row per (session, month) (#488). The source is the status-line spool — the live
file and its rolled generations — and every derivable figure on the row is a
**period delta** of the payload's session-lifetime running totals: a period's
consumption is the difference between the cumulative totals at consecutive period
ends, and a session's first timestamped period carries its total from the session's
start. The output-token column is the one figure no row can carry — see below.

**The boundary is a column, never a footnote.** The spool is a record of interactive
sessions: the tap fires on a status-line render, the orchestrator seat renders none,
so this table omits the orchestrator's own turns — the largest non-dispatched consumer
it claims to cover — while counting the human's interactive sessions alone. The
`boundary` column says exactly that on every row, and the rebuild's `sessions` summary
line carries `orchestrator=absent`. A figure quoted from this table without its
boundary is the human's interactive spend presented as the overhead number.

| Column | Null? | Meaning |
|---|---|---|
| `session_id` | never | The session, from the payload |
| `period` | never | The month, `YYYY-MM`, from the render's own timestamp |
| `renders` | never | Timestamped renders of this session in this period |
| `last_render_at` | + `last_render_at_reason` | The period's last render — the instant the delta runs to |
| `cost_usd_list_price` | + `cost_usd_list_price_reason` | The period's delta of `cost.total_cost_usd` — **list price, not spend** (#220) |
| `duration_ms` | + `duration_ms_reason` | The period's delta of `cost.total_duration_ms` |
| `lines_added` | + `lines_added_reason` | The period's delta of `cost.total_lines_added` |
| `lines_removed` | + `lines_removed_reason` | The period's delta of `cost.total_lines_removed` |
| `output_tokens` | + `output_tokens_reason` | Always null: the payload's token keys are context-window gauges, not session-lifetime counters, so no per-period output total exists — the reason says so, never a gauge delta |
| `boundary` | never | The marker naming what this figure omits and why |

Two absences carry two different reasons: a counter no render of the session ever
carried is a ceiling of the source, and a counter present at one end of a period
boundary and missing at the other is a difference that cannot be taken. The counters
should be monotone; a delta that is not passes through raw, never clamped. The
output-token column is a third absence, and the reason it always carries names the
mechanism: every token key in the payload (`context_window.total_output_tokens`
among them) gauges the current context window — the gauge falls and rises between
renders of one session — so a delta of it is noise, and the column is absent rather
than noise-shaped.

## The `period_overhead` table

One row per period with session overhead or a landing (#488). The fully-loaded figure
is **direct plus overhead over the period's landings**, a period aggregate — and it is
**absent on every row, with the reason naming why**: the payload carries no
session-lifetime output-token counter (its token keys are context-window gauges), so
the overhead half converts to no meter the direct half shares. The direct half is the
Claude lane's five-hour-window points; the overhead half's sound figures are
list-price dollars; and dollars do not commensurate across lanes either, since
non-Claude lanes report `cost=uncalibrated`. A number that adds points to dollars is a
number in no meter at all, so the column is null with that reason rather than zero —
absent is a fact about the source, not a small value. The row still carries the same
`boundary` warning as the overhead it derives from, extended with the
direct half's own scope: it covers the Claude lane alone, and every other lane's direct
spend stays in its own unconverted meter outside the figure.

**No overhead figure is attached to an issue, structurally.** Neither session table
carries an issue column — a session-grain record names no issue, an orchestrator
session dispatches many, and dividing across them is a conversion the project's rules
forbid. A table that cannot express the apportionment is the structural form of that
rule, the way `flow_lead_time`'s column list is the structural form of "no mean".

| Column | Null? | Meaning |
|---|---|---|
| `period` | never | The month, `YYYY-MM` |
| `sessions` | never | Sessions with renders in this period |
| `renders` | never | Their renders |
| `sessions_with_cost` | never | Of those, how many carried a cost figure — partial reads stay visible |
| `cost_usd_list_price` | + `cost_usd_list_price_reason` | The period's overhead in list-price dollars — never a spend |
| `sessions_with_output` | never | Always 0 — no session can carry a derivable output total, and the constant says so |
| `output_tokens` | + `output_tokens_reason` | Always null: no session-lifetime output-token counter exists in the payload, only window gauges |
| `overhead_window_points` | + `overhead_window_points_reason` | Always null, with the same reason — no numerator exists to divide by the calibration's tokens-per-point |
| `landings` | never | Work items landed in this period, every lane |
| `direct_landings` | never | Of those, the Claude-lane landings whose cost was derivable |
| `direct_window_points` | + `direct_window_points_reason` | The Claude lane's direct cost over the period's landings |
| `fully_loaded_window_points` | + `fully_loaded_window_points_reason` | Always null, a period aggregate named but not computed: the halves share no meter, and the reason names the incommensurability — never a sum of what survived |
| `boundary` | never | The marker, extended with the direct half's lane scope |

**Periods come from timestamps, never from generation boundaries.** The spool's
rollover is not serialised (#464's review): two simultaneous rolls can drop the oldest
generation one roll early, and nothing in the surviving files records that it happened.
A generation boundary is therefore not a period boundary anywhere in this store, and a
period whose lines were lost to an early drop reads short with no signal — rare,
silent, and in the flattering direction; the hazards list carries it. What the store
can see it says: renders older than the tap's timestamps carry none, cannot be placed
in a period, and are counted in `session_renders_untimestamped` rather than summed.

## The `queue_depth` table

One row per queue per sample (#492). The source is the queue surface's own
`queue-depths.jsonl`, journalled by the sampler that folds into `just
watch-report`'s queue rung — one event per queue of the closed set, every
sample, so a queue missing from the journal is a queue that was not sampled
and never a queue that read as empty. An absent journal is zero rows: the
sampler had not run before that rebuild, and the coverage line's
`queue_depth samples=0` says so rather than refusing.

**Zero, unread and unknown are three different rows.** `state` carries which
of the three a sample is: `counted` (the depth is on the row, zero included),
`unreadable` (a source exists and that sample could not read it), and
`unrecorded` (no record anywhere carries the queue's membership — the
slot-lock queue today, whose bash seam journals nothing; a candidate-read
refusal carries its refusal kind in the raw event's `cti.queue.depth.reason`). `count` is null
everywhere except `counted`, and a null here is the honest rendering of both
non-counting states: zero belongs to a counted empty queue and to nothing
else. `oldest` and `oldest_age_s` carry the same trichotomy one level down —
`measured` where a record holds the entry instant, `none` where the queue is
empty, `unrecorded` where items wait and nothing says since when.

| Column | Null? | Meaning |
|---|---|---|
| `sampled_at` | never | The sample's own instant, as the event carried it |
| `queue` | never | Which queue, one of the registry's closed set of seven |
| `state` | never | `counted`, `unreadable` or `unrecorded` — see above |
| `count` | + `count_reason` | The depth; zero is a counted sample and null is not |
| `count_reason` | except `counted` | The state's own name for the absence, or `unrecorded: <refusal-kind>` where the candidate read refused |
| `oldest` | never | `measured`, `none` or `unrecorded` |
| `oldest_age_s` | + `oldest_age_s_reason` | Seconds the oldest item had waited |
| `oldest_age_s_reason` | except `oldest = 'measured'` | The oldest state's own name for the absence |

A line that will not parse, is not this family's event, or names a queue or a
state outside the closed sets is counted in `malformed` and its siblings still
load — the stage reader's line, one family over.

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
