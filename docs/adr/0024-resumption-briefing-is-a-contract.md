# Resuming a dead agent gets a runbook after all: the briefing is a contract, not an affordance

Delegated-decision: yes
Date: 2026-08-01
Stood-in-for: human sign-off on new ADRs and on changes to CLAUDE.md — this ADR, `docs/agents/recovery.md`, and the CLAUDE.md agent-skills reference (#37; directed by the human as top priority, shape delegated)
Reviewed-by-human: 2026-08-02

Amends ADR-0022's declined-runbook clause and nothing else in it. The stale-infra rule —
a dead run's leftovers carry no `verdict.json`, are not results, and its world is state
to clear, never context to inherit — stands untouched and is cited, not restated, by the
runbook this ADR creates.

## What overturns the decline

ADR-0022 declined a recovery runbook on the evidence of two resumptions: both worked from
the worktree's last commit plus `git status`, so "a procedure would prescribe what the
tools already afford." A third death-and-recovery within the same two nights confirmed
that half — the worktree mechanics again needed nothing — and exposed what the decline
never weighed: every recovery also required a **resumption briefing**, hand-reconstructed
by the orchestrator all three times. A resumed agent's transcript predates everything
that landed while it was dead, so the orchestrator each time rebuilt (a) what moved on
`main`, (b) what of the agent's own environment died with it, and (c) which of its
assumptions no longer held. The tools afford none of that: git shows what landed, but
nothing points a resumed agent at the delta between its transcript and the world, and a
briefing that omits one part fails silently — a resumed agent that trusts its dead run's
output, or claims an ADR number that landed meanwhile, produces defects indistinguishable
from ordinary work. Three identical improvisations of a failure-silent step is the
pattern the decline said did not exist.

## The decision

`docs/agents/recovery.md` is the runbook: recognising death, worktree inspection,
the briefing's three required parts, the ADR-0022 stale-state rule by citation, and the
resumed agent's obligations on wake (fetch, re-read what moved, re-verify its transcript's
claims). The briefing is a two-sided contract — the orchestrator owes the reconstruction,
the resumed agent owes the re-verification — because either side alone leaves the same
silent gap. CLAUDE.md's agent-skills section references it, which is where a recovering
orchestrator looks.

The runbook deliberately stays at ADR-0022's grain: one governing instruction (a dead
agent has been asleep, not failed; its last commit is sound, everything after it is
suspect) with the three briefing parts as its only enumeration, rather than a case list —
the three recoveries differed in every incidental detail and agreed only on those parts.

## Overturned by

- A recovery where following the runbook produced a worse outcome than the orchestrator's
  own judgement would have — then the runbook is over-prescribing and shrinks back toward
  ADR-0022's original decline.
- The briefing's three parts proving incomplete in practice — a recovery corrupted by
  something the briefing format never asks for adds a part at a retro; it does not accrete
  ad hoc.
