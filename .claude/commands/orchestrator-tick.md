---
description: One orchestrator cycle — harvest finished dispatches, land what is ready, refill WIP, report only what changed.
---

Orchestrator tick. Act; do not wait for the human, and hold the waits this seat is for (`docs/agents/orchestration.md`).

Where this file and the code disagree, the code wins. Rules live at their pointers; this file carries steps and commands only.

## 0. Read the turn top

- `just watch-report`
- Answer a gate-clock drift line with `just gate-clock-history` before proposing any anchor move.
- `just controller reconcile`
- `just queue state`, then `just queue next`

If `just watch-report` prints `action=refill-before-landing`, run section 3 before section 2.

## 1. Harvest

For every dispatch finished since the last tick:

- Read its result and its report.
- `just review exchange <issue>` — for a dispatch that produced a branch.
- `just dispatch --seat review --issue N --reviewing P --base-sha <sha>` — the SHA `just review exchange` emitted. Pass no `--brief-file`: the review seat runs in a dispatch-owned disposable worktree and `just brief` composes an `issue-N` tree.
- `just review record --issue N --reviewed-sha SHA --findings FILE`
- `just review-loop sync --issue N --reviewed-sha <sha>` — pre-landing verdicts only; nothing enforces that (#646). Route a post-landing verdict's claims per `docs/review-dispatch.md`.
- `just review-loop adjudicate --issue N --finding <id> --route ROUTE` — nothing above Low may be left open. Routes and their conditions: `docs/agents/review-severity.md`, `tools/review_loop.py`'s `_route_checks`.
- `just ledger-sync sync --behind`, then `just ledger-sync show --dispatch <id>`, before quoting a run's spend or outcome.
- `just verdict` — paste verbatim where a pool gated the work; never retype the SHA or the evidence path.
- `just trial close-audit --issue N` — on every completion you judge. Judging the close stays yours.
- `just review-loop terminus --issue N` — once per loop, when its prompt comes due.
- `just worktree done <name>` when the issue is closed, or `just worktree archive <name> --ref R` for clean unlanded work already preserved on a named remote ref.

Brief a reviewer to read the test reports rather than re-run the suite (`docs/review-dispatch.md`). Do not post the review report yourself; `just dispatch-follow` reports delivery. Refusal handling: `docs/review-dispatch.md`.

## 2. Land

- `just land --audit-file FILE`, the audit written outside the worktree.
- Add `--corpus POOL` where the diff reaches an in-world surface (`docs/agents/orchestration.md`, "The landing half").
- Read the printed `landed=`, `gate_review=` and exit status. Exit 2 means the work is on `origin/main` with a step outstanding. Run any `merge_command=` it names.
- After the landing: re-exchange from a tree at the landed commit, then `just dispatch --seat review --issue N --reviewing P --base-sha <landed sha>`.
- Then run `just observatory` in the **main checkout** and commit the `docs/observatory/landed-issues.md` update as a follow-up.
- Close the landed issue; a landed-but-open issue still occupies a slot.

A registered human reviewer: `just review record --issue N --reviewed-sha SHA --findings FILE --reviewer-profile P` (ADR-0080).
A gated path owes its approval: `just gated-paths check` names them and prints both `approve` commands; approval is the human's act.
A change no dispatch record claims declares its author: `just review-loop author --profile P --issue N`, from an interactive session.

## 3. Refill to the limit

Read the limit and its ruling from `just queue state`.

- `just handoff N` first, on a continuation.
- `just worktree add <name>`
- `just brief N --seat S --out FILE`, then write its variable half: task, scope, ground truth, and the reason for a non-default seat, naming the comment each pre-derived decision came from (`docs/agents/orchestration.md`).
- `just dispatch --seat S --issue N --brief-file FILE` — naming neither `--lane` nor `--profile` (ADR-0071 ruling 2); the two are both-or-neither.
- `just watch <name> <worktree>` at dispatch.
- `just dispatch-follow <id> [<id> …]` — one invocation over the cohort; never a follower per id.

Lane preference among admissible lanes: zai, then codex, then claude-native (#217). Preference never overrides a refusal.

Honour an issue's `cti.dispatch-plan/1` routing block by hand; no tool reads it (#463).

## 4. Priority

`just queue next` prints one candidate by default (`--count N` for more), with its derivation. Rank by kind:

1. The correctness backlog, defect-class first.
2. The remaining throughput levers.
3. The banked branches, disjoint surfaces first.
4. The records backlog.

Re-rank if the evidence says so, and say so in the tick.

## 5. Two reviews per landing

`critical` and `high` go back once (#217). The cap counts review rounds over one landing, never findings. It disagrees with ADR-0071 and `tools/escalation.py`'s `THREE_ROUND_THRESHOLD`, and the cap binds (human ruling, 2026-08-29, on #643); #645 carries both.

At the cap with a `critical` or `high` outstanding, take one of three routes: delete or simplify what is being defended; narrow the claim and file the remainder; or park and escalate to the human. Each still produces a diff that owes a fresh verdict. Arbiter routes are not open at the cap.

When round two finds the same class of defect as round one, stop patching and question the requirement (#217).

Read a changelog fragment as a claim: every sentence must be true of the code as merged (ADR-0077).

Take rulings under the human's standing authorisation and record them where they bind; a delegated gated decision goes into an ADR-0013-marked ADR.

## 6. Report briefly

- Something landed, was filed, or needs a decision: a few lines.
- Nothing changed: one line — `no change — <what is running>`.
- Never re-send a full status unless asked.

## 7. Escalate at once, not at the end of the tick

A gated sign-off you cannot take; a `critical` that recurs on the same branch; a lane's quality breaker tripping; a refusal you cannot route around. Not `quota_exhausted` (`AGENTS.md`'s failure-class table).

Preserve typed refusals and exit status when chaining commands; check the operation's own result, not the presence of a success line.
