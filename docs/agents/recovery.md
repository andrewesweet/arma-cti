# Recovering an interrupted agent

> Status: validated ×5 — first two uses as a written procedure, both 2026-08-01: #21's
> agent dead mid-Arma-run, and one silent stall mid-turn with the run still live. Three
> more on #46 in one cycle (mid-pass, post-pass, post-commit), every briefing written to
> this document's three-part contract, every resumption clean. What failed in that cycle
> was never the resumption but the noticing — one stall sat unseen ~8 hours behind a
> monitoring check that could not fail — so the second amendment is the section on
> noticing, the orchestrator's side of the contract. Third amendment (2026-08-02): the
> worktree-vanish mode, improvised identically twice before it was written.

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

The two signs can also combine: an agent can stop mid-turn while its run — server, daemon,
staged world — is still live, with a completion notification firing anyway. That is death
with live work, not a false alarm. Treat it as death, and treat the still-running work as
the stale state below: nobody is going to write its verdict, so whatever it eventually
emits is not a result to cite (ADR-0022). Seen once, 2026-08-01.

A live agent can also lose its ground: its isolation worktree vanishes mid-run and Bash
starts refusing with "isolated worktree no longer exists". Seen twice (the #48 research
session's strands; the #56 review, which lost 14 config files unreviewed — #94), cause
unobservable from inside a session and tracked in #105; both victims were read-only
sessions whose worktrees held no commits, consistent with the harness reaping a worktree
it sees as unchanged. The work is not resumable in place: finish any read-only reporting
from the main checkout, **never commit there**, name what went unexamined instead of
papering over it (the #56 review shipped with its gap as an issue, which is the model),
and treat anything uncommitted as dead with the worktree.

## Noticing in time: the orchestrator's side

Recovery is cheap; not noticing is what costs. Three stalls on one agent in one cycle
each resumed cleanly from a briefing, but one sat unseen for ~8 hours — with a
*finished* pass nobody read — because the orchestrator was watching the clock and its
clock-watching lied (ADR-0033).

- **Check when the work signals, not when the clock does.** An agent's observable work
  has completion edges — a server exits, a pass finishes, a lock frees — and each edge is
  the moment to look at the agent that owns it. The proven mechanism for the server-backed
  case: a background watchdog loop that re-invokes the orchestrator when the server
  exits, re-armed each cycle, plus a grace-then-nudge check when a completion edge passes
  without the agent reporting.
- **A self-check must fail closed.** `pgrep -f arma3server` matched the orchestrator's
  *own command line* and reported SERVER-LIVE for hours over a dead server; `pgrep -x`
  matches the process, not the prose. Third instance of the shape (#41's bare
  `tasklist.exe`, #44's daemon-address default agreeing with itself): a check the checker
  satisfies by existing is not a check, and "could not observe" is never "still running".
- **Nested subagents report to the session that spawned the tree, not to their parent
  agent.** A parent waiting on its strand's report waits on something that will arrive at
  the orchestrator instead; relay it (files plus a message worked, at ~15k tokens of
  double-handling on #48). Plan the plumbing before fanning out two levels deep.

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
