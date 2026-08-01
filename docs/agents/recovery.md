# Recovering an interrupted agent

Improvised identically three times across 2026-08-01 (docs/process-log.md), then codified
(ADR-0024). The governing instruction, from which everything below follows:

> **Treat a dead agent as one that has been asleep, not one that has failed: its last
> commit is sound, everything after that moment — its own leftovers and its picture of
> the world — is suspect until re-established.**

## Recognising death

A task-failure notification is death. So is silence: an agent that has stopped reporting
and whose worktree has stopped changing is dead for recovery purposes. Do not wait it out
indefinitely, and do not fear a false positive — recovery starts from commits, so
recovering an agent that was merely slow costs a briefing, not work.

## Before resuming: inspect the worktree

`git log -1` plus `git status` in the dead agent's worktree is the whole of the resumable
state — three recoveries needed nothing else. Uncommitted changes are readable context for
the briefing, not results.

Everything else the death left behind is stale infra under ADR-0022: evidence without a
`verdict.json` is not a result, and any server, daemon, or staged world it was running is
state to clear, never context to inherit. The tier lock frees itself on holder death; do
not "recover" it.

## The resumption briefing

The resumed agent's transcript predates everything that happened while it was dead, and it
cannot know what it missed. The briefing must reconstruct all three; omitting any one
silently corrupts the resumed work into defects that look ordinary:

1. **What moved on `main`** — commits landed, ADR numbers claimed or taken, issues opened
   and closed, since the agent's last commit.
2. **What of its own environment died with it** — processes gone, evidence half-written
   (and per ADR-0022, not a result), locks it held that are now free.
3. **Which of its assumptions no longer hold** — ADR-number claims that collided, files or
   surfaces another agent now owns, eliminations whose tested context changed.

## The resumed agent's side

The briefing is a contract with two sides. On wake, before building on anything, the
resumed agent must:

- `git fetch origin` and read what landed since its last commit, plus open-issue comments
  for claims made while it slept;
- re-verify every claim its transcript makes that the briefing marks moved — ADR numbers,
  ownership, eliminations — rather than trusting its own memory over the tree;
- treat its dead run's uncommitted output and in-flight results as ADR-0022 stale state:
  redo the verification, do not cite the corpse.
