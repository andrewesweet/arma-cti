# A hook governs from the session's worktree copy, not from main

Delegated-decision: yes
Date: 2026-08-02
Stood-in-for: human sign-off on CLAUDE.md changes, an ADR-0013 amendment, and the retro/recovery markers (twelfth retro's amendment batch, session unattended)
Reviewed-by-human: pending

Amendment batch for the twelfth retro (scheduled: eight issues closed since
`536706f` — #47, #117, #118, #120, #61, #62, #63, #51; #122 closed as a duplicate
of #121). Claimed by comment on #123. Full findings: `docs/process-log.md`,
entry 2026-08-02 (eight issues).

## Decisions

**1. CLAUDE.md's hook paragraph states where a hook's code actually runs.**
Claude Code hooks execute from each session's own worktree copy of
`.claude/hooks/`, not from `main`. During #120's fix, a *fourth* false positive
fired from the orchestrator's still-stale copy while the corrected hook already
sat in the fix agent's worktree; the orchestrator then rebased its worktree to
pick the fix up. Without the sentence, the two documented readings of a denial
are both wrong in that window: CLAUDE.md says a denial signals a gated surface
(it was prose, not a gated surface), and the natural inference is that the
landed fix failed (it had not run). One sentence in the hook paragraph closes
both misreadings. A `docs/agents/recovery.md` line was considered and declined —
the quirk is hook semantics, not interrupted-agent recovery, and the reader who
needs it is whoever just got denied, standing in front of CLAUDE.md's hook
sentence.

*Overturned by*: evidence that hooks resolve from `main` or from the settings'
repo root regardless of worktree (e.g. a stale-copy denial that cannot be
reproduced after this harness behaviour changes), at which point the sentence is
deleted rather than qualified.

**2. ADR-0013 names the `Delegated-decision: no` form.** Three ADRs this cycle
(0039, 0040, 0041) record decisions the human took directly, in session, and
each improvised the same marking: `Delegated-decision: no` plus a
`Reviewed-by-human:` line naming the in-session decision. The convention text
only defined the `yes` form, so the practice existed with no words — the
convention-lands rule applied to the convention's own document. The amendment
records the form; the `yes` grep remains the complete delegation set.

*Overturned by*: the human preferring their own decisions kept out of
`docs/adr/`'s field-block scheme entirely, in which case 0039–0041's blocks are
reworded to whatever they choose and the paragraph is removed.

**3. ADR claiming keeps claim-by-comment; a central next-number file is
declined.** This cycle produced the rule's heaviest concurrency yet — the
0039→0040→0041 renumber chains across three concurrent landings — and the rule
held each time: every collision was found on the rebase and renumbered as
prescribed. The churn is real, but a next-number file is a path every ADR
landing must touch, which converts number collisions into merge conflicts on
one file whose resolution is the same renumber plus a file to keep honest. The
churn is the cheap answer. Marker moves to ×5 with this cycle as the exemplar.

*Overturned by*: a renumber chain that loses content or mis-links references
(the failure the rule's cost is supposed to stay below), or claim volume growing
past what fetch-and-scan can keep coherent.

**4. Marker moves** (each with its exemplar in the same edit, per the retro
skill's step 5): elimination-context ×2 → ×3, widened by two words to cover an
inherited rationale (#118: the review's keep-reason — "a supervisor that can
restart them" — had expired when #102 landed restart-refused; the agent
re-derived a surviving reason rather than inheriting the expired one).
Convention-lands-with-instance ×2 → ×3 (#118 landed ADR-0041's convention, the
macro pair, the lint, and the 19 guard deletions in one commit).
Recovery runbook ×7 → ×8 (#51's stall, resumed clean off a briefing to the
document's contract). Retro skill ×11 → ×12. Failure classes stay ×7 and
probe-window ×6 — #47's class-identical pool verdicts and #124's correct
`node_crashed` are the machinery operating, not new earns.

*Overturned by*: the standard route — a marker's next failure downgrades it.

## Explicitly not changed

- **Away-mode needs no new text.** The human accepted two items, deferred the
  rest, and left; the session runs unattended for days. The existing machinery
  already defines that state completely: gated decisions proceed as delegated
  ADRs under ADR-0013/0019 with `Reviewed-by-human: pending`, the retro reports
  the queue depth each cycle, human-first work waits under `ready-for-human`
  (which already means "requires human action first"), and nothing pages. No
  instruction exists to add that is not already operating.
- **No duplicate-scan-before-filing rule** (#121/#122): one duplication in ~124
  issues, both filings honest, deduplicated for the cost of one comment. A
  standing scan taxes every filing to save that comment.
- **Nothing from #47/#51/#124's build ground** — the exploration-as-audit
  paragraph, honest-remainder handling, and #124's if-it-recurs structure all
  ran as already written; code follow-ups live in their issues.
