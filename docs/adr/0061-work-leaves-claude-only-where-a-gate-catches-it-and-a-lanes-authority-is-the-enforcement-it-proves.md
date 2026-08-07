# Work leaves Claude only where a gate catches it, and a lane's authority is the enforcement it proves

Date: 2026-08-05
Decided-by: human, in the inaugural grilling session for the multi-provider dispatch initiative
Claimed: after `git fetch origin` (`docs/adr/` on `origin/main` topping at 0060) and a search of
every open issue finding no claim above 0060
Amended: 2026-08-05, same session, before human review — Decision 6 replaced and the held section
resolved, on the prior-art sweep this ADR itself commissioned. An ADR is amendable until the human
has read it and immutable afterwards; this one reached `origin/main` by the worktree collision on
#105 rather than by review, so nothing had relied on it

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

Time-boxed exception (human ruling on #217, 2026-08-06): until `2026-08-10T14:00Z`, retros may run
as the `fable` seat on the `codex` lane at profile `codex-sol-xhigh`. This suspends Decision 2 for
that triple only; the clock reapplies the standing bar at the expiry instant without a revocation.
Every other fable-on-foreign route remains ineligible throughout, and the orchestrator seat remains
ineligible on every foreign lane.

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

## Decision 6: admission is an absolute bar against the existing history, not a comparison

No separate eval corpus and no model-as-judge. The quality signal is what the project already
produces per issue: gate cycles to first green, red runs before green, corpus verdict class and
count, review findings raised afterwards, rework commits in the following week, wall clock, and
quota consumed on each pool.

The question that gates a lane is **absolute, not comparative**. The WIP freeze is rationing rather
than policy — it exists only while Claude tokens are the scarce currency, and lifts once foreign
lanes are live and their result quality is trusted. So what must be established is whether a lane
clears the bar, not whether it beats Claude. An absolute question needs no control arm and no
randomisation.

- **Admission, per seat.** A profile is admitted when its own gate record over N issues clears a
  bar **pre-registered before that lane's numbers are seen**. The bar is derived from the Claude
  history already in the repo — free, no new spend on the scarce pool, no discarded arm.
- **Tuning.** Which cheap profile suits which seat is settled by paired dual-run with both arms on
  cheap pools, where double-spend costs nothing scarce.
- **Reserved.** A foreign lane against Claude head to head, only for a specific question judged
  worth the scarce spend.

This is chosen over a benchmark because a benchmark drifts from the live repo and a task whose
answer sits in git history is a memorisation hazard — SWE-bench's contamination is measured at 76%
buggy-file-path accuracy on Verified against 53% off-benchmark. It is chosen over a judge because
judge preferences are known to favour verbosity and the judge's own model family, which is
precisely the comparison being made. Both would also be new verification passes, which CLAUDE.md
forbids beyond the gates.

Two weaknesses, stated rather than glossed. The historical baseline is confounded by task mix and
by process changes over the period, which is why pre-registration is load-bearing: seeing the new
lane's numbers first would turn the confounding into a licence to move the bar. And the signal
remains silent about a wrong landing that passed every gate.

Recorded because it constrains everything downstream: arm count, not sample size, is the binding
constraint on what is measurable here. No published router beats a static policy at *n* in the
tens — RouteLLM needed 65,000 pairwise comparisons, RouterBench 405,000 outcomes — so the
**marginal effects of lane and of effort are not estimable on this project, ever**. Published
benchmark results have exactly one legitimate use: seeding the initial profile-to-seat table.

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

## Settled by the prior-art sweep, awaiting a first applied instance

Five rulings were taken in the same session and deliberately not recorded as decisions here,
because prior art might already have solved them and landing them unread would be the doc-first
mistake this project has made twice. Four research dispatches then read the field; their documents
are in `docs/research/`. The outcomes are below. They remain out of the numbered decisions until
each has a first applied instance, per the rule that a convention living only in a design document
is not yet a convention; a second ADR lands them with the code.

- **Substrate** — **settled, not spiked.** Anthropic's Consumer Terms §3 bars accessing the
  Services by automated or non-human means except via an API key, and §2 bars credential sharing.
  Reaching the Anthropic subscription only through Claude Code is therefore the one compliant
  configuration, not a preference. The mirror is permitted and documented — the `claude` binary may
  drive a non-Anthropic endpoint, consuming no Anthropic quota, credential or traffic, and z.ai
  publishes the variables for it. The remaining spike narrows to native CLIs against `opencode`,
  for non-Anthropic lanes only. The owed terms read widens to OpenAI's, and the standing rule it
  produced is that **no subscription credential goes into any third-party process, on any lane** —
  three separate tools offered to do exactly that.
- **Portability** — **APM failed; re-decided.** APM emits no hook target for Codex or opencode, and
  its audit does not track root compiled files, so generating `CLAUDE.md` would have bought zero
  drift enforcement. `rulesync` spans both lanes but its opencode output is inert. Neither removes
  the opencode payload bridge, which is one hand-written file we own regardless. The decision is
  `AGENTS.md` as sole source with `CLAUDE.md` reduced to an `@AGENTS.md` import and hook
  configuration hand-written per target — conditional on one drift mechanism per surface, all in
  `just check`: a form check that `CLAUDE.md` is exactly the import line; the behavioural
  hook-parity suite Decision 4 already mandates; and a static equivalence check over the seat and
  profile registry.
- **Telemetry** — **stands**, with one correction: "all lanes" requires a traces pipeline, because
  opencode emits no metrics at all and carries tokens only as spans.
- **Durability** — **stands with less to build.** The collector's `group_by` file export writes one
  record per dispatch, so filtering, splitting and durability are configuration rather than code,
  and the compaction step disappears. One constraint discovered: a dispatch identity distinguishes
  only separate processes, so an in-session subagent cannot be ledgered — which reinforces the
  dispatch-as-separate-process model.
- **Dispatch granularity** — **stands.** Per-request-type routing requires a session-global base
  URL, which forfeits the subscription; the leading proxy reaches the subscription by replaying a
  stored OAuth credential, which is the barred path. Corroborating: that proxy abandoned its own
  category router in favour of Claude Code's native model-slot variables.
- **Breaker** — **stands, halved.** The leading library was rejected as the breaker on measured
  grounds: a five-second default cooldown, a failure *ratio* rather than consecutive-N, no quality
  trip, no supported surface, and cooldown transitions that never reach OTel. But Codex publishes
  quota state first-party, including a reset time, so Decision 7's "computed, never guessed" is
  free and pre-dispatch on that lane. Only the quality half needs building. z.ai publishes no
  machine-readable equivalent.

Both candidates this section originally named as likely to replace a ruling outright were rejected,
each on a primary source read rather than a summary. The sweep's cost was four read-only dispatches;
it prevented two builds on false premises and one on a tool that does not do what it claims.

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
- **Decision 6** — a lane that clears the pre-registered admission bar and then produces work that
  is wrong in ways the gates do not see. That would show the bar measures gate compliance rather
  than quality, and admission would need a signal the gates do not supply. Also: any evidence that
  the historical baseline's task mix differs from the new work enough to make the comparison
  meaningless, which would force a live control arm despite its cost.
- **Decisions 7 and 8** — either class failing to fire in practice, which would make it the #71
  shape after all; or a required response proving wrong — for instance a quota reset that is not
  computable from published window boundaries, which would collapse `quota_exhausted` back into
  `infra_unavailable`.
