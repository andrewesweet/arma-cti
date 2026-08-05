# The prior art for routing agent work across providers, and which of it we should not build

**Researched**: 2026-08-05
**Question** (R1, for the five rulings held at the end of ADR-0061): the multi-provider dispatch initiative plans a substrate spike, a whole-run dispatch granularity, and a bespoke per-lane circuit breaker. Prior art may already solve those better. CLAUDE.md's standing rule — do not build what already exists — has cost this project a day and a redundant code generator when it was skipped.
**Answer in one line**: **none of the five held rulings is overturned — the two candidates ADR-0061 expected to replace rulings 12 and 16 both fail, on different grounds.** `claude-code-router` does route per request type, but reaches an Anthropic subscription by reading `~/.claude/.credentials.json` and replaying the OAuth token at `api.anthropic.com` — the practice Anthropic's Consumer Terms §3 bars and which `opencode` deleted in v1.3.0 with the words "Anthropic explicitly prohibits this"; with that path closed, no proxy can route *part* of a session to the subscription, because `ANTHROPIC_BASE_URL` is session-global and subscription OAuth does not survive being pointed at a gateway. LiteLLM's cooldowns turn out to be a five-second reactive rate-limit damper with no quality trip, no supported way to add one, and transitions that cannot reach OTel. What the sweep does buy is smaller and real: **`acpx` is the lane façade we were about to invent**, and **Codex publishes its own quota state at `account/rateLimits/read`**, which removes half the breaker we were about to write.

---

## 0. Method and limits

**What was read.** Repository source and official specification pages, not write-ups about them: the `claude-code-router` tree at tag `v2.0.0` and at `main`, `BerriAI/litellm` at pinned commit `b735578822613df8eb2eab6e7082e8890f5bf4b4`, the `openai/codex` tree via the GitHub contents API, the `sst/opencode` docs source, the Agent Client Protocol specification pages, `acpx`'s CLI reference, Anthropic's Claude Code documentation and Consumer Terms, and z.ai's devpack documentation.

**Evidence class is stated per claim**, in three grades used throughout:

- **primary source read** — the file, clause, or spec page was fetched and the quoted text is verbatim from it.
- **documented but untested** — an official document asserts it; nothing here ran it.
- **inferred** — a conclusion drawn from the above, flagged as reasoning rather than fact.

**Limits.**
- **Nothing here was executed.** No substrate was installed, no lane was dispatched, no proxy was started. Every operational-cost figure is read off documentation, not measured on this box. The spike ruling 5 calls for is not discharged by this document and should not be treated as discharged.
- **Version churn is the main hazard.** `claude-code-router` shipped v3.0.19 on the day of this research and had restructured so far that the routing file this brief asked about returns 404 on `main`. Findings below are pinned to a version wherever the version matters.
- **One negative finding is soft.** Absence of token-refresh logic in `claude-code-router` is "not found by a targeted read", not "proven absent".
- Sibling dispatches cover telemetry (OTel), portability (APM), and the evaluation regime. This document stops at the routing substrate and the façade, and does not re-decide those.

---

## 1. The constraint that decides most of the sweep

Ruling 5 carries one part that is not held and is absolute: **the Anthropic subscription is reached only ever through Claude Code**. Everything else in this document is downstream of how that constraint interacts with the mechanism every proxy candidate uses.

**`ANTHROPIC_BASE_URL` is session-global.** Claude Code's documentation describes it as the way "to route requests to a custom endpoint or gateway"; there is no documented per-request, per-model, or per-subagent base-URL override. A subagent may pin a `model` in its frontmatter, but not a base URL. — *documented*, https://code.claude.com/docs/en/llm-gateway-connect, https://code.claude.com/docs/en/env-vars, https://code.claude.com/docs/en/subagents.

**Subscription OAuth does not survive being pointed at a gateway.** Claude Code's credential precedence puts cloud-provider credentials, then `ANTHROPIC_AUTH_TOKEN`, then `ANTHROPIC_API_KEY`, then `apiKeyHelper`, then `CLAUDE_CODE_OAUTH_TOKEN`, and only last the subscription OAuth obtained by `/login`; the gateway documentation instructs setting an explicit credential variable alongside the base URL. — *documented*, https://code.claude.com/docs/en/authentication. The docs do not print the sentence "subscriptions are incompatible with custom base URLs", so this is **inferred** from the precedence order plus every documented gateway example using an explicit key. It is the reading the implementations agree with, below.

**The terms bar the workaround directly.** Anthropic's Consumer Terms, §3 *Use of our Services*, prohibit:

> "Except when you are accessing our Services via an Anthropic API Key or where we otherwise explicitly permit it, to access the Services through automated or non-human means, whether through a bot, script, or otherwise."

and §2 prohibits sharing account credentials:

> "You may not share your Account login information, Anthropic API key, or Account credentials with anyone else or make your Account available to anyone else."

— *primary source read*, https://www.anthropic.com/legal/consumer-terms. Claude Code is Anthropic's own product and is therefore the "explicitly permit it" case; a third-party process replaying the same OAuth token is not.

**An implementer confirms the reading by having removed the feature.** `opencode`'s own provider documentation says, verbatim:

> "There are plugins that allow you to use your Claude Pro/Max models with OpenCode. Anthropic explicitly prohibits this.
>
> Previous versions of OpenCode came bundled with these plugins but that is no longer the case as of 1.3.0
>
> Other companies support freedom of choice with developer tooling - you can use the following subscriptions in OpenCode with zero setup:
>
> - ChatGPT Plus
> - Github Copilot
> - Gitlab Duo"

— *primary source read*, `packages/web/src/content/docs/providers.mdx` in `sst/opencode`, lines 356–369.

That is two independent sources — the rights-holder's terms and an implementer that shipped the capability and then withdrew it — pointing the same way. **Ruling 5's hard constraint is not merely a policy choice this project made; it is the only compliant configuration available.** It should be treated as settled rather than spiked.

**The mirror stays permitted, and is already a first-class path.** ADR-0061 allows the `claude` binary to drive a non-Anthropic endpoint, since that consumes no Anthropic quota, credential or traffic. z.ai documents exactly this as its supported integration: set `ANTHROPIC_BASE_URL` to `https://api.z.ai/api/anthropic` with `ANTHROPIC_AUTH_TOKEN` set to a z.ai key, and map the model slots with `ANTHROPIC_DEFAULT_OPUS_MODEL=glm-5.2`, `ANTHROPIC_DEFAULT_SONNET_MODEL=glm-5.2`, `ANTHROPIC_DEFAULT_HAIKU_MODEL=glm-4.7`. — *primary source read*, https://docs.z.ai/devpack/tool/claude. Nothing in the sweep disturbs this, and no proxy is needed to achieve it.

---

## 2. `claude-code-router` — the candidate that fails on the constraint, not on capability

**What it is.** A local HTTP server that speaks the Anthropic Messages API, translates to other providers, and gets Claude Code to talk to it by overriding the base URL. MIT, 36,424 stars, 1,052 open issues, last push 2026-08-05 — *primary source read*, GitHub API, observed 2026-08-05.

**It has restructured under the question.** The `default` / `background` / `think` / `longContext` / `webSearch` category router this brief asked about is **v2.0.0 and earlier**. `packages/core/src/utils/router.ts` returns 404 on `main`; current `main` is v3.0.19, published the day of this research. Both are reported below because the decisive answer differs between them.

### 2.1 Interception (v2.0.0) — primary source read

`packages/cli/src/utils/createEnvVariables.ts`, complete:

```typescript
return {
  ANTHROPIC_AUTH_TOKEN: apiKey,
  ANTHROPIC_BASE_URL: `http://127.0.0.1:${port}`,
  NO_PROXY: "127.0.0.1",
  DISABLE_TELEMETRY: "true",
  DISABLE_COST_WARNINGS: "true",
  API_TIMEOUT_MS: String(config.API_TIMEOUT_MS ?? 600000),
  CLAUDE_CODE_USE_BEDROCK: undefined,
};
```

The token is CCR's own local gateway key (`config.APIKEY`, defaulting to the literal `"test"`), not an Anthropic credential. `ccr code` then spawns the real binary (`config?.CLAUDE_PATH || process.env.CLAUDE_PATH || "claude"`). Port defaults to 3456; config at `~/.claude-code-router/config.json`.

**It also reads `~/.claude/projects`** — the Claude Code session transcript directory — to map session ids to projects for project-scoped routing. Worth knowing before pointing it at this repo.

### 2.2 Per-request-type routing (v2.0.0) — primary source read

All rules in `getUseModel`, evaluated in this order:

1. **explicit override** — `req.body.model` containing a comma is split into `provider,model` and used directly.
2. **`longContext`** — checked first. `longContextThreshold` defaults to **60000**; triggers when `tokenCount > threshold`, or when the *previous* response's `input_tokens` exceeded the threshold and this request exceeds 20000.
3. **subagent tag** — `system[1].text` beginning `<CCR-SUBAGENT-MODEL>` names the model explicitly.
4. **`background`** — pure model-name substring matching: `req.body.model` must contain **both** `"claude"` and `"haiku"`.
5. **`webSearch`** — any tool whose `type` starts with `web_search`; carries an explicit comment that it must outrank thinking.
6. **`think`** — presence of the `req.body.thinking` field.
7. otherwise `default`.

Token counting uses tiktoken `cl100k_base` — an **OpenAI encoding used as an approximation for Anthropic content**. There is no `image` category; the scenario type is exactly `'default' | 'background' | 'think' | 'longContext' | 'webSearch'`.

So the categories are real but **coarser than the name suggests**: `background` is not "this is a background task", it is "the model string says haiku". That matters for ruling 12, because it means the proxy is not classifying *work*; it is reading a decision Claude Code already made and re-targeting it.

A `CUSTOM_ROUTER_PATH` CommonJS hook is `require`d and called as `customRouter(req, config, { event })`, returning `"provider,model"` or falsy to fall through. The v2 docs describe a different signature (`function(config, context)`) — a **doc/code mismatch**, flagged rather than resolved.

### 2.3 What v3 did to the categories — primary source read

**The named categories are gone.** Built-in routing for Claude Code in v3 is (a) Agent-Profile alias mapping through the `ANTHROPIC_DEFAULT_*_MODEL` env vars, and (b) the `<CCR-SUBAGENT-MODEL>` tag. `packages/core/src/agents/claude-code/environment.ts` sets only model-selection env — including `ANTHROPIC_DEFAULT_FABLE_MODEL`, so it already knows this project's tier.

Replacing the ladder is a generic conditional rule engine (`condition` over `request.body.*` / `request.header.*` / `request.auth.*` with `starts with`, `contains`, comparison operators; `rewrites` with `set`/`delete`/array ops; fallback `off`/`retry`/`model-chain`) plus a sandboxed script rule receiving `input.tokenCount`, `input.summary.lastUserText`, `input.summary.toolNames`, `input.summary.hasImage` and similar. The v2 categories are **reconstructible** in that engine — *inferred* from the documented input surface — but are no longer supplied.

This is the most useful signal in the whole candidate: **the leading per-request-type router abandoned per-request-type routing** and moved to the model-slot env vars Claude Code exposes natively. It is weak evidence that the granularity in ruling 12 is not where the value is.

### 2.4 The subscription question — primary source read, and it disqualifies the tool

In **v2**, upstream Anthropic auth is API-key only: `packages/core/src/transformer/anthropic.transformer.ts` sets `x-api-key`, or `Authorization: Bearer` under a `UseBearer` option, with no OAuth handling and no `anthropic-beta: oauth-2025-04-20`.

In **v3**, `packages/core/src/agents/local-providers/claude-code.ts` implements precisely the prohibited path. It locates the Claude Code login:

```javascript
path.join(claudeCodeStorageDir(), ".credentials.json"),
path.join(os.homedir(), ".claude", ".credentials.json"),
path.join(os.homedir(), ".claude", "credentials.json"),
path.join(os.homedir(), ".config", "claude", "credentials.json")
```

(on macOS additionally shelling out to `security dump-keychain` and `security find-generic-password`), reads the `claudeAiOauth` field, and builds upstream auth as:

```javascript
const auth = bearerAuthPlugin("claude-code-oauth", token, {
  "anthropic-beta": "oauth-2025-04-20"
});
```

It is a documented user-facing feature: "Claude Code import reads local Claude Code OAuth credentials. When a usable access token is available, CCR can import it as a `Claude Code API` provider."

**This is the answer to the brief's decisive question, and it is the opposite of good news.** The capability exists — so `claude-code-router` *can* route some categories to Anthropic-on-subscription and others elsewhere — but the mechanism is a third-party process reading the credential file and replaying the token, which is what §1 establishes is barred. The tool solves ruling 12's granularity problem by doing the one thing ruling 5 forbids.

Supporting detail, all verified: the built-in Anthropic *transformer* still has no OAuth — PR #1408 adding it is **open and unmerged** as of 2026-08-05. **No token-refresh logic was found** (the refresh token is stored but only the access token used), so an imported provider goes stale on expiry — *soft negative*. Open issue #1528, "OAuth provider plugin overwrites client `anthropic-beta` header", is directly hazardous to this project, since that header is how cache-TTL and long-context betas are requested.

**No terms-of-service discussion exists in the repo.** Searches on `subscription`, `terms of service` and `ban` returned only technical threads (#482 "Combining Pro / Max Subscription Access with API Keys in CCR", #1219, #1274, #1408, #1528). Not all 1,052 open issues were read. Absence of the discussion is not permission; the repo simply does not raise the question.

### 2.5 Prompt caching — primary source read

`cache_control` handling is **explicit and opt-in per provider**. `packages/core/src/transformer/cleancache.transformer.ts` exists solely to strip breakpoints:

```typescript
if ((item as TextContent).cache_control) {
  delete (item as TextContent).cache_control;
}
```

It is not applied globally; it exists because non-Anthropic providers reject the unknown field. The Anthropic transformer preserves `cache_control` on system blocks and tool results.

**No cache-TTL handling was found anywhere** — nothing that understands `{"type": "ephemeral", "ttl": "1h"}` versus the five-minute default. Stated as *not found*, not *absent*. Whether the OpenAI/Gemini/DeepSeek transformers strip `cache_control` themselves or rely on `cleancache` being configured was **not verified**, nor was whether `cache_creation_input_tokens` / `cache_read_input_tokens` survive the response translation back to Claude Code.

Given that this project's measured bill is 68.5% cache reads and 27.0% cache writes (`docs/research/token-efficiency.md` §1), an unaudited translation layer between Claude Code and its cache accounting is a material risk, independent of the licensing question.

### 2.6 Verdict

**Reject for the Anthropic lane, on ruling 5. Do not adopt for the other lanes either, on cost-benefit.**

The non-Anthropic lanes do not need it: z.ai already publishes an Anthropic-shaped endpoint and the model-slot env vars reach it with no proxy at all (§1). What CCR would add over that is multi-provider fan-out inside one session — which is ruling 12's granularity, which §2.3 shows its own author retreated from. Against that: a 1,052-issue MIT project that restructured incompatibly between v2 and v3 in under a year, an unaudited cache-translation layer, and a component that reads this project's credential file and session transcripts.

*Evidence class: mechanism and code — primary source read; the cost-benefit conclusion — inferred.*

---

## 3. LiteLLM — solves the lane-authentication problem, does not solve the breaker

Read at pinned commit `b735578822613df8eb2eab6e7082e8890f5bf4b4` on `main`, ~2026-08-05. MIT, except the `enterprise/` directory. Everything relevant below is in the OSS half — cooldowns, all routing strategies, fallbacks, budgets, Prometheus, and OpenTelemetry are free.

### 3.1 The cooldown mechanism is not a circuit breaker in our sense — primary source read

**There is no deployment-level setting named `circuit_breaker`.** The only `circuit_breaker` in the tree is `RedisCircuitBreaker`, guarding LiteLLM's own Redis connection. The deployment mechanism is called "cooldown" throughout.

Two gates run in sequence in `_set_cooldown_deployments()` (`litellm/router_utils/cooldown_handlers.py:249`).

**Gate 1, a status filter** (`_is_cooldown_required`, line 61): 429, 401, 404 and 408 cool down; any *other* 4xx does not; 5xx and unparseable errors do; and any exception whose string contains `APIConnectionError` is on a hard-coded ignore list.

**Gate 2 is where the surprise is** (`_should_cooldown_deployment`, line 169). The default branch **never consults `allowed_fails`**: `_is_allowed_fails_set_on_router()` (line 412) returns False whenever `router.allowed_fails == litellm.allowed_fails`, which is true whenever you left it at the default of 3. The live default is instead a **failure ratio over the current minute**:

- 429 and the model group has more than one deployment → cool down
- `percent_fails > 0.5` with at least 5 requests this minute and more than one deployment → cool down
- `percent_fails == 1.0` with at least 1000 requests this minute → cool down

Single-deployment model groups are largely exempt. A consecutive-N counter exists only on the legacy branch, reached only by setting `allowed_fails` to a non-default value or setting `allowed_fails_policy`.

**The docs and the source disagree.** https://docs.litellm.ai/docs/routing presents `allowed_fails: 3` as the live trip threshold; at that value the source shows it inert. Recorded as a doc/source divergence rather than resolved.

**The default cooldown is 5 seconds** (`DEFAULT_COOLDOWN_TIME_SECONDS`, `litellm/constants.py:32`). Duration precedence is: the deployment's own `cooldown_time`, then the failing response's `retry-after` header, then the router default. So a provider that sends `retry-after` gets honoured; one that does not gets five seconds — three orders of magnitude short of a five-hour quota window.

### 3.2 The three things ruling 16 needs, and LiteLLM's answer to each

**Quota exhaustion with a known reset window — partial, and only reactive.** LiteLLM cools on a 429 it has already received. `x-ratelimit-remaining-*` is **not read from provider responses for routing** — LiteLLM *emits* those headers computed from its own counters, and reads them only when assembling health-check results (negative finding from exhaustive grep, *primary source read*). There is no proactive quota state.

**N consecutive provider errors — no**, by default. See §3.1: it is a ratio, not a run.

**N consecutive gate failures (the quality trip) — no mechanism at all.** This is the decisive gap. Nothing outside the request path can trip a cooldown: `_set_cooldown_deployments()` is private and in-process, there is no HTTP admin route for it (exhaustive grep of `litellm/proxy/**`), and no supported hook for "cool this lane because a downstream gate failed". Our quality trip is driven by `just check` outcomes, which LiteLLM never sees.

**State readable before dispatch — awkwardly.** No admin endpoint exists, and this looks deliberate: `health_check.py:310-313` says failure exceptions are returned separately "so callers can use them for cooldown integration without risking JSON-serialization errors in the `/health` response". Three channels do exist — the Redis key `deployment:<model_id>:cooldown` (only if Redis is configured), the Prometheus `litellm_deployment_state` gauge and `litellm_deployment_cooled_down` counter, and in-process `router.cooldown_cache.get_active_cooldowns(...)`.

**Transitions to OpenTelemetry — no.** LiteLLM emits OTel natively for *request spans* (`litellm.callbacks = ["otel"]`, with `OTEL_EXPORTER` / `OTEL_ENDPOINT` / `OTEL_HEADERS`), but cooldown transitions do not reach it. `router_cooldown_event_callback()` (`litellm/router_utils/cooldown_callbacks.py:21-78`) is the only thing invoked on a transition and its entire body is Prometheus. Greps for `cooldown` across `litellm/integrations/opentelemetry.py`, `litellm/integrations/otel/` and `custom_logger.py` return zero hits — **there is no `CustomLogger` hook for cooldown transitions**, so you cannot even write your own callback to catch them. Without a Prometheus logger registered, the transition is silently dropped.

That last point matters for ADR-0061's telemetry direction: the one event we most want on the bus is the one event LiteLLM will not put there.

### 3.3 Subscription-backed lanes — the strongest area, and the one needing a terms read

**A `chatgpt` provider exists with a full OAuth device-code flow.** `LlmProviders.CHATGPT = "chatgpt"` is a real provider; `litellm/llms/chatgpt/authenticator.py` implements `_request_device_code`, `_poll_for_authorization_code`, `_exchange_code_for_tokens` and **`_refresh_tokens`**, persisting to `~/.config/litellm/chatgpt/auth.json`. Documented at https://docs.litellm.ai/docs/providers/chatgpt as "ChatGPT Subscription", route prefix `chatgpt/`.

**But read `litellm/llms/chatgpt/common_utils.py:14-24` before adopting it:**

```python
# OAuth + API constants (derived from openai/codex)
CHATGPT_API_BASE: Final = "https://chatgpt.com/backend-api/codex"
DEFAULT_ORIGINATOR: Final = "codex_cli_rs"
DEFAULT_USER_AGENT: Final = "codex_cli_rs/0.0.0 (Unknown 0; unknown) unknown"
```

It reaches the subscription by **presenting itself to OpenAI as the Codex CLI**. That is the same category of practice as §2.4 — a third party wearing a first-party client's identity to reach a subscription endpoint — and it deserves the same read of OpenAI's terms that ADR-0061 already requires for Anthropic's, before anything is built on it. This document does not clear it.

**Anthropic OAuth tokens are accepted as credentials, with the same problem.** `ANTHROPIC_OAUTH_TOKEN_PREFIX = "sk-ant-oat"` and `ANTHROPIC_OAUTH_BETA_HEADER = "oauth-2025-04-20"` (`litellm/types/llms/anthropic.py:720-721`); a key starting `sk-ant-oat` is sent as `Authorization: Bearer` with that beta header. There is **no device login and no refresh** on this path — you supply the token and re-supply it on expiry. This is the §1 prohibited path again, reached by a different tool.

Note that LiteLLM's own tutorial https://docs.litellm.ai/docs/tutorials/claude_code_max_subscription runs the **reverse** direction — Claude Code as the *client* pointing at LiteLLM, with `forward_client_headers_to_llm_api: true` passing the client's own token upstream. That is passthrough, not LiteLLM holding a subscription credential.

**No provider shells out to a local CLI**, so wrapping `claude` or `codex` as a lane is code we would write. The sanctioned extension point is real: subclass `CustomLLM` (`litellm/llms/custom_llm.py:41`, importable as `from litellm import CustomLLM`), implement `completion` / `acompletion` / `streaming` / `astreaming`, raise `CustomLLMError(status_code, message)`, and register via `litellm.custom_provider_map` in the SDK or `litellm_settings.custom_provider_map` in the proxy. A handler raising `CustomLLMError(429, ...)` on quota exhaustion **would** trip the cooldown path correctly, since `router.py:7030` reads `getattr(exception, "status_code", "")` — *inferred* from the two code paths, untested.

### 3.4 Operational footprint

**The SDK Router runs in-process with no proxy, no Postgres and no Redis**: `Router.__init__` leaves `redis_cache` as `None` unless configured and uses `InMemoryCache` throughout (`router.py:528-538`, `:605`). On one laptop that is the cheap configuration, and it is the one to reach for.

Without Redis, cooldown state is per-process and lost on restart — **and no external process can read it**, since the Redis key is the only out-of-process channel besides scraping Prometheus. The proxy server, by contrast, needs Postgres (`DATABASE_URL`) for virtual keys, teams, budgets and spend logs, and Redis once more than one instance runs. Routing and cooldowns survive without the database; keys and budgets do not.

### 3.5 Verdict

**Do not adopt as the breaker. Reconsider only as transport, and only after a terms read.**

Against ruling 16 point by point: no quality trip and no way to build one through supported surfaces; a ratio rather than a consecutive-N availability trip; a five-second default cooldown against five-hour quota windows; no proactive quota state; no admin endpoint; and cooldown transitions that cannot reach OTel. Bending it into the specified shape means forking `cooldown_callbacks.py` and calling a private method — which is more work, and more fragile, than writing the breaker.

What it genuinely offers is lane authentication and the `CustomLLM` seam. But the Anthropic half of that is the §1 prohibited path, and the ChatGPT half impersonates the Codex CLI. Both are exactly what ADR-0061's constraint exists to avoid.

*Evidence class: cooldown mechanism, OTel gap, auth code paths, footprint — primary source read at a pinned commit. Enterprise split and budget semantics — documented. `CustomLLM` tripping cooldowns — inferred. Nothing executed.*

---

## 4. The façade: Agent Client Protocol, and `acpx`

This addresses the decision parked in the grilling session — a bespoke MCP tool façade matching Claude Code's native `Agent` contract.

### 4.1 ACP is a real standard, and it is not ours to invent

JSON-RPC 2.0 over stdio. Apache-2.0. The repository has moved out of `zed-industries` to its own organisation — `agentclientprotocol/agent-client-protocol`, 3,871 stars, last push 2026-08-04. Stable protocol version is the integer `1`; `protocolVersion` identifies a MAJOR version only, and adding capabilities is explicitly not breaking. Official SDKs in Rust, TypeScript, Python, Kotlin, Java. — *primary source read*, https://agentclientprotocol.com/protocol/overview, GitHub API observed 2026-08-05.

Method surface, agent side: `initialize`, `authenticate`, `session/new`, `session/prompt` (all baseline), `session/load`, `session/set_mode`, `logout` (optional), `session/cancel` (notification). Client side: `session/request_permission` (baseline), `fs/read_text_file`, `fs/write_text_file`, the `terminal/*` family, `elicitation/create` (optional). Progress arrives as `session/update` notifications carrying `plan`, `agent_message_chunk`, `tool_call`, `tool_call_update`, `usage_update`.

**Session resume exists and is capability-gated** on `loadSession`. `session/load` MUST replay the entire conversation as `session/update` notifications before returning — which for a headless orchestrator is a real cost, not a free resume.

**Permissions are machine-answerable**, which is what makes headless operation possible at all: `session/request_permission` offers options keyed `allow_once` / `allow_always` / `reject_once` / `reject_always`, and clients may answer from settings rather than prompting a human.

### 4.2 But ACP is an editor protocol, and its client list says so

The specification's own framing is "the user is primarily in their editor"; full support for remote agents is stated to be a work in progress. **There is no sub-agent, task-delegation, or agent-spawning concept in the protocol** — *documented but untested*: the method indexes and schema pages were read, a grep of raw `schema.json` was not run. Every client on the official list is an editor or IDE: Zed, JetBrains, Qt Creator, Emacs, several Neovim plugins, VS Code extensions, Visual Studio, Obsidian. **Nothing on it is an orchestrator.**

The shape we want is nonetheless derivable: `session/new` → `session/prompt` → accumulate `agent_message_chunk` → read the `StopReason` (`end_turn`, `max_tokens`, `max_turn_requests`, `refusal`, `cancelled`). The gap is that the response payload is a stop reason, **not a report** — the final text exists only as the concatenation of notifications the client chose to keep. That is an adapter's worth of work rather than a mismatch.

Harnesses that a lane runs internally are handled by vendor extension, not protocol: every ACP type reserves `_meta`, and the Claude adapter uses it — subagent updates carry `_meta.claudeCode.parentToolUseId`, and the launching calls are marked `_meta.claudeCode.subagent = true`, gated on the client advertising `clientCapabilities._meta["subagent-transcript"]`.

### 4.3 Lane coverage is uneven, and two of our three depend on adapters the vendors disowned

| Lane | ACP status |
|---|---|
| **Claude Code** | **Not first-party.** `claude acp serve` was requested and **closed as not planned** (anthropics/claude-code#6686). Reachable only via the ACP org's `@agentclientprotocol/claude-agent-acp`, built on the Claude Agent SDK |
| **OpenAI Codex** | **Not first-party.** ACP request on `openai/codex#9085` also **closed as not planned**. Bridge is `@agentclientprotocol/codex-acp`, which drives `codex app-server` |
| **z.ai GLM** | **Not an ACP agent at all** — absent from the official agents list. Would have to ride as a model behind a Claude-shaped lane |
| Gemini CLI | First-party, in-tree (`--acp`) — not one of our lanes, listed for contrast |

— *primary source read*, https://agentclientprotocol.com/overview/agents and the two linked issues.

That is the central risk in adopting ACP as our contract: for the two lanes we actually need, the adapter is maintained by neither vendor, and both vendors declined to own it.

### 4.4 `acpx` is the piece we were about to build

`openclaw/acpx`, MIT, 3,104 stars, created 2026-02-17, pushed 2026-08-05. Self-described as "a headless command-line client for the Agent Client Protocol (ACP) — talk to coding agents from the command line, not the PTY", giving "agents, orchestrators, and developers one structured interface for persistent sessions, one-shot runs, permissions, and machine-readable output". — *primary source read*, https://github.com/openclaw/acpx.

The surface maps onto this project's needs almost line for line:

- `acpx exec [prompt]` — one-shot, temporary session, saves nothing. `acpx <agent> [prompt]` resumes a session keyed on `(agentCommand, cwd, name?)`.
- `--format json` — one raw ACP JSON-RPC message per line (NDJSON); `--format quiet` puts assistant text on stdout and errors on stderr.
- `--approve-all` / `--approve-reads` (default) / `--deny-all` — the headless permission answer.
- `--timeout <seconds>` for the agent response deadline.
- **Typed exit codes**: `0` success, `1` agent/runtime error, `2` CLI usage, `3` timeout, `4` no session found, `5` permission denied, `130` interrupted.
- Session state in `~/.acpx/sessions/*.json`; `acpx compare <agent>... '<prompt>'` runs the same prompt on several agents.

Built-in adapters spawn: `claude` → `npx -y @agentclientprotocol/claude-agent-acp`; `codex` → `npx -y @agentclientprotocol/codex-acp`; `opencode` → `npx -y opencode-ai acp`; and `--agent '<command>'` for anything else. Auth is delegated to the upstream agent — which is the right shape for ruling 5, since it means the Claude lane authenticates as Claude Code itself rather than having its credential read.

**The typed exit codes are the find.** `3` timeout, `5` permission denied and `1` runtime error map onto the failure-class table directly, and a distinct exit code is exactly the kind of typed verdict CLAUDE.md's "untyped red = harness bug" rule wants.

**Costs, stated.** It is **pre-1.0**, with an explicit README warning to "treat its CLI and runtime interfaces as evolving". It belongs to the OpenClaw organisation, whose main repository has changed identity twice in nine months — GitHub's rename redirects resolve `moltbot/moltbot` and `clawdbot/clawdbot` to the same repository object now named `openclaw/openclaw`, created 2025-11-24 (*primary source read*, GitHub API). The reasons for those renames appear only in secondary write-ups and are **not asserted here**.

### 4.5 A first-party alternative the brief did not name: `codex app-server`

Worth recording because it competes with the ACP adapter for the Codex lane specifically. `codex app-server` is OpenAI's own JSON-RPC 2.0 interface — the one powering their VS Code extension — over stdio, websocket, or unix socket, with a schema you can generate against your exact binary (`codex app-server generate-ts`, `generate-json-schema`). — *primary source read*, `codex-rs/app-server/README.md`.

Its method surface is richer than ACP's for orchestration: `thread/start`, `thread/resume`, `thread/fork` (copy history to a new thread, optionally truncated at a turn), `turn/start`, `turn/steer` (inject input into an in-flight turn), `turn/interrupt`, `thread/compact/start`, plus `thread/list` filtered by `parentThreadId` / `ancestorThreadId` for **spawned subagent threads**. Backpressure is explicit — JSON-RPC error `-32001`, "Server overloaded; retry later."

`codex-acp` drives this, so choosing ACP for the Codex lane means accepting an adapter over a first-party protocol that already does more. That is a real trade, not an obvious win.

---

## 5. Portkey and OpenRouter — brief, and both negative

**Portkey.** MIT gateway, 12,648 stars, last push 2026-05-25 — roughly ten weeks stale as observed. Conditional routing is `{"strategy": {"mode": "conditional", "conditions": [...]}, "targets": [...]}` querying `metadata.<key>`, `params.<key>`, `url.pathname` with `$eq $ne $in $nin $gt $gte $lt $lte $regex $and $or`; two-segment keys only. — *primary source read*, https://portkey.ai/docs/product/ai-gateway/conditional-routing. This is the same capability `claude-code-router` offers, expressed as JSON rather than code, and it operates on HTTP model calls — **nothing for CLI or subscription-backed lanes**. Which Portkey features are SaaS-gated versus present in the MIT gateway was **not verified**.

**OpenRouter.** The `openrouter/auto` router is NotDiamond-backed and **OpenRouter's own docs mark it deprecated**, to be replaced by `openrouter/auto-beta`, with published benchmarks showing the old router far behind (50% vs 83.8% on PhD-level science; 34% vs 74% on agentic customer service). BYOK exists but is enterprise-shaped — Azure, AWS Bedrock, Google Vertex, via API keys or service-account JSON — and costs 5% of the equivalent metered price. — *primary source read*, https://openrouter.ai/docs/features/model-routing, https://openrouter.ai/docs/use-cases/byok.

**Decisively: OpenRouter cannot use a Claude Pro/Max subscription.** It is strictly metered credits or provider API keys. The BYOK documentation describes only enterprise API and service-account authentication and mentions no consumer subscription. — the absence is *primary source read*; the categorical "cannot" is *inferred* from that absence plus the billing model, since OpenRouter nowhere prints the negative.

Neither offers anything the other candidates do not. Both operate one layer below the problem: on HTTP model calls, where a Claude Max seat is not reachable at all.

---

## 6. What this does to the five held rulings

ADR-0061 named two candidates as likely to replace two rulings outright: "LiteLLM's Router implements per-deployment cooldowns, failure-threshold circuit breaking and rate-limit-aware routing today, and `claude-code-router` already routes Claude Code traffic per request type across providers." **Both expectations are refuted, for different reasons.** LiteLLM's cooldowns are a short reactive rate-limit damper that cannot express either trip family we specified (§3.2). `claude-code-router` does route per request type, but only by taking the base URL globally — and its route to a subscription is the one §1 shows is barred (§2.4). The held rulings therefore land, not fall.

| Held ruling | Outcome | Why |
|---|---|---|
| **5 — substrate** | **Hardened, and the spike narrows** | The Anthropic-only-through-Claude-Code constraint is now backed by Consumer Terms §3 and by `opencode` deleting the capability in v1.3.0 (§1). The proxy arm of the spike is dead — not because proxies fail, but because the only proxy that reaches a subscription does so illegitimately (§2.4). The spike that remains is native CLIs against `opencode` **for the non-Anthropic lanes only** |
| **12 — granularity** | **Stands; whole-run per lane** | Per-request-type routing requires a session-global base-URL override, which forfeits the subscription (§1). Its leading implementation also abandoned the category router between v2 and v3 in favour of Claude Code's native model-slot env vars (§2.3). Nothing found argues for finer granularity |
| **16 — breaker** | **Stands, and shrinks — see below** | LiteLLM was the candidate to replace it outright and does not: no quality trip and no supported way to build one, a failure *ratio* rather than consecutive-N, a five-second default cooldown against five-hour windows, and transitions that cannot reach OTel (§3.2, §3.5). But the availability half is partly free — Codex publishes its own quota state |
| **Façade (parked)** | **Adopt ACP's contract; evaluate `acpx` as the client** | A real standard exists with 36 agent implementations; inventing an MCP tool set means owning an adapter per harness forever (§4.1). But ACP is an editor protocol whose every client is an IDE, and our two key lanes are served by adapters both vendors declined to own (§4.2–4.3) |
| Portability, telemetry | Out of scope here | Sibling dispatches |

**Ruling 16 shrinks by about half, and this is the sweep's second real finding.** The breaker was specified with two trip families — availability (quota exhaustion with a known window reset; N consecutive provider errors) and quality (N consecutive gate failures) — with state read before dispatch. The quality half has no prior art and must be built: it depends on this project's own gates, and nothing in the field models "N consecutive `just check` failures on a lane".

The availability half is different. **Codex publishes its own quota state as a first-party API.** `codex app-server`'s `account/rateLimits/read` returns:

```json
{ "rateLimits": { "primary": { "usedPercent": 25, "windowDurationMins": 15, "resetsAt": 1730947200 },
                  "secondary": null, "rateLimitReachedType": null } }
```

with `resetsAt` a Unix timestamp for the next reset and `rateLimitReachedType` naming the backend-classified limit state when one is reached; an `account/rateLimits/updated` notification pushes changes. — *primary source read*, `codex-rs/app-server/README.md` §7.

That is exactly ADR-0061 Decision 7's requirement that a `quota_exhausted` wait be "computed, never guessed", available **before dispatch** and without inferring anything from error patterns. z.ai's side is documented but coarser: the GLM Coding Plan is a subscription with dual windows — credits resetting five hours after consumption and again every seven days, at 2,000/10,000 (Lite), 12,000/60,000 (Pro), 28,000/140,000 (Max) — with off-peak usage charged at 50%, peak being Mon–Fri 14:00–18:00 SGT. Whether the API returns a header or error carrying quota state **is not documented** — *primary source read of the absence*, https://docs.z.ai/devpack/overview.

So the recommendation on ruling 16 is: **build the quality half, read the availability half from the provider where it is published**, and only fall back to error-pattern inference on lanes that publish nothing.

---

## 7. Recommendations, with evidence class

1. **Do not adopt `claude-code-router`.** Rejected on ruling 5 for the Anthropic lane; rejected on cost-benefit elsewhere, since z.ai's native Anthropic-shaped endpoint reaches the same place with no proxy. — *mechanism primary source read; conclusion inferred.*
2. **Treat ruling 5's Anthropic constraint as settled rather than spiked**, and narrow the spike to native CLIs against `opencode` for the non-Anthropic lanes. Note `opencode` legitimately supports ChatGPT Plus, GitHub Copilot and GitLab Duo subscriptions with zero setup, and `codex exec` supports ChatGPT sign-in with `--json`, `--output-last-message`, `--output-schema` and `resume`. — *documented.*
3. **Adopt ACP's contract for the façade rather than inventing an MCP tool set**, and evaluate `acpx` as the client in the same spike. Weigh `codex app-server` directly for the Codex lane, since `codex-acp` is an adapter over a first-party protocol that already does more. — *primary source read; the choice between them is untested and belongs in the spike.*
4. **Shrink the breaker to its quality half plus a provider-state reader, and build it ourselves.** Consume `account/rateLimits/read` for the Codex lane rather than inferring quota from errors. Do not adopt LiteLLM to carry it: the quality trip has no supported surface there, and cooldown transitions cannot reach OTel. — *primary source read.*
5. **Do not put a subscription credential in any third-party process, on any lane.** Three separate tools offer to do it — `claude-code-router`'s credential-file import (§2.4), LiteLLM's `sk-ant-oat` Bearer path and its `chatgpt` provider presenting as `codex_cli_rs` (§3.3). ADR-0061 already requires one terms read before landing; this widens it to OpenAI's terms as well, and the answer for Anthropic is already no. — *primary source read.*
6. **If any proxy is ever reconsidered, audit `cache_control` and TTL survival first.** No TTL handling was found in the candidate, and this project's bill is 95.5% cache traffic. — *not-found, not proven absent.*

---

## 8. Where the uncertainty is

- **Nothing was executed.** Every claim about how a substrate behaves under load, under this repo's hooks, or against this repo's gates is untested.
- **`acpx` is pre-1.0** and its interfaces are declared evolving; its organisation has renamed twice in nine months. Adopting it means accepting churn, and the evaluation should include what breaks when it moves.
- **The ACP adapter risk is structural, not incidental.** Anthropic and OpenAI both closed ACP requests as not planned. An adapter layer neither vendor owns sits between us and two of three lanes.
- **z.ai publishes no machine-readable quota state** that this sweep could find, so that lane's availability breaker may have to infer after all.
- **`claude-code-router`'s non-Anthropic transformers were not individually read**, so whether each strips `cache_control` is unknown. Immaterial given recommendation 1, recorded in case that reverses.
- **The subscription-versus-gateway incompatibility is inferred**, not quoted: Anthropic documents a credential precedence and gateway examples using explicit keys, but never prints the sentence. The terms clause and `opencode`'s withdrawal are the load-bearing evidence, not the docs.
- **LiteLLM's `chatgpt` provider is untested and its terms standing unread.** It is the only route found that reaches a ChatGPT subscription from a library rather than a CLI, so if the Codex lane ever needs library access rather than `codex exec`, this is where to look — after the terms read recommendation 5 asks for.
- **z.ai support in LiteLLM was not researched**, and `lar1`, one of its routing strategies, was not identified.
- **LiteLLM's doc/source divergence on `allowed_fails` is recorded, not resolved.** If we ever do use its cooldowns, that discrepancy should be settled by experiment rather than by reading either side again.
