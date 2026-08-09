# A recipe's gated row follows through the gate, and a detached watcher is not a parked turn

Delegated-decision: yes
Date: 2026-08-05
Stood-in-for: human sign-off on CLAUDE.md, process-doc and skill marker changes — the
twenty-second retro's amendment batch (session unattended)
Reviewed-by-human: 2026-08-08
Claimed: comment on #200, 2026-08-05, after `git fetch origin` (`docs/adr/` on
`origin/main` topping at 0056) and a scan of every open issue's comments finding no
claim above 0056

Amendment batch for the twenty-second retro (scheduled: ten closes since `05fa370` —
the first cycle at the ten-close cadence — #182+#125, #190, #188, #172, #192, #198,
#197, #199, #149). Full findings: `docs/process-log.md`, entry 2026-08-05.

## Decision 1: the three command-table rows land, verbatim as proposed

`just watch`, `just watch-report` (#198) and `just verdict` (#199) landed as recipes
with their CLAUDE.md table rows *proposed, not taken*, because the table sits on a
human-gated file. The command-surface convention — a recipe and its table row land in
the same commit — was therefore violated by the gate itself, for the first time since
the convention was written. This batch lands the three rows with the row text exactly
as the two closes proposed it. Taking this under ADR-0013 is judged clearly safe: the
rows document landed, unit-tested tooling; they change no gate, class, port, or
behaviour; and the convention that wants them on the table is itself validated ×4.

## Decision 2: the reconciliation clause

One clause is added to the command-surface paragraph: where the row's surface is
gated, the row follows through the sign-off gate — human approval or an ADR-0013
record — rather than lagging silently. Without it, the next recipe to land faces the
same collision with no stated resolution, and the convention reads as demanding what
the gate forbids.

## Decision 3: the watching sentence gains the `just watch` exception

CLAUDE.md's working-style line — "nothing an agent arms outlives its turn" — became
false to the letter when #198 landed a watcher that detaches by design. The
sentence's point survives (a parked wait nothing will wake is still a stall); the
amendment names the sanctioned shape: detached, and read at the top of a turn that
happens anyway. Left unamended, the sentence is a reason for a future session to
refuse the tool built to satisfy it.

## Decision 4: marker upkeep (retro step 5)

- **Failure classes ×8 → ×9** — #149's landing gate: three stops typed
  `infra_unavailable` in one multi-agent night (play-session guard twice, #124's
  port sweep once), each cause read before requeueing, none interpreted, and 39
  passing probe verdicts from the partial pools left unstitched.
- **Elimination-context ×8 → ×9** — #189: an ADR ruling's embedded engine premise
  (AI succession) tested rather than inherited, disproved in-world, the built
  reclaim withdrawn rather than landed inert.
- **ADR-claiming ×6 → ×7** — #182's 0054 claim collided with the twenty-first
  retro's concurrent 0054; found on the landing rebase, renumbered to 0055, fresh
  scan clean — exactly as prescribed.
- **Recovery runbook ×13 → ×14** — the #149 marathon's stalls beyond the pair the
  thirteenth use counted (orchestrator-side count: nine on the one issue), every
  one a watcher catch, zero self-recoveries; mid-marathon the watch became a tool.
- **Retro skill ×21 → ×22**; CLAUDE.md's banner counts twenty-two retros.

## Not taken, and why

- **#200's working-style rule** ("a turn does not block for five minutes") — an open
  ruling issue explicitly routed to the human; taking it here would pre-empt that
  ruling. The consolidated recommendation lives in a comment on #200.
- **#201's exemplar prune** — with the human; this batch keeps its new exemplars
  terse in anticipation but prunes nothing.
- **A decision-ticket "engine-falsifiable premises get a diagnostic first" line** —
  declined at one instance (#189): the probe gate caught the false premise before it
  landed, at the cost of one withdrawn commit, so the existing gate priced the miss.
  A second premise landing inert earns the line.
- **`docs/agents/orchestration.md`** — the twenty-first's rule-of-three threshold is
  now met (report-cadence muting and the dispatch freeze join the WIP limit and
  conservation windows as standing memory-only rules), but the rules' authoritative
  contents live in orchestrator memory this session cannot read, and a
  mis-transcribed standing rule is worse than a proposed doc. Recommended to the
  human instead, with the threshold evidence.

## What would overturn this

- Decision 1/2: the human preferring different row wording, or ruling that gated-table
  rows must always wait for explicit approval — either reverts to proposal-only and
  the clause comes out.
- Decision 3: a ruling on #200 that restates the watching rule wholesale — the clause
  is then subsumed and should be rewritten with it.
- Decision 4: any marker's exemplar failing audit — e.g. the orchestrator's nine-stall
  count for #149 not standing up (it is orchestrator-side, corroborated in-repo only
  by the churn it names), or a reading of #149's gate showing a stop that *was*
  interpreted. Note one correction already made at this batch's own audit: the
  dispatch brief attributed ADR-0055's memory floor as having fired live; the runs
  tree carries no `starved` marker, so the floor's only proven firing remains the
  no-Arma staged one, and no exemplar here claims otherwise.

Amended 2026-08-09 (#217): this ADR's own overturn text above left open whether a gated
command-table row may land under ADR-0013 or must each time wait for explicit approval. **Ruled
generally: decision 1's own test is promoted to the default.** A gated command-table row may land
under an ADR-0013 record when it documents landed, tested tooling and changes no gate, class, port
or behaviour. Anything failing that test waits for explicit approval. Ruled by the human on #217,
2026-08-06.
