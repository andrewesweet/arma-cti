# An agent watches from inside its turn, and a defect named in a close-out gets filed

Delegated-decision: yes
Date: 2026-08-04
Stood-in-for: human sign-off on CLAUDE.md changes and the process-doc/skill markers (seventeenth retro's amendment batch, session unattended)
Reviewed-by-human: 2026-08-04
Claimed: comment on #168, 2026-08-04, after `git fetch origin` (origin/main at
`3cb4db0`, `docs/adr/` topping at 0047) and a scan of open-issue comments
finding no claim above 0047

Amendment batch for the seventeenth retro (scheduled: five closes since
`a1cc654` — #141, #144, #163, #180, #164 — plus the disk-exhaustion crash
cluster, #181's filing, and #168's fix committed but stalled unlanded). Full
findings: `docs/process-log.md`, entry 2026-08-04 (seventeenth retro).

## Decisions

1. **The watching-inside-turn sentence lands, on the recurrence the fifteenth
   retro named as its price.** A new working-style bullet in CLAUDE.md: an
   agent watching a run watches it from inside its turn — nothing an agent
   arms outlives its turn, so a turn that ends "standing by" or "monitor
   armed" is a wait nothing will wake. ADR-0047's rejected list deferred
   exactly this sentence as a first instance and said a recurrence earns it.
   Evidence of recurrence: two "monitor armed" claims on 2026-08-04 coincided
   with stopped-with-no-live-children task notifications (orchestrator's
   report), and the #168 agent stalled twice in one evening at the identical
   point — background `just unit` launched, run finished, agent never woke to
   read it — its completed fix (`e24e25d`) sitting committed on no branch,
   unlanded and unannounced, until the orchestrator's external watcher found
   it; both stalls needed an explicit prod naming what had finished.
   `docs/agents/recovery.md`'s noticing section gains the orchestrator-side
   complement, stated as standing rather than ad-hoc on the second identical
   save (the runbook's own codification threshold): an agent dispatched with
   a run attached gets a watcher armed at dispatch.

2. **A defect a close-out names "worth its own issue" is filed in the same
   session.** One short section in `docs/agents/issue-tracker.md`. Evidence:
   twice in one cycle a close named a defect worth filing and filed nothing —
   #164's attempt-3 comment ("A separate defect this exposes, worth its own
   issue": the admission gate's per-slot figure) and #163's close ("Worth a
   look separately (not filed here)": cross-agent machine-wide memory
   exhaustion) — while `docs/regression-tier.md`'s own "worth a look if it
   recurs" line also recurred with no issue. Triage selects from the tracker,
   not from prose in closed issues. First applied instance lands with the
   convention: this retro files the memory-floor issue those two closes named.

3. **A crash-recovery checkpoint is audited by diff, not by file list.** One
   bullet in `docs/agents/recovery.md`'s resumed-agent section: a blanket
   `git add -A` checkpoint taken around a death can sweep in pre-landing
   copies of files other agents have since landed, so replaying it reverts
   their work; read the staged diff against `origin/main` and confirm every
   hunk is yours. Evidence: #164's checkpoint (`3c1b9e0`) carried the
   pre-#167 copy of `block-no-verify.py`; #167's fix (`db16aa8`) landed on
   `main` in between; the revert was caught only in `git diff --cached`. A
   single instance, but the failure mode is another agent's landed fix
   reverted silently on `main` — the same class that earned the
   evidence-not-inference sentence from one instance.

4. **Markers.** Failure classes ×7 → ×8: #164's five corpus attempts, of
   which only the fifth was a result — a host-guard refusal and a crash-killed
   half-run each correctly not-a-result, attempt 3's `node_crashed` escalated
   with the box's own trace quoted rather than retried or pinned on the diff,
   vindicated when the human found OS disk exhaustion and the healthy-box
   rerun passed 21/21; the first end-to-end run of that row's
   collect-and-escalate response. Elimination-context ×4 → ×5: the same
   escalation checked its fresh 19 MiB reading against #124's disproved
   memory-edge hypothesis and found the contexts differ (a bring-up never
   below 3.9 GiB is not a running pool at 19 MiB), so the prior disproof was
   not inherited as a reason to look away. Recovery runbook ×9 → ×10: the
   crash cluster — four orchestrator deaths in one window (orchestrator's
   count; in-repo corroboration in #164's attempt-2 kill and
   crash-recovery-checkpoint note and #144's attempt-3 loss), every recovery
   the codified move at near-zero cost to commit-early. Retro skill
   ×16 → ×17.

## Rejected

Adding the harness (`spike/run.sh`, `regress.sh`, `host-guard.sh`) to the
full-corpus gate's surface list after #144 landed corpus-less: the letter of
the gate excludes harness-only changes, the agent said so explicitly rather
than skipping silently, the #83 unit-tested classification layer is the
designed no-Arma gate for harness logic, and the corpus's own traffic
validated the new harness within two hours (#163's 20/20) and fully the next
day (#164's 21/21). A flake-row earn note for #181 (the row operating as
written, at filing rather than at fix; growth of the row resisted). A rule
from the fail-open class's second recurrence (#168 — the issue machinery is
handling it; each recurrence has been one layer further out, which is a fact
for the issue, not a rule). Any change to "fewer slots free is a smaller
pool, not a failure" (the floor question is code behaviour, owned by the
issue this retro files, not prose). Note one reversal mid-retro: the draft
rejected an orchestrator watcher rule beyond recovery.md's existing noticing
section as scheduling-not-doc-text, and the #168 agent's second identical
stall arrived while the retro ran — two identical external saves in one
evening is the codification threshold, so the standing-watcher sentence
landed instead (decision 1).

## What would overturn this

- **Decision 1** falls if the harness ever gives subagents a wake-on-event
  mechanism that survives a turn boundary — the sentence then describes a
  limitation that no longer exists and should shrink to whatever residue
  remains.
- **Decision 2** falls if it produces issue spam — closes filing trivia to
  discharge the sentence rather than judged defects — at which point the
  judgement moves back into prose and the sentence is removed.
- **Decision 3** falls if a checkpoint-diff audit across, say, ten recoveries
  never again finds a foreign hunk, or if reading the diff proves more
  error-prone than an automated foreign-hunk check, which would supersede the
  manual bullet.
- **Decision 4's counts** fall with their exemplars: the failure-class earn if
  the disk diagnosis is overturned (the readings were the box's, not the
  code's, and a re-diagnosis would re-open what the class table is credited
  with catching); the elimination-context earn with it; the runbook count if
  the cluster's recoveries are shown to have lost work commit-early should
  have saved.
