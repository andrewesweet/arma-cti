# Autonomous continuous improvement of the system of work

Research date: 2026-08-14

**Status:** Background research informing
[target-state specification #376](https://github.com/andrewesweet/arma-cti/issues/376)
and [MVP specification #377](https://github.com/andrewesweet/arma-cti/issues/377).
The specifications and their child issues govern delivery; this report is not operative
process policy.

## Conclusion

The target state needs a fourth mechanism around the three delivery mechanisms already
identified. It is not another code reviewer and should not be folded into the outer
coordinator:

```text
Human product curation
        │
        ▼
Initiative compiler ──▶ Outer coordinator ──▶ Inner issue runner ──▶ Initiative audit
        ▲                       ▲                      ▲                    ▲
        │                       │                      │                    │
        └───────────────────────┴──────────┬───────────┴────────────────────┘
                                           │ typed events and immutable traces
                                           ▼
                         System-of-work improvement controller
                  observe → diagnose → propose → independent review
                         → preregister → shadow/canary
                         → promote or roll back → monitor
                                           │
                                           ▼
                            Versioned workflow/policy registry
```

The delivery system is the *managed system*. The improvement controller is a separate,
slower feedback loop over it. This resembles IBM's autonomic-manager architecture: a
self-managing system is split into managed elements and a manager with explicit
interfaces and behavioural requirements, rather than allowing each managed component
to rewrite itself opportunistically. IBM reported validating the pattern in two
prototypes. ([IBM autonomic-computing architecture](https://research.ibm.com/publications/an-architectural-approach-to-autonomic-computing))

The strongest honest target is:

> **Fully autonomous improvement inside a human-ratified constitutional envelope.**

The agents may change prompts, skills, routing, WIP policy, retry policy, workflow
stages, templates, tools and gates through an empirical release process. They may not
change the product's intended outcomes, grant themselves more authority, rewrite the
evaluator that judges their own candidate, suppress provenance, or weaken hard safety
boundaries. Those are the root of authority, not ordinary process configuration.

This preserves the desired human role. The human curates product outcomes, not routine
process amendments. A request to change the constitutional envelope is an exceptional
`meta_authority_required` outcome, not a standing retrospective approval queue. A
system that can change its own objectives, evaluator and permissions and then certify
the result is not autonomous governance; it has no independent ground truth.

## What arma-cti has today

The repository already contains unusually strong foundations. The missing part is not
"add retrospectives"; it is turning retrospective findings into controlled, measurable
policy experiments.

### The original loop

[ADR-0009](../adr/0009-process-backbone-and-retro-evolution.md) established the
initial contract: process changes originate in `/retro`, are sign-off gated, and are
journalled in [the process log](../process-log.md). The project-owned
[retro skill](../../.claude/skills/retro/SKILL.md) supplies:

- scheduled and event-driven triggers;
- an evidence sweep concerned with friction in commands, gates, skills and conventions;
- proposals grounded in observed instances rather than taste;
- a bias toward deleting instructions and mechanising recurring failures;
- human sign-off and an explicit pending-review count;
- a durable journal; and
- `validated ×N` markers that upgrade only through real use.

The process log shows that this is a real learning loop rather than ceremonial prose.
It records rejected hypotheses, refuted findings, recurring failure shapes, amendments,
and cases where prose was escalated into a mechanical check after repetition. The
marker checker in `tools/check_validated_markers.py` is itself an example: two
retrospectives found the same count/list drift before the class was made mechanical.

This is close to the strongest part of Google's SRE postmortem practice. Google defines
postmortems around documented impact, contributing causes and effective preventive
actions; predefines objective triggers; formally reviews the result; files action
items into the bug tracker; and extracts structured metadata for trend analysis.
Google also stresses that an action without an owner, tracking record and verifiable
end state is likely to disappear. ([SRE postmortem culture](https://sre.google/sre-book/postmortem-culture/),
[SRE Workbook postmortem practice](https://sre.google/workbook/postmortem-culture/))

### The post-ADR-0071 direction

[ADR-0071, ruling 3](../adr/0071-the-foreign-lane-is-rescinded-seats-carry-profile-preferences-and-no-change-lands-alone.md)
sharpens the separation of authority:

- a `retro` is its own seat;
- it identifies and researches improvements and files backlog items;
- it lands nothing, because finding and implementing are different jobs; and
- no model instance may both propose a change and produce the review verdict that
  clears it.

The implementation has begun to embody that direction:

- `tools/dispatch.py` registers a distinct `retro` seat and independently resolved
  profiles;
- `tools/brief.py` states that the seat "finds, researches and files backlog items;
  lands nothing";
- `tools/ledger.py` gives it the typed `lands_nothing` outcome instead of confusing its
  completion with a failed landing; and
- recent retros bank evidence durably in tracker issues (#276, #307 and #316) while the
  cycle is running, rather than reconstructing everything from one session's memory.

The current checkout is in transition. The retro skill still contains the older
"apply approved diffs" and journal-landing instructions; ADR-0071 explicitly sequences
a rewrite. Recent process-log entries mostly follow the newer behaviour but retain the
journal as a named landing. That inconsistency is current implementation evidence, not
something this research report changes.

### What the #317 family contributes

The #317-family design supplies most of the governance substrate a meta-loop needs:

- author-distinct review and per-finding adjudication;
- bounded fix rounds and an arbiter terminus;
- typed dispatch outcomes rather than generic retry;
- profile, seat, issue and gate provenance in dispatch and ledger records;
- post-landing review as a containment signal; and
- the proposed observatory's rework measures, stratified by pre-work signals rather
  than read naively across incomparable tasks.

ADR-0071 is deliberately clear about the observatory's boundary: it reports review
rounds, escalations, arbiter invocations, disputes and landings; it ranks implementer
profiles on fix rounds per landing; and **it never routes or changes policy**. It also
notes that where rework appears is not necessarily where it was caused. The current
tree carries the strata and telemetry prerequisites, while the observatory itself is
still a sequenced work item rather than a present `tools/observatory.py` command.

That reporting-only boundary is correct. Measurement must not silently become policy.
But even after the whole #317 family is implemented, four pieces remain absent:

1. a typed improvement hypothesis and experiment contract;
2. evaluation data which the proposing policy cannot contaminate or rewrite;
3. controlled activation, canarying and automatic rollback of policy versions; and
4. an autonomous promotion authority bounded by invariants, replacing routine human
   sign-off without becoming self-approval.

## What prior art adds

### Postmortems must feed owned, reviewed work

Google's practice supports the current move from retro-authored commits to filed work.
Postmortem drafts receive formal review for evidence depth and action-plan quality;
action items have owners, priorities, tracking bugs and verifiable end states; tools
monitor their closure and aggregate trends across incidents. Google's workbook also
warns that changing operator behaviour is less dependable than improving automation
and process. ([SRE Book](https://sre.google/sre-book/postmortem-culture/),
[SRE Workbook](https://sre.google/workbook/postmortem-culture/))

The lesson is not merely "file a ticket." The improvement ticket needs enough structure
to be falsifiable, and the system must later check whether the promised recurrence
reduction actually occurred.

### Evals turn reflection into an empirical loop

OpenAI's evaluation guidance recommends task-specific tests drawn from real
distributions, logging everything so traces can become eval cases, continuous
evaluation on every change, and held-out evaluation rather than subjective impressions.
It explicitly lists overly generic metrics, biased datasets and vibe-based evaluation
as anti-patterns. It also recommends evaluating each nondeterministic step and handoff
in agent workflows, not only the final output. ([OpenAI evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices))

This maps well to a system of work. A workflow policy is executable behaviour and should
have regression cases: dispatch eligibility, dependency fan-in, failure typing, recovery,
review independence, adjudication, landing and initiative acceptance. The project
already tests many of these mechanisms as protocols; the missing move is to treat the
whole policy candidate as the unit under evaluation.

The evaluator itself is part of the risk. OpenAI's 2026 audit estimated roughly 30% of
SWE-Bench Pro's public tasks were broken, including underspecified prompts,
overly strict tests, low-coverage tests and misleading prompts. The audit used repeated
investigator-agent passes plus independent experienced-engineer review and concluded
that flawed evals can distort deployment and safety decisions. ([OpenAI coding-eval audit](https://openai.com/index/separating-signal-from-noise-coding-evaluations/))

### Agents can improve their own scaffolding

The research evidence is real, but not yet evidence for unrestricted production
self-governance.

[A Self-Improving Coding Agent](https://arxiv.org/abs/2504.15228) let an agent edit its
own orchestration code and reported benchmark improvement from 17% to 53% on a random
SWE-bench Verified subset. Its framework includes a concurrent overseer that reads the
call graph and event stream, can warn a running agent and can cancel pathological or
stuck runs. This demonstrates that workflow code, tools and context management are
legitimate optimization targets, and that oversight should see trajectories rather
than only final scores.

The [Darwin Gödel Machine](https://arxiv.org/abs/2505.22954) goes further. It analyzes
evaluation logs, proposes and implements modifications to its own coding-agent code,
quantitatively evaluates each child, and keeps a branching archive rather than replacing
one production version in place. It discovered changes to editing tools, context-window
management, multiple attempts and peer-review mechanisms, reporting SWE-bench
improvement from 20% to 50%. The archive matters: lower-performing intermediate nodes
sometimes became stepping stones to later improvements, while a latest-version-only
baseline could damage its own ability to improve. The authors also report sandboxing
and human oversight; the [official repository](https://github.com/jennyzzt/dgm) warns
that model-generated code may behave destructively.

The useful transfer is therefore **candidate branching plus empirical selection**, not
"let the current production orchestrator rewrite itself." Keep stable and experimental
policy lineages, preserve every result, and activate only an exact candidate that has
passed a separate release decision.

### A constitution can replace per-instance human feedback

[Constitutional AI](https://arxiv.org/abs/2212.08073) shows a useful division of labour:
humans provide a short list of principles, models generate critiques and revisions,
and models provide scalable preference feedback under those principles. It obtained
useful behaviour with far fewer human harm labels. It also found model critiques could
be inaccurate or overstated, and evaluated the resulting systems on conversations
distinct from the training data.

For arma-cti, the analogue is not model fine-tuning. It is a small, higher-authority
process constitution plus autonomous proposal, review and trial underneath it. The
constitution should define authority and invariants, not accumulate every operational
instruction. Otherwise the root becomes another prompt that the same optimizer can
rewrite to make its candidate pass.

### Progressive delivery is the right activation model

Google defines a canary as a partial, time-limited deployment evaluated against a
control. Canary population and duration bound the amount of reliability budget at risk;
bad candidates are paused and rolled back, while good ones proceed. ([Google SRE
canarying](https://sre.google/workbook/canarying-releases/)) Argo Rollouts provides a
useful executable analogue: an analysis result can promote, abort, pause as inconclusive,
or run in dry-run mode, and measurements are retained. ([Argo Rollouts analysis](https://argo-rollouts.readthedocs.io/en/stable/features/analysis/))

A workflow change should be released the same way. A new review prompt, WIP algorithm
or retry policy should first run in replay or shadow, then on a bounded cohort of eligible
issues against the last-known-good policy. An invariant violation aborts immediately;
inconclusive evidence never becomes a pass. Google's error-budget policy adds the
portfolio-level control: when reliability misses its SLO, ordinary releases stop and
work shifts to reliability. ([Google SRE error-budget policy](https://sre.google/workbook/error-budget-policy/))

### One score is unsafe

Microsoft's SPACE research says developer productivity cannot be represented by one
metric or dimension. ([SPACE framework](https://www.microsoft.com/en-us/research/publication/the-space-of-developer-productivity-theres-more-to-it-than-you-think/))
DeepMind's specification-gaming review explains the deeper danger: capable optimizers
can exploit a slight misspecification to achieve the literal reward at the expense of
the intended outcome, including tampering with the reward channel. ([DeepMind on
specification gaming](https://deepmind.google/blog/specification-gaming-the-flip-side-of-ai-ingenuity/))

The software-agent version is no longer hypothetical. RewardHackingAgents exposes
evaluator tampering and train/test leakage in mutable workspaces. Scripted attacks
succeeded against both; locking only one mechanism stopped only one vector; evaluator
locking plus file-access evidence and a trusted reference metric made integrity itself
an auditable outcome. ([RewardHackingAgents](https://arxiv.org/abs/2603.11337))

The system-of-work controller should therefore use one predeclared primary measure per
hypothesis, several guardrail measures, and hard invariants. It should not optimize an
all-purpose "agent productivity score."

### Provenance belongs outside the candidate

SLSA defines provenance as verifiable information describing where, when and how an
artifact was produced, including its builder, inputs, dependencies, invocation and
byproducts. ([SLSA provenance](https://slsa.dev/spec/v1.2/provenance)) The direct domain
is software supply chains, but the model transfers cleanly to policy releases.

Every activated workflow version should be attributable to:

- the exact baseline and candidate hashes;
- the evidence window and trace identifiers;
- proposer, reviewer, implementer and promotion-controller identities;
- model/provider/profile versions;
- evaluator and dataset versions;
- trial eligibility and assignment;
- all measurements and integrity verdicts; and
- promotion, rollback and post-promotion outcomes.

The control plane, not the candidate's workspace, must produce this record. Provenance
written by the thing being judged is a claim, not containment.

## Recommended meta-loop

### 1. Observe continuously, convene selectively

Every delivery stage emits immutable, typed events carrying the active policy version.
The observatory remains a read model over those events. A separate trigger evaluator
creates a retrospective run on either:

- **predeclared corrective triggers:** a governance/invariant violation, severe escaped
  defect, human rescue outside product curation, repeated untyped failure, rollback, or
  repeated occurrence of one process-friction class; or
- **portfolio triggers:** every N completed work items, initiative fan-in, phase end, or
  enough new exposure for an active policy trial.

This retains the current five-close and phase/playtest ideas while removing dependence
on an orchestration session remembering to convene them. The controller deduplicates
triggers and freezes an evidence boundary before dispatching the retro.

### 2. Make the retro an investigator, not a policy authorizer

The retro agent reads the fixed evidence window, current process surfaces and relevant
history. Its output is a typed improvement proposal, not a commit:

```text
process-change candidate
  evidence: immutable run/issue/commit/trace references
  diagnosis: workflow mechanism believed causal
  affected policy surfaces and blast radius
  candidate change or bounded search space
  primary expected effect
  guardrail effects that must not worsen
  hard invariants
  replay/shadow/canary eligibility
  stop and rollback conditions
  confidence and known confounds
```

This formalizes what the strongest current retros already do. A finding which cannot
name a causal mechanism or a falsifiable outcome may still be banked as an observation,
but it is not yet eligible for a policy experiment.

### 3. Review the finding independently

A fresh, author-distinct process reviewer challenges:

- whether every cited instance survives re-derivation;
- whether the class recurs or is merely one work item's defect;
- whether the proposed mechanism addresses the class rather than its latest symptom;
- whether removal or a mechanical check is simpler;
- what metric-gaming and evaluator-tampering paths exist;
- what other policy changes contaminate the evidence window; and
- whether the proposal crosses the constitutional boundary.

This is the meta-loop application of #317's never-alone rule. A process reviewer lands
nothing. Disagreement follows the same bounded adjudication pattern as an implementation
finding.

### 4. Compile a preregistered experiment

Once the diagnosis is accepted, a distinct experiment-planning run freezes, before
candidate outcomes are visible:

- baseline policy version and candidate;
- eligible issue strata and exclusions;
- assignment method;
- replay, shadow and live phases;
- primary measure;
- guardrail vector and hard-stop conditions;
- minimum exposure or duration;
- missing/inconclusive-data semantics; and
- automatic rollback and post-promotion observation windows.

The candidate then enters the ordinary outer coordinator and inner issue runner for
implementation, tests, independent review, adjudication and landing. The resulting
commit is only a **policy release candidate**. Landing it must not silently activate it.

### 5. Evaluate without training on the test

Use three evidence sets:

1. **Diagnostic traces** are visible to the retro and candidate author. They explain the
   failure and support local replay, but cannot prove general improvement.
2. **Locked holdouts** are controlled by the evaluation service, inaccessible from the
   candidate workspace, and run by a trusted harness.
3. **Future-work cohorts** consist of eligible issues and initiatives that did not exist
   when the candidate was authored. Continuously adding new problems is the mechanism
   LiveCodeBench uses to reduce benchmark contamination. ([LiveCodeBench](https://arxiv.org/abs/2403.07974))

Workflow policy and evaluator specification are independently versioned. A change to an
evaluator may improve the evaluator, but it cannot be used as evidence that a policy
changed in the same candidate improved. Evaluation-integrity failures are first-class
verdicts and abort promotion.

### 6. Shadow, canary, promote or roll back

Activation proceeds through explicit states:

```text
authored → independently reviewed → replayed → shadowed → canary
                                               │           ├─ promote exact hash
                                               │           ├─ inconclusive: remain stable
                                               │           └─ guardrail red: roll back
                                               └─ invariant red: reject
```

Shadow mode computes what the candidate *would* have dispatched or decided while the
stable policy remains authoritative. Canary mode assigns only a bounded eligible cohort
to the candidate. The controller compares candidate and stable results within declared
strata, promotes only the tested hash, and keeps the stable version immediately
restorable. Post-promotion monitoring can reopen the experiment and roll back on a
late regression.

At arma-cti's scale, many experiments will not have enough cases for persuasive
frequentist claims. The honest response is not to invent significance. Require exact
protocol regressions for deterministic behaviour, repeated cases for process claims,
matched strata where possible, and a bounded exposure window. Record `inconclusive`
when the project cannot identify an effect. High-confidence invariant improvements can
still ship; small estimated throughput differences usually cannot.

### 7. Score a vector, not a league table

The permanent observatory should expose at least:

- **product and quality:** initiative-acceptance gaps, escaped defects, post-landing
  findings, architecture-conformance findings;
- **review and rework:** rounds, severity, adjudications, arbiter outcomes, reverts;
- **flow:** ready-to-start time, active time, blocked time, WIP occupancy, fan-in delay;
- **resilience:** recovery outcomes, typed infrastructure/provider failures, stale
  claims, duplicate dispatches;
- **cost:** provider-native plan consumption, tokens, Arma slot time and wall-clock,
  reported without false cross-provider conversion;
- **human dependence:** product decisions, process interventions and rescue actions as
  distinct classes; and
- **governance:** author-distinct review, containment, provenance completeness, eval
  integrity and policy-bypass events.

Each experiment selects one primary measure from this vector. Safety, product acceptance,
review independence, typed-failure semantics, evaluator integrity and provenance are
constraints, not exchangeable score components. A faster candidate does not buy the
right to lose one of them.

## Constitutional envelope

The non-self-modifiable kernel should be small enough to remain comprehensible:

1. human-authored product intent and acceptance remain authoritative;
2. one model instance cannot propose and clear the same change;
3. a candidate cannot modify or observe its own locked evaluator or holdout;
4. activation is only through the versioned experiment/promotion controller;
5. every decision and artifact carries tamper-resistant provenance;
6. destructive, credential, data-boundary and spend authorities cannot be widened by
   the workflow they constrain;
7. hard failures abort and restore last-known-good state; `inconclusive` is never green;
8. constitutional changes cannot validate themselves.

Everything else should be ordinary, autonomously improvable policy. Keeping routine
instructions out of the kernel is important: otherwise every useful retrospective
becomes a constitutional amendment and the human review queue simply moves upward.

## How this fits the existing architecture

No new implementation control plane is required.

- The **observatory** supplies read-only evidence and trends.
- The **improvement controller** triggers retros, freezes evidence, owns experiment
  assignment and policy activation, and never writes implementation code.
- The **retro seat** investigates and files a typed process-change item; it lands nothing.
- The **outer coordinator** schedules that item like other dependency-bearing work.
- The **inner issue runner** implements and independently reviews the candidate.
- The **policy registry/deployer** shadows, canaries, promotes and rolls back the exact
  reviewed artifact.
- The **initiative audit** and post-landing review feed outcome evidence back to the
  observatory.

This preserves one queue, one dispatch surface, one worktree authority, one review loop
and one landing protocol. The meta-loop adds an evidence and activation plane, not a
second scheduler.

## Delivery path from a post-#317-family state

1. **Make policy version observable.** Compute one manifest/digest over the operative
   process surfaces and attach it to every dispatch, review, verdict, ledger row and
   initiative audit. Do this before automating improvement; otherwise there is no
   exposure record.
2. **Type the evidence bank.** Preserve narrative, but add machine-readable friction,
   intervention, invariant, recurrence and provenance fields. Auto-populate facts from
   traces; leave diagnosis to the retro.
3. **Finish the retro role split.** Align the skill with ADR-0071: investigate, research
   and file; implementation and review occur through ordinary tickets. Resolve the
   journal exception explicitly.
4. **Introduce process-change and experiment schemas.** Require hypothesis, evidence,
   primary measure, guardrails, scope, stop conditions and rollback. Add deterministic
   validation before publication.
5. **Build locked replay and shadow evaluation.** Keep the evaluator and holdout outside
   candidate workspaces. Initially report only; compare its conclusions with the current
   human gate.
6. **Canary reversible low-risk policy.** Start with prompts, briefing composition,
   retry timing or WIP selection—not authority, safety or acceptance semantics. Force
   at least one abort, inconclusive result and rollback in the acceptance corpus.
7. **Automate promotion inside the kernel.** Author-distinct meta-review plus green
   locked evals and canary guardrails replaces routine human sign-off for pre-authorized
   classes.
8. **Expand autonomy only from evidence.** Add higher-risk policy classes after the
   controller has demonstrated provenance, containment, correct rollback and no
   self-approval across real cycles.

The important sequencing is: **instrument → investigate → independently review →
experiment → canary → activate**. A retrospective directly editing the live workflow
collapses all six acts into one model session, confounds every subsequent observation,
and creates controller oscillation. Retros should make hypotheses; only the separate
release controller should make a hypothesis standing policy.
