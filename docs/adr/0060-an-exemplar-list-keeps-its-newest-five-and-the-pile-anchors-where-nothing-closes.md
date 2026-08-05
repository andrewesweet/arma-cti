# An exemplar list keeps its newest five, and the pile anchors where nothing closes

Delegated-decision: yes
Date: 2026-08-05
Stood-in-for: human sign-off on CLAUDE.md, process-doc and skill marker changes — the
twenty-third retro's amendment batch (session unattended)
Reviewed-by-human: pending
Claimed: comment on #217, 2026-08-05, after `git fetch origin` (`docs/adr/` on
`origin/main` topping at 0058) and a scan of every open issue's comments finding the
highest claim at 0059 (#170, in flight)

Amendment batch for the twenty-third retro (scheduled: ten closes since `e3b5d99` —
#157, #165, #151, #193, #175, #205, #207, #206, #153, #210). Full findings:
`docs/process-log.md`, entry 2026-08-05 (twenty-third).

## Decision 1: the exemplar prune's first execution

Per the human's 2026-08-05 approval on #201 (rule landed in the retro skill at
`4287d63`): every CLAUDE.md `validated ×N` list past five exemplars is cut to its
newest five, the dropped text archived verbatim in the journal entry's prune record.
Executed on probe-window (8 → 5), failure classes (9 → 5), elimination-context
(10 → 5, after this batch's append), and ADR-claiming (7 → 5); convention-lands
reached exactly five by append and drops nothing. Each pruned list opens with a
pointer to the full record so a count above the list length reads as the prune, not
as the same-edit-clause violation the marker gate exists to catch. #209 measured the
exemplar blocks at 2,246 tokens (1.095% of the bill) — the cycle's largest single
prefix saving. This is execution of an approved ruling, delegated only in its
editorial choices (which five survive is mechanical — newest — and the pointer
wording is this batch's).

## Decision 2: `just handoff`'s row lands verbatim (ADR-0057's clause)

#210 landed the recipe with its row proposed, not taken, exactly as ADR-0057
prescribes for the gated table. The row lands here with the text and placement
(after `just verdict`) as the close proposed. Same safety reasoning as ADR-0057
decision 1: documentation of landed, unit-tested tooling; no gate, class, port or
behaviour moves. The sweep for other row-less recipes found none — `watch`,
`watch-report` and `verdict` got their rows under ADR-0057, and the `check-*`/
`unit-*`/`build-*` sub-recipes have never carried rows, being components of rows
that exist.

## Decision 3: the consolidated pile anchors on a standing issue

The twenty-second retro's consolidated recommendation sat on #200, which the human
ruled and closed two hours later — the pile's one findable copy went into a closed
thread, and the 2026-08-05 label audit named exactly this shape as one of the two
standing exceptions to `ready-for-human` search. Fix, landed with its first applied
instance per the convention-lands rule: standing issue #217 (open by design, the
current pile always its newest comment), one sentence in retro skill step 3, and a
short exceptions note in `docs/agents/triage-labels.md` naming both exceptions (the
ADR review queue's anchored grep; the pile issue).

## Decision 4: two currency edits to CLAUDE.md

- The hooks paragraph gains the two token-economy denial hooks (#205's subagent
  wait denial, #207's oversized-Read denial) and the sentence splitting the two
  denial families' required responses — the old "a hook denial is a signal you're
  on a gated surface" was made false in general by hooks whose denials are
  remedies, not gates.
- The `just check` row names the validated-marker check, the same class of fix as
  the twenty-first's unnamed ADR-form check.

## Decision 5: marker upkeep (retro step 5)

- **Elimination-context ×9 → ×10** — #157/#165: a test comment's self-defending
  rationale ("these two are the contended leg"; there were six) re-derived from the
  probe headers, and an issue's "run by nothing" premise falsified by re-reading,
  the asked-for deletion declined with the stay of execution in the file's header.
- **Convention-lands ×4 → ×5** — #208 landed the handoff template with itself as
  first instance; #210 landed the retrieval tool with the doc's pointer in the same
  commit.
- **Recovery runbook ×14 → ×15** — the first post-tooling stalls (#153 twice on a
  green pool, #170 on reds), both watcher catches inside ADR-0042's stale-copy
  window; the prod's cost now cited (2.32%, #206) beside what #204's ruling would
  remove.
- **Retro skill ×22 → ×23**; CLAUDE.md's banner counts twenty-three retros.

## Not taken, and why

- **A "measure before building" working-style line** — the cycle's clearest
  pattern (#195 → #197/#198/#199, #207's threshold re-measurement, #209's declined
  slot-API arithmetic, #210's fail-open jq caught by running it: measurement
  inverted the handed intuition every time), but every instance arose *without*
  the rule, and this cycle's own arithmetic says a prefix sentence must out-earn
  its cache cost. Routed to the human on #217 as a recommendation with the
  evidence; a cycle where an unmeasured optimisation lands and misses is what
  would earn it outright.
- **The runbook watcher-section rewording** ("the prod costs 2.32% — end-before-
  wait removes both") — waits on #204's ruling rather than pre-empting it; the
  fifteenth use carries the numbers so the ruling can read them.
- **A failure-class earn** — #210's exit 1/exit 3 split and #151's `pool_signalled`
  refusal are design within the table, per the twentieth's precedent.
- **A probe-window move** — nothing landed on it this cycle; #170's frame-race fix
  (per #33's precedent, window unmoved) counts at its landing, not before.
- **#211's ending-agent handoff rule** — an open proposal issue with its own flow;
  taking it here would pre-empt #212's break-even measurement.

## What would overturn this

- Decision 1: the human preferring a different survivor set (e.g. curated rather
  than newest-five), or the prune-pointer wording reading as a count violation to
  any auditor — either reverts by restoring the archived text from the journal's
  prune record, which is byte-complete for that purpose.
- Decision 2: the human preferring different row wording — reverts to
  proposal-only as with ADR-0057.
- Decision 3: the human preferring the pile live somewhere else (a pinned issue, a
  doc, the next guided session's agenda) — #217 then closes with a pointer and the
  two sentences move.
- Decision 4: evidence the split sentence misreads either hook family — e.g. a
  gated-surface hook whose denial also names a remedy an agent should take.
- Decision 5: any exemplar failing audit — the stall pair is orchestrator-side,
  corroborated in-repo only by the landing gaps in #153's and #170's timelines; an
  audit showing either agent self-recovered would cut the fifteenth use back.
