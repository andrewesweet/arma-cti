# The orchestrator watches the work, not the clock, and its self-checks fail closed

Delegated-decision: yes
Date: 2026-08-02
Stood-in-for: human sign-off on changes to CLAUDE.md, the project skills, and the agent
process docs — the eighth retro's amendment batch (five issues: #45, #48, #26, #50, #46)
Reviewed-by-human: 2026-08-02

## The decision

Four amendments, one of them the headline.

1. **`docs/agents/recovery.md` gains the orchestrator's side of the recovery contract: a
   section on noticing death in time.** Three points, each with a measured instance from
   this cycle: check an agent at its work's completion edges rather than on wall-clock
   (the watchdog-loop pattern — background loop re-invoking the orchestrator on server
   exit, re-armed each cycle, plus grace-then-nudge — proven in-session and previously
   living only in a transcript); a self-check must fail closed (`pgrep -f arma3server`
   matched the orchestrator's own command line and reported SERVER-LIVE for hours over a
   dead server, while the #46 agent sat stalled ~8 h with a *finished* pass nobody read);
   and nested subagents report to the spawning session, not their parent agent (#48's
   strands, ~15k tokens of relay double-handling). Runbook marker: `validated ×2` → `×5`
   on #46's three clean briefed resumptions, amended for the gap those stalls exposed —
   the runbook covered *how* to recover and nothing covered *when to look*.

2. **`docs/agents/triage-labels.md` widens `ready-for-human` to "requires human action
   first"** — implementation, or the opening step of otherwise-agent work. Ratifies #50's
   deliberate deviation (#52 commissioning machine B, #54 buying a licence): both issues
   are mostly agent work that a human action gates, and the label's plain meaning already
   said the human goes first. Adopted as vocabulary rather than recorded as drift.

3. **CLAUDE.md's elimination-context line widens to inherited measurements** and earns
   ×2 on #26: the issue's diagnosis ("Squad count binds, island size barely matters") was
   measured while the Observation carried both rosters; #27/#28 had since made the enemy
   term grow with the map, and re-measuring before designing inverted it — ADR-0030
   charges the budget to the island because the agent re-measured first. No new named
   "re-measure before designing" rule: it is this rule with four more words.

4. **Marker bumps**: probe-window `×5` → `×6` (#46 kept `two-commanders`' floor a second
   time and made its absence claims 2 s watchers — strictly stronger, window unmoved);
   ADR-claiming `×3` → `×4` (#49's mid-flight 0030 → 0031 renumber, found on the rebase,
   exactly as prescribed); retro skill `×7` → `×8`.

## Rejected alternatives

- **Leaving the watchdog pattern as transcript lore.** Rejected: the fail-open
  self-observation shape is now at three instances (#41's bare `tasklist.exe`, #44's
  daemon-address defaults agreeing with themselves, this cycle's `pgrep -f`), the cost is
  measured (~8 h of unnoticed stall), and the fix is proven in use — which is exactly the
  bar the last retro set when it declined a rule at two instances and left a comment on
  #5 instead. The harness side of the shape stays where it is; this lands the
  orchestrator side where the orchestrator reads.
- **A runbook cadence rule separate from the watchdog** ("poll stalled agents every N
  minutes"). Rejected as the clock-watching that just failed; the section says to watch
  the work's own completion edges, and the watchdog is the exemplar mechanism, not a
  prescription of its implementation.
- **A new named CLAUDE.md rule for #26's re-measure-before-designing.** Rejected:
  over-prescription; the elimination-context line already says it about eliminations, and
  widening it is smaller than a sibling rule.
- **Treating #50's `ready-for-human` labels as drift to revert.** Rejected: the label
  exists, its meaning already puts the human first, and the deviation read it plainly;
  the widened wording records what the label demonstrably means here.
- **A failure-class earn or new class this cycle.** None. The `pgrep` lie is outside the
  verdict system (orchestration, not a harness verdict), and #45's
  dirty-world-would-have-passed finding is #44's false-green shape again — a harness
  lying green cannot type its own lie; the defence remains structural (#45 declined
  multiplexing for exactly this). Table stays `validated ×5`.
- **Process changes for the four directed reviews (#55–#58).** None needed: findings land
  as prioritised backlog issues through the existing tracker machinery — creation, triage
  labels, closing discipline, decision-ticket escalation all apply unchanged, and nothing
  in the docs blocks any of it.

## What would overturn this

- The watchdog pattern producing false nudges that cost more than the stalls it catches,
  or the Phase-3 orchestrator (#5) replacing transcript-driven orchestration with a
  harness-level completion signal — either retires the recovery.md section in favour of
  the mechanism that supersedes it.
- A human-action-first issue rotting under `ready-for-human` because no agent looked at
  it again — that would argue for a distinct label after all.
- An inherited measurement whose context was re-checked and still misled — that would
  say the elimination-context line's remedy is too weak, not merely under-applied.
