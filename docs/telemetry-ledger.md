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
           cost_usd, priced, unclassified }
end_state{ class, reason, evidence }
gate     { outcome, landed { sha, commits, reason }, returncode, started_at, ended_at }
```

### Cross-lane normalisation

Three lanes report the same fact three ways, and each has a way to be read wrongly
without erroring:

- **Claude Code** — `claude_code.token.usage` datapoints keyed by a `type` attribute
  (`input`, `output`, `cacheRead`, `cacheCreation`), plus `claude_code.cost.usage` in USD.
- **opencode** — AI SDK spans carrying `gen_ai.usage.input_tokens` / `output_tokens`,
  *and its own `ai.usage.inputTokens` copy of the same number on the same span*. The
  reader takes the first key present per bucket; adding both would double every opencode
  dispatch. It is rename-tolerant across the `gen_ai` vintages (`prompt_tokens` /
  `completion_tokens`) because the lanes disagree about which one they emit. opencode
  reports no cost, so those rows are `priced: false` and `cost_usd: null` — never a zero,
  which would read as a free dispatch.
- **Codex** — `codex.turn.token_usage`. Its aggregation temporality is unverified, which
  is why the reader believes each metric's own `aggregationTemporality`: delta datapoints
  sum, a cumulative series contributes its maximum. Summing a cumulative counter would
  multiply a dispatch's spend by how often the collector scraped it.

A metric or token type the reader does not recognise lands in `unclassified` with its
name. Nothing is silently dropped.

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
  three lanes' session files and would be an independent cross-check on the ledger's cost
  arithmetic — the part most likely to be quietly wrong, since opencode reports tokens and
  no money, so the ledger must price them itself. Until it is installed, that arithmetic
  has no second opinion. This is a gap, not a plan; see `docs/research/agent-observability-and-cost-ledgers.md`.
- **A dispatch's cost on a foreign lane is unpriced**, not zero. Fraction-of-cap per pool
  (ADR-0061 Decision 1) is read from the breaker's quota feed (#226), not from here.
