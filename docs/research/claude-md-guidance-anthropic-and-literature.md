# Managing `CLAUDE.md` and `AGENTS.md`: cross-provider guidance, evidence, and intervention plan

- **Researched:** 2026-08-21
- **Repository baseline:** `1341ca2f4c1009875ea1fea08569128efa49f0b1`
- **Derived specification:** [#497](https://github.com/andrewesweet/arma-cti/issues/497)
- **Scope:** Current Anthropic/Claude Code and OpenAI/Codex documentation; official engineering blogs and talks by their staff; primary academic literature on repository instruction files, long context, and agent harnesses; and this project's Claude Code, Codex, dispatch, review, session-log, and OpenTelemetry evidence. Sources were checked through 2026-08-21.

## Answer in one sentence

This repository needs an immediate Codex truncation fix followed by a measured reduction of root `AGENTS.md`/`CLAUDE.md` to a small cross-provider map: the current 66,692-byte file exceeds Codex's default 32 KiB project-instruction limit and is cut off mid-sentence, while both vendors recommend keeping always-loaded guidance small and moving procedures, path-specific rules, mechanical invariants, and verbose investigation to more precise harness surfaces.

## Evidence labels and method

Claims below carry one of these labels:

- **Official guidance**: current Anthropic product documentation.
- **Official product fact**: documented Claude Code loading or enforcement behavior.
- **Anthropic practice**: an Anthropic engineering post, Claude blog by named Anthropic staff, official talk, or incident report. It is evidence of practice, not a universal product contract.
- **OpenAI guidance/product fact**: current official Codex documentation.
- **OpenAI practice**: an official OpenAI engineering/developer post or a public talk by OpenAI staff. It is evidence from that team or evaluation, not a universal product guarantee.
- **Academic result**: the authors' reported result. It is not automatically causal outside the reported models, repositories, and harness.
- **Repository fact**: measured directly in this checkout on 2026-08-21.
- **Project telemetry**: an aggregate over local session logs, dispatch records, verdicts, or OTel captures. Prompt and source-code bodies were not inspected for this report.
- **Inference**: a proposed implication. It is explicitly not a source's direct instruction.

The vendor search covered the current Claude Code and Codex documentation indexes and the pages for memory/instructions, context, best practices, skills, subagents, hooks, permissions/rules, output styles or prompts, MCP, plugins, sessions, and telemetry; Anthropic Engineering, the Claude blog, OpenAI's company and developer blogs, official webinar/training catalogs, and public conference talks by staff. The literature search covered arXiv, ACL Anthology, OpenReview, authors' replication packages, and direct citations from the newest context-file studies. Search terms combined `CLAUDE.md`, `AGENTS.md`, context/configuration files, instruction following, long context, context engineering, skills, hooks, and coding-agent evaluation.

OpenAI product claims below use the current official Codex manual fetched from `learn.chatgpt.com` on 2026-08-21. OpenAI company/developer posts are separately labeled as practice. Community posts and vendor-independent templates were used only to discover primary sources; no recommendation relies on them.

Documentation pages do not expose publication or update dates. They are marked “accessed 2026-08-21”; dated posts and papers carry their visible date. The latest documentation is treated as authoritative where older advice conflicts. An independent `gpt-5.6-sol`/xhigh adversarial review then challenged the draft against the repository implementation and newest source revisions; the corrections it established are incorporated below.

## Executive diagnosis

### P0: Codex is silently losing half the project instructions

- **OpenAI product fact:** Codex loads one global instruction file, then concatenates at most one project instruction file per directory from repository root to current working directory. `project_doc_max_bytes`, 32 KiB by default, limits the project-file chain; the global file is represented separately. Codex builds the chain once per run/session. The documentation's “combined size” wording is ambiguous about global scope; current Codex 0.147.0 session state and implementation apply the counter to project instructions. Source: [Custom instructions with AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md), accessed 2026-08-21; current session `world_state.state.agents_md` inspection.
- **Repository fact:** there is no tracked `.codex/config.toml`, and the user config does not override `project_doc_max_bytes`. Root `AGENTS.md` alone is 66,692 bytes. The active global `~/.codex/AGENTS.md` is another 445 bytes of total context but does not consume the project-chain byte budget.
- **Repository fact:** the first 32,768 bytes of `AGENTS.md` end inside line 89 at “its half-written evidence carries no `verdict.json` and is”. Codex therefore receives only part of the command surface and none of the complete `Failure classes`, `Contract`, `Toolchains`, `Commits`, `Working style`, or `Agent skills` sections. This is a correctness defect, not merely a token-efficiency opportunity.
- **Inference:** temporarily raising the Codex limit is justified as containment, but retaining a large limit would conceal future growth and preserve the attention/staleness problems both vendors describe. The durable fix is a root small enough to fit with headroom under the default chain limit.

### Growth and concentration

| Revision/date | Lines | Words | Bytes | Observation |
|---|---:|---:|---:|---|
| Founding file, 2026-07-30 (`c1c06a4`) | 70 | 596 | 4,086 | Initial project guidance |
| 2026-08-08 (`2525475`) | 173 | 7,442 | 47,709 | Value in the reported observation's baseline |
| Symlink conversion, 2026-08-09 (`b3f3a23`) | 173 | 7,442 | 47,709 | `AGENTS.md` became source; `CLAUDE.md` became symlink |
| 2026-08-19 (`85098f0`) | 187 | 10,185 | 65,001 | Exact upper value in the reported observation |
| Current, 2026-08-21 | 189 | 10,452 | 66,692 | 40.4% word growth from August 9 in twelve days |

**Repository fact:** line count grew only 9.2% while words grew 40.4%, which explains why the literal 200-line heuristic did not constrain the artifact. The current file is about 21.6 times the 485-word median Claude context file and 31.2 times the 335.5-word median Codex context file in the latest 2,303-file field study. Those medians are descriptive, not normative targets. Source for corpus medians: Chatlatanagulchai et al., [Agent READMEs](https://arxiv.org/abs/2511.12884), revised August 9, 2026.

| Current section | Words | Bytes | Share of root words | Likely destination |
|---|---:|---:|---:|---|
| Command surface | 3,945 | 25,024 | 37.7% | Self-describing `just` commands, small root trigger, task skills |
| Working style | 2,782 | 17,029 | 26.6% | Mechanical checks, concise universal rules, ADR/process history |
| Seats and profiles | 1,562 | 9,689 | 14.9% | Registry-generated briefs and provider agent definitions |
| All other sections | 2,163 | 14,950 | 20.7% | Prune, retain, or scope statement by statement |

**Repository fact:** the top three sections contain 79.3% of words and 77.6% of bytes. They are coherent extraction seams; no semantic minification is required to get below the Codex cap.

### Provider adapters exist, but their coverage is asymmetric

- **Repository fact:** Claude Code 2.1.238 has four project agent definitions, four project skills, one 8.7 KiB legacy command, nine hook programs, and project permissions/hook wiring in `.claude/settings.json`. Codex CLI 0.147.0 has no static tracked project skills, custom agents, rules, or `.codex/hooks.json` in `.agents`/`.codex`.
- **Repository fact:** dispatched Codex is not unprotected. `tools/dispatch.py` translates every configured `PreToolUse` and `PostToolUse` command from `.claude/settings.json` into per-invocation Codex `--config hooks.*` values through `tools/hook_parity.py`. Unit tests execute committed denial hooks against captured Codex payloads, and a live Codex probe proved that exit code 2 blocks the command and prevents the write. Sources: `tools/dispatch.py::_codex_hook_argv`, `tools/hook_parity.py`, `tests/unit/test_hook_parity.py`, and [Codex lane live findings](./codex-lane-live-findings.md#4-hook-parity-proven-and-it-needed-no-hook-edited).
- **Repository fact:** the proof is narrower than “all enforcement is equivalent.” It covers configured command hooks on dispatched Codex, including live `PreToolUse` denial. It does not prove every edit payload, every `PostToolUse` consequence, unconfigured lifecycle events, or an interactive Codex session launched outside `just dispatch`.
- **Inference:** provider-specific files should remain thin adapters over shared commands, registries, and hook logic. The next work is an invariant-to-enforcement coverage audit and targeted gap closure, not construction of a second hook system.

### Telemetry is rich enough to direct an experiment, not yet to prove one

- **Project telemetry:** at the 2026-08-21T19:34Z snapshot, local storage contained 1,485 Claude JSONL session files (about 1.5 GiB), 715 Codex session JSONLs (about 503 MiB), and 671 Codex files mentioning this repository. There were 664 dispatch records: 321 `claude-native`, 191 `codex`, and 152 `zai`; 663 result files, of which 650 carried an outcome; and 83 dispatch review verdicts containing 163 findings. Only six normalized ledger rows existed, so the ledger was not yet a representative cross-lane dataset. Counts are file counts under `~/.claude/projects`, `~/.codex/sessions`, and `~/.arma-cti/dispatches`; result/verdict content counts select the `outcome` and `findings` fields. This snapshot is reproducible but live state will grow.
- **Project telemetry:** the current 909 MiB OTel capture window contains 10,863 Claude LLM-request spans, 10,999 tool spans, 10,297 tool-execution spans, 914 interaction spans, 7,741 token-usage metrics, 7,741 cost metrics, and 141 session-count points. Dispatch ID, issue, lane, profile, seat, base SHA, tokens, latency, tool decisions, and skill names are available for joins.
- **Project telemetry:** dispatched Codex already exports to the shared loopback OTel collector. At the review snapshot, 185 per-dispatch files under `/var/log/claude-otel/dispatches` carried `service.name=codex_exec`, CTI dispatch/issue/lane/profile/seat/base-SHA attributes, and Codex token, latency, and tool metrics. `tools/ledger.py` already normalizes `codex.turn.token_usage`, including delta-versus-cumulative temporality. The gap is materializing and joining the existing capture—not adding another exporter. Sources: `tools/dispatch.py::_codex_metrics_override`, [telemetry ledger](../telemetry-ledger.md#cross-lane-normalisation), and `tools/ledger.py`.
- **Repository fact:** the existing [token-efficiency study](./token-efficiency.md) found 97.1% of raw Claude input tokens were cache reads and estimated a small API-input-equivalent saving from then-proposed root moves. The [plan-currency follow-up](./token-efficiency-plan-currency.md) found generation/output, not cached context, dominates current subscription-plan usage. Root reduction should therefore be justified primarily by restored Codex correctness, adherence, context headroom, latency, and maintainability—not by an assumed large subscription saving.
- **Project telemetry/privacy:** 914 current OTel spans carry both `user_prompt` and `user_prompt_length` attributes, and identity attributes are common. This report did not inspect their values. New measurement should record guidance hashes, lengths, sources, and outcomes rather than adding prompt bodies; prompt/identity retention needs a separate privacy review.

## The 200-line recollection is correct, but the unit matters

- **Official guidance:** Anthropic currently says to “target under 200 lines per `CLAUDE.md` file”; longer files consume more context and reduce adherence. It separately says that concise, specific instructions work better; recommends Markdown headings and bullets; warns that contradictory rules can be selected arbitrarily; and recommends periodically pruning outdated or conflicting content. Source: [How Claude remembers your project](https://code.claude.com/docs/en/memory), accessed 2026-08-21.
- **Anthropic practice:** Anthropic Applied AI's March 24, 2026 advanced-patterns webinar repeats “Keep files < 200 lines,” adds `.claude/rules/` and path scoping, and recommends excluding irrelevant `CLAUDE.md` files to avoid contradiction. Source: [webinar page](https://www.anthropic.com/webinars/claude-code-advanced-patterns) and [official slides, page 7](https://resources.anthropic.com/hubfs/Claude%20Code%20Advanced%20Patterns_%20Subagents%2C%20MCP%2C%20and%20Scaling%20to%20Real%20Codebases.pdf).
- **Repository fact:** `AGENTS.md` is 189 physical lines, 10,452 whitespace-delimited words, and 66,692 bytes. `CLAUDE.md` is a symlink to `AGENTS.md`. The previously observed 10,185 words is already 267 words below the present checkout.
- **Inference:** the repository is technically below the literal line target. It is not within the target's intent: its average line contains about 55 words, so physical line count masks a book-length always-on prompt. Anthropic publishes no word, byte, or token cap that would let us substitute a different official threshold. Actual loaded tokens should therefore be measured with Claude Code's `/context`, not estimated from words.
- **Academic result:** the 2026 configuration-smells paper defines context bloat mechanically as at least 200 lines. This repository demonstrates a limitation of that heuristic: line count alone can miss long-paragraph bloat. The paper's wider categories remain useful, but its threshold is a detection heuristic rather than a performance law. Source: dos Santos et al., [Configuration Smells in AGENTS.md Files](https://arxiv.org/abs/2606.15828), first submitted June 14, 2026.

## What the latest Anthropic guidance says

### 1. Root context is a scarce, always-on resource

- **Official product fact:** root `CLAUDE.md` loads at session start and remains in the session. After compaction, Claude Code re-reads/re-injects root `CLAUDE.md` and unscoped rules. Source: [Context window](https://code.claude.com/docs/en/context-window), accessed 2026-08-21.
- **Anthropic practice:** the June 18, 2026 steering guide calls root `CLAUDE.md` high context cost because every line costs tokens whether relevant or not. It reserves root context for facts needed throughout a session: build commands, directory or monorepo shape, conventions, and team norms. Source: [Steering Claude Code](https://claude.com/blog/steering-claude-code-skills-hooks-rules-subagents-and-more), Michael Segner, June 18, 2026.
- **Official guidance:** Anthropic's current best-practices page says to include only broadly applicable, project-specific facts Claude cannot reliably infer: non-obvious commands, non-default style, test runners, repository etiquette, architectural decisions, environment quirks, and gotchas. It says to exclude facts inferable from code, standard conventions, detailed API documentation, fast-changing information, long tutorials, file-by-file maps, and generic aspirations such as “write clean code.” It proposes a direct deletion test: if removing a line would not cause Claude to make mistakes, cut it. Source: [Claude Code best practices](https://code.claude.com/docs/en/best-practices), accessed 2026-08-21.
- **Official guidance:** project architecture, coding standards, common workflows, and build/test commands are legitimate `CLAUDE.md` subjects, but specificity and concision improve adherence. Source: [How Claude remembers your project](https://code.claude.com/docs/en/memory), accessed 2026-08-21.

### 2. Claude 5 changed the preferred balance from guardrails to judgment

- **Anthropic practice:** for Opus 5 and Fable 5, the Claude Code team removed more than 80% of its system prompt without measurable loss on its coding evals. The team found accumulated instructions conflicted across the system prompt, skills, and user request. This is an internal ablation result, not a prescription to remove exactly 80% from every project. Source: Thariq Shihipar, [The new rules of context engineering for Claude 5 generation models](https://claude.com/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models), July 24, 2026.
- **Anthropic practice:** the same post's current recommendations are to delete obsolete guardrails, give the model room to match surrounding code, use progressive disclosure instead of front-loading everything, place repeated behavior in tool interfaces/descriptions, use auto-memory rather than `CLAUDE.md` as an anecdote ledger, and keep project `CLAUDE.md` lightweight with most of its useful content devoted to codebase-specific gotchas. Long skills should also be split. Source: same July 24 post.
- **Inference:** older advice to repeat or intensify instructions with `IMPORTANT`/`YOU MUST` should not drive a new design. That advice appears in Anthropic's April 18, 2025 best-practices post, while the July 2026 Claude 5 post explicitly describes repetition, examples, and up-front rules as an older playbook to reconsider. Preserve an emphatic instruction only if current telemetry shows it is load-bearing and no deterministic mechanism can enforce it.

### 3. Context quality is a signal-to-noise problem, not a capacity contest

- **Anthropic practice:** Anthropic's context-engineering article describes context as a finite “attention budget” with diminishing returns and recommends the smallest set of high-signal tokens likely to produce the desired behavior. It recommends prompts at the right altitude—neither brittle if/else catalogs nor vague platitudes—and curated canonical examples rather than exhaustive edge-case lists. Source: [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents), September 29, 2025.
- **Anthropic practice:** the August 14, 2026 session guide says every file read and command output remains in the conversation and is sent on subsequent turns. It recommends `/clear` between unrelated tasks, quiet flags for noisy commands, subagents for noisy investigation, and running `/context` in a fresh session to identify unnecessary startup content. Source: Lydia Hallie, [Maximizing the value of your Claude Code sessions](https://claude.com/blog/maximizing-the-value-of-your-claude-code-sessions), August 14, 2026.
- **Official guidance:** current best practices call the context window the most important resource, recommend `/clear` between tasks, and recommend subagents for verbose investigations. Source: [Claude Code best practices](https://code.claude.com/docs/en/best-practices), accessed 2026-08-21.
- **Inference:** prompt caching can reduce the price of repeated prefixes but does not turn loaded text into free attention or context capacity. Cost, loaded-context size, and adherence must be measured separately.

### 4. Prompt instructions are advisory; hard requirements need enforcement

- **Official product fact:** `CLAUDE.md` is model-visible context, not an enforced configuration mechanism. Anthropic directs zero-exception blocks to a `PreToolUse` hook and permissions. Source: [How Claude remembers your project](https://code.claude.com/docs/en/memory) and [Extend Claude Code](https://code.claude.com/docs/en/features-overview), accessed 2026-08-21.
- **Anthropic practice:** the June 2026 steering guide is stronger: “never do this” in `CLAUDE.md` is the wrong mechanism for a real guardrail because models can miss instructions under pressure, ambiguity, long sessions, or prompt injection. Hooks and permissions are the deterministic mechanisms; centrally managed settings are the organization-wide enforcement mechanism. Source: [Steering Claude Code](https://claude.com/blog/steering-claude-code-skills-hooks-rules-subagents-and-more), June 18, 2026.
- **Official product fact:** hook events are deterministic triggers. Command, HTTP, and MCP-tool handlers execute outside the main model context; prompt and agent hook handlers use model judgment in separate contexts. Only returned output consumes main-session context. Source: [Hooks reference](https://code.claude.com/docs/en/hooks) and [Hooks guide](https://code.claude.com/docs/en/hooks-guide), accessed 2026-08-21.
- **Inference:** a root sentence that repeats a gate, formatter, validator, permission, or blocking hook should be presumed redundant until an ablation shows that the prose prevents a different failure. A pointer explaining how to discover or recover from a refusal can still be useful; duplicating the entire enforcement policy is not.

## What the latest OpenAI guidance says

### 1. Keep `AGENTS.md` short, accurate, practical, and scoped

- **OpenAI guidance:** a good `AGENTS.md` covers important layout, run/build/test/lint commands, engineering and PR conventions, constraints, and the definition of done. OpenAI immediately qualifies this: “A short, accurate `AGENTS.md` is more useful than a long file full of vague rules”; start with basics, add rules after repeated mistakes, and reference task-specific planning, review, or architecture documents when the main file grows. Source: [Codex best practices](https://learn.chatgpt.com/guides/best-practices), accessed 2026-08-21.
- **OpenAI guidance:** the customization overview says “Keep it small,” place guidance in the closest directory where it applies, and pair prose with pre-commit hooks, linters, and type checkers. Skills hold richer repeatable workflows without loading their bodies up front. Source: [Codex customization](https://learn.chatgpt.com/docs/customization/overview), accessed 2026-08-21.
- **OpenAI practice:** OpenAI's agent-first product team tried one large `AGENTS.md` and reports that it crowded out task/code context, made all guidance equally noisy, rotted, and resisted verification. The team now uses a roughly 100-line `AGENTS.md` as a table of contents into structured, versioned docs, with linters and a recurring doc-gardening agent. Source: Ryan Lopopolo, OpenAI MTS, [Harness engineering](https://openai.com/index/harness-engineering/), February 11, 2026.
- **Inference:** “roughly 100 lines” is one successful team's design, not an OpenAI product limit. It is nevertheless a useful aspirational shape for this project when combined with a byte/active-chain budget that prevents long-line gaming.

### 2. GPT-5.6 guidance directly favors leaner, ablated prompts

- **OpenAI guidance:** current GPT-5.6 model guidance recommends removing repeated instructions/examples, simplifying tool descriptions, stating each instruction once, exposing only relevant tools, retaining examples when they encode a requirement or repair a measured gap, and measuring context at startup and as the conversation grows. Source: [GPT-5.6 model guidance](https://developers.openai.com/api/docs/guides/latest-model#favor-leaner-prompts), accessed 2026-08-21.
- **OpenAI practice:** in a sample of OpenAI internal coding-agent eval runs, leaner system-prompt configurations improved scores by roughly 10–15%, reduced total tokens by 41–66%, and reduced cost by 33–67%. OpenAI labels the ranges directional, says results vary by workload, and recommends removing one instruction/tool group at a time before rerunning representative evals. This is a model-level result, not an `AGENTS.md` product limit or a forecast for this repository. Source: same guidance.
- **Inference:** the existing cross-provider ablation plan is also the current recommendation for the Codex model consuming this project. It strengthens the case for incremental deletion but does not justify copying OpenAI's percentages into the benefit estimate.

### 3. Root policy should route into narrow skills; scripts and CI handle deterministic steps

- **OpenAI practice:** the OpenAI Agents SDK repositories keep repository policy and short if/then skill triggers in `AGENTS.md`; repeatable verification, compatibility planning, docs sync, release review, and handoff live in narrow repo skills. Skill scripts perform deterministic parts, the model handles contextual parts, and stable workflows can run in GitHub Actions. Source: Kazuhiro Sera, [Using skills to accelerate OSS maintenance](https://developers.openai.com/blog/skills-agents-sdk), March 9, 2026.
- **OpenAI practice:** that post reports 457 merged PRs over December 2025–February 2026 versus 316 in the preceding three months. The observation coincides with the skills/Actions setup but does not isolate its causal effect.
- **OpenAI guidance:** Codex skill metadata is available for discovery; the body and references load when selected. Current repo skills live under `.agents/skills` from current working directory to repository root, and symlinked skill directories are supported. Codex caps the initial skill listing to 2% of the context window or 8,000 characters, whichever is smaller. Source: [Build skills](https://learn.chatgpt.com/docs/build-skills), accessed 2026-08-21.
- **OpenAI practice:** OpenAI's skills guidance warns against “prompt spaghetti” and brittle megadocs, recommends concrete positive/negative routing boundaries, and treats name/description as the decision boundary. Sources: [Shell + Skills + Compaction](https://developers.openai.com/blog/skills-shell-tips) and [Testing Agent Skills Systematically with Evals](https://developers.openai.com/blog/eval-skills), January 22, 2026.

### 4. Scoped judgment stays in instructions; deterministic checks stay outside them

- **OpenAI practice:** Codex Code Review guidance recommends small, consequential, non-obvious rules close to governed code, with both invariant and safe path. Broad rules create noise; formatting and mechanical checks belong in CI. In OpenAI's reported internal suite, rule-guided review recovered 98% of required custom findings versus 58.3% for the baseline, but that is a review-specific vendor evaluation, not a general coding-task result. Source: [Custom Code Review rules for Codex](https://developers.openai.com/blog/custom-code-review-rules-for-codex), accessed 2026-08-21.
- **OpenAI product fact:** Codex lifecycle hooks can run command handlers at `PreToolUse`, `PermissionRequest`, `PostToolUse`, compaction, prompt, subagent, stop, start, and end events. Project hooks require project trust. Source: [Codex hooks](https://learn.chatgpt.com/docs/hooks), accessed 2026-08-21.
- **OpenAI product fact:** Codex `.rules` files control command approval outside the sandbox; they are experimental and are not a substitute for behavioral repository guidance. Prefix rules support inline matching/non-matching tests. Source: [Codex rules](https://learn.chatgpt.com/docs/agent-configuration/rules), accessed 2026-08-21.
- **OpenAI practice/staff talk:** in his April 9, 2026 AI Engineer Europe keynote, Lopopolo described delivering instructions at the point of need through lints, structural tests, skills, and reviewer agents instead of front-loading a system prompt, and advised doing the minimum harness work that produces the needed feedback. Sources: [conference program](https://www.ai.engineer/europe/2026), [recording](https://www.youtube.com/watch?v=am_oeAoUhew), and [timestamped talk index](https://talksintel.ai/ai-ml/conferences/aie-eu-2026/harness-engineering-how-to-build-software-when-humans-steer/).

### 5. Evaluate guidance as a behavior change, not a prose cleanup

- **OpenAI practice:** OpenAI's skill-evaluation guide defines an eval as prompt, captured trace/artifacts, checks, and a comparable score. It separates outcome, process, style, and efficiency goals; recommends small targeted prompt sets, including positive and negative triggers; and uses `codex exec --json` for deterministic trace checks. Source: [Testing Agent Skills Systematically with Evals](https://developers.openai.com/blog/eval-skills), January 22, 2026.
- **OpenAI guidance:** custom prompts are deprecated, local-only, and explicit; use skills for repository-shared or implicitly invoked reusable instructions. Source: [Custom prompts](https://learn.chatgpt.com/docs/custom-prompts), accessed 2026-08-21.
- **Inference:** the project's existing retro rule “add a root rule after an observed failure” has only an additive half. Vendor guidance and the corpus evidence require a placement decision, a behavioral check, and a retirement path as part of the same feedback loop.

## Claude Code mechanisms that can replace or supplement root text

The “context cost” entries are Anthropic's documented relative categories, not measured costs for this repository.

| Mechanism | Loading and persistence | Appropriate use | Important limitations | Sources |
|---|---|---|---|---|
| Root `CLAUDE.md` | Always at session start; high cost; root is re-read after compaction | Small set of universally needed, non-obvious repository facts and commands | Advisory, not enforcement; every line competes in every task | [memory](https://code.claude.com/docs/en/memory), [context window](https://code.claude.com/docs/en/context-window), [steering](https://claude.com/blog/steering-claude-code-skills-hooks-rules-subagents-and-more) |
| Parent and nested `CLAUDE.md` | Parent files load at launch; a child file loads when Claude reads within its subtree; child context is lost after compaction until the subtree is touched again | Conventions owned by one directory or component | Scope follows directory traversal, not arbitrary globs; an irrelevant parent still loads | [memory](https://code.claude.com/docs/en/memory), [steering](https://claude.com/blog/steering-claude-code-skills-hooks-rules-subagents-and-more) |
| `.claude/rules/*.md` | Unscoped rules are always loaded; `paths` frontmatter loads only when matching files are read; rules are re-injected after compaction subject to scope | Cross-cutting constraints applying to selected file patterns | Splitting into unscoped files organizes text but saves no context; unscoped rules are mechanically equivalent to root content | [memory](https://code.claude.com/docs/en/memory), [features](https://code.claude.com/docs/en/features-overview), [steering](https://claude.com/blog/steering-claude-code-skills-hooks-rules-subagents-and-more) |
| `@path` imports | Imported file is loaded in full at launch; nested imports are followed up to four hops | Single-source organization and reuse | Imports do not save context; they only move bytes between files | [memory](https://code.claude.com/docs/en/memory) |
| Symlink `CLAUDE.md -> AGENTS.md` | Claude Code follows the symlink and sees the target as project context | One source shared with tools that natively use `AGENTS.md` | Solves source duplication only; it does not reduce Claude's loaded context | [memory](https://code.claude.com/docs/en/memory) |
| Skills | Skill name/description normally load at startup; body and referenced support files load when invoked or matched; invoked skills are re-injected after compaction within a shared budget | Procedural workflows, review/release/deploy checklists, occasional reference material, reusable scripts/assets | Trigger descriptions themselves consume startup context; overly broad descriptions under/over-trigger; full skill remains session context once invoked; keep `SKILL.md` below 500 lines and put detail in support files | [skills](https://code.claude.com/docs/en/slash-commands), [features](https://code.claude.com/docs/en/features-overview), [skills practice](https://claude.com/blog/lessons-from-building-claude-code-how-we-use-skills) |
| Manual-only skills | With `disable-model-invocation: true`, absent from auto-invocation context and invoked explicitly | Side-effectful or rare operator workflows where zero startup cost matters | The user or dispatch harness must invoke them; no automatic discovery | [skills](https://code.claude.com/docs/en/slash-commands) |
| Forked skills | `context: fork` runs the skill in isolated subagent context | Procedures whose intermediate search/output should not pollute the main session | Only the result returns; procedure is less steerable in the main thread | [skills](https://code.claude.com/docs/en/slash-commands), [features](https://code.claude.com/docs/en/features-overview) |
| Legacy slash commands | `.claude/commands/*.md` still works | Compatibility with existing commands | Anthropic recommends skills for new work because skills can bundle supporting files; migrating the filename alone changes no instruction quality | [skills](https://code.claude.com/docs/en/slash-commands) |
| Custom subagents | Name, description, and tools load at startup; body loads on invocation in an isolated context; only a summary returns | Deep search, log analysis, dependency audit, focused review, parallel side work | Ordinary custom subagents still receive project `CLAUDE.md`; moving text to an agent definition does not erase an oversized root from that subagent. Built-in Explore and Plan agents omit project `CLAUDE.md` and git status | [subagents](https://code.claude.com/docs/en/sub-agents), [features](https://code.claude.com/docs/en/features-overview) |
| Hooks | Event configuration runs outside the model loop; usually zero main-context cost unless output is returned | Deterministic formatting, validation, denials, logging, notifications, and instruction-load telemetry | Deterministic trigger does not make prompt/agent hook judgments deterministic; noisy returned output can itself bloat context | [hooks](https://code.claude.com/docs/en/hooks), [hooks guide](https://code.claude.com/docs/en/hooks-guide), [steering](https://claude.com/blog/steering-claude-code-skills-hooks-rules-subagents-and-more) |
| `InstructionsLoaded` hook | Fires when a `CLAUDE.md` or rule is loaded and reports the source/reason | Measure actual hierarchical and path-scoped instruction loading | Observes loading, not whether the model followed the instruction | [hooks reference](https://code.claude.com/docs/en/hooks) |
| Permissions and managed settings | Enforced by the harness/admin policy | Operations that must be denied or approved | They control tool authority, not architectural taste or reasoning | [permissions](https://code.claude.com/docs/en/permissions), [steering](https://claude.com/blog/steering-claude-code-skills-hooks-rules-subagents-and-more) |
| `SessionStart` hook | Runs on start/resume/clear and can return dynamic context or set environment | Small, current, computed context such as an issue or live state | Runs every session; Anthropic says keep it fast; returned context is still context, so this can recreate root bloat dynamically | [hooks reference](https://code.claude.com/docs/en/hooks) |
| Output styles | Injected into and persists in the system prompt; high cost | A substantial role, tone, or response-format change | Not a home for project knowledge; custom styles can remove built-in coding instructions unless `keep-coding-instructions: true`; apply only to the main agent | [output styles](https://code.claude.com/docs/en/output-styles), [steering](https://claude.com/blog/steering-claude-code-skills-hooks-rules-subagents-and-more) |
| Appended system prompt/file | Applied at startup for one CLI invocation; remains through the invocation | Dispatch-specific tone, format, or truly task-specific steering | Moderate persistent cost; replacement-system-prompt flags discard Claude Code defaults and are much riskier | [CLI reference](https://code.claude.com/docs/en/cli-reference), [steering](https://claude.com/blog/steering-claude-code-skills-hooks-rules-subagents-and-more) |
| Auto-memory | A small index is loaded at startup and topic files can be read on demand; machine-local | Claude-learned debugging facts and personal patterns that should evolve from experience | Not a shared, version-controlled policy mechanism; susceptible to stale or poisoned memories; not an enforcement layer | [memory](https://code.claude.com/docs/en/memory), [new context rules](https://claude.com/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models) |
| MCP or purpose-built CLI/tools | Tool names/descriptions are exposed; data and results enter when tools are called | Discoverable source-of-truth queries, live state, concise command contracts, external services | Too many overlapping tools and verbose results also consume context; tools need evaluation and token-efficient outputs | [MCP](https://code.claude.com/docs/en/mcp), [Writing effective tools](https://www.anthropic.com/engineering/writing-tools-for-agents) |
| Plugins | Package skills, agents, hooks, and MCP servers for distribution | Reusable capability shared across projects or installed selectively | Packaging does not change the loading behavior or quality of the packaged components | [plugins](https://code.claude.com/docs/en/plugins) |
| Dynamic workflows | A task-generated JavaScript harness coordinates isolated agents, models, worktrees, loops, or adjudication | Long, parallel, highly structured, or adversarial work | New and higher-token; Anthropic says ordinary coding tasks usually do not need it; not a storage mechanism for universal project policy | [A harness for every task](https://claude.com/blog/a-harness-for-every-task-dynamic-workflows-in-claude-code), June 2, 2026 |
| `/clear`, `/compact`, `/context` | Session controls, not stored instructions | Remove unrelated history, compress a long task, and inspect actual loaded context | They do not fix an oversized root: root is present in a new session and re-injected after compaction | [context window](https://code.claude.com/docs/en/context-window), [session value](https://claude.com/blog/maximizing-the-value-of-your-claude-code-sessions) |

## Approximately equivalent Claude Code and Codex surfaces

“Equivalent” means similar placement purpose, not identical loading, precedence, trust, or enforcement semantics. Those differences determine whether an extraction is safe.

| Need | Claude Code CLI | Codex CLI | Project implication |
|---|---|---|---|
| Always-on repository kernel | Root `CLAUDE.md`; this repo's symlink to `AGENTS.md` is supported; target under 200 lines | Global instructions plus root-to-CWD project `AGENTS.md`; the project chain stops at 32 KiB by default | Keep the symlink and one source; budget the project chain under Codex's cap and track global context separately |
| Directory-specific instructions | Parent files load at launch; child `CLAUDE.md` loads lazily when Claude reads in its subtree | Only files from root down to the launch CWD load at session start; later traversal below CWD does not add a child file | Nested files are not portable in behavior. For Codex, dispatch with `--cd` to the owning subtree or use a selected skill/brief |
| File-pattern behavioral rules | `.claude/rules/*.md` supports `paths` frontmatter; unscoped rules are always loaded | No corresponding path-glob behavioral rule. `.codex/rules` governs command approvals; nested `AGENTS.md` is CWD-scoped | Use Claude path rules only as an adapter; keep the underlying constraint/test/provider-neutral. Never assume Codex saw it |
| Reusing/importing prose | `@path` imports and symlinks; imports are eager | No documented `AGENTS.md` import mechanism; files may point to docs the agent reads on demand | Preserve the root symlink; use explicit, validated pointers rather than eager imports for detail |
| Repeatable workflows | `.claude/skills`; metadata first, body on demand; manual-only and forked modes | `.agents/skills` scanned CWD-to-root; metadata first, body on selection; symlinks supported | Put shared skill source in one generated/symlinked layout after resolving this environment's read-only `.agents` mount; test trigger parity |
| Legacy/custom slash prompts | `.claude/commands` still works, but Anthropic recommends skills for new workflows | Custom prompts are deprecated and local-only; OpenAI recommends skills | Migrate `orchestrator-tick` to a shared skill or `just` workflow, not a second Codex prompt |
| Specialized subagents | `.claude/agents/*.md`; isolated context, tool/model/permission options; ordinary agents inherit project root | `.codex/agents/*.toml`; narrow roles can set developer instructions, model, effort, sandbox, MCP, and skills | Generate both provider adapters from `tools/dispatch.py`'s seat registry. External `just dispatch` remains the stronger process/isolation boundary |
| Deterministic lifecycle actions | Hooks configured in `.claude/settings.json`; includes `InstructionsLoaded`; command/HTTP/MCP handlers | Hooks in `.codex/hooks.json` or config; similar start/tool/prompt/compact/subagent/stop/end events; no documented `InstructionsLoaded` event | Dispatched Codex already translates the repository's configured command hooks. Audit and test uncovered events/payloads rather than build a second system; keep provider-only observability explicit |
| Permissions and command authority | Settings allow/deny, permissions, managed settings, and `PreToolUse` hooks | Sandbox/approval policy, permission profiles, `.rules` prefix decisions, managed requirements, and hooks | Enforcement must be proved independently in both harnesses; prose is not the fallback for a missing safety boundary |
| Output/role style | Output styles persist in the main system prompt and can replace coding defaults | No documented repo-scoped output-style counterpart; custom agent developer instructions cover specialized roles | Do not move correctness policy here. Keep normal project prose and role-specific generated agent instructions |
| Local learned memory | Auto-memory index plus on-demand topic files; machine-local | Codex memories carry learned/personal context in supported clients; not shared repository policy | Do not use either for binding team rules or audit history |
| External/live systems | MCP/tools/plugins; tool descriptions/results consume context when exposed/called | MCP/tools/plugins with similar role; plugins can bundle skills, MCP, and hooks | Use MCP for live/off-repo state, not static policy already versioned locally. No new plugin is needed for this single-repo migration |
| Deterministic project workflow | Shell plus project commands, hooks, tests, CI | Shell plus project commands, hooks, tests, CI | `just` is the deepest portable interface already present. Make it discoverable and keep provider adapters thin |
| Loaded-context inspection | `/context`, `InstructionsLoaded`, session logs, OTel | Session JSONL `world_state.state.agents_md.text`; TUI/session events; `codex exec --json` for evals | Hash captured loaded text against deterministic discovery output. A model summary or later file read is an adherence test, not proof of startup loading |

Sources: Claude columns use the official documentation linked in the preceding table. Codex columns use [AGENTS.md discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md), [skills](https://learn.chatgpt.com/docs/build-skills), [subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents), [hooks](https://learn.chatgpt.com/docs/hooks), [rules](https://learn.chatgpt.com/docs/agent-configuration/rules), [custom prompts](https://learn.chatgpt.com/docs/custom-prompts), and [MCP](https://learn.chatgpt.com/docs/extend/mcp), all accessed 2026-08-21.

### Portability traps

- Splitting prose into unscoped Claude rules or `@imports` changes organization, not startup context.
- A nested file is lazy in Claude but invisible to a Codex session launched at repository root. A ticket that introduces hierarchy must state the Codex launch-CWD or skill-routing counterpart.
- A Claude hook protects dispatched Codex only when `tools/hook_parity.py` translates it and the relevant payload/blocking semantics are proved. Interactive Codex outside `just dispatch` does not inherit that runtime adapter.
- A `.codex/rules` file is an approval boundary, not a place for architecture or workflow prose.
- Skills are progressive, not free: both providers expose metadata at startup, and broad catalogs/descriptions can consume the listing budget or misroute.
- Custom subagents do not erase root cost: Claude ordinary subagents inherit root instructions, and Codex custom agents are full spawned configurations.
- Output styles, auto-memory, MCP, and plugins solve different problems. Using them as a policy dumping ground would preserve or increase context and maintenance cost.

### Placement decision distilled from Anthropic's current sources

1. Does it have to hold mechanically every time? Use a hook, permission, managed setting, test, linter, gate, or tool contract; keep only the minimum human/model-facing recovery hint.
2. Must every task know this non-obvious repository fact? Keep a short root statement.
3. Does it apply only to a directory? Use nested `CLAUDE.md`.
4. Does it apply to a glob or cross-cutting subset? Use a path-scoped rule.
5. Is it a procedure or occasional reference? Use a skill, possibly manual-only or forked.
6. Is it verbose investigation or a focused role? Use an isolated subagent and return a small result.
7. Is it live state or detailed command semantics? Expose a concise, discoverable CLI/tool rather than copying a changing table into context.
8. Is it tone or output shape only? Consider an output style or invocation-specific appended prompt, not repository policy.
9. Is it obvious from nearby code, already enforced, historical narration, or generic good practice? Delete it from agent context.

Steps 1–9 are an **inference** that composes the official feature-selection guidance; no single Anthropic source presents exactly this sequence.

## Direct academic evidence on repository context files

The literature does not support either “context files always help” or “delete them entirely.” It supports minimal, specific, evaluated guidance.

| Study | Design and reported result | What it supports here | Limits |
|---|---|---|---|
| Gloaguen et al., [Evaluating AGENTS.md](https://arxiv.org/abs/2602.11988), v2 revised June 23, 2026 | Multiple agents/models on SWE-bench Lite plus 138 CTXbench tasks with developer files. LLM-generated files changed mean success by −0.5 percentage points on SWE-bench and −2 points on CTXbench, neither significant, while raising cost by 20% and 23%. Developer files averaged +2.4 points versus no file (`p=.21`) at up to 19% extra cost; developer files significantly outperformed LLM-generated ones by about 7 points (`p=.038`). Both induced more exploration/testing. | Extra requirements are not free; human curation matters; compare against both no-file and generated-file controls; report significance and the behavioral/cost path. | Models included Sonnet 4.5, GPT-5.2, GPT-5.1 mini, and Qwen3-30B, not current Claude 5/GPT-5.6 profiles. One sample per setting and aggregate results hide repository/task interactions. |
| Lulla et al., [Impact of AGENTS.md on efficiency](https://arxiv.org/abs/2601.20404), revised March 30, 2026, ICSE JAWs 2026 | Paired Codex runs on 124 small PR tasks from 10 repositories. With existing `AGENTS.md`, median runtime fell 28.64% and output tokens 16.58%; a 50-task sample checked only that changes were non-trivial and relevant. | A concise navigation/operations file can reduce wandering and improve throughput; removing all repository guidance may lose efficiency. | One agent, small changes (under 100 changed lines and at most five files), efficiency rather than gold-test correctness, and weak completion validation. It does not establish that a larger file is better. |
| Khatri, [Do Context Files Help Coding Agents?](https://arxiv.org/abs/2607.27250), July 28, 2026; REALM/EMNLP 2026 under review | 288 runs, Claude Code and Codex, 17 tasks across three Python repositories, three repeats, gold tests, with none vs always-on vs selective context. Reported correctness was statistically flat: Claude 53.3% none vs 55.6% always/selective; Codex 58.8% none vs 56.9% always vs 52.9% selective. | Context strategy may improve operations without fixing skill-gated implementation failures. Project evals should target known instruction-sensitive failures, not only overall pass rate. | Single-author preprint, only three repositories and 17 tasks; equivalence bounds remain broad (roughly 10–15 percentage points); contemporary but still model/version-specific. |
| Shepard and Albrecht, [Probe-and-Refine Tuning](https://arxiv.org/abs/2606.20512), June 18, 2026; accepted to a COLM 2026 workshop according to the authors | Synthetic bug-fix probes iteratively refined repo guidance. On SWE-bench Verified with Qwen3.5-35B over four trials, mean resolve rate rose from 25.5% unguided and 28.3% static guidance to 33.0% refined. Gains came from reaching/evaluating more patches, not greater per-patch precision; a second model degraded. | Guidance should be derived from observed failures and evaluated on the consuming profile. It can improve localization/coverage, not substitute for implementation capability. | Different open models and a custom 16k harness, not Claude Code/Codex; synthetic tuning risks overfitting; cross-model transfer failed. |
| dos Santos et al., [Configuration Smells in AGENTS.md Files](https://arxiv.org/abs/2606.15828), June 14, 2026; accepted SCAM 2026 per the manuscript | Grey-literature-derived catalog, heuristics, and manual review of 100 popular repositories. At least one smell appeared in 91 files: lint leakage 62%, context bloat 42%, skill leakage 35%, conflicting instructions 28%, init fossilization 24%, blind references 16%. Detector precision varied from 57% for conflicts to 93% for lint leakage. | A practical audit vocabulary: enforceable duplicates, rare procedures, conflict, staleness, and unexplained links are plausible root-removal candidates. | Prevalence study, not a causal performance evaluation; 200-line bloat threshold misses this repository's long-line case; conflict detector is noisy. |
| Chatlatanagulchai et al., [Agent READMEs](https://arxiv.org/abs/2511.12884), v2 revised August 9, 2026 | Mined 2,303 context files in 1,925 repositories. Common content was testing (75.9%), implementation details (70.8%), architecture (68.1%), and build/run commands (63.0%); files evolved through frequent small additions while deletions were negligible. | Treat context as maintained configuration with review and deletion, not a write-once README. The additive-growth pattern matches the reported 7,442→10,185→10,452 words here. | Descriptive corpus study; common content is not proof that content is beneficial. |

### Broader context and instruction-following evidence

- **Academic result:** Liu et al.'s TACL study found that long-context performance depends strongly on position and often degrades when relevant information sits in the middle. Source: [Lost in the Middle](https://aclanthology.org/2024.tacl-1.9/), TACL 2024. This supports salience concerns, not a Claude Code-specific line cap.
- **Academic result:** Levy et al. found performance declines as irrelevant context length grows even when retrieval is perfect, across several model families and tasks including code. Source: [Context Length Alone Hurts LLM Performance Despite Perfect Retrieval](https://aclanthology.org/2025.findings-emnlp.1264/), Findings of EMNLP 2025. The tested models predate Claude 5.
- **Academic result:** He et al.'s multi-turn instruction-following benchmark reported instruction-following degradation over turns and large recovery when all instructions were restated at the end; Claude 3.5 Sonnet was among the older models tested. Source: [MMMT-IF](https://arxiv.org/abs/2409.18216), September 2024. This supports fresh task briefs for task-specific constraints, not repeated global root text.
- **Academic result:** Laban et al. found substantial unreliability in multi-turn decomposition even where single-turn aptitude changed little. Source: [LLMs Get Lost in Multi-Turn Conversation](https://www.microsoft.com/en-us/research/publication/llms-get-lost-in-multi-turn-conversation/), ICLR 2026. This supports clean sessions and durable handoffs for a new task.
- **Anthropic practice:** Anthropic's dynamic-workflow post identifies goal drift after long sessions and compaction, and uses isolated focused agents to reduce it. Source: [A harness for every task](https://claude.com/blog/a-harness-for-every-task-dynamic-workflows-in-claude-code), June 2, 2026.
- **Inference:** these studies explain why a 10,452-word prompt is risky, but none measures this repository on its actual Claude/Codex profiles. They justify a hypothesis and an evaluation plan, not an unconditional rewrite.

## Prioritized project interventions

This is a qualitative CD3 ordering: continuing delay/risk avoided divided by delivery duration. It exposes the inputs rather than pretending sparse evidence supports a monetary delay-cost number. Reach is the share of future runs exposed; severity is 1–5; confidence grades the evidence for that harm/benefit. Delivery estimates count autonomous-agent landings and minimum evaluation runs, not human days.

The project supplies useful cycle anchors: at the 2026-08-21 snapshot, 327 successful implementer dispatches had a median duration of 1,091 seconds (interquartile range 654–1,718), while 254 successful review dispatches had a median of 502 seconds (382–675). `just gate-clock-history` reported last-ten-green medians of 64 seconds for `unit` and 105 seconds for `fast`. These are baselines for analogous work, not promises: queueing, review rounds, quota, task scope, and the intervention's evaluation runs dominate elapsed delivery time.

“Minimum eval runs” is an experimental floor, not a claim of statistical power. A basic cross-provider paired pilot is 36 runs: three task classes × two prompt variants × two representative providers × three repeats. The pilot estimates variance; the final sample and non-inferiority margin must then be predeclared. Trigger suites use 10–20 positive/negative prompts per OpenAI's guidance and can therefore exceed the table's floor when repeated across profiles.

| Rank | Intervention | Reach / severity / confidence | Estimated delivery evidence | Qualitative CD3 | Benefit onset |
|---:|---|---|---|---|---|
| 0 | Contain and detect Codex truncation | Every current Codex run / 5 / high | 1 focused landing; 2 deterministic load checks; no behavioral claim | Highest | Next Codex dispatch |
| 1 | Attribute guidance and materialize the existing telemetry | All subsequent experiments / 4 / high | 1–2 landings; backfill existing bus; no new exporter | Very high | First attributable dispatch |
| 2 | Build the targeted paired evaluation pilot | All later prompt changes / 4 / high | Multi-landing/eval package; ≥36 runs before sample sizing | High prerequisite | First trustworthy ablation |
| 3 | Remove/archive historical narration and establish the kernel skeleton | Every provider run / 4 / high | 1 focused landing plus pilot execution | Very high after rank 2 | First deletion cohort |
| 4 | Audit existing enforcement, close evidence gaps, remove prose duplicates | Every provider run and safety boundary / 5 / high | 1–2 landings plus targeted negative/live tests | High | Per proved invariant family |
| 5 | Replace the 25 KiB command catalog with deep `just` help | Every provider run / 4 / high | 2–3 landings plus ≥60 command-routing runs | High | Per migrated command family; completes cap exit with rank 3 |
| 6 | Move seat/lifecycle procedures to shared skills, briefs, and generated adapters | Seat-specific runs / 3 / medium | 2–4 landings per workflow cluster plus ≥60 trigger runs | Medium-high | Per migrated workflow |
| 7 | Add root-budget, placement, and retirement governance | Every future guidance change / 4 / high | 1 landing after ranks 3–5 | High | Next attempted addition |
| 8 | Scope specialized guidance with provider-aware routing | Subtree-specific runs / 2 / medium | 1–3 landings per subtree plus ≥12 scope cases | Medium | Per subtree/task route |
| 9 | Expand isolated reconnaissance/review only on measured pressure | Long/noisy runs / 2 / low pending measurement | 1 landing and ≥12 paired runs per candidate | Conditional | Only after telemetry shows pressure |

### 0. Contain and detect Codex truncation

- **Intervention:** before another Codex implementation/review run, temporarily set `project_doc_max_bytes` to 96 KiB in the dispatcher's per-invocation configuration. This covers the current 66,692-byte root project file with headroom without changing interactive Codex globally. Add a preflight assertion that computes the expected root-to-CWD project sources and refuses a captured loaded-project text that is truncated or differs.
- **Grounding:** OpenAI documents the default limit, silent stop behavior, source-verification commands/logs, and raising/splitting as remedies. Source: [AGENTS.md discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md). The temporary 96 KiB value is a project inference from measured bytes, not vendor guidance.
- **Measure/accept:** compare a normalized hash of session JSONL `world_state.state.agents_md.text` with the deterministic expected project instruction text; record source paths, bytes, launch CWD, harness version, and query timestamp. The current line-89 cutoff must disappear. Late-file canaries remain separate adherence tests because Codex can read the file later with a tool. Exit condition: remove the override after every supported dispatch CWD has a project chain no larger than 24 KiB. Track the global file separately as total context.

### 1. Attribute guidance and materialize the telemetry already captured

- **Intervention:** extend the existing dispatch/ledger path with an immutable guidance manifest: provider/harness version, guidance variant, project/global source paths and hashes kept distinct, captured loaded-text hash, actual startup tokens where available, skill-catalog and hook/policy digests, model/profile/effort/seat, base SHA, launch CWD, and query version. Materialize/backfill the existing per-dispatch OTel files and Codex session JSONLs through `tools/ledger.py`; do not build a second exporter.
- **Grounding:** Anthropic recommends fresh `/context`, instruction-load telemetry, prompt ablation, and per-model evaluation; OpenAI defines trace/artifact/check evals and 10–20 prompt trigger sets for individual skills. Sources: [Anthropic session value](https://claude.com/blog/maximizing-the-value-of-your-claude-code-sessions), [Anthropic quality postmortem](https://www.anthropic.com/engineering/april-23-postmortem), and [OpenAI skill evals](https://developers.openai.com/blog/eval-skills).
- **Measure/accept:** every new dispatch joins its manifest to result, gate, review verdict, provider metrics, and elapsed time; backfill reports exact covered, degraded, unclassified, in-flight, and missing counts instead of treating absence as failure. Re-running the documented queries yields the published counts. No prompt body is added to telemetry.

### 2. Build the targeted paired evaluation pilot

- **Intervention:** freeze a small versioned corpus with three strata: historical instruction-sensitive failures, ordinary representative work, and negative controls where migrated guidance must not trigger. Add a runner that holds base SHA, task, profile, effort, permission mode, worktree state, timeout, resources, tool/harness versions, and cache state constant; randomize prompt-variant order and retain traces/artifacts/checks. Start with at least 36 runs across one representative Claude and Codex profile, then use observed variance to predeclare the full sample, profile coverage, and quality/safety non-inferiority margins.
- **Grounding:** Anthropic's quality postmortem requires per-model ablation, soak, and gradual rollout; its infrastructure study shows environment alone can move agent benchmarks by several points. OpenAI's current GPT-5.6 and skill-eval guidance require representative tasks, one-group-at-a-time ablation, positive and negative triggers, captured traces/artifacts, and comparable scores. Sources: [Anthropic quality postmortem](https://www.anthropic.com/engineering/april-23-postmortem), [infrastructure noise](https://www.anthropic.com/engineering/infrastructure-noise), [GPT-5.6 model guidance](https://developers.openai.com/api/docs/guides/latest-model#favor-leaner-prompts), and [OpenAI skill evals](https://developers.openai.com/blog/eval-skills).
- **Measure/accept:** the runner reproduces a result from its manifest; reports task quality/safety first, then instruction behavior, throughput, context/tokens, and maintenance; separates cached input, output, tool results, and subagent work; and never treats three repeats as statistical proof. The pilot must finish and publish the full experiment design before a high-risk instruction cohort is deleted.

### 3. Remove/archive historical narration and establish the kernel skeleton

- **Intervention:** apply the deletion test to `Working style` first. Archive dated examples, validation history, rescinded-policy narrative, and detailed rationale in their existing ADR/process-log authorities; delete generic or inferable advice. Retain a concise universal fact or recovery pointer where a current requirement remains. This cohort excludes any sentence whose removal depends on an unproved safety/enforcement mechanism; Rank 4 owns those.
- **Grounding:** Anthropic excludes historical/inferable/tutorial/generic content and reports deleting over 80% of its Claude 5 prompt without measured loss. OpenAI's agent-first team uses a short root map into structured documentation. Sources: [Claude best practices](https://code.claude.com/docs/en/best-practices), [Claude 5 context rules](https://claude.com/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models), and [OpenAI harness engineering](https://openai.com/index/harness-engineering/).
- **Measure/accept:** every removed statement has a deletion/move reason and authoritative destination where one is still needed. Run Rank 2's experiment on the cohort; links resolve; instruction-sensitive and ordinary quality/safety are non-inferior; negative controls do not add search or clarification thrash. The coherent section offers about 17 KiB of reduction. Revert a repeatable profile-specific regression and find a more precise surface.

### 4. Audit existing enforcement, close evidence gaps, and remove prose duplicates

- **Intervention:** inventory every remaining root `always`, `never`, `refuse`, gate, and authority statement. Map it to universal fact, shared command/test/linter, translated hook, permission, skill, scoped guidance, ordinary documentation, or uncovered gap. Treat the existing runtime Codex translation as implementation, not a proposal. Close only demonstrated gaps—especially live Codex edit payload and `PostToolUse` behavior—before deleting a duplicate. Ad-hoc Codex outside `just dispatch` remains a separately declared coverage boundary.
- **Grounding:** both vendors distinguish advisory instructions from hooks, permissions, tests, and CI. Local `tools/hook_parity.py` and its tests already carry every configured command hook; the live findings prove one real `PreToolUse` denial and explicitly leave edit/`PostToolUse` evidence incomplete. Sources: [Claude steering](https://claude.com/blog/steering-claude-code-skills-hooks-rules-subagents-and-more), [Codex hooks](https://learn.chatgpt.com/docs/hooks), [Codex lane live findings](./codex-lane-live-findings.md#4-hook-parity-proven-and-it-needed-no-hook-edited), and `tests/unit/test_hook_parity.py`.
- **Measure/accept:** publish the statement-to-authority map and uncovered gaps. Every migrated safety/data-loss invariant has an adversarial negative test on each consuming harness/profile; live tests cover the provider boundary that unit payload tests cannot. Record block/refusal hits, false denials, bypasses, recovery time, and gate outcome. Remove prose only after equal or stronger behavior is proved.

### 5. Replace the command catalog with a deep, self-describing `just` interface

- **Intervention:** retain only the universal `just` rule and discovery entry point in root. Make each relevant recipe expose current purpose, arguments, preconditions, gate tier, refusal classes, and recovery via `just <verb> --help` or a generated equivalent backed by the command's existing authority. Generate any human index from the same data. Task skills/briefs query this interface rather than copy the table.
- **Grounding:** Anthropic recommends expressive, non-overlapping, token-efficient tool interfaces and moving repeated behavior from prompts into tools; OpenAI reports using standard repository scripts and skills instead of copied instructions. Sources: [Writing effective tools](https://www.anthropic.com/engineering/writing-tools-for-agents), [Claude 5 context rules](https://claude.com/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models), [OpenAI harness engineering](https://openai.com/index/harness-engineering/), and [OpenAI Agents SDK skills](https://developers.openai.com/blog/skills-agents-sdk).
- **Measure/accept:** a 10–20-case positive/adjacent-negative/irrelevant command-discovery suite, repeated on representative Claude and Codex profiles, selects the correct recipe, flags, refusal recovery, and “do not run” cases. Help matches executable schemas/tests; stale-copy defects are zero; unsafe/wrong command attempts and lookup latency do not regress; 25,024 root bytes disappear. Current `just --list` fragments are not sufficient. After ranks 3 and 5, establish a root target of roughly 100 ordinary lines and **≤16 KiB**, with every supported root-to-CWD project chain **≤24 KiB**; these are project headroom targets, not vendor limits. Remove Rank 0's cap override only then.

### 6. Move seat and lifecycle procedures into shared skills, generated briefs, and provider agent adapters

- **Intervention:** keep the authoritative seat/profile registry in `tools/dispatch.py`. Generate concise `.claude/agents/*.md` and `.codex/agents/*.toml` adapters only where an in-session surface is needed. Move review, retro, recovery, land, probe/regress, and orchestration procedures into narrow shared skills or the existing generated dispatch brief. Migrate the legacy `.claude/commands/orchestrator-tick.md` to a skill/`just` workflow; Codex custom prompts are deprecated. Resolve the current read-only `.agents`/`.codex` mount before choosing symlink versus generation. This closes skill/agent-surface asymmetry; it is not hook-parity work.
- **Grounding:** both vendors recommend narrow skills with progressive disclosure and narrow/opinionated subagent roles; OpenAI's production SDK pattern uses short root if/then skill triggers, and Anthropic says a multi-step procedure belongs in a skill. Sources: [Claude skills](https://code.claude.com/docs/en/slash-commands), [Claude subagents](https://code.claude.com/docs/en/sub-agents), [Codex skills](https://learn.chatgpt.com/docs/build-skills), [Codex subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents), and [OpenAI Agents SDK skills](https://developers.openai.com/blog/skills-agents-sdk).
- **Measure/accept:** generator convergence and seat/profile parity tests pass; skill invocation precision/recall is measured with explicit, implicit, adjacent-negative, and irrelevant prompts; procedure completion/gate outcome is non-inferior; listing/body tokens are measured separately; Codex and Claude route the same task to equivalent policy. Remove 9,689 root bytes without duplicating registry facts.

### 7. Prevent regrowth with budget, placement, and retirement governance

- **Intervention:** fold a small guidance check into the existing gate. It enforces line/byte/active-chain budgets, validates links and generated surfaces, and requires an observed failure plus placement rationale for additions: universal fact, skill, path scope, brief, tool/help, enforcement, or ordinary docs. Every addition names a behavior test and retirement condition. Retros default to replacing/deleting an obsolete instruction when code or tooling absorbs it.
- **Grounding:** both vendors recommend adding rules from repeated real failures while keeping them current; OpenAI's harness team mechanically validates docs; Anthropic's postmortem added ablation, audits, soak, and gradual rollout after one prompt line caused a reported 3% regression. Corpus studies show additions dominate deletions. Sources: [Codex best practices](https://learn.chatgpt.com/guides/best-practices), [OpenAI harness engineering](https://openai.com/index/harness-engineering/), [Claude best practices](https://code.claude.com/docs/en/best-practices), [Anthropic quality postmortem](https://www.anthropic.com/engineering/april-23-postmortem), and [Agent READMEs](https://arxiv.org/abs/2511.12884).
- **Measure/accept:** root delta and reason per landing; budget exceptions; stale/duplicate/conflict findings; additions versus deletions; time from observed failure to tested placement; instruction-caused regressions. The check must reject line minification that preserves excess bytes.

### 8. Scope specialized guidance with provider-aware routing

- **Intervention:** after the kernel and skills exist, move genuine directory ownership rules to nested files and cross-cutting Claude-only globs to scoped `.claude/rules`. For Codex, start the dispatched session in the owning subtree or route via a task-selected skill/brief; do not assume late traversal loads a nested file. Avoid unscoped rules/imports.
- **Grounding:** both products document hierarchy, but Claude child loading is lazy while Codex stops at launch CWD. Sources: [Claude memory](https://code.claude.com/docs/en/memory) and [Codex AGENTS.md discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md).
- **Measure/accept:** relevant and irrelevant path cases report actual loaded sources; false-positive/false-negative scope events are zero in the test set; applicable adherence is non-inferior; unrelated startup tokens fall; cross-surface tasks still see every required rule; post-compaction behavior is tested in Claude.

### 9. Expand isolated reconnaissance/review only on measured pressure

- **Intervention:** continue using external `just dispatch` for independent seats. Add or refine in-session subagents only for verbose wiki/log/code searches or review where main-context high-water/compaction data shows a problem. Require compact cited summaries; do not use subagents merely to store root text.
- **Grounding:** Anthropic and OpenAI both describe subagents as context isolation for bounded work and warn through their economics that isolation can increase total tokens. Sources: [Anthropic context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents), [Claude subagents](https://code.claude.com/docs/en/sub-agents), and [Codex subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents).
- **Measure/accept:** main-context high-water, compactions, subagent total input/output, summary size/citation accuracy, missed evidence, elapsed time, and downstream correctness. Adopt only when quality or throughput improves enough to offset added total work.

## Changes that look modular but do not solve the problem

- **Splitting the root into unscoped `.claude/rules` files:** organization improves, but all text remains always loaded. **Official product fact:** unscoped rules have the same context behavior as root content.
- **Importing large documents with `@path`:** source maintenance improves, but imports load in full. **Official product fact:** imports do not provide lazy context.
- **Keeping both a copied `CLAUDE.md` and `AGENTS.md`:** creates drift. **Official product fact:** Claude Code officially supports an import or symlink because it does not natively read `AGENTS.md`; this repository's symlink is the right single-source shape.
- **Reformatting 10,452 words into fewer than 200 lines:** passes a heuristic while preserving context cost and likely reducing scanability. **Inference** from the heuristic's rationale and this repository's current shape.
- **Moving project policy into an output style:** output styles have high persistent cost and can replace default coding behavior. **Official guidance:** use them for substantial role/output changes, not repository knowledge.
- **Using auto-memory for shared rules:** memory is local, mutable, and advisory. It is useful for learned personal facts, not binding, reviewable project governance.
- **Using custom subagents without first shrinking root:** ordinary custom subagents still load project `CLAUDE.md`, so root bloat is inherited.
- **Assuming skills are free:** descriptions consume startup context and invoked bodies consume session context. Hundreds of checked-in skills can create a new listing tax; Anthropic recommends measuring invocation and distributing optional skills selectively.
- **Replacing one giant root with one giant skill:** only changes when the same bloat arrives. Anthropic says keep `SKILL.md` below 500 lines, use progressive supporting files, split long skills, and put high-signal gotchas first.
- **Deleting all repository guidance:** the efficiency study reports material runtime/token gains from existing files, while Anthropic still recommends a small root. The target is minimal high-signal guidance, not zero context.

## Evaluation design required before a spec

### Experimental unit and stratification

- Run each candidate prompt version on the same issue/task starting state and same profile, effort, permission mode, worktree state, timeout, CPU/RAM, dependency cache, and tool versions.
- Stratify at least by model/profile, seat, task surface, gate tier, task duration, and whether the migrated instruction should trigger.
- Include three task sets: historical instruction-sensitive failures, ordinary representative tasks, and negative controls where the migrated instruction is irrelevant.
- Repeat because agent outcomes are stochastic. Pair or randomize run order and report uncertainty.
- **Grounding:** Anthropic found infrastructure configuration alone moved Terminal-Bench scores by up to six percentage points and recommends treating resource configuration as a first-class experimental variable and running across times/days. Source: [Quantifying infrastructure noise in agentic coding evals](https://www.anthropic.com/engineering/infrastructure-noise), February 5, 2026.

### Outcome hierarchy

1. **Quality/safety guardrails:** task correctness, full required gate outcome, data-loss/security incidents, architectural invariant violations, review findings, regressions, and incomplete work.
2. **Instruction behavior:** applicable instruction followed, non-applicable instruction ignored, correct skill/rule loaded, correct command/refusal recovery, contradictions or clarification turns.
3. **Throughput:** elapsed task-to-land time, autonomous completion rate, first-pass gate rate, rework cycles, human interventions, and queue throughput.
4. **Context/usage:** fresh-session root tokens, total main-context high-water mark, compactions, cached/uncached input, output, tool-result tokens, subagent totals, tool calls, latency, and monetary cost.
5. **Maintenance:** prompt diff size, stale-copy findings, root growth, skill/rule trigger defects, and time to update one policy source.

### Decision rule

- Land an extraction when quality/safety is non-inferior within a pre-declared margin and at least one context, throughput, or maintainability metric materially improves.
- Revert or redesign when an applicable behavior regresses, even if average token cost falls.
- Do not accept an overall pass-rate null as proof that a migrated rule is unnecessary; targeted negative tests are more sensitive to rare invariants.
- Evaluate every active model/profile. Anthropic's prompt postmortem and probe-and-refine paper both show model-specific effects.

These decision rules are **inferences**, informed by Anthropic's postmortem/eval practice and the conflicting academic results; they are not an Anthropic product requirement.

## Source chronology and authority notes

### Current Anthropic official documentation, accessed 2026-08-21

- [How Claude remembers your project](https://code.claude.com/docs/en/memory): line target, hierarchy, rules, imports, symlink/`AGENTS.md`, pruning, enforcement distinction, `InstructionsLoaded`.
- [Context window](https://code.claude.com/docs/en/context-window): startup load, compaction re-injection/loss, skills budget, `/context`.
- [Extend Claude Code](https://code.claude.com/docs/en/features-overview): feature-selection matrix, hooks versus skills, subagent isolation, path rules.
- [Claude Code best practices](https://code.claude.com/docs/en/best-practices): include/exclude criteria, deletion test, context hygiene, over-specification failure.
- [Extend Claude with skills](https://code.claude.com/docs/en/slash-commands): legacy commands, progressive loading, manual invocation, forked context, size guidance.
- [Create custom subagents](https://code.claude.com/docs/en/sub-agents): isolated contexts, inheritance, built-in agent exceptions, skill preload.
- [Hooks reference](https://code.claude.com/docs/en/hooks) and [hooks guide](https://code.claude.com/docs/en/hooks-guide): event/enforcement semantics and instruction loading telemetry.
- [Output styles](https://code.claude.com/docs/en/output-styles): system-prompt effects and coding-default caveat.
- [CLI reference](https://code.claude.com/docs/en/cli-reference): appended/replaced system prompt behavior.
- [Manage sessions](https://code.claude.com/docs/en/sessions), [costs](https://code.claude.com/docs/en/costs), [plugins](https://code.claude.com/docs/en/plugins), and [MCP](https://code.claude.com/docs/en/mcp): supporting session, distribution, and tool facts.

### Current OpenAI official documentation, accessed 2026-08-21

- [Custom instructions with `AGENTS.md`](https://learn.chatgpt.com/docs/agent-configuration/agents-md): global/project precedence, root-to-CWD loading, fallback names, the 32 KiB default project-chain cap, and source verification.
- [Codex best practices](https://learn.chatgpt.com/guides/best-practices) and [customization overview](https://learn.chatgpt.com/docs/customization/overview): recommended root subjects, “short, accurate”/“keep it small” guidance, nearest-scope placement, and pairing prose with checks.
- [GPT-5.6 model guidance](https://developers.openai.com/api/docs/guides/latest-model#favor-leaner-prompts): lean prompt ablation, directional internal coding-agent results, relevant-tool selection, and startup/growing-context measurement.
- [Build skills](https://learn.chatgpt.com/docs/build-skills): `.agents/skills`, progressive disclosure, symlinks, metadata budget, and trigger evaluation.
- [Custom agents](https://learn.chatgpt.com/docs/agent-configuration/subagents): narrow roles and provider/model/effort/sandbox/MCP/skill configuration.
- [Hooks](https://learn.chatgpt.com/docs/hooks) and [rules](https://learn.chatgpt.com/docs/agent-configuration/rules): lifecycle interception versus command-approval policy.
- [Custom prompts](https://learn.chatgpt.com/docs/custom-prompts) and [MCP](https://learn.chatgpt.com/docs/extend/mcp): deprecated prompt surface and external tool/data integration.

### Dated Anthropic staff sources

- Dec 19, 2024: [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)—prefer the simplest measured architecture; framework complexity must earn itself.
- Apr 18, 2025: [Claude Code: Best practices for agentic coding](https://www.anthropic.com/engineering/claude-code-best-practices)—historical origin of `CLAUDE.md` conventions. Its emphasis/repetition advice is superseded for current Claude 5 design by July 2026 guidance.
- Sep 11, 2025: [Writing effective tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents)—tool boundaries, descriptions, concise outputs, evaluation.
- Sep 29, 2025: [Effective context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)—attention budget, just-in-time retrieval, compaction, subagents.
- Oct 16, 2025: [Equipping agents with Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)—three-level progressive disclosure and executable assets.
- Nov 26, 2025: [Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)—fresh sessions plus durable progress artifacts.
- Feb 5, 2026: [Infrastructure noise](https://www.anthropic.com/engineering/infrastructure-noise)—control harness/resource/time confounders.
- Mar 24, 2026: [Harness design for long-running application development](https://www.anthropic.com/engineering/harness-design-long-running-apps)—durable artifacts and periodic simplification/ablation of harness components.
- Apr 23, 2026: [Claude Code quality postmortem](https://www.anthropic.com/engineering/april-23-postmortem)—a single verbosity line caused a 3% regression; per-model eval, ablation, audits, soak, and gradual rollout.
- Jun 2, 2026: [Dynamic workflows](https://claude.com/blog/a-harness-for-every-task-dynamic-workflows-in-claude-code)—isolated task-specific orchestration and its cost limits.
- Jun 3, 2026: [How Anthropic uses skills](https://claude.com/blog/lessons-from-building-claude-code-how-we-use-skills)—gotcha-led skills, trigger descriptions, scripts, scoped hooks, and usage telemetry.
- Jun 18, 2026: [Steering Claude Code](https://claude.com/blog/steering-claude-code-skills-hooks-rules-subagents-and-more)—current seven-mechanism decision table.
- Jul 24, 2026: [New context-engineering rules for Claude 5](https://claude.com/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models)—latest model-generation-specific simplification guidance.
- Aug 14, 2026: [Maximizing session value](https://claude.com/blog/maximizing-the-value-of-your-claude-code-sessions)—latest direct context/cost operating guidance found.
- Aug 18, 2026: [Claude on call](https://claude.com/blog/ai-ci-cd-on-call)—current Anthropic example of standing Markdown skills, detailed bug-class references, a learned lessons file, tools, and orchestrator/executor isolation. It is a domain case study, not a recommendation to put hundreds of lines in root `CLAUDE.md`.
- Aug 20, 2026: [Claude Code guide for startups](https://claude.com/blog/claude-code-guide-for-startups)—latest Claude Code post found; it points readers back to the steering guide and emphasizes connected sources of truth, skill/plugin distribution, deterministic verification, and automation. It does not revise the `CLAUDE.md` placement guidance.

### Anthropic talks

- Mar 24, 2026: [Claude Code Advanced Patterns](https://www.anthropic.com/webinars/claude-code-advanced-patterns), Lizzie Alvarado Ford and Alon Krifcher, Applied AI at Anthropic; [slides](https://resources.anthropic.com/hubfs/Claude%20Code%20Advanced%20Patterns_%20Subagents%2C%20MCP%2C%20and%20Scaling%20to%20Real%20Codebases.pdf).
- May 7, 2026: [How we Claude Code](https://claude.com/code-with-claude/session/sf-ext-how-we-claude-code), Thariq Shihipar, Anthropic MTS. The public session description confirms a stock-versus-tuned workshop using project context, commands, hooks, and subagents; no textual transcript was available, so no finer claim in this report relies on the recording.
- May 6/19, 2026: [Running an AI-native engineering org](https://claude.com/code-with-claude/session/sf-running-an-ai-native-engineering-org), Fiona Fung, Claude Code/Cowork engineering leader. The later [written recap](https://claude.com/blog/running-an-ai-native-engineering-org) grounds the included dogfooding, verification, and process-deletion implications.

### Dated OpenAI staff sources

- Jan 22, 2026: [Shell + Skills + Compaction](https://developers.openai.com/blog/skills-shell-tips)—procedures on demand, concrete routing boundaries, and avoiding brittle megadocs.
- Jan 22, 2026: [Testing Agent Skills Systematically with Evals](https://developers.openai.com/blog/eval-skills)—outcome/process/style/efficiency checks, positive and negative trigger sets, trace capture, and `codex exec --json`.
- Feb 11, 2026: Ryan Lopopolo, [Harness engineering](https://openai.com/index/harness-engineering/)—the failed giant-`AGENTS.md` approach, roughly 100-line map, repository docs as system of record, mechanical validation, doc gardening, and executable architectural invariants.
- Mar 9, 2026: Kazuhiro Sera, [Using skills to accelerate OSS maintenance](https://developers.openai.com/blog/skills-agents-sdk)—short root routing policy, narrow skills, scripts, Actions, and an observational throughput comparison.
- Accessed Aug 21, 2026: [Custom Code Review rules for Codex](https://developers.openai.com/blog/custom-code-review-rules-for-codex)—small scoped judgment rules with safe paths; mechanical checks in CI; vendor review-eval result.

### OpenAI staff talk

- Apr 9, 2026: Ryan Lopopolo, “Harness Engineering: How to Build Software When Humans Steer,” AI Engineer Europe; [conference program](https://www.ai.engineer/europe/2026), [recording](https://www.youtube.com/watch?v=am_oeAoUhew), and [timestamped index](https://talksintel.ai/ai-ml/conferences/aie-eu-2026/harness-engineering-how-to-build-software-when-humans-steer/). The report uses only claims corroborated by the recording/index and Lopopolo's official written post.

## Bottom line for the cross-provider spec

The root should become a small cross-provider kernel, not a compressed version of the present document. Anthropic's strongest current distinction is semantic:

- universally needed, non-obvious facts stay;
- deterministic obligations execute;
- task procedures load on demand;
- path constraints load with their paths;
- verbose search happens in isolated contexts;
- detail remains authoritative and discoverable in tools, code, ADRs, and reference files;
- every migration is evaluated on the model/profile that consumes it.

The next spec should set its target in actual startup tokens and measured behavior, not only “fewer than 200 lines.” A physical-line gate alone would approve the current 10,452-word file and therefore cannot be the acceptance criterion.
