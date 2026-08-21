# The observatory widens to the whole system of work, and still reports rather than routes

Delegated-decision: no
Date: 2026-08-21
Supersedes: ADR-0071 ruling 6's scope, which defined the observatory as a rework rollup over
dispatched implementer work. Ruling 6 is amended in place as Amendment A8 rather than left to
disagree with this record; every one of its rulings on *output* — the ranking key, the seat it
ranks, per-lane spend, report-never-route, pre-work stratification, the conditional containment
column and the sample-size caveat — is carried forward unchanged and restated below
Supersedes: none otherwise — ADR-0061 Decision 5 stands, and this record leans on it rather than
touching it; ADR-0071 rulings 1 through 5 and 7 stand unchanged
Reviewed-by-human: the human's rulings of 2026-08-21, given across a design session. On scope:
"(b)" — propose a superset and amend ADR-0071 ruling 6 — against the alternatives of building
ruling 6 as ruled or keeping a parallel layer. On the primary metric: "(a)" — honour the refusal
to convert between lane meters, file the calibration work separately, never overturn. On what the
system optimises: cost per landed issue first, with rework, human minutes and wall-clock as its
drivers. On authority: "Read only". On consumers, in order: an analytical agent on demand, then
the in-loop orchestrator, then the retro-time human
Claimed: 0078 — after `git fetch origin` (`docs/adr/` on `origin/main` topping at 0077) and a scan
of the comment bodies of all sixty most recent open issues, which returned ADR-0071, ADR-0075 and
ADR-0077 and no number at or above 0078. The blind window AGENTS.md records still applies: a claim
living in a comment on an issue that closed before its ADR landed would not have been seen, and
the landing rebase is the backstop

## What changes

ADR-0071 ruling 6 replaced an upfront admission bar with a retrospective observatory. It scoped
that observatory to **rework over dispatched implementer work**. That scope is widened here to
**the system of work as a whole**, for a reason ruling 6 could not have had: the measurements
that scope excludes turn out to be two orders of magnitude larger than the ones it includes.

Measured over the whole history, 2026-08-05 to 2026-08-21, 372.7 hours and 639 dispatches:
**84.0% of the ruled WIP capacity went unused**, mean concurrency was **0.48 against a limit of
3**, and **251.8 hours sit in 254 idle gaps**, the longest running 16 hours 27 minutes. Against
that, the per-dispatch efficiencies the project has repeatedly measured — brief size, scaffolding
overhead, prompt compression — are rounding. `docs/research/dispatch-cost-and-occupancy.md` found
70.1% loss in one 191-minute block and priced the brief at "at most 5 of 669 lost agent-minutes";
the whole-history figure is worse, because that block was awake.

An observatory scoped to what a dispatch spends, in a system where 84% of the loss is a dispatch
that never started, would measure the wrong thing carefully.

## The decision

### 1. The observatory observes the whole work system, not only dispatched implementer work

Four units of work are observable, each by a paired start and finish event carrying a shared
identity: **a dispatch, a gate run, a review round, a landing**. A fifth — the orchestrator's own
turn — is observable only at session grain, and §3 states what that costs.

Ruling 6's output is unchanged by this. It ranks what it ranked, on what it ranked it on. What
widens is the set of questions the same data can answer.

### 2. The primary metric is cost per landed issue, reported per lane and never summed

The human ranks cost per landed issue first, with rework, human minutes and wall-clock understood
as its drivers rather than as competitors to it.

**It is reported once per lane, in that lane's own meter, and never combined.** ADR-0071 ruling 6
and #317 refuse a conversion between the three meters rather than deferring it, and that refusal
is reaffirmed here rather than relaxed. The evidence behind it has not weakened: #220 found
`cost_usd` anti-correlated with plan cost by three orders of magnitude, and #218's A/B modelled
$849.76 for a pair of arms that moved the plan meter by exactly zero.

The consequence is stated plainly rather than softened: **a single cross-lane cost-per-issue
number does not exist and will not be synthesised.** The Claude lane has a calibration (#218,
30,209 output tokens per plan point) and 111 landed issues behind it; z.ai and Codex have none.
Measured today, the Claude lane costs **3.29 plan points per landed issue**. z.ai's 76,601 output
tokens per landed issue is a number in a different currency, not a smaller one.

Funding calibrations for the other two lanes is the only legitimate route to the number the human
actually wants. It is filed as separate work and priced before it is committed to, because
#237's calibration run cost about 2.5 plan points against 10 budgeted.

### 3. Attribution widens beyond `dispatch_only`, and the new boundary is stated

Ruling 6 recorded the ledger's attribution honestly: "all dispatched work, attributed to the
dispatched seat", with the orchestrator's own turns in no row and in-session subagents
unledgerable. That under-attribution is now the largest known error in the primary metric, because
the orchestration seat burns 904 output tokens per minute and nothing has ever priced a whole
session of it.

**Non-dispatched sessions are brought into scope at session grain**, via the status-line spool,
which already captures per-session cost, tokens, duration, lines changed, model, effort and
session id for every session, and which #464 has stopped destroying on every roll.

**And the limit of that is a ruling, not an omission.** A session-grain record carries no issue,
and an orchestrator session dispatches many issues. Apportioning its spend across them would be a
conversion of exactly the kind Decision 5 forbids. So overhead is reported **per period, never
apportioned to an issue**. A fully-loaded figure — direct plus overhead, divided by landings in
the same period — is a legitimate period-level aggregate and is offered as one; it is never
attached to an individual issue.

In-session subagents remain structurally unattributable. Nothing here changes that.

### 4. Rework keeps its ruled key and gains a companion that varies

Fix rounds per landing remains the ranking key, ranked only for implementer-seat profiles, read as
where rework appears and never as who caused it. None of that moves.

**But measured today it barely varies**: across the 28 issues the review loop has recorded,
**22 sit at round zero**, four at one, one at two, one at three. Ruling 6 required the sample-size
limit be stated as the estimate it is; this is a sharper problem than small n, because a key with
almost no variance cannot separate profiles however long it runs.

So **dispatches per issue** is added as a reported, unranked companion — 188 issues, 79 of them at
a single dispatch, with a tail to 23. It is a rework proxy with real spread, and it is the measure
most likely to move under an intervention. It does not become the ranking key: that would be a
ruling, and this record does not take it.

### 5. Every gate leg records whether it passed

Today no gate leg records a pass or a fail anywhere. Gate outcome is inferred from git, so a gate
that ran green and never landed is invisible, and `gate_clock` times two recipes of the several
that run. #446's 2× gate regression ran two weeks unnoticed and was findable only because Claude
Code's transcripts happen to carry a timestamp — "an accident of the harness, not a record this
project keeps".

A gate run emits its recipe, its per-leg outcome and its wall-clock. This is the one place in this
record where genuinely new information is captured rather than existing information joined.

### 6. Four fields that do not exist today, and a queue depth that has no event

The process-mining literature grades an event log one to five stars and rules that analysis
is trustworthy only at three or above. This project's log is at **two**: recorded
automatically, but as a by-product, with varying coverage and — the defining property — *it
is possible to bypass*. An interactive session that lands work leaves no dispatch record,
which is why `just review-loop author --profile P` had to be invented at all.

Four fields raise it, one column each:

- **`block_reason` on every wait interval.** Without it, wait time is one undifferentiated
  number, and "waiting for the human" is indistinguishable from "waiting for a lane's peak
  band to close" — two opposite interventions. Given that §1 of the research document finds
  the loss overwhelmingly in waiting rather than working, this is the highest-value single
  field in the design.
- **An `abandoned` terminal state carrying its class.** `infra_unavailable`,
  `quota_exhausted` and `provider_refused` are work that started and explicitly is not a
  result. Counting them as work-in-progress inflates cycle time without bound; dropping them
  silently understates it. This project has had the vocabulary since its failure-class table
  and has never had the state.
- **Qualified object relations** — each event naming the objects it touches *and in what
  role*: subject, author, reviewer, produced, consumed, occupied. This is what makes
  `gate_review=cross_lane` checkable **from the log** rather than believed from a printed
  line, and what stops one `just land` event being counted three times over.
- **`first_pass` per stage transition**, which yields first-pass yield per stage and rolled
  throughput yield for the pipeline. Five stages at 90% each is 59% — every stage healthy
  while four issues in ten need rework somewhere.

And one observation has no event because nothing happens: **queue depth**. Reinertsen's
first queueing principle is that product-development inventory is invisible; an issue behind
the WIP limit, a branch awaiting a reviewer, a finding filed and unadjudicated appear
nowhere unless deliberately counted. A periodic depth sample per queue is the only way to
see them, and counting them is most of the job.

### 7. A reading becomes a signal by one rule, and the rule is Rule One

Interventions here are judged over samples in the tens, which is the design point of a
process-behaviour chart rather than a compromise: limits come from a baseline of as few as
four points, twelve preferred, at `X̄ ± 2.660 × mR̄`, and three-sigma limits are chosen on
economic grounds rather than as a normality claim — which is why they work on skewed data
like cycle times.

**One detection rule: a point outside the limits.** Wheeler's own recommendation, because
further rules "shift this balance toward more false alarms in order to find smaller
signals" and produce a chart that is "an unending nag which you must ignore in
self-defense". For a consumer that is partly an autonomous loop, an alerting surface that
trains its reader to ignore it is worse than none.

Three practices bind with it. **Limits are frozen** at the baseline and later points plotted
against them, because recomputing as data arrives is how a real shift gets absorbed and
disappears. **Strata are charted separately** — Wheeler's camshaft case, where three
parallel processes interleaved in time order produced moving ranges measuring between-process
differences and went blind to real signals, is exactly what charting three lanes in one
series would do. And **not-a-result classes are excluded from the value chart** and counted
separately, because they are not process output and including them inflates the moving range
until nothing can signal.

### 8. Signals are paired events, not long spans

Anything spanning a dispatch is emitted as `started` and `finished` events sharing an identity,
with duration computed at query time. Not as a span.

The reason is mechanical. OpenTelemetry exports a span only when it ends, so a span covering an
hour-long dispatch is invisible until it finishes and is **lost entirely if the process dies** —
and this project plans for agents dying. A single span per dispatch would therefore be absent in
exactly the cases most worth investigating, while **a missing `finished` event is itself the stall
signal**, which is what `just watch` exists to produce and what 226 measured stalls make the most
valuable signal in the system.

Names follow the GenAI semantic conventions where one exists — seat as `gen_ai.agent.name`, lane as
`gen_ai.provider.name`, the four token classes as `gen_ai.usage.*` — and `cti.*` where none does:
dispatch id, issue, worktree, profile, effort, gate class, review cause. Never one nested inside
the other. **No attribute name is ever deleted or repurposed**, only deprecated, because the
archive is permanent and a silent rename breaks every query written before it.

**No metric is emitted by this project yet.** With files and a SQL engine, every rate, error rate
and duration distribution is a `GROUP BY` over the events, at full cardinality, retroactively.
A metric is added only when a live surface must answer without a scan.

### 9. It reports and never routes

Unchanged from ruling 6, and reaffirmed as the human's explicit instruction in this session:
"Read only". Nothing derived from this telemetry excludes a profile, reroutes work, or trips a
breaker. The dropped admission bar is the worked example — a measurement given authority it could
not carry, which never adjudicated once across 24 routes — and the action on a bad reading remains
a human ruling at a retro.

The in-loop consumer the human ranked second is bound by the same constraint and by one more:
`docs/agents/orchestration.md` already rules that the orchestrator's turn-top read is "a verdict,
never a dashboard of numbers (#209)". Any live signal added here is silent when healthy and states
a verdict when not, exactly as the six existing sub-reads do.

### 10. One derived store, rebuilt rather than migrated, and one committed summary

The store is a cache and never a source of truth: a full rebuild from the immutable JSONL sources
on every run. Rebuild cost is not a constraint — **591 files, 618 MB, 59,682 lines and 279,823 OTel
records parse in 3.3 seconds** in unoptimised Python — so a schema change is a re-run rather than a
migration, which matters because this schema will change repeatedly.

Beside it, **one committed per-issue summary row** — cost in its lane's meter, rounds, dispatches,
duration, lanes involved — which survives box death, diffs under review, and gives an analyst a
cheap first read. `docs/process-log.md` is the precedent: this project's only longitudinal record
is committed prose, for reasons that apply here.

**And the store is the single canonical flattening.**
`docs/research/mlflow-role-in-system-of-work-improvement.md` recommends MLflow as the derived
evidence and experiment workbench. MLflow is not installed — absent from `pyproject.toml`,
`uv.lock`, `justfile` and `tools/` — so that recommendation stands unadopted, and this record does
not retire it. If MLflow is ever piloted it projects **from this store**, not from raw. Two
independent flattenings of the same events would be the "second copy nothing compares" shape retro
31 named as its cycle's dominant failure.

### 11. The analyst's contract is part of the deliverable, not documentation of it

Three written artefacts, kept beside the store: a **schema reference** naming every column, its
source and why each nullable column is null; a **query cookbook** holding the questions retros have
actually asked, each with its SQL; and a **hazards list**.

The hazards list is the part that earns its keep, and the first entry is one this design walked
into while being written. Claude emits token counts as log records; Codex emits
`codex.turn.token_usage` as a **histogram metric**. A log-only reader returns rows, looks correct,
and books an entire lane at zero — which is the "reading meter silence as free" error #220
prohibits, reproduced by accident within an hour of a document arguing against it. A hazard that
costs an hour to rediscover and leaves no trace when missed belongs in a durable list, not in a
reviewer's memory.

## When telemetry is added, and by whom

The durable rule this record contributes:

- Add a **dimension to an existing event** when a question was asked and could not be answered.
  This is nearly always the right move: one column, retroactive from the moment it lands.
- Add a **new event family** only when no existing event's lifetime contains the thing measured.
- Add a **metric** only when a live surface must answer without a scan.
- A landing that adds a unit of work — a seat, a gate recipe, a lifecycle state — adds that unit's
  start and finish events **in the same commit**, which is this project's existing rule that a
  convention lands with its first applied instance.
- Never add a signal speculatively. An unread signal is indistinguishable from an absent one and
  carries a maintenance obligation the absent one does not.
- Every signal distinguishes **absence from zero, with a reason code**.

## What this costs, stated rather than discovered

It is more surface. Four event families, a registry, a store, three documents and a `just` recipe,
against a project whose command table is already long enough that two of its rows went a day
without the recipes they named.

It does not reduce the work of judging. Ruling 6's own words hold: the observatory measures rework
and sees none of the five orchestration-process criteria #242 measured, and that remains a loss
rather than a substitution.

And the first thing it will show is uncomfortable. An 84% capacity loss is not a finding about any
lane, profile or model; it is a finding about the seat that decides what runs, and about the hours
in which nobody is awake to decide. The measurement was cheap and the answer is not.

## What would overturn this

- **A cross-lane calibration landing** would make §2's refusal unnecessary rather than principled,
  and the primary metric would become a single number. That is a ruling to take then, on evidence,
  not now.
- **Occupancy rising to near the ruled limit under an intervention** would move the ranking in §4's
  companion measure and the priority in the research document's shortlist; per-dispatch efficiency
  would then be the right end of the problem, which today it is not.
- **A durable record of hook bypasses existing** would make ruling 6's containment column
  buildable; until then it stays absent, because an empty column reads as evidence that bypasses
  did not occur.
- **Claude Code proving to ingest `TRACEPARENT` from its environment** would make a single stitched
  trace per issue possible and would make §6's join-key-first design a fallback rather than the
  primary mechanism. This is untested and named as untested.
- **The review loop's round distribution developing real variance** would remove §4's reason for a
  companion measure, and the ruled key would stand alone as ruling 6 intended.

## Sequencing

The specs and tickets this record authorises are ordered so that stopping after any one leaves
something that works: the query layer over data that already exists comes before any new emission,
because it is what makes the next decision an informed one. New emission — gate legs first, since
they are the only genuinely absent information — follows. The analyst's three documents land with
the query layer, not after it, because a store nobody can interrogate is the state this record
exists to end.
