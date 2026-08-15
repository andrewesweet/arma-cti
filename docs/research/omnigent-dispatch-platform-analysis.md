# Omnigent as an agent/provider/model dispatch substrate

**Status:** Background technology-adoption assessment. No Omnigent adoption is authorized by
this document; [MVP specification #377](https://github.com/andrewesweet/arma-cti/issues/377)
governs the autonomous-development work and explicitly defers an additional execution runtime.

**Researched:** 2026-08-07

**Question:** What does Omnigent provide for dispatching work across coding-agent harnesses, model providers, and models, and what would a migration from a bespoke control plane gain or lose?

**Answer in one line:** Omnigent is a broad, attractive harness/session/policy/UX layer, but it is not yet a replacement for a project-specific, deterministic orchestration kernel; use it as a bounded integration or alternate execution surface, not as the new system of record.

## 1. Method, snapshot, and confidence

This note uses only primary Omnigent sources: its official website/docs and the official repository. Source inspection is pinned to [`a30deaec`](https://github.com/omnigent-ai/omnigent/commit/a30deaecbec2261cab86289be0ec796a714c0df6), the `main` head inspected on 2026-08-07. That snapshot identifies itself as `0.9.0.dev0` and as Alpha in package metadata ([source](https://github.com/omnigent-ai/omnigent/blob/a30deaecbec2261cab86289be0ec796a714c0df6/pyproject.toml#L5-L23)); the public FAQ explicitly says it is not production-ready ([FAQ](https://omnigent.ai/faq)). The latest release changelog in the snapshot is v0.8.1, dated 2026-08-03, while development and nightly tags have continued since then ([changelog](https://github.com/omnigent-ai/omnigent/blob/a30deaecbec2261cab86289be0ec796a714c0df6/CHANGELOG.md#L1-L14)).

Evidence labels used below:

- **Documented fact:** stated by an official Omnigent document or current source.
- **Source finding:** behaviour verified in the pinned implementation, but not necessarily promised as a stable public contract.
- **Inference:** a migration conclusion drawn from those facts. It must be validated in a pilot.

No claim below that a feature was “not found” should be read as proof that it cannot exist in an extension or future release.

## 2. What Omnigent actually is

Omnigent calls itself an open-source “meta-harness”: a common orchestration layer over coding agents, custom agents, policies, sandboxing, and collaborative interfaces ([README](https://github.com/omnigent-ai/omnigent/blob/a30deaecbec2261cab86289be0ec796a714c0df6/README.md#L3-L14)). Its deployed architecture has three parts:

1. A **server** that stores every conversation, message, and tool call, and owns artifacts, agent catalogs, skills, authentication, and server-side MCP policy enforcement.
2. A **runner** that executes the chosen harness locally or in a remote/cloud sandbox.
3. Terminal, web, desktop, mobile, Slack, and REST **interfaces** over the same sessions.

These are documented platform responsibilities, not just a launch script ([deployment overview](https://omnigent.ai/docs/deploy/overview)). Postgres is required for multiple server instances; SQLite is for a single instance or demo ([database docs](https://omnigent.ai/docs/deploy/database)). The implementation also creates one lazily started harness subprocess per conversation, with crash detection, startup orphan cleanup, terminal-state release, and a configurable one-hour idle reaper ([process manager](https://github.com/omnigent-ai/omnigent/blob/a30deaecbec2261cab86289be0ec796a714c0df6/omnigent/runtime/harnesses/process_manager.py#L1-L17), [idle lifecycle](https://github.com/omnigent-ai/omnigent/blob/a30deaecbec2261cab86289be0ec796a714c0df6/omnigent/runtime/harnesses/process_manager.py#L100-L162)).

That is a materially larger product surface than a bespoke dispatch kernel. It is strongest as a shared execution and interaction platform.

## 3. Capability assessment

### 3.1 Agents and harnesses

**Documented fact.** Omnigent currently supports direct and/or native-TUI modes for Claude Code, Codex, Cursor, Antigravity, Goose, Qwen Code, Kimi, Hermes, Pi, OpenCode, Kiro, Copilot, OpenAI Agents SDK, and Grok Build. Claude Code and Codex have both direct (`claude-sdk`, `codex`) and native (`claude-native`, `codex-native`) variants ([harness matrix](https://omnigent.ai/docs/build/harnesses)). Generic Agent Client Protocol (ACP) agents can also be registered by launch command.

The distinction matters:

- In **direct mode**, Omnigent drives the model and tools, so its persistent session, streaming, tool, and policy semantics are closest to uniform.
- In **native mode**, it starts and mirrors the vendor TUI. The vendor still owns important loop, approval, resume, usage, and model-selection behaviour.
- A **generic ACP agent** owns its own auth, model, loop, native tools, and context window; Omnigent renders it, handles exposed permission requests/interrupts, and can lend its built-in MCP tools ([ACP contract](https://omnigent.ai/docs/build/harnesses)).

**Inference.** “One harness interface” is not semantic interchangeability. A migration must test continuation, cancellation, tool-policy coverage, usage accounting, model overrides, and failure recovery separately for every direct/native pair actually used. Omnigent reduces adapter work; it does not eliminate vendor behavioural differences.

**Extensibility.** Additional direct/headless harnesses can be installed through the `omnigent.community.harness` Python entry-point. They appear in YAML, the CLI, and UI. Community native-TUI harnesses are explicitly not pluggable yet ([plugin contract](https://omnigent.ai/docs/build/harnesses)). Custom ACP is the easier route when an agent already speaks ACP.

### 3.2 Providers and the named target models

**Documented fact.** The public credential guide names first-party API-key setup for Anthropic, OpenAI, OpenRouter, Groq, DeepSeek, xAI, Mistral, Together AI, and Fireworks; official Claude and Codex CLIs can use Claude Pro/Max and ChatGPT Plus/Pro subscriptions. Any OpenAI-compatible or Anthropic-compatible endpoint can be configured as a gateway/local provider, including common gateways and local servers ([models and credentials](https://omnigent.ai/docs/build/models)). Provider configuration is family-oriented: Anthropic Messages for Claude-family harnesses and OpenAI Responses/Chat for Codex/OpenAI Agents, with a separate Gemini path ([provider source](https://github.com/omnigent-ai/omnigent/blob/a30deaecbec2261cab86289be0ec796a714c0df6/omnigent/onboarding/provider_config.py#L1-L42), [provider kinds](https://github.com/omnigent-ai/omnigent/blob/a30deaecbec2261cab86289be0ec796a714c0df6/omnigent/onboarding/provider_config.py#L101-L145)).

The current source is already aware of the models in question:

- The release-curated Claude subscription fallback includes `claude-opus-5`.
- The Codex fallback includes `gpt-5-6-sol`, Luna, Terra, and GPT 5.5.
- Current smart-router GPT arms include `glm-5-2` and GPT 5.6 Sol/Luna.

See the pinned fallback catalogs and router menus ([source](https://github.com/omnigent-ai/omnigent/blob/a30deaecbec2261cab86289be0ec796a714c0df6/omnigent/model_fallbacks.py#L20-L53), [routing arms](https://github.com/omnigent-ai/omnigent/blob/a30deaecbec2261cab86289be0ec796a714c0df6/omnigent/model_fallbacks.py#L115-L145)). Omnigent normally prefers live provider listings, cached for five minutes, and marks subscription/CLI fallbacks as static and unverified ([model catalog](https://github.com/omnigent-ai/omnigent/blob/a30deaecbec2261cab86289be0ec796a714c0df6/omnigent/model_catalog.py#L1-L29), [cache](https://github.com/omnigent-ai/omnigent/blob/a30deaecbec2261cab86289be0ec796a714c0df6/omnigent/model_catalog.py#L82-L100)).

Important qualifications:

- Opus 5 is in the Claude subscription catalog, but the current `task_v1` external-router Claude menu is Opus 4.8 and Sonnet 5. “Available to a harness” and “offered to this router” are different claims.
- GLM 5.2 is a current Codex/router arm. For one probed gateway on the Codex/Responses wire, Omnigent clamps unsupported `xhigh`/`max` effort to `medium`; deployments may override this gateway-specific rule ([effort caps](https://github.com/omnigent-ai/omnigent/blob/a30deaecbec2261cab86289be0ec796a714c0df6/omnigent/reasoning_effort.py#L52-L66)).
- Z.ai appears in the source’s MLflow-derived provider catalog and a Pi model-id example, but it is not in the public first-party key table and there is no Z.ai-specific provider adapter or base-URL logic in the inspected source ([catalog names](https://github.com/omnigent-ai/omnigent/blob/a30deaecbec2261cab86289be0ec796a714c0df6/omnigent/onboarding/providers/__init__.py#L381-L463), [Pi pass-through](https://github.com/omnigent-ai/omnigent/blob/a30deaecbec2261cab86289be0ec796a714c0df6/omnigent/pi_native_credentials.py#L897-L918)). The plausible path is a Z.ai OpenAI/Anthropic-compatible endpoint or Pi-native provider configuration. **Inference:** treat Z.ai/GLM compatibility as a required pilot test, not established parity.

Omnigent can switch model mid-session while preserving conversation and tool state ([model docs](https://omnigent.ai/docs/build/models)). That is useful operationally but does not guarantee that the new model/harness can faithfully interpret every vendor-specific historical item.

### 3.3 Routing is first-message classification, not a learned scheduler

**Documented fact.** Smart Routing selects a harness and model from the first message, then applies the result for the rest of the session. It has two backends:

- a built-in LLM judge using the server `llm:` configuration;
- an external `POST <base_url>/routes:select` service, receiving one option per model/harness pair and a prompt truncated to 4,000 characters.

The public protocol and configuration are documented in [Smart Routing](https://omnigent.ai/docs/build/routing). Off-gateway calls use the built-in judge; gateway-backed calls can prefer the external router. If the external router fails and a judge exists, current source falls back to the judge ([router selection](https://github.com/omnigent-ai/omnigent/blob/a30deaecbec2261cab86289be0ec796a714c0df6/omnigent/server/routing_backend.py#L1-L15), [fallback](https://github.com/omnigent-ai/omnigent/blob/a30deaecbec2261cab86289be0ec796a714c0df6/omnigent/server/routing_backend.py#L129-L182)). The route call has a nine-second budget, one attempt, and fails open to the harness/default model rather than stalling the work ([source](https://github.com/omnigent-ai/omnigent/blob/a30deaecbec2261cab86289be0ec796a714c0df6/omnigent/server/smart_routing.py#L45-L68)). A persisted decision label enforces “route once” for the session ([turn routing](https://github.com/omnigent-ai/omnigent/blob/a30deaecbec2261cab86289be0ec796a714c0df6/omnigent/runner/turn_routing.py#L437-L465)).

**Source finding.** The external client latches one known permanently unavailable condition for the lifetime of the process, but no general provider circuit breaker, quota-aware admission controller, or outcome-quality feedback loop was found. The built-in route is an LLM classification decision, not a scheduler trained on local gate outcomes.

**Inference.** Omnigent routing can replace simple “classify task, choose harness/model” logic. It does not replace a project control plane that reserves scarce slots, reasons about dependency DAGs, enforces phase transitions, learns from test/review results, or trips providers based on repeated local failures. Its external protocol is nevertheless a useful integration seam: the existing router could remain authoritative while Omnigent becomes the session/harness executor.

### 3.4 Multi-agent lifecycle and concurrency

**Documented/source fact.** `sys_session_send` creates or continues a distinct child conversation with its own history and visible session-tree node. Results auto-deliver to the parent; work can be cancelled. Distinct task titles emitted in one response dispatch concurrently, while reusing `(agent, title)` continues the same session and cannot run a second concurrent turn ([spawn contract](https://github.com/omnigent-ai/omnigent/blob/a30deaecbec2261cab86289be0ec796a714c0df6/omnigent/tools/builtins/spawn.py#L56-L103), [concurrency semantics](https://github.com/omnigent-ai/omnigent/blob/a30deaecbec2261cab86289be0ec796a714c0df6/omnigent/tools/builtins/spawn.py#L114-L139)). Model and, when allow-listed, harness overrides can be supplied at child creation.

Polly is the built-in coding supervisor. Officially it decomposes work, gives each implementer a git worktree, assigns a different-vendor reviewer, requires each implementer to open a PR, never merges, and leaves the final decision to a human ([Polly docs](https://omnigent.ai/docs/use/builtin-agents/polly)).

There is an important implementation boundary:

- The per-turn fan-out cap is a runner-side policy (`max_dispatches_per_turn: 6`).
- Much of the worktree/registry/PR/cross-review lifecycle is encoded in Polly’s system prompt and skills. For example, the fan-out skill instructs the supervisor to execute `git worktree add`, record `.polly/registry.json`, dispatch, cross-review, and later remove the worktree ([Polly config](https://github.com/omnigent-ai/omnigent/blob/a30deaecbec2261cab86289be0ec796a714c0df6/examples/polly/config.yaml#L326-L369), [fan-out skill](https://github.com/omnigent-ai/omnigent/blob/a30deaecbec2261cab86289be0ec796a714c0df6/examples/polly/skills/fanout/SKILL.md#L6-L46)).
- Polly itself and its generic shell terminals are explicitly configured without an OS sandbox; coding workers have separate worktrees, and native workers use bypass/YOLO modes so they do not stall on prompts. Omnigent’s catastrophic blast-radius denial remains in force ([Polly config](https://github.com/omnigent-ai/omnigent/blob/a30deaecbec2261cab86289be0ec796a714c0df6/examples/polly/config.yaml#L292-L324), [Polly security posture](https://omnigent.ai/docs/use/builtin-agents/polly)).

**Inference.** Omnigent has durable child-session primitives, but Polly’s engineering workflow is partly an LLM-followed protocol, not an all-or-nothing transactional scheduler. No documented global capacity pool equivalent to a hard host/provider/model slot allocator was found; the visible controls are per-response fan-out, per-session process lifecycle, policy/cost limits, and deployment capacity. Preserve any existing hard resource locks until a load test proves an equivalent.

### 3.5 Isolation, policies, and security boundaries

This is one of Omnigent’s strongest gains. Its OS sandbox supports Linux bubblewrap namespaces/seccomp and macOS Seatbelt; requested sandboxing fails closed if unavailable. Working directories are read-only by default, write paths are explicit, top-level dotfiles are masked by default, recursive masking is optional, and named paths can be hidden. HTTP(S) egress can be default-deny through a MITM proxy, private/metadata IPs are blocked by default, and credentials can be injected by a secretless proxy without placing the real secret in the sandbox ([OS sandbox docs](https://omnigent.ai/docs/policies/os-sandbox)). Agent environments are also deny-by-default except for a small base, the current harness’s credential family, and explicit pass-through names.

The boundary is narrower than “everything the agent can cause”:

- The sandbox applies to `sys_os_*` calls and declared terminals.
- MCP servers are spawned outside it.
- The supervisor/model-loop process is outside it.
- Generic ACP defaults to no sandbox when it needs to write its own configuration, unless explicitly tightened.

Those limitations are explicit in the [sandbox documentation](https://omnigent.ai/docs/policies/os-sandbox). Server/spec/session policy layers can still ALLOW, DENY, or ASK on tool activity, including server-proxied MCP calls. Built-in policies cover blast radius, loops/thrashing, costs, and destructive connector operations; custom callable policies provide project-specific extension points ([built-in policies](https://omnigent.ai/docs/policies/builtin)).

**Inference.** Omnigent meaningfully improves the baseline, especially for unattended workers and secret handling. It should not be treated as a complete security boundary unless MCP subprocesses, the supervisor, native bypass modes, hidden-file recursion, and connector credentials all receive a deployment-specific threat review.

### 3.6 Persistence, observability, reliability, and retries

**Persistence.** The server’s database persists session history, users, and artifacts; Postgres supports multiple server replicas ([database docs](https://omnigent.ai/docs/deploy/database)). Local or cloud runner filesystems are a separate concern. Session transcript durability does not make an ephemeral runner workspace durable; persistent volumes or git/remote artifacts are still required.

**Observability.** Current source implements opt-in OpenTelemetry/OTLP tracing with response-derived trace IDs, W3C propagation, session correlation, FastAPI/httpx/SQLAlchemy instrumentation hooks, and LLM usage normalization. Literal message/tool content is off by default; if enabled it is shallow-redacted and capped ([telemetry source](https://github.com/omnigent-ai/omnigent/blob/a30deaecbec2261cab86289be0ec796a714c0df6/omnigent/runtime/telemetry.py#L1-L27), [privacy controls](https://github.com/omnigent-ai/omnigent/blob/a30deaecbec2261cab86289be0ec796a714c0df6/omnigent/runtime/telemetry.py#L57-L132)). A separate anonymous product-analytics channel is enabled by default from v0.6, claims not to collect prompts, contents, tool arguments, files, or credentials, and can be disabled by environment or config ([usage telemetry](https://omnigent.ai/docs/deploy/telemetry)).

The repository’s holistic end-to-end observability design is still labelled **Proposed**, and explicitly lists quality/eval scoring as a non-goal ([design](https://github.com/omnigent-ai/omnigent/blob/a30deaecbec2261cab86289be0ec796a714c0df6/designs/OBSERVABILITY.md#L1-L16), [non-goals](https://github.com/omnigent-ai/omnigent/blob/a30deaecbec2261cab86289be0ec796a714c0df6/designs/OBSERVABILITY.md#L42-L63)). **Inference:** tracing and cost visibility are useful platform telemetry, but they do not replace a project ledger that connects dispatch choices to tests, review findings, or acceptance-gate quality.

**Retries.** The shared LLM retry policy defaults to seven retries with exponential backoff/jitter, a 120-second per-request timeout, and retries for 429/500/502/503/504 ([retry policy](https://github.com/omnigent-ai/omnigent/blob/a30deaecbec2261cab86289be0ec796a714c0df6/omnigent/spec/types.py#L85-L115)). Tool-call retry is narrower: the inspected implementation retries timeouts, but not arbitrary non-timeout exceptions ([tool retry](https://github.com/omnigent-ai/omnigent/blob/a30deaecbec2261cab86289be0ec796a714c0df6/omnigent/runtime/tool_retry.py#L93-L145)). Smart Routing deliberately has no retry and fails open. These are sensible interactive defaults, not generalized job-level recovery or cross-provider failover.

The v0.8 changelog records fixes in critical seams such as dropped first messages, resume on managed sandboxes, policy handling of malformed tool payloads, host credential exposure, native sub-agent completion, and orphaned Codex processes ([changelog examples](https://github.com/omnigent-ai/omnigent/blob/a30deaecbec2261cab86289be0ec796a714c0df6/CHANGELOG.md#L15-L74), [later fixes](https://github.com/omnigent-ai/omnigent/blob/a30deaecbec2261cab86289be0ec796a714c0df6/CHANGELOG.md#L179-L193)). These are fixed issues, not evidence that the current build still has them. They do demonstrate high velocity and why an alpha migration needs pinned versions, canaries, and rollback.

### 3.7 Deployment and operational surface

Omnigent can run locally, as Docker Compose with Postgres, on common PaaS targets, Kubernetes, Databricks, or with local/managed sandbox runners. Managed Databricks is Beta; self-managed deployment is required for some custom YAML policies, bring-your-own provider keys, and custom egress controls ([deployment overview](https://omnigent.ai/docs/deploy/overview)). The core package requires Python 3.12+, and native harnesses add Node, vendor CLIs, tmux, and platform sandbox prerequisites. Native Windows support is degraded: direct SDK/web paths work, but native TUI wrappers and filesystem/network isolation do not ([README prerequisites](https://github.com/omnigent-ai/omnigent/blob/a30deaecbec2261cab86289be0ec796a714c0df6/README.md#L91-L148), [Windows](https://github.com/omnigent-ai/omnigent/blob/a30deaecbec2261cab86289be0ec796a714c0df6/README.md#L152-L176)).

The server supports built-in invite accounts, OIDC, and header-based SSO ([auth docs](https://omnigent.ai/docs/collaborate/auth)). It is Apache License 2.0 ([license](https://github.com/omnigent-ai/omnigent/blob/a30deaecbec2261cab86289be0ec796a714c0df6/LICENSE#L1-L24)); Databricks is the named copyright holder ([NOTICE](https://github.com/omnigent-ai/omnigent/blob/a30deaecbec2261cab86289be0ec796a714c0df6/NOTICE#L1-L3)). There is therefore no source-license blocker to adapting or embedding it, but maintaining a fork of a fast-moving multi-harness platform would be costly.

## 4. This repository: current system, backlog, and Omnigent

The local system is not a general agent workbench. It is a repository-specific control plane
around separate Claude Code and Codex processes. Its binding unit is an opaque
`(lane, model, effort)` profile, not a freely composed provider/model/effort choice
([dispatch design](../multi-provider-dispatch.md), [ADR-0061](../adr/0061-work-leaves-claude-only-where-a-gate-catches-it-and-a-lanes-authority-is-the-enforcement-it-proves.md)).

| Concern | Implemented here now | Planned or still open | Omnigent comparison |
|---|---|---|---|
| Harnesses and providers | `claude-native` reaches Anthropic; the same Claude Code binary reaches Z.ai through a per-process Anthropic-compatible endpoint; `codex` reaches the authenticated Codex CLI. | Herma is proposed as a third foreign, OpenAI-compatible lane through a new harness ([#234](https://github.com/andrewesweet/arma-cti/issues/234)). | Much broader adapter catalog and an easier path to future harnesses. Z.ai still needs a live compatibility proof. |
| Models and effort | Registered profiles include Opus aliases, `gpt-5.6-sol`, `gpt-5.6-terra`, GLM 5.2 and GLM 4.7. Z.ai effort is deliberately collapsed because the endpoint ignored Claude Code's thinking budget. | Competence and gate experiments aim to qualify foreign profiles for more seats rather than assume model equivalence ([#262](https://github.com/andrewesweet/arma-cti/issues/262)). | Live catalogs, session effort, effort caps, and mid-session model switching are gains. Smart Routing's model/harness pick is not the measured, immutable profile arm used by local admission. |
| Dispatch decision | The caller selects a profile and seat. `just dispatch` then fails closed through issue readiness, queue policy, admission, lane breaker, Z.ai off-peak policy, credential checks, and worktree identity. The queue derives candidates but does not launch them. | A per-dispatch keep-on-Claude class file plus advisory issue-surface check and enforcing landing-diff check is open ([#266](https://github.com/andrewesweet/arma-cti/issues/266)). | Omnigent Smart Routing classifies the first prompt into a model/harness and fails open to defaults if routing fails. It cannot replace this refusal ladder without custom policies or an external authoritative router. |
| Orchestration | Queue, brief, admission audit, recovery, watcher, dispatcher, ledger, and landing are separate deterministic tools. A standing orchestrator still sequences them. | The runbook will standardise the Opus/high standing loop, episodic fable acts, top-of-turn checks, and wait/recovery rules ([#267](https://github.com/andrewesweet/arma-cti/issues/267)). A separate Opus/xhigh human interlocutor is planned for CLI/iOS ([#255](https://github.com/andrewesweet/arma-cti/issues/255)). | Polly supplies fan-out, worktrees, cross-vendor review, durable child sessions, and excellent supervision UX. Its standard workflow is prompt/skill-driven, PR-based, human-merged, and therefore does not match this project's gated autonomous landing contract. Omnigent is especially attractive for the interlocutor/session requirement. |
| Capacity and economics | Queue policy enforces the human's freeze, WIP limit, packages/carve-outs, and surface conflicts. Breakers react to quota/provider/quality evidence. The ledger compares subscription-window fraction-of-cap or prompt allowance rather than pretending API list price is spend. | The quota tap still needs the binding `limits[]` scope and `Retry-After` ([#261](https://github.com/andrewesweet/arma-cti/issues/261)); scarcity routing becomes relevant only when a second pool binds. | Omnigent has per-session/subagent USD budgets and retry backoff, but no equivalent subscription-window meter, off-peak rule, quality breaker, or queue-policy ladder. It also does not add a documented global provider/model lease scheduler. |
| Authority and safety | Z.ai inherits a narrow Claude command allowlist and has proven gate/commit/land. Codex uses workspace-write roots and translated hooks, but cannot currently both commit and run the libgit2-based gate without escalation. | Fix the Codex sandbox conflict ([#265](https://github.com/andrewesweet/arma-cti/issues/265)), real edit-hook parity ([#273](https://github.com/andrewesweet/arma-cti/issues/273)), and single-source agent instructions ([#264](https://github.com/andrewesweet/arma-cti/issues/264)). | Omnibox can improve filesystem, egress, environment, and credential isolation if configured. Default Polly instead runs its supervisor and workers without the OS sandbox and launches Codex in bypass/YOLO mode, so it is not a safe drop-in default. |
| Evidence and learning | Every run has an immutable dispatch record, brief, log, result, OTel identity, and ledger row. Admission is pre-registered per profile/seat; consecutive bad outcomes can trip quality. | Decision-replay, authorship, corpus, gate-diff, and orchestration experiments would dissolve current keep-on-Claude classes ([#262](https://github.com/andrewesweet/arma-cti/issues/262)). | Omnigent adds richer session history and distributed traces, but its router does not consume this project's gate/review/admission evidence. Keep the local ledger as the outcome system of record. |

The comparison is therefore asymmetric. Omnigent is much more complete above the agent loop
(sessions, UI, adapters, collaboration, deployment) and the local system is much deeper below the
work-item boundary (eligibility, quota economics, admission, gates, and proof of landing).

## 5. What a move would gain

Relative to maintaining all of these capabilities in-house, Omnigent offers:

1. **A much broader adapter portfolio.** Claude/Codex direct and native support plus many additional harnesses, ACP, and direct/headless plugins.
2. **A coherent session plane.** Durable transcripts, resumable child conversations, cancellation, steering, session trees, model switching, artifacts, and cross-device continuity.
3. **Human supervision UX.** Web/mobile/desktop/terminal access, live native panes, approvals, take-over, collaboration, and project/session browsing.
4. **Substantially better generic governance.** Layered tool policies, cost controls, blast-radius checks, OS filesystem/network isolation, environment minimization, and credential brokering.
5. **A provider-neutral configuration layer.** First-party keys, subscription logins, gateways, local endpoints, Databricks, live model catalogs, and an external router protocol.
6. **An operational base.** Auth, Postgres migrations, multi-instance support, cloud runners, Kubernetes, telemetry, usage/cost reporting, and deployment recipes.
7. **A community-maintained compatibility burden.** Vendor CLI and model churn is shared with an upstream project rather than carried entirely by the local codebase.

These are large gains if the goal is to build a multi-user agent workbench. They are smaller if the existing system is primarily a deterministic repository workflow engine.

## 6. What a full replacement would lose or put at risk

Unless independently rebuilt on top of Omnigent, a full replacement risks losing:

1. **Deterministic orchestration contracts.** Polly’s worktree/registry/review workflow is significantly prompt-and-skill driven. Project-specific state machines, dependency ordering, hard phase gates, and artifact schemas are not supplied automatically.
2. **Current queue and lane governance, plus any future scheduler authority.** Omnigent has no ready equivalent for this repository's per-dispatch freeze/WIP/carve-out/surface-conflict refusals, subscription-aware breaker, or off-peak rule. Nor does it supply a documented global provider/model/host lease scheduler if the backlog later needs one.
3. **Outcome-driven routing.** Smart Routing chooses once from the first prompt. It does not learn from the repository’s test, review, acceptance, latency, or cost outcomes.
4. **Uniform semantics.** Direct, native, and ACP harnesses expose different levels of lifecycle, policy, model, cost, and cancellation control.
5. **Mature stability.** The project itself says Alpha/not production ready, and its recent changelog shows rapid changes and fixes in the exact integration seams this migration would depend on.
6. **A smaller trusted/operated surface.** Server, database, runner tunnels, web clients, vendor CLIs, MCP proxies, sandbox providers, telemetry, and auth all become part of the dependency and threat model.
7. **Known Z.ai parity.** GLM 5.2 is represented, but a first-class Z.ai adapter is not documented; provider/model/effort/cost behaviour needs empirical verification.
8. **Freedom from upstream shape changes.** The license permits a fork, but a fork would re-acquire much of the maintenance burden the migration was meant to shed.

## 7. Recommendation: bounded integration, not replacement

**A wholesale move is not justified now.** Omnigent’s strongest features and the bespoke control plane’s likely strongest features sit at different layers:

- Omnigent: harness adapters, persistent conversations, interactive supervision, policies, sandboxing, provider configuration, and deployment.
- Bespoke control plane: profile registry, queue and lane refusals, work-item/brief state, deterministic gates, evidence capture, admission, and outcome feedback.

The justified move is to test Omnigent as an **execution/session substrate behind or beside the existing control plane**, keeping the existing dispatcher, queue policy, profile registry, breaker, admission records, and project ledger authoritative.

### Recommended pilot

Run a pinned Omnigent deployment for a small, representative slice:

1. One Claude Code native worker on Opus 5, one Codex direct/native worker on GPT 5.6 Sol, and one GLM 5.2 path through the actual Z.ai/gateway configuration.
2. Dispatch from the existing controller through Omnigent’s REST/session or external-router seams; do not adopt Polly as the authoritative scheduler in phase one.
3. Retain current WIP/freeze/carve-out refusals, worktree rules, issue/brief artifacts, deterministic gates, and result ledger.
4. Compare at least: launch success, first-turn delivery, resume after runner/server restart, cancellation, provider outage/429 behaviour, concurrent WIP refusal, tool-policy coverage, secret exposure, transcript fidelity, subscription-meter accuracy, and end-to-end task quality.
5. Disable anonymous usage telemetry if required by policy; enable OTLP separately in a controlled backend.
6. Pin a release, maintain an immediate fallback to the current dispatcher, and upgrade only after replaying the acceptance matrix.

### Decision gate

Expand Omnigent only if the pilot shows that it removes more adapter/session/security code than the integration and operations it adds, while preserving the existing deterministic guarantees. Even then, retire homegrown code by layer:

- **Good early retirement candidates:** vendor launch wrappers, transcript/UI plumbing, generic approvals, and generic OS sandbox code.
- **Keep until Omnigent has proven equivalents:** queue policy, profile admission, project lifecycle state, gate and landing enforcement, quality/outcome ledger, provider trip logic, and the evidence-based routing policy.

This captures most of Omnigent’s value without betting the project’s control plane on an alpha product or forcing a false choice between “homebrew everything” and “replace everything.”
