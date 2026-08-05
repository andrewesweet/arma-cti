# What the plan actually charges: the token-efficiency denominator, reconciled

**Researched**: 2026-08-05
**Question** (#220): `docs/research/token-efficiency.md` ranks in **input-equivalents**, multiples of
Anthropic's published base input rate. #218 measured what this Max subscription's plan limits meter,
and it is not that currency. Which number does this project optimise, and what does the ranking look
like in it?
**Answer in one line**: the project runs on **two** cost models and needs both — a **token-flow
view** (input-equivalents, what the work costs a model to process) and a **plan-currency view**
(percentage points of the binding plan window, what the constraint actually charges) — and in
plan currency the sibling document's headline inverts: **everything the model writes is not 4.5% of
the bill, it is on the order of a third of it, and the entire cache-cliff family that document ranks
first, second and third rounds to under 0.7% of the plan meter combined.**

This document is the reconciliation #220 asked for. It does not re-base the sibling; that is the
human's adoption call, and §5 states exactly what is being asked for.

---

## 0. Method, evidence classes, limits

Everything here is arithmetic over three measurements already on the record. No new experiment was
run for this document.

**Sources.**

- **#218** (comment 5190936794) — the plan-meter A/B: 128 byte-identical Claude Code sessions,
  104,588,224 cache-write tokens split ABBA between the one-hour and five-minute TTLs, against a
  positive control of 16 sessions producing 181,253 output tokens. Readout is
  `five_hour.utilization` and `seven_day.utilization` from `https://api.anthropic.com/api/oauth/usage`.
- **#203 / #206** — the transcript census behind `token-efficiency.md`: 208 files, 18,712
  de-duplicated assistant turns, 2026-07-30 to 2026-08-05, with the `cache_creation` TTL split.
- **`docs/research/token-efficiency.md`** — the token-flow model and the standing rankings.

**Evidence class on every claim below**, in the sibling's register:

- **[measured]** — a number read off an instrument that moved.
- **[bounded]** — the instrument did not move; the number is an upper bound at the instrument's
  resolution.
- **[inferred]** — arithmetic over measured quantities plus a stated assumption.
- **[unmeasured]** — named because it is load-bearing and nobody has measured it.

**Instrument and its resolution.** The only plan telemetry this account exposes is integer
percentage of the five-hour and seven-day windows. `limit_dollars` and `used_dollars` are `null`;
the credit meter is disabled with `out_of_credits`. One five-hour point is 30,209 output tokens —
several median agent runs — so **a single dispatch is below the instrument's resolution by two to
three orders of magnitude.** Every per-dispatch number in this project's future will be an
estimator, not a reading. §6 builds the ledger metric around that fact rather than against it.

**Limits worth stating before any of the numbers are used.**

1. **Cache reads were never measured.** #218's arms were single-turn, so `cache_read = 0` in both.
   Reads are 97.1% of this project's raw tokens and 68.5% of its token-flow bill. §3 shows the
   residual analysis bounds their weight *per token* but leaves their **aggregate share of the plan
   meter unresolved between roughly zero and roughly 60%**. This is the single largest open quantity
   in the project's cost model and §7 is the experiment that closes it.
2. **The plan meter is the account's, the transcripts are the project's.** The human uses this
   Claude account for work outside arma-cti. Any share-of-meter figure here therefore has a
   denominator larger than its numerator's scope. Stated per figure where it bites.
3. **Window mismatch.** The project's recorded history is six days; the weekly meter is a rolling
   seven-day window. Treated as equal, which is a ~15% error in the denominator's favour.
4. **Integer resolution on the weekly conversion.** The five-hour weight is anchored on a six-point
   movement (relative resolution ~8%). The five-hour-to-weekly conversion is anchored on movements
   of one and two points, so it carries a factor-of-roughly-two uncertainty. Two independent routes
   are computed in §3 and reported side by side rather than averaged.
5. **What drives the meter is inferred, not established.** §2 shows the data excludes per-request
   and per-session metering, and is consistent with output-token metering. It is equally consistent
   with metering something correlated with output — decode time being the obvious candidate. The
   ranking below does not depend on which, because both make generation the metered act.

---

## 1. Two cost models, and what each one is for

Neither model is wrong. They measure different things, and the sibling document's problem is not its
arithmetic but its label: its §0 states its cost model as measured billing telemetry, and for this
account there is no bill.

| | **Token-flow view** | **Plan-currency view** |
|---|---|---|
| Unit | input-equivalents (multiples of base input rate) | percentage points of the binding plan window |
| Source of the rates | Anthropic's published API price list | measured against this account's plan meter (#218) |
| What it measures | what the work costs a model to process | what the constraint charges the human |
| Answers | "how much context is this shape of work moving?" | "how close is this to the wall we hit?" |
| Correct on | an API key, any per-token bill, and as a latency and context-pressure proxy | this Max subscription, while it is the scarce pool |
| Where it lives | `docs/research/token-efficiency.md` | this document |
| Status of a saving in it | real work avoided; may or may not be spend avoided | spend avoided, in the only currency in which "we ran out" is a sentence |

**Keep both, and say which is which at every ranking.** The token-flow view has four live uses that
the plan-currency view cannot serve:

1. It is the correct model the moment the project touches an API key, and #221's multi-provider
   initiative puts two per-token-ish pools in play (Codex meters credits scaling with tokens; z.ai
   meters prompt counts, which is a third currency again).
2. Context size drives latency. A 320,000-token p90 context is slow to prefill regardless of what it
   is charged, and #195's finding — a blocked turn throws away its prefix and pays wall-clock to
   rebuild it — is a real cost in a currency the plan meter cannot see.
3. Context size drives quality. That is independent of price and is not this document's subject.
4. If the plan is ever exceeded and credits engage, list pricing applies directly. Credits are
   currently disabled on this account, so this is a contingency, not a condition.

What the token-flow view must stop doing is standing in for a spending ranking. That is the whole of
what #220 asks to correct.

---

## 2. The plan-currency cost model

### 2.1 The weights

Percentage points of the **five-hour** window, per million tokens:

| Class | Plan weight (pp₅ₕ / Mtok) | Class of evidence | Basis |
|---|---:|---|---|
| Output | **33.10** | [measured] | 6 points on 181,253 tokens (#218 control) |
| Cache write, 1-hour TTL | **< 0.0096** | [bounded] | 0 points on 52,290,112 tokens |
| Cache write, 5-minute TTL | **< 0.0096** | [bounded] | 0 points on 52,298,112 tokens |
| Cache read | **unresolved** — see §3 | [unmeasured] | never isolated; both arms single-turn |
| Fresh input | **unresolved** | [unmeasured] | never isolated |
| Per request / per session | **0** | [measured] | 128 sessions → 0 points; 16 sessions → 6 points |

Ratios that follow directly:

- **An output token weighs at least 3,462× a cache-write token on this plan** [measured/bounded].
  Under the token-flow view it should weigh 2.5× a one-hour write. Plan accounting departs from list
  pricing by **≥ 1,400×**.
- **The meter is not counting requests or sessions.** The arms made eight times the control's
  sessions and moved the meter zero while the control moved it six. This rules out the most obvious
  alternative to token metering, and it is worth stating because it was not stated in #218: the null
  is a null on request count as well as on cache writes.
- **The only class the control had more of than the arms was output.** The arms pushed ~800 kB of
  prompt through each of 128 sessions — vastly more input of every kind — and emitted two tokens
  each. Generation is the metered act, or is the proxy for whatever is.

Weekly-window weights, for the aggregate arithmetic in §3:

| Class | Plan weight (pp₇d / Mtok) | Basis |
|---|---:|---|
| Output | **5.52** | 1 weekly point on 181,253 tokens (60 → 61 on the control) |
| Cache write, either TTL | **< 0.0096** | 0 weekly points on 104,588,224 tokens |

Five-hour to weekly conversion, for reference: the control gives 6 five-hour points per weekly
point, the whole experiment gives 9 per 2, i.e. 4.5. Both are integer-resolution readings of small
movements. **Take 5 ± 1.5** and treat any figure that depends on it as order-of-magnitude.

### 2.2 One number that needs no denominator

Output volume across the project's recorded history is exact: **3,993,900 tokens** (#203's census).
At the measured weight:

> **3.9939 Mtok × 33.10 pp₅ₕ/Mtok = 132 five-hour-window points.** [measured]

Six days of this project's work generated the equivalent of **4.6 entire five-hour windows'
budget in generation alone**, at a per-token weight known to about ±8%. That figure carries none of
this document's denominator problems. It is what the model wrote, priced in the currency the plan
charges, and it is the number every output-side intervention is a share of.

The corresponding figure for the whole of cache writes — the class the sibling ranks first, second
and third — is **< 0.83 five-hour-window points across the same six days** [bounded]. Not 0.83 per
window: 0.83 in total, for 86,163,009 tokens.

---

## 3. The bill, both ways — and the hole in the middle

Weekly-point arithmetic over #203's census (208 files, 18,712 turns, 2026-07-30 → 2026-08-05),
against a weekly meter observed at 59–61% throughout that span.

| Class | Raw tokens | **Token-flow share** | Plan cost (pp₇d) | **Plan-currency share** |
|---|---:|---:|---:|---:|
| Fresh input | ≈240,000 | 0.05% | ≤ 1.3 [unmeasured] | ≤ ~2% |
| Cache write — 5-min TTL | 68,803,090 | 19.24% | < 0.66 [bounded] | **< 1.1%** |
| Cache write — 1-hour TTL | 17,359,919 | 7.77% | < 0.17 [bounded] | **< 0.3%** |
| Cache read | ≈3.06 B | **68.48%** | **unresolved** | **0 – 62%** [unmeasured] |
| Output | ≈3,993,900 | 4.47% | **22.0** [measured] | **≈ 37%** [inferred] |
| **Observed meter** | | | **≈ 60** | |

The `fresh input` row is priced at the worst assumption available — that it weighs like output — and
is still small. Every other row is derived above.

**The residual.** 60 − 22.0 − 0.8 = **37 weekly points unattributed**. Over 3,060 Mtok of cache
reads that is 0.0122 pp₇d/Mtok, i.e. an output token would weigh **452× a read token**. But the
residual also absorbs the human's Claude usage outside this project, any non-token component of
metering, and the six-day-versus-seven-day window mismatch. **It is a ceiling on reads, not a
measurement of them.**

**A second, independent route to output's share**, with a different error profile: 132 five-hour
points over 28.8 five-hour windows is 4.6 points per window if work were uniform, against meter
readings of 14–23% taken *during* active work. That gives output **20–33%** of an actively-worked
window. It shares no arithmetic with the weekly route beyond the measured per-token weight, and it
lands in the same place.

**So the honest statement of output's share is: a quarter to a half, point estimates 20–33% and
37%, against 4.47% in the token-flow view.** The precision is poor and the order of magnitude is
not in doubt, because the per-token weight is measured to ±8% and the token count is exact. Note
also that the more of the account meter belongs to the human's other work, the *larger* output's
share of this project's own plan bill — the confound pushes the figure up, not down.

### The hole, stated plainly

Cache reads are 68.5% of the token-flow bill and somewhere between nothing and 62% of the plan
bill. Every recommendation whose prize is "put fewer tokens in context" — prefix size, tool-output
volume, deferred loading, redundant re-reads, worktree cache scope — is a claim on that unresolved
term. **They cannot be ranked until it is measured**, and §7 gives the experiment. Two of them can
be resolved anyway, because even the ceiling makes them small; §4 marks which.

The upper end matters. If reads do carry the residual, then halving mean context per turn (166,567
→ 83,284 tokens) would be worth up to **31% of the plan meter** — larger than every intervention in
either document put together. If they do not, it is worth nothing. That is the whole spread, on one
unrun experiment.

---

## 4. Re-ranking the standing recommendations

Four buckets. **Inverts** — the prize was cache traffic and is measured to round to zero.
**Promoted** — the prize is generation and was suppressed by a wrong denominator. **Suspended** —
sits on the unresolved read term. **Unaffected** — grounded in correctness, not currency, and
therefore currency-independent.

### 4.1 Inverts — measured, and the direction is not in doubt

| Sibling item | Token-flow prize | **Plan-currency prize** | What survives |
|---|---:|---:|---|
| §4 #1 Parallelise the pytest tier so `just fast` returns inside the TTL | 2.6% | **< 0.15%** [bounded] | Wall clock: 6 m 17 s → 1 m 44 s, measured. Do it for the six-minute gate, not for the tokens |
| §4 #2 Take agent waits out of the turn | 3.9% | **< 0.22%** [bounded] | Correctness: an agent that has ended cannot stall. #218 §6's own recommendation; ADR-0053's precedent |
| §4 #3 Never hold a turn open past its cache's TTL | 12.89% ceiling | **< 0.68%** [bounded] | The parking half — "do not park work and go quiet" — is a rule about a stalled process, and holds |
| §2's whole two-cliff analysis | the document's headline | ~0 as spend | Correct as a **token-flow** measurement, and it is the best evidence anywhere of how the two TTLs behave. Retired only as a spending finding |
| §6 #4 Simultaneous parallel spawn defeats caching | mechanism, unpriced | ~0 | Nothing. Spawn in parallel freely |
| §6 #3 / §7 Worktree cache fragmentation, `--exclude-dynamic-system-prompt-sections` | unmeasured | ~0 | Retired as a spend question. The one-flag experiment is no longer worth running for cost |
| #204's session-fallback token arithmetic | 1.25× vs 2.0× | 0.0013 points | #218 already made this call: re-base the rule on correctness. This document only agrees |

The pattern: **the cache-cliff family was the sibling's top three findings and it is, in the
currency the human spends, worth under 0.7% of the plan meter in total.** Three of the four items
survive on non-currency grounds and should be kept — but kept for the right reason, and re-argued
rather than re-priced. That is CLAUDE.md's own rule about inherited rationale, applied to a
measurement rather than to prose.

### 4.2 Promoted — the same measurement, read the other way

Nothing in this bucket was ranked in the sibling, because §1's "everything the model writes is 4.5%
of the bill" is an explicit ceiling *against* ranking any of it. That ceiling is wrong here by
roughly eightfold, and the items it suppressed are now the top of the list.

| Intervention | Why it is first-order now | Evidence |
|---|---|---|
| **Reasoning effort as a spend lever.** Extended thinking bills as output tokens; a seat's effort setting is an output-volume multiplier | The one dial that scales the *only* metered class, directly, with no engineering | Vendor-documented for API billing; **[unmeasured] against the plan meter specifically** — §7 names the arm |
| **The seat-default change already taken** (implementer seat xhigh → high, 2026-08-04/05) | Under plan currency this is plausibly the largest single spend intervention the project has made. Under input-equivalents it registers as approximately nothing | [inferred] from the above; volume delta not measured |
| **Fan-out discipline.** N subagents produce N reports | §6 #5's conclusion ("subagents do not save money") survives with its mechanism *replaced*: the cost is N generations, not N cold CLAUDE.md loads | [inferred] |
| **Retry and regeneration discipline.** `--max-turns`, not re-running a red gate blind, not regenerating a report | Every retry is a fresh generation and generation is the whole meter | [inferred] |
| **CLAUDE.md's existing ban on verification passes and verifier subagents** | §6 #15 records it as widely-repeated waste with *no published measurement*, kept as a quality rule. In plan currency a verification pass is pure generation over an already-cached prefix — the most expensive shape of turn there is. It is now a first-order cost rule that happens also to be a quality rule | [inferred] |
| **Terse reports, and the telegraphic register for agent-to-agent prose** | Ranked out by the 4.5% ceiling. At a quarter-to-a-half share it is worth ranking in. Note this is the *opposite* of §6 #10's finding about the caveman register, which measured 8.5% off **output** against an advertised 65% — 8.5% of a third is worth more than 8.5% of a twentieth, and it costs nothing | [inferred] |
| **§4 #7, `rtk gain` — strengthened from "not evidence of saving" to "plausibly net negative."** RTK compresses tool output, which is the near-free class, and JetBrains measured turns **+13.8%** and cache reads **+14.3%** | More turns means more generations. In plan currency a tool that trades output volume for input volume is trading the metered class for the free one, in the wrong direction | [inferred] from the JetBrains measurement; the output-token delta was not itself reported, so this is a mechanism argument, not a measurement |

The general rule this bucket collapses to, and the one sentence worth carrying:

> **On this plan, the project is charged for what it writes, not for what it reads.** Every process
> rule that shortens a generation, removes a generation, or avoids repeating one is spending money.
> Every process rule that shrinks context is buying latency and headroom, and may be buying nothing
> else.

### 4.3 Suspended — awaiting the read arm

These sit entirely on the unresolved read term. Two of them resolve anyway, because even the
residual ceiling makes them small; those are marked **resolved-small** and can be treated as
settled.

| Sibling item | Token-flow prize | Worst-case plan prize (reads carry the whole residual) | Status |
|---|---:|---:|---|
| §4 #4 Prune expired exemplars from `CLAUDE.md` | 0.9% | **≤ 0.46%** | **resolved-small.** Do it for prefix hygiene and readability; it is not a spend item either way |
| §4 #6 Single summary line on green from `just` recipes | 0.18% | **≤ 0.12%** | **resolved-small.** Free to do while editing recipes; never worth an issue |
| §1's amplification model (4.95 input-equivalents per context token; 10.80 for a turn-0 prefix token) | the document's second headline | undefined in plan currency | **suspended.** It is a token-flow quantity by construction and has no plan-currency analogue until reads are weighed |
| §6 #14 Redundant file re-reads (measured here at 0.39% of the token-flow bill) | 0.39% | ≤ ~0.25% | **resolved-small**, by the same arithmetic |
| The whole tool-result surface (#206's correction: 9.35 Mtok of arrival, ≈10% of the token-flow bill) | ~10% | **≤ 6.7%** | **suspended**, and blocked regardless: §5 rejects semantic compression on accuracy, and the median result is 352 characters, so there is no mechanical trim available |
| §6 #8 Deferred tool loading | ~85% off tool schemas | ≤ small | **suspended**, no action. Already on; keep it on. Costs nothing to keep |
| §7 The cost of a subagent's cold `CLAUDE.md` load | unmeasured | ≤ small, and now dominated by that subagent's *output* | **superseded.** §4.2's fan-out row is the same question asked in the right currency |
| **#216** — move three situational `CLAUDE.md` blocks out of the always-loaded prefix | prefix reduction | on the read term | **suspended.** Its case is context-window headroom and prefix hygiene, not spend, and it should be argued that way |
| **Context size in general** (mean 166,567 tokens/turn) | the bulk of the bill | **up to 31% of the plan meter** for a halving | **suspended, and this is the one that matters.** §7 |

### 4.4 Unaffected — correctness-grounded, currency-independent

Nothing in this bucket moves, and nothing in it should be re-argued.

- **§5, semantic compression of code or context in the tool path.** Rejected because compression
  destroys verbatim edit anchors — SWE-bench-Go patch application 27/40 → 15/40 — and this project's
  edits go through `Edit` with exact-match `old_string`. Unaffected. It now *also* buys at most the
  read term, which strengthens an already-sufficient case.
- **§5, token-optimised serialisation (TOON, TRON).** Rejected for trading 9–14 points of accuracy
  for 18–27% of tokens. Unaffected, and the tokens it trades for are the near-free class.
- **§5, chasing raw token counts.** Unaffected, and its reasoning strengthens: raw counts were
  misleading under input-equivalents because 97.1% of them are reads billed at a tenth; under plan
  currency they are misleading because 99.9% of them are reads and writes charged at under 1/450th.
- **§4 #5, batch human questions to session boundaries.** 0.10% either way. Survives on wall-clock
  and on the human's attention, which is what it was always really about.
- **The gates.** Corpus, `just fast`, criterion audits, retro cadence. #195's scope bar — a saving
  that degrades a gate is out of scope — is untouched, and every row in both documents still clears
  it.
- **The loop inventory L1–L15**, where the item is hygiene rather than tokens: L14's two-line
  `.gitattributes` (`merge=union` on `CHANGELOG.md`), L4's worktree pre-flight, L6's ADR-number
  scanner. L1's *pricing* moves to §4.1; L1's reason for existing — a stalled agent is not noticed —
  does not.
- **§0–§3 of the sibling as measurements.** The census, the TTL split, the two cliffs, the
  attribution of blocking calls, the RTK and community evidence classes. Every one of them is still
  a correct statement about token flow. Only their use as a spending ranking changes.

### 4.5 The summary table #220 asked for

| Verdict | Count | Items |
|---|---:|---|
| **Inverts** (measured) | 7 | §4 #1, #2, #3; §2's cliff analysis as spend; §6 #4; §6 #3 / §7 fragmentation; #204's token arithmetic |
| **Promoted** (measured weight, inferred application) | 7 | effort as a lever; the seat-default change; fan-out discipline; retry discipline; the verification-pass ban as a cost rule; terse output; `rtk gain` strengthened to net-negative |
| **Suspended** (needs the read arm) | 4 | the amplification model; the whole tool-result surface; deferred loading; context size in general — plus #216 |
| **Resolved-small** (bounded below 0.5% regardless) | 3 | §4 #4 prune; §4 #6 one-line-on-green; §6 #14 re-reads |
| **Unaffected** (correctness-grounded) | 6 groups | §5 ×3; §4 #5; the gates; the hygiene half of L1–L15 |

---

## 5. What is being asked of the human

The reconciliation above is a measurement, and needs no ruling. Three things do.

1. **Does `token-efficiency.md` §4 get re-ordered, or does it keep its ranking with a currency
   label?** This document's recommendation is the latter — the sibling stays a token-flow document,
   labelled as one, and this document carries the plan-currency ranking. Two documents, two
   currencies, each saying which it is, is #220's candidate 1. Re-ordering §4 in place would destroy
   the token-flow ranking, which is still the right one on an API key and for latency, and #221 puts
   two per-token pools in play within the week.
2. **Do the four `[inferred]` promotions in §4.2 become process guidance?** Effort discipline,
   fan-out discipline, retry discipline, and re-basing the verification-pass ban as a cost rule.
   These touch `CLAUDE.md`, which is a sign-off gate. Note that the strongest of them — the effort
   default — has already been taken by the human's own seat mapping on 2026-08-05, so this would be
   recording a rationale for a decision already made rather than proposing a new one.
3. **Does the read arm (§7) run?** It is the largest unresolved quantity in the project's cost model
   and the cheapest remaining experiment. It also decides whether #216 and the whole context-size
   family are worth engineering.

#218 is sitting `ready-for-human` on the adoption call for the same measurement. These are one
decision, not two.

---

## 6. The dispatch ledger's metric, for ADR-0061 Decision 1

D1 says the three subscriptions do not share a currency, that Claude spend is the only quantity
optimised, and that telemetry records fraction-of-cap for all three from the first dispatch so the
rule can be *replaced* by scarcity routing rather than reopened. #220's answer must agree with it.
It does, and it sharpens it: **fraction-of-cap is the right commensurable, and this document says
what goes into it on the Claude side.**

### 6.1 The metric

**`cap_fraction` — percentage points of a pool's binding window cap, per dispatch.** Dimensionless,
a share of a scarce refilling budget, and the only quantity that means the same thing on a pool
metering input-equivalents, a pool metering credits, and a pool metering prompt counts.

Every pool has at least two windows. Record all of them and mark which one **bound** at dispatch
time — the one nearest exhaustion. Scarcity routing, when D1 is eventually replaced, routes on the
binding window, not on an average.

### 6.2 Two numbers per pool, never one

| Field | What it is | Why both are needed |
|---|---|---|
| `cti.cap_fraction.observed` | the meter delta across the dispatch, from #226's quota feed | Ground truth, but integer-resolution: one Claude point is 30,209 output tokens, several median agent runs. A single dispatch reads **0** almost always. Useful in aggregate and for calibrating the estimator; useless as a per-dispatch cost |
| `cti.cap_fraction.est` | the estimator, computed from the dispatch's own counters | The ledgerable per-dispatch number. Everything the ledger is for — "what did dispatch D on issue #N cost" — is this field |

Recording only `observed` gives a ledger of zeroes. Recording only `est` gives a ledger nobody can
check. Recording both makes the estimator falsifiable against the meter over N dispatches, which is
the only validation available at this resolution.

### 6.3 The per-pool estimator

| Pool | Estimator | Basis | Confidence |
|---|---|---|---|
| **Claude** | `output_tokens / 30,209` points of the five-hour window; `output_tokens / 181,253` of the seven-day | `output_tokens` — **not** input, **not** cache | `measured`, with `excludes = ["cache_read"]` until §7 runs |
| **Codex** | `credits_consumed / window_credit_cap` | provider publishes `usedPercent` first-party, so `observed` and `est` converge; `est` from `codex.turn.token_usage` × the credit conversion | `measured` once the conversion is read off a real run |
| **z.ai** | `prompt_count × tod_multiplier / window_prompt_cap` | prompt counts, token-independent by construction | `estimated`, always — #226 already rules this, and no machine-readable state exists |

The Claude row is this document's contribution to the ledger and the thing #220 exists to settle:
**a Claude dispatch's plan cost is its output token count, divided by a measured constant.** Input
volume, context size and cache behaviour do not enter it — not because they are free in principle,
but because they are measured at under 1/450th the weight and the residual that could change that is
named in `excludes` rather than silently assumed away.

If the z.ai lane does meter purely by prompt count regardless of context size — #221 carries this as
an open unknown — then that lane's economics are the exact opposite of Claude's: a fat context is
free and a chatty agent is expensive on Claude, while a fat context is free and a chatty agent is
*also* free on z.ai, with only the turn count charged. The ledger reads that off the same schema
without a special case, which is the point of choosing fraction-of-cap over tokens.

### 6.4 What the record must carry so the estimator can be re-derived

Every constant above is a calibration and every calibration will move — a plan change, a model
change, or §7's read arm adding a term. The ledger must therefore carry the inputs, not just the
output:

- raw counters: `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens` split
  by TTL, `request_count`, `prompt_count`
- `cti.profile` — the opaque `(lane, model, effort)` token of ADR-0061 D5. Effort belongs here for a
  reason this document supplies: it is an output-volume multiplier, so it is a **cost** dimension on
  this plan and not only a quality one
- `cti.cap_fraction.calibration_id` — which conversion was applied, e.g. `claude/218-2026-08-05`
- wall clock, and the window boundaries in force

A recalibration then **re-derives history rather than invalidating it.** Without
`calibration_id`, the first plan change silently rewrites every past number in the ledger.

### 6.5 Three things the metric must not do

1. **Must not use `total_cost_usd`.** Claude Code's client-side cost figure reproduces API list
   pricing exactly — #218 recovered the whole rate card from it — and it modelled **$849.76** for a
   run that moved the plan meter zero. It is a token-flow number wearing a currency symbol, and a
   ledger that records it as "cost" will rank every future decision the way the sibling document
   does.
2. **Must not infer "no plan cost" from "the meter did not move."** #218's third confound: 28.6 M
   tokens of raw `/v1/messages` traffic on the same OAuth credential moved the meter zero, verified
   with a four-minute poll, while a `claude -p` batch minutes later moved it. Meter silence is not
   evidence of free, and it is exactly the shape a mis-wired lane would produce.
3. **Must not attribute a foreign-lane dispatch a Claude cost of zero by construction.** The
   orchestrator's own turns — composing the briefing, reading the report, quoting the verdict — are
   Claude output, and under §2 output is the whole of what Claude charges. If they are not
   attributed to the dispatch that caused them, the saving from routing work off Claude is
   overstated by precisely the term that decides whether routing is worth it. #227 already records
   that `cti.dispatch_id` cannot reach an in-session subagent, since it shares its parent's resource
   block; the same limit applies here and must be **recorded as a known under-attribution**, not
   left implicit. Concretely: the ledger should carry `cti.cap_fraction.attribution =
   "dispatch_only"` so a later reader knows the orchestrator's share is missing rather than zero.

### 6.6 Where this lands

The attribute names and the ledger schema are #227's surface, not this document's. This section is
handed there by comment. The one thing that is *not* #227's to decide, and is settled here, is the
Claude estimator's basis: **output tokens, on a measured constant, with cache reads named as an
exclusion.**

---

## 7. The one experiment that closes this

**A multi-turn cache-read arm on #218's harness.** #220's body already names it; this document
prices the design.

**Design.** One main Claude Code session (one-hour TTL, so the prefix survives the run), a prefix of
roughly 165,000 tokens matching this project's mean context, then ~1,000 turns each appending a
trivial delta and replying with one word. Cache reads ≈ **165 Mtok**. Output ≈ 2,000 tokens, which
is 0.07 five-hour points — negligible against the signal. Poll `/api/oauth/usage` at block
boundaries only; it rate-limits at roughly one read per minute (#218's fourth confound).

**Discrimination.**

| Hypothesis | Predicted five-hour movement over 165 Mtok of reads |
|---|---:|
| Reads carry the §3 residual (0.061 pp₅ₕ/Mtok) | **≈ 10 points** |
| Reads weigh like cache writes (< 0.0096 pp₅ₕ/Mtok) | **≤ 1.6 points** |

A movement of ≥ 5 points says reads are a first-order term and the whole context-size family comes
straight back to the top of the ranking. A movement of ≤ 2 points says the residual is elsewhere —
the human's other work, or a non-token component — and **output is essentially the whole of what
this plan charges**, which would make §4.2 the entire ranking.

Either result is decisive, the arm costs about ten points of one five-hour window, and the harness
already exists.

**A second, cheaper arm worth naming while the harness is warm**: fresh (uncached) input was never
isolated either, and §3 prices it at the worst available assumption. Same shape, uncached prefix,
one turn each.

**A third, if the effort promotion in §4.2 is to be more than an inference**: two otherwise identical
sessions at two effort levels, comparing output token volume and meter movement. That measures the
lever the seat mapping already pulled.

---

## 8. Regime boundary

**Everything in this document describes a Max subscription's plan limits.** On an API key the
published list model applies, `token-efficiency.md` is right as written, and the cache-cliff family
returns to the top of the ranking with its full 12.89%. The two documents are not in conflict; they
describe two regimes, and this project is currently in one of them.

Three conditions would move it:

- **Credits engaging.** Currently disabled (`out_of_credits`), and #203's census confirms the
  documented over-limit fallback has never fired in this project's history. If credits are ever
  enabled and the plan is exceeded, list pricing applies to the overflow and both models are live at
  once.
- **A lane that is not Claude Code.** ADR-0061's held mirror ruling permits the `claude` binary to
  drive a non-Anthropic endpoint. That consumes no Anthropic quota, so its Claude `cap_fraction` is
  genuinely zero — but it may cost real money on the foreign pool under that pool's own model, which
  is why §6 makes `cap_fraction` per-pool rather than global.
- **A plan change.** The constants in §2 are calibrations of one account on one date.
  `calibration_id` in §6.4 exists for this.

---

## 9. What this document does not claim

- It does not claim the sibling is wrong. Every measurement in it stands; only its use as a
  spending ranking changes.
- It does not claim to have measured cache reads. §3 gives a ceiling from a residual, and a ceiling
  derived from a residual absorbs every confound in the system.
- It does not claim the plan meters output tokens *as such*. It claims generation is the metered
  act, that request count and cache traffic are excluded at the instrument's resolution, and that
  output tokens are the best available proxy for whatever the underlying quantity is.
- It does not claim the promotions in §4.2 are measured. Their **weight** is measured; their
  **application** — that a lower effort setting or a shorter report reduces output volume by an
  amount worth having — is inference, and §7's third arm is how it stops being one.
- It does not forecast. Every share here is a share of six days of one project's history under one
  workload mix.
