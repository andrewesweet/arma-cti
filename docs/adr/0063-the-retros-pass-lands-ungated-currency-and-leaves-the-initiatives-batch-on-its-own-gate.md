# The retro's pass lands ungated currency, and leaves the initiative's batch on its own gate

Delegated-decision: yes
Date: 2026-08-05
Stood-in-for: human sign-off on CLAUDE.md, process-doc and skill marker changes — the
twenty-fourth retro's amendment batch (session unattended)
Reviewed-by-human: 2026-08-08
Claimed: comment on #217, 2026-08-05, after `git fetch origin` (`docs/adr/` on
`origin/main` topping at 0062) and a scan of every open issue's comments finding no
claim above it

Amendment batch for the twenty-fourth retro (scheduled: ten closes since `ee1080e` —
#214, #196, #204, #223, #230, #213, #226, #227, #232, #231). Full findings:
`docs/process-log.md`, entry 2026-08-05 (twenty-fourth).

## Decision 1: the scope boundary with #228 is honoured, and recorded as deliberate

The multi-provider initiative's CLAUDE.md amendments accumulate on #228 by design —
it is that initiative's own human-gated vehicle (dispatch rulings, 2026-08-05). This
batch therefore takes **none** of them, including where ADR-0057's reconciliation
clause would otherwise route a landed recipe's row through a retro: the `just
dispatch`, `just land`, `just ledger-sync`, `just breaker` and `just prereqs` rows,
the gitleaks word on the `just check` row, the `quota_exhausted` and
`provider_refused` failure-class rows, the profile extension of Model roles, the
review-diversity wording, and the seat-eligibility divergence all stay on #228 and
land only with the human's sign-off there. A consequence stated rather than left to
be noticed: until #228 lands, `CLAUDE.md`'s command table knowingly lags five landed
recipes, and the lag is the gate operating, not a drift.

## Decision 2: three currency edits to CLAUDE.md

- **Model roles** gains the seat-enumeration limit #219 hit twice: the harness reads
  `.claude/agents/` once at session start, so a seat written mid-session is not
  dispatchable in that session, and a seat that must persist lands on `main` through
  the mapping's sign-off, never as a file in a session's tree. This is where the
  next orchestrator reads before dispatching, which is why the fact lands here
  rather than only in #219's report.
- **The five-minute bullet's two forward references resolve to their measurements**,
  with both rules unchanged and both rulings left with the human: #219 has run (the
  seat does not discriminate on verdict-reading; transcription does — paste, never
  retype) and the orchestrator still reads; #218 has run (the one-hour premium is
  below the meter's floor) and dispatch-as-a-session stays unsanctioned pending the
  ruling. Stating a finished measurement's result beside the interim rule it informs
  is the same class of edit as ADR-0057's clearly-safe documentation.
- **The `just check` row names the conflict-marker check** (#231) — the same class
  of fix as ADR-0060 decision 4's naming of the validated-marker check. #231's own
  close routed nothing to #228 and owed no new row; this names a component on the
  row that already enumerates its siblings. The gitleaks word on the same cell is
  **not** taken: it is #223's, proposed on #228, and follows that gate (Decision 1).

## Decision 3: marker upkeep (retro step 5), with the prune-on-append

Per ADR-0060 decision 1, a list at five that earns a new exemplar appends the newest
and drops the oldest in the same edit, the drop archived verbatim in the journal
entry's prune record.

- **Failure classes ×9 → ×10** — #222: `flake_quarantine`'s required response ran
  distributed for the first time — four arrangements, six full-suite runs, a
  different parameter each time, and every gate that met it quoted the class,
  re-ran once as briefed, and did not act, with no coordination beyond the class
  itself. Dropped: #41 (archived in the journal).
- **Elimination-context ×10 → ×11** — #218/#220/#232: the token-efficiency
  corpus's ranking was an inherited measurement priced in a currency this account
  does not pay; re-measured in plan currency it inverted, and the ledger was
  re-based on the measured currency rather than inheriting `cost_usd` as cost —
  the line's first application to a whole cost model. Dropped: #156/#152 (archived
  in the journal).
- **Recovery runbook ×15 → ×16** — the four BLIND watcher findings over the removed
  prior-art worktrees, resolved by the runbook's by-hand look as finished-and-
  cleaned agents (their output landed on main) and acked on the human's
  instruction; the first BLIND that resolved to nothing-wrong.
- **Retro skill ×23 → ×24**; CLAUDE.md's banner counts twenty-four retros.

## Not taken, and why

- **A convention-lands bump for #213 landing via itself** — `just land` gating its
  own first landing (red, then green) is the strictness principle and fail-closed
  discipline operating, not a design-document convention landing with its first
  instance; the journal names the cycle's "tools catching their authors" pattern
  instead, on three instances (#213's gate_red, gitleaks on #223's own fixture,
  `just prereqs` un-greening its Codex config to `unverified`).
- **A "measure before building" working-style line** — re-weighed at the evidence
  bank's request against this cycle's two further inversions (#218's null, #220's
  re-ranking; the count across the token track is now five). The twenty-third's
  reasoning has *strengthened*: all five arose without a resident rule, so the
  behaviour is demonstrably self-sustaining, and #209's arithmetic still prices
  every resident sentence. Stays with the human on #217, with the note that the
  same evidence would equally justify closing the item as adopted-in-practice.
- **Any amendment to the dispatch freeze or the initiative's WIP reservation** —
  human rulings (2026-08-05), context for this retro and not its surface. The
  freeze-propagation caveat (#217, 17:12Z: a freeze recorded durably does not
  reach a session already running) is recorded in the journal as an offered input
  for the still-recommended orchestration doc, not landed as a rule from a seat
  that cannot read the orchestrator's memory.
- **A probe-window move** — nothing landed on an in-world window this cycle; #170
  remains in flight and counts at its landing.
- **A failure-class earn for the breaker's classes** — `quota_exhausted` and
  `provider_refused` are #228's scope (Decision 1); their first firings are the
  breaker's staged documents, not corpus verdicts.

## What would overturn this

- Decision 1: the human ruling on #228 that some subset should have landed
  incrementally at retros — the boundary then moves to whatever line that ruling
  draws, and the lagging rows land by executing it.
- Decision 2: the human ruling #218 or #219 differently from the interim the
  clauses state — the clauses then update to the ruling, which is their design; or
  evidence that naming check components on the `just check` row misleads (e.g. a
  reader treating the enumeration as exhaustive when the justfile has moved) — the
  row then reverts to naming the recipe alone.
- Decision 3: any exemplar failing audit — #222's distributed handling is
  corroborated by the closes that quote it (#223, #227) and its own thread's
  baseline table; the BLIND resolution is orchestrator-side, corroborated in-repo
  by #217's 17:12Z comment and the four landed research commits; an audit showing
  either otherwise cuts the count back. The prune reverts by restoring the
  journal's archived text, which is byte-complete for that purpose.

Amended 2026-08-09 (#217): decision 1's acceptance of a knowingly lagging command table, for as
long as #228 sat unruled, is withdrawn — **the boundary needs no lag.** A landed recipe's row may
go through a retro even where an initiative owns the surface, so the always-loaded table is never
knowingly wrong: an agent reading the table during the lag sees no `just dispatch`, no `just
land`, no `just breaker` — recipes it is expected to use — and a knowingly-wrong always-loaded
surface is a different cost from a lagging proposal. This applies to rows documenting
already-landed recipes only; it does not disturb the #228/#248 split for *rulings*, which stays
exactly as decision 1 and ADR-0065 decision 2 set it. Ruled by the human on #217, 2026-08-06.
