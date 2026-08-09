# The landed initiative rulings get their ADR, and two post-ratification corrections are recorded

Date: 2026-08-09
Decided-by: human, on #221 — the prior-art sweep rulings of 2026-08-05T15:51Z, the quota-feedback
ruling of 2026-08-05T16:13Z, and Decisions 1 and 2 of 2026-08-05T21:14Z. Nothing is decided by this
document: every ruling below was taken by the human on the date named beside it, and this ADR is
the durable home Decision 1 of 21:14Z ordered for them
Claimed: against `origin/main` at `5ed7417`, whose `docs/adr/` tops at 0065, plus a search of every
open issue finding no claim above 0065. The worktree was created by `just worktree add`, which
fetches; `git fetch origin` was not re-run in this session, so the rebase inside `just land` is the
backstop the standing rule provides for exactly that gap
Reviewed-by-human: pending

This is the second ADR of the multi-provider dispatch initiative. ADR-0061 recorded the eight
rulings that were independent of which substrate won, and deliberately held six more as *settled by
the prior-art sweep, awaiting a first applied instance* — because a convention living only in a
design document is not yet a convention. Those instances have since landed. This document is where
those rulings live, together with the ruling that changed shape (portability), the two corrections
to how ADR-0061's own rulings were reached, and the full reasoning behind two of its 2026-08-06
amendments.

ADR-0061 is ratified and immutable and is not reopened here. It was amended on 2026-08-06 by the
human's ruling on #221 — seven corrections of fact, no decision reversed, each marked inline on the
page — and reviewed the same day. Where a passage below supersedes something ADR-0061 says, it says
so rather than quietly writing the current state.

Each decision states the ruling, when and where it was taken, the first instance that landed it,
and how the tree reads today. Where a ruling's *premise* has since been superseded by measurement,
that is recorded under **Every ruling checked against what landed** rather than smoothed into the
ruling's own text.

## Decision 1: the substrate is each provider's own CLI, and the mirror is permitted

Ruled 2026-08-05T15:51Z (#221, the prior-art sweep report).

A subscription is reached only through the vendor's own client. The standing rule the sweep
produced is absolute: **no subscription credential goes into any third-party process, on any lane**
— three separate tools offered to do exactly that.

The **mirror** is the one apparent exception and is not one: the `claude` binary may be pointed at a
non-Anthropic endpoint, consuming no Anthropic quota, credential or traffic. z.ai publishes the
variables for it (`ANTHROPIC_BASE_URL`, plus the three `ANTHROPIC_DEFAULT_{OPUS,SONNET,HAIKU}_MODEL`
slots), so this is that provider's own documented integration rather than a workaround.

**As landed** — #225, `dd3923e`. `LANES` in `tools/dispatch.py` registers `claude-native` (the
`claude` binary on the box's own login, no credential of ours), `zai` (the same binary against
`https://api.z.ai/api/anthropic`), and `codex` (OpenAI's own CLI, which reads its own
`~/.codex/auth.json`, so again no credential of ours). `assemble_environment` strips every
lane-owned variable from the parent's environment whatever its value and then adds back only the
ones the lane owns, so a lane's identity is a function of the lane and never of the shell that
dispatched it.

## Decision 2: dispatch granularity is a whole agent run assigned to one lane

Ruled 2026-08-05T15:51Z. Per-request-type routing requires a session-global base URL, which
forfeits the subscription; the leading proxy reaches the subscription by reading
`~/.claude/.credentials.json` and replaying the OAuth token, which Decision 1 bars outright.
Corroborating, from that project's own history: it abandoned its category router in v3 in favour of
Claude Code's native model-slot variables.

**As landed** — #223, `f86cba9`. `just dispatch --lane L --profile P --seat S --issue N` starts one
logical subagent as one separate process and returns a dispatch id at once. Identity travels as
`OTEL_RESOURCE_ATTRIBUTES` (`cti.dispatch_id`, `cti.lane`, `cti.profile`, `cti.seat`, `cti.issue`,
`cti.base_sha`), and a parent's `cti.*` is dropped from the child so two dispatches can never share
an id.

One consequence is recorded because it reinforces the decision rather than merely following from
it: a dispatch identity distinguishes only separate processes, so an in-session subagent shares its
parent's resource block and cannot be ledgered at all.

## Decision 3: the lane circuit breaker has two trip families, and never invents a wait

Ruled 2026-08-05T15:51Z as *stands, shrinks by half*; the halving is Correction 2 below.

- **Availability.** The lane cannot serve now. Quota exhaustion is the common case, it is
  foreseeable, and its wait is computed from a published window boundary — never guessed. It
  auto-resets: at the reset the circuit goes half-open, one dispatch probes it, an ordinary outcome
  closes it.
- **Quality.** The lane is serving and what it serves is wrong: N consecutive gate failures, or N
  consecutive refusals, on one profile. This does **not** auto-reset, because time does not fix it.
  It escalates, and clearing it is a human act.

A third case looks like the first and must not behave like it: N consecutive provider errors with
no published reset **open the lane and hold it**. Reopening is on evidence — a fresh first-party
reading showing the lane answering — or by a human's hand, never on a timer this project chose.

**As landed** — #226, `tools/breaker.py` and `just breaker`. The state is read by `just dispatch`
before anything is planned, so a closed lane refuses before a briefing is composed.

## Decision 4: OTel is the single capture bus for every lane

Ruled 2026-08-05T15:51Z, with one correction taken in the same breath: "all lanes" requires a
*traces* pipeline as well as metrics, because opencode emits no metrics at all and carries its token
counts only as AI SDK spans.

Attributes are `cti.*` and coexist with nothing: the `gen_ai.*` semantic conventions are entirely
`development`, and OTel's own naming guidance forbids proprietary attributes under its namespace.

Two properties of the bus were ruled with it. Content logging is off — `OTEL_LOG_USER_PROMPTS`
stays unset, and the `prompt` attribute's value is the literal `<REDACTED>`. And Codex's
`metrics_exporter` defaults to `Statsig` → `https://ab.chatgpt.com/otlp/v1/metrics`, an undocumented
off-box surface, which must be disabled **before** first use rather than after.

**As landed** — #227, `a885306`, with the off-box exporter disabled by `just prereqs` before the
lane's first run (#230).

## Decision 5: durability is a filtered non-rotating per-dispatch export, with one view over it

Ruled 2026-08-05T15:51Z as *three changes, all less work*. The collector's `group_by` file export
writes one file per `cti.dispatch_id`, so the filtering, the splitting and the durability are
collector configuration with no code behind them — and the compaction step the original design
carried **disappears**. `dispatch.json` / `turns.jsonl` / `raw/` was over-structured: the collector
output already is the raw record.

**As landed** — #227. Records carrying `cti.dispatch_id` go to
`/var/log/claude-otel/dispatches/dispatch-<id>.jsonl`, append-only and non-rotating, beside the
existing rotating capture. `just ledger-sync` is a **materialised view**, not a second writer: it
opens both telemetry paths read-only, writes exactly one file — `~/.arma-cti/dispatches/<id>/ledger.json`
— and a test checksums the rotating capture across a sync for that claim. Rows are kept
indefinitely; the raw export is pruned at 30 days and only where a row exists that was materialised
from the durable export and read at least one record out of it.

A phrasing note, because the two forms are both in circulation: the summary table in #221's
Decision 1 renders this row as "compaction to `~/.arma-cti/dispatches/<id>/`", which is the wording
from *before* the sweep removed the compaction step. What landed is the ruling, not the summary
row.

## Decision 6: secrets live in one file at mode 0600, reached only by environment

Ruled 2026-08-05T15:51Z, as the mechanical face of Decision 1's standing rule.

`~/.arma-cti/credentials.env` at mode 0600, outside every worktree. A credential reaches a child
process by environment and by nothing else: never on argv, so never in `ps`; never in the dispatch
record, which names the *key* it used and never its value; never in the brief and never in the log.
The limit is stated rather than glossed — **this protects against git, not against the agent**,
which runs as the same user.

**As landed** — #223 and #230. `read_credentials` refuses a missing file (`credentials_missing`), a
mode any group or other can reach (`credentials_mode`, printing `want=0600`), and a file lacking
this lane's key (`credential_absent`); all three are `infra_unavailable`, because a lane that could
not be reached says nothing about the code under test. `just prereqs credentials` takes the one
pasted key at 0600 outside every worktree, and `just prereqs tools` installs `gitleaks`.

`just check`'s `check-secrets` is `gitleaks dir . --no-banner --redact`. Two details are decisions
rather than defaults: `dir` and not `git`, because on a detached worktree `gitleaks git` reports
"0 commits scanned" and a gate that quietly scans nothing is worse than no gate; and `--redact`,
because a secrets gate that prints the secret has moved it rather than caught it.

## Decision 7: both foreign lanes land inside week one

Ruled 2026-08-05T15:51Z, sequenced by the handoff of 16:33Z: #223 the dispatcher first, since
everything depends on it and it needs no credential; #230 `just prereqs`; #224's admission bar
**before any foreign lane lands**, or it cannot be set honestly; then #225 z.ai as the first relief,
#226 the breaker, #227 the telemetry spine.

**As landed** — the z.ai lane at `dd3923e` on 2026-08-05 and the Codex lane at `988553b` on
2026-08-06, both inside week one and in the ruled order. The decision is discharged; it is recorded
because a later reader asking why two providers arrived in one week should find the answer here
rather than infer haste.

## Decision 8: the orchestrator sees a verdict per lane, never percentages

Ruled 2026-08-05T16:13Z.

The rationale is #209's: where a rule-table already decides, an agent is not handed numbers to
reason about. The breaker owns the threshold; the orchestrator owns the dispatch. Delivery is folded
into `just watch-report`, which CLAUDE.md already puts at the top of an orchestrator's turn, so the
feed costs no extra call — one line per lane that is not dispatchable, and silence for every lane
that is.

The weaknesses were recorded with the ruling rather than after it. The Claude status line lives in
the human's global `~/.claude/settings.json`, which this repository cannot govern, enforce or test;
status lines run only in interactive sessions, so a headless orchestrator loses that feed entirely;
and with the tap absent the dispatch path is 429-reactive — late, but not blind.

**As landed** — #226. `just watch-report` leads with the breakers, ahead of the queue and the
watchers, and the line is a verdict: `dispatch=refused`, a failure class, and a reset time where the
provider published one.

Two of this ruling's premises about *feeds* have since been superseded by measurement. The ruling
itself — a verdict, never percentages — is unaffected; see **Every ruling checked against what
landed**.

## Decision 9: `AGENTS.md` is the source, and `CLAUDE.md` is a committed symlink to it

Ruled 2026-08-05T21:14Z (#221, Decision 2). This is the one ruling that changed shape rather than
merely gaining an instance, so its history matters: ADR-0061 held portability as *APM failed;
re-decided*, and the sweep's replacement was an `@AGENTS.md` import guarded by a form check
asserting `CLAUDE.md` is exactly the import line. The human's ruling kept the substance —
`AGENTS.md` as sole source, hook configuration hand-written per target, no compiler — and replaced
the mechanism with `ln -s AGENTS.md CLAUDE.md`, committed.

Both routes were documented and both work; the symlink was preferred for one risk and one
structural reason.

1. **The import carries an undocumented compaction risk.** The docs state that a project-root
   `CLAUDE.md` survives compaction — Claude re-reads it from disk and re-injects it — and say
   nothing about whether that re-read re-expands imports. This project's entire process lives in
   that file. A symlink has no import to re-expand and cannot fail that way.
2. **Drift stops being checked and becomes impossible.** Git stores the link, so the two files
   cannot diverge, and `just check` asserts it is still a symlink in one line. That is a stronger
   guarantee for less machinery than a form check over the import line.

The import's one advantage — appending Claude-specific content below the line — is what this ruling
does not want, since `AGENTS.md` is the sole source.

Drift control is one mechanism per surface, all in `just check`: **instructions**, structurally, by
the symlink plus its assertion, with `protect-gated-paths` moved to guard `AGENTS.md` since that is
where the sign-off gate now lives; **hooks**, behaviourally, by the parity suite ADR-0061 Decision 4
already mandates, which is what catches configuration that is present but mis-wired; **agent
definitions**, by static equivalence of the seat and profile registry per target, modulo a
documented exception list.

Recorded because it is repeatedly assumed otherwise: **the rename saves no context.** Imported files
load at launch, so neither the import nor the symlink changes what the file costs — that is #216's
and #220's ground, not this ruling's.

**As landed** — #264, sequenced after #228's rows and the #218/#219/#220 landings exactly as the
ruling required, because moving the guard is a gate outage on the file that carries the gates.
`b3f3a23` makes `AGENTS.md` the source and `CLAUDE.md` the symlink; `ac8b6a4` adds
`check-source-link` (`tools/check_source_symlink.py`) to `just check`. `ls -l` reads
`CLAUDE.md -> AGENTS.md`.

## Correction 1: substrate was settled by the terms, not by a spike

ADR-0061 recorded native per-provider CLIs against `opencode` as a question a spike would settle.
It was not one, and the difference is not cosmetic: a preference settled by spike can be reopened by
a better spike, and a constraint from a provider's terms cannot.

Anthropic's Consumer Terms **§3** bar accessing the Services by automated or non-human means except
via an API key, and **§2** bars credential sharing. Reaching the Anthropic subscription only through
Claude Code is therefore the one compliant configuration. `claude-code-router` is barred outright,
on what it does rather than on how well it works: it reads `~/.claude/.credentials.json` and replays
the OAuth token.

What remains genuinely spikeable is narrower than ADR-0061 states — native CLIs against `opencode`,
**for non-Anthropic lanes only**. The owed terms read widens to OpenAI's for the same reason:
LiteLLM's `chatgpt` provider presents as `codex_cli_rs/0.0.0`, which is the same category of
concern.

## Correction 2: the breaker halved, and the rejected library's four defects are the design

ADR-0061 scoped the breaker as wholly this project's to build. Half of it is not. Codex publishes
quota state first-party — `account/rateLimits/read`, returning `usedPercent`, `windowDurationMins`,
`resetsAt` and `rateLimitReachedType`, plus an `account/rateLimits/updated` notification — so on that
lane the availability half is free and, more importantly, **pre-dispatch**. Only the quality half is
ours.

LiteLLM was rejected as the breaker on four counts, every one from a primary source read rather than
a summary:

1. a five-second default cooldown, against windows five hours long;
2. a failure **ratio** rather than consecutive-N;
3. no quality trip at all;
4. cooldown transitions that never reach OTel, so the breaker's own state changes would be invisible
   to the single capture bus of Decision 4.

The rejection is recorded as a correction rather than as trivia because those four counts *are* the
specification of what replaced it. CLAUDE.md's standing rule — never extend, invent or guess a
breaker's wait — is count one turned into a rule, and Decision 3's consecutive-N quality trip is
counts two and three.

Correction 2's own account of z.ai has since been superseded; see below.

## The metering premise, in full

ADR-0061's amendment A1 carries the corrected sentence; the argument lives here, by the human's
ruling of 2026-08-06T20:40Z on #221, so that no fact carries its full argument in two documents and
only one of them can go stale.

ADR-0061 Decision 1 originally read "Claude meters **input-equivalents**". That measured the wrong
quantity. This plan meters **generation**. The figures, with their sources: an output token weighs
33.10 points per Mtok of the five-hour window, against under 0.0096 for a cache write and at most
0.0095 for a cache read — a ratio of ≥3,477× against a cache-read token (#218, #220, #237). #218's
control arm is the cleanest single reading: the same 181,253 output tokens moved the five-hour and
seven-day meters by 6 points and 1 point respectively, while 104.6 M cache-write tokens moved the
five-hour meter by zero.

Three things follow, and none of them is a reversal:

- **Decision 1's conclusion is untouched.** Greedy routing with Claude spend as the only optimised
  number stands; only its stated reason was wrong.
- **What counts as a saving inverts.** Compressing input is close to free to begin with, so
  interventions on that class are worth what they are worth on latency and ergonomics rather than on
  spend. Effort, by contrast, is an output-volume multiplier, which is why the default implementation
  tier's drop from xhigh to high is plausibly the largest single spend intervention this project has
  made — and why it registers as approximately nothing when measured in input-equivalents (#220).
- **The ledger's spend column is `cap_fraction`, not dollars** (#232). `claude_code.cost.usage`
  reproduces Anthropic's API list pricing exactly and is anti-correlated with plan cost by roughly
  three orders of magnitude — it modelled $849.76 for a run that moved the plan meter by zero. It
  survives in a row under its own name as a check on the token counters and is not a decision input.

The calibration is carried as `claude/218-2026-08-05` with a per-window `tokens_per_point`,
precisely so that a re-measured rate re-prices the ledger's history rather than invalidating it.

## Why `review` is an eligible seat

ADR-0061's amendment A3 adds `review` to Decision 2's eligible list, which had omitted it while the
same document's Decision 3 admitted it and `SEATS` in `tools/dispatch.py` carried all four. The
reasoning belongs here, by the same 2026-08-06T20:40Z ruling.

Decision 2 is phrased around mechanical gates, so a seat with no gate behind it looks ineligible by
construction. Review is the case where the phrasing and the property come apart. **A review's output
is claims, not commits.** Each claim names a file, a line and a failure scenario, all cheap to check
against the code, and a false finding costs one wasted look — it cannot land anything. The blast
radius is bounded without a gate, which is the property Decision 2 is actually asking for.

Provider diversity is the second half, and it is the one place where a second model is strictly
better than a second run of the same one: different training, different blind spots. Two providers
over one diff is **one review pass with two lenses, not two passes** — CLAUDE.md says so in those
words, because the prohibition on verification passes beyond the gates would otherwise read as
forbidding the second lens.

The asymmetry is stated rather than hidden: false positives are checkable and false negatives are
silent. That is equally true of a Claude reviewer, so the comparison is model-against-model, not
model-against-perfect.

## Every ruling checked against what landed

#221's own overturn condition for Decision 1 is "a ruling being contradicted by what actually
landed, which the ADR-writing pass should surface rather than paper over". Each decision above was
read against the tree at `5ed7417` before it was written down: the `LANES`, `PROFILES` and `SEATS`
registries and the credential and environment handling in `tools/dispatch.py`; `tools/breaker.py`;
`docs/telemetry-ledger.md`; the justfile's `check-secrets` and `check-source-link`; the symlink
itself. The three SHAs named in the ruling table all resolve — `dd3923e`, `f86cba9`, `a885306`.

**No ruling is contradicted by what landed.** Three *premises* have moved since they were ruled on,
and each is recorded here rather than written into the ruling's text as though it had always said
this:

1. **z.ai's quota is machine-readable after all.** The 16:13Z ruling and ADR-0061's held breaker
   bullet both record that z.ai publishes no machine-readable equivalent, so its headroom must be
   estimated from our own dispatch count and always presented as estimated. #275 re-derived a
   first-party endpoint — `GET /api/monitor/usage/quota/limit`, returning `percentage` and
   `nextResetTime` — and `tools/breaker.py` now trips and closes that lane on it. The ledger
   estimator is explicitly barred from tripping or closing anything, on a reason worth keeping: z.ai
   meters prompt counts and the ledger records dispatches, so one dispatch is many prompts and the
   estimate is a lower bound in a unit the cap is not denominated in. The endpoint is absent from
   z.ai's OpenAPI inventory and its response shape has already changed once, so an unfamiliar or
   failed response is no evidence and leaves a held lane held. Decision 8 is untouched: what reaches
   the orchestrator is still a verdict.
2. **The Claude feed is first-party, with the status line as the fallback.** The ruling specified a
   status-line script chaining the existing one and writing `rate_limits` into the breaker's state
   as a side effect. What landed reads `/api/oauth/usage` in a detached single-flight refresh,
   preferring the entry the provider marks `is_active`, with the aggregate status-line pair as the
   fallback and a 429 scheduling the next read at the endpoint's own `retry-after` boundary — never
   at a duration invented here. The ruling's own recommendation is what changed it: it said a polled
   first-party endpoint is the more robust pattern and is the one to prefer wherever a provider
   offers one. The governance weakness it recorded survives verbatim, since the fallback is still
   the human's global status line.
3. **"Compaction" is wording that predates its own ruling.** See Decision 5.

One stale line noticed and deliberately not repaired here: `docs/telemetry-ledger.md`'s known limits
still say "Codex is not yet a lane here at all", while `tools/dispatch.py` has registered `codex`
since `988553b` on 2026-08-06. It is a statement about the ledger's estimator coverage rather than a
ruling, and repairing it is outside this issue's scope, so it is raised on #263 instead.

## What would overturn this

- **Decision 1** — a change to Anthropic's or OpenAI's terms, or a documented first-party route to a
  subscription that is not the vendor's own client. Separately, the narrowed spike (native CLIs
  against `opencode`, non-Anthropic lanes only) returning a result that makes `opencode` the better
  runner for a lane; that would move the substrate without touching the compliance finding.
- **Decision 2** — a provider offering per-request routing that neither needs a session-global base
  URL nor replays a stored credential, which is the pair of constraints this decision rests on.
- **Decision 3** — a quality trip firing on a lane that was serving correctly, which would mean the
  breaker is measuring the diff rather than the provider; or a published reset boundary proving not
  computable, in which case the availability half returns to being unknowable and the lane is
  **held**, never given an invented wait.
- **Decision 4** — a lane whose spend cannot reach the bus at all, which would make the single-bus
  claim false rather than merely incomplete. A lane that is invisible until a pipeline is added is
  the expected case, not the overturning one.
- **Decision 5** — a record loss traced to the collector's `group_by` export, which would put a
  compaction step back; or growth under `~/.arma-cti/dispatches/` that the 30-day prune does not
  bound.
- **Decision 6** — a credential reaching a committed file with `gitleaks` green, or the stated limit
  becoming the live failure: this protects against git, not against an agent running as the same
  user.
- **Decision 7** — nothing. It is discharged, and it is recorded for the reader who asks why two
  providers landed in one week.
- **Decision 8** — an orchestrator decision that a verdict cannot express and a number could, which
  would be the first evidence that #209's rule-table reasoning does not reach this surface.
- **Decision 9** — the symlink failing to load in any lane's toolchain, or a foreign tool that
  follows `AGENTS.md` but not a symlinked `CLAUDE.md`. #221's ruling names the remedy in advance:
  the import returns, with the compaction question as its condition.
- **Correction 1** — a reading of Anthropic's §3 that does not bar automated non-API access, or a
  vendor statement permitting what it appears to bar. The correction is about *why* the substrate is
  what it is, so overturning it reopens the spike rather than the configuration.
- **Correction 2** — Codex's quota endpoint disappearing, or ceasing to be readable before a
  dispatch, which returns the availability half to this project. The four defects that disqualified
  the rejected library are measurements of that library and would be overturned only by it changing.
- **The metering premise** — a re-measurement of the plan's meter, or a plan change. Neither
  invalidates the ledger's history: that is what the calibration id is for.
- **`review`'s eligibility** — a measured false-negative rate materially worse on a foreign reviewer
  than on a Claude one over the same diffs. This needs paired data; a single missed defect does not
  establish it.
