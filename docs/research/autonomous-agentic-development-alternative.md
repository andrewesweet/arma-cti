# Closest OSS system to product-curator-only development

Research date: 2026-08-14

**Status:** Historical candidate assessment informing
[target-state specification #376](https://github.com/andrewesweet/arma-cti/issues/376).
Its Gas City adoption recommendation is superseded for the MVP by the repository-owned
controller specified in [#377](https://github.com/andrewesweet/arma-cti/issues/377).
This report remains research evidence, not operative process policy.

## Verdict

**Gas City is the closest current OSS foundation for the stated vision.** It is closer
than the Symphony implementations because it is a software-factory builder rather than
only an issue-to-agent scheduler. Its intended unit of input is a feature or outcome;
its formulas can turn that input into durable work, fan it out across agents, review and
gap-check the result, retry failures, and return a finished branch without an operator
supervising each session. The project is MIT licensed. ([Gas City overview](https://github.com/gastownhall/gascity/blob/main/docs/index.mdx),
[repository](https://github.com/gastownhall/gascity))

The best target for arma-cti is not unmodified Gas City. It is:

> **Gas City control plane + a pinned build pack + arma-cti/#317 governance.**

Gas City should own decomposition, durable workflow execution, dependencies, agent
capacity, recovery, and observability. The existing command surface should continue to
own provider routing, failure meanings, independent-review eligibility, evidence, and
landing.

## What “product curator only” requires

The bar is higher than autonomous issue resolution. A system must accept a high-level
product outcome and perform all of these without routine human intervention:

1. turn the outcome into requirements, acceptance criteria, architecture, and a task
   graph;
2. execute independent work concurrently in isolated workspaces;
3. reconcile dependencies, failures, dead workers, restarts, and capacity;
4. verify behavior and independently review the authored change;
5. repair review findings and integration failures;
6. land a proven change; and
7. expose enough evidence for a human to curate the next product outcome.

The human still decides whether a shipped capability is valuable. They do not groom
individual implementation tickets, approve plans, answer routine agent questions, or
review every diff.

## Why Gas City is closest

### It starts above the ticket level

Gas City's first-party description says a feature is decomposed into tracked units,
implemented in parallel, reviewed, checked for gaps against the plan, and completed by
filling what is missing. A formula records how the whole job is performed; Beads retain
the individual work and survive crashes. Agents and roles are configuration rather than
hard-wired scheduler behavior. ([overview](https://github.com/gastownhall/gascity/blob/main/docs/index.mdx))

The official [Gas City packs](https://github.com/gastownhall/gascity-packs) make that
claim concrete:

- `build-basic`: requirements → plan → review → decompose → implement → three-lane
  review;
- `bmad-build`: PRD → architecture → epics/stories → readiness → implementation →
  acceptance audit → adversarial review;
- `compound-build`: planning, implementation, multiple specialist reviewer lanes, and
  resolution; and
- `gstack-build`: founder/PM-flavoured intake, planning, QA, security, and release
  readiness.

The packs distinguish `interactive`, `autonomous`, and `headless` participation modes,
so human approval gates are a workflow choice rather than an unavoidable step.

### It has a real durable control plane

The core provides multiple runtime backends, Beads-backed work and dependencies,
formulas and waits, a supervisor that reconciles desired and running state, health
patrol, and pack-scoped multi-project configuration. ([repository architecture](https://github.com/gastownhall/gascity#what-you-get))

The July 2026 v1.4.0 release added a run-centred dashboard/API, persisted session/work
identity, orphan recovery, stronger retry/fan-out/drain/finalization behavior, runtime
routing across tmux/subprocess/ACP/Kubernetes, cost and token evidence, and release gates
covering unit, process, integration, tutorial, real-inference, and macOS tests.
([v1.4.0 release](https://github.com/gastownhall/gascity/releases/tag/v1.4.0))

That is materially closer to a continuously operating factory than a desktop dashboard
or a prompt that starts several terminals.

### Independent judgment can be made explicit

The default packs already use multiple review lanes. A compatible semantic layer such
as [AgentOps](https://github.com/boshu2/agentops) goes further: implementation and
validation are separate contexts; validation binds to the exact intent and candidate;
the verdict is `PASS`, `FAIL`, or `NOT_PROVEN`; and an optional content-addressed verdict
preserves what was judged. Its Gas City integration describes workers in isolated
worktrees, a fresh validator, and a refiner that merges. This resembles #317's review
and adjudication direction more closely than Symphony's prompt-level “review complete.”

AgentOps is useful evidence and a source of patterns, not a required dependency. The
arma-cti equivalents are already deeper in several places and should remain canonical.

## Runner-up: Stoneforge

[Stoneforge](https://github.com/stoneforge-ai/stoneforge) is the closest out-of-box UX
to the vision:

- a persistent Director receives a goal and creates prioritized dependent tasks;
- ephemeral Workers are dispatched into isolated worktrees;
- a Merge Steward tests, squash-merges on success, and creates repair work on failure;
- recovery Stewards handle stuck tasks; and
- event-sourced state, messages, knowledge, workflows, and a web dashboard survive
  restarts.

It is nevertheless the runner-up rather than the recommendation. Its README explicitly
calls it early-stage experimental software, says agents run with permission checks
bypassed, and removes human approval gates. That may be the desired interaction model,
but it is not yet an adequate safety model. It also combines tracker, knowledge system,
runtime, review, and merge authority into one large trust boundary. It is Apache-2.0.

Stoneforge is an excellent two-day vision prototype. Gas City is the better foundation
for a system whose mechanical gates and failure semantics already matter.

## Why the earlier shortlist ranks lower under this criterion

| System | Why it loses to Gas City for this vision |
|---|---|
| [Kata Symphony](https://github.com/gannonh/kata-symphony) | Strong issue-to-merge controller, but normally begins with a sufficiently specified tracker issue. Its planning layer is adjacent to the scheduler rather than the core factory loop. |
| [oh-my-symphony](https://github.com/cskwork/oh-my-symphony) | Excellent multi-runtime local operations, but it primarily dispatches existing tickets through configured stages. |
| [Contrabass](https://github.com/junhoyeo/contrabass) | Strong scheduling/recovery ideas, but its principal abstraction remains issue-driven agent execution. |
| [Agent Orchestrator](https://github.com/Untrivial-ai/agent-orchestrator) | Has a project-level planning agent, but its current product is built around interactive supervision, reviewing workers, and returning feedback. |
| [Warren](https://github.com/jayminwest/warren) | Strong sandboxed execution substrate; product decomposition and an issue-tracker seam are not its current centre. |

## Recommended arma-cti shape

The safest route is an adapter, not a replacement:

| Factory responsibility | Authoritative arma-cti mechanism |
|---|---|
| Product outcome intake and decomposition | Gas City formula; preserve the originating issue/ruling as immutable intent |
| Eligibility, WIP, reservations | `just queue` |
| Model/provider/seat selection | `just dispatch` and its opaque profiles |
| Workspace lifecycle | `just worktree` |
| Worker liveness and recovery | Gas City run state plus `just watch`/`just recover` |
| Failure interpretation | Existing typed failure classes and lane breakers; never generic retry |
| Independent review | Review seat with recorded `--reviewing` subject and profile exclusion |
| Evidence and cost | `just ledger-sync`, verdict records, regression evidence |
| Landing | `just land`; the factory receives the typed result and cannot bypass it |

The Gas City formula should call these commands as ports. It should not invoke provider
CLIs directly, synthesize its own worktrees, or merge through GitHub.

## Adoption recommendation

Run one autonomous initiative as a canary with the default `build-basic` pack adapted
to the command surface. Do not begin with the most elaborate methodology. The canary
should deliberately include a worker death, rejected review, provider refusal, failed
gate, restart, and competing landing attempt.

Proceed only if it finishes without human steering and every dispatch, verdict, repair,
and merge is attributable and replayable. If it needs a human to resolve implementation
ambiguity, feed that ambiguity back into product-intent and domain-model quality rather
than normalizing human supervision as part of the factory.
