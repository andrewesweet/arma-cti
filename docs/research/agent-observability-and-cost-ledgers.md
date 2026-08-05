# Agent observability and cost ledgers: is the dispatch ledger a solved problem?

**Explored**: 2026-08-05, research dispatch R2, against the grilling session's rulings 10 and 11. Box as it stands: `otelcol-contrib` 0.157.0, Claude Code 2.1.222, `opencode` at `c9d967443`.
**Outcome**: **no existing tool replaces the ledger, but almost none of it needs writing either.** Every candidate fails on the same axis — they are analytics surfaces over a database, not durable per-dispatch evidence files, and the two that could hold an external key want ClickHouse or Postgres running permanently on a laptop that is already hosting an Arma server. What replaces the *writing* half is the collector itself: `fileexporter`'s `group_by` splits records into one file per `cti.dispatch_id` with no code at all. That is tested on this box, not inferred.

Evidence class is marked per claim: **[tested here]** means I ran it on this machine this session; **[primary source read]** means I read the source or spec that owns the fact; **[documented, untested]** means a first-party doc says so and I did not exercise it; **[inferred]** means I reasoned to it.

## The headline

| Candidate | Ingests metrics + logs? | Holds an issue-number key? | Runs without a DB server? | Verdict |
|---|---|---|---|---|
| Langfuse | **no** — traces only | yes, `metadata`, filterable | no — 6 containers: Postgres, ClickHouse, Redis, MinIO | **no** |
| Helicone | **no** — proxy-first, OTLP unconfirmed | yes, custom properties | no — 1 container wrapping Postgres + ClickHouse + MinIO | **no**, and unmaintained since Mar 2026 |
| Braintrust | **no** — traces only | yes, `metadata`/`tags` | no — hosted control plane, phones home | **no** |
| Arize Phoenix | **no** — traces only | metadata yes, filtering on it doubtful | **yes** — single process on SQLite | **closest, still no** |
| `ccusage` | n/a — reads session files, not OTel | no, time and project only | yes, one-shot CLI | **no, but adopt alongside** |
| **collector `group_by`** | **it already is our pipeline** | **yes — it *is* the grouping key** | **yes, no new process** | **this is the writer** |

The one-line recommendation: **keep ruling 10, amend ruling 11.** OTel stays the single capture bus. The ledger stays a materialised view. But `just ledger-sync` shrinks from "compact the filtered export into per-dispatch directories" to "join a per-dispatch file the collector already wrote to the issue, the arm and the SHA" — because the split, the filtering and the durability are collector config, and config is the thing this project prefers to code.

## What the box already emits, measured

Before asking what to build, I inventoried the live capture at `/var/log/claude-otel/claude-telemetry.jsonl` — 376 lines scanned, every attribute key counted. **[tested here]**

Resource attributes present, in full: `host.arch`, `os.type`, `os.version`, `service.name`, `service.version`, `wsl.version`. That is the entire resource block. Nothing else.

**The load-bearing consequence: `session.id` is a *record* attribute, not a resource attribute.** It appears as `metric:session.id` and `log:session.id`, never in the resource. So today there is no resource-level key on which anything could be filtered or grouped — the resource block is identical for every session on the box. Any per-dispatch routing has to *put* a key in the resource block; it cannot discover one there.

Metrics emitted: `claude_code.active_time.total`, `claude_code.code_edit_tool.decision`, `claude_code.cost.usage`, `claude_code.lines_of_code.count`, `claude_code.token.usage`.

Events emitted: `api_request`, `assistant_response`, `hook_execution_complete`, `hook_execution_start`, `skill_activated`, `subagent_completed`, `tool_decision`, `tool_result`, `user_prompt`.

Record attributes worth naming, because they are most of a ledger already: `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`, `cost_usd`, `cost_usd_micros`, `model`, `final_model`, `model_swapped`, `duration_ms`, `agent.name`, `agent.source`, `agent_type`, `effort`, `session.id`, `terminal.type`.

Two of those deserve emphasis. `agent.name`, `agent_type` and `effort` are already attached to token and cost records, and `subagent_completed` is already an event — **the existing pipeline can already attribute spend to an individual subagent dispatch, per model and per effort tier, with no change whatsoever.** The gap the ledger fills is not measurement. It is the join to a GitHub issue, an arm and a landed SHA, and durability past a 250 MB rotation window.

### Content logging is genuinely off, and a filtered export would not leak it

The brief says content logging must stay off, so I checked what the `prompt` attribute actually contains rather than trusting the absence of a flag. Every `user_prompt` event carries `prompt_length` and a `prompt` attribute whose value is the literal string `<REDACTED>`. **[tested here]** `OTEL_RESOURCE_ATTRIBUTES` and `OTEL_LOG_USER_PROMPTS` are set nowhere in `~/.claude/settings.json`, `/etc/environment`, `.bashrc` or `.profile`. **[tested here]**

So the attribute exists as a placeholder and the content does not. A second exporter carrying the same records inherits that redaction — the risk of a durable ledger leaking prompt text is not a risk unless someone sets `OTEL_LOG_USER_PROMPTS=1`. It should stay unset, and the ledger design should not need it.

### Nothing here disturbs the diagnostics skill

`~/.claude/skills/wsl-session-diagnostics/SKILL.md` §"Data sources" item 2 consumes exactly this file, by path, parsing `resourceMetrics[].scopeMetrics[].metrics[].sum.dataPoints[]` for `session.id` and `timeUnixNano` to get per-session last-seen. **[primary source read]** Every change proposed below is *additive* — a new processor used only by new pipelines, and a new exporter. The existing `metrics` and `logs` pipelines keep their receiver, processor and exporter lists byte-for-byte, `/var/log/claude-otel/claude-telemetry.jsonl` keeps its rotation, and the skill's query keeps working on unchanged input. This is verified below rather than asserted: the fan-out test confirms the unfiltered pipeline still receives records that the filtered pipeline also took.

## The collector mechanism, tested on this box

This is the section that changes ruling 11, so I ran it rather than reading it. A second `otelcol-contrib` instance on port 14318, internal metrics disabled to avoid the live collector's 8888, writing to scratch. The live collector and `/etc/otelcol-contrib/config.yaml` were never touched.

### The processor is `filterprocessor`, and no connector is needed

One receiver may be listed in more than one pipeline of the same signal. The collector's own `processor/README.md` states it: "the receiver may be attached to multiple pipelines, in which case the same data will be passed to all attached pipelines via a data fan-out connector." **[primary source read]** So the second export is two extra pipelines re-listing the existing `otlp` receiver — `routingconnector` and `forwardconnector` are both available and both more invasive, because they must be inserted into the existing pipeline's graph.

Pipeline independence is guaranteed by a documented mechanism, not by luck. Because `filterprocessor` mutates data, its pipeline runs in Exclusive Ownership mode, and the same README states that in that mode data "will be cloned at the fan-out connector before passing further to each pipeline." **[primary source read]** I confirmed the effect directly: with a filter dropping non-`cti` records in pipeline B, pipeline A's output still contained the plain record, both `cti` records and both metrics. **[tested here]**

**The semantics gotcha, quoted:** filterprocessor conditions are DROP-if-true, not keep-if-true — "If **any** condition is met, the telemetry is dropped (each condition is ORed together)." **[primary source read]** So "keep only records carrying `cti.dispatch_id`" is written as the inverted condition `resource.attributes["cti.dispatch_id"] == nil`. Getting this backwards silently exports the complement of what you wanted, and no gate would catch it.

Both config shapes work on 0.157.0: the modern `log_conditions:` / `metric_conditions:` form and the deprecated `logs: log_record:` / `metrics: metric:` form each validated and ran. **[tested here]** The modern form is the one to write; the contrib README's deprecation table maps the old to the new.

### `fileexporter` `group_by` is the whole per-dispatch split

`fileexporter` substitutes a resource attribute's value into a `*` wildcard in `path`, creating missing directories recursively. **[primary source read]** Exercised here: two dispatches sending on one connection produced `dispatch-D1.jsonl` and `dispatch-D2.jsonl` automatically, and D1's file held both its log event and its metric datapoint — logs and metrics for one dispatch interleave into one file, which is what a ledger wants. **[tested here]**

Four behaviours I checked because the design depends on them and the README does not state them all:

- **Omitting `rotation:` gives a single non-rotating file.** The README says rotation is only enabled when specified; note that a bare `rotation:` with an empty body still enables it at defaults of 100 MB × 100. **[primary source read]** Confirmed: the non-rotating exporter produced one growing file. **[tested here]**
- **`append: true` survives a collector restart.** After stopping and restarting the collector, `dispatch-D1.jsonl` contained both the pre-restart and post-restart record. **[tested here]** This is what makes the file a durable record rather than a session buffer. The README states `append: true` is incompatible with `rotation` — which suits a ledger, since a ledger must not rotate.
- **`group_by` composes with `append` and `flush_interval`.** The contrib README gives no example combining them and the earlier reading flagged the combination unverified; the combination validates and runs on 0.157.0. **[tested here]**
- **Hostile attribute values are sanitised, and the path prefix holds.** A dispatch id of `../escape` produced `<ledger-dir>/dispatch-/escape.jsonl` — inside the ledger directory, not above it — matching the README's documented guarantee that "the final path is guaranteed to start with the prefix part of the `path` config value." **[tested here + primary source read]** A value containing `/` becomes a subdirectory rather than an error, so **dispatch ids should be constrained to a safe alphabet by the thing that mints them**, not by the collector. Left unconstrained, a stray id silently fragments the ledger into directories.

Output is line-delimited JSON — "Each line in the file is a JSON object" **[primary source read]** — so a per-dispatch file is greppable and streamable with the same idioms the diagnostics skill already uses on the main capture.

### The config sketch

Additive only. The existing `metrics` and `logs` pipelines below are shown exactly as they stand in `/etc/otelcol-contrib/config.yaml` today and are not edited.

```yaml
processors:
  batch:
  # NEW — used only by the ledger pipelines below.
  # DROP-if-true: drops everything WITHOUT the key, i.e. keeps only cti-tagged records.
  filter/cti:
    error_mode: ignore
    log_conditions:
      - resource.attributes["cti.dispatch_id"] == nil
    metric_conditions:
      - resource.attributes["cti.dispatch_id"] == nil

exporters:
  file/claude:            # EXISTING — untouched, still rotating, still the skill's input
    path: /var/log/claude-otel/claude-telemetry.jsonl
    format: json
    rotation:
      max_megabytes: 50
      max_backups: 5

  file/ledger:            # NEW — non-rotating (no `rotation:` key at all), append-only,
                          # one file per dispatch via the `*` wildcard
    path: /var/log/claude-otel/dispatches/dispatch-*.jsonl
    format: json
    append: true
    flush_interval: 1s
    create_directory: true
    group_by:
      enabled: true
      resource_attribute: cti.dispatch_id
      max_open_files: 20

service:
  pipelines:
    metrics:              # EXISTING — unchanged
      receivers: [otlp]
      processors: [batch]
      exporters: [file/claude]
    logs:                 # EXISTING — unchanged
      receivers: [otlp]
      processors: [batch]
      exporters: [file/claude]
    metrics/ledger:       # NEW — re-lists the same receiver
      receivers: [otlp]
      processors: [filter/cti, batch]
      exporters: [file/ledger]
    logs/ledger:          # NEW
      receivers: [otlp]
      processors: [filter/cti, batch]
      exporters: [file/ledger]
```

This shape — modulo the scratch paths — is the one that validated and ran. **[tested here]** `max_open_files` defaults to 100 and caps concurrently open per-dispatch files; 20 is ample for a WIP limit of three and keeps the descriptor cost trivial.

Two operational caveats. The collector runs as its own user, so `/var/log/claude-otel/dispatches/` needs to be writable by it — `create_directory: true` handles creation but not a permission mismatch on the parent. And a non-rotating append-only file grows without bound by design: **the ledger needs a retention decision made deliberately** (per-dispatch files are individually small and individually deletable, which is the argument for `group_by` over one flat filtered file).

## Getting `cti.*` into the resource block

The filter selects on a resource attribute, so every lane must be able to put one there. All three can, by the same mechanism.

- **Claude Code** documents `OTEL_RESOURCE_ATTRIBUTES` explicitly, with the example `export OTEL_RESOURCE_ATTRIBUTES="department=engineering,team.id=platform,cost_center=eng-123"`, and states the values are attached "as attributes on every metric datapoint and event record, in addition to sending them in the OTLP resource block." **[primary source read]** Both placements are useful: the resource block drives the filter, the datapoint labels make the records self-describing once split out. `OTEL_METRICS_INCLUDE_RESOURCE_ATTRIBUTES=false` suppresses the datapoint copy if cardinality ever matters. Format is strict — no spaces, US-ASCII, percent-encode anything exotic — which is a second reason to keep dispatch ids to a plain alphabet.
- **opencode** parses `OTEL_RESOURCE_ATTRIBUTES` itself in `packages/core/src/effect/observability.ts` and merges it into the resource ahead of its own keys, so caller-supplied attributes survive. **[primary source read]** It also adds `service.name: "opencode"`, `service.version`, `deployment.environment.name`, `opencode.client`, `opencode.process_role`, `opencode.run_id` and `service.instance.id`.
- **Codex** carries a `span_attributes` map in `OtelSettings` **[primary source read]**, though see the lane section below for why Codex is the least certain of the three.

The important structural point: this works because each lane is a **separate child process** whose environment the dispatcher controls. A Claude Code subagent running in-process inherits its parent's resource attributes and cannot be tagged separately — so a `cti.dispatch_id` distinguishes *dispatched processes*, not logical subagents within one session. For in-session subagents the existing `agent.name` / `agent_type` record attributes remain the only discriminator, and they are record-level, so they cannot drive `group_by`. **[inferred, from the tested fact that `group_by` reads resource attributes and the measured fact that `agent.name` is a record attribute]**

## OTel GenAI semantic conventions: should `cti.*` defer to `gen_ai.*`?

**No, and the conventions themselves say so.**

The `gen_ai.*` conventions moved out of `open-telemetry/semantic-conventions` into a dedicated `semantic-conventions-genai` repository at v1.42.0, the changelog marking it a breaking change: all `gen_ai.*` attributes, metrics, events and spans "are deprecated in this repository and have moved." **[primary source read]** In the new repo, **every** `stability:` field across the registry and span models reads `development` — nothing is Stable, nothing is Release Candidate. **[primary source read]** The prose agrees: metrics are "all currently in Development status."

They also churn. `gen_ai.system` was renamed to `gen_ai.provider.name` at v1.37.0; `gen_ai.usage.prompt_tokens` / `completion_tokens` became `input_tokens` / `output_tokens` earlier still; the message-event family was deprecated wholesale at v1.37.0. **[primary source read]**

On coexistence, the general naming guidance in `docs/general/naming.md` is direct: prefix your own names with something you own, and do not put proprietary attributes under an OpenTelemetry semantic-convention namespace, because the spec will collide with you later. **[primary source read]**

So the answer to the brief's question is: **`cti.*` coexists with `gen_ai.*` and defers to it for nothing.** They are answering different questions. `gen_ai.*` describes a model call; `cti.*` describes *which dispatch, which issue, which arm* — project-owned facts no vendor convention will ever define. Reading `gen_ai.usage.input_tokens` when a lane happens to emit it is right; *writing* our dispatch identity into a Development-status namespace that renamed its provider attribute one minor release ago is not. The one thing worth doing is treating `gen_ai.usage.*` as a *read* target with a rename-tolerant reader, since the three lanes disagree about which vintage they emit.

## Lane coverage: what each of the three actually emits

### Claude Code — metrics and logs today, traces available behind a beta flag

Claude Code 2.1.222 is installed. **[tested here]** The current docs state tracing exists and is off by default: "Tracing is off by default. To enable it, set both `CLAUDE_CODE_ENABLE_TELEMETRY=1` and `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1`, then set `OTEL_TRACES_EXPORTER`." **[primary source read]** Spans run `claude_code.interaction` → `claude_code.llm_request` / `claude_code.tool` / `claude_code.hook`, with subagent spans. **[documented, untested]** The `llm_request` span mixes namespaces — `gen_ai.request.model`, `gen_ai.response.id`, `gen_ai.system` (still the *deprecated* name) alongside `input_tokens`, `output_tokens`, `agent_id`, `workflow.run_id`. **[primary source read, from the docs page]**

Neither `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA` nor `OTEL_TRACES_EXPORTER` is set on this box, and the collector has no `traces` pipeline. **[tested here]** So this is an available capability, not a current one. Enabling it would be a real change in data volume and shape, and the `claude_code.hook` spans in particular would be noisy given how many hooks this repo runs. Worth noting, not worth doing as part of the ledger.

Namespace for metrics and events is entirely `claude_code.*`, not `gen_ai.*` — matching what I measured in the capture file.

### opencode — traces and logs, no metrics, and tokens only if you ask

Read directly from the clone at `c9d967443`. **[primary source read]**

Telemetry is gated on one thing: `export const enabled = !!base` where `base = Flag.OTEL_EXPORTER_OTLP_ENDPOINT`. Setting `OTEL_EXPORTER_OTLP_ENDPOINT` turns it on; there is no separate enable flag. It exports **traces** to `${base}/v1/traces` (`@opentelemetry/exporter-trace-otlp-http` 0.214.0, via `BatchSpanProcessor`) and **logs** to `${base}/v1/logs` (Effect's `OtlpLogger` with JSON serialisation). **There is no metrics exporter at all** — so opencode's spend can only be reconstructed from spans, never from a counter.

**Do opencode's own spans carry token counts? No.** I read every `withRunSpan` / `setRunSpanAttributes` call site in `packages/opencode/src/cli/cmd/run/`. The attributes are `opencode.mode`, `opencode.directory`, `opencode.resume`, `opencode.agent.name`, `opencode.model.provider`, `opencode.model.id`, `opencode.model.variant`, `opencode.initial_input`, `opencode.demo` and `session.id`. Span names are `RunInteractive.session`, `RunInteractive.turn`, `RunInteractive.localMode`, `RunInteractive.attachMode`. Timing and identity, no usage. Grepping the package sources for `gen_ai` returns nothing.

**But the AI SDK spans underneath them do, and they are gated behind a config flag.** `packages/opencode/src/session/llm.ts` and `packages/opencode/src/agent/agent.ts` both pass `experimental_telemetry: { isEnabled: cfg.experimental?.openTelemetry, ... }`, whose schema annotation reads "Enable OpenTelemetry spans for AI SDK calls (using the 'experimental_telemetry' flag)". So `experimental.openTelemetry: true` in opencode's config is required for any token-bearing span. `llm.ts` additionally sets `functionId: "session.llm"` and `metadata: { userId, sessionId }`, which the AI SDK surfaces as `ai.telemetry.functionId` and `ai.telemetry.metadata.*`.

The installed AI SDK is `ai` 6.0.168. Grepping its `dist/` for attribute names gives, verbatim: `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.response.id`, `gen_ai.response.finish_reasons`, `gen_ai.system`, `gen_ai.request.{temperature,top_p,top_k,max_tokens,presence_penalty,frequency_penalty,stop_sequences}`, plus its own `ai.usage.inputTokens`, `ai.usage.outputTokens`, `ai.usage.cachedInputTokens`, `ai.usage.reasoningTokens`, `ai.usage.totalTokens`. **[primary source read]**

So the opencode lane is: **set `OTEL_EXPORTER_OTLP_ENDPOINT`, set `experimental.openTelemetry: true`, and you get spans carrying `gen_ai.usage.input_tokens` / `output_tokens` and cached and reasoning token detail — with cost left to compute yourself, since the SDK reports tokens and not money.** Note it emits `gen_ai.system`, the name deprecated at semconv v1.37.0, which is exactly why the reader should be rename-tolerant.

One collision worth knowing: opencode sets a bare `session.id` span attribute, the same key Claude Code uses on its records. Convergent, not coordinated — a reader must disambiguate by `service.name`.

**Consequence for ruling 11: the collector needs a `traces` pipeline after all**, not for Claude Code but for opencode, whose token counts exist only as spans. That is a genuine addition to the current config, and `filterprocessor` supports `trace_conditions` in the same shape. I did not exercise the traces path in the fan-out test — the tested legs were logs and metrics. **[untested]**

### Codex — it does emit OTel, but the default sends metrics to OpenAI

The Codex repo has a dedicated `codex-rs/otel/` crate covering logs, traces and metrics, with W3C trace-context propagation. **[primary source read]** `OtelSettings` carries `environment`, `service_name`, `service_version`, `codex_home`, `exporter`, `trace_exporter`, `metrics_exporter`, `runtime_metrics`, `span_attributes` and `tracestate`. Token usage is a metric: `codex.turn.token_usage`, alongside `codex.goal.token_count`, `codex.api_request.duration_ms`, `codex.turn.e2e_duration_ms`, `codex.tool.call` and others — all under `codex.*`, none under `gen_ai.*`. **[primary source read]**

Three findings that matter more than the attribute list:

1. **The defaults are not neutral.** From `codex-rs/core/src/config/otel.rs`: `exporter` and `trace_exporter` default to `None`, but `metrics_exporter` defaults to **`Statsig`** — an OpenAI-internal ingestion exporter with a built-in endpoint (`https://ab.chatgpt.com/otlp/v1/metrics`) and API key. **[primary source read]** So a Codex lane left at defaults exports metrics off-box by default and nothing to our collector. Pointing it at `127.0.0.1:4318` is an explicit, required act, and anyone measuring a Codex lane should know where the default sends data.
2. **This surface is undocumented.** Grepping the public `docs/config.md` for "otel" and "telemetry" returns zero hits. **[primary source read — absence confirmed by direct grep]** The `[otel]` table is discoverable only by reading the crate. That makes it a moving target with no compatibility promise; an unannounced key rename would break the lane silently.
3. **`log_user_prompt` defaults to `false`.** **[primary source read]** Good default; worth asserting rather than assuming if the lane is ever wired.

Codex is not installed on this box — `which codex` finds nothing and `~/.codex` does not exist **[tested here]** — so none of the above is exercised, and the exact TOML key spellings (serde renames on `OtelConfigToml`) were **not** resolvable from the files I read. **[explicitly unverified]** Treat Codex's configuration surface as needing a hands-on spike before any ledger design commits to it.

### Summary of lane coverage

| | metrics | logs | traces | tokens where? | `cti.*` injectable? |
|---|---|---|---|---|---|
| Claude Code | yes, on | yes, on | beta, off | metrics + log records | yes, `OTEL_RESOURCE_ATTRIBUTES` |
| opencode | **none** | yes | yes | **spans only**, and only with `experimental.openTelemetry` | yes, `OTEL_RESOURCE_ATTRIBUTES` |
| Codex | yes (default → OpenAI) | yes | yes | `codex.turn.token_usage` metric | probably, via `span_attributes` — unverified |

Three lanes, three namespaces, three different signal types carrying the same fact. **The ledger's real work is normalisation**, and that is the part no off-the-shelf tool does for this particular trio.

## Community dashboards

`ColeMurray/claude-code-otel` is the closest thing to prior art: a docker-compose of OpenTelemetry Collector → Prometheus (metrics) → Loki (logs) → Grafana (dashboards), MIT licensed, four containers, six dashboard sections covering cost, tool usage, performance and event logs. No Tempo, so no traces. Retention is left to the operator's Prometheus and Loki config with no default durable archive. **[primary source read]**

Others in the same shape, found but not read in depth: `acreeger/claude-code-metrics-stack`, `NikiforovAll/ccdashboard` (offers a lighter .NET Aspire backend as an alternative to the Grafana stack), `rockdarko/claude-code-metrics-prometheus`, and a first-party Grafana Labs "Claude Code" dashboard for Grafana Cloud. **[documented, untested]**

**Verdict: not worth adopting, and the reason is not quality.** These are dashboards — they answer "what did I spend this week" by aggregating into a time-series database. The ledger answers "what did dispatch D, on issue #217, arm B, actually do, and what SHA did it land" — a per-record durable join to an external key, quoted into an issue months later. Prometheus is explicitly the wrong store for that: it is a sampling time-series database that drops labels at cardinality and retains by time, not a record store. Four containers running permanently on a box hosting an Arma server, to get a worse answer to a different question, is a bad trade.

The narrower point stands, though: if the human ever wants *weekly spend dashboards* rather than per-dispatch evidence, this stack is the ready-made answer and should be adopted rather than written. Those are different wants, and the ledger should not try to serve both.

## The four hosted candidates

**One fact disqualifies all four before any of the others matter: every one of them is a traces-only OTLP consumer.** None accepts OTLP metrics, none accepts OTLP logs. **[primary source read, per candidate below]** Our pipeline emits metrics and logs and no traces, and Claude Code's spend lives in `claude_code.token.usage` and `claude_code.cost.usage` — metrics. So adopting any of these means first re-instrumenting the Claude Code lane to emit spans (the unset `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA` beta), and even then the cost *metric* would still have nowhere to go. They ingest a different shape of telemetry than the one this box produces.

The second disqualifier is what they are for. All four are analytics products over a database — they answer "show me traces matching a filter", with retention as a policy knob. The ledger is an evidence artefact: a durable file, joined to an issue, quoted into a close months later, surviving whatever tool fashion prevails. A row in a ClickHouse table on a laptop is a worse `~/.arma-cti/runs/`.

### Langfuse

OTLP on `/api/public/otel` (alias `/api/public/otel/v1/traces`), HTTP/JSON and HTTP/protobuf, gRPC not supported. **Traces only.** **[primary source read]** External key: `metadata` key-value pairs, filterable in UI and API — a genuine fit for an issue number. **[primary source read]** Self-hosting is six containers from the official compose: `langfuse-web`, `langfuse-worker`, ClickHouse, Postgres, Redis, MinIO. **[primary source read]** No SQLite or single-binary mode. MIT core with a proprietary `ee/` tier that gates, among other things, **data retention management** — so configurable TTL is a paid feature, though self-hosted data is retained indefinitely by default. **[primary source read]** Minimum RAM/CPU is undocumented. **[could not verify]**

Verdict: the external-key story is exactly right and the operational cost is impossible. ClickHouse plus Postgres plus Redis plus MinIO, running permanently, on the box that runs the Arma tier's three slots, is the single heaviest option on the list bar Braintrust.

### Helicone

Flag first: Helicone was **acquired by Mintlify on 2026-03-03 and the hosted product is in maintenance mode**. **[primary source read]** That alone rules it out for a durable evidence store.

OTLP ingestion is unconfirmed and probably absent — the docs index carries zero otel/otlp pages, and the only path found is a `HeliconeAsyncLogger` OpenLLMetry wrapper rather than a documented OTLP endpoint. **[primary source read, incomplete]** The product is proxy-first: you route model calls through it. External key: "custom properties" via `Helicone-Property-*` headers, filterable. **[primary source read]** Self-host is one `helicone-all-in-one` container, which sounds light until you read what it bundles — Postgres, ClickHouse and MinIO internally, so it is three stateful services wearing one container, not a no-DB mode. **[primary source read]** Apache 2.0. **[primary source read]** Self-hosted provider support is restricted to OpenAI and Anthropic, which excludes the z.ai GLM lane outright.

Verdict: wrong architecture (a proxy, not a capture bus), unmaintained, and does not cover one of the two target lanes.

### Braintrust

OTLP at `/otel/v1/traces`, **traces only**, mapping `gen_ai.*` attributes into its own span model. **[primary source read]** External key: `metadata` and `tags`, queryable via BTQL. **[primary source read]** Self-hosting is a hybrid — "data plane in your infra, control plane hosted by Braintrust" — requiring Postgres 17+, Redis 7+, S3-compatible storage and the proprietary Brainstore engine, three to five containers, and it phones home regardless. **[primary source read]** The platform is closed-source proprietary SaaS; only the SDKs and the deployment repo are open. Free tier retains 14 days. **[primary source read]**

Verdict: not self-hostable in any sense this project means. A hosted control plane is a permanent external dependency on a machine whose whole telemetry design is deliberately loopback-only.

### Arize Phoenix

The closest of the four, and worth stating why it still loses.

OTLP at `/v1/traces` over HTTP/protobuf, plus gRPC on 4317. **Traces only.** **[primary source read]** External key: span `metadata`, `tags`, `session.id` and `user.id` via context managers, metadata being an arbitrary dict serialised into a span attribute. **[primary source read]** Caveat: filtering the UI or API on *arbitrary metadata keys* is unconfirmed and an open enhancement issue suggests it is missing — `session.id` and `user.id` appear to have first-class filtering, arbitrary metadata may not. **[documented, untested]** That caveat bites precisely where we need it, since an issue number would be arbitrary metadata.

Operationally it is genuinely light: the shipped compose is two containers (`phoenix` + `postgres:16`), and there is a real no-DB-server mode — `uvx arize-phoenix serve` runs single-process in memory, or persists to a local SQLite file via `PHOENIX_WORKING_DIR`. **[primary source read; the SQLite specifics documented, untested]** Retention self-hosted is indefinite by default (`PHOENIX_DEFAULT_RETENTION_POLICY_DAYS=0`) and configurable per project. **[primary source read]** Licence is Elastic License 2.0 — source-available, prohibits offering it as a hosted service to third parties, which does not constrain personal use. **[primary source read]**

Verdict: **no, but it is the one to revisit if the question ever changes.** It fails on the same traces-only axis as the rest, and its arbitrary-key filtering is doubtful. But it is the only candidate that runs as one process against SQLite with no database server, so if this project ever wants to *browse* agent traces interactively — as opposed to holding durable per-dispatch evidence — Phoenix is the cheap way to try it, and it can be run ad hoc rather than continuously. It complements a file-based ledger; it does not replace one.

## `ccusage` — the one to adopt alongside, for a different job

`ccusage` reads local session files from coding-agent CLIs; it is a one-shot CLI, not a daemon, MIT licensed, and keeps no store of its own — it is purely a reader of files that already exist. **[primary source read]** Subcommands are temporal: `daily`, `weekly`, `monthly`, `session`, plus `blocks` for five-hour billing windows and `statusline`.

The finding that makes it interesting here: **it already reads all three of our lanes.** Its documented sources include Claude Code (`~/.claude/projects/`, overridable by `CLAUDE_CONFIG_DIR`), Codex (`${CODEX_HOME:-~/.codex}`) and OpenCode (`${OPENCODE_DATA_DIR:-~/.local/share/opencode}`), among a dozen others. **[primary source read]**

But it cannot be the ledger. Its grouping keys are time and Claude *project* directory (`--project`, `--instances`) — there is no arbitrary external key, so no issue number, no arm, no SHA. **[primary source read]** And it reads session transcripts, not OTel, so it sits entirely outside ruling 10's capture bus.

What it is genuinely good for is **an independent cross-check on the ledger's cost arithmetic across all three lanes at once**, from a different data source, at zero standing cost. That is worth having precisely because the ledger's per-lane cost normalisation is the part most likely to be quietly wrong — opencode reports tokens and no cost, so the ledger must price them itself, and a second opinion computed from transcripts would catch a mispriced model.

## What must be built

Given the above, the ledger is roughly one recipe and one reader, not a service.

1. **Collector config** (human-gated — `/etc/otelcol-contrib/config.yaml` is production): the additive `filter/cti` processor, the `file/ledger` exporter with `group_by`, and two — eventually three, once opencode's traces matter — new pipelines. Tested shape given above.
2. **Dispatch-time attribute injection**: whatever mints a dispatch sets `OTEL_RESOURCE_ATTRIBUTES` in the child's environment with `cti.dispatch_id` and whatever else the join needs, constraining the id to a filesystem-safe, US-ASCII, space-free alphabet. The alphabet constraint is not optional — it is load-bearing for both the collector's path handling and Claude Code's documented format rules.
3. **`just ledger-sync`**: much smaller than ruling 11 assumed. The collector has already produced `dispatch-<id>.jsonl`, already filtered and already durable. What remains is the *join and normalisation*: read that file, fold the three lanes' differing token attributes into one shape, attach the issue number, the arm, the gate verdict and the landed SHA, and write `outcome.json`. Per ADR-0049, the decision ladder and the aggregation are Python under pytest, not bash.
4. **Blobs stay files.** Nothing found argues against that half of ruling 11.

What does *not* need building: the filtering, the per-dispatch split, the durability, the append-across-restart, or any storage service.

## Amendments to rulings 10 and 11

**Ruling 10 (OTel as the single capture bus) stands, with one correction.** Nothing found displaces it, and the measured capture shows it already carries most of a ledger. The correction is that "all lanes" is not free: opencode publishes **no metrics at all**, so a metrics-and-logs bus cannot see opencode's spend. Ruling 10 survives only if the bus includes traces.

**Ruling 11 needs three amendments.**

1. *The traces pipeline is required, but for opencode, not for Claude Code.* Claude Code's traces are a beta behind an unset flag; opencode's spans are the only place its token counts exist. The rationale in the ruling should be corrected, or the pipeline will be built for the wrong reason and scoped wrongly.
2. *The filtered export should be `group_by`-split, not a single flat file.* The collector writes one file per dispatch natively. This removes the compaction step from `just ledger-sync`, makes retention a per-dispatch delete, and was tested here including across a collector restart.
3. *`dispatch.json` / `turns.jsonl` / `raw/` is more structure than the evidence needs.* The collector's own output is already the raw per-dispatch record, line-delimited, appended in arrival order. What `just ledger-sync` must add is the join — issue, arm, verdict, SHA — and the cross-lane normalisation. A single `outcome.json` beside the collector's file matches the corpus-evidence convention at `~/.arma-cti/runs/` more closely than a four-way split would.

One thing neither ruling anticipated: **`cti.dispatch_id` can only distinguish separate processes.** An in-session Claude Code subagent shares its parent's resource block, so the ledger's unit is a dispatched CLI invocation. If the intent was to ledger in-process subagents too, that needs a different mechanism — the existing `agent.name` / `agent_type` record attributes — and it cannot use `group_by`.

## What I could not verify

- The exact `[otel]` TOML key spellings for Codex, including serde renames on `OtelConfigToml`. The consuming code and the field list were read; the struct definition was not located. Codex is not installed here, so nothing about that lane is exercised.
- The traces leg of the fan-out and `group_by` test. Logs and metrics were exercised end to end; `trace_conditions` is documented in the same shape and was not run.
- Claude Code's trace span hierarchy and attributes, which come from the docs page rather than from observed output — the beta flag is not set on this box.
- Whether `group_by`'s `max_open_files` behaves gracefully at its limit; not probed.
- Retention behaviour of the four hosted candidates on their free tiers, beyond what their own docs claim.

## Reproducing the collector tests

The scratch configs and scripts used are not committed — they contain absolute scratch paths and were throwaway. The shape is fully given in the config sketch above; reproducing is: run a second `otelcol-contrib` on a spare port with `service.telemetry.metrics.level: none` (otherwise it collides with the live collector's 8888 and exits), `curl` OTLP JSON to `/v1/logs` and `/v1/metrics` with and without a `cti.dispatch_id` resource attribute, and inspect which files appear. The live collector is never involved.
