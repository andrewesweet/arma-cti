# Observing the system of work: what to measure, how to capture it, and how to ask

**Question.** This project has spent thirty retros improving its own process by argument
and anecdote. What telemetry would let it improve by measurement instead — what data
points, captured how, sliced how, and read by whom?

**Status.** This is research, not a decision record. Sections 1 and 2 contain dated
observations and research findings. Sections 3 through 5 are design proposals that later
issues may adopt, change or reject. Where this document restates a ruling, it cites the
ADR that owns it; no `must`, `should` or proposed schema here creates policy by itself.

**Answer, in one paragraph.** Capture is not the only gap: an OTel collector already runs
on loopback, and the 2026-08-21 observation found durable per-dispatch files for 626 of
639 dispatches. Two purpose-built readers already aggregate narrow slices across records:
`just occupancy` over dispatch intervals and `just gate-clock-history` over gate-clock
rows. **General consumption remains the gap.** No persisted observatory store joins
dispatch, gate, review, landing and telemetry records across work items; the observation
found `ledger.json` on 6 of 639 dispatch records, while the review journal has no general
reader and lacks the author-profile, subject-commit and landing links needed to calculate
ADR-0071 ruling 6's fix-rounds-per-landing key. The proposal is a query layer over the
files that exist, lifecycle events that preserve distinctions the current closeout code
already makes, and a written analyst contract. Its largest dated observation is that
84.0% of ruled capacity went unused in the observed window. That figure is not a
reproducible baseline: no input snapshot or digest was committed.

---

## What this document is not

Three documents already cover ground this one deliberately does not repeat.

- `docs/research/agent-observability-and-cost-ledgers.md` established the collector
  mechanism, `filterprocessor`, `fileexporter` `group_by`, per-lane emission coverage,
  the four hosted candidates and `ccusage`. Its config sketch is what runs today.
- `docs/research/claude-codex-mlflow-observability-gap-analysis.md` covers Claude/Codex
  parity and the common measurement contract.
- `docs/research/mlflow-role-in-system-of-work-improvement.md` recommends MLflow as a
  derived evidence and experiment workbench and rejects it as a controller.

This document sits one layer above all three. They answer *how do we capture agent
telemetry*. This answers *what should we measure about the work system, and how does
anyone read it afterwards*.

**One proposal conflict, stated rather than resolved silently.** The MLflow document recommends
MLflow as the derived evidence plane. MLflow is **not installed** — absent from
`pyproject.toml`, `uv.lock`, `justfile` and `tools/`, so the recommendation stands
unadopted. Proposing a second derived plane without saying so would be the
"second copy nothing compares" shape retro 31 named as its cycle's dominant failure. The
non-binding position this document proposes: **the derived store is the single canonical flattening**,
and MLflow, if ever piloted, projects from that store rather than from raw. One
flattening, two consumers. A later ruling or implementation issue may accept or reject it.

---

## 1. Dated observation, not a reproducible baseline

Every number below was observed on 2026-08-21 from mutable state on this box. The pass
used throwaway scripts over local state, then-current `origin/main`, and live GitHub
queries. No input snapshot, script or digest was committed. Section 8 records the inputs
that were consulted, not commands that can reproduce the figures. Treat every figure as
a dated observation, not a binding baseline or a result reproducible from this repository.

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
191-minute block at 70.1% loss and mean occupancy 1.50/5. In the dated dispatch-record
window, loss was **84.0%** and mean concurrency was **0.48**; the earlier awake block
appeared better than that wider observation.

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

### 1.3 Cost per landed issue was computed in the dated pass

Built as a throwaway extractor over the per-dispatch sinks, joined to `dispatch.json` and
to commits on `origin/main` that reference the issue. This is a `dispatch_only` cost per
landed issue and excludes orchestrator work:

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
In that dated Claude-only corpus, 10,162 `blocked_on_user` spans totalled 21 minutes.
That observation does not support permission prompts as a large cost in that window; it
does not prove the claim for other lanes or later records.

### 1.5 Flow metrics in the dated pass

From 475 issues, 353 closed:

- Lead time, open to close: **p50 7.2 h · p70 24.6 h · p85 54.7 h · p95 117.1 h · max 258 h**.
- **69%** close within a day; **90%** within three.
- Throughput: **16.0 closes/day** mean over 22 active days, ranging 1 to 41.

### 1.6 Review rounds per issue are derivable; the ruled ranking key is not

ADR-0071 ruling 6 ranks on **fix rounds per landing**. Current review records cannot
derive that key. `~/.arma-cti/review/journal.jsonl` holds 37 `cti.review.round` events and
43 `cti.review.dispute` events; the 28 `loop.json` files hold 58 findings — 42 medium, 16
low — with adjudication routes 40 `accepted_and_filed`, 3 `fixed`, 15 unadjudicated. Those
records identify issues and review loops, but carry no durable author-profile,
subject-commit or landing linkage.

What is derivable is the distribution of review rounds per issue: **22 issues at 0, four
at 1, one at 2, one at 3**. Median zero. That describes issue-level review activity only;
it does not establish the distribution or discriminatory power of fix rounds per landing.
Computing the ruled key needs durable links from each fix round to its subject commit and
author profile, then from that commit to its landing. That linkage is a dependency on the
proposed observability set, not a measure this document can assert from current records.

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

Three structural holes visible on baseline `29cf0e8`, each checked against source:

1. **This project emits no spans and no metrics of its own.** It emits eight bespoke
   `cti.*` log event families through `tools/otel_event.py`: `cti.breaker.transition`,
   `cti.queue.transition`, `cti.review.arbiter.resolved`,
   `cti.admission.trial.transition`, and the four review-loop events
   `cti.review.round`, `cti.review.escalation`, `cti.review.dispute` and
   `cti.review.terminus`. There is no project span for a dispatch, a gate run or a review
   round, and no dispatch, gate or landing lifecycle event.
2. **No gate leg records pass or fail.** Gate outcome is inferred from git, so a green
   gate that never landed is invisible. `gate_clock` times `unit` and `fast` only.
3. **The spend estimator is unfalsified.** Every `cap_fraction.observed` is hardcoded
   `null` from a map nothing populates, and `ccusage` is not installed.

---

## 2. The frameworks, and what each one asks for

### 2.1 Technical observability

The findings below are from the OpenTelemetry specifications and the observability
literature; sources are listed in §9.

**Research heuristic for span versus metric versus log.** No single OTel page states it;
the proposal infers it from the three data models. A **span** fits a thing with a start, an
end and a causal position in a larger operation. A **metric** fits a question asked
repeatedly over time with bounded dimensions that must be answered without a scan. A
**log or event** fits a discrete fact with no duration, or a wide record to be sliced
later on high-cardinality fields. This heuristic is not a project ruling.

The proposed corollary shapes most of the design: **metrics can be derived from events at query
time; events cannot be derived from metrics.** With files and a SQL engine, a metric buys
nothing that a `GROUP BY` does not, at full cardinality, retroactively. So: **emit no
metrics of our own yet.** That is a research recommendation, not adopted policy; a later
issue may choose differently when something must be answered live without a scan.

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
investigating. The proposed alternative is a **pair of events**:
`cti.dispatch.started` and `cti.dispatch.finished` sharing a dispatch id, with duration
computed in SQL. A missing `finished` is an investigation signal, not proof of a live
stall: current `result.json` publication and a future event append cannot be one atomic
write, so the result may exist when the event does not. `just watch` and the atomic result
remain the current lifecycle authorities unless a later design unifies them.

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

The source's naming guidance: custom attributes use a unique prefix, and it is *not
recommended* to nest them under an existing convention namespace — so `cti.*` is correct
for this proposal and `gen_ai.cti.*` is not. `otel.*` is reserved. Adopting that mapping
as project policy remains a later decision.

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
attribute goes on an event. The research proposal would never remove or repurpose an
attribute name, only deprecate it, because a rename silently breaks historical queries.
Schema URLs could date every record so a query knows which spelling an old file used.
Neither choice has been ruled.

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
dispatch from the *reviewing* dispatch. Current landing output prints
`gate_review=cross_lane`, but no durable log stores it. Qualifiers make that cause checkable
only after a later event persists both the cause and its relations.

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
may still help. The literature's operational rule is to plot every open item's age against
a historical percentile band. The dated pass observed p85 lead time at 54.7 hours; using
that observation to act on a 60-hour item or replace a fixed timeout remains an authority
choice for the human, not a conclusion this research can implement.

**Little's Law is a stability test, not a forecast.** The Law requires every item admitted
to WIP to leave it. Since #495, atomic `result.json` closeout gives dispatches terminal
lifecycle states including `child_not_launched`, `child_state_unknown` and
`harness_failed_after_child`; these records no longer remain live merely because a child
did not complete normally. What still does not exist is the proposed **analytical category
`abandoned`, with its existing class** for separating not-a-result yield loss from completed
work. That category must preserve the lifecycle status and must never make
`child_state_unknown` look reconciled.

**Flow efficiency is touch time over elapsed time.** Dispatch wall-clock supplies part of
touch time, but non-dispatched work and explicit wait-interval boundaries are absent, so
this system cannot compute whole-work-system flow efficiency exactly today. Typical
software teams land at 15–40%. The dated observations in §1.1 suggest this project's number
may be low, but current records cannot say which causes dominate the wait. The proposed
missing field is **`block_reason` on every wait interval**,
distinguishing
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

**Research recommendation: statistical process control fits samples of this size.** This
is not a compromise — it is the design point. An XmR chart's limits come from a baseline
that "may have as few as four points", twelve preferred, computed as
`X̄ ± 2.660 × mR̄`. Three-sigma limits are chosen on economic grounds rather than a
normality claim, which is why they work on skewed data like cycle times. Four practices
follow. They are proposed analytical practices, not binding project rules:

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

**Research hypothesis, not an observation:** the human may be the Theory-of-Constraints
constraint. Current records carry neither complete `human_ruling_requested` and
`human_ruling_given` transitions nor a measured utilisation, so describing that resource
as an M/M/1 server near full utilisation would outrun the data. Paired ruling intervals
would make the hypothesis testable.

**Research proposal: consider two rework metrics, alongside one empirical finding.**
*Rolled Throughput Yield* is the product of each stage's first-pass yield:
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

**The natural experiment is not yet recorded.** Every gate landing prints `gate_review=`
as one of four causes — `cross_lane`, `lane_exhausted`, `lane_barred`, `same_lane_chosen` —
to landing output. No durable result, event or journal stores that cause, so current
records do not supply the independent variable for comparing cross-lane and same-lane
review effectiveness. Starting that comparison needs durable, landing-linked capture of
the cause, plus a stated window and escape channel for the dependent variable.

---

## 3. Non-binding proposed design

Everything in this section is a research proposal. ADR-0078 records the human's rulings on
the authority choices; this section does not add to that record.

### 3.1 Lifecycle events that preserve current closeout states

The current base emits the eight event families listed in §1.7. The following are proposed
additional lifecycle projections through the existing `tools/otel_event.py` dual-write
seam. They do not replace the current records that own lifecycle truth.

| Proposed event | Proposed source and contract |
|---|---|
| `cti.dispatch.started` | Emitted when `just dispatch` mints an id; carries identity, seat, lane, profile, model, effort, issue, worktree, base SHA, route, strata and breaker state. This means “dispatch record started”, not “child launched”. |
| `cti.dispatch.finished` | Projected only after `result.json` has been published by the same-directory atomic replacement in `tools/dispatch.py:write_result`; carries every applicable result field rather than inferring completion from child exit. |
| `cti.gate.finished` | Emitted for each gate recipe; carries recipe outcome plus the proposed per-leg pass/fail/not-run and duration fields, head SHA, tests collected, load and foreign gate processes. Per-leg outcome does not exist today. |
| `cti.landing.finished` | Projected from the landing report; separates repository landing state from audit posting and issue closing, rather than treating all exit-0 landings as identical closeout. |

The proposed dispatch finish contract must preserve the four current `status` values:
`child_finished`, `child_not_launched`, `child_state_unknown` and
`harness_failed_after_child`. It also carries `failure_phase`, `failure`, `refusal`,
`failure_class`, `returncode`, `outcome`, `action`, `gate_clock_collection`,
`harness_finish`, timestamps and `review_delivery` when each exists. A review run's
delivery must remain distinguishable as `review_delivery=posted`,
`review_delivery=not_attempted`, or the typed `review_delivery_failed` refusal. A nullable
field needs a reason; absence must never be rewritten as success. `child_finished` does
not imply return code zero, and `harness_failed_after_child` needs the separate harness
fields to identify what failed. `child_state_unknown` retains #495's inspect-and-reconcile
action and must not look safe to retry. A review-delivery timeout is uncertain — the
remote post may already have completed — and must not be rewritten as definite non-delivery.

Atomic publication is part of that semantic contract. Child exit is not dispatch
completion. `result.json` is staged, flushed, `fsync`ed and replaced atomically; a failed
write deliberately leaves no published result. This proposal does **not** yet say how a
separate event journal can atomically agree with that file. Therefore a result-write
failure cannot honestly be represented as `cti.dispatch.finished` today: the current
observable is no `result.json` plus `result_write=failed` on the runner's output. A later
design must choose a separate closeout-failure event or a single atomic authority before
using the event as lifecycle truth. It must not emit ordinary completion.

The proposed landing contract has three independent dimensions:

- repository state: `not_landed`, `landed_merge_outstanding` (current exit 2, work already
  on `origin/main`) or `landed`;
- `audit_recorded=yes|no|not_attempted`, preserving its reason and the current
  `verified=posting_call not_verified=content_or_quality` limit; and
- `issue_closed=yes|no|not_attempted`, preserving its reason.

It also carries exit code, typed refusal or outstanding-step reason, issue, pushed SHA,
`gate_review=` cause, review verdict identity and declared author when available. Thus a
failed audit post is `repository=landed, audit_recorded=no, issue_closed=no`, not ordinary
closeout; a successful audit followed by failed closing is distinct again. On current
exit 2 the audit and close are not attempted. These proposed spellings are not current
code and may change, but an implementation may not collapse the states.

The current `cti.review.round` event is a transition summary, not a paired lifecycle. No
current code fact defines a review-round start and finish boundary. A paired review-round
contract therefore remains unrepresentable until a later design chooses those boundaries;
this document does not pretend the existing event is a pair.

### 3.2 Proposed additional fields and samples

The process literature suggests four additional fields and one periodic observation. All
remain proposals:

- **`block_reason`** on wait intervals, from a closed vocabulary with an explicit
  `undetermined` value;
- **an `abandoned` analytical terminal state with its existing failure class**, provided
  it does not erase the dispatch closeout states above;
- **qualified object relations** naming subject, author, reviewer and other roles;
- **`first_pass`** on each stage transition, including an undetermined value; and
- **queue-depth samples**, because no transition occurs while an item waits.

### 3.3 Proposed identity and durability boundary

`cti.dispatch_id` already joins per-dispatch telemetry to the dispatch resource attributes.
The proposal keeps it as the dispatch spine and adds a session-grain identity for work no
dispatch covers.

That session source is **not historically durable on this base**. `tools/quota_tap.sh:54-62`
performs one rollover from `statusline.jsonl` to `statusline.jsonl.1`, overwriting the old
backup on the next roll. Commit `4a48f96` for #464, parked at
`origin/issue-464-parked` on 2026-08-22, is not an ancestor of baseline `29cf0e8` or this
branch. It adds bounded generations, but it has not landed. Until it does, the spool
discards older session history and any whole-system or fully-loaded cost denominator that
uses it is incomplete. The proposal becomes sound for retained history only after #464
lands; a timestamp is still separately required because current lines have none.

The proposed attribute registry — one file naming every `cti.*` attribute, its requirement
level and reason, plus a check leg — is also research. No ruling currently requires it.

### 3.4 Proposed derived store and analyst contract

The proposal is a full rebuild over whatever source files remain available, making the
derived store a cache rather than a source of truth. Not every input is immutable on this
base: the session spool above is the counterexample. The 2026-08-21 pass observed 591
files, 618 MB, 59,682 lines and 279,823 OTel records parsing in 3.3 seconds in unoptimised
Python. Because neither inputs nor script were committed, that timing is a dated
observation, not a reproducible capacity proof.

The proposed outputs are a large local store and a small generated, committed per-issue
summary. DuckDB, a single canonical flattening, and the summary schema are research choices
for #478–#493 to accept or reject; this document does not mandate them.

Three proposed analyst artefacts accompany the store:

1. a schema reference naming every column, its source and each null reason;
2. a worked-query cookbook for questions already asked; and
3. a hazards list, beginning with Codex token metrics versus Claude log records, truncated
   JSON, always-null `cap_fraction.observed`, the spool's missing timestamp and destructive
   rollover, lane-limited span coverage, and `dispatch_only` attribution.

---

## 4. Proposed guidelines for future work

These are candidate rules, not rules this research document can create. A later issue or
human ruling may adopt, alter or reject each one independently.

**Candidate capture guideline.** Prefer a dimension on an existing wide event when its
lifetime contains the question; add an event family only for a distinct lifetime; add a
metric only for a live bounded-cardinality query. Avoid speculative unread signals.

**Candidate feature obligation.** A feature adding a unit of work could add matching
lifecycle capture in the same commit. This is not an existing project convention for
telemetry, and the current review-round boundary shows why it cannot be applied by slogan.

**Candidate attribute policy.** Reuse `gen_ai.*` where a convention exists, use `cti.*`
where none does, register custom names, and deprecate rather than repurpose them. No human
ruling has adopted the registry or deprecation policy.

**Recorded authority boundary.** ADR-0071 ruling 6 forbids profile exclusion, rerouting and
breaker trips derived from observatory readings. ADR-0078 records the human's rulings on
those capabilities. This research describes those choices without adding to them.

**Candidate data-quality guideline.** Distinguish absence from zero and preserve a reason
when known. This is supported by existing writers but is not universal: current result
fields are legitimately absent by state, and the status-line spool has no historical-loss
marker when a generation is overwritten.

---

## 5. Proposed measurement order

Ranked. The human held no prior view, so this is a proposal with its reasoning attached.

**1. Occupancy, and the overnight gap in particular.** 84.0% of ruled capacity is lost;
251.8 hours sit in 254 gaps; the longest is 16.5 hours. This dwarfs everything else in
this document by two orders of magnitude. #295 diagnosed the cohort barrier, landed the
fix, and said plainly that the prospective arm "is the seat's, and it is not run here" —
with numbers to beat of mean occupancy 1.50/5 and 669 lost agent-minutes. **That
measurement has never been taken**, the instrument already exists (`just occupancy`), and
it is the cheapest real result available. The cohort barrier accounts for 292 agent-minutes;
the overnight gaps are far larger and nothing has diagnosed them.

**2. Rework, beginning with the missing linkage.** Current records derive review rounds
per issue, not fix rounds per landing or the ruled profile ranking. First persist links
from each fix round to its subject commit and author profile, then from that commit to its
landing. Dispatches per issue already varies across 188 issues, with a tail to 23, and
remains a proposed unranked companion. Report the ruled key only after its linkage exists.

**3. Gate duration, continued.** #446 found a 2× regression that ran two weeks unnoticed
and had no guilty commit, findable only because Claude Code's transcripts happen to carry
a timestamp — "an accident of the harness, not a record this project keeps". `gate_clock`
now keeps it, for two recipes, with 111 rows. Extending it to every recipe and adding
per-leg pass/fail is small and closes the blind spot that produced the finding.

**4. Cross-lane versus same-lane review effectiveness — persist the independent variable
first.** Every gate landing prints `gate_review=` as one of four causes, but no durable
record stores that output. The natural experiment is therefore not running in an
analysable record. Capture the cause against the landing before collecting escaped defects
per landing within a **stated window** and escape channel. Capers Jones's data says formal
inspection removes ~85% of defects against under 50% for most testing, so this remains a
high-value comparison; this project has not yet recorded the inputs needed to run it.

**5. Aging work-in-progress, as a candidate signal beside fixed-timeout watching.** Cycle
time is known only after intervention was possible; item age is the same quantity while it
may still help. The dated pass observed p85 lead time at 54.7 hours. Using that observation
to trigger or replace watching is one of ADR-0078's ruled authority choices; this research
does not authorise it.

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

## 6. Research limits

Ruling 6 requires its own output to state what it cannot measure. This research list is
evidence for that output, not an expansion of the ruling.

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
2. **What causes the overnight gaps?** The dated pass observed 251.8 hours; the cause
   remains undiagnosed. The cohort barrier explains 292 minutes of it.
3. **Would z.ai and Codex calibrations be worth their cost?** #237's calibration run cost
   about 2.5 plan points against 10 budgeted. A calibration would improve that lane's own
   report; under the recorded ruling it would not authorise a cross-lane total or ranking.
4. **Does `OTEL_METRICS_INCLUDE_RESOURCE_ATTRIBUTES` change what the metric leg carries?**
   Metrics do reach the per-dispatch files, so resource attributes are evidently present;
   whether datapoint-level copies would add anything is unverified.

---

## 8. Provenance of the dated observation

The following is an input inventory, not a reproduction procedure. The scripts were
throwaway, the local files have since changed, `origin/main` moves, live GitHub answers
change, and no snapshot or digest pins any of them. A future reproducible baseline needs a
committed extractor plus an input snapshot or content digests.

```text
Occupancy and idle gaps (§1.1)
  read ~/.arma-cti/dispatches/*/result.json

Per-dispatch shape by seat and lane (§1.2)
  read ~/.arma-cti/dispatches/*/{dispatch,result}.json

Cost per landed issue (§1.3)
  read /var/log/claude-otel/dispatches/dispatch-*.jsonl
  read both log records (Claude) and histogram metrics (Codex)
  joined to then-current `git log origin/main` for landing

Span time decomposition (§1.4)
  read resourceSpans in the same sinks; Claude lane only, from 2026-08-18

Lead time and throughput (§1.5)
  queried live GitHub issue number, createdAt and closedAt fields

Review rounds (§1.6)
  read ~/.arma-cti/review/journal.jsonl and ~/.arma-cti/review/*/loop.json
```

The resulting figures remain useful as a dated observation. They are not acceptance
values for #478–#493 until a reproducible source set exists.

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
