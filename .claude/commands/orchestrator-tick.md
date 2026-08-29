---
description: One orchestrator cycle — harvest finished dispatches, land what is ready, refill WIP, report only what changed.
---

Orchestrator tick. Act; do not wait for the human — and **hold the waits this seat is for**. Ending a turn mid-wait is the subagent's rule and does not apply here (`docs/agents/orchestration.md`). *(The act-rather-than-ask half is this file's own convention; no ruling behind it.)*

**Where this file and the code disagree, the code wins and this file is wrong** — except where a ruling says otherwise and names the conflict, as section 5's cap does. Citations name the ruling or the implementing symbol rather than line numbers, which had all drifted by the time #643 audited them; a citation is a lead to check, not proof the rule is recorded. Distinguishing a recorded ruling from this file's own convention reliably is #474, and until it lands this file does not promise it.

## 0. Read the turn top

`just watch-report` first: lane breakers, the queue's underfill verdict, the review-loop terminus prompts (`review_terminus=due|blocked|incomplete|unreadable`; a `due` line names `just review-loop terminus --issue N` and is a prompt, not a landing prerequisite), watcher findings, Remote Control health, the trial and the gate clock. Every part is silent while healthy. **A gate-clock drift line is answered with `just gate-clock-history`, which is owed before any anchor move is proposed** (`AGENTS.md`, that recipe's row) — the live instance is `fast`, on #644.

Then `just controller reconcile` — exactly one System-of-Work reconciliation cycle, reporting the normalised Control Facts, the derived lifecycle state and the ordered Control Actions, and recording its transitions in its own journal. `--dry-run` inspects a cycle and writes nothing. *(Human ruling, 2026-08-29, on #643: the tick uses this recipe, and it runs after `just watch-report`. No earlier authority bound it to this seat.)*

Then `just queue state` and `just queue next` — the candidate with its derivation, or a named refusal. The queue selects and prints; it never dispatches (ADR-0053).

## 1. Harvest

For every dispatch finished since the last tick, do the orchestrator's half. **These acts belong to the seats that own them, not to every completion**: exchange belongs to a dispatch that produced a branch, and a verdict is derived only from a completed `seat=review` dispatch (`tools/review_exchange.py`'s `derive_binding`).

- Read its result and its report.
- **Exchange its branch** with `just review exchange <issue>` (`tools/review_exchange.py`), and retire its tree when the issue is closed (`just worktree done <name>`, or `just worktree archive <name> --ref R` for clean unlanded work already preserved on a named remote ref). "Push the branch" describes neither the recipe nor what the reviewer needs.
- **Dispatch the review over that branch**: `just dispatch --seat review --issue N --reviewing P`, naming the profile whose work it reviews. Never-alone's second instance is a separate session, not a subagent, and no verdict exists until it has run (`docs/agents/orchestration.md`, "The review function" and the tools table). Resolution returns neither that profile nor any other the issue's dispatch records place on the work.
- Record the verdict with `just review record --issue N --reviewed-sha SHA --findings FILE`, then **fold it into the loop with `just review-loop sync --issue N --reviewed-sha <sha>`** — the route that opens the loop at round zero or records the next round with the severities taken from the record, so the seat under review cannot re-grade its own review on the way in (`open` and `round` cannot make that promise).
- **Adjudicate every finding above Low; nothing above Low may be left open** (`tools/review_loop.py`'s `stop_condition`). Low findings are recorded and never block. `just review-loop adjudicate --issue N --finding <id> --route ROUTE` takes one of four routes. **Which route a finding may take, and on what condition, is `docs/agents/review-severity.md`'s and `_route_checks`'s; this file restates neither.** One thing no check can catch is worth carrying: `_route_checks` verifies only that `--conditional-on` is non-empty, so a made-up condition writes a semantically empty adjudication that still clears the rung. Inventing one to clear a landing is the abuse the restriction exists to prevent.
- **Materialise the ledger before quoting the run**: `just ledger-sync sync --behind`, then `just ledger-sync show --dispatch <id>`. `AGENTS.md` requires the row after a dispatched run ends and before its spend or outcome is quoted into an issue.
- **Paste `just verdict` verbatim where a pool gated the work** — never retype the SHA or the evidence path (#219). Separately, on **every** completion you judge and whether or not corpus evidence was owed, run `just trial close-audit --issue N`: it computes and cites the six checkable claims over a close and concludes nothing further (#328). Judging the close stays yours.
- Run `just review-loop terminus --issue N` when its prompt comes due: once per loop, it files every upheld finding on the originating item and records every dismissal, then writes `landing.json` — the record **post-landing review** reads (`render_landing`, `tools/review_loop.py`). The landing rung reads the loop and its stop condition, never this record, which is why the prompt is not a landing prerequisite.

**Reviewers are passed test reports and do not re-run the suite** (#353, clarified by #449). A reviewer that identifies a needed gate **proposes** it; the review seat is `lands=False` under forced plan mode (`tools/dispatch.py`'s `review` seat row), so an implementer lands it on its own issue.

**Review delivery is the dispatcher's transport, not yours** (#496). `deliver_review` posts the one bounded section the reviewer's markers enclose and prints `review_delivery=posted`; do not post the report yourself. `just dispatch-follow` prints `review_delivery_failed` and exits non-zero on an undelivered review — that exit is the stop, not a completed run. **Which refusal admits a deliberate relay, which takes a fresh review, and which leaves the loop unadvanced, is stated in `docs/review-dispatch.md` and implemented in `deliver_review`; this file restates neither.** Read the refusal's own `reason=` and its action line, and treat the missing comment as never a clean review.

## 2. Land

If a branch is gated, reviewed and adjudicated, land it with `just land --audit-file FILE`, passing one complete criterion-by-criterion audit written outside the worktree: what landed, who reviewed it, and what was filed rather than fixed. The rung posts that audit itself and closes only from the posting receipt, so no comment anyone else wrote satisfies the close; without one it refuses `audit_file_unreadable`, and `audit_recorded=yes` verifies the posting call rather than the audit's content (#461, #499).

**A landing whose diff reaches an in-world surface refuses `corpus_owed` unless `--corpus POOL` names a whole, green `just regress` run over a matching tree.** The corpus cannot be run from a subagent, so the seat's obligation is to *see the run happen* and name its pool (`docs/agents/orchestration.md`, "The landing half").

**A verdict survives a clean rebase** (#417): `just land` and `--stage` record it (`_record_clean_rebase`, `tools/land.py`), and the verdict carries to the moved commit where that chain reaches it and the diff's exact identity matches (`docs/review-dispatch.md`). A hand-resolved replay or a binary diff does not carry, so a second landing orphans no other branch's verdict by itself.

**Read the landing's `gate_review=` line.** Every gate-path landing prints exactly one of `cross_lane`, `lane_exhausted`, `lane_barred` or `same_lane_chosen`, derived at landing time and never declared by whoever is landing; what each means, and the two refusals where the record cannot be computed, are `tools/land_review.py`'s gate decision and `AGENTS.md`'s routing-class-6 paragraph. **`review_same_profile` is absolute** — take the same-lane review when a cross-lane one is unavailable, not when it is merely inconvenient.

**Exit codes are part of the contract**: 0 is the invocation's own success, not proof of a landing — a clean `--dry-run` or `--stage` exits 0 too and prints `landed=no` (`tools/land.py`'s `stage` and dry-run plan), so read that line, not the code alone. 1 is nothing landed; 2 is the work **is** on `origin/main` and a step is outstanding — never a success. On the sandbox case the rung prints `merge_command=` naming the exact command for the orchestrator. A stale main checkout is where ADR-0042's stale-hook window comes from, so run what it names.

**After the landing, dispatch the `review` seat once more.** The post-landing pass is the sole remaining catch for a real finding an arbiter dismissed, and it reads the terminus record (`AGENTS.md`, the three named exceptions to the no-further-passes rule). "Post-landing" names when the pass runs; `--seat` accepts no such name.

**After a successful landing, the landed-issue projection is yours.** Run `just observatory` in the **main checkout** and commit its generated `docs/observatory/landed-issues.md` update as your own follow-up. A feature branch never writes that file; `just observatory` deliberately has no feature-branch guard, so running it anywhere else dirties that tree (`docs/agents/orchestration.md`, "The landing half").

**Occupancy is by issue, not by tree.** `queue_policy.derive_in_flight` unions issue worktrees with unfinished dispatch records, then drops every issue GitHub reports closed. A successful `just land` normally closes the issue. So a **landed-but-open** issue still occupies a slot; closing it releases the slot and leaves the tree as `worktree_done_owed`, which retirement then clears.

A registered human reviewer satisfies never-alone instead of a dispatched one: `just review record --issue N --reviewed-sha SHA --findings FILE --reviewer-profile P` writes a separate declared record and refuses a dispatched session (ADR-0080).

**A change on a sign-off-gated path owes its own approval or one of ADR-0013's two standing routes.** `just gated-paths check` runs inside `just check`, names the gated paths and prints both `approve` commands; approval is the human's act and refuses a dispatched session. Neither standing route is a general exemption — the `Delegated-decision: yes` line authorises only the ADR carrying it (#548), and the command-table route reaches only `AGENTS.md`'s data rows (#544) — and both are still reviewed under never-alone. `.claude/commands/` is not on the gated list.

**A change no dispatch record claims declares its author.** `just review-loop author --profile P --issue N`, from an interactive session, gives the never-alone rung an author to exclude; it adds one and never clears the check, and it refuses a session carrying `CTI_DISPATCH_ID` (`AGENTS.md`, that row, citing #294). It is the route for a change under `.claude/`, which a dispatched session does not write and which therefore leaves no record to read. The mechanism holding that line differs by lane and this file names none. *(Human ruling, 2026-08-29, on #643: that gap is the intent, so every correction to this file needs an interactive session.)*

## 3. Refill to the limit

Read the limit **and its ruling** from `just queue state` — it holds both, and a number or a date copied into this file goes stale silently. This file states none.

**Canonical dispatch is `just dispatch --seat S --issue N`, naming neither `--lane` nor `--profile`** (ADR-0071 ruling 2): the seat's preference list resolves the profile, and the two flags are both-or-neither. Naming both stays a way of choosing and never a way around, a refusal attaching to the `(profile, seat)` pair rather than to the resolution path; prefer the canonical form where the seat's own list reaches the same place.

When more than one lane is admissible and the choice is yours, the order of preference is **zai, then codex, then claude-native** (#217, human instruction of 2026-08-19). Preference chooses among admissible lanes; it never overrides a refusal. Still binding: the off-peak rule on zai (#238, no override — the refusal carries no failure class), the breaker, and the routing policy. A `codex` dispatch first runs a synchronous instruction-delivery preflight (#502): `instruction_delivery_mismatch` and `instruction_preflight_unavailable` are both `infra_unavailable` and are not results.

**Codex may take the implementer seat**: `IMPLEMENTER_PREFERENCE` places `codex-luna-max` after the off-peak z.ai head `zai-glm53flash-max` (`tools/dispatch.py`'s registry). Canonical seat resolution walks that order and records what it passes over. This is not a general rule about seats — `orchestrator` is the sole `claude_only=True` row (ADR-0071 ruling 1).

**Read each issue's routing block.** Recent issues carry a `cti.dispatch-plan/1` comment naming seat, lane and profile per stage with escalation triggers; no tool reads it. #463 records the blocks as advisory and leaves the treatment open — honour the block, refuse a contradiction, or proceed with a printed departure are all live options on that issue. Honouring by hand is this file's convention pending that decision, and is not #463's ruling. An honoured block is one such deliberate choice, and it never overrides a refusal.

**Before dispatching**: on a continuation, `just handoff N` is the **first** read, ahead of the issue body and `git log`. Then `just worktree add <name>` for the tree — it fetches, detaches from `origin/main` and pre-flights — and `just brief N`, then write the variable half: task, scope, ground truth, and the reason for a non-default seat, after reading the issue's thread rather than its body alone. Arm `just watch <name> <worktree>` at dispatch. **Follow a cohort in one invocation**: `just dispatch-follow <id> [<id> …]` returns on the **first** of them; never loop one follower per id inside one background task — that loop is a barrier, and the seat sleeps through every slot the faster members free (#280, #295).

The implementer's Work Run may include a bounded self-review before it hands the candidate over (ADR-0079 ruling 1); that is its own interior, not a missing pass and not a defect to reject.

## 4. Priority

`just queue next` returns the **eligible** candidates in issue-number order with a reason beside every one it dropped (`queue_policy`'s selection); it ranks no kinds and this ranking is the seat's, applied over what that read returns. This file names the *order of kinds*, never issue numbers, because a number written here decays by construction:

1. The correctness backlog, defect-class first — a check comparing a token rather than the thing is the standing example.
2. The remaining throughput levers.
3. The banked branches, disjoint surfaces first. Judge rebase against re-implementation per branch on how far behind it is and what it touches; no threshold is recorded anywhere.
4. The records backlog.

Re-rank if the evidence says so, and say so in the tick rather than re-ranking quietly.

## 5. Two reviews per landing, and the cap changes the work

`critical` and `high` go back **once** (#217, human rulings of 2026-08-18 and 2026-08-19, verified on #217's thread). **The cap counts review rounds over one landing — the first review, and one re-review after the fix — never findings**: two `high`s in one report are one round, and clearing them is one patch. `medium` and below may be *routed* without a further review round, but not by default: filing one is `accepted_and_filed`, and that route requires named work outside the diff on which the harm is conditional. An unconditional `medium` is ordinarily fixed in this diff, but `fixed` is not the only route open to it: an authorised arbiter route may close it, and a finding left open blocks the landing (harvest, above).

**The cap and the code disagree, and the cap binds** (human ruling, 2026-08-29, on #643): ADR-0071 and `tools/escalation.py`'s `THREE_ROUND_THRESHOLD` specify three fix rounds and four reviews, and the ADR is wrong. Nothing in the tree counts to two, so the cap is this seat's to hold by hand. **#645 carries both — the ADR's correction and the cap's missing in-tree home.**

**At the cap with a `critical` or `high` outstanding, what is barred is a third patch defending the same claim** (#217). The branch takes one of three routes: delete or simplify the thing being defended; narrow the claim to something provably sound and file the remainder; or park and escalate to the human. The first two are not a third fix — they remove or shrink the subject instead of defending it — but each still produces a diff, and **a verdict binds the SHA and the diff it judged** (`docs/review-dispatch.md`), so the changed branch owes a fresh verdict before it lands. Whether that verdict re-opens the count is undecided and sits on #645 with the rest; do not read it as licence for a third defence of the same claim. **The arbiter routes are not open at the cap**: `escalation_fires_on` requires the wall, `review_rounds >= 3` (`tools/review_loop.py`; `tools/escalation.py`), so "escalate" here means the human, never an arbiter.

**A changelog fragment is read as a claim, not as prose, and every sentence in it must be true of the code as merged** (ADR-0077, #460).

**Earlier trigger, worth more than the cap** (#217): when round two finds the *same class* of defect as round one, stop patching and question the requirement. #405 and #417 are that ruling's worked examples, not its source: #405 spent four rounds on one class and ended by deleting what was being defended. Two instances of a class is evidence about the design.

Take rulings under the human's standing authorisation (#217), record them where they bind, and do not park work waiting for a turn. That authorisation does not displace ADR-0013: a delegated gated decision goes into a marked ADR.

## 6. Report briefly

- Something landed, was filed, or needs a decision: a few lines.
- Nothing changed: **one line** — `no change — <what is running>`.
- Never re-send a full status unless asked for one.

## 7. Escalate at once, not at the end of the tick

A gated sign-off you cannot take; a `critical` that recurs on the same branch; a lane's quality breaker tripping; a refusal you cannot route around. **`quota_exhausted` is not one of them**: it is not a result, and the response is another lane or the provider's own published reset, never a wait this project invents; escalation follows the breaker's trip after consecutive refusals, not the quota (`AGENTS.md`'s failure-class table).

**Preserve typed refusals and exit status when chaining commands.** A `refusal=` line filtered out of a chained command's output on 2026-08-21 dispatched a reviewer onto a stale tree (`d-20260821-015246-9e1696`, stopped before it reported). Check the operation's own result — the tree's HEAD, the recipe's exit code — rather than the presence of a success line. *(This file's convention, from that incident; no ruling behind it.)*
