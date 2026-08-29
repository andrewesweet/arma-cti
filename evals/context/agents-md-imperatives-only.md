# arma-cti working rules — imperatives only

Derived from `AGENTS.md` at commit `cbbaf9f8` (2026-08-29). The rule of derivation:
directive sentences only, taken from the **Contract** and **Working style** sections;
the `_(validated ×N …)_` evidence annotations, every table, and narrative rationale are
dropped. Refresh by hand when the underlying rules move materially. This file is an
experimental stimulus for the `AGENTS.md` ablation task, not a copy of the file.

## Contract

**Always**: run `just check` + `just unit` after every edit; read the failure bundle
before modifying code when one exists.

**Never**: edit an acceptance spec to make it pass; add a sleep, retry, or timeout
extension to make a test pass; introduce a bare `random` or bare `sleep` in SQF; call
`setGroupOwner` outside `spike/desync-load.sqf`; treat `infra_unavailable` as a result.

**Never** `export ANTHROPIC_BASE_URL` (or any lane variable) into a shell, a profile,
or `~/.claude/settings.json`.

**Never** extend, invent or guess a breaker's wait. A lane reopens at a boundary its
provider published, on evidence that it is serving again, or by a human's hand — never
on a timer this project chose.

The Arma tier may allocate ports within **[2400, 3000)** and must never take 2302–2306.

## Working style

- A turn does not block for five minutes. An agent that has ended cannot stall. In a
  subagent, foreseeably long work is dispatched detached and the agent then **ends**:
  it commits, arms `just watch`, writes a handoff, and stops there. In the orchestrator,
  waiting is what the seat is for. The exception list is empty and grows only at a retro.
- Reading a finished verdict is not seat-gated. Quote `just verdict`'s rendered body
  verbatim; never retype the SHA or the evidence path.
- Deliver what was asked, at the scope intended. Make routine judgement calls yourself;
  check in only when different readings of the request would lead to materially
  different work. If the request seems mistaken or a better approach exists, say so in
  a sentence and continue as asked.
- The gates above are this project's verification. Beyond the three named exceptions
  (never-alone, the post-landing review, and the Work Run's bounded self-review), do
  not add further verification passes, re-checks, or verifier subagents.
- Two providers over one diff is **one review pass with two lenses**, not a second pass.
- Delegate to subagents only for sizeable, genuinely independent tracks of work; never
  to double-check your own work.
- Ground progress claims in tool results from this session: quote failing output, name
  skipped steps, mark unverified work as unverified.
- An agent watching a run watches from inside its turn: nothing an agent arms outlives
  its turn.
- Before any work in a worktree, verify it is exclusively yours — clean `git status`,
  no foreign uncommitted files — and commit early and often. Foreign files mean stop
  and report, never reset.
- Measure before building: a rule proposed on cost or threshold grounds is checked by
  running the measurement, not settled by intuition.
- An elimination — or any inherited measurement or rationale — holds only in the
  context it was tested. Re-derive before inheriting.
- In any review pass, report everything you find; filtering by severity happens in a
  separate pass, not during the review.
- Match written documents to what the task needs — no filler sections, boilerplate, or
  redundant summaries. Lead every summary with the outcome.
- Land a convention together with its first applied instance; one living only in a
  design document is not yet a convention.
- ADR numbers are claimed, not assigned on write: scan `origin/main` and open issues
  before writing, and renumber on the landing rebase if the number collided.
