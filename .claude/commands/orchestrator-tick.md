---
description: One orchestrator cycle — harvest finished dispatches, land what is ready, refill WIP, report only what changed.
---

Orchestrator tick. Act; do not wait for the human.

## 1. Harvest

For every dispatch finished since the last tick, do the orchestrator's half — the half a
dispatched session cannot do for itself (#393):

- Read its result and its report.
- Push its branch and archive its tree. A slot held by finished work is what silently caps WIP.
- Post the report to the issue, record the verdict with `just review record`, file every
  finding of `medium` and below as its own issue, and adjudicate each one
  `accepted_and_filed` with the work its harm is conditional on.

## 2. Land

If a branch is gated, reviewed and adjudicated, land it and close its issue with what landed,
who reviewed it, and what was filed rather than fixed.

**One landing at a time.** Each push rebases every other branch, so a second landing started in
parallel orphans the first branch's verdict. Restage, exchange, review, verdict, land — in that
order, for one branch, before starting the next.

## 3. Refill to the limit — currently **two**, and that is deliberate

Lane order of preference: **zai, then codex, then claude-native** (human, 2026-08-19).

Preference chooses among admissible lanes; it never overrides a refusal. Still binding: the
cross-lane rung on class-6 paths, the off-peak rule on zai (#238), the breaker, and the routing
policy. Codex cannot take the implementer seat until #405 lands.

Sweep finished trees before concluding the limit is reached — the counter reads worktrees, not
running sessions.

**Why two.** Landing is serial and each landing forces every other banked branch to rebase, so rework is
O(N) in the number banked while completion stays at one. Branches decay while they wait: today the ones
landed within the hour replayed clean, the ones thirty commits behind cost a rebase dispatch each, and
one at forty-three was judged unsalvageable. **Stop starting, start finishing.**

**One standing exception:** work that removes the coupling keeps a slot regardless — #358 (per-branch
changelog fragments), #421 (one predicate for both brief paths), #426 (the cross-lane preference). Those
are the constraint, not inventory.

**The limit returns to five when #358 lands**, because parallel branches then stop colliding on the
hottest shared file and the parallelism becomes real rather than nominal.

## 4. Priority

1. **#417 → #416 → #405** — the chain that ends with Codex able to take all work.
2. **#358**, **#353**, **#393** — the remaining throughput levers.
3. The banked branches, disjoint surfaces first.
4. The records and correctness backlog.

Re-rank if the evidence says so, and say so in the tick rather than re-ranking quietly.

## 5. Two reviews per landing, and the cap changes the work

`medium` and below are filed and the branch lands; `critical` and `high` go back **once**
(#217, human rulings of 2026-08-18 and 2026-08-19). Two reviews total — not one per finding.

**At the cap with a `critical` or `high` outstanding, a third patch is not an option.** The
branch takes one of three routes: delete or simplify the thing being defended; narrow the
claim to something provably sound and file the remainder; or park and escalate.

**Earlier trigger, worth more than the cap:** when round two finds the *same class* of defect
as round one, stop patching and question the requirement. #405 spent four rounds on one class
— a check comparing a token rather than the thing — and ended by deleting what was being
defended. #417 the same. Two instances of a class is evidence about the design.

Take rulings under the human's standing authorisation, record them where they bind, and do
not park work waiting for a turn.

## 6. Report briefly

- Something landed, was filed, or needs a decision: a few lines.
- Nothing changed: **one line** — `no change — <what is running>`.
- Never re-send a full status unless asked for one.

## 7. Escalate at once, not at the end of the tick

A gated sign-off you cannot take; a `critical` that recurs on the same branch; a provider quota
or breaker trip; a refusal you cannot route around.
