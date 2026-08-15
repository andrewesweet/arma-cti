# OSS alternatives to OpenAI Symphony

Research date: 2026-08-14

**Status:** Background prior-art survey informing
[target-state specification #376](https://github.com/andrewesweet/arma-cti/issues/376).
No product surveyed here is selected by the repository-owned MVP in
[#377](https://github.com/andrewesweet/arma-cti/issues/377).

## Question and comparison bar

This scan looks for open-source systems pursuing Symphony's operational goal: turn a
tracker backlog into bounded, isolated, observable coding-agent runs so that a human
manages work rather than individual sessions.

A close substitute therefore needs most of these properties:

- tracker- or queue-driven unattended dispatch;
- an isolated, persistent workspace per item;
- concurrent workers, claims, retries, and reconciliation;
- continuity across turns or process restarts;
- a path from implementation through PR, CI, review, and landing;
- operator-visible state; and
- repository-owned workflow policy.

This is a stricter bar than “can run several coding agents.” It excludes a normal
agent IDE, a one-shot issue resolver, and a multi-agent swarm from the direct-substitute
category even when those tools are useful.

## Bottom line

There are credible alternatives, but the closest ones are mostly young Symphony
implementations or forks rather than independent, proven products. The best direct
candidates to study are **Kata Symphony**, **oh-my-symphony**, and **Contrabass**.
None is a drop-in fit for arma-cti:

- Kata has the best GitHub/Linear ticket-to-merge story, but its documented runners
  are Codex and Pi rather than arma-cti's lane/profile dispatcher.
- oh-my-symphony has the broadest per-ticket CLI choice and stronger local operations,
  but its documented trackers are local Markdown, Linear, and Jira, not GitHub Issues.
- Contrabass combines GitHub/Linear/local trackers with multiple runtimes and unusually
  explicit crash/claim handling, but is still an early implementation whose claims
  need a practical trial.

The more mature-looking adjacent projects solve only part of the problem. GitHub
Agentic Workflows is an event-driven, hardened automation substrate; Warren is a
sandboxed execution control plane; Shep and Agent Orchestrator are human-initiated
agent supervisors. They can teach useful lessons but do not replace Symphony's
long-running tracker reconciler.

Most importantly, none of the reviewed projects documents mechanical equivalents for
arma-cti's typed failure classes, lane breakers, profile provenance, independent-review
exclusion, or adjudication. Adopting one as the outer scheduler should not displace
the #317 governance layer.

## Direct substitutes

| Project | What overlaps Symphony | Main difference or risk | License |
|---|---|---|---|
| [Kata Symphony](https://github.com/gannonh/kata-symphony) | Headless polling of GitHub Projects v2 or Linear; issue claims and dependency gating; worktree, clone, or Docker isolation; concurrent multi-turn workers; retries/reconciliation; per-state prompts and models; full PR/review/merge lifecycle; TUI, HTTP API, and SSH worker pools. Its [orchestrator reference](https://github.com/gannonh/kata-symphony/blob/main/apps/symphony/README.md) is unusually detailed. | Closest feature match, but it is a recent project and supports Codex app-server or Pi RPC as documented worker types. Much of “quality complete” still depends on workflow prompts and tracker transitions. | MIT |
| [oh-my-symphony](https://github.com/cskwork/oh-my-symphony) | A direct Symphony fork with unattended polling, isolated worktrees, concurrency, retries, managed service commands, TUI/web control, token/rate-limit visibility, pause/resume, local Markdown/Linear/Jira trackers, and per-ticket choice among several agent CLIs. It adds SQLite run leases and restart-safe issue flags. | Strongest match for heterogeneous local agents, but no documented GitHub tracker. Its broad operator surface and agent-authored state transitions enlarge the correctness surface. | Apache-2.0 |
| [Contrabass](https://github.com/junhoyeo/contrabass) | Go reimplementation with GitHub, Linear, and an internal board; worktree provisioning; claims, dependency blocking, orphan recovery, deterministic backoff, stall detection, crash recovery, headless/TUI/web modes, and several agent runners. | Attractive operational design, but young and broad. Treat README completeness as a hypothesis until restart, duplicate-dispatch, stale-claim, and landing behavior pass a local fault-injection trial. | Apache-2.0 |
| [broomva/symphony](https://github.com/broomva/symphony) | Rust implementation of the Symphony spec with Linear, GitHub, and Markdown trackers, isolated workspaces, lifecycle hooks, concurrency, retries, reconciliation, and an API. | More a portable spec implementation than a different system of work; smaller evidence base and less documented PR/review governance than the three above. | Apache-2.0 |

These projects deserve to be called alternatives because they implement the same
control loop, even though several explicitly derive from the Symphony specification.
Their existence also means a greenfield reimplementation should justify itself against
available code, not only against OpenAI's Elixir reference.

## Adjacent systems worth studying

### GitHub Agentic Workflows (`gh-aw`)

[GitHub Agentic Workflows](https://github.com/github/gh-aw) compiles Markdown workflow
definitions into GitHub Actions and supports Copilot, Claude, Codex, Gemini, and Pi.
Its most important contribution is its security model: agent jobs are read-only and
sandboxed by default, while requested GitHub mutations go through scoped, validated
“safe outputs.” The [workflow documentation](https://github.github.com/gh-aw/reference/workflow-structure/)
also keeps deterministic CI separate from agentic interpretation.

It is event- or schedule-driven rather than a persistent tracker/workspace reconciler.
Actions jobs are disposable, so it does not naturally preserve one issue's workspace,
claim, session, and retry state across a long lifecycle. It is therefore not a direct
Symphony replacement, but it is the strongest source here for mechanically mediating
external writes.

### Warren

[Warren](https://github.com/jayminwest/warren) is a self-hosted control plane for
short-lived coding agents. It supplies fresh bwrap or Kubernetes isolation per run,
an event stream, steering and cancellation, cron triggers, restart-aware supervision,
cost/token reporting, cost caps, PR creation, and serial plan execution. This is a
stronger execution and isolation substrate than a bare worktree.

Its own status section says the issue-tracker seam is still future work. Runs are
primarily manual, scheduled, or plan-driven rather than continuously reconciled from
GitHub/Linear issue state. Warren could sit below a Symphony-like scheduler, not replace
that scheduler today. It is MIT licensed.

### Shep

[Shep](https://github.com/shep-ai/shep) runs Claude Code, Cursor, Gemini, or another CLI
in isolated worktrees from a feature prompt. It can add requirements/plan approval
gates, commit and push, open a draft PR, watch CI, and attempt bounded CI repair. It is
local-first and MIT licensed.

Shep starts from `shep feat new`, not from a continuously reconciled external backlog.
Its feature state machine and CI feedback loop are relevant, but dispatch remains
human-initiated and locally owned.

### Agent Orchestrator

The former Composio repository now redirects to
[Untrivial Agent Orchestrator](https://github.com/Untrivial-ai/agent-orchestrator).
The current project is an Apache-2.0 desktop application with a local daemon, isolated
branches/worktrees, a persistent project-planning agent, many supported coding-agent
interfaces, and a live board derived from worker, PR, CI, review, and merge state.

It is a good interaction design for supervising a fleet, especially its separation of
project-level planning from task workers. It is not currently presented as a headless
issue-tracker polling service, so its goal is interactive orchestration rather than
Symphony's unattended reconciliation.

### OpenHands Resolver

The [OpenHands issue resolver](https://github.com/OpenHands/OpenHands/blob/main/openhands/resolver/README.md)
can respond to a trigger label, attempt an issue fix in CI or locally, publish a branch
or PR, and revisit PR comments across GitHub, GitLab, Bitbucket, and Azure DevOps. It is
explicitly optimized for one issue at a time. This makes OpenHands a possible worker
backend, not a fleet scheduler.

## Projects not recommended for a new adoption

- [Vibe Kanban](https://github.com/BloopAI/vibe-kanban) has a polished board,
  workspaces, multi-agent support, diff review, previews, and PR creation, but its own
  README says the project is sunsetting.
- [Overstory](https://github.com/jayminwest/overstory) contains useful worktree,
  inter-agent messaging, merge, and runtime-adapter ideas, but the repository was
  archived on 2026-05-28. Warren is its author's stated successor.

## Fit with arma-cti and issue #317

The direct candidates overlap the outer half of the proposed system of work:

| Need | Existing candidates | arma-cti-specific requirement still missing |
|---|---|---|
| Select work and keep workers busy | Kata, oh-my-symphony, Contrabass | Queue freeze, WIP reservations, carve-outs, and human-ruling provenance |
| Isolate concurrent changes | All direct candidates; Shep and Agent Orchestrator | Existing `just worktree` preflight, archive/restore, and landing invariants |
| Route across models/providers | oh-my-symphony is broadest; `gh-aw` also supports several engines | Opaque lane/profile registry, probation, quota windows, circuit breakers, and seat eligibility |
| Recover and retry | All direct candidates claim retries; oh-my-symphony and Contrabass add durable recovery features | Failure-class-specific response instead of generic retry/backoff |
| Review and merge | Kata has the most complete documented loop | Author/profile exclusion, independent review evidence, adjudication, and the non-skippable `just land` gate |
| Observe operations | Kata, oh-my-symphony, Contrabass, Warren, Agent Orchestrator | Per-dispatch ledger joined to profile/lane evidence and #317 observatory questions |

This suggests a boundary, not a wholesale replacement:

1. Keep `just queue`, `just dispatch`, `just worktree`, `just land`, admission, breakers,
   and the failure taxonomy authoritative.
2. If prototyping a candidate, make its worker adapter invoke the existing dispatcher
   and consume typed outcomes. Do not let it launch provider CLIs or push/merge directly.
3. Let the candidate own polling, claims, continuation, reconciliation, and a read-only
   operational view.
4. Represent human review and adjudication as explicit non-active tracker states, with
   state transitions performed only after the existing mechanical evidence passes.

## What to borrow

The best ideas are distributed across projects rather than concentrated in one tool:

- From Kata: GitHub Projects v2 as an operator surface, dependency-aware eligibility,
  per-state policy, and a concrete ticket-to-PR feedback loop.
- From oh-my-symphony: a thin agent-backend protocol, local file-backed operation,
  managed-service ergonomics, pause/resume, durable leases, and restart-safe flags.
- From Contrabass: orphan-claim recovery, explicit branch-advance checks, deterministic
  retry, liveness snapshots, and crash recovery as first-class scheduler behavior.
- From `gh-aw`: default read-only execution and validated, least-privilege write
  mediation. This is stronger than asking an agent prompt to limit its own mutations.
- From Warren: one ephemeral sandbox per run, persisted event streams, resource
  admission, spend caps, and runtime/control-plane separation.
- From Agent Orchestrator: derive the board from factual worker/PR/CI/review state and
  keep project planning separate from task execution.

## Recommended next step

Do not select a product from README comparison alone. A bounded spike should test two
architectural candidates, not migrate the process:

- **Kata Symphony** for the closest GitHub-backed control loop; and
- **oh-my-symphony or Contrabass** for multi-runtime and recovery mechanics.

Give each the same synthetic queue and fault script: duplicate poll, stale tracker
state, worker death, host restart, provider refusal, quota exhaustion, failed gate,
review rejection, and concurrent landing attempt. The winning criterion is not how
many agents it starts. It is whether every transition remains attributable,
idempotent, recoverable, and subordinate to the existing typed gates.
