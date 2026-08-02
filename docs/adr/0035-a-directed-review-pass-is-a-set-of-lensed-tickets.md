# A directed review pass is a set of lensed tickets, and a lost worktree is a death mode

Delegated-decision: yes
Date: 2026-08-02
Stood-in-for: human sign-off on changes to CLAUDE.md, the project skills, and the agent
process docs — the ninth retro's amendment batch (the review phase: #55–#58, #95, #49,
and fixes #59, #60, #67, #68, #69, #81, #83)
Reviewed-by-human: 2026-08-02

## The decision

Four amendments.

1. **`docs/agents/issue-tracker.md` gains a "Directed review passes" section.** The human
   triggered the first whole-project review ad hoc; five tickets (four parallel fable
   lens reviews + one extension) independently held to one deliverable shape — rubric
   self-assessment against a stated numeric target, full sweep before severity filtering,
   findings as severity-tagged backlog issues, priority ordering against the open backlog
   — and two concurrency disciplines emerged and held: note a neighbouring lens's finding
   rather than re-filing it, and cite an in-flight fix as evidence rather than filing
   over it (#95 did both). ~45 findings flowed through the normal tracker machinery and
   the first seven were fixed the same day. The section captures the ticket shape and the
   two disciplines so the next phase boundary reuses them instead of re-deriving them.
   It also carries the scope lesson as one line: #58's harness-scoped review left the
   play path to an extension ticket, and that extension (#95) produced the cycle's worst
   score (~5/10) on exactly the surface no automated tier exercises.

2. **`docs/agents/recovery.md` gains the worktree-vanish death mode.** Twice (the #48
   research session's strands, the #56 review — which lost 14 config files unreviewed,
   #94), a live agent's isolation worktree disappeared mid-run and Bash refused with
   "isolated worktree no longer exists". The existing stale-state rule covers a *dead*
   agent's leftovers, not a live agent losing its ground, and the response was improvised
   identically both times, which is this runbook's own bar for writing it down: finish
   read-only from the main checkout, never commit there, name the gap as an issue, treat
   anything uncommitted as dead. Cause is unobservable from inside a session; #105 tracks
   it for the human, with the hypothesis that both victims were read-only sessions whose
   commit-free worktrees the harness reaped as "unchanged".

3. **The retro skill's step 5 gains the same-edit clause** (`×N` and its appended
   exemplar move together). The last retro commit appended the #46 and #49 exemplars to
   the probe-window and ADR-claiming markers without bumping ×5/×3 — the exact drift the
   retro before it had corrected once and judged "the log catches it" sufficient. Twice
   in two consecutive retro commits, both under step 5, is a failure of the step, not of
   attention; one sentence in the step is the smallest fix. Both labels corrected.

4. **Marker moves**: failure classes `×5` → `×6` (#83: `run.sh`'s non-hold path retyped
   every in-mission FAIL as `assertion_failed`; found by review because a wrong class is
   by definition a harness bug, and the fix made classification unit-testable in the
   no-Arma tier — a wrong class is now a red `just unit`); probe-window label corrected
   to `×6` and ADR-claiming to `×4` (the lagged bumps ADR-0033 already recorded);
   recovery runbook stays `×5`, amended (no resumption ran through the document this
   cycle; the vanish recoveries were improvised outside it); retro skill `×8` → `×9`.

## Rejected alternatives

- **Leaving the review pass as precedent in the process log.** Rejected: the shape was
  reproduced five times within the instance and the human triggered it ad hoc, so
  without a written home the next boundary re-derives the ticket from transcripts. The
  section is descriptive of what already happened, not new prescription — the
  over-prescription bias cuts against inventing process, not against recording one that
  ran.
- **A standing production-lens review at every phase boundary.** Rejected: the score
  spread (game code 8.5–9, harness 7–8.2, play path 5) shows verification investment
  protected exactly the tested surfaces, but the designed standing production lens is
  the playtest loop, which has not yet had its first session — mandating a second
  standing instrument before the first has run once would be premature. #95's findings
  (#96–#103) are the catch-up; the scope-the-production-surfaces line in the review
  section is the durable residue. A second phase boundary showing the same spread would
  reopen this.
- **Naming the /tmp-file relay as the nested-agent pattern.** Rejected: second instance
  (#56's sweep slices, after #48's strands) confirms the existing recovery.md
  known-behaviour line, and the double-handling (~15–20k tokens per occurrence) is a
  harness quirk to be retired by better plumbing, not a pattern to ossify by
  specification. The line stands unchanged.
- **Codifying severity-first, ground-partitioned burn-down waves.** Rejected: one
  orchestration instance, working as designed under the human's directive — a
  scheduling call, the same reason parallel-dispatch partitioning stayed uncodified two
  retros ago.
- **A failure-class earn beyond #83, or a new class.** None: the review cycle's false
  greens (#81's cycle.sh, #97's error-shaped-as-success) are again the shape the table
  cannot type — a harness or world lying green cannot classify its own lie; the defence
  stays structural, as decided at #44/#45.

## What would overturn this

- A second directed review pass finding the section's shape wrong in use — a lens that
  cannot self-score against a rubric, or the note-don't-refile discipline losing a
  finding — would amend or retire the section.
- The vanish cause (#105) turning out to be something other than reaping-unchanged, or
  a harness fix landing, would rewrite or delete the recovery.md paragraph.
- A third count/list lag despite the same-edit clause would say the fix is at the wrong
  layer and the count should be derived from the list rather than stated beside it.
- A first playtest session failing to surface play-path resilience defects of #95's
  class would revive the standing production-lens review this batch declined.
