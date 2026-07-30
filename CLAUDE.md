# arma-cti

Personal Arma 3 Capture the Island scenario, developed primarily by autonomous agents with maximal automated testing. Session-based persistent campaign; player as Commander or squad leader.

> **Process status: unproven — written 2026-07-30, before first practical use.** Every rule here is a hypothesis until a retro validates it. Propose changes only via `/retro`; never drift silently. Audit trail: `docs/process-log.md`.

## Read first

- `CONTEXT.md` — domain glossary. Use its vocabulary exactly; respect the _Avoid_ lists.
- `docs/adr/` — binding decisions. Flag conflicts explicitly; never silently override.
- `docs/mvp-scope.md` — what is in and out of the MVP.

## Model roles

- **fable[1m], effort high** — planning sessions, architecture and periodic review, anything touching ADRs, CONTEXT.md, schema semantics, or process docs. Defer structural decisions to a fable session rather than improvising.
- **opus[1m], effort xhigh** — implementation and day-to-day review. May delegate to sonnet/haiku subagents and chooses their effort freely.
- Sessions hand over via `/handoff`.

## Command surface

Interact with the project through `just` only. (Recipes land during Phase 0; table updates as they arrive.)

| Command | Purpose | Requires Arma | Run when |
|---|---|---|---|
| `just check` | HEMTT lints, schema freshness, grep lints | No | Every edit |
| `just unit` | pytest, cargo test, SQF-VM suite | No | Every edit |
| `just build` | HEMTT build + shim build | No | Before any Arma tier |
| `just accept <spec-id>` | Server+HC bring-up, one spec | Yes | On behaviour change |
| `just accept-all` | Full acceptance suite | Yes | Pre-commit for gameplay changes |

## Failure classes

Every harness verdict carries a `class`. Read it before anything else. Untyped red = harness bug; fix the harness first.

| Class | Required response |
|---|---|
| `assertion_failed` | Fix the code under test |
| `timeout` | Investigate synchronisation. Never extend the timeout to pass |
| `node_crashed` | Collect dump, escalate to human |
| `oracle_disagreement` | Capture layer is prime suspect. State reasoning for human review before touching it |
| `infra_unavailable` | Stop. Not a result. Do not interpret |
| `engine_drift` | Arma build changed. Suspect the engine, escalate; do not "fix" our code against it |
| `schema_stale` | Regenerate; never hand-edit generated files |
| `flake_quarantine` | Do not act. Fix synchronisation separately |

## Contract

**Always**: run `just check` + `just unit` after every edit; read the failure bundle before modifying code when one exists.

**Never**: edit an acceptance spec to make it pass; add a sleep, retry, or timeout extension to make a test pass; introduce a bare `random` or bare `sleep` in SQF (seeded PRNG and CBA scheduler adapters only); treat `infra_unavailable` as a result.

## Working style

- Deliver what was asked, at the scope intended. Make routine judgement calls yourself; check in only when different readings of the request would lead to materially different work. If the request seems mistaken or a better approach exists, say so in a sentence and continue as asked.
- The gates above are this project's verification. Do not add further verification passes, re-checks, or verifier subagents beyond them.
- Delegate to subagents only for sizeable, genuinely independent tracks of work. Do not delegate what you can finish yourself in a handful of tool calls, and never to double-check your own work.
- Ground progress claims in tool results from this session: quote failing output, name skipped steps, mark unverified work as unverified.
- In any review pass, report everything you find; filtering by severity happens in a separate pass, not during the review.
- Match written documents to what the task needs — no filler sections, boilerplate, or redundant summaries. Lead every summary with the outcome.

**Human sign-off gates** — nothing lands on these without explicit approval: `CONTEXT.md` term changes; new or changed ADRs; acceptance spec changes; snapshot schema semantics; perceptual checklist growth; gameplay balance/feel decisions; changes to this file or the project skills.

## Agent skills

### Issue tracker

GitHub Issues on `andrewesweet/arma-cti` via `gh`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: root `CONTEXT.md` + `docs/adr/`. See `docs/agents/domain.md`.

### Workflow backbone

Use the installed engineering skills rather than improvising process: `/implement` (+ `/tdd`, `/code-review`) for build work, `/research` for fact-finding (primary sources, cited, committed), `/prototype` for design questions, `/diagnosing-bugs` for hard bugs, `/handoff` between sessions. Project-owned skills: `/playtest-brief`, `/playtest-ingest`, `/retro`. Global skills are shared across projects — never edit them; project process learning lands only in this file, the project skills, and `docs/process-log.md`.
