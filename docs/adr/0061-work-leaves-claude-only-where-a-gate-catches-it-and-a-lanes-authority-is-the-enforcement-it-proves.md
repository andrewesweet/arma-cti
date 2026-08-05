# Work leaves Claude only where a gate catches it, and a lane's authority is the enforcement it proves

Date: 2026-08-05
Decided-by: human, in the inaugural grilling session for the multi-provider dispatch initiative
Claimed: after `git fetch origin` (`docs/adr/` on `origin/main` topping at 0060) and a search of
every open issue finding no claim above 0060

The project is building infrastructure to dispatch logical subagents onto non-Anthropic coding
subscriptions — OpenAI Codex and the z.ai GLM Coding Plan — so that work which does not need
Claude stops consuming it. The driver is to minimise token spend while still delivering the fully
autonomous agentic development process; a wider provider set also buys task fit and price
arbitrage, since z.ai's plan discounts off-peak hours.

This ADR records the rulings that are independent of which substrate wins. The rulings that a
prior-art sweep could overturn are named as held at the end, and are not taken here.

## Decision 1: Claude spend is the only number optimised, and all three pools are metered

The three subscriptions do not share a currency. Claude meters input-equivalents against a weekly
plan limit; Codex meters credits scaling with tokens against a five-hour window and a weekly cap;
z.ai meters *prompt counts* — not tokens — against its own five-hour and weekly caps, with a
time-of-day multiplier. There is no honest single number.

So the operating rule is greedy: anything clearing its quality floor goes off Claude, and Claude
spend is the only quantity optimised. Only Claude is scarce today — the WIP limit stands at zero
on token budget — and the other two pools are bought and idle.

Telemetry nonetheless records fraction-of-cap for all three from the first dispatch. That costs
nothing now and is what allows this rule to be *replaced* by scarcity routing once a second pool
binds, rather than reopened from nothing. #220 asks the same question for a single provider; its
answer must agree with this one.

## Decision 2: work may leave Claude iff a mechanical gate catches a wrong answer

Eligibility is not a judgement made per task. It is a property of the surface: a task class is
eligible when wrongness is caught mechanically — `just fast`, the regression corpus, the repo
hooks, `cog verify`, the human sign-off gate.

Eligible: the implementer, mechanical and recon seats. Not eligible: orchestration, retros, ADRs,
`CONTEXT.md`, schema semantics and process docs — the fable seat — and the #181 shape, a
diagnosis whose plausible wrong fix would also have gone green.

CLAUDE.md already draws this line between fable and opus, on exactly this reasoning. Reusing it
means no new safety argument is needed, only a new provider.

## Decision 3: review is eligible, and provider diversity is the point

A review's output is claims, not commits. Each claim names a file, a line and a failure scenario,
all cheap to check against the code, and a false finding costs one wasted look — it cannot land
anything. The blast radius is bounded without a mechanical gate behind it.

Provider diversity is the one place where a second model is strictly better than a second Claude
run: different training, different blind spots. Two providers over one diff is **one pass with two
lenses, not two passes**, and CLAUDE.md's prohibition on verification passes beyond the gates must
be worded to say so — otherwise an agent will read the second lens as the forbidden thing.

The known asymmetry is stated rather than hidden: false positives are checkable and false
negatives are silent. That is equally true of a Claude reviewer, so the comparison is
model-against-model, not model-against-perfect.

## Decision 4: a lane's authority is the enforcement it demonstrably runs

A lane earns authority by passing a hook-parity suite — a pytest suite that fires each hook's
trigger condition on that lane and asserts the denial.

- All hooks proven: full subagent authority. Own worktree, commits, runs gates, pushes to main.
- Some hooks missing: worktree and commit only; landing is done by another seat.

This matters because the enforcement layer is not uniform. `cog verify` is a git-level
`commit-msg` hook and fires whoever commits; `just check`, `just unit` and the corpus fire whoever
runs them. But the `PreToolUse` denials — generated-file protection, acceptance-spec protection,
`--no-verify` blocking, the token-economy hooks — are per-harness configuration, and configuration
that was never tested is configuration that is probably wrong on first use.

Codex's hook system is near-identical to Claude Code's (same event names, same exit-code-2 denial
convention), and opencode's plugin API can shim to the same scripts, so parity is reachable on
both. Reachable is not proven, which is what the suite is for.

## Decision 5: `(lane, model, effort)` is one opaque arm, not three dimensions

Effort vocabularies do not commensurate. Claude Code offers five levels; GLM-5.2 has two thinking
levels plus off, so `xhigh` and `max` both land on GLM's Max and `high` and `xhigh` may be the
same configuration; Codex has four; opencode exposes a provider-specific `--variant`. Worse, the
mapping is non-monotonic across providers — GLM Max may sit above or below Opus high depending on
the task.

So the unit of guidance is a **profile**: `opus-high`, `zai-glm52-max`, `codex-gpt-high`. Guidance
maps profile to seat. Randomisation is over profiles. This is CLAUDE.md's Model roles table — which
already binds `(model, effort)` as a pair per task class — extended by one field, not a new concept.

The cost is stated plainly: no question of the form "is xhigh worth it in general" can be answered.
Only "is this profile better than that one for this seat" — which is the question the guidance
needs.

## Decision 6: the evidence is randomised assignment measured by the existing gates

No separate eval corpus and no model-as-judge. The lane is randomised within an eligible task
class, and the quality signal is what the project already produces per issue: gate cycles to first
green, red runs before green, corpus verdict class and count, review findings raised afterwards,
rework commits in the following week, wall clock, and quota consumed on each pool.

Randomisation is the load-bearing part. Without it the data is confounded — route the easy issues
to the cheap lane and the cheap lane looks brilliant. Randomising makes observational data causal
and costs nothing.

This is chosen over a benchmark because a benchmark drifts from the live repo and a task whose
answer sits in git history is a memorisation hazard; and over a judge because judge preferences are
known to favour verbosity and the judge's own model family, which is precisely the comparison being
made. Both would also be new verification passes, which CLAUDE.md forbids beyond the gates.

The weakness is stated: the signal is slow, and silent about a wrong landing that passed. A class
the free signal cannot separate escalates to paired dispatch — the same issue on two lanes, in two
worktrees, one output discarded.

## Decision 7: `quota_exhausted` joins the failure-class table

| Class | Required response |
|---|---|
| `quota_exhausted` | Not a result. Re-dispatch to another lane, or queue until the window resets. Never interpret the partial work |

It earns a row because its required response differs from every existing one. `infra_unavailable`
says stop and escalate to a human; quota exhaustion needs neither, being foreseeable and
schedulable — z.ai and Codex both reset on known five-hour and weekly boundaries, so the wait is
computed, never guessed. Routing quota to `infra_unavailable` would halt the process several times
a day for something that fixes itself, and a rule that is wrong in the common case gets ignored in
all cases.

Everything else provider-side — OAuth expiry, provider 5xx, outage, network — maps to
`infra_unavailable` unchanged.

## Decision 8: `provider_refused` joins the failure-class table

| Class | Required response |
|---|---|
| `provider_refused` | Not a result — the verdict says nothing about the code under test. Re-dispatch to another lane, record the refusal against that profile as evidence, and escalate when N consecutive refusals trip that lane's quality breaker |

This is not the #71 shape of a class nothing can emit: Claude Code already logs
`claude_code.api_refusal` with a category attribute, so the signal exists on day one. Its response
differs from every other row — `infra_unavailable` escalates, `untyped_harness_failure` sends you
to the harness, `quota_exhausted` waits — and a refusal is *evidence for the routing rule*, because
a model that refuses a class of work is unfit for it.

## Held pending the prior-art sweep

Five rulings were taken in the same session and are deliberately **not** recorded here, because
prior art may already solve them and landing them now would be the doc-first mistake this project
has made twice. Four research dispatches are reading the field; the rulings land with their first
applied instance, in a second ADR.

- **Substrate** — native per-provider CLIs against `opencode`, decided by spike. One part is not
  held and is absolute: the Anthropic subscription is reached only ever through Claude Code. The
  mirror is permitted — the `claude` binary may drive a non-Anthropic endpoint, since that consumes
  no Anthropic quota, credential or traffic — subject to one read of Anthropic's current terms
  before landing.
- **Portability** — adopting Microsoft's APM for the compile step, which would make `CLAUDE.md` a
  generated file and move its sign-off gate to the source primitive.
- **Telemetry and the ledger** — OTel as the single capture bus with a per-dispatch ledger as a
  materialised view over it.
- **Dispatch granularity** — a whole agent run assigned to one lane, against an in-session proxy
  routing per request type.
- **The lane circuit breaker** — availability and quality trips, state read before dispatch.

Two candidates already look capable of replacing the last two outright: LiteLLM's Router
implements per-deployment cooldowns, failure-threshold circuit breaking and rate-limit-aware
routing today, and `claude-code-router` already routes Claude Code traffic per request type across
providers.

## What would overturn this

- **Decision 1** — a second pool binding, at which point greedy routing becomes scarcity routing
  and the recorded fraction-of-cap telemetry is what makes the switch cheap. Also any finding from
  #220 that contradicts the metering model.
- **Decision 2** — a landing that passed every gate and was still wrong in a way a Claude agent
  would not have been. That would show gate coverage is not the safety property claimed, and the
  eligible seat list contracts.
- **Decision 3** — a measured false-negative rate materially worse on a foreign reviewer than on a
  Claude one over the same diffs. Note this needs paired data to establish; a single missed defect
  does not.
- **Decision 4** — a hook that cannot be shimmed on a lane, or a parity suite that passes while the
  enforcement it claims to prove does not actually fire. The suite asserting on its own mock rather
  than the lane's real denial path is the specific failure to watch for.
- **Decision 5** — evidence that a provider's effort levels *do* commensurate with Claude's well
  enough to route on a shared scale, which would make profiles needless ceremony.
- **Decision 6** — a finding that this project's landing rate is too low for randomised assignment
  to separate profiles in reasonable time. That is a live risk and is in the sweep's scope; if it
  holds, the regime moves to paired dispatch or an existing eval framework.
- **Decisions 7 and 8** — either class failing to fire in practice, which would make it the #71
  shape after all; or a required response proving wrong — for instance a quota reset that is not
  computable from published window boundaries, which would collapse `quota_exhausted` back into
  `infra_unavailable`.
