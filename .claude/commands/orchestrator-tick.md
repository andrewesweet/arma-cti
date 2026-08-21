---
description: One orchestrator cycle — harvest finished dispatches, land what is ready, refill WIP, report only what changed.
---

Orchestrator tick. Act; do not wait for the human.

Every rule below cites where it was taken. A sentence here with no citation is not a ruling; treat it as description, and if it conflicts with the code, the code wins and this file is wrong.

## 1. Harvest

For every dispatch finished since the last tick, do the orchestrator's half — the half a
dispatched session cannot do for itself:

- Read its result and its report.
- **Exchange its branch** with `just review exchange <issue>`, and retire its tree. A slot held by
  finished work is what silently caps WIP. Exchange is the operation; "push the branch" describes
  neither what the recipe does nor what the reviewer needs (`tools/review_exchange.py`).
- Post the report to the issue, record the verdict with `just review record`, file every
  finding of `medium` and below as its own issue, and adjudicate each one
  `accepted_and_filed --filed-issue <n> --conditional-on <n>` — the route names the issue it filed,
  and refuses without it (`tools/review_loop.py`).

**A review seat may be unable to post.** The seat is forced into `permission_mode="plan"`
(`tools/dispatch.py`'s `SEATS`), and a lane without `ExitPlanMode` completes the review and cannot
comment. Read the run's report before concluding a reviewer went quiet, and post on its behalf.

**Reviewers are passed test reports; they do not re-run the suite** (#353, and the human's ruling of
2026-08-20). They may land review-specific gates and post their own findings. The wall-clock cost of
a re-run is the reason. Do not brief a reviewer to run the gate.

## 2. Land

If a branch is gated, reviewed and adjudicated, land it and close its issue with what landed,
who reviewed it, and what was filed rather than fixed. The close must carry a criterion-by-criterion
audit naming `just check`, `just unit` and `just mutation`; the rung refuses the close without one
(#461, `tools/land.py`'s `AUDIT_MARKERS`).

**A verdict survives a clean rebase** (#417). `just land` and `just land --stage` record the rebase,
and an earlier verdict carries to the moved commit when the recorded chain reaches it and the diff's
exact identity still matches. A fresh review is owed when that proof fails — a hand-resolved replay,
or a binary diff, which is not carried. So a second landing does **not** automatically orphan another
branch's verdict, and restaging every branch after every landing is work this rule already removed
(`docs/review-dispatch.md:358-372`, `tools/land.py:990-1018`).

**Landing does not free a WIP slot; retiring the worktree does.** A landed tree still counts.

## 3. Refill to the limit

The limit is **five in flight, any lane** — the human's ruling under the #284 stage-1 experiment.
It is not restated here as a number to be maintained: read it from `just queue state`, which holds
the live policy and its ruling text.

Lane order of preference: **zai, then codex, then claude-native** (human, 2026-08-19).

Preference chooses among admissible lanes; it never overrides a refusal. Still binding: the off-peak
rule on zai (#238, no override), the breaker, and the routing policy.

**The cross-lane rung is a preference, not a bar** (#426). `just land` prints `gate_review=` and
refuses only on `review_lane_unknown` or `gate_class_undetermined`. Reading it as a bar parks
branches that are landable.

**Every seat is open to every lane.** Codex heads the implementer preference
(`tools/dispatch.py`'s `IMPLEMENTER_PREFERENCE`, `codex-luna-max` first).

**The in-flight count reads worktrees *and* dispatch records** — `queue_policy.gather` derives it
from both, minus closed issues. A finished dispatch whose record has no result still counts, so
sweeping trees alone will not explain a `wip_reached` refusal.

**Read each issue's routing block.** Recent issues carry a `cti.dispatch-plan/1` comment naming the
seat, lane and profile per stage and the escalation triggers. `just dispatch` does not read it yet
(#463); until it does, honour it by hand.

## 4. Priority

1. The correctness backlog, defect-class first: #458's class — a check comparing a token rather than
   the thing — has ten recorded instances and three candidate escapes.
2. #353 and #393, the remaining throughput levers.
3. The banked branches, disjoint surfaces first. Re-implement rather than rebase once a branch is
   tens of commits behind: measured on #340, #342 and #349.
4. The records backlog.

Re-rank if the evidence says so, and say so in the tick rather than re-ranking quietly.

## 5. Two reviews per landing, and the cap changes the work

`medium` and below are filed and the branch lands; `critical` and `high` go back **once**
(#217, human rulings of 2026-08-18 and 2026-08-19). Two reviews total — not one per finding.

**At the cap with a `critical` or `high` outstanding, a third patch is not an option.** The
branch takes one of three routes: delete or simplify the thing being defended; narrow the
claim to something provably sound and file the remainder; or park and escalate.

**A false claim in a shipping artefact is worth breaking the cap for**, and has been, repeatedly. A
changelog fragment is read as a claim, not as prose (ADR-0077, #460), and every sentence in it must be
true of the code as merged. The same standard applies to a docstring that states a floor and to a
close table that summarises decisions: five landings were blocked on this in one session, each on a
sentence that was nearly true.

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

**A refusal inside a chained command is not noise.** Read every line a command prints before acting
on any of it: a `refusal=` filtered past has dispatched a reviewer onto the wrong commit.
