# The Codex lane, measured against the live CLI

**Question.** #243 asks four things, of which the first is a decision ADR-0061 deferred:
which substrate the Codex lane runs on — OpenAI's native `codex` CLI or `opencode` — with
the hook-parity suite of Decision 4 gating whichever gets authority. The other three are
consequences: telemetry parity, the registry wiring, and one live proof dispatch.

**Outcome.** The native `codex` CLI wins on all three axes that were in question, and two
of the findings invert what ADR-0061 expected. Hook parity is not merely *reachable* on
this substrate, it is nearly free: Codex sends Claude Code's own hook payload, down to the
tool names, so not one of the eight committed hooks needed editing. Telemetry parity
needed **no engineering at all** — the mechanism the dispatcher already uses for every
other lane works unchanged. And effort is a genuinely distinct dimension here, which is
the exact opposite of the z.ai lane, where five effort levels collapsed into one.

**Method.** Codex CLI 0.146.1, ChatGPT Plus, authenticated on this box before this work
began. Every claim below comes from the CLI itself — its own model cache, its own config
parser, its own hook execution, its own OTLP export — rather than from documentation.
Where the CLI is the only source and no second one exists, that is stated. Dated
2026-08-06.

**Standing caveat, inherited from #225 and equally true here.** These are single
observations against a hosted service on one evening, and a hosted service may change any
of them without telling us. What each finding is good for is a *registry decision now*,
re-checkable by re-running the arrangement in its section.

## 1. What the subscription actually reaches, and what the models are called

The human named "gpt-5.6 sol and terra" as the models of interest. Those are not
identifiers, and the identifiers were read rather than guessed, from the authenticated
CLI's own cache at `~/.codex/models_cache.json` (`fetched_at`
2026-08-05T18:47:11Z, `client_version` 0.146.1) — eight entries:

| slug | display name | catalogue default effort | visibility |
|---|---|---|---|
| `gpt-5.6-sol` | GPT-5.6-Sol | `low` | listed |
| `gpt-5.6-sol-wm` | GPT-5.6-Sol-WM | `low` | hidden |
| `gpt-5.6-terra` | GPT-5.6-Terra | `medium` | listed |
| `gpt-5.6-luna` | GPT-5.6-Luna | — | listed |
| `gpt-5.5` | GPT-5.5 | — | listed |
| `gpt-5.4` | GPT-5.4 | — | listed |
| `gpt-5.4-mini` | GPT-5.4-Mini | — | listed |
| `codex-auto-review` | Codex Auto Review | — | — |

So the registry names `gpt-5.6-sol` and `gpt-5.6-terra`. `gpt-5.6-sol-wm` is a "Work Mode
routing alias" the catalogue marks `visibility: hide` and `supported_in_api: false`, and
registering an alias beside the thing it aliases would be the same non-distinction
ADR-0061 Decision 5 exists to prevent.

Each model publishes its own `supported_reasoning_levels`, and for both registered models
that list is six: `low`, `medium`, `high`, `xhigh`, `max`, `ultra`. Note this is
first-party *publication* of an effort vocabulary, which z.ai did not offer — but
publication is not behaviour, which is §3.

## 2. The config schema, verified rather than inferred

#230 wrote `~/.codex/config.toml` with `metrics_exporter = "none"` and recorded the key
spellings as **UNVERIFIED**, because the `[otel]` table is absent from Codex's public
`docs/config.md` and the spellings came from reading the Rust struct. That flag can now be
cleared, on an oracle the CLI supplies itself.

`codex exec --strict-config` errors on unknown configuration fields. Pointed at a
throwaway `CODEX_HOME` with no credential, it parses the config and *then* fails on auth,
so the two failures are cleanly distinguishable:

    $ codex exec --strict-config -c 'otel.bogus_key="x"' …
    Error loading config.toml: …:2:1: unknown configuration field `otel.bogus_key`

    $ codex exec --strict-config -c 'otel.metrics_exporter="none"' …
    ERROR … failed to connect to websocket: HTTP error: 401 Unauthorized

Every key #230 guessed is real: `otel.exporter`, `otel.metrics_exporter`,
`otel.trace_exporter`, `otel.log_user_prompt`, `otel.environment`, `otel.span_attributes`.
The exporter value is an enum where `"none"` and `"statsig"` are unit variants and the OTLP
ones are struct variants — `exporter = "otlp-http"` fails with *"invalid type: unit
variant, expected struct variant"*, while
`{ otlp-http = { endpoint = "…", protocol = "binary" } }` parses.

**What this settles for the config file on this box**: it says what it was meant to say.

## 3. Effort is a real dimension, which is the inverse of z.ai

#225 found z.ai's endpoint ignored `thinking.budget_tokens` entirely: one hard prompt at
budget 1,024 and at 32,000 were indistinguishable, so five Claude effort levels became one
registered profile. The same question, asked the same way here, answers the other way.

The first attempt did not discriminate, and the reason is worth recording because it is
the trap #225's method exists to avoid. Asked to count the domino tilings of a 4×6
rectangle — the arrangement #225 used — `xhigh` spent **57 reasoning tokens** and answered
281 correctly. That is a memorised constant, not a computation, and a memorised answer
costs the same at every effort. A prompt that cannot be recalled was needed.

Second arrangement, non-memorisable: a 4×10 grid with two named cells removed, count the
tilings of the remaining 38 cells, work it out by hand. Same prompt, same model
(`gpt-5.6-terra`), identical input token counts, one variable:

| `model_reasoning_effort` | `input_tokens` | `cached_input_tokens` | `output_tokens` | `reasoning_output_tokens` |
|---|---|---|---|---|
| `low` | 15,990 | 11,008 | 492 | **484** |
| `xhigh` | 15,990 | 11,008 | 2,401 | **2,393** |

A factor of 4.9 in reasoning tokens on identical input. The levels decide something, so the
registry carries levels.

**What this decides.** Four profiles, not one and not twelve: `codex-sol-xhigh`,
`codex-sol-high`, `codex-terra-medium`, `codex-terra-low`. Two of the six published levels
are deliberately unregistered. `ultra` is described by the provider as "maximum reasoning
with automatic task delegation" — a different execution model rather than a deeper one, and
an arm that may spawn its own work is not something to hand a seat before it is understood.
`max` is simply unmeasured.

**Stated limit**: the factor of 4.9 was measured on `terra` only. The `sol` profiles rest
on the catalogue publishing the same six levels for both, not on a second measurement.

## 4. Hook parity: proven, and it needed no hook edited

ADR-0061 Decision 4 makes a lane's authority the enforcement it demonstrably runs, and
names the specific way a parity claim goes wrong — "the suite asserting on its own mock
rather than the lane's real denial path". So the denial was put to the real lane first.

Codex 0.146.1 accepts a `[hooks]` table with the event names `PreToolUse`,
`PermissionRequest`, `PostToolUse`, `PreCompact`, `PostCompact`, `SessionStart`,
`SessionEnd`, `SubagentStart`, `SubagentStop` and `UserPromptSubmit`. A probe hook was
attached to `PreToolUse` and a Codex turn was asked to run two shell commands, the second
of which wrote a tripwire file.

    2026-08-06T03:26:26Z ERROR codex_core::tools::router:
      error=Command blocked by PreToolUse hook: denied by arma-cti parity probe.
      Command: echo blocked > TRIPWIRE.txt

`echo hello` succeeded, the tripwire command was blocked, `TRIPWIRE.txt` did not exist
afterwards, and the hook's stderr reached the model, which reported the block accurately.
**Exit code 2 denies, exactly as it does in Claude Code.**

The payload the probe captured is the finding that made everything else cheap:

```json
{
  "session_id": "019fd51b-835f-7732-8855-a73841a75d4c",
  "turn_id": "019fd51b-83ef-7353-857d-48fa291cb290",
  "transcript_path": "/home/andre/.codex/sessions/…/rollout-….jsonl",
  "cwd": "/tmp/codex-probe-243",
  "hook_event_name": "PreToolUse",
  "model": "gpt-5.6-terra",
  "permission_mode": "bypassPermissions",
  "tool_name": "Bash",
  "tool_input": { "command": "echo hello" },
  "tool_use_id": "exec-ae6f66c0-…"
}
```

`tool_name` is **`Bash`** — Claude Code's tool name, not Codex's internal `shell`. Every
hook in `.claude/hooks/` reads `tool_name` and `tool_input` and nothing else, so all eight
run unedited. That is why `tools/hook_parity.py` is a translation of *configuration* and
contains no reimplementation of any hook.

**The one thing that does not carry** is `$CLAUDE_PROJECT_DIR`, which the command strings
in `.claude/settings.json` interpolate and Codex does not set. It is resolved at
translation time into an absolute path, so a missing hook script is a checkable condition
before a dispatch rather than a silent no-op during one.

**One friction worth recording.** Codex gates a newly seen or edited hook behind an
interactive "review required" prompt keyed on a stored `trusted_hash` — right for a human
at a terminal, a hang for a detached child. `--dangerously-bypass-hook-trust` declines the
re-prompt without disabling hooks, and the dispatcher passes it. The hooks it then runs are
this repository's own committed ones, already governed by the gate that no session may edit
them.

**Authority, under Decision 4**: the two events this repository configures — `PreToolUse`
and `PostToolUse` — both fire, and the denial path is proven for `PreToolUse`. The suite in
`tests/unit/test_hook_parity.py` runs the real scripts against this captured payload.

## 5. Telemetry parity needed no engineering

ADR-0061's prior-art sweep found no off-the-shelf OTel hook target for Codex and concluded
this would be engineering. It is not, and the reason is one measurement.

The collector's `filter/cti` keys on `resource.attributes["cti.dispatch_id"]`, so the
question is whether Codex's OTel resource block can be made to carry our six `cti.*`
attributes. Two candidate mechanisms were tried in one run, against a throwaway OTLP sink
on loopback that stored every batch verbatim:

| mechanism | appeared in the exported resource block |
|---|---|
| `OTEL_RESOURCE_ATTRIBUTES` environment variable | **yes — all 7 batches** |
| `otel.span_attributes` config table | no — 0 batches |

`OTEL_RESOURCE_ATTRIBUTES` is exactly what `assemble_environment` already sets for every
lane. So the dispatcher's existing identity mechanism carries over with nothing added, and
`otel.span_attributes` is not used.

One measured detail that would otherwise have cost a debugging session: **Codex POSTs to
the endpoint verbatim** rather than appending a signal path to a base. Given
`http://127.0.0.1:4319`, every batch arrived at `/`. The lane therefore configures the full
`http://127.0.0.1:4318/v1/metrics`, which is what the collector's OTLP receiver expects.

### 5.1 Two defects this found in the ledger, both fixed

The first Codex dispatch produced a ledger row reading `in=0 out=0` beside 49 records. Two
distinct causes, and the second is the more serious:

1. **Shape.** `codex.turn.token_usage` is a **histogram**, not a sum, and it is keyed by
   `token_type` rather than Claude Code's `type`. The reader knew only `sum` and `gauge`.
2. **A silent drop, against the module's own promise.** `tools/ledger.py`'s docstring says
   "A metric or attribute whose shape it does not recognise is reported in `unclassified`,
   never silently dropped." That held for an unrecognised *attribute* and not for an
   unrecognised *body*: a body shape the reader did not know yielded no datapoints at all,
   so the metric never reached the net meant to catch it. `unclassified` was empty while
   the whole of the dispatch's token usage went missing.

A third trap was avoided rather than fixed. Codex emits **six** `token_type` values per
turn and only four of them partition it: `total` is input plus output, and
`reasoning_output` is a *subset* of `output`. Bucketing either would have inflated every
Codex row — `total` alone would have doubled it — with nothing downstream to disagree.
Those two are named in `NON_DISJOINT_TOKEN_TYPES` so the exclusion is findable rather than
inferable from an absence.

Row after the fix, from the proof dispatch, matching the export's histogram sums exactly:

    input_tokens 16,089 · output_tokens 27 · cache_read_tokens 11,008 · cache_creation_tokens 0

Worth noting against #225: Codex reports the **cache-write half**, which z.ai does not. A
zero there from this lane is a measurement; the same zero from the z.ai lane is a silence.

## 6. The off-box exporter is silent, and how that was established

Codex's `metrics_exporter` defaults to `Statsig`, an OpenAI-internal exporter with a
built-in endpoint at `https://ab.chatgpt.com/otlp/v1/metrics`. #230 disabled it before
first use; #243 owed the verification with the network watched.

**First attempt, and why it proved nothing.** Watching `ss` for connections to
`ab.chatgpt.com`'s addresses cannot discriminate: `ab.chatgpt.com` and `chatgpt.com`
resolve to the *same* Cloudflare A records on this box — `104.18.32.47` and
`172.64.155.209`. A connection to either is consistent with both the API and the metrics
endpoint. Recorded because an IP-level all-clear here would have been worthless.

**Second attempt, discriminating.** TLS SNI is cleartext, so `strace -f -e trace=network`
on the run reads the hostname each connection actually asked for, and needs no root:

| observation | count |
|---|---|
| TLS ClientHello SNI `chatgpt.com` (length prefix `\v` = 0x0b = 11 = `len("chatgpt.com")`) | 16 |
| TLS ClientHello SNI `ab.chatgpt.com` | **0** |
| the string `ab.chatgpt.com` anywhere in the trace | **0** |
| the string `statsig` anywhere in the trace, any case | **0** |
| `connect()` to `127.0.0.1:4318` (our collector) | 2 |

One earlier appearance of `ab.chatgpt.com` in a trace is accounted for rather than waved
away: it was a `write()` of `~/.codex/config.toml`'s own text, whose comment block — the
one #230 wrote — quotes the endpoint while explaining what is being disabled. Our
documentation, not a packet.

**A structural argument stands behind the observation**, which matters because absence of
evidence is weak on its own: `metrics_exporter` is a single-valued enum in the schema §2
verified, so setting it to `otlp-http` means the Statsig exporter is not constructed at
all. The positive control is that the metrics demonstrably went somewhere — 155 records
carrying this dispatch's `cti.dispatch_id` reached the loopback collector.

**What this does not establish**: that no *other* OpenAI telemetry path exists. The claim
is about the OTel metrics exporter, which is the one that had an off-box default.

## 7. Why not `opencode`

Both candidates were examined; the CLI won on each axis that was in question.

| | `codex` CLI 0.146.1 | `opencode` 1.18.13 |
|---|---|---|
| Reaching the subscription | already authenticated, `~/.codex/auth.json` at 0600 | its own OAuth flow (provider `openai`, method "ChatGPT Pro/Plus"), a **second** credential store, currently empty |
| Reads `~/.codex/auth.json` | n/a — it owns it | **no** (no `CODEX_HOME` or `.codex/auth` reference in the bundle) |
| Hook denial | Claude Code's payload and exit-2 convention, proven in-world | exists, as a TypeScript plugin setting `output.status = "deny"` on `permission.ask` — a shim we would own |
| Telemetry | first-class `[otel]`, OTLP exporters, honours `OTEL_RESOURCE_ATTRIBUTES` | OTel SDK vendored and env vars honoured, but **active emission unverified**; no exporter config of its own |

`opencode` is permitted by the human's 2026-08-06 ruling and is not rejected on policy. It
loses on evidence: a second credential store for no gain, a veto we would have to write and
maintain rather than a protocol we already speak, and a telemetry path that could not be
shown to emit. ADR-0061 left open that "both may hold" — `opencode` remains a live
candidate for #234's Herma lane, whose endpoint is OpenAI-compatible and whose natural
clients are exactly such harnesses. Nothing here forecloses that.

## 8. The lane, end to end, once

`just dispatch --lane codex --profile codex-terra-low --seat recon --issue 243`, dispatch
**`d-20260806-033344-18a832`**, exit 0 in 9.1 s. The task was deliberately inert — name your
lane, touch nothing — and the worktree was a throwaway git repository outside this
checkout.

| Claim | Evidence |
|---|---|
| Auth reaches ChatGPT Plus, with no credential of ours | exit 0; `auth_mode="Chatgpt"` on every metric datapoint; nothing in `~/.arma-cti/credentials.env` is read for this lane |
| The profile's model reaches the wire | the run banner reports `model: gpt-5.6-terra`, and every `codex.turn.token_usage` datapoint carries `model="gpt-5.6-terra"` |
| The profile's effort reaches the wire | the run banner reports `reasoning effort: low` |
| Identity survives to the collector | all six `cti.*` resource attributes on the export; `cti.lane=codex` among them |
| A ledger row prices it against the right pool | `pool: "codex"`, `class: "ok"`, 155 records from a non-degraded source |
| The admission boundary is honoured | the ladder ran and refused nothing; `cap_fraction` is typed `no-estimator` rather than estimated |
| The off-box exporter stays silent | §6 |

**What this run does not prove.** The hook overrides did not ride on it: the proof worktree
carries no `.claude/settings.json`, so the enforcement path exercised in-world was §4's
probe rather than this dispatch. And as with #225, what this proves is the lane's plumbing,
nothing about what the model is fit for — that is the admission bar's question, and no
Codex-produced work has landed in this repository.

## 9. What a reader should not take from this

- Not that the four registered profiles are the right four. They are a seed set; which
  profile suits which seat is ADR-0061 Decision 6's paired-dual-run question and is not
  touched here.
- Not that the Codex pool is priced. It is typed `no-estimator` and deliberately so: the
  **numerator** is present (Codex reports per-turn output tokens on the bus) and the
  **denominator** is missing (how many output tokens make one percentage point of a
  ChatGPT Plus window is unpublished and unmeasured). This is the mirror image of the z.ai
  pool, which has the denominator and lacks the numerator. #218's method applies unchanged
  when a calibration is spent; #243 deliberately did not spend one.
- Not that effort levels commensurate with Claude's. ADR-0061 Decision 5's
  non-monotonicity finding stands: nothing here compares quality across providers, and
  `xhigh` on this lane is not `xhigh` on Claude.
- Not that the six published reasoning levels are six distinct arms. Two adjacent levels
  were shown distinct; the other four pairs were not tested.
