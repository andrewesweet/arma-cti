# Observing the system of work: what to measure, how to capture it, and how to ask

**Question.** This project has spent thirty retros improving its own process by argument
and anecdote. What telemetry would let it improve by measurement instead — what data
points, captured how, sliced how, and read by whom?

**Answer, in one paragraph.** Capture is not the problem and has not been for weeks: an
OTel collector already runs on loopback, 626 of 639 dispatches already have a durable
per-dispatch file, and those files already carry per-request tokens, cost, duration,
model, tool decisions and the six-attribute `cti.*` identity that joins a record to a
dispatch, a seat, a lane and an issue. **Consumption is the problem.** Nothing in the
system aggregates across dispatches; the one view that would (`ledger.json`) exists on 6
of 639 records; the review journal that computes ADR-0071 ruling 6's ranking key is read
by nothing. The work is a canonical wide event per unit of work, a query layer over the
files that already exist, and a written contract so an analyst does not re-derive the
schema every time. The single largest finding is that the metric the human ranked first
— cost per landed issue — is dominated not by what a dispatch spends but by the **84% of
ruled capacity that goes unused**, and nothing measures that today except on demand.

---

## What this document is not

Three documents already cover ground this one deliberately does not repeat.

- `docs/research/agent-observability-and-cost-ledgers.md` established the collector
  mechanism, `filterprocessor`, `fileexporter` `group_by`, per-lane emission coverage,
  the four hosted candidates and `ccusage`. Its config sketch is what runs today.
- `docs/research/claude-codex-mlflow-observability-gap-analysis.md` covers Claude/Codex
  parity and the common measurement contract.
- `docs/research/mlflow-role-in-system-of-work-improvement.md` rules MLflow in as a
  derived evidence and experiment workbench and out as a controller.

This document sits one layer above all three. They answer *how do we capture agent
telemetry*. This answers *what should we measure about the work system, and how does
anyone read it afterwards*.

**One conflict, stated rather than resolved silently.** The MLflow document recommends
MLflow as the derived evidence plane. MLflow is **not installed** — absent from
`pyproject.toml`, `uv.lock`, `justfile` and `tools/`, so the recommendation stands
unadopted. Proposing a second derived plane without saying so would be the
"second copy nothing compares" shape retro 31 named as its cycle's dominant failure. The
position this document takes: **the derived store is the single canonical flattening**,
and MLflow, if ever piloted, projects from that store rather than from raw. One
flattening, two consumers. That belongs in the ADR, not in a footnote here.

---

## 1. The measured baseline

Every number below was measured on 2026-08-21 from this box. Reproduction commands are in
§9. They are the first whole-history figures the project has had; every previous
measurement of the work system was a single block or a single session.

### 1.1 What the machine actually did

Over **372.7 hours** of project wall-clock (2026-08-05T17:28Z to 2026-08-21T06:09Z), across
**639 dispatches** touching **188 issues**:

| Measure | Value |
|---|---|
| Dispatched agent-hours delivered | 179.2 |
| Wall minutes with **at least one** agent running | 7,510 of 22,361 — **33.6%** |
| Mean concurrency across the window | **0.48** |
| Capacity at the ruled WIP of 3 | 67,083 agent-minutes |
| Used | 10,753 — **16.0%** |
| **Lost** | 56,330 — **84.0%** |
| Total idle time, in gaps | **251.8 hours across 254 gaps** |
| Longest single gap | **16 h 27 m** (2026-08-10T21:58Z → 08-11T14:25Z) |

Concurrency histogram, in minutes at each level: **1 agent → 5,209 · 2 → 1,629 · 3 → 461 ·
4 → 152 · 5 → 59**.

This extends `docs/research/dispatch-cost-and-occupancy.md`, which measured one
191-minute block at 70.1% loss and mean occupancy 1.50/5. Over the whole history the loss
is **84.0%** and mean concurrency is **0.48**. The block was not unrepresentative; it was
better than average, because it was awake.

### 1.2 Per-dispatch shape

Median and p90 wall-clock minutes per dispatch, by seat and by lane, over the 626
dispatches carrying both timestamps:

| Seat | n | median | p90 | max | total h |
|---|---|---|---|---|---|
| implementer | 339 | 17.6 | 43.4 | 121.2 | 122.6 |
| review | 245 | 8.2 | 17.0 | 42.3 | 38.7 |
| mechanical | 16 | 3.1 | 10.6 | 16.9 | 1.4 |
| fable | 10 | 18.5 | 25.6 | 40.1 | 3.4 |
| retro | 10 | 12.3 | 16.9 | 18.0 | 2.1 |
| recon | 5 | 0.9 | — | 8.6 | 0.3 |
| planner | 1 | 5.9 | — | 5.9 | 0.1 |

| Lane | n | median | p90 | max | total h |
|---|---|---|---|---|---|
| claude-native | 312 | 11.2 | 29.5 | 121.2 | 78.3 |
| codex | 162 | 8.5 | 18.2 | 29.9 | 26.1 |
| zai | 152 | 20.5 | 51.1 | 111.0 | 64.1 |

Outcomes by lane: `claude-native` 303 ok / 8 unclassified / 10 absent; `codex` 158 ok / 4
unclassified / 4 absent; `zai` 135 ok / **13 `quota_exhausted`** / 4 unclassified.

### 1.3 Cost per landed issue is computable today

Built as a throwaway extractor over the per-dispatch sinks, joined to `dispatch.json` and
to commits on `origin/main` that reference the issue:

| Lane | Landed issues | Output tokens | Per issue | Plan points per issue |
|---|---|---|---|---|
| claude-native | 111 | 11,024,812 | 99,323 | **3.29 pp₅ₕ** |
| zai | 86 | 6,587,710 | 76,601 | no calibration exists |
| codex | — | — | — | see below |

The Claude figure uses #218's calibration of 30,209 output tokens per 1% of a five-hour
window. z.ai and Codex have no calibration, and per ADR-0071 ruling 6 and #317 these are
**never summed**.

**The first extractor booked Codex at zero, and it looked like it worked.** Claude emits
token counts on `claude_code.api_request` **log records**; Codex emits
`codex.turn.token_usage` as a **histogram metric** with a `token_type` attribute. A
log-only reader silently returns nothing for an entire lane. This is precisely the
"reading meter silence as free" error #220 prohibits, reproduced by accident within an
hour of designing against it. It is recorded here as a named hazard, not a footnote,
because the failure is invisible: the query runs, returns rows, and omits a third of the
fleet.

### 1.4 Where time goes inside a dispatch

From the trace pipeline, which has been live since 2026-08-18 and covers the Claude lane
only:

| Span | n | total hours | mean |
|---|---|---|---|
| `claude_code.interaction` (root turn) | 176 | 50.79 | 17 m 19 s |
| `claude_code.llm_request` | 8,745 | 29.39 | 12.1 s |
| `claude_code.tool` | 10,161 | 21.27 | 7.5 s |
| `claude_code.tool.execution` | 8,976 | 20.91 | 8.4 s |
| `claude_code.tool.blocked_on_user` | 10,162 | **0.36** | 127 ms |

So inside a dispatched turn, time splits roughly **58% inference, 41% tool execution**.
And **permission prompts are not a cost** — 10,162 blocking spans totalling 21 minutes
across the whole corpus. That hypothesis is now dead, measured, for the price of one
query.

### 1.5 Flow metrics, for the first time

From 475 issues, 353 closed:

- Lead time, open to close: **p50 7.2 h · p70 24.6 h · p85 54.7 h · p95 117.1 h · max 258 h**.
- **69%** close within a day; **90%** within three.
- Throughput: **16.0 closes/day** mean over 22 active days, ranging 1 to 41.

### 1.6 The ruled ranking key is near-degenerate

ADR-0071 ruling 6 ranks on **fix rounds per landing**. Its inputs exist and are readable:
`~/.arma-cti/review/journal.jsonl` holds 37 `cti.review.round` events and 43
`cti.review.dispute` events; the 28 `loop.json` files hold 58 findings — 42 medium, 16
low — with adjudication routes 40 `accepted_and_filed`, 3 `fixed`, 15 unadjudicated.

The distribution of rounds per issue is **22 issues at 0, four at 1, one at 2, one at 3**.
Median zero. The problem is not sample size, which ruling 6 anticipated and required be
stated as an estimate; it is that **the key barely varies**, so it cannot separate
profiles no matter how long it runs at this rate.

A companion measure with real variance already exists: **dispatches per issue**, across
188 issues — 79 issues took one dispatch, 39 took two, and the distribution has a long
tail to #329 at 23. Proposed below as a reported, unranked companion. The ruled key stays
the ruled key; ranking on a different one would be a ruling, not a preference.

### 1.7 Capture coverage, and its holes

| Lane | dispatches | with a durable sink | with token records |
|---|---|---|---|
| claude-native | 321 | 314 | 313 |
| codex | 166 | 160 | 158 |
| zai | 152 | 152 | 149 |

Four lines across four files are **truncated JSON**, consistent with a flush racing a
write. Small, but a naive reader dies on the first one — the benchmark written for this
document did exactly that.

Three structural holes, each provable by absence:

1. **This project emits no spans and no metrics of its own.** All six bespoke `cti.*`
   event families are log records posted to `/v1/logs`. There is no span for a dispatch, a
   gate run or a review round.
2. **No gate leg records pass or fail.** Gate outcome is inferred from git, so a green
   gate that never landed is invisible. `gate_clock` times `unit` and `fast` only.
3. **The spend estimator is unfalsified.** Every `cap_fraction.observed` is hardcoded
   `null` from a map nothing populates, and `ccusage` is not installed.

---

## 2. The frameworks, and what each one asks for

### 2.1 Technical observability

The findings below are from the OpenTelemetry specifications and the observability
literature; sources are listed in §10.

**The decision rule for span versus metric versus log.** No single OTel page states it;
it follows from the three data models. Emit a **span** when the thing has a start, an end
and a causal position in a larger operation. Emit a **metric** only for a question asked
repeatedly over time with bounded dimensions, that must be answered without a scan. Emit
a **log or event** for a discrete fact with no duration, or a wide record to be sliced
later on high-cardinality fields.

The corollary decides most of this design: **metrics can be derived from events at query
time; events cannot be derived from metrics.** With files and a SQL engine, a metric buys
nothing that a `GROUP BY` does not, at full cardinality, retroactively. So: **emit no
metrics of our own yet.** Add one only when something must be answered on a live surface
without a scan.

**Wide structured events are the recommended primitive.** Majors' framing — one source of
truth, arbitrarily wide structured events, from which metrics, traces and SLOs are all
*derived* — matches this project's constraints exactly, because the cost argument against
it (storing the same data in three pillars) does not apply to local files, and the cost
argument *for* it (engineers' time spent below the value line) is the whole of the
problem here. Leach's "canonical log lines" is the same idea a layer down: one wide record
emitted at the end of a unit of work, carrying every dimension anyone might slice on.

**This project already has the shape and does not know it.** `just ledger-sync` is a
canonical-log-line materialiser. Framing it that way says what to do — **add dimensions to
it** — rather than what to build beside it.

**Long spans are the wrong instrument here.** OpenTelemetry has no answer for spans that
outlive their process: a span is exported only at `End()`, so an hour-long span is
invisible until it finishes and is **lost entirely if the process dies**. This project
plans for agents dying — `flock` releases on holder death, ADR-0022 — so a single
`invoke_agent` span per dispatch would be absent in exactly the cases most worth
investigating. The alternative is a **pair of events**: `cti.dispatch.started` and
`cti.dispatch.finished` sharing a dispatch id, with duration computed in SQL. A missing
`finished` is then *itself the stall signal*, which is what `just watch` exists to detect
and what a lost span can never provide.

**Trace context can cross a process boundary, and probably will not here.** The
Environment Variables as Context Propagation Carriers spec (Release Candidate) defines
`TRACEPARENT`/`TRACESTATE` as env carriers; the parent copies its environment, injects,
and spawns. But nothing extracts automatically, and any process this project does not
control — Claude Code, Codex — will not join unless it implements extraction. Claude Code
documents `CLAUDE_CODE_PROPAGATE_TRACEPARENT`, but as outbound propagation through
proxies, not ingestion. **Treat "Claude Code joins my trace" as unverified**; the cheap
test is to set `TRACEPARENT` in a dispatch environment and check whether the emitted
`claude_code.interaction` span carries our trace id. Until then the join key does the
work: **`cti.dispatch_id` is load-bearing and a span link is a nicety.**

**Semantic conventions exist for exactly this domain and are cheap to adopt now.** The
GenAI conventions moved to `open-telemetry/semantic-conventions-genai`; everything
`gen_ai.*` is Development, so alignment is cheap today and expensive later. The mapping
that fits this project's vocabulary:

| Concept here | Convention |
|---|---|
| seat | `gen_ai.agent.name` |
| dispatched run | `invoke_agent {seat}`, `gen_ai.operation.name=invoke_agent` |
| lane | `gen_ai.provider.name` (`anthropic`; `zai` documented as system-specific) |
| model | `gen_ai.request.model` / `gen_ai.response.model` |
| tokens | `gen_ai.usage.input_tokens`, `.output_tokens`, `.cache_read.input_tokens`, `.cache_write.input_tokens` |
| tool call | `execute_tool` span, `gen_ai.tool.name` |
| effort, profile, issue, dispatch id, worktree | **no convention exists** → `cti.*` |

Naming rules that bind: custom attributes use a unique prefix, and it is *not
recommended* to nest them under an existing convention namespace — so `cti.*` is correct
and `gen_ai.cti.*` is not. `otel.*` is reserved.

**Cardinality is a metric problem and not a trace problem.** Each distinct attribute set
on a metric is a separate series; the SDK's default aggregation cardinality limit is
2,000, and on overflow it emits `otel.metric.overflow=true` **and silently loses data**.
Spans and logs have no such limit — a dispatch id, a SHA, a worktree path all belong on
spans and events and never on a metric attribute. Worth knowing: Claude Code's
`OTEL_METRICS_INCLUDE_SESSION_ID` defaults true, which puts a per-session UUID on every
metric. Survivable at this volume, but it is the highest-cardinality choice in the current
pipeline and it was defaulted into rather than chosen.

**RED and USE both apply, to different things.** RED — Rate, Errors, Duration — is for
services and maps onto dispatches (rate per seat and lane, error rate by failure class,
duration distribution) and onto gate runs, where `just gate-clock-history` is already RED
with the R and E missing. USE — Utilization, Saturation, Errors — is for resources, and the
regression slot pool is the one genuine finite resource in this system: utilisation is the
fraction of wall time a slot lock is held, saturation is queue depth at `--wait`,
errors are `infra_unavailable` acquires. That is currently unmeasured. **Neither framework
says anything about whether an answer was correct**, which is the observatory's problem
and not one telemetry closes.

**Governance has a published vocabulary worth borrowing.** Requirement levels — Required,
Conditionally Required, Recommended, Opt-In — are the right words for deciding whether an
attribute goes on an event. Deprecation practice is absolute: *attributes are never
removed, only deprecated*, because an archive is permanent and a rename silently breaks
every historical query. Schema URLs date every record so a query written today knows which
attribute spelling an old file used.

### 2.2 Business process observability

The work-system half of the literature turns out to be the more useful of the two, because
it names the fields this project is missing rather than the transport it already has.

**Process mining sets the floor, and this project sits below it.** The Process Mining
Manifesto's minimum minable log is **case id plus activity**, with **timestamp** making
anything about time computable and **resource** making organisational analysis possible.
The XES standard adds one more field that everyone skips and then regrets:
`lifecycle:transition` — `start`/`complete`/`abort`/`suspend`/`resume`. Without a paired
start and complete you cannot separate **service time from waiting time**, which is the
single most valuable derived quantity available here.

The Manifesto grades logs one to five stars and rules that mining is only trustworthy at
three or above. **This project is at two stars**: events are recorded automatically but as
a by-product of other systems, coverage varies, and — the defining property of a two-star
log — *it is possible to bypass the system*. An interactive session that lands work leaves
no dispatch record at all, which is exactly why `just review-loop author --profile P` had
to be invented. Reaching four stars needs one explicit emitter, a declared case notion, and
no path that produces work without producing events.

Its second guideline, GP2, is *"Log Extraction Should Be Driven by Questions"*, and its
worked example is this project's problem a decade early: orders, order lines and deliveries
in many-to-many relationships, where one may extract data to describe the life-cycle of any
of the three. Substitute issue, dispatch, commit and review round.

**Object-centric logs exist because forcing one case id causes two named pathologies**, and
this project would hit both. *Convergence*: one real event duplicated across many cases
because it touches several objects — one `just land` run that closes an issue, lands a gate
diff and updates the changelog. *Divergence*: unrelated instances of one activity collapsed
into a single case, so a discovered model invents ordering that does not exist — issue #329
with 23 dispatches and eleven gate runs would be modelled as a loop it never had. OCEL 2.0
adds three things worth having: **object-to-object relations** (commit produced-by dispatch,
dispatch works-on issue), **time-varying object attributes** so "what was the lane's breaker
state at the moment this was refused" is answerable without reconstruction, and
**qualifiers** on relations, which is how one landing event distinguishes the *author*
dispatch from the *reviewing* dispatch. Without qualifiers, `gate_review=cross_lane` is not
checkable from the log.

**And conformance checking is the capability this project would use most.** The Manifesto is
explicit that it applies "to procedural models, organizational models, declarative process
models, business rules/policies, laws". Every rule in `AGENTS.md` — never-alone, review
resolving away from the author's profile, `gate_review` being one of exactly four values, no
dispatched session writing to `.claude/`, `just land` re-gating after rebase — is a
declarative model that a log can be checked against. Alignment-based conformance says not
merely that a violation occurred but *where in the trace* rule and reality diverged. That is
a different and better answer than a counter reading zero.

**Flow metrics supply the one leading indicator in the set.** The Kanban Guide's four are
WIP, throughput as an exact count of items, cycle time, and **work item age** — the elapsed
time between start and *now*, computed on unfinished work. Cycle time is lagging: it is
known only after intervention was possible. Age is the same quantity while intervention
still helps, and the operational rule is to plot every open item's age against the
historical percentile band. Measured here: p85 lead time is 54.7 hours, so an item at 60
hours is the one to act on. This is a better stall detector than a fixed-timeout watcher
because the threshold comes from the project's own distribution rather than a guess.

**Little's Law is a stability test, not a forecast**, and this system fails one of its
assumptions structurally. The Law requires that all work started completes and exits;
`infra_unavailable`, `quota_exhausted` and `provider_refused` are all work started that did
not complete and is explicitly not a result. Counting them as WIP inflates cycle time
without bound; dropping them silently understates WIP. The correct treatment is a **third
terminal state — `abandoned`, with its class** — excluded from cycle-time distributions and
counted separately as a yield loss. This project already has the vocabulary; it has never
had the state.

**Flow efficiency is touch time over elapsed time**, and this system can compute it exactly
where most cannot: touch time is dispatch wall-clock while a session is actually running,
and everything else is wait. Typical software teams land at 15–40%. The measured figures in
§1.1 imply this project's number is low and dominated by two arcs — waiting for the human,
and waiting for a lane to reopen. Which is why the field that matters most is one that does
not exist anywhere today: **`block_reason` on every wait interval**, distinguishing
`waiting_human` from `lane_peak_band` from `quota_exhausted` from `waiting_reviewer` from
`wip_limit`. Without it, wait time is one undifferentiated number and two opposite
interventions look identical.

**DORA transfers almost intact with one substitution**: *deployment* becomes `just land` to
`origin/main`. Deployment frequency is lands per day; change lead time is first commit to
landed SHA; change fail rate has an unusually crisp proxy in a land followed within a window
by a revert, a hotfix, or a red gate on `main`. Two findings from DORA's own research bear
on a project that is 100% AI-authored: in 2024, each 25% increase in AI adoption associated
with roughly a **1.5% drop in throughput and a 7.2% drop in stability**; in 2025 the
throughput correlation **flipped positive while stability did not recover** — "speed without
stability". That is the empirical justification for this project's gate discipline, and it
is a hypothesis its own telemetry can test at n=1 with adoption pinned at 100%.

**SPACE's rules are worth importing; three of its five dimensions are not.** The framework
requires metrics across **at least three dimensions**, forbids stacking several from one
dimension, and insists at least one be perceptual. Satisfaction, most of collaboration and
the perceptual half of efficiency are survey instruments aimed at humans. The honest
adaptation is to apply the S dimension to **the one human, n=1** — one weekly question about
perceived ease of landing a change is legitimate and cheap. **Inventing a survey for an LLM
and treating its self-report as a perceptual measure would be the token-versus-thing error
#458 already names.**

**DevEx supplies the best analogue in the literature for an LLM workforce.** Its three
dimensions map unusually well. *Feedback loops* are gate duration — and the framework's
claim is that this is a work-quality metric, not a cost metric: a 12-minute gate and a
40-minute gate produce different code, not merely later code. *Cognitive load* is **context
budget**, and it is measurable exactly: prompt tokens before the first tool call, files
opened before the first edit, and the number of places a rule is stated — `just
check-arbiter` is already a cognitive-load instrument and was never framed as one. DevEx
finds cognitive load the highest-leverage intervention for humans; the argument is stronger
for workers whose context is a hard finite resource with measurable degradation. *Flow
state* has a real analogue too: **interruptions per dispatch** — hook denials, permission
refusals, typed refusals, stale-copy false positives, each classified. A dispatch hitting
four hook denials before useful work is the agent equivalent of four meetings before lunch,
and #254's whole filed diagnosis dissolved into one such interruption.

**Statistical process control is the right statistics for samples of this size**, and that
is not a compromise — it is the design point. An XmR chart's limits come from a baseline
that "may have as few as four points", twelve preferred, computed as
`X̄ ± 2.660 × mR̄`. Three-sigma limits are chosen on economic grounds rather than a
normality claim, which is why they work on skewed data like cycle times. Four practices
follow and all four matter here:

- **Rule One only** — a point outside the limits. Wheeler's own recommendation, because
  extra rules "shift the balance toward more false alarms in order to find smaller signals"
  and produce charts that are "an unending nag which you must ignore in self-defense". For a
  system whose consumer is an autonomous loop, this is close to a hard constraint.
- **Freeze the limits** at the baseline and plot later points against them. Recomputing as
  data arrives is how a real shift gets absorbed into the limits and disappears.
- **Stratify before charting.** Wheeler's camshaft case — three parallel processes
  interleaved in time order, whose moving ranges measured between-process differences and
  went blind to within-process signals — is exactly what charting three lanes' dispatches in
  one series would do. One chart per lane, or per lane and seat.
- **Exclude not-a-result classes** from the value chart and chart them separately as counts.
  They are not process output, and including them inflates `mR̄` and blinds the chart.

**Queueing theory explains the 84%, and says the fix is not more capacity.** Kingman's
formula puts mean wait at `ρ/(1−ρ) × (c_a²+c_s²)/2 × τ`: going from 80% to 90% utilisation
**more than doubles** wait for no extra work delivered, and variability is a *linear*
multiplier on all of it — so predictable dispatches are worth more than fast ones.
Reinertsen's Q1 is the principle that names this project's real problem: **"Product
development inventory is physically and financially invisible."** An issue sitting behind a
WIP limit, a branch pushed to `refs/heads/issue-N` awaiting a reviewer, a finding filed and
unadjudicated — none of these appear anywhere unless deliberately counted. **Counting them
is most of the job.** And his operational claim inverts the usual instinct: *"if you want to
control cycle time you do not measure cycle time, you measure queue size"*, because queue
size leads and cycle time follows.

One peculiarity is worth stating because the standard model does not fit. **A lane is not a
server that slows under load; it is a server with scheduled unavailability and a hard
capacity cap** — closer to a vacation queue or token bucket. Within a window Kingman
applies; across windows the dominant delay is deterministic window wait. So the useful lane
metric is not utilisation but **burn rate against window remaining**, giving a projected
exhaustion time. And Reinertsen's Q6 is a live risk here: pushing lanes toward exhaustion
raises refusal rates, turns dispatches into not-a-result, forces re-dispatch, and therefore
**increases service-time variability** — which by Kingman multiplies the wait already being
suffered. High utilisation of a quota lane does not merely slow the system; it makes it
erratic.

The human is the constraint in the Theory-of-Constraints sense — an M/M/1 server with
utilisation near one and a very long service time — and every
`human_ruling_requested → human_ruling_given` interval is constraint time that should be
measured separately from everything else.

**Rework has two metrics this project should adopt, and one empirical finding it should
read carefully.** *Rolled Throughput Yield* is the product of each stage's first-pass yield:
five stages at 90% each is **59%**, so every stage can look healthy while four issues in ten
need rework somewhere. The stages here are brief, implementation, own gate, cross-lane
review, land. *Defect Removal Efficiency* is defects found before release over all defects
found, **measured over a stated window** — Jones uses 90 days, ISBSG 30, and a DRE without
its window compares to nothing.

Jones's table across more than 13,000 projects is the finding that bears hardest on this
project's architecture: **formal inspections remove 85% of defects on average; most forms of
testing remove under 50%**, with unit testing at 40%, regression testing at 35% and system
testing at 42%. His conclusion is that inspections plus static analysis plus testing is "the
only known way of achieving cumulative defect removal levels higher than 95%", and that a
four-stage test pipeline with no inspections caps out near 85% — which he calls "something
of a professional embarrassment". Read against this system: **the cross-lane never-alone
review is the inspection line and is the highest-yield mechanism available**, the gates are
the test lines, and the data supports the existing rule against adding further verification
passes rather than improving the review lens. His other number is a checkable claim about
this repository: **7% of defect repairs introduce a new defect**.

**And the natural experiment is already running.** Every gate landing prints `gate_review=`
as one of four causes — `cross_lane`, `lane_exhausted`, `lane_barred`, `same_lane_chosen`.
That is the independent variable of a comparison between cross-lane and same-lane review
effectiveness, being recorded already, on the project's own strongest process claim. The
dependent variable is escaped defects per landing within a stated window. Nothing needs to
be built to start collecting it beyond the window and the escape channel.

---

## 3. The proposed design

Four pieces. Each is independently useful, and they are ordered so that stopping after
any one of them leaves something that works.

### 3.1 A canonical wide event per unit of work

Four units of work, four event families, each a single OTLP log record with `EventName`
set — following the existing `tools/otel_event.py` dual-write pattern, which posts to the
collector and appends to a local journal carrying `exported` and `export_detail`, so the
journal is durable and the collector is the query path.

| Event | Emitted when | Carries |
|---|---|---|
| `cti.dispatch.started` | `just dispatch` mints an id | identity, seat, lane, profile, model, effort, issue, worktree, base SHA, route, strata, breaker state at dispatch, plan charge |
| `cti.dispatch.finished` | the runner writes `result.json` | outcome, failure class, returncode, killed-by, wall seconds, token totals per class, per-lane spend in that lane's meter |
| `cti.gate.finished` | every gate recipe, not just `unit` and `fast` | recipe, **per-leg pass/fail**, wall seconds, head SHA, tests collected, load, foreign gate processes |
| `cti.landing.finished` | `just land` completes or refuses | issue, SHA, refusal class if any, `gate_review=` cause, review verdict identity, declared author if any |

The paired started/finished shape is deliberate and is the design's load-bearing choice:
**a missing `finished` is the stall signal**, it survives the agent being killed, and it
needs no long-lived span. It is also XES's `lifecycle:transition` under another name, which
is what makes service time separable from waiting time at all.

Three of the four are close to free — `dispatch.py`, `land.py` and `gate_clock.py`
already compute everything listed. `cti.gate.finished` is the one that needs new
information: **no gate leg currently records whether it passed**, which is why a green
gate that never landed is invisible today.

Four fields do not exist anywhere today and are what the process literature says the log is
missing. They cost a column each.

- **`block_reason`** on every wait interval — `waiting_human`, `lane_peak_band`,
  `quota_exhausted`, `breaker_open`, `waiting_reviewer`, `worktree_occupied`, `wip_limit`,
  `slot_unavailable`. Without it, wait time is one undifferentiated number and two opposite
  interventions are indistinguishable. This is the highest-value single field in the design.
- **An `abandoned` terminal state, with its class.** Little's Law assumes all started work
  completes; `infra_unavailable`, `quota_exhausted` and `provider_refused` are work that
  started and explicitly is not a result. Counting them as WIP inflates cycle time without
  bound; dropping them understates it. A third terminal state is the correct treatment, and
  it doubles as the yield-loss numerator.
- **Qualified object relations** — an event names the objects it touches and *in what role*:
  `subject`, `author`, `reviewer`, `produced`, `consumed`, `occupied`, `blocked_by`. This is
  what makes `gate_review=cross_lane` checkable from the log rather than believed from a
  printed line, and what stops one `just land` event being duplicated across three cases.
- **`first_pass`** — whether this stage was reached without rework. One boolean per stage
  transition yields first-pass yield per stage and rolled throughput yield for the pipeline.

A fifth observation has no natural event because nothing happens: **queue depth**. An issue
behind the WIP limit, a branch awaiting a reviewer, a finding filed and unadjudicated are
invisible inventory, and a periodic depth sample per queue is the only way to see them.

### 3.2 One identity, stated once

`cti.dispatch_id` already joins a record to a dispatch, seat, lane, profile, issue and base
SHA, injected into `OTEL_RESOURCE_ATTRIBUTES` per invocation. It stays the spine. Two
additions:

- **Non-dispatched sessions get an identity too.** The orchestrator's own turns and the
  human's interactive sessions carry no dispatch id and reach no row, which is why nobody
  knows what the orchestration seat consumes. The status-line spool already captures
  per-session cost, tokens, duration, lines changed, model, effort and `session_id` for
  **every** session — 6,043 lines of it, read today only for `rate_limits`. #464 made it
  keep generations rather than destroying its history on every roll. It needs a timestamp,
  which it currently lacks entirely.
- **Attribute names live in one registry.** One file listing every `cti.*` name with a
  requirement level and a one-line reason, in the shape of `SEATS` in `tools/dispatch.py`
  — names in one place, never typed by hand into a surface. A `just check` leg asserting
  that every emitted attribute appears in the registry is mechanical and prevents exactly
  the drift `just check-arbiter` exists to catch elsewhere.

### 3.3 A derived store, rebuilt rather than migrated

A full rebuild from the immutable JSONL sources on every run, so the store is a cache and
never a source of truth. **Measured: 591 files, 618 MB, 59,682 lines, 279,823 OTel records
parse in 3.3 seconds** in unoptimised Python. At the current ~1 GB/fortnight and a 90-day
retention, a rebuild lands near 20 seconds. Rebuild cost is not a design constraint, which
means schema changes are re-runs rather than migrations — and this schema will change
repeatedly in its first month.

Two consumers, one flattening:

- **The big store** under `~/.arma-cti/`, outside every worktree, like all other evidence.
- **A small committed per-issue summary** — one row per landed issue: cost in its lane's
  meter, rounds, dispatches, duration, lanes involved. It survives box death, diffs in
  review, and gives an analyst a cheap first read. Written by the same tool, never by hand.
  `docs/process-log.md` is the precedent: the project's only longitudinal record is
  committed prose, and it is committed for good reasons that apply here too.

DuckDB is the query engine, over `read_json` views. The `otlp` community extension exists
and matches this use case, but it is early-stage, single-node, caps file reads at 100 MB
and has already broken its schema between minor versions — so a hand-rolled flattening of
about thirty lines of SQL is the smaller liability, with the extension as an optional
accelerator.

### 3.4 The analyst's contract

The mission's actual requirement: *future analytical agents should not work from first
principles each time*. That needs three written things, and they are the cheapest part of
this proposal.

1. **A schema reference** — every table, every column, what it means, which source file it
   came from, and which columns are nullable *and why* the null exists.
2. **A worked-query cookbook** — the ten questions that have actually been asked in retros,
   each with its SQL. Cost per landed issue by lane. Occupancy over a window. Rounds per
   landing by profile. Gate duration trend against its anchor. Lead time percentiles.
   Dispatches per issue. Failure class rates by lane. Idle gaps over N minutes. Spend by
   seat. Tool-time versus inference-time inside a dispatch.
3. **A hazards list**, and this is the part that earns its keep. Every trap this document
   hit while measuring: Codex tokens are metrics not logs, and a log-only reader books a
   lane at zero; four lines of the archive are truncated JSON and a naive parser dies on
   the first; `cap_fraction.observed` is always null and `0.0` there would be a lie; the
   statusline spool has no timestamp and is ordered only by line position; spans exist
   only from 2026-08-18 and only on the Claude lane; `dispatch_only` attribution means
   totals exclude the orchestrator.

---

## 4. Guidelines for future work

Proposed as the durable rule this document contributes, in the form a `CLAUDE.md` or ADR
sentence would take.

**When to add telemetry.** Add a **dimension to an existing wide event** when a question
was asked that could not be answered — that is nearly always the right move, it is one
column, and it is retroactive from the moment it lands. Add a **new event family** only
when no existing event's lifetime contains the thing being measured. Add a **metric** only
when a live surface must answer without a scan. Never add a signal speculatively: an
unread signal is indistinguishable from an absent one and costs a maintenance obligation.

**What every new feature owes.** A landing that adds a unit of work — a new seat, a new
gate recipe, a new lifecycle state — adds that unit's start and finish events in the same
commit. This is the existing convention that a rule lands with its first applied instance,
applied to telemetry.

**How to spell it.** Reuse `gen_ai.*` where a convention exists; use `cti.*` where none
does; never nest one inside the other. Register the name with a requirement level and a
reason. **Never delete or repurpose an attribute name** — deprecate it and keep it
readable, because the archive is permanent and a silent rename breaks every historical
query written before it.

**What a signal must never do.** Report, never route. Nothing derived from this telemetry
excludes a profile, reroutes work or trips a breaker. That is ADR-0071 ruling 6's
constraint and it is reaffirmed rather than restated: the dropped admission bar is the
worked example of a measurement given authority it could not carry, and it never
adjudicated once across 24 routes.

**What a signal must always do.** Distinguish absence from zero, with a reason code. Every
existing writer in this project already does this and it is why its data is worth
querying at all.

---

## 5. What to measure first

Ranked. The human held no prior view, so this is a proposal with its reasoning attached.

**1. Occupancy, and the overnight gap in particular.** 84.0% of ruled capacity is lost;
251.8 hours sit in 254 gaps; the longest is 16.5 hours. This dwarfs everything else in
this document by two orders of magnitude. #295 diagnosed the cohort barrier, landed the
fix, and said plainly that the prospective arm "is the seat's, and it is not run here" —
with numbers to beat of mean occupancy 1.50/5 and 669 lost agent-minutes. **That
measurement has never been taken**, the instrument already exists (`just occupancy`), and
it is the cheapest real result available. The cohort barrier accounts for 292 agent-minutes;
the overnight gaps are far larger and nothing has diagnosed them.

**2. Rework, with a companion that has variance.** The ruled key is right and nearly
static — 22 of 28 issues at round zero. Dispatches per issue, across 188 issues with a tail
to 23, is the measure that can actually move under an intervention. Report both; rank only
the ruled one.

**3. Gate duration, continued.** #446 found a 2× regression that ran two weeks unnoticed
and had no guilty commit, findable only because Claude Code's transcripts happen to carry
a timestamp — "an accident of the harness, not a record this project keeps". `gate_clock`
now keeps it, for two recipes, with 111 rows. Extending it to every recipe and adding
per-leg pass/fail is small and closes the blind spot that produced the finding.

**4. Cross-lane versus same-lane review effectiveness — the natural experiment already
running.** Every gate landing prints `gate_review=` as one of four causes, so the
independent variable of the project's strongest process claim is being recorded today. What
is missing is the dependent variable: escaped defects per landing, within a **stated
window**, with an escape channel. Capers Jones's data says formal inspection removes ~85% of
defects against under 50% for most testing, so this is the highest-yield mechanism in the
system and it has never been checked against its own record.

**5. Aging work-in-progress, as a replacement for fixed-timeout watching.** Cycle time is
known only after intervention was possible; item age is the same quantity while it still
helps. The p85 lead time measured here is 54.7 hours, which is a threshold derived from this
project's own distribution rather than guessed — unlike every timeout in the watcher today.

**Deliberately not first: per-dispatch efficiency.** Brief size, prompt compression and
scaffolding overhead have been measured repeatedly and found small — the 837-token brief
was at most 5 of 669 lost agent-minutes. Optimising the 16% that is used, while 84% goes
unused, is the wrong end of the problem. Kingman's formula sharpens the point: at low
utilisation, shaving service time barely moves total time in system, because the queue term
dominates.

**Deliberately not built: a dashboard.** Nothing above needs one. Control charts want to be
a static image per stratum regenerated by a recipe; process models want to be opened when
there is a question. And `docs/agents/orchestration.md` already rules that the orchestrator's
turn-top read is a verdict and never a dashboard of numbers.

---

## 6. What this can never measure

Stated because ruling 6 requires it and because the honest list is short.

- **Never-alone's benefit.** Defects prevented has no counterfactual and no control arm.
  The one observable proxy is post-landing findings on landings that passed pre-landing
  review, and that is all the evidence this design will ever produce.
- **Whether an answer was correct.** RED tells you a lane is slow, never that it is wrong.
- **Causal attribution between overlapping fixes.** Retro 18 already recorded this: when
  two changes are live in one cycle, which one moved the behaviour is not separable, and
  usually does not need to be.
- **Containment.** A bypassed hook leaves no durable fact, so the column is either backed
  by a record that does not yet exist, or absent. An empty column would be read as
  evidence that bypasses did not occur, which is worse than no column.
- **Cross-lane spend as one number.** Three meters that do not convert. Reported per lane,
  never summed, and the conversion is refused rather than deferred.

---

## 7. Open questions

1. **Does Claude Code ingest `TRACEPARENT` from its environment?** Undetermined. The test
   is one dispatch with the variable set and one query for the trace id.
2. **What causes the overnight gaps?** Measured at 251.8 hours; undiagnosed. The cohort
   barrier explains 292 minutes of it.
3. **Would z.ai and Codex calibrations be worth their cost?** #237's calibration run cost
   about 2.5 plan points against 10 budgeted. Until both exist, cross-lane cost per landed
   issue is not computable and must not be synthesised.
4. **Does `OTEL_METRICS_INCLUDE_RESOURCE_ATTRIBUTES` change what the metric leg carries?**
   Metrics do reach the per-dispatch files, so resource attributes are evidently present;
   whether datapoint-level copies would add anything is unverified.

---

## 8. Reproduction

```sh
# Occupancy and idle gaps over the whole history (§1.1)
#   reads ~/.arma-cti/dispatches/*/result.json

# Per-dispatch shape by seat and lane (§1.2)
#   reads ~/.arma-cti/dispatches/*/{dispatch,result}.json

# Cost per landed issue (§1.3)
#   reads /var/log/claude-otel/dispatches/dispatch-*.jsonl
#   MUST read both log records (Claude) and histogram metrics (Codex)
#   joins to `git log origin/main` for landing

# Span time decomposition (§1.4)
#   reads resourceSpans in the same sinks; Claude lane only, from 2026-08-18

# Lead time and throughput (§1.5)
#   gh issue list --state all --limit 500 --json number,createdAt,closedAt

# Review rounds (§1.6)
#   reads ~/.arma-cti/review/journal.jsonl and ~/.arma-cti/review/*/loop.json
```

The scripts these came from were throwaway. That is the point of §3.3: they should not
have been, and the next analyst should inherit views rather than rewrite them.

---

## 9. Sources

**OpenTelemetry specifications.** [Trace API](https://opentelemetry.io/docs/specs/otel/trace/api/) ·
[Traces concepts](https://opentelemetry.io/docs/concepts/signals/traces/) ·
[Metrics data model](https://opentelemetry.io/docs/specs/otel/metrics/data-model/) ·
[Metrics SDK](https://opentelemetry.io/docs/specs/otel/metrics/sdk/) ·
[Instrument selection](https://opentelemetry.io/docs/specs/otel/metrics/supplementary-guidelines/) ·
[Logs data model](https://opentelemetry.io/docs/specs/otel/logs/data-model/) ·
[Env-var context carriers](https://opentelemetry.io/docs/specs/otel/context/env-carriers/) ·
[W3C Trace Context](https://www.w3.org/TR/trace-context/) ·
[SDK env vars](https://opentelemetry.io/docs/specs/otel/configuration/sdk-environment-variables/) ·
[OTLP File Exporter](https://opentelemetry.io/docs/specs/otel/protocol/file-exporter/) ·
[Semconv naming](https://opentelemetry.io/docs/specs/semconv/general/naming/) ·
[Attribute requirement levels](https://opentelemetry.io/docs/specs/semconv/general/attribute-requirement-level/) ·
[Telemetry schemas](https://opentelemetry.io/docs/specs/otel/schemas/)

**GenAI semantic conventions**, moved repo. [Spans](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-spans.md) ·
[Agent spans](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md) ·
[Metrics](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-metrics.md)

**Long-running spans**, an acknowledged and unresolved gap.
[Specification discussion #4646](https://github.com/open-telemetry/opentelemetry-specification/discussions/4646) ·
[Specification issue #3349](https://github.com/open-telemetry/opentelemetry-specification/issues/3349)

**Collector and storage.** [fileexporter](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/exporter/fileexporter/README.md) ·
[clickhouseexporter](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/exporter/clickhouseexporter/README.md) ·
[DuckDB `otlp` extension](https://duckdb.org/community_extensions/extensions/otlp) ·
[duckdb-otlp schemas](https://smithclay.github.io/duckdb-otlp/reference/schemas/) ·
[DuckDB JSON loading](https://duckdb.org/docs/stable/data/json/loading_json)

**Process mining.** [Process Mining Manifesto, van der Aalst et al. 2011](https://www.vdaalst.com/publications/p658.pdf) ·
[IEEE 1849-2023 XES](https://ieeexplore.ieee.org/document/10267858/) ·
[XES standard extensions](https://www.xes-standard.org/xesstandardextensions) ·
[OCEL 2.0 specification, arXiv:2403.01975](https://arxiv.org/abs/2403.01975) ·
[ocel-standard.org](https://www.ocel-standard.org/) ·
[Object-centric process mining: divergence and convergence](https://www.researchgate.net/publication/335698927)

**Flow and queueing.** [The Kanban Guide, Vacanti & Coleman](https://kanbanguides.org/english/) ·
[Kanban Pocket Guide ch.6](https://www.prokanban.org/blog/https-prokanban-org-blog-the-kanban-pocket-guide-chapter-6-the-basic-metrics-of-flow) ·
[Little's Law and system stability, Vacanti](https://www.leanability.com/en/blog/2017/08/littles-law-and-system-stability/) ·
[Actionable Agile Metrics for Predictability](https://actionableagile.com/books/aamfp/) ·
[Kingman's formula](https://en.wikipedia.org/wiki/Kingman%27s_formula) ·
[The 175 Principles of Flow, Reinertsen](http://lpd2.com/sample-page/the-principles-of-flow/)

**Delivery and developer-experience research.** [DORA four keys](https://dora.dev/guides/dora-metrics-four-keys/) ·
[2024 DORA report](https://dora.dev/research/2024/dora-report/) ·
[2025 DORA report](https://dora.dev/dora-report-2025/) ·
[The SPACE of Developer Productivity](https://people.uncw.edu/vetterr/classes/csc550-spring2023/The%20SPACE%20of%20Developer%20Productivity.pdf) ·
[DevEx: what actually drives productivity](https://dl.acm.org/doi/10.1145/3610285)

**Statistical process control.** [Wheeler, three-sigma limits](https://www.qualitydigest.com/static/magazine/aug/wheeler.html) ·
[Wheeler, what makes the XmR chart work](https://www.spcpress.com/pdf/DJW250.pdf) ·
[Wheeler & Stauffer, when should we use extra detection rules](https://www.spcpress.com/pdf/DJW322.Oct.17.Using%20Extra%20Detection%20Rules.pdf)

**Rework and defect removal.** [Capers Jones, software defect removal efficiency](https://www.ppi-int.com/wp-content/uploads/2021/01/Software-Defect-Removal-Efficiency.pdf) ·
[ASQ: first pass yield](https://asq.org.in/glossary/quality/F/first-pass-yield/)

**Practice.** [Observability Engineering, 2nd ed.](https://www.oreilly.com/library/view/observability-engineering-2nd/9781098179915/) ·
[Majors, one key difference](https://charity.wtf/2024/11/19/there-is-only-one-key-difference-between-observability-1-0-and-2-0/) ·
[Honeycomb, structured events](https://www.honeycomb.io/blog/structured-events-basis-observability) ·
[Leach, canonical log lines](https://brandur.org/canonical-log-lines) ·
[RED method](https://grafana.com/blog/2018/08/02/the-red-method-how-to-instrument-your-services/) ·
[USE method](https://www.brendangregg.com/usemethod.html) ·
[Claude Code monitoring](https://code.claude.com/docs/en/monitoring-usage)
