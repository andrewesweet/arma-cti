# The dispatch ledger

One row per dispatched process: what it consumed, how it ended, which issue it was for,
and the commit that landed. `just ledger-sync` materialises it; `~/.arma-cti/dispatches/<id>/ledger.json`
is where it lands, beside the plan and brief `just dispatch` already left there.

ADR-0061's telemetry ruling makes OTel the single capture bus for every lane, and its
durability ruling makes this a **materialised view** over that bus rather than a second
writer. Everything below follows from those two sentences.

## What writes what

| | Writer | Path | Rotates |
|---|---|---|---|
| Records, all signals | the collector | `/var/log/claude-otel/claude-telemetry.jsonl` | yes, 50 MB × 5 |
| Records carrying `cti.dispatch_id` | the collector | `/var/log/claude-otel/dispatches/dispatch-<id>.jsonl` | **no**, append-only |
| The row | `just ledger-sync` | `~/.arma-cti/dispatches/<id>/ledger.json` | n/a |

The second row of that table is the collector's `group_by` file export, added by the
filtered pipelines `just prereqs sudo-script` generates (#230). The split, the filtering
and the durability are all collector configuration; the view exists for the three
readings configuration cannot do.

`just ledger-sync` opens both telemetry paths read-only. It writes exactly one file, the
row, and it never appends to, edits or moves a record. A test checksums the rotating
capture across a sync for precisely this claim.

## Which source a row read, and why it matters

**Preferred: the durable per-dispatch export.** Already filtered, already keyed by
dispatch, non-rotating, and complete by construction.

**Today, for most rows: the rotating capture.** The export directory exists only once the
human has run the root script; until then the same records are still reachable, because
the live `metrics` and `logs` pipelines are unfiltered and a dispatch's `cti.*` resource
block goes through them too. But the capture rotates at 50 MB × 5, and on this box that
is a few days. It therefore **loses records without saying so**, which is why reading it
is treated as a degradation rather than a fallback:

- the row carries `source.kind: rotating_capture` and `source.degraded: true`;
- every printed line carries `source=` and `degraded=`;
- a degraded sync ends with a `warning=degraded_source` line naming the fix;
- a dispatch with **no** records read from a degraded source is typed `unknown`, never
  `infra_unavailable`. Absence there is a fact about the view, not about the dispatch,
  and typing it as the dispatch's end state would be the view inventing a record.

With neither source present, `just ledger-sync` refuses `refused=telemetry_source_absent
class=infra_unavailable` and is not a result.

The traces leg matters for the same reason: opencode emits no metrics at all and carries
its token counts only as AI SDK spans. Until the collector has a `traces` pipeline, that
lane's spend is invisible rather than zero.

## What a row holds

```
schema, materialised_at, dispatch_id, lane, profile, seat, issue, base_sha
source   { kind, path, degraded }
records  { total, metrics, logs, spans }
usage    { input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens,
           list_price_usd, list_priced, list_price_note, unclassified }
cap_fraction { pool, unit, basis, excludes, attribution, attribution_note,
               calibration_id, est_reason, observed_reason,
               binding_window, binding_reason,
               windows { <window> { est, observed, tokens_per_point } } }
end_state{ class, reason, evidence }
gate     { outcome, landed { sha, commits, reason }, returncode, started_at, ended_at }
```

### Cross-lane normalisation

Three lanes report the same fact three ways, and each has a way to be read wrongly
without erroring:

- **Claude Code** — `claude_code.token.usage` datapoints keyed by a `type` attribute
  (`input`, `output`, `cacheRead`, `cacheCreation`), plus `claude_code.cost.usage`, which
  the row carries as `list_price_usd` and nothing ranks on (see below).
- **opencode** — AI SDK spans carrying `gen_ai.usage.input_tokens` / `output_tokens`,
  *and its own `ai.usage.inputTokens` copy of the same number on the same span*. The
  reader takes the first key present per bucket; adding both would double every opencode
  dispatch. It is rename-tolerant across the `gen_ai` vintages (`prompt_tokens` /
  `completion_tokens`) because the lanes disagree about which one they emit. opencode
  reports no list price, so those rows are `list_priced: false` and `list_price_usd:
  null` — never a zero, which would read as a free dispatch.
- **Codex** — `codex.turn.token_usage`. Its aggregation temporality is unverified, which
  is why the reader believes each metric's own `aggregationTemporality`: delta datapoints
  sum, a cumulative series contributes its maximum. Summing a cumulative counter would
  multiply a dispatch's spend by how often the collector scraped it.

A metric or token type the reader does not recognise lands in `unclassified` with its
name. Nothing is silently dropped.

### What a dispatch cost: `cap_fraction`, not dollars

ADR-0061 Decision 1 optimises Claude spend, and on a subscription with no bill the
quantity that means "how close is this to the wall we hit" is **percentage points of a
plan window's cap**, per dispatch. It is also the only unit that means the same thing on
a pool metering input-equivalents, one metering credits and one metering prompt counts,
which is why it is the row's spend column rather than tokens. The metric, its calibration
and its prohibitions are #220's: `docs/research/token-efficiency-plan-currency.md` §6.

**The Claude estimator is output tokens over a measured constant.** One five-hour point
is 30,209 output tokens; one seven-day point is 181,253 (#218's control arm moved the two
meters 6 and 1 on the same 181,253 tokens). Input volume, context size and cache
behaviour do not enter it — they measure at under 1/450th the per-token weight, and the
one residual that could change that is named in `excludes: ["cache_read"]` rather than
assumed away.

**Two halves per window, never one.** `est` is the estimator from the dispatch's own
counters and is the per-dispatch number everything else here is for. `observed` is the
meter delta, and it is what makes `est` falsifiable in aggregate — recording only `est`
gives a ledger nobody can check, and recording only `observed` gives a ledger of zeroes,
because one point is several median agent runs and a single dispatch sits two to three
orders of magnitude under the instrument.

**`observed` is `null` today, with the reason in the row.** The quota feed is a
status-line spool read by #226's breaker, not an OTel record carrying `cti.dispatch_id`,
so no meter delta reaches this view. Absent, not zero: #218's third confound was 28.6 M
tokens moving the meter zero on a verified poll, so **meter silence is never evidence of
a free dispatch**, and a `0.0` in that field would assert exactly that. Filling the half
in would also mean this view inventing #226's record shape for it.

**`binding_window` is `null` for the same reason.** The binding window is whichever is
nearest exhaustion — a fact about accumulated consumption, which only the meter knows.
Both windows are estimated and recorded; none is named as binding until something can say
so. Scarcity routing, when it replaces Decision 1's greedy rule, will route on that one.

**The pool comes from the plan's lane, never from the counters.** The z.ai lane runs the
same binary against a different endpoint, so its records look identical; reading the pool
off them would price z.ai's tokens against Claude's calibration. A lane with no known
pool, and a pool with no measured estimator (z.ai meters prompt counts with a time-of-day
multiplier and publishes no machine-readable state), both get a typed reason and no
number. Neither is ever booked Claude at zero — that zero is precisely what would make
routing work off Claude look free by construction.

**`attribution: "dispatch_only"` is a stated under-attribution.** The orchestrator's own
Claude turns — composing the briefing, reading the report, quoting the verdict — are
Claude output, and they share their parent's resource block and carry no
`cti.dispatch_id`, so no row can hold them. Every row is therefore incomplete by a known
term rather than complete; on a foreign lane that missing term is the one that decides
whether the routing saved anything.

**`calibration_id`** (`claude/218-2026-08-05`) and the per-window `tokens_per_point` are
carried so a re-measured rate re-prices history rather than invalidating it. Without it
the first plan change silently rewrites every past number in the ledger.

**`est` is stored unrounded.** Its accuracy is the calibration's — ±8% on the five-hour
weight — not the ledger's; rounding to some shorter decimal would both assert a precision
the view does not have and turn a small dispatch's cost into `0.0`.

### What `list_price_usd` is, and what it must not be used for

`claude_code.cost.usage` reproduces Anthropic's API list pricing exactly — #218 recovered
the whole rate card from it — and it modelled **$849.76** for a run that moved the plan
meter zero. It is a token-flow number wearing a currency symbol, anti-correlated with
plan cost by roughly three orders of magnitude. It survives in the row under its own name
with `list_price_note` beside it, because it is a useful independent check on the token
counters, and it is **not a decision input**: nothing ranks a profile, a seat, a lane or a
routing choice on it. The summary line does not print it at all. No key called `cost_usd`
exists anywhere in the row, and a test asserts that.

### End-state typing

In ADR-0061's vocabulary, from provider records only, in this order:

| Condition | Class |
|---|---|
| `result.json` carries the dispatcher's own refusal | that refusal's class (always `infra_unavailable`) |
| a provider refusal event | `provider_refused` |
| a provider error with a rate-limit status or error type | `quota_exhausted` |
| no `result.json` yet | `unknown` — the run has not ended |
| no records, durable source | `infra_unavailable` — reached no provider |
| no records, degraded source | `unknown` — the view cannot see |
| otherwise | `ok` |

A `quota_exhausted` row carries whatever `reset_at` the record held, **copied verbatim**.
What a closed lane then waits for, when it reopens, and whether the trip escalates are
#226's breaker, not this view's: the ledger types a dispatch's end state, the breaker
owns the lane's. #226 emits its transitions as `cti.breaker.transition` log events under
`service.name: arma-cti-breaker` with no `cti.dispatch_id`, so they belong to no
dispatch's file and no row reads them.

### The join

- **Issue** — from the dispatch record.
- **Landed SHA** — git's answer: commits on `origin/main` after the dispatch's `base_sha`
  whose message references `#<issue>`. The newest is reported, with the count, since an
  issue may land in several commits and the tip is what a reader wants to `git show`.
- **Gate outcome** — `landed`, `not_landed`, `running`, or `not_a_result`.

`landed` is the gate evidence, and it is the only mechanical one available. The gates run
*inside* the dispatched process, and `result.json` is deliberately facts-only (#223) — a
coding agent's exit code is not a gate result. What is mechanical is that a commit on
`origin/main` cleared `cog verify` and the repo hooks, and that CLAUDE.md binds landing to
a green `just fast`. The limit that leaves is stated rather than papered over: **a green
gate run that never landed is invisible here.** A dispatch whose end state says it was
never a result — `quota_exhausted`, `provider_refused`, `infra_unavailable` — is reported
`not_a_result` rather than as a failed gate, so a routing fact never enters the quality
record ADR-0061 Decision 6 reads.

## Content logging

It is off, and the ledger is where it could come back on. The row copies attribute
*values* only from an allowlist — `status_code`, `refusal_category`, `reset_at`, `model`,
`error_type` — every one a code, a category or a timestamp. No record body and no other
attribute value ever reaches a row, so a capture that one day carried prompt text still
would not put it in the ledger. `OTEL_LOG_USER_PROMPTS` stays unset regardless.

## Retention policy

**The rows are kept indefinitely.** They are the evidence quoted into an issue months
later, they are a few kilobytes each, and nothing in this tool deletes one at any age.

**The raw per-dispatch export is pruned after 30 days** (`RETENTION_DAYS`), and only when
all three hold:

1. the file is older than the horizon;
2. a row exists for that dispatch;
3. that row was materialised **from the durable export** and read at least one record out
   of it.

Conditions 2 and 3 are what stop the policy destroying the only copy of records the view
never saw. A raw file with no row, a row taken from the rotating capture, and a row that
read zero records are all kept and each says why. `just ledger-sync prune` reports and
deletes nothing; `--apply` deletes.

The rotating capture keeps its existing 50 MB × 5 rotation. That is the diagnostics
skill's input and not ours to change.

Review point: `just ledger-sync prune` prints a file count. If `~/.arma-cti/dispatches/`
ever becomes large enough to notice, the growth term is `dispatch.log` — the run's own
output blob, which the durability ruling keeps as a file — not the rows.

## Known limits

- **Only dispatched processes are ledgerable.** A `cti.dispatch_id` lives in the resource
  block, and an in-session Claude Code subagent shares its parent's. `group_by` cannot
  split it and no row can describe it. The only discriminators for those are the
  record-level `agent.name` / `agent_type` attributes, which cannot drive the export.
- **`ccusage` is not installed on this box** (`which ccusage` finds nothing). It reads all
  three lanes' session files and would be an independent cross-check on the token counters
  the whole spend column stands on — every `cap_fraction` estimate is `output_tokens`
  divided by a constant, so a wrong output count is a wrong cost with nothing to catch it.
  Until it is installed, that arithmetic has no second opinion. This is a gap, not a plan;
  see `docs/research/agent-observability-and-cost-ledgers.md`.
- **The observed half of every `cap_fraction` is missing**, which leaves the estimator
  unfalsified rather than wrong. Closing it needs a meter reading at each end of a
  dispatch, keyed to it, on the bus — #226's quota feed and #230's collector config, not
  this view's to write.
- **A foreign lane's spend is unestimated**, not zero. z.ai meters prompt counts against a
  time-of-day multiplier and publishes no machine-readable state, so its estimator waits
  on #226. Codex is not yet a lane here at all.
