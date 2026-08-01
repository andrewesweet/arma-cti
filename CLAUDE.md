# arma-cti

Personal Arma 3 Capture the Island scenario, developed primarily by autonomous agents with maximal automated testing. Session-based persistent campaign; player as Commander or squad leader.

> **Process status: unproven — written 2026-07-30, before first practical use.** Every rule here is a hypothesis until a retro validates it. Propose changes only via `/retro`; never drift silently. Audit trail: `docs/process-log.md`.

## Read first

- `CONTEXT.md` — domain glossary. Use its vocabulary exactly; respect the _Avoid_ lists.
- `docs/adr/` — binding decisions. Flag conflicts explicitly; never silently override.
- `docs/mvp-scope.md` — what is in and out of the MVP.
- `docs/reference/arma-wiki/` — vendored Bohemia wiki, now the whole of it (6,690 pages); the live one is Cloudflare-blocked from here. Check it before experimenting on engine behaviour, and before writing your own version of anything the engine might already do. A day of Phase 0 went to rediscovering one documented sentence; Phase 1 built a code generator around a JSON parser the engine had shipped two versions earlier.
  - Paths are guessable: `commands/setDamage.wiki`, `functions/BIS_fnc_spawnGroup.wiki`, plus `topics/`, `classnames/`, `templates/`. `MANIFEST.json` maps every title to its path and carries the redirect aliases. Read a directory's `INDEX.md` rather than listing it — `commands/` alone holds 2,672 files.
  - Which games a page applies to lives in its `// categories:` header, never in the wikitext: BIKI generates categories from templates, so grepping page source for `Arma 3` finds nothing.
  - Pages tagged only for pre-Arma-3 titles are excluded, so a miss is not proof the wiki lacks the page.

## Model roles

- **fable[1m], effort high** — planning sessions, architecture and periodic review, anything touching ADRs, CONTEXT.md, schema semantics, or process docs. Defer structural decisions to a fable session rather than improvising.
- **opus[1m], effort xhigh** — implementation and day-to-day review. May delegate to sonnet/haiku subagents and chooses their effort freely.
- Sessions hand over via `/handoff`.

## Command surface

Interact with the project through `just` only.

| Command | Purpose | Requires Arma | Run when |
|---|---|---|---|
| `just check` | cog, HEMTT lints, ruff, ty, rustfmt, clippy | No | Every edit |
| `just unit` | pytest, cargo test | No | Every edit |
| `just fast` | `check` + `unit` | No | Every edit |
| `just build` | HEMTT addon, shim `.so`, mission PBOs | No | Before any Arma tier |
| `just build-shim-windows` | Cross-compiled `.dll` | No | Before a play session |
| `just spike` | Server + HC + stub daemon, phase-0 measurements | Yes | Ad hoc |
| `just probe [file] [hold]` | Phase-1 world, held up, with a probe from `spike/probes/` appended to the harness | Yes | Verifying a change in-world |
| `just regress [--wait s] [name...]` | The in-world regression corpus in `spike/probes/`: fresh world per probe, one typed verdict each, worst class as the exit code | Yes | Before landing any issue that touches an in-world surface (`addons/`, `missions/`, `extension/`, the daemon's world-facing half, manifests). Named probes while iterating |

Not yet built: `just accept <spec-id>` and `just accept-all`, the acceptance tiers. Phase 3, owned by #5 — the names stay reserved for it (ADR-0016).

`just regress` and `just probe` both serialise on a machine-scoped lock at `~/.arma-cti/tier.lock`: the Arma tier is single-occupancy, and agent worktrees are siblings, so a repo-scoped lock would serialise nobody. A held lock is reported as `infra_unavailable` with the holder's metadata and is **not a result** — do not interpret it, and do not retry into it blindly; `--wait <secs>` bounds a queue. An agent that dies holding the tier releases the lock by itself (kernel `flock`; proven on the first holder death, 2026-08-01): its half-written evidence carries no `verdict.json` and is **not a result**, and any server, daemon, or staged world it left behind is stale state to clear, never context to inherit (ADR-0022). Evidence lands under `~/.arma-cti/runs/`, outside every worktree, and the durable record is the verdict plus evidence path plus SHA quoted into the issue the run gated. Full design: `docs/regression-tier.md`.

`hold` is the probe's window in seconds, default 150. Raise it when the probe's **subject** genuinely takes longer — `spike/probes/contact-decay.sqf` runs at 300 because no shorter window can contain the 120 s of knowledge decay it measures. State the reason in the probe's own header, which is authoritative — this table is not. This is not licence against the `timeout` row above: sizing the window to what is being measured is allowed, extending it until a flaky probe passes is the thing that row forbids. A probe that fails at 150 and passes at 300 without its subject having grown that long is a synchronisation bug, and the fix is in the probe. _(validated ×3 — #28: both probes were flaky and neither fix was a longer wait. Observers left in Reserve sit at the engine's default behaviour with weapons down and never acquired six men at 90 m across a full window; and a bearing off the leader's facing is a guess about line of sight that lands behind a hangar often enough to matter. #17: the harness itself was capping every probe at a hard-coded 180 s regardless of the caller's window; the fix honoured the subject-sized window rather than extending anything to pass. #33: a probe read two effects that land on separate pump turns in the same breath; fixed by waiting on the pair, window unmoved.)_

## Failure classes

Every harness verdict carries a `class`. Read it before anything else. Untyped red = harness bug; fix the harness first. _(validated ×4 — Phase 0: `infra_unavailable` fired on a stale daemon holding the port and correctly refused to be a result. Phase 1: a deliberately emptied manifest produced `assertion_failed` in-world and the harness refused to pass rather than booting an empty world. #22: deleting the manifest to stage a failure took the daemon down first, `infra_unavailable` stopped that run being read as anything, and the guard reached properly classified `assertion_failed`. #23: the old harness called every in-mission failure `assertion_failed`, including ones the world had typed `timeout` or `oracle_disagreement` — the table's required-response column is what made a wrong class a harness bug, and the runner now believes the line's own class.)_

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

The Arma tier shares this machine with the human's play sessions, and WSL2 mirrored networking shares the port space with Windows. The tier uses **2402–2406** and must never take 2302–2306.

## Toolchains

Strictness principle: every tool runs in its strictest practical mode and warnings are errors. A suppression (`# noqa`, `#[allow]`, ignore entry) requires an inline comment justifying it.

- **Python** (daemon, planner, tests): managed by `uv` (locked deps, pinned interpreter; run everything via `uv run`). `ruff` for lint + format; `ty` (Astral) for type checking; `pytest` + `hypothesis`; `coverage.py`; `mutmut` scoped to snapshot save/load and the planner.
- **Rust** (shim only): toolchain pinned in `rust-toolchain.toml`; `cargo clippy -- -D warnings` and `rustfmt --check` in `just check`; `cargo-xwin` for the Windows `.dll`.
- **SQF**: HEMTT lints are the primary static tier (SQF-VM optional — see docs/research/arma-toolchain.md).

Repo hooks (`.claude/hooks/`, wired in `.claude/settings.json`) enforce mechanically: no edits to generated files or acceptance specs (`tests/specs/`), no `git commit --no-verify`, auto-format on edit. A hook denial is a signal you're on a gated surface — propose, don't work around.

## Commits, changelog, versioning (ADR-0010)

- Commit messages follow Conventional Commits 1.0.0 (`feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `build`, `chore`, `ci`; optional scope; `BREAKING CHANGE:` footer or `!` for breaking). A `commit-msg` hook (`cog verify`) rejects everything else; if the hook is missing on a fresh clone, run `cog install-hook commit-msg`.
- Any commit with user-visible effect updates the `[Unreleased]` section of `CHANGELOG.md` in the same commit (Keep a Changelog 1.1.0 categories: Added/Changed/Deprecated/Removed/Fixed/Security). The changelog is curated for humans — never paste commit logs into it.
- Releases: `cog bump --auto` derives the SemVer 2.0.0 bump and tags `vX.Y.Z`. `0.y.z` until MVP scope is fully playable.
- Landing from an agent worktree: `git push origin HEAD:main`, then `git -C <main checkout> merge --ff-only origin/main`. A bare `git push origin main` pushes the local `main` branch, which the worktree is not on, and is rejected as non-fast-forward.

## Working style

- Deliver what was asked, at the scope intended. Make routine judgement calls yourself; check in only when different readings of the request would lead to materially different work. If the request seems mistaken or a better approach exists, say so in a sentence and continue as asked.
- The gates above are this project's verification. Do not add further verification passes, re-checks, or verifier subagents beyond them.
- Delegate to subagents only for sizeable, genuinely independent tracks of work. Do not delegate what you can finish yourself in a handful of tool calls, and never to double-check your own work.
- Ground progress claims in tool results from this session: quote failing output, name skipped steps, mark unverified work as unverified.
- An elimination holds only in the context it was tested. Before inheriting one, check that context still applies: `skipLobby` sat on a closed issue's eliminated list, written off against a server whose mission was not initialised; against one that was, it worked first time.
- In any review pass, report everything you find; filtering by severity happens in a separate pass, not during the review.
- Match written documents to what the task needs — no filler sections, boilerplate, or redundant summaries. Lead every summary with the outcome.
- Land a convention together with its first applied instance; one living only in a design document is not yet a convention. Twice now: Phase 0's command table listed recipes that did not exist, and ADR-0016's probe headers sat on no probe for a day of corpus growth. _(validated ×1 — #23 landed the `just regress` table row, the lock, and the evidence conventions in the same commit as the recipe.)_

**Human sign-off gates** — nothing lands on these without explicit approval: `CONTEXT.md` term changes; new or changed ADRs; acceptance spec changes; snapshot schema semantics; perceptual checklist growth; gameplay balance/feel decisions; changes to this file or the project skills.

Under the human's standing authorisation, an agent may take one of these decisions in their stead, but only by recording it in an ADR carrying the ADR-0013 marker, so `grep -rl "^Delegated-decision: yes" docs/adr/` answers "tell me every decision made on my behalf" completely. An unrecorded delegated decision is out of policy.

**ADR numbers are claimed, not assigned on write.** Agents run concurrently in separate worktrees, so two of them picking "the next free number" from the same `main` produce two ADR-00NNs — which happened on 2026-07-31 and cost a renumber. Before writing, `git fetch origin` and take the next number above every ADR on `origin/main` **and** every ADR number mentioned in an open issue comment; when landing, if the number collided, renumber yours as part of the rebase rather than leaving both. _(validated ×2 — #22 claimed ADR-0017 by issue comment while ADR-0018 landed concurrently; no collision. #23 wrote 0020 while #31 claimed it, and renumbered to 0021 during the rebase, exactly as prescribed.)_

## Agent skills

### Issue tracker

GitHub Issues on `andrewesweet/arma-cti` via `gh`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: root `CONTEXT.md` + `docs/adr/`. See `docs/agents/domain.md`.

### Interrupted-agent recovery

A dead agent resumes from its worktree under a two-sided resumption briefing; its leftovers are ADR-0022 stale infra. See `docs/agents/recovery.md` (ADR-0024).

### Workflow backbone

Use the installed engineering skills rather than improvising process: `/implement` (+ `/tdd`, `/code-review`) for build work, `/research` for fact-finding (primary sources, cited, committed), `/prototype` for design questions, `/grill-me` for gameplay and design decisions that need human sign-off, `/diagnosing-bugs` for hard bugs, `/handoff` between sessions. Project-owned skills: `/playtest-brief`, `/playtest-ingest`, `/retro`. Global skills are shared across projects — never edit them; project process learning lands only in this file, the project skills, and `docs/process-log.md`.
