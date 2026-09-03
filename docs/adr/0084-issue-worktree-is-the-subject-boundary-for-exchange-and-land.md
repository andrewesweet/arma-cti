# Issue worktree is the subject boundary for exchange and land

Delegated-decision: yes
Date: 2026-09-03
Stood-in-for: human sign-off on the `AGENTS.md` command-table rows for `just review`
and `just land`, under the ADR-0013 command-table route. The rows describe the
issue-worktree subject check and the `just land --issue N` declaration; the recipes
and their behavior land together.
Reviewed-by-human: pending
Supersedes: none
Claimed: 0084 — `git fetch origin` was attempted but the Codex sandbox refused its
`FETCH_HEAD` write. A scan of all open issue comments found no ADR-0084 claim.

## What happened

#688 found that `just review exchange` could publish the caller's unrelated `HEAD`
under another issue's review ref, while `just land` could inspect the caller's empty
tree and report `nothing_to_land` for work held in the issue's linked worktree. The
caller directory is not a reliable subject: the orchestrator's command boundary resets
it between commands.

## Decision

Under the standing authorisation, the `just review` and `just land` rows may describe
the issue-named subject boundary. Exchange resolves `issue-N` from the repository's
canonical linked-worktree path and refuses another caller tree. The dispatcher harness
is the one legitimate external exchange caller; it opts in explicitly because its
disposable dispatch tree is not issue-named. Land derives the issue from its canonical
worktree name or accepts an explicit positive `--issue N`, then refuses a different
caller tree before reading landing state.

The implementation keeps the low-level landing seam usable by tests that supply its
roots directly; the public command is the boundary that resolves and validates the
caller.

## What would overturn it

A human identifies a legitimate user-facing exchange or landing workflow that must act
on a different tree. That workflow must receive its own explicit declaration or the
resolution rule must be revisited; silent caller-`HEAD` acceptance is not restored.
