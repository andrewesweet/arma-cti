# Symphony and issue #317: complementary layers of an autonomous system of work

Date: 2026-08-14

Source snapshot: OpenAI Symphony at commit
[`8001b52`](https://github.com/openai/symphony/tree/8001b52e3062495a16e520e4ceaf8f9de868c4d0),
and arma-cti at commit
[`bbb6ade`](https://github.com/andrewesweet/arma-cti/tree/bbb6adebe4682b5612c88305645c6a199bcdce46).
This note uses only first-party repository documentation, source, and issue records.

**Status:** Background research informing
[target-state specification #376](https://github.com/andrewesweet/arma-cti/issues/376)
and [MVP specification #377](https://github.com/andrewesweet/arma-cti/issues/377).
The specifications, not this comparison, govern current delivery.

## Answer in one line

Symphony and [#317](https://github.com/andrewesweet/arma-cti/issues/317) share the goal of
letting a human manage work rather than supervise individual agent turns, but they solve different
layers of that problem: **Symphony is the outer, long-running issue scheduler and worker runtime;
#317 is the inner allocation, independent-review, escalation, and quality-observation constitution.**
They are more complementary than competing.

The clean combined shape is:

```text
tracker / queue
    -> Symphony-like coordinator: claim, schedule, isolate, reconcile, resume, observe runtime
        -> #317 work protocol: plan, select seat/profile, implement, independently review,
           adjudicate, land, observe rework
```

This distinction matters because copying Symphony wholesale would discard several controls that
#317 exists to add, while treating #317 as a scheduler would leave polling, claims, concurrency,
continuation, and active-run reconciliation to an orchestrator's memory and attention.

## What Symphony is

Symphony's normative specification defines a long-running service that polls an issue tracker,
creates one isolated workspace per issue, and runs a coding-agent session there. Its four named
problems are repeatable daemon execution, workspace isolation, versioned in-repository workflow
policy, and operational visibility over concurrent runs. It explicitly calls itself a
**scheduler/runner and tracker reader**, not the owner of ticket business logic; a successful run
may stop at a workflow-defined handoff such as `Human Review` rather than at `Done`.
([spec](https://github.com/openai/symphony/blob/8001b52e3062495a16e520e4ceaf8f9de868c4d0/SPEC.md#L16-L44))

Its architecture is deliberately layered:

- a repository-owned `WORKFLOW.md` supplies typed YAML configuration and the per-issue prompt;
- an adapter normalizes one tracker into a small read interface;
- one orchestrator owns claims, concurrency, retries, and reconciliation;
- a workspace manager and agent runner isolate and execute each issue;
- structured logs and optional status surfaces expose operations.

Those layers and their boundaries are explicit in the specification.
([components and layers](https://github.com/openai/symphony/blob/8001b52e3062495a16e520e4ceaf8f9de868c4d0/SPEC.md#L71-L150))

The core state machine is operational, not a software-delivery judgement model. It distinguishes
unclaimed, claimed, running, retry-queued, and released issues; serializes mutations through one
authority; and reconciles tracker state before every dispatch. A normal turn can continue in the
same live Codex thread and workspace, while an abnormal exit receives exponential backoff.
([state machine](https://github.com/openai/symphony/blob/8001b52e3062495a16e520e4ceaf8f9de868c4d0/SPEC.md#L635-L731),
[scheduling and retry](https://github.com/openai/symphony/blob/8001b52e3062495a16e520e4ceaf8f9de868c4d0/SPEC.md#L735-L839))

The bundled Elixir workflow is a strong example policy, not the Symphony kernel. It tells one
Codex profile to reproduce first, maintain a single tracker workpad, validate, sweep all PR
feedback, and stop at `Human Review`; only a human's move to `Merging` starts the landing flow.
([workflow posture](https://github.com/openai/symphony/blob/8001b52e3062495a16e520e4ceaf8f9de868c4d0/elixir/WORKFLOW.md#L67-L116),
[review and merge states](https://github.com/openai/symphony/blob/8001b52e3062495a16e520e4ceaf8f9de868c4d0/elixir/WORKFLOW.md#L230-L273))
The core spec deliberately does not prescribe this business logic.
([non-goals](https://github.com/openai/symphony/blob/8001b52e3062495a16e520e4ceaf8f9de868c4d0/SPEC.md#L60-L69))

## What #317 is

Issue #317 and ADR-0071 redesign how arma-cti assigns and judges agent work after 112 recorded
multi-provider dispatches. The design replaces provenance-based eligibility with **seats carrying
ordered profile preferences**, keeps profiles as opaque `(lane, model, effort)` tokens, and scopes a
refusal to a `(profile, seat)` pair. The result chooses a worker for the kind of work, with explicit
fallback and escalation, rather than treating provider provenance as a quality proxy.
([#317](https://github.com/andrewesweet/arma-cti/issues/317),
[ADR-0071 seat map and resolution](https://github.com/andrewesweet/arma-cti/blob/bbb6adebe4682b5612c88305645c6a199bcdce46/docs/adr/0071-the-foreign-lane-is-rescinded-seats-carry-profile-preferences-and-no-change-lands-alone.md#L120-L162))

Its central quality invariant is “no change lands alone”: proposer, reviewer, and lander are
separate roles; the proposer may land, but the verdict must come from another instance. The
mechanical floor is a completed review dispatch record bound to the exact SHA, excluding potential
authors, with every finding above Low adjudicated. The ADR is explicit that same-user evidence can
still be forged, so this is a convention with enforcement against mistakes and shortcuts, not a
hostile-worker identity guarantee.
([ADR-0071 review invariant](https://github.com/andrewesweet/arma-cti/blob/bbb6adebe4682b5612c88305645c6a199bcdce46/docs/adr/0071-the-foreign-lane-is-rescinded-seats-carry-profile-preferences-and-no-change-lands-alone.md#L269-L321))

The review loop is also a termination protocol. A different profile reviews the exact commit;
findings are handled per item; after three fix-and-re-review rounds, an arbiter rules and the
pre-declared default lands the change while filing every non-dismissed finding and preserving
dismissals for post-landing review.
([ADR-0071 review loop and terminus](https://github.com/andrewesweet/arma-cti/blob/bbb6adebe4682b5612c88305645c6a199bcdce46/docs/adr/0071-the-foreign-lane-is-rescinded-seats-carry-profile-preferences-and-no-change-lands-alone.md#L323-L400))

Finally, #317 moves profile judgement from an ex-ante admission bar to an observatory. It ranks
implementer profiles only on fix rounds per landing; reports other counts and per-lane spend beside
that key; stratifies only on signals known before work; and **reports without routing**. The ADR
also states the attribution, confounding, and missing-counterfactual limits rather than pretending
the metric measures defects prevented.
([ADR-0071 observatory](https://github.com/andrewesweet/arma-cti/blob/bbb6adebe4682b5612c88305645c6a199bcdce46/docs/adr/0071-the-foreign-lane-is-rescinded-seats-carry-profile-preferences-and-no-change-lands-alone.md#L456-L545))

This is still a target design, not one atomic feature. As of the source snapshot, seat resolution,
review-profile exclusion, generated seat surfaces, pre-work strata, and escalation emissions have
landed, while the review loop, SHA-bound verdict, landing refusal, and observatory remain open child
issues.
([#321](https://github.com/andrewesweet/arma-cti/issues/321),
[#322](https://github.com/andrewesweet/arma-cti/issues/322),
[#323](https://github.com/andrewesweet/arma-cti/issues/323),
[#324](https://github.com/andrewesweet/arma-cti/issues/324),
[#325](https://github.com/andrewesweet/arma-cti/issues/325),
[#331](https://github.com/andrewesweet/arma-cti/issues/331),
[#332](https://github.com/andrewesweet/arma-cti/issues/332),
[#334](https://github.com/andrewesweet/arma-cti/issues/334),
[#336](https://github.com/andrewesweet/arma-cti/issues/336))

## Comparison

| Axis | Symphony | #317 |
|---|---|---|
| Immediate problem | Keep issues moving through unattended, isolated agent runs | Allocate work across profiles and prevent one instance from clearing its own work |
| Unit of coordination | One tracker issue and its persistent workspace | One dispatch/role, one reviewable SHA, and the findings attached to it |
| Primary control loop | Poll, claim, dispatch, reconcile, continue, retry, release | Plan, resolve seat/profile, implement, review, fix, arbitrate, land |
| Policy surface | Typed `WORKFLOW.md` front matter plus prompt | Seat registry, routing/escalation data, review records, landing refusal, and binding ADRs |
| Worker choice | One configured Codex command/profile for a run | Ordered multi-provider profile preferences per seat, plus explicit escalation |
| Concurrency | Global and per-tracker-state limits owned by one orchestrator | Queue freeze/WIP/routing policy plus per-dispatch lane availability and breakers |
| Isolation | Deterministic per-issue directory; VCS population is implementation-defined | Detached worktree per dispatched branch with typed creation, checking, archive, and landing protocols |
| Quality gate | Core is neutral; bundled workflow uses tests, PR feedback, and human approval | Independent pre-landing verdict, exact-SHA binding, adjudication, and post-landing review |
| Failure response | Most worker failures become exponential-backoff retries | Failure classes prescribe different actions; several red/refusal classes are explicitly not results |
| Runtime observation | Running/retrying sessions, turns, tokens, rate limits, duration, logs | Dispatch ledger plus planned rework rounds, escalations, disputes, landings, and containment evidence |
| Durability | Tracker plus workspace recover useful operation; retry/running state is in memory | Dispatch evidence and ledger are durable outside worktrees; review lineage is intended to gate landing |
| Human role | Core permits any posture; bundled workflow requires human approval before `Merging` | The autonomous loop terminates without waiting on a human; humans change policy later through rulings/retros |
| Trust claim | Preview for trusted environments; sandbox and approvals are deployment-defined | Project-specific gates and containment, with same-user forgery and coverage gaps stated explicitly |

The table's Symphony claims follow its defined scheduler boundary, state machine, workspace model,
and trust posture.
([scheduler boundary](https://github.com/openai/symphony/blob/8001b52e3062495a16e520e4ceaf8f9de868c4d0/SPEC.md#L36-L44),
[workspace safety](https://github.com/openai/symphony/blob/8001b52e3062495a16e520e4ceaf8f9de868c4d0/SPEC.md#L851-L948),
[trust posture](https://github.com/openai/symphony/blob/8001b52e3062495a16e520e4ceaf8f9de868c4d0/SPEC.md#L1719-L1797))
The #317 claims follow its seat, review, escalation, and observatory rulings.
([#317 implementation decisions](https://github.com/andrewesweet/arma-cti/issues/317),
[ADR-0071 escalation conditions](https://github.com/andrewesweet/arma-cti/blob/bbb6adebe4682b5612c88305645c6a199bcdce46/docs/adr/0071-the-foreign-lane-is-rescinded-seats-carry-profile-preferences-and-no-change-lands-alone.md#L416-L454))

## Do they serve similar goals?

Yes, at the mission level. Symphony says its purpose is to turn project work into isolated,
autonomous runs so teams manage work rather than supervise Codex, and assumes a repository already
made suitable for agents.
([README](https://github.com/openai/symphony/blob/8001b52e3062495a16e520e4ceaf8f9de868c4d0/README.md#L1-L19))
Arma-cti's declared mode is also autonomous development with maximal automated testing, and #317
tries to make allocation routine while putting a second judgement between one model's blind spot
and a landing.
([#317 problem and solution](https://github.com/andrewesweet/arma-cti/issues/317))

No, at the mechanism level. Symphony answers **“which eligible issue runs where, and how does it
keep running?”** #317 answers **“which kind of instance should do each role, who may judge it, how
does disagreement terminate, and what evidence should change future allocation?”** Symphony's core
can host a weak or strong delivery policy because it intentionally leaves PR and ticket business
logic to the prompt. #317 is that missing governance, specialized to this project's multi-provider,
gate-heavy environment.

Symphony therefore does not supersede `just dispatch`, `just worktree`, `just land`, the failure
class table, or the #317 review loop. A Symphony-like service could call those interfaces and keep
their policy; replacing them with generic workspace hooks and generic retry would be a regression.

## What arma-cti can learn from Symphony

### 1. Add an outer coordinator, not a second inner workflow

The most valuable import is Symphony's single-authority loop: reconcile active work, validate,
select eligible issues, claim before launch, dispatch to capacity, and release or retry from typed
outcomes. This would turn the current standing orchestration practice into a service that can run
between human conversations. Symphony makes duplicate prevention and cancellation consequences of
state, not instructions an agent must remember.
([claim and reconciliation rules](https://github.com/openai/symphony/blob/8001b52e3062495a16e520e4ceaf8f9de868c4d0/SPEC.md#L725-L839))

For arma-cti, the coordinator should be thin. It should call the existing `just queue`, `just
worktree`, `just dispatch`, `just watch-report`, `just ledger-sync`, review-loop, and `just land`
interfaces. It should not duplicate their rule tables in a new prompt. That preserves #317's choice
that conditions and allocation reach agents through mechanisms and generated surfaces rather than
ever-growing resident prose.
([ADR-0071 mechanism-over-prose ruling](https://github.com/andrewesweet/arma-cti/blob/bbb6adebe4682b5612c88305645c6a199bcdce46/docs/adr/0071-the-foreign-lane-is-rescinded-seats-carry-profile-preferences-and-no-change-lands-alone.md#L585-L639))

### 2. Make tracker state drive reconciliation, not merely selection

Symphony continuously refreshes running issues and stops work that becomes terminal, inactive, or
unroutable; it also distinguishes terminal cleanup from a non-active pause.
([active-run reconciliation](https://github.com/openai/symphony/blob/8001b52e3062495a16e520e4ceaf8f9de868c4d0/SPEC.md#L819-L847))
The transferable idea is not Symphony's particular `Todo`/`Human Review` labels. It is that a human
ruling, freeze, issue close, label removal, or dependency change should be reflected into live runs
by one reconciliation loop. Arma-cti's richer queue policy remains authoritative; tracker state is
an input to it, not a replacement for it.

### 3. Separate operational telemetry from quality telemetry

Symphony's runtime events and status snapshot answer “what is running, retrying, stalled, consuming
tokens, or rate-limited now?”
([events](https://github.com/openai/symphony/blob/8001b52e3062495a16e520e4ceaf8f9de868c4d0/SPEC.md#L1039-L1063),
[runtime snapshot](https://github.com/openai/symphony/blob/8001b52e3062495a16e520e4ceaf8f9de868c4d0/SPEC.md#L1390-L1448))
#317's observatory answers “where did review rework appear over completed landings?” These are
orthogonal views and should remain so. A useful live surface would expose issue, seat, resolved
profile, workspace/worktree, turn count, last event, retry due time, breaker state, and current
review round, while the retrospective ledger continues to own quality ranking.

### 4. Use structured session continuation where a lane supports it

Symphony keeps one app-server process and Codex thread alive across continuation turns, sends the
full task only once, and rechecks issue eligibility between turns.
([continuation contract](https://github.com/openai/symphony/blob/8001b52e3062495a16e520e4ceaf8f9de868c4d0/SPEC.md#L662-L674),
[agent runner](https://github.com/openai/symphony/blob/8001b52e3062495a16e520e4ceaf8f9de868c4d0/SPEC.md#L950-L1177))
For the Codex lane this could reduce repeated briefing and make “keep working until the item changes
state” mechanical. It should be an execution adapter beneath #317's seat/profile resolution, not a
Codex-only replacement for the multi-provider dispatcher.

### 5. Adopt the typed, last-known-good configuration pattern selectively

Symphony reloads `WORKFLOW.md` dynamically, validates again before dispatch, keeps reconciliation
running when dispatch config is invalid, and retains the last known good config after a bad reload.
([reload and preflight](https://github.com/openai/symphony/blob/8001b52e3062495a16e520e4ceaf8f9de868c4d0/SPEC.md#L535-L603))
That is a strong pattern for queue limits, polling cadence, and other operational settings. It is
not a reason to move binding ADR semantics or the failure-class response table into hot-reloaded
YAML. Reloadable mechanics and reviewed governance have different change costs.

### 6. Strengthen workspace and credential boundaries at the coordinator seam

Symphony requires the worker cwd to equal its per-issue workspace, requires that path to remain
under a normalized root, and collision-safely sanitizes tracker identifiers.
([workspace invariants](https://github.com/openai/symphony/blob/8001b52e3062495a16e520e4ceaf8f9de868c4d0/SPEC.md#L928-L948))
It also executes tracker tools host-side and removes tracker credential variables from the coding
agent's environment.
([tool and secret boundary](https://github.com/openai/symphony/blob/8001b52e3062495a16e520e4ceaf8f9de868c4d0/SPEC.md#L1091-L1132))
Arma-cti already has stronger typed worktree lifecycle and per-invocation lane credential assembly;
a future coordinator should assert those existing invariants rather than fall back to arbitrary
workspace shell hooks. Host-side, issue-scoped tracker tools are worth copying, provided their
mutation scope and idempotency are explicit.

### 7. Give the outer coordinator its own conformance suite

Symphony's spec includes an unusually concrete validation matrix for config reload, path
containment, adapter normalization, claims, retries, reconciliation, app-server handling, and
observability.
([test matrix](https://github.com/openai/symphony/blob/8001b52e3062495a16e520e4ceaf8f9de868c4d0/SPEC.md#L2049-L2202))
Arma-cti should borrow that specification style for the scheduler seam: test the refusal or state
transition a caller sees, including duplicate-claim prevention, freeze during a run, terminal issue
cleanup, stale workspace recovery, profile exhaustion, and restart. This fits #317's own rule that
tests assert external behavior at seams.
([#317 testing decisions](https://github.com/andrewesweet/arma-cti/issues/317))

## What should not be copied

1. **Do not replace the project failure classes with automatic exponential retry.** Symphony maps
   worker errors to retries by default.
   ([recovery behavior](https://github.com/openai/symphony/blob/8001b52e3062495a16e520e4ceaf8f9de868c4d0/SPEC.md#L1634-L1688))
   In arma-cti, `infra_unavailable`, `quota_exhausted`, `provider_refused`, `node_crashed`, and an
   untyped harness failure deliberately demand different responses. The outer scheduler must consume
   those verdicts, not flatten them into “try the same work again.”

2. **Do not use Symphony's in-memory state as the review authority.** Symphony deliberately loses
   retries, running sessions, and live worker state on restart, recovering from tracker plus
   workspaces.
   ([restart model](https://github.com/openai/symphony/blob/8001b52e3062495a16e520e4ceaf8f9de868c4d0/SPEC.md#L1690-L1704))
   That is acceptable for scheduling but not for #317's author/reviewer identity, SHA binding,
   findings, adjudications, or landing verdict. Those must remain durable and reconstructable.

3. **Do not mistake workspace isolation for a complete trust boundary.** Symphony itself warns that
   it is a trusted-environment preview, leaves approval and sandbox posture implementation-defined,
   and says workspace isolation is not a substitute for those controls.
   ([preview warning](https://github.com/openai/symphony/blob/8001b52e3062495a16e520e4ceaf8f9de868c4d0/README.md#L10-L11),
   [trust boundary](https://github.com/openai/symphony/blob/8001b52e3062495a16e520e4ceaf8f9de868c4d0/SPEC.md#L1719-L1732))
   The bundled workflow is particularly high-trust: approvals are `never`, the workspace is
   writable, and network access is enabled.
   ([reference config](https://github.com/openai/symphony/blob/8001b52e3062495a16e520e4ceaf8f9de868c4d0/elixir/WORKFLOW.md#L30-L39))

4. **Do not import the bundled human-review state by accident.** The reference workflow waits for a
   human to move `Human Review` to `Merging`; #317 deliberately specifies an autonomous terminus.
   Either posture can be valid, but changing between them is a human ruling, not an implementation
   convenience.

5. **Do not encode never-alone only in `WORKFLOW.md`.** Symphony intentionally leaves delivery
   policy in the prompt, while #317 requires a landing refusal derived from dispatch evidence. A
   prompt can ask for review; it cannot prove that the exact SHA received an independent verdict or
   that every material finding was adjudicated.

6. **Do not collapse seats into one global Codex model.** The reference workflow configures one
   `gpt-5.5`/xhigh Codex command for every active issue.
   ([reference model config](https://github.com/openai/symphony/blob/8001b52e3062495a16e520e4ceaf8f9de868c4d0/elixir/WORKFLOW.md#L30-L39))
   That is simpler than #317's problem, not an answer to it. The useful Symphony abstraction is the
   runner interface beneath seat resolution.

## Recommended synthesis

After #317's sequenced transition is complete, prototype a **thin standing coordinator** with this
boundary:

1. Read the existing queue and issue state; claim one issue under the existing freeze/WIP/package
   rules.
2. Ask the existing dispatcher to resolve a seat and profile; never reproduce that registry.
3. Create/check the issue worktree through `just worktree`; launch the selected lane through its
   existing adapter.
4. Reconcile tracker/queue state and structured worker events; stop or resume using the project's
   typed response rules.
5. Drive the #317 review, adjudication, and exact-SHA landing protocol as its own nested state
   machine.
6. Publish live operational state from the coordinator, and durable quality outcomes from the
   ledger/observatory.
7. Persist enough lineage that a restart can reconstruct claims, authoring dispatches, review SHA,
   findings, and adjudication before any landing decision.

This adopts Symphony's strongest idea—**make the work queue an executable, observable state
machine**—without weakening #317's strongest idea—**no worker is the sole judge of the change it
authored**.

Because ADR-0071 explicitly warns that concurrent or stalled transition steps turn its temporary
inconsistency into a defect, this coordinator should be explored after the current sequence rather
than introduced midway through it.
([ADR-0071 sequencing](https://github.com/andrewesweet/arma-cti/blob/bbb6adebe4682b5612c88305645c6a199bcdce46/docs/adr/0071-the-foreign-lane-is-rescinded-seats-carry-profile-preferences-and-no-change-lands-alone.md#L727-L787))
