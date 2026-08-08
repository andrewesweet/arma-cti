# A ruled decision lands by its stated vehicle, and the watcher's compensation is permanent

Delegated-decision: yes
Date: 2026-08-04
Stood-in-for: human sign-off on CLAUDE.md, process-doc and skill marker changes — the
twentieth retro's amendment batch (session unattended)
Reviewed-by-human: 2026-08-08
Claimed: comment on #186, 2026-08-04, after `git fetch origin` (`docs/adr/` on
`origin/main` topping at 0052) and a scan of every open issue's comments finding no
claim above 0052

Amendment batch for the twentieth retro (scheduled: five closes since `ba8961f` —
#159, #162, #169, #181, #185). Full findings: `docs/process-log.md`, entry 2026-08-04
(twentieth retro).

## Proportionality

Weighed per the eighteenth's precedent, against a queue at 1 (0051). Journal-only was
the live default and most of the cycle stays there — the diagnostic exemplar, the
slot-0 fork, the cadence question all journal without a rule. What earns application
now is count-and-exemplar upkeep (whose deferral is the fifteenth's named defect) plus
two one-sentence records of things the cycle settled: the decision-ticket convention's
second clean run, and the watcher attribution's end state. One batch ADR, no new
rules, queue re-opens at 2.

## Decisions

**1. The decision-ticket convention takes its second exemplar (#169) in
`docs/agents/issue-tracker.md`.** The convention's first full run since its #31
exemplar, clean end to end: the guided session's rulings closed as ADR-0052 plus #188
and #189 in dependency order, no code on the ticket, same evening. The exemplar also
records where the convention's slack sits, because #169 exercised it: the ruling
comment explicitly left two names to the implementing ADR, and the agent's correction
of the working `commander_down` to `caller_dead` was made on ruling 5's own logic
(one code for both principals), alongside the load-bearing placement finding (a
post-resolution check would type a dead leader `wrong_side`) and a deliberate
non-filing for the engine-owned half, verified against the vendored wiki. Names and
placement to the implementer, rulings to the session.

*Overturned by*: an implementing agent "correcting" a ruling rather than a working
name — the slack clause then over-teaches and the exemplar needs a sharper boundary.

**2. Recovery runbook ×11 → ×12; the noticing clause states the compensation is
permanent.** Fourth stall, fourth watcher catch (#162's agent, parked after its corpus
finished; orchestrator's watcher, prodded with the verdict in hand), zero prevented or
caught by text. The nineteenth already named the defect — a parked run's completion
does not wake the agent that parked it — harness-level; the runbook now says what
follows: it is Claude Code harness behaviour, not this repo's to fix, so the watcher
is the permanent compensation rather than a stopgap awaiting an in-repo fix, and
further catches are it working, not new findings. This closes the attribution thread
the eighteenth opened and the nineteenth scored; retros stop re-litigating it.

*Overturned by*: the harness gaining run-completion wake-ups (the sentence then
retires with the watcher's necessity), or a stall the watcher misses.

**3. CLAUDE.md's ADR-0049 bullet records the migration's track: three conversions,
clean.** The nineteenth deferred a marker "until #162 lands"; #162 landed (its shim
and harness items), and #185 landed seam 2 the same evening — `tools/probe_verdict.py`,
`tools/host_guard_verdict.py` (#161), `tools/pool_merge.py` (#185), each red-first
pins into one Python home with every caller failing closed, zero regressions, and
\#185 honouring the coordination note by routing the class-table residue to #92/#147
at the `CLASS_RANK` comment rather than leaving a parallel table. The bullet's
parenthesis replaces "first instance" with the three-conversion record so the next
migrating agent inherits the pattern's standing, not its birth.

*Overturned by*: a conversion regressing the tier — the record then gains the failure
rather than being reverted.

**4. Elimination-context ×6 → ×7 (#159's ground-shift check).** #159 inherited a
filed finding whose line number the tree had moved under (#79/#82 moved the spawn
count onto the roster), checked rather than trusted it, found the live reader of the
invented 8 was by then the `squad_reinforced` arm, and fixed both squad arms — stating
the shift in the close. First application of the line to a filed defect's ground
rather than a measurement, rationale, or work list; exemplar appended in the same
edit.

*Overturned by*: the exemplar list's own length doing harm, per ADR-0051 decision 2's
prune clause.

**5. Retro skill ×19 → ×20.** Twentieth run, unattended, no procedural
self-amendment. The header records the cycle's shape: every decision the cycle needed
arrived pre-ruled from the guided decision-capture session, the outputs flowed through
four distinct vehicles (decision ticket → ADR + issues; ruling → prototype ticket;
ruling → issue-comment decision, deliberately not an ADR per the issue's own
criteria; ruling → same-evening implementation) without a new rule, and the one
approved-but-queued edit landed by executing the sign-off.

*Overturned by*: nothing specific — the count reverts cleanly if rejected.

## Recorded here, not delegated

- **The `just generate` row and the `just check` row's generated-schema mention in
  CLAUDE.md's command table** are not a delegated decision: they execute the human's
  explicit sign-off on #162 (2026-08-04: "the human approves adding the `just
  generate` row to CLAUDE.md's command table (alongside its `check-generated` guard
  being reflected wherever the table's cog/lint row already covers it). This comment
  is the sign-off; the row edit itself flows back through the orchestrator's queue").
  Listed for transparency because they ride in this batch's commit; the wording is
  \#162's proposed row verbatim.
- **A human-gated leftover, flagged not taken**: ADR-0027's sentence "the only thing
  that lowers the demand is somebody looking" now holds of the banded half only —
  \#181's committed-force floor, implemented under the human's hysteresis ruling on
  \#177/#181, qualifies it. The amendment's record lives in `src/cti_daemon/planner.py`'s
  `_mass` docstring and #181's closing comment; the ADR file itself carries no
  pointer. Whether ADR-0027 gets an amendment note is the human's call at review —
  editing an approved ADR is exactly what the gate covers, and the ruling's substance
  is already human-approved, so nothing is at risk while it waits.

## What would overturn this

- The human rejecting any decision above at review: each is a count, an exemplar, or
  a one-sentence record, named above, and reverts cleanly.
- The per-decision overturn rows above.
