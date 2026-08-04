# Recovering an interrupted agent

> Status: validated ×11 — first two uses as a written procedure, both 2026-08-01: #21's
> agent dead mid-Arma-run, and one silent stall mid-turn with the run still live. Three
> more on #46 in one cycle (mid-pass, post-pass, post-commit), every briefing written to
> this document's three-part contract, every resumption clean. What failed in that cycle
> was never the resumption but the noticing — one stall sat unseen ~8 hours behind a
> monitoring check that could not fail — so the second amendment is the section on
> noticing, the orchestrator's side of the contract. Third amendment (2026-08-02): the
> worktree-vanish mode, improvised identically twice before it was written. Sixth and
> seventh uses (2026-08-02): session limits killed both review-burn-down tail agents
> mid-flight; both resumed clean, and one briefing mis-read "clean, zero ahead" as lost
> work — the resumed agent's fetch-and-verify side caught it and corrected the
> orchestrator, the first time that half of the contract has earned its keep against a
> wrong briefing. Fourth amendment: the evidence-not-inference sentence in the briefing
> section, from that instance. Eighth use (2026-08-02): #51's agent stalled mid-cycle
> and resumed clean off a briefing to the same three-part contract, no amendment needed.
> Ninth use (2026-08-02): the orchestrating session itself died mid-cycle — the second
> such death — taking the #130 agent with it; the successor's briefing said "no
> verification evidence survives on my side" rather than inferring what the dead session
> had seen, and the agent rebased, re-verified from scratch, and landed. Fifth amendment:
> the orchestrator-death section, codified after its second identical improvisation, the
> same threshold the worktree-vanish mode earned by. (The fourteenth retro's edit added
> the ninth use without moving the count — the first violation of the same-edit clause
> since it was written; fixed by the fifteenth, which per ADR-0038's shape escalates a
> second violation to a mechanical check.) Sixth amendment (2026-08-02): the
> shared-assignment variant of the worktree mode, after #105's instances 3–5 in one
> evening. Tenth use (2026-08-03/04): the disk-exhaustion crash cluster — four
> orchestrator deaths in one window (the orchestrator's count; in-repo corroboration in
> #164's crash-killed corpus attempt and crash-recovery checkpoint and #144's attempt-3
> loss), root-caused by the human to a full Windows OS drive, every recovery the
> codified move at near-zero cost to commit-early. Seventh and eighth amendments
> (2026-08-04, from that cluster): the checkpoint-diff bullet in the resumed agent's
> side, and the monitor-claim clause in the noticing section. Eleventh use
> (2026-08-04): the standing watcher's first catch since it was codified — the #159
> agent sat silent for 40 minutes after its corpus run finished green (21/21,
> worktree clean and unlanded), dispatched with the do-not-park briefing line carried
> and CLAUDE.md's watching sentence live. Three stalls, three watcher catches, none
> prevented or caught by text: the attribution question the eighteenth retro left
> open is answered, and the layer this document made standing is the one that works.

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

The mode has a second variant: the harness hands one worktree to two live agents (#105,
instances 3–5, all in one evening — including the orchestrator's own primary worktree,
twice). Nothing looks wrong from inside either session until one agent's routine
reset-to-origin or the harness's auto-clean destroys the other's uncommitted work, which
is how instance 3 cost the #132 agent its edits (recovered from notes). Hence the
pre-flight in CLAUDE.md's working style: verify the worktree is exclusively yours before
touching it, commit early, and on finding foreign files stop and report — the stopped
agent loses a dispatch, the reset would have lost another session's work. The pre-flight
prevented exactly that on its first firing (instance 5, the fifteenth-retro dispatch).

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
- **A subagent's "monitor armed" is a claim about time after its own turn, which nothing
  it arms survives — so the insurance watcher is standing, not an ad-hoc save.** Twice on
  2026-08-04 the claim coincided with a turn that had already stopped with no live
  children, and the #168 agent stalled twice in one evening at the identical point:
  background `just unit` launched, run finished, agent never woke, each stall caught only
  by the orchestrator's external watcher and cleared only by an explicit prod naming what
  had finished. Two identical saves is this document's codification threshold: an agent
  dispatched with a run attached gets a watcher armed at dispatch. The agent-side rule is
  CLAUDE.md's watching-inside-turn sentence. A third catch (2026-08-04: #159's agent, 40
  minutes silent after a green corpus run, both text layers demonstrably live) settled
  the attribution: the text does not prevent the stall and the watcher catches it, three
  for three. Keep the sentence because it is true; rely on the watcher because it works.

## When the orchestrator itself dies

Seen twice (both 2026-08-02), both recovered at zero cost, and the reason generalises: the
orchestrator holds no durable state of its own. Everything that matters lives on `main`,
in the issues, and in the agents' worktrees, so a successor session rebuilds its picture
from those plus the harness's task-notification breadcrumbs — there is nothing else to
look for, and nothing on the dead orchestrator's side to mourn. It then treats every
in-flight agent as an interrupted agent under this document, one briefing each. The one
asymmetry: the briefer is the party that lost its memory, so the evidence-not-inference
sentence binds hardest here — the second crash's briefing said "no verification evidence
survives on my side" outright, which is what let the resumed agent re-verify from scratch
rather than trust a ghost's summary.

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

The briefing states what the evidence shows, not what it implies. "Clean, zero ahead" is
proof of committed-and-pushed, yet one briefing asserted from it that announced work had
died uncommitted — the agent had pushed and then continued, so the same evidence meant
landed, not lost (2026-08-02). Landed-vs-lost is the resumed agent's to verify on wake,
and that verification — the agent checked the tree and corrected the orchestrator rather
than redoing landed work — is why the error cost nothing.

## The resumed agent's side

The briefing is a contract with two sides. On wake, before building on anything, the
resumed agent must:

- `git fetch origin` and read what landed since its last commit, plus open-issue comments
  for claims made while it slept;
- re-verify every claim its transcript makes that the briefing marks moved — ADR numbers,
  ownership, eliminations — rather than trusting its own memory over the tree;
- treat its dead run's uncommitted output and in-flight results as ADR-0022 stale state:
  redo the verification, do not cite the corpse;
- audit any blanket checkpoint (`git add -A`) taken around the death by diff, not by
  file list: a checkpoint can sweep in pre-landing copies of files other agents have
  since landed, so replaying it reverts their work on `main`. Read the staged diff
  against `origin/main` and confirm every hunk is yours — #164's checkpoint carried the
  pre-#167 copy of `block-no-verify.py` after #167's fix had landed in between, and the
  revert showed only in `git diff --cached`, never in the file list.
