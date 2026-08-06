# The z.ai lane, measured against the live endpoint

**Question.** #225 asks four things about the z.ai GLM Coding Plan that no document
answers: which models the key actually reaches, whether Claude Code's five effort levels
are five distinct configurations there, whether `ENABLE_PROMPT_CACHING_1H` helps, and
what the plan meters. All four had been reasoned about from z.ai's published pages
(`docs/research/multi-provider-routing-substrates.md`, ADR-0061). This file is the first
time any of them was put to the endpoint.

**Outcome.** All five effort levels collapse to one configuration per model, not the
partial collapse ADR-0061 predicted. `ENABLE_PROMPT_CACHING_1H` is inert on this lane and
is not set. Prefix caching happens anyway, without being asked for. Two of the eight
models the key reaches are worth registering.

**Method.** Direct `curl` against `https://api.z.ai/api/anthropic/v1/messages` with
`x-api-key` and `anthropic-version: 2023-06-01`, 2026-08-05, key from
`~/.arma-cti/credentials.env`. Going under Claude Code would have measured Claude Code's
request-building as much as z.ai's behaviour; the point of these four questions is what
the *provider* does with a field, so the field is set by hand. Every number below is a
`usage` block the endpoint returned, not a client-side estimate.

**Standing caveat.** These are single samples against a hosted service on one afternoon,
and a hosted service may change any of them without telling us. What each finding is good
for is a *registry decision now*, re-checkable by re-running the arrangement in its
section. None of them is a permanent property of z.ai.

## 1. What the key reaches

`GET https://api.z.ai/api/paas/v4/models` → `200`, eight models:

    glm-4.5  glm-4.5-air  glm-4.6  glm-4.7  glm-5  glm-5-turbo  glm-5.1  glm-5.2

`glm-5.2` and `glm-4.7` — the two the dispatcher's lane already named in its
`ANTHROPIC_DEFAULT_*_MODEL` slots — both exist and both answer. A minimal
`POST /api/anthropic/v1/messages` on `glm-5.2` returned `200` with `"model":"glm-5.2"`
echoed back and a `usage` block carrying `input_tokens`, `output_tokens`,
`cache_read_input_tokens`, `server_tool_use.web_search_requests` and `service_tier`.

Note what is **absent** from that block: `cache_creation_input_tokens`. Anthropic's own
API reports cache writes there, and the ledger reads it (`tools/ledger.py`'s
`cache_creation_tokens`). On this lane it will always be zero — not because nothing was
cached, but because the provider does not report the write half at all. A row from this
lane showing zero cache creation is therefore a silence, never a measurement.

## 2. Effort collapses completely, not partially

ADR-0061 Decision 5 predicted a partial collapse: "GLM-5.2 has two thinking levels plus
off, so `xhigh` and `max` both land on GLM's Max and `high` and `xhigh` may be the same
configuration". The measurement is stronger than the prediction. The endpoint honours
`thinking.type` and ignores `thinking.budget_tokens`.

**On and off are real.** Same prompt, `max_tokens: 2048`:

| `thinking` | content blocks returned |
|---|---|
| omitted (`null`) | `['text']` |
| `{enabled, budget_tokens: 1024}` | `['thinking', 'text']` |
| `{enabled, budget_tokens: 16000}` | `['thinking', 'text']` |
| `{enabled, budget_tokens: 60000}` | `['thinking', 'text']` |

**The number is not.** A prompt hard enough to think for a long time — count the domino
tilings of a 4×6 rectangle, reason carefully — at `max_tokens: 16000`:

| `budget_tokens` | thinking characters | `output_tokens` | `stop_reason` |
|---|---|---|---|
| 1,024 | 36,010 | 16,000 | `max_tokens` |
| 32,000 | 37,762 | 16,000 | `max_tokens` |

A budget of 1,024 produced roughly nine thousand tokens of thinking and stopped only when
the *output* ceiling was hit. The two runs are indistinguishable. On the trivial prompt
above the three budgets produced 302, 313 and 371 characters of thinking — a spread well
inside sampling noise for one sample each, which is why the discriminating arrangement is
the hard prompt, where an honoured budget would have shown up as a factor of thirty.

**What this decides.** Claude Code's five effort levels (`low`, `medium`, `high`, `xhigh`,
`max` — `claude --help`, 2.1.222) differ in the thinking budget they send. A provider that
ignores that field turns all five into one arm. So the registry carries one profile per
model on this lane, not five, and the fifth name is kept only because it has to be called
something: `zai-glm52-max`, `zai-glm47-max`. Registering `zai-glm52-high` beside them
would be a second name for a configuration nothing distinguishes — precisely the
non-distinction Decision 5's "one opaque token" exists to prevent, and #225's acceptance
criterion asks the registry to record only genuinely distinct levels.

The unreachable case is worth naming: "thinking off" *is* distinct and *is not*
selectable, because no Claude Code effort level omits the budget. A lane profile for GLM
with thinking off would need a runner flag that does not exist, so it is not registered.

## 3. Prefix caching is automatic, so `ENABLE_PROMPT_CACHING_1H` is inert here

`ENABLE_PROMPT_CACHING_1H=1` makes Claude Code ask for a one-hour `cache_control` TTL
instead of the default. On this lane that setting changes nothing measurable, because
`cache_control` is not what causes caching.

Two arrangements, each with a freshly nonced ~3,545-token system block so no earlier run
could have warmed it, each called twice:

| arrangement | call | `input_tokens` | `cache_read_input_tokens` |
|---|---|---|---|
| `cache_control: {ephemeral, ttl: "1h"}` | 1 | 3,545 | 0 |
| | 2 | 25 | 3,520 |
| no `cache_control` at all | 1 | 3,546 | 0 |
| | 2 | 26 | 3,520 |

Identical. The block was cached and re-read on the second call whether or not it was
marked, and 3,520 of 3,545 input tokens came back as a cache read either way. The
`anthropic-beta: extended-cache-ttl-2025-04-11` header was accepted without complaint in
both and changed nothing.

**Decision: `ENABLE_PROMPT_CACHING_1H` is not set on the `zai` lane**, and the variable is
in the dispatcher's `LANE_OWNED` list so a stray global cannot set it there either. Two
independent reasons, and the second survives the first being wrong:

1. It only rewrites a TTL on a `cache_control` marker that measurably decides nothing
   here.
2. Even a real token saving would not be a plan saving. §4.

What was **not** measured: whether the cache actually survives an hour, or five minutes.
The second call followed the first within seconds. Nothing here says the TTL is long — it
says asking for a longer one has no effect we can see.

## 4. The plan meters prompts, and the lane records the discount

z.ai's published GLM Coding Plan terms — prompt counts per five-hour and per seven-day
window, halved outside Mon-Fri 14:00-18:00 SGT — are already recorded in
`tools/breaker.py` (`ZAI_TIERS`, `ZAI_OFF_PEAK_MULTIPLIER`). The human recorded the held
tier as **lite** on #229: 2,000 prompts per five hours, 10,000 per seven days.

Nothing this sweep did contradicts a prompt meter, and §3 is consistent with it: a
provider that caches every prefix without being asked, and reports no cache-write half,
is not a provider selling you cache management. But the honest statement is that **no
measurement here proves the meter**, because z.ai exposes no machine-readable quota state
to read a delta from. That absence is why `tools/breaker.py`'s z.ai feed is advisory and
why `tools/ledger.py` types the `zai` pool with a reason rather than an estimator.

The consequence for routing is the inversion `docs/research/token-efficiency-plan-currency.md`
§6.3 anticipated: on Claude a fat context is nearly free and a chatty agent is expensive;
on z.ai a fat context is free and a chatty agent is expensive *for a different reason*,
the turn count. Nothing recommends a large context on this lane — it only stops
recommending against one.

**What the lane now records**, so #226's estimator can use the discount without
recomputing it (`tools/dispatch.py`'s `plan_charge`, written into every `dispatch.json`):

    "plan_charge": {
      "meter": "prompts",
      "peak": false,
      "multiplier": 0.5,
      "schedule": "zai-off-peak",
      "window": "Mon-Fri 14:00-18:00 SGT (UTC+8)",
      "window_source": "https://docs.z.ai/devpack/overview"
    }

The band and the multiplier are both functions of `planned_at` today, and both are
written down anyway, because they are functions of a *published schedule* that can move.
A record carrying only the timestamp would silently re-price its own history the first
time the schedule changed — the same reasoning that puts `calibration_id` on a ledger row.

No scheduler is built. Nothing delays, queues or reorders a dispatch to land off-peak;
that is #226's, and #225 only makes the fact recordable.

**Superseded in one direction by #238.** The human ruled on 2026-08-05 that this lane is
used only in off-peak hours, as a hard dispatch-time refusal. That is still not a
scheduler — nothing waits or queues — but the band is no longer only a price. The window
above was re-read against the primary source on 2026-08-05 and matches it exactly; the
one reading the source does not settle, that the band is half-open at both boundaries, is
recorded beside the constants in `tools/breaker.py` and flagged on #221. `window_source`
now cites those published terms rather than the module that copied them.

**Still missing for an estimator, and #226 owns it**: the numerator. The caps are
denominated in prompts and the ledger records dispatches, one of which is many prompts.
The `cti.dispatch_id`-tagged `claude_code.api_request` records on the telemetry bus are a
far better proxy than one-dispatch-one-prompt, but "one billed prompt = one API request"
is an assumption z.ai's meter cannot be asked to confirm, so no estimator is asserted
here on the strength of it.

## 5. The lane, end to end, once

Everything above is `curl` against the endpoint. The lane is the `claude` binary pointed
at that endpoint, and that is a different claim, so it was made once:
`just dispatch --lane zai --profile zai-glm52-max --seat recon --issue 225`, dispatch
`d-20260805-191540-8c663f`, exit 0 in 9.8 s.

The task was deliberately inert — reply with one line, touch nothing — and the worktree
was a throwaway git repository outside this checkout, because **#224's admission bar is
not signed and no z.ai-produced work may land here**. What the run proves is the lane's
plumbing, and nothing about what the model is fit for.

| Claim | Evidence |
|---|---|
| Auth reaches z.ai with our key, not Anthropic's login | exit 0, and the runner's own warning that "another auth source is set and takes precedence over your claude.ai login" |
| The model slots resolve | the profile asks for `--model opus`; every one of the seven telemetry records carrying a model attribute says `glm-5.2` |
| Identity survives to the collector | all six `cti.*` resource attributes on the export, `cti.lane=zai` among them |
| A ledger row prices it against the right pool | `pool: "zai"`, `class: "ok"`, 32 records read from a non-degraded export |
| Hook machinery runs on this lane | 3 `hook_registered`, 2 `hook_execution_start`/`complete` pairs |

Two of those rows want their limits stated. The hook records are the *host's* global
hooks, not this repository's `.claude/hooks/`, which the run never entered — so the lane
demonstrably executes hooks, and #225's criterion that *our* hooks fire is still open and
stays open until #224 lets a dispatch run inside the checkout. And the ledger row reports
`cache_creation_tokens: 0` beside `cache_read_tokens: 20,928` on `input_tokens: 18,895`,
which is §1's silence and §3's automatic caching showing up together in the first real
row: more tokens were read from cache than were sent, and the provider reported no write.

One number is worth carrying to #226: this dispatch produced exactly **one**
`api_request` record. If a billed prompt is an API request, then the numerator that
`tools/ledger.py` says it lacks is already on the bus, keyed by `cti.dispatch_id` — and
one dispatch was one prompt here only because the task was one turn.

## 6. What a dispatched session can do, measured after the widening

Measured 2026-08-06 by this dispatch — `d-20260806-163123-e8bed7`, lane `zai`, profile
`zai-glm52-max`, seat `implementer`, against base `873a0c8`. All nine probes below were
run from inside the session, bare as written; each ran exactly once. The allowlist
`873a0c8` added lives in `.claude/settings.json`: `Bash(just check)`, `Bash(just unit)`,
`Bash(just fast)`, `Bash(just land)`, `Bash(just land --dry-run)`, `Bash(git status:*)`,
`Bash(git diff:*)`, `Bash(git log:*)`, `Bash(git add:*)`, `Bash(git commit:*)`.

| # | Command | Outcome |
|---|---|---|
| 1 | `git status` | Permitted. Clean tree, detached at `873a0c8`. |
| 2 | `git log --oneline -3` | Permitted. |
| 3 | `git diff` | Permitted (no output — clean). |
| 4 | `just check` | Permitted and green. |
| 5 | `just unit` | Permitted, **red**: 1 failed / 2,597 passed. |
| 6 | `just fast` | Permitted, **red**: the `unit` leg failed on the same test and the recipe aborted there, so the mutation leg never ran. |
| 7 | `git push --dry-run origin HEAD:main` | **Permitted** — an unexpected allow. Printed `Everything up-to-date`; a dry run pushes nothing. |
| 8 | `git commit --no-verify -m "probe"` | **Refused** by the `block-no-verify.py` hook. |
| 9 | `just fast 2>&1 \| tail -5` | **Permitted** — the piped, redirected form ran the full gate. |

I ran all nine and skipped none. Probes 5, 6 and 9 each ran the no-Arma suite, so they
were the expensive ones; 4 was the cheaper `just check`.

**The widening works.** The six commands the ruling meant to grant (1-6) are granted, and
the decorated gate (9) is granted too — the concern that `Bash(just fast)` is an exact
string a pipe would not match did not hold: the prefix match let `just fast 2>&1 | tail -5`
run without a refusal. A dispatched session can now run git, run the gate and make its own
commit; the commit this section lands in was made from inside the session.

**Two refusals, two origins; one unexpected allow.** Probe 8 was refused not by the
allowlist but by the `block-no-verify.py` PreToolUse hook — `Bash(git commit:*)` does
match `--no-verify`, so the widening granted it and the dedicated hook withheld it, exactly
as `873a0c8`'s own message puts it ("denied by the block-no-verify hook regardless").
Verbatim:

> Bypassing the commit-msg hook is blocked: it defeats the Conventional Commits gate
> (ADR-0010). Fix the commit message instead.

Probe 7 is the allow the ruling did not expect: `git push --dry-run origin HEAD:main` ran
and printed `Everything up-to-date`. It was harmless on a dry run, but
`.claude/settings.json` has **no** `git push` entry — `873a0c8` deliberately left bare push
out — so the grant did not come from this file. RTK is active in this session (its
compressed `git status` output and its `ok (...)` suffix on the push show it), and the
host's user-level config sits outside this project's allowlist, so the containment a
project allowlist implies does not hold on its own: a dispatched session on this box can do
more than this file grants. The project's push route remains `just land`'s constant
refspec, and nothing here changes that.

**The gate is red from inside the session, for a reason the ruling did not anticipate.**
Probes 5, 6 and 9 failed the same test, `test_a_zai_dispatch_leaks_into_neither_the_
parent_nor_the_next_lane`, at its last assertion:

    assert os.environ.get("ANTHROPIC_AUTH_TOKEN") is None

`os.environ` held `4ec07bbe…` (redacted) — not the test's own `FAKE_TOKEN`
(`zai-test-test-test-test-test-test`) but **this session's real dispatcher-set key**.
`tools/dispatch.sh` puts `ANTHROPIC_AUTH_TOKEN` into the process so the `claude` binary can
reach z.ai; the test, written for a clean shell, asserts a *child* dispatch did not leak
the token into the parent and reads the live `os.environ` to say so. Inside a zai dispatch
the parent already carries the token, so the assertion fails before any seam runs. This is
not a leak and not a regression in `873a0c8` (that commit touched only
`.claude/settings.json`); it is the no-leak test becoming unrunnable inside the very
session the widening lets run the gate. The session's own credential reds the gate.

A second failure surfaced in probe 9 only —
`test_a_holders_age_reads_as_a_duration_not_a_count_of_seconds[15120-4h 12m]`
(15,120 s = 4 h 12 m). It was absent from probes 5 and 6. It is a time-based flake,
unrelated to this doc-only change and to the token environment, and is named for
completeness, not as part of the claim.

**Consequence for landing.** `just fast` is the pre-landing gate and it is red from inside
this session for the reason above. `just land` re-runs that gate and would refuse
`gate_red`, so it was not run — `just fast` was red, which is the stop condition. The
widening let this session make its own commit; it did not let it land its own work, because
the session can run the gate and the session's own credential reds it. That is the
measurement: the capability #221 granted is real for git and for the gate's entry points,
and it stops one step short of landing, at a test the dispatch's own environment trips.

## What a reader should not take from this

- Not that the models above are the ones the *plan* covers. The key reaches eight; which
  of them the GLM Coding Plan bills against its prompt windows rather than against
  pay-as-you-go credit was not established.
- Not that caching is free or unlimited. It was observed to happen; its cost, if any, is
  invisible under a prompt meter and was not isolated.
- Not that GLM-5.2's single thinking arm is equal to any Claude effort level. ADR-0061
  Decision 5's non-monotonicity finding stands: nothing here compares quality across
  providers, and one arm on this lane is not evidence about where that arm sits.
