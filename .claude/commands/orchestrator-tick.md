---
description: One orchestrator cycle — harvest finished dispatches, land what is ready, refill WIP, report only what changed.
---

Orchestrator tick. Act; do not wait for the human. *(This file's own convention; no ruling behind it.)*

**Where this file and the code disagree, the code wins and this file is wrong.** Citations below name the ruling or the implementing path where one is known. Three review rounds each found the previous version's citation promise false in a different way — rules with no citation, citations to sources that did not state the rule, and citations to a ruling's worked examples rather than to the ruling. Treat a citation as a lead to check, not as proof that the rule is recorded. Most of the orchestration rulings here are #217's. Making the file reliably distinguish a recorded ruling from its own convention is #474; until that lands, this file does not promise it.

## 1. Harvest

For every dispatch finished since the last tick, do the orchestrator's half. **These acts belong to the seats that own them, not to every completion**: exchange belongs to a dispatch that produced a branch, and a verdict is derived only from a completed `seat=review` dispatch (`tools/review_exchange.py:10-26,210-218`; `derive_binding` at `:757-845`).

- Read its result and its report.
- **Exchange its branch** with `just review exchange <issue>` (`tools/review_exchange.py`), and retire its tree when the issue is closed. "Push the branch" describes neither the recipe nor what the reviewer needs.
- Post the report to the issue, record the verdict with `just review record`, file every finding of `medium` and below as its own issue, and adjudicate each with `just review-loop adjudicate --route accepted_and_filed --filed-issue <n> --conditional-on "<the work outside the diff the harm depends on>"` (#217 for the policy that every `medium` and below is filed; `tools/review_loop.py:549-562,1431-1440` for the argument validation). `--filed-issue` is required. **`--conditional-on` takes a description, not an issue number** — any non-empty string passes, so a number there writes a semantically empty adjudication that still clears the rung.

**Reviewers are passed test reports and do not re-run the suite** (#353, clarified by #449). They post their own findings. A reviewer that identifies a needed gate **proposes** it; the review seat is `lands=False` under forced plan mode and cannot land it (`tools/dispatch.py:811-814`), so an implementer lands it on its own issue.

**If a reviewer reports it could not post, relay for it** — but only on an observed refusal (`docs/review-dispatch.md:139-173`). Both runner families do post from forced plan mode; absence of `ExitPlanMode` is not evidence that `gh issue comment` is unavailable. Two runs on #455 this session (`d-20260821-012423-2f47dd`, `d-20260821-015701-05d3f8`) ended with the review written to a plan file and unposted; that is the observed case this covers, not a standing expectation.

## 2. Land

If a branch is gated, reviewed and adjudicated, land it and close its issue with what landed, who reviewed it, and what was filed rather than fixed. The close needs a criterion-by-criterion audit in **one comment** naming `just check`, `just unit` and `just mutation`; the rung refuses `audit_absent` without it (#461, `tools/land.py`'s `AUDIT_MARKERS`).

**A verdict survives a clean rebase** (#417). `just land` and `just land --stage` record the rebase, and a verdict carries to the moved commit when the recorded chain reaches it and the diff's exact identity matches. A hand-resolved replay or a binary diff does not carry (`docs/review-dispatch.md:358-372`, `tools/land.py:990-1018`). So a second landing does not automatically orphan another branch's verdict.

**Occupancy is by issue, not by tree.** `queue_policy.derive_in_flight` unions issue worktrees with unfinished dispatch records, then drops every issue GitHub reports closed. A successful `just land` normally closes the issue. So a **landed-but-open** issue still occupies a slot; closing it releases the slot and leaves the tree as `worktree_done_owed`, which retirement then clears.

## 3. Refill to the limit

Read the limit and its ruling from `just queue state` — it holds both, and a number copied into this file goes stale silently. The ruling recorded there is the orchestrator's of 2026-08-19, taken on the human's standing authorisation, because #358 landed and the throttle's exit condition was met. (#284's own closing ruling says "WIP 3 remains in force" and closes that experiment as superseded; it is not the current authority.)

Lane order of preference: **zai, then codex, then claude-native** (#217, human instruction of 2026-08-19).

Preference chooses among admissible lanes; it never overrides a refusal (#217). Still binding: the off-peak rule on zai (#238, no override), the breaker, and the routing policy.

**The cross-lane rung is a preference, not a bar** (#426). On that rung specifically, lane coincidence no longer refuses; unknown lane or gate class still does — `review_lane_unknown`, `gate_class_undetermined`. Every other refusal in `tools/land.py:110-179` stands, including the absolute `review_same_profile`.

**Codex may take the implementer seat**: `IMPLEMENTER_PREFERENCE` heads with `codex-luna-max` (`tools/dispatch.py:708`). This is not a general rule about seats — `orchestrator` is the sole `claude_only=True` row (`tools/dispatch.py:858`, ADR-0071 ruling 1).

**Read each issue's routing block.** Recent issues carry a `cti.dispatch-plan/1` comment naming seat, lane and profile per stage with escalation triggers. `just dispatch` does not read them yet. #463 records them as advisory and leaves the treatment open — honour the block, refuse a contradiction, or proceed with a printed departure are all live options on that issue. Honouring by hand is this file's convention pending that decision, and is not #463's ruling.

## 4. Priority

1. The correctness backlog, defect-class first: #458's class — a check comparing a token rather than the thing — records eight instances in its body and a ninth in #470, with three candidate escapes.
2. #353 and #393, the remaining throughput levers.
3. The banked branches, disjoint surfaces first. Judge rebase against re-implementation per branch on how far behind it is and what it touches; #340, #342 and #349 are the open cases and record no threshold.
4. The records backlog.

Re-rank if the evidence says so, and say so in the tick rather than re-ranking quietly.

## 5. Two reviews per landing, and the cap changes the work

`medium` and below are filed and the branch lands; `critical` and `high` go back **once** (#217, human rulings of 2026-08-18 and 2026-08-19). Two reviews total — not one per finding.

**At the cap with a `critical` or `high` outstanding, a third patch is not an option** (#217). The branch takes one of three routes: delete or simplify the thing being defended; narrow the claim to something provably sound and file the remainder; or park and escalate.

**A changelog fragment is read as a claim, not as prose, and every sentence in it must be true of the code as merged** (ADR-0077, #460). ADR-0077 records five false fragments found, of which three blocked a landing.

**Earlier trigger, worth more than the cap** (#217)**:** when round two finds the *same class* of defect as round one, stop patching and question the requirement. #405 and #417 are that ruling's worked examples, not its source: #405 spent four rounds on one class and ended by deleting what was being defended. Two instances of a class is evidence about the design.

Take rulings under the human's standing authorisation (#217), record them where they bind, and do not park work waiting for a turn. That authorisation does not displace ADR-0013: a delegated gated decision goes into a marked ADR.

## 6. Report briefly

- Something landed, was filed, or needs a decision: a few lines.
- Nothing changed: **one line** — `no change — <what is running>`.
- Never re-send a full status unless asked for one.

## 7. Escalate at once, not at the end of the tick

A gated sign-off you cannot take; a `critical` that recurs on the same branch; a provider quota or breaker trip; a refusal you cannot route around.

**Preserve typed refusals and exit status when chaining commands.** A `refusal=` line filtered out of a chained command's output on 2026-08-21 dispatched a reviewer onto a stale tree (`d-20260821-015246-9e1696`, stopped before it reported). Check the operation's own result — the tree's HEAD, the recipe's exit code — rather than the presence of a success line. *(This file's convention, from that incident; no ruling behind it.)*
