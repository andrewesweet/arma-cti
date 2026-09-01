---
description: One orchestrator cycle — harvest finished dispatches, land what is ready, refill WIP, report only what changed.
---

Orchestrator tick. Act; do not wait for the human, and hold the waits this seat is for (`docs/agents/orchestration.md`).

Pointers below to open issues — #463, #645, #646, #647 — are permitted: human ruling of 2026-08-30, #643.

## 0. Read the turn top

- `just watch-report`
- Answer a gate-clock drift line with `just gate-clock-history` before proposing any anchor move.
- `just controller reconcile`
- `just queue state`, then `just queue next` — section 4 ranks every `considered.N=eligible` number it prints.

If `just watch-report` prints `action=refill-before-landing`, run section 3 down to and
including its `just watch` step, stop before its `just dispatch-follow`, then run
sections 1 and 2. Follow the new dispatch in section 1's cohort invocation
(`docs/agents/orchestration.md`, "Follow a cohort in one invocation").

## 1. Harvest

Read the result and the report of every dispatch finished since the last tick.

Launch the whole review cohort before waiting on any of it. For each finished dispatch that produced a branch, run the review-dispatch sequence:

- `just review-loop author --profile P --issue N`, from an interactive session, where no dispatch record claims the change — before the dispatch below.
- `just review exchange <issue>`
- `just dispatch --seat review --issue N --reviewing P --base-sha <sha>` — the SHA `just review exchange` emitted. Pass no `--brief-file`: review dispatches take the default brief until #647 lands (human ruling of 2026-08-30, #643; `docs/review-dispatch.md`).
- `just watch <name> issue-<n> path --await-path ~/.arma-cti/dispatches/<id>/result.json` —
  the issue's own worktree, never the review's own tree (`tools/dispatch.py`,
  `disposable_worktree`); `<id>` is what `just dispatch` returned.

Then, once, over every review dispatch just launched:

- `just dispatch-follow <id> [<id> …]` — one invocation over the cohort; never a follower per id.

Process that completed review through the steps below, then run sections 2 and 3 for it — land it and refill the freed capacity — and only then re-follow the remainder, in the same turn (`docs/agents/orchestration.md`, "Follow a cohort in one invocation").

Per completed review:

- `just review record --issue N --reviewed-sha SHA --findings FILE` — only after that completion.
- `just review-loop sync --issue N --reviewed-sha <sha>` — pre-landing verdicts only (#646). Route a post-landing verdict's claims per `docs/review-dispatch.md`.
- `just review-loop adjudicate --issue N --finding <id> --route ROUTE` — nothing above Low may be left open. Routes and their conditions: `docs/agents/review-severity.md`, `tools/review_loop.py`'s `_route_checks`.
- `just ledger-sync sync --behind`, then `just ledger-sync show --dispatch <id>`, before quoting a run's spend or outcome.
- `just verdict <pool-dir>` — name the exact pool; paste verbatim where a pool gated the work; never retype the SHA or the evidence path.
- `just review-loop terminus --issue N` — once per loop, when its prompt comes due.
- `just worktree done <name>` when the issue is closed, or `just worktree archive <name> --ref R` for clean unlanded work already preserved on a named remote ref.

Brief a reviewer to read the test reports rather than re-run the suite. Do not post the review report yourself. Refusal handling and the briefing rule: `docs/review-dispatch.md`.

## 2. Land

- `just land --audit-file FILE`, the audit written outside the worktree.
- Add `--corpus POOL` where the diff reaches an in-world surface (`docs/agents/orchestration.md`, "The landing half").
- Read the printed `ok=landed`, `gate_review=` and exit status.
- On exit 2: run the `merge_command=` it names, then run `just land --resume --audit-file FILE` to complete the post-push half even when that merge already made the main checkout current. Never close by hand from exit 2; exit 2 remains an incomplete landing, not success.
- After the landing, run the post-landing review — its own pass, not a re-entry into section 1:
  - `just dispatch --seat review --issue N --reviewing P --base-sha <landed sha>`. Pass no
    `--brief-file` (human ruling of 2026-08-30, #643; `docs/review-dispatch.md`).
  - `just watch <name> <main checkout> path --await-path ~/.arma-cti/dispatches/<id>/result.json`.
  - `just dispatch-follow <id>`.
  - Route the report's claims per `docs/review-dispatch.md`, "Routing": a **defect** as a new
    `needs-triage` issue naming the reviewed issue, the reviewed SHA, the cited `file:line` and
    the review's dispatch id; an **observation** as a comment on the reviewed issue; a claim
    **not upheld** recorded on the reviewed issue as checked and not upheld.
  - Run no `just review-loop sync` and no `just land` for this pass (#646).
- `just trial close-audit --issue N`, once `just land` has closed the issue.
- `just observatory` in the **main checkout**, then commit the `docs/observatory/landed-issues.md` update as a follow-up.

A registered human reviewer: `just review record --issue N --reviewed-sha SHA --findings FILE --reviewer-profile P` (ADR-0080).
Where the diff reaches a gated path, run `just gated-paths check` and take one of the routes `AGENTS.md` and `tools/gated_paths.py` list. Approval is the human's act.

## 3. Refill to the limit

Read the limit and its ruling from `just queue state`.

- On a continuation, `just handoff N` first.
- No tree yet: `just worktree add <name>`.
- Clean work already archived on a named remote ref: `just worktree restore <name> --ref R`.
- A tree already present: `just worktree check <name>`; on `worktree_occupied` naming another holder, stop and report.
- `just brief N --seat S --out FILE`, then write its variable half: task, scope, ground truth, and the reason for a non-default seat, naming the comment each pre-derived decision came from (`docs/agents/orchestration.md`).
- `just dispatch --seat S --issue N --brief-file FILE` — naming neither `--lane` nor `--profile` (ADR-0071 ruling 2); the two are both-or-neither.
- `just watch <name> <worktree> path --await-path ~/.arma-cti/dispatches/<id>/result.json`
  at dispatch; `<id>` is what `just dispatch` returned.
- `just dispatch-follow <id> [<id> …]` — one invocation over the cohort; never a follower per id.

Lane preference: `tools/dispatch.py`'s `SEATS`, `just dispatch --list`.

Read an issue's `cti.dispatch-plan/1` routing block before dispatching (#463).

## 4. Priority

Read each eligible issue — `gh issue view N` — then rank by kind:

1. The correctness backlog, defect-class first.
2. The remaining throughput levers.
3. The banked branches, disjoint surfaces first.
4. The records backlog.

Re-rank if the evidence says so, and say so in the tick.

## 5. Two reviews per landing

Send `critical` and `high` back once (#217); count rounds over one landing, never findings. Round-cap disagreement: #645.

At the cap with a `critical` or `high` outstanding, take one of three routes: delete or simplify what is being defended; narrow the claim and file the remainder; or park and escalate to the human. Take no arbiter route at the cap.

When round two finds the same class of defect as round one, stop patching and question the requirement (#217).

Read a changelog fragment as a claim: every sentence must be true of the code as merged (ADR-0077).

Take rulings under the human's standing authorisation and record them where they bind; a delegated gated decision goes into an ADR-0013-marked ADR.

## 6. Report briefly

- Something landed, was filed, or needs a decision: a few lines.
- Nothing changed: one line — `no change — <what is running>`.
- Never re-send a full status unless asked.

## 7. Escalate at once, not at the end of the tick

Escalate a gated sign-off you cannot take; a `critical` that recurs on the same branch; a lane's quality breaker tripping; a refusal you cannot route around. Do not escalate `quota_exhausted` (`AGENTS.md`'s failure-class table).

Preserve typed refusals and exit status when chaining commands; check the operation's own result, not the presence of a success line.
