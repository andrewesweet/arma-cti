# A flake fix states its reproduction baseline, and an orchestrator death is a known mode

Delegated-decision: yes
Date: 2026-08-02
Stood-in-for: human sign-off on CLAUDE.md changes and the process-doc/skill markers (fourteenth retro's amendment batch, session unattended)
Reviewed-by-human: pending
Claimed: comment on #131, 2026-08-02, after `git fetch origin` (origin/main at
`2bd98dc`, `docs/adr/` topping at 0045) and a scan of open-issue comments
finding no claim above 0045

Amendment batch for the fourteenth retro (scheduled: five closes since
`8a035ec` — #127, #129, #128, #126, #130 — plus #131 opened and now running,
#132–#135 filed, and the second orchestrator-process death). Full findings:
`docs/process-log.md`, entry 2026-08-02 (fourteenth retro).

## Decisions

**1. The `flake_quarantine` row now demands a reproduction baseline.** #130 was
the third round of one flake (#121 orphan fd, #122 duplicate, #130
`proc.wait()` vs last-fd-close), and what finally settled it was not a pass
rate but the mechanism argued and *measured* — the 3.0/7.4 ms race window,
then 535 reproductions of the exact arrangement producing zero reds, stated
honestly so a future recurrence knows this box never reproduced the failure it
was fixing. Rounds one and two argued from pass rates and each bought one more
round. The row's required response gains the demand: state the fix's
reproduction baseline — arrangement, run count, reds, pre- and post-fix — in
the flake's issue. #132 already carries the demand as an acceptance criterion,
filed by #130's agent unprompted; this lands the sentence where every
flake-fixer reads first.

*Overturned by*: the baseline proving theatre — a fix whose stated baseline a
recurrence shows was measuring the wrong arrangement would mean the demand
needs to name what an arrangement is, or be dropped as false comfort.

**2. The orchestrator's own death is a section in the recovery runbook, not an
improvisation.** Two host-process crashes (both 2026-08-02), both recovered at
zero cost by the same unwritten move: rebuild the picture from `main`, the
issues, the agents' worktrees, and the harness's task notifications — the
orchestrator holds no durable state of its own — then brief every in-flight
agent as an interrupted agent. Two identical improvisations is the threshold
the runbook's own worktree-vanish mode was codified at, so the section lands,
with the one asymmetry stated: the briefer is the party that lost its memory,
so evidence-not-inference binds hardest ("no verification evidence survives on
my side", the second crash's briefing, is the model). Runbook ×8 → ×9 in the
same batch (ninth use: #130's resumption, exemplar in the same edit).

*Overturned by*: an orchestrator death whose recovery needs something the
section does not name — state the successor could not rebuild from those four
sources — which would show the "no durable state" premise wrong.

**3. The landing paragraph names the sandboxed-agent hand-back.** #130's agent
could not run the ff-only merge in the shared checkout (worktree isolation)
and handed it back to the orchestrator explicitly — the correct move, written
nowhere. The failure mode of the silent alternative is concrete: a main
checkout that quietly stops tracking `origin/main` is exactly where ADR-0042's
stale-hook window comes from. One sentence in CLAUDE.md's landing bullet.

*Overturned by*: the sentence proving unnecessary — if sandbox policy later
lets landing agents run the merge, the sentence reverts to noise and goes.

**4. Marker moves.** Recovery runbook ×8 → ×9 (decision 2). Retro skill
×13 → ×14 (fourteenth run, no self-amendment needed; the concurrent #131
session is step 3's queue being cleared at the human's cadence, not a skill
change). Counts and exemplars moved in the same edits per the step-5 clause.

## Rejected in the same pass

- **Any amendment for #131's clearing mechanism.** The guided review session is
  running *now* — scope expanded in session on the human's instruction, four
  verdicts recorded one-comment-per-ADR, a nitpick filed as #134 rather than
  folded in, long-term intent preserved as #135 — but it has not completed. A
  first instance running well is not yet a convention (the convention-lands
  rule); it earns its sentence in the issue-tracker doc when the session
  closes #131.
- **A marker or rule for ADR-0038's overturn clause firing as designed.** #129
  escalated the trailer ban to a commit-msg hook exactly as the clause
  predicted, and proved the gate live on its own landing. That is an overturn
  section doing its job, recorded in the journal as the first executed one;
  the ADRs' overturn sections carry no marker to move, and inventing one for
  a first instance is the exemplar route's job.
- **A rule encouraging brief-refusal-with-reasoning.** #130's agent refused the
  briefing's grace-on-acquire suggestion with recorded reasoning and was right
  to. The working-style paragraph already licenses exactly this; a second
  instruction would be over-prescription.
- **Any text for phoned-in decision recording.** Three decisions delivered in
  one mobile reply landed at `e850c94` quoting verbatim, verifying an
  orchestrator claim against ADR-0025/#42 before writing it, and correcting a
  stale key-row in passing. No friction observed; nothing to fix.
- **A wider flake-rounds convention** (beyond decision 1). Rounds two and three
  were not expensive for lack of records — #130's body carried the arrangement
  and the suspected mechanism — but because the mechanism was subtle. The
  baseline sentence is the part with evidence behind it.

## What would overturn this

- The human rejecting any decision above at #131-style review: each is one
  sentence, one section, or one marker, named above, and reverts cleanly.
- The per-decision overturn rows above.
