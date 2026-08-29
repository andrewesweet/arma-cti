---
description: One orchestrator cycle — harvest finished dispatches, land what is ready, refill WIP, report only what changed.
---

Orchestrator tick. Act; do not wait for the human — and **hold the waits this seat is for**. Ending a turn mid-wait is the subagent's rule and does not apply here (`docs/agents/orchestration.md`). *(The act-rather-than-ask half is this file's own convention; no ruling behind it.)*

**Where this file and the code disagree, the code wins and this file is wrong.** Citations name the ruling or the implementing symbol — a function, a docstring section, a refusal name — rather than line numbers, because line numbers at these coordinates had all drifted by the time #643 audited them. A citation is a lead to check, not proof the rule is recorded. Most of the orchestration rulings here are #217's. Making the file reliably distinguish a recorded ruling from its own convention is #474; until that lands, this file does not promise it.

## 0. Read the turn top

`just controller reconcile` first — exactly one System-of-Work reconciliation cycle, reporting the normalised Control Facts, the derived lifecycle state and the ordered Control Actions, and recording its transitions in its own journal. It runs before **any** read that selects, `just watch-report`'s queue report included, because a non-dry cycle mutates tracker, worktree and dispatch state and would stale a selection already taken. `--dry-run` inspects a cycle and writes nothing. *(Human ruling, 2026-08-29, on #643: the tick uses this recipe. No earlier authority bound it to this seat.)*

Then `just watch-report`: lane breakers, the queue's underfill verdict, the review-loop terminus prompts (`review_terminus=due|blocked|incomplete|unreadable`; a `due` line names `just review-loop terminus --issue N` and is a prompt, not a landing prerequisite), watcher findings, Remote Control health, the trial and the gate clock. Every part is silent while healthy.

Then `just queue state` and `just queue next` — the candidate with its derivation, or a named refusal. The queue selects and prints; it never dispatches (ADR-0053).

## 1. Harvest

For every dispatch finished since the last tick, do the orchestrator's half. **These acts belong to the seats that own them, not to every completion**: exchange belongs to a dispatch that produced a branch, and a verdict is derived only from a completed `seat=review` dispatch (`tools/review_exchange.py`'s `derive_binding`).

- Read its result and its report.
- **Exchange its branch** with `just review exchange <issue>` (`tools/review_exchange.py`), and retire its tree when the issue is closed (`just worktree done <name>`, or `just worktree archive <name> --ref R` for clean unlanded work already preserved on a named remote ref). "Push the branch" describes neither the recipe nor what the reviewer needs.
- Record the verdict with `just review record --issue N --reviewed-sha SHA --findings FILE`, then **fold it into the loop with `just review-loop sync --issue N --reviewed-sha <sha>`** — the route that opens the loop at round zero or records the next round with the severities taken from the record, so the seat under review cannot re-grade its own review on the way in (`open` and `round` cannot make that promise).
- **Adjudicate every finding above Low; nothing above Low may be left open** (`tools/review_loop.py`'s `stop_condition`). Low findings are recorded and never block. `just review-loop adjudicate --issue N --finding <id> --route ROUTE` takes one of four routes. **Which route a finding may take, and on what condition, is stated in `docs/agents/review-severity.md` and enforced as far as it can be by `tools/review_loop.py`'s `_route_checks`; this file restates neither.** One thing is worth carrying here because no check can catch it: `_route_checks` verifies that `--conditional-on` is non-empty and nothing more, so a made-up condition writes a semantically empty adjudication that still clears the rung. Inventing one to clear a landing is the abuse the restriction exists to prevent.
- **Materialise the ledger before quoting the run**: `just ledger-sync sync --behind`, then `just ledger-sync show --dispatch <id>`. `AGENTS.md` requires the row after a dispatched run ends and before its spend or outcome is quoted into an issue.
- **Paste `just verdict` verbatim where a pool gated the work** — never retype the SHA or the evidence path (#219). Separately, and on **every** completion you judge, whether or not corpus evidence was owed, run `just trial close-audit --issue N`, which computes and cites the six checkable claims over a close and concludes nothing further, the admission bar having been dropped (#328). Judging the close stays yours (`docs/agents/orchestration.md`, the top-of-turn sequence, step 6).
- Run `just review-loop terminus --issue N` when its prompt comes due: once per loop, it files every upheld finding on the originating item and records every dismissal, then writes the landing record the landing rung reads.

**Reviewers are passed test reports and do not re-run the suite** (#353, clarified by #449). A reviewer that identifies a needed gate **proposes** it; the review seat is `lands=False` under forced plan mode (`tools/dispatch.py`'s `review` seat row), so an implementer lands it on its own issue.

**Review delivery is the dispatcher's transport, not yours** (#496). The reviewer bounds its report with the marker lines its brief supplies and does not call `gh`; `deliver_review` posts that one bounded section, and a posted review prints `review_delivery=posted` as a completion. Do not post the report yourself. `just dispatch-follow` prints `review_delivery_failed` and exits non-zero on an undelivered review — treat that exit as the stop, not as a completed run. **Which refusal admits a deliberate relay, which takes a fresh review, and which leaves the loop unadvanced, is stated in `docs/review-dispatch.md` and implemented in `deliver_review`; this file restates neither.** Read the refusal's own `reason=` and its action line, and treat the missing comment as never a clean review.

## 2. Land

If a branch is gated, reviewed and adjudicated, land it with `just land --audit-file FILE`, passing one complete criterion-by-criterion audit written outside the worktree: what landed, who reviewed it, and what was filed rather than fixed. The rung posts that audit as its own comment and closes only from the successful posting receipt, so no comment anyone else wrote can satisfy the close. It refuses `audit_file_unreadable` without one, and `audit_recorded=yes` verifies the posting call rather than the audit's content or quality (#461, #499).

**A landing whose diff reaches an in-world surface refuses `corpus_owed` unless `--corpus POOL` names a whole, green `just regress` run over a matching tree.** The corpus cannot be run from a subagent, so the seat's obligation is to *see the run happen* and name its pool (`docs/agents/orchestration.md`, "The landing half").

**A verdict survives a clean rebase** (#417). `just land` and `just land --stage` record the rebase (`_record_clean_rebase`, `tools/land.py`), and a verdict carries to the moved commit when the recorded chain reaches it and the diff's exact identity matches (`docs/review-dispatch.md`, "The verdict binds the diff, not only the commit"). A hand-resolved replay or a binary diff does not carry. So a second landing does not automatically orphan another branch's verdict.

**Read the landing's `gate_review=` line.** Every gate-path landing prints exactly one, naming one of four derived facts: `cross_lane` (the preferred check), `lane_exhausted`, `lane_barred`, or `same_lane_chosen` (`tools/land_review.py`'s gate decision). It is computed at landing time from the registry and the records, never declared by whoever is landing, and no flag suppresses it — the three downgrades are different facts and a reader must be able to tell them apart. Two refusals survive where the record cannot be computed: `review_lane_unknown` and `gate_class_undetermined`. **`review_same_profile` is absolute** — take the same-lane review when a cross-lane one is unavailable, not when it is merely inconvenient.

**Exit codes are part of the contract**: 0 landed; 1 nothing landed; 2 the work **is** on `origin/main` and a step is outstanding — never a success. On the sandbox case the rung prints `merge_command=` naming the exact command for the orchestrator (`tools/land.py`'s refusal vocabulary). A stale main checkout is where ADR-0042's stale-hook window comes from, so run what it names.

**After a successful landing, the landed-issue projection is yours.** Run `just observatory` in the **main checkout** and commit its generated `docs/observatory/landed-issues.md` update as your own follow-up. A feature branch never writes that file; `just observatory` deliberately has no feature-branch guard, so running it anywhere else dirties that tree (`docs/agents/orchestration.md`, "The landing half").

**Occupancy is by issue, not by tree.** `queue_policy.derive_in_flight` unions issue worktrees with unfinished dispatch records, then drops every issue GitHub reports closed. A successful `just land` normally closes the issue. So a **landed-but-open** issue still occupies a slot; closing it releases the slot and leaves the tree as `worktree_done_owed`, which retirement then clears.

A registered human reviewer satisfies never-alone instead of a dispatched one: `just review record --issue N --reviewed-sha SHA --findings FILE --reviewer-profile P` writes a separate declared record and refuses a dispatched session (ADR-0080).

**A change on a sign-off-gated path owes its own approval or one of two standing routes.** `just gated-paths check` runs inside `just check` and refuses a change to `AGENTS.md`, `CLAUDE.md`, `CONTEXT.md`, `docs/adr/`, `tests/specs/` or `.claude/skills/` unless one covers it. `just gated-paths approve --issue N --path P` takes exactly one of `--change-id ID` or `--content-id ID`, is the human's act, and refuses a dispatched session. Both standing routes are ADR-0013's, and neither is a general exemption: a changed ADR carrying the exact `Delegated-decision: yes` line in its field block authorises **only the ADR carrying it**, every other gated path in the diff still owing its own approval or its own marker (#548); and one ADR-0013 entry authorises a diff **confined to `AGENTS.md`'s command-table data rows** naming recipes the justfile resolves at that same commit, whose mechanical floor is `just check-command-table` — which does not judge the rows' prose (#544). Both are still reviewed under never-alone. `.claude/commands/` is not on the gated list.

**A change no dispatch record claims declares its author.** `just review-loop author --profile P --issue N`, from an interactive session, names the profile that wrote it so the never-alone rung has an author to exclude. It adds an author and never clears the check, and it refuses a session carrying `CTI_DISPATCH_ID`. This is the route for a change under `.claude/`, which a dispatched session does not write (`AGENTS.md`, the `just review-loop author` row, citing #294), so such a change leaves no dispatch record for the rung to read. The mechanism that holds that line differs by lane, and this file names none. *(Human ruling, 2026-08-29, on #643: that gap is the intent, so every correction to this file needs an interactive session.)*

## 3. Refill to the limit

Read the limit **and its ruling** from `just queue state` — it holds both, and a number or a date copied into this file goes stale silently. This file states none.

**Canonical dispatch is `just dispatch --seat S --issue N`, naming neither `--lane` nor `--profile`** (ADR-0071 ruling 2): the seat's preference list resolves the profile, and the two flags are both-or-neither everywhere. Naming an explicit route — both `--lane` and `--profile` — stays a way of choosing and never a way around, since a refusal attaches to the `(profile, seat)` pair rather than to the resolution path. Handing work to a particular lane or profile is what the recipe is for; prefer the canonical form where the seat's own list would reach the same place.

When more than one lane is admissible and the choice is yours, the order of preference is **zai, then codex, then claude-native** (#217, human instruction of 2026-08-19). Preference chooses among admissible lanes; it never overrides a refusal. Still binding: the off-peak rule on zai (#238, no override — the refusal carries no failure class), the breaker, and the routing policy. A `codex` dispatch first runs a synchronous instruction-delivery preflight (#502): `instruction_delivery_mismatch` and `instruction_preflight_unavailable` are both `infra_unavailable` and are not results.

**Codex may take the implementer seat**: `IMPLEMENTER_PREFERENCE` places `codex-luna-max` after the off-peak z.ai head `zai-glm53flash-max` (`tools/dispatch.py`'s registry). Canonical seat resolution walks that order and records what it passes over. This is not a general rule about seats — `orchestrator` is the sole `claude_only=True` row (ADR-0071 ruling 1).

**Read each issue's routing block.** Recent issues carry a `cti.dispatch-plan/1` comment naming seat, lane and profile per stage with escalation triggers; no tool reads it. #463 records the blocks as advisory and leaves the treatment open — honour the block, refuse a contradiction, or proceed with a printed departure are all live options on that issue. Honouring by hand is this file's convention pending that decision, and is not #463's ruling. An honoured block is one such deliberate choice, and it never overrides a refusal.

**Before dispatching**: `just brief N`, then write the variable half — task, scope, ground truth, and the reason for a non-default seat — after reading the issue's thread, not its body alone. Arm `just watch <name> <worktree>` at dispatch. **Follow a cohort in one invocation**: `just dispatch-follow <id> [<id> …]` returns on the **first** of them; never loop one follower per id inside one background task — that loop is a barrier, and the seat sleeps through every slot the faster members free (#280, #295).

The implementer's Work Run may include a bounded self-review before it hands the candidate over (ADR-0079 ruling 1); that is its own interior, not a missing pass and not a defect to reject.

## 4. Priority

Derive the ranking from the tracker each tick (`just queue next`); this file names the *order of kinds*, never issue numbers, because a number written here decays by construction:

1. The correctness backlog, defect-class first — a check comparing a token rather than the thing is the standing example.
2. The remaining throughput levers.
3. The banked branches, disjoint surfaces first. Judge rebase against re-implementation per branch on how far behind it is and what it touches; no threshold is recorded anywhere.
4. The records backlog.

Re-rank if the evidence says so, and say so in the tick rather than re-ranking quietly.

## 5. Two reviews per landing, and the cap changes the work

`critical` and `high` go back **once** (#217, human rulings of 2026-08-18 and 2026-08-19, verified on #217's thread). Two reviews total — not one per finding. `medium` and below may be *routed* without a further review round, but not by default: filing one is `accepted_and_filed`, and that route requires named work outside the diff on which the harm is conditional. An unconditional `medium` is ordinarily fixed in this diff, but `fixed` is not the only route open to it: an authorised arbiter route may close it, and a finding left open blocks the landing (harvest, above).

**At the cap with a `critical` or `high` outstanding, a third patch is not an option** (#217). The branch takes one of three routes: delete or simplify the thing being defended; narrow the claim to something provably sound and file the remainder; or park and escalate. **The arbiter routes are not a fourth option at the cap**: `escalation_fires_on` requires the wall, `review_rounds >= 3` (`tools/review_loop.py`, `_route_checks` and `escalation_fires_on`; `tools/escalation.py`), so at two rounds an outstanding `critical` or `high` has only `fixed` or the block.

**A changelog fragment is read as a claim, not as prose, and every sentence in it must be true of the code as merged** (ADR-0077, #460). ADR-0077 records five false fragments found, of which three blocked a landing.

**Earlier trigger, worth more than the cap** (#217): when round two finds the *same class* of defect as round one, stop patching and question the requirement. #405 and #417 are that ruling's worked examples, not its source: #405 spent four rounds on one class and ended by deleting what was being defended. Two instances of a class is evidence about the design.

Take rulings under the human's standing authorisation (#217), record them where they bind, and do not park work waiting for a turn. That authorisation does not displace ADR-0013: a delegated gated decision goes into a marked ADR.

## 6. Report briefly

- Something landed, was filed, or needs a decision: a few lines.
- Nothing changed: **one line** — `no change — <what is running>`.
- Never re-send a full status unless asked for one.

## 7. Escalate at once, not at the end of the tick

A gated sign-off you cannot take; a `critical` that recurs on the same branch; a provider quota or breaker trip; a refusal you cannot route around.

**Preserve typed refusals and exit status when chaining commands.** A `refusal=` line filtered out of a chained command's output on 2026-08-21 dispatched a reviewer onto a stale tree (`d-20260821-015246-9e1696`, stopped before it reported). Check the operation's own result — the tree's HEAD, the recipe's exit code — rather than the presence of a success line. *(This file's convention, from that incident; no ruling behind it.)*
