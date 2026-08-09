# The window discipline holds at first contact, and a finding list is re-checked whole

Delegated-decision: yes
Date: 2026-08-04
Stood-in-for: human sign-off on CLAUDE.md, process-doc and skill marker changes — the
twenty-first retro's amendment batch (session unattended for these; the cycle's three
larger process changes were human-instructed in session and are recorded below as not
delegated)
Reviewed-by-human: 2026-08-08
Claimed: comment on #186, 2026-08-04, after `git fetch origin` (`docs/adr/` on
`origin/main` topping at 0053) and a scan of every open issue's comments finding no
claim above 0053

Amendment batch for the twenty-first retro (scheduled: five closes since `5bea145` —
#148, #166, #147, #150, #191). Full findings: `docs/process-log.md`, entry 2026-08-04
(twenty-first retro).

## Proportionality

Weighed against a queue at 2 (0051, 0053). The cycle's substantive process changes —
the retro cadence and scope, the CLAUDE.md review, the model-effort mapping and its
agent seats — were all human-instructed in session, so none of them is delegated and
none enters the queue. What remains for delegation is count-and-exemplar upkeep only:
four marker moves, no new rules, queue re-opens at 3.

## Decisions

**1. Probe-window discipline ×7 → ×8 (#150/#191's `ai-reinforce`).** The corpus's
newest probe met the rule at first contact: its first corpus run timed out in its own
scaffold — staging read the board through `view`, which refuses an AI-commanded side
(`wrong_side`), while the decision under test had already fired at t=10, visible in
the timeline. The fix went to the probe's staging (the `cti_presenceReport` pattern),
never the 300 s window, and the probe then passed twice at 25 s. The finding also
landed in `docs/regression-tier.md` beside the compileFinal one (`558d03e`), so the
next probe author inherits it where probes are designed.

*Overturned by*: the exemplar list's own length doing harm, per ADR-0051 decision 2's
prune clause.

**2. Elimination-context ×7 → ×8 (#147's whole-list re-location).** The tree had been
reshaped four times between #147's filing and its fix (#171, #161, #162, #185); the
agent re-located each of the seven findings before fixing it — all seven fixed, none
declined, the shifts stated in the close. First application of the line to an entire
finding list rather than a single filed ground (#159's shape, one cycle earlier).

*Overturned by*: same prune clause as above.

**3. Recovery runbook ×12 → ×13 (stalls five and six, both #149).** Both watcher
catches, orchestrator-side observations: 90 minutes silent on uncommitted work across
five addon files — the commit-early violation corrected on the prod — then 2+ hours
silent through a usage-conservation window, resumed clean. Six stalls, six watcher
catches, zero self-recoveries; the permanence sentence operating, not a new finding.
The exemplar adds one sharper edge without a new rule: a stall sitting on uncommitted
work is what turns an orchestrator death from a prod into work at risk — the
commit-early line's price read from the stall's side.

*Overturned by*: a stall the watcher misses, or the harness gaining run-completion
wake-ups (per ADR-0053 decision 2).

**4. Retro skill ×20 → ×21.** Twenty-first run, attended-by-instruction: three
in-session human decisions beyond normal scope (the cascading CLAUDE.md review, the
skill's scope/cadence amendment, the model-effort mapping delivered mid-retro), each
landed citing its instruction as sign-off, while the delegated remainder still went
through ADR-0013 as this file. First scope amendment since the sign-off wording that
was human-decided directly rather than queued.

*Overturned by*: nothing specific — the count reverts cleanly if rejected.

## Recorded here, not delegated

- **The retro-skill scope/cadence amendment** (`f7c42f0`): incremental
  `/revise-claude-md` in every retro's scope; scheduled trigger 5 → 10 closes
  effective after the twenty-first. Human decision, 2026-08-04, orchestrator session;
  the commit quotes it. The cadence sentence is the cadence's first written home.
- **The CLAUDE.md currency pass** (`a87ad36`): status banner updated off
  "unproven-and-unused", ADR-form check named in the `just check` row, code homes
  named in the toolchain bullets. Authorised by the human's review instruction; no
  rule's meaning touched; the banner edit is the one a reviewer may want to eye first.
- **The model-effort mapping and agent seats** (`13de963`): CLAUDE.md's Model roles
  replaced with the ratified five-tier mapping plus the inheritance mechanism note;
  `.claude/agents/{cti-implementer,cti-implementer-light,cti-mechanical,cti-recon}.md`
  land as its enforcing instances in the same commit. One judgement call flagged:
  `cti-recon` includes Bash for inspection (git/gh/rg) with read-only conduct stated
  in its prompt, since a literal no-Bash seat could not run a triage sweep.

  **Currency note:** that list was superseded on 2026-08-05: `cti-implementer-light`
  no longer exists, `cti-implementer` is opus/high and is the default tier, and
  `cti-implementer-xhigh` is the reserved seat. This record is a dated snapshot and is
  not wrong about its date — the seats moved after it was written.
- **Open, not taken**: the 500k-token alternative retro trigger (not ruled on —
  orchestrator memory says ask when it next matters); where standing
  orchestrator-only rules live (this retro's answer: repo surfaces when they bind
  repo-governed process, journal + memory otherwise; a `docs/agents/orchestration.md`
  declined at one cycle's evidence); one mapping amendment proposed to the human in
  the retro report (ruling transcriptions with drafting slack on gated semantic
  surfaces sit above `cti-mechanical`).

## What would overturn this

- The human rejecting any decision above at review: each is a count and exemplar,
  named above, and reverts cleanly.
- The per-decision overturn rows above.
