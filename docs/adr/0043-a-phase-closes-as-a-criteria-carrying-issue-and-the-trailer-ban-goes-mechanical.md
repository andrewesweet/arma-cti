# A phase closes as a criteria-carrying issue, and the trailer ban goes mechanical

Delegated-decision: yes
Date: 2026-08-02
Stood-in-for: human sign-off on CLAUDE.md changes and the process-doc/skill markers (thirteenth retro's amendment batch, session unattended)
Reviewed-by-human: pending

Amendment batch for the thirteenth retro (scheduled: five issues closed since
`af4c09b` — #123, #104, #121, #125's landing, #24 — plus the phase boundary:
#3's four acceptance boxes all tick, `docs/command-port-audit.md`). Claimed by
comment on #127. Full findings: `docs/process-log.md`, entry 2026-08-02
(thirteenth retro).

## Decisions

**1. Phase close needs no new convention: a phase issue is a criteria-carrying
issue, and the existing closing discipline already governs it.** #3's
criterion-by-criterion comment did unprompted everything a convention would
prescribe — each box evidenced from probes and the audit, the one demo
amendment recorded rather than quietly reinterpreted (#126), and the honest
residue named per ticket: #19 open on the person-criterion, #42 on the next
brief, #106 on recurrence odds, #18/#126 human-gated. The pattern across this
log is that one instance done well unprompted is evidence *against* a rule.
What "Phase 1 done" means is therefore what #3's comment says it means: the
phase's own boxes ticked with evidence, residue tracked on its own open
tickets under its own labels, and the phase issue itself closing by hand when
the human-first remainder resolves. #3 gains the `ready-for-human` label to
make that state legible in the tracker, matching #19's relabelling.

*Overturned by*: a second phase boundary whose closing comment fails to carry
this shape unprompted — that would be the recurrence that earns a written
convention.

**2. The closing-keyword ban becomes a mechanical check (#129).** #24
auto-closed on a `Closes` trailer despite `docs/agents/issue-tracker.md`'s ban
— second instance after #89, both on criteria-carrying issues, both caught by
their own agents only after the close. Two self-corrected instances against a
written rule is the document-vs-mechanism shape ADR-0038 named: the mechanism
silently bypasses the document. #129 puts a closing-keyword deny in the
commit-msg gate, matching exactly the syntax GitHub acts on (so it cannot
false-positive in the sense that burned `block-no-verify.py` — there is no
innocent prose form of the thing GitHub executes), blanket rather than
criteria-scoped (a hook cannot know what #N carries; the cost is one hand
close), decision logic under `just unit` per #83/#120. The alternative —
accept the 2-for-2 self-correction rate — was weighed and declined: both
corrections happened after the gate was skipped, which is recovery, not the
gate holding.

*Overturned by*: the check producing denials on messages GitHub would not have
acted on, which would mean the exactness claim is wrong.

**3. The multi-agent tier ceiling gets one sentence of doc, not an
orchestrator-serialisation rule.** Three frictions in one cycle — #124 (the
no-Arma tier killing the Arma tier, fixed at `875846f`), #125 (two pools
overlapping; pre-flight, re-check and `--wait`-queues-on-the-machine all
landed), #127 (the Windows client unserialised across pools, filed) — and each
got a mechanical fix at the layer that owns it. A standing "the orchestrator
serialises corpus-gating dispatches" rule was weighed and declined: it would
codify scheduling (declined twice before on the same grounds), forfeit the
pool's measured 2.48× and the point of `--wait`, and prescribe around
machinery that now degrades correctly. What was genuinely unwritten is the
race the pre-flight does not close — two pools starting within ~90 s both read
an empty machine — so `docs/regression-tier.md` now states it plainly beside
the pre-flight, with the re-check named as the layer that catches it and the
cross-pool reservation named as deliberately unbuilt until ADR-0028's N
question is settled. Beyond that, this cycle is the machine restating #50's
conclusion; the second machine (#52–#54) stays the human's deferred decision.

*Overturned by*: a second cycle in which concurrent gating agents lose runs to
each other *through* the landed layers (pre-flight + re-check + `--wait` +
#127's lock), which would show the layers insufficient and the scheduling rule
necessary after all.

**4. The offline-planner staging proof is an exemplar, not a rule.** #104 ran
the real `UtilityPlanner` offline over the exact staged sequence across thirty
seeds before trusting the probe — the board proven to *force* the decision the
probe bets on, and the probe's one staging bug found by its own fixture. First
instance, done unprompted, of a pattern that strengthens bet-on-the-decision
and assert-your-staging at once; recorded in CLAUDE.md's probe-paragraph
exemplar list (the ×7 earn) and in #104's own closing comment, where the next
probe author will find it. No rule, per the standing bar: first instances are
exemplars.

**5. Markers (count and exemplar in the same edit, per the skill's step 5).**
Probe-window ×6 → ×7 (#104's derived 480 s window plus the offline board
proof; #24's 150 → 300 with arithmetic in the header). Elimination-context
×3 → ×4 (#124: the memory-edge story re-tested and disproved, the reporter's
own recurrence comment retracted; readings stood, the story did not). Retro
skill ×12 → ×13 (thirteenth use, no self-amendment needed). Unchanged, with
reasons: failure classes stay ×7 (#124's `node_crashed`, #125's
`infra_unavailable` refusals and #127's guard stop are the machinery
operating, not new kinds of earn); convention-lands stays ×3; ADR-claiming
stays ×5 (#123's "0043 stays free" note and this batch's fetch-and-scan claim
are the rule operating); recovery runbook stays ×8 (nothing briefed through it
this cycle); `playtest-brief` ×1, `playtest-ingest` unproven, still waiting on
the human playing brief 0001.

## Also weighed and declined

An index for the exemplar patterns in circulation (~16 by count: honest-
remainder, if-it-recurs, note-don't-refile, bet-on-decision, assert-staging,
derived-not-chosen, measured-window placeholders, exploration-as-audit,
decision-tickets, directed/supplemental review passes, named-consumer,
fail-closed self-checks, convention-lands, elimination-context, ADR-claiming,
honest-odds). Each lives where its reader looks — CLAUDE.md's marker
parentheticals, the tier doc, the tracker doc — and the process log is one
entry per retro and greppable. An index would be a maintained duplicate, the
same shape as the central ADR-number file declined at the twelfth retro; grep
is the index until grep fails someone, which would be the evidence to revisit.
