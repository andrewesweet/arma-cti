# An interrupted tier run is not a result, and the corpus stays whole until thirty minutes

Delegated-decision: yes
Date: 2026-08-01
Stood-in-for: human sign-off on process-doc changes — this retro's amendments to CLAUDE.md and its status markers (scheduled retro on #31, #23, #32, #34, #33; docs/process-log.md carries the full entry). The retro skill's two blocked edits from the previous retro stay pending for the human and are not retried here.
Reviewed-by-human: pending

Decided at the second scheduled retro of 2026-08-01, from one event the process had no
words for: a session limit killed two agents mid-flight, one of them mid-Arma-run,
leaving a dead server, a half-written evidence directory, and an uncommitted worktree.
Recovery worked — but it was improvised by the orchestrator, and the next orchestrator
should not have to improvise it.

## What the death proved without being asked

The tier lock freed itself. `flock(2)` was chosen over a pidfile precisely because the
kernel releases it when the holder dies (docs/regression-tier.md, ADR-0016), and this
was the first holder death: no stale lock, no `infra_unavailable` against a ghost —
the exact failure Phase 0 met on a pidfile-less port, designed out before it could
recur. No amendment needed there; the design's rationale is now a measured fact.

## The decision: a dead run's leftovers are stale infra, not evidence

CLAUDE.md's lock paragraph gains one sentence: an agent that dies holding the tier
releases the lock by itself; its half-written evidence directory carries no
`verdict.json` and is **not a result** (the same discipline as `infra_unavailable` —
do not interpret it); any server, daemon, or staged world it left behind is stale
state to clear before the next run, never context to inherit.

That is the whole rule. A recovery runbook for resuming a dead agent's worktree was
considered and declined: both resumptions this cycle worked from nothing but the
worktree's last commit plus `git status`, which is what worktrees are for, and a
procedure would prescribe what the tools already afford.

**Overturned by**: a dead run whose partial evidence was actually needed to diagnose
the death itself — if that happens, the fix is to carve out "read but never gate on",
not to delete this rule.

## The corpus-selection tripwire, made concrete

Event assessed at this retro: the per-issue **full-corpus** run changed behaviour
within hours of landing (#32 was gated by it and it closed a corpus gap in place) and
its cost is a measured ~1.5–2 minutes of wall per probe including bring-up (8 probes:
12 m 38 s, 13 m 10 s, 12 m 56 s; 9 probes: ~16 m). The design defers selection until
the corpus grows and makes that call a fable-session call; this retro is one, and sets
the trigger as a number rather than a mood: **when a full green pass first exceeds
30 minutes measured — on the current curve, roughly 15–18 probes — build selection on
the `issues:` header before adding the next probe.** Until then the full corpus stays
the per-issue gate; issue-class subsets were considered and declined, because the
expensive failures to date remain the unselected kind. Tracked as an issue so the
tripwire has an owner when it fires.

**Overturned by**: the cost curve bending first — a probe class whose subject needs
multi-hour windows would blow the budget long before probe count does, and then the
trigger is that probe, not the total.

## Status-marker upgrades taken here (CLAUDE.md)

Per the retro skill's step 5, each on a firing this cycle, cited inline in CLAUDE.md:

- **Failure classes ×3 → ×4** — building #23's runner found the harness had been
  mistyping every in-world failure as `assertion_failed`, including ones the world had
  typed `timeout` or `oracle_disagreement`; the table's required-response column is
  what made a wrong class a harness bug, and the fix was in the harness.
- **Probe-window rule ×2 → ×3** — #33's probe failed on effects landing on separate
  pump turns; fixed by waiting on the pair, window unmoved.
- **ADR-claiming rule ×1 → ×2** — this cycle's 0021 collided with #31's claim of 0020
  and was renumbered during the rebase, exactly as the rule prescribes.
- **Convention-lands-with-first-instance ×1 (first marker)** — #23 landed the
  `just regress` table row, the lock, and the evidence conventions in the same commit
  as the recipe.

**Overturned by**, for any marker: the next firing where following the rule's required
response was wrong — markers go down as well as up, at a retro.
