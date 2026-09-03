# Frozen baseline for the self-review pipeline experiment

**Frozen 2026-08-26T07:22:37Z.** This is the pre-pipeline baseline #588's evaluation rule compares
against, and #602 recomputes. It is recorded as a dated act rather than as figures in a spec,
because every figure below has moved while being quoted: the corpus went from 691 dispatches on
22 August to 938 on 26 August, and the return rate fell from 0.642 to 0.572 over three days.

## Method

Every `dispatch.json` under the dispatch root, sorted by `planned_at` within its issue, reduced to
a seat sequence over `implementer` and `review`. Timings come from each dispatch's `result.json`.
Nothing here reads the telemetry ledger, so nothing here is affected by #525's Codex fault.

## The figures

| | value |
|---|---|
| dispatches | 938, spanning 2026-08-05 to 2026-08-26 |
| issues with implementer or review work | 243 |
| issues that reached review | 162 |
| implementer dispatches | 504 (2.074 per issue) |
| review dispatches | 391 (1.609 per issue) |
| handoffs (I→R) | 334 |
| returns (R→I) | 191 |
| **return rate *p*** | **0.5719** |
| **λ**, where *p* = 1 − e^(−λ) | **0.8483** |
| reviews per issue that reached review | 2.4136 |
| clean `IR` fraction | 48 / 162 = 0.2963 |

### The rework loop is close to memoryless

Under a geometric model with return probability *p*, expected reviews per reaching-issue is
1/(1−*p*) = 2.3357, against 2.4136 observed — a **+3.23% residual**.

| reviews | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | ≥10 |
|---|---|---|---|---|---|---|---|---|---|---|
| observed | 61 | 45 | 27 | 9 | 10 | 5 | 2 | 1 | 1 | 1 |

The practical consequence: an intervention's effect is expressible as a change in one parameter.
The −20% consumption target requires *p* ≈ 0.465, which by λ requires the self-review to remove
**about 26% of the findings the independent reviewer would otherwise raise**. That is a
per-finding quantity, which is why the leading indicators in #588 reach a verdict in tens of Work
Items where the lagging one needs roughly 190.

**A break in this relation is itself a finding.** If reviews-per-issue and *p* stop agreeing after
the pipeline lands, the intervention changed the mechanism rather than the rate, which is more
informative than a moved mean and shows up in distribution shape sooner.

### Cycle time and process cycle efficiency

Over 179 issues with two or more timed dispatches: median cycle 1.65 h, median touch 0.80 h.

| PCE | p25 | median | mean | p75 |
|---|---|---|---|---|
| touch ÷ cycle | 0.197 | **0.640** | 0.539 | 0.808 |

**This is an upper bound.** Cycle time here runs from the first dispatch's start, so the queue
before work begins is invisible; #380 gaining a became-ready timestamp is what would close that.

The median Work Item is work-dominated, which is the opposite of the usual lean picture and was
not what I predicted. The bottom quartile at 0.197 is where the waiting lives, and the mean cycle
time being four times the median says the same thing: **the tail carries the loss, not the
average.** Interventions aimed at the median will not find it.

### Stock levels at freeze

| stock | level |
|---|---|
| worktrees owing `just worktree done` | **17** |
| dispatches with no materialised ledger row | **160 of 938** |

The worktree stock deserves the same kind of note. `just loop-metrics` now derives it locally
(#672): every registered worktree whose name carries an issue number (`issue-N`, `review-N…`)
counts when a ledger row attests `gate=landed` for that issue. The level is a proxy for the
tracker's answer, and the report discloses every way that proxy can err — landings invisible
for want of a materialised ledger row, issues closed without a landing, issues landed but not
yet closed, issues reopened after landing, and, for a past window, registrations that changed
since the boundary — while claiming no single net direction. The frozen **17** above was
measured before this derivation existed, so it is not directly comparable to the reader's
figure.

The ledger stock deserves a note. It held 6 rows on 22 August and 778 on 26 August — drained by a
sync run on 23 August — but the newest row is from that date, so it has been refilling at roughly
64 a day since. That is the difference between materialisation as an act and as a flow, observed
rather than argued. And the rows that exist were computed before #526 lands, so the Codex ones
carry that fault while looking authoritative.

## Setpoints

Ruled by the human on 2026-08-26. A level with no target is a number someone has to judge; a level
with one is a variance that can be alarmed on. These are policy rather than anything derivable,
and they are revisable — recorded here because #602 reports every level against its setpoint where
one is ruled, and nothing else in the repository holds them.

| stock | setpoint | alarm |
|---|---|---|
| worktrees owing `just worktree done` | 0 | 3 |
| dispatches with no materialised ledger row | 0 | 20 |
| unratified provisional terms | 0 | 5 |
| open findings per Work Item | ≤ 2 | — |
| ready Work Items | ≥ 3 | below 3 |

The last is a floor rather than a ceiling: coordination starving is as much a fault as coordination
overloading, and only one of the two is currently visible.

Two of these are already breached at freeze — worktree debt at 17 against an alarm of 3, and
unmaterialised ledger rows at 160 against an alarm of 20.

## A prediction, recorded while it is still falsifiable

The stocks-and-flows reading says throughput is currently bounded by the WIP limit and by the
worktree stock, not by capability. Clearing that stock frees WIP, throughput rises, and the
bottleneck migrates. **The prediction is that it migrates in this order:**

1. **Lane capacity** — the z.ai off-peak window and per-lane quotas.
2. **Human attention** — sign-off gates, Product Questions, rulings.
3. **Gate wall-clock** — the serial cost of `just fast` per landing.

Recorded now because a prediction written after the observation is a rationalisation. What would
falsify it: throughput rising after the worktree stock clears without any of the three binding, or
one of them binding in a different order.

## What this baseline cannot support

It is one project, one operator, and a corpus that grows under measurement. The geometric fit is a
good fit on one dataset, not a validated law. The PCE figure excludes a queue it cannot see. None
of the thresholds in #588 are derived from any of this — they are targets, and the detection floor
recorded there says plainly that the lagging one needs roughly 190 Work Items to confirm.
