# A worktree is verified exclusive before work, and the review queue clears through a guided session

Delegated-decision: yes
Date: 2026-08-02
Stood-in-for: human sign-off on CLAUDE.md changes and the process-doc/skill markers (fifteenth retro's amendment batch, session unattended)
Reviewed-by-human: pending
Claimed: comment on #105, 2026-08-02, after `git fetch origin` (origin/main at
`165c45d`, `docs/adr/` topping at 0046) and a scan of open-issue comments
finding no claim above 0046

Amendment batch for the fifteenth retro (scheduled: five closes since `2a880f3`
— #132, #133, #134, #137, #138 — plus #105's instances 3–5 in one evening and
the #131 guided review session clearing all 29 pending ADRs). Full findings:
`docs/process-log.md`, entry 2026-08-02 (fifteenth retro).

## Decisions

1. **The worktree pre-flight is standing mitigation while #105 is open.** A new
   working-style bullet in CLAUDE.md: before any work in a worktree, verify it
   is exclusively yours (clean `git status`, no foreign uncommitted files
   appearing during the run), commit early and often, and on finding foreign
   files stop and report — never reset. `docs/agents/recovery.md` gains the
   shared-assignment variant of the worktree mode beside the vanish variant.
   Evidence: #105's instances 3–5 — worktree assignment handed two agents one
   tree five times in one evening, instance 3 destroyed the #132 agent's
   uncommitted edits, and the improvised pre-flight prevented a repeat on its
   first firing (instance 5, this retro's own first dispatch). Past the
   two-improvisation codification threshold with a demonstrated save.

2. **The flake-baseline clause's earn is recorded in its row.** CLAUDE.md's
   `flake_quarantine` row gains the two first-cycle earns: #132's
   four-arrangement table (10/10 red pre-fix, 0 post) and #138's 5/5-refused vs
   5/5-granted with the holder named by pid — plus #138's incidental finding
   that stating the arrangement exposed the old test's arrangement as never
   reproducing the linger, i.e. the rule also catches non-load-bearing tests.

3. **The queue-clearing mechanism's convention lands, now its first run is
   complete.** `docs/agents/issue-tracker.md` gains a section describing the
   guided review session shape #131 held to (one verdict comment per ADR, flips
   as one commit, worklist grep quoted at close-out, nitpicks filed not folded
   in, scope expanded only on instruction, anomalous verdict lines queried).
   The fourteenth retro deferred this under the convention-lands rule; the
   session has since closed out all 29 ADRs (landed `4a83025`), so the sentence
   lands with its first applied instance. Convention-lands moves ×3 → ×4 on
   the deferral-then-land as exemplar.

4. **Step 3's queue grep is anchored.** The retro skill now counts
   `grep -rl "^Reviewed-by-human: pending" docs/adr/`, matching ADR-0013's
   canonical worklist form. Evidence: after the #131 approvals, the unanchored
   form over-counted 6-for-1 (five prose mentions of the string in approved
   ADRs against one genuinely pending).

5. **Markers.** Retro skill ×14 → ×15. Recovery runbook count corrected
   ×8 → ×9 — the fourteenth retro's commit added the ninth use without moving
   the count, the first violation of the step-5 same-edit clause since it was
   written; recorded in both status blocks, with a second violation escalating
   to a mechanical check per ADR-0038's shape. Sixth recovery-runbook
   amendment: the shared-assignment variant (decision 1).

## Rejected

A relay rule for cross-agent diagnosis (#134's incidental reproduction reaching
the #132 agent mid-flight is orchestration working, not a doc gap). Text for
#134's SHA-vs-landed honesty (the ground-progress-claims bullet already binds
it), and a sharper edge for the same agent's quote-before-read violation — it
quoted a 20/20 verdict banner no tool result yet contained, right by luck, and
self-corrected on the record afterwards; first instance of the shape, the
proposed sentence would enumerate a case the bullet already forbids, and a
second instance escalates per the trailer precedent that self-correction is
not the gate holding. A rule from #137's grep-not-heading gate fitting (journal exemplar). A
sentence for the #79/#82 agent's turn-ending "standing by" wait (first
instance, below the two-improvisation threshold; recurrence earns it). A
mechanical marker-count check now (first violation of the written clause; the
escalation condition is stated instead). Failure-class earns for #133's
dirty-slot `infra_unavailable` typing (machinery operating).

## What would overturn this

- **Decision 1** falls when #105 resolves at the harness level — the bullet
  then shrinks to whatever residue the confirmed cause leaves, and a pre-flight
  that never again finds a foreign file across, say, twenty isolated dispatches
  is evidence to remove it rather than keep paying its line. It also falls if
  stopping on foreign files ever proves more destructive than proceeding
  (nothing observed suggests it can be).
- **Decision 2** falls with the flake-baseline clause itself: a fix whose
  stated baseline misleads a later recurrence worse than no baseline would
  have.
- **Decision 3** falls if the second queue-clearing session cannot reuse the
  shape — e.g. the human prefers batch verdicts without per-ADR comments — at
  which point the section is rewritten from that session, not defended.
- **Decision 4** falls only with ADR-0013's anchored form itself.
- **Decision 5's escalation condition** fires, rather than falls, on a second
  same-edit violation; it falls if the check proves unbuildable against prose
  ordinals without false positives, in which case the clause stays behavioural.
