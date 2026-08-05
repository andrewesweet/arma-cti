# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **The landing protocol is one call that cannot forget a step.** `just land` runs the
  whole of CLAUDE.md's Commits-section procedure — fetch, rebase onto `origin/main`,
  re-gate, `git push origin HEAD:main`, fast-forward the main checkout — and refuses by
  name rather than by shell error. #209 measured 220 hand calls doing exactly this
  across 117 of 214 agents, and each of the procedure's documented traps exists because
  agents kept falling into it. Three of them are now mechanisms rather than prose. The
  refspec is a constant no argument reaches, so `git push origin main` — which pushes
  the local `main` branch that a detached worktree is not on — cannot be typed through
  this recipe. The gate is *inside* the protocol: `just fast` runs after the rebase on
  every landing that pushes anything, with no flag to skip it and no heuristic deciding
  it is unnecessary, and its output is never captured, so a red gate hands back the
  gate's own words. And the fast-forward into the main checkout can no longer be skipped
  in silence: when it does not run the exit is non-zero and one line, `merge_command=`,
  names the exact command the orchestrator must run — CLAUDE.md's "never skip it
  silently" with a mechanism behind it at last, against the stale-hook window ADR-0042
  and #130 describe. Refusals are the recipe's own vocabulary rather than the harness
  failure-class table (a landing is not a corpus verdict), and the exit code separates
  "nothing landed" from "the work IS on origin/main and a step is outstanding". Logic is
  Python under pytest with the justfile keeping only the seam (ADR-0049); the ladder is
  asserted class by class and the end-to-end tests drive real `git` over a bare
  repository, a main checkout and a linked worktree, never the real remote. #213.
- **A lane stops being dispatched to when it runs out of quota or starts serving the
  wrong thing, and the two are kept apart.** `just breaker` keeps one circuit per lane,
  and `just dispatch` reads it before it plans anything, so a lane that cannot help
  costs nothing to discover. An **availability** trip is quota exhaustion: the lane
  reopens at the provider's own published window boundary — computed, never guessed,
  which is why ADR-0061 gave `quota_exhausted` a failure-class row rather than routing
  it to `infra_unavailable` — and at that boundary the circuit goes half-open, one
  dispatch probes it, and an ordinary outcome closes it. A **quality** trip is three
  consecutive gate failures or refusals on one lane: it refuses with `provider_refused`
  and does not reset on a timer at all, because time does not fix a provider that
  swapped the model behind a name, so it escalates and a human clears it with `just
  breaker reset --lane L --force`. Three consecutive provider errors with no published
  reset open the lane and *hold* it; inventing a cooldown there is the measured defect
  that disqualified LiteLLM as this breaker, so nothing here invents one, and a held
  lane reopens on a fresh first-party quota reading or on an explicit reset. Feeds are
  per provider and honest about what each can know: Claude's is a status-line tap that
  passes the human's own status line through untouched, Codex's is
  `account/rateLimits/read`, and z.ai publishes nothing machine-readable, so its
  consumption is *estimated* from our own dispatch ledger against the documented
  five-hour and seven-day caps and the peak multiplier — labelled estimated, and
  deliberately unable to trip anything, because the ledger counts dispatches and the cap
  counts prompts. With no tap wired the lane is 429-reactive: a finished run's own log
  is classified and fed back, which is late but not blind, and the refusal says so.
  `just watch-report` now prints one verdict line per lane that is not dispatchable and
  stays silent about every lane that is fine — a verdict, never three percentages — and
  `just breaker state` names the lanes whose feed has never said anything. Every
  transition goes to OTel and to a journal beside the state, so a collector that is down
  loses nothing. #226.

- **A logical subagent is dispatched onto a named lane, and the lane's environment goes
  nowhere else.** `just dispatch --lane claude-native --profile opus-high --seat
  implementer --issue 223` starts a separate process and returns a dispatch id at once,
  per CLAUDE.md's rule that a turn does not block for five minutes. Week one registers
  two lanes, both on the `claude` binary: `claude-native`, which reaches the Anthropic
  subscription the one compliant way ADR-0061 records, and `zai`, the permitted mirror
  against z.ai's own published Anthropic-shaped endpoint. A **profile** is one opaque
  `(lane, model, effort)` token in a registry — `opus-high`, `zai-glm52-max` — because
  effort vocabularies do not commensurate across providers (ADR-0061 Decision 5), so
  there is deliberately no `--model` and no `--effort` on the recipe. A **seat** carries
  Decision 2: a foreign lane refuses the seats no mechanical gate covers, so
  `--lane zai --seat fable` comes back `seat_not_eligible` rather than being trusted to
  the caller's memory. The **environment is assembled per invocation and exported
  nowhere** — `ANTHROPIC_BASE_URL` set globally would redirect every Claude Code session
  on this box, the orchestrator included — and assembly strips every lane-owned variable
  from the inherited environment before adding this lane's, so a parent that already
  carries a foreign base URL produces exactly the same child as a clean one. Credentials
  come from `~/.arma-cti/credentials.env` at mode 0600, by environment only: never on
  argv, so never in `ps`, and the dispatch record names the key it used and not its
  value. Identity rides on `OTEL_RESOURCE_ATTRIBUTES` as `cti.dispatch_id`, `cti.lane`,
  `cti.profile`, `cti.seat`, `cti.issue` and `cti.base_sha`, which is what makes a
  dispatch's telemetry self-identifying and Decision 1's per-pool metering a query. The
  dispatched process asserts `git rev-parse --show-toplevel` against its assignment
  before the runner starts and refuses loudly on a mismatch (#105's fourth instance),
  and a lane that cannot be reached — no credentials file, no key, no worktree — is
  `infra_unavailable` and not a result. Logic is Python under pytest with bash keeping
  only the fork (ADR-0049); the end-to-end tests run the real seam against a real git
  worktree and a fake `claude` on `PATH`, so the negative claims are made about an
  actual child environment rather than a mock. #223.

- **`just check` refuses a committed credential.** `check-secrets` runs `gitleaks` over
  the working tree on every static-tier run — #221's secrets ruling, landed with the
  first thing that has a credential to protect. `dir` rather than `git`, because on a
  detached worktree `gitleaks git` reports "0 commits scanned" and a gate that quietly
  scans nothing is the #41 shape; `--redact`, because a secrets gate that prints the
  secret has moved it rather than caught it. The stated limit is unchanged: this
  protects against git, not against the agent, which runs as the same user. #223.

