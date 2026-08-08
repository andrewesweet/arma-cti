# A lane-blind gate's row lands with the retro, and the initiative's proposals get a second vehicle

Delegated-decision: yes
Date: 2026-08-06
Stood-in-for: human sign-off on CLAUDE.md, process-doc and skill marker changes — the
twenty-fifth retro's amendment batch (session unattended)
Reviewed-by-human: 2026-08-08
Claimed: comment on #217, 2026-08-06, after `git fetch origin` (`docs/adr/` on
`origin/main` topping at 0064) and a scan of open-issue comments finding no claim
above it

Amendment batch for the twenty-fifth retro (scheduled: ten closes since `879d6e9` —
#225, #224, #228, #218, #219, #220, #92, #238, #239, #240). Full findings:
`docs/process-log.md`, entry 2026-08-06 (twenty-fifth).

## Decision 1: the `just mutation` row lands here, because the quality track is not the initiative

ADR-0063 decision 1 routes the multi-provider initiative's CLAUDE.md amendments to
that initiative's own human-gated vehicle. #239's mutation smoke is not on that
route: it was commissioned from the human's lane-quality questions but built
**lane-blind** by design — it gates every landing identically, whichever lane wrote
it, and its decisions are already recorded in ADR-0064 sitting in the review queue.
So ADR-0057's reconciliation clause applies in its ordinary retro form: `just fast`'s
row now reads `check` + `unit` + `mutation`, and a `just mutation` row lands with the
floor's no-flag rule and the `NO_PYTHON_SUBJECT` named-list escape stated, since a
gate an agent meets after every edit is exactly the kind of rule that must not be
discovered by denial.

## Decision 2: the initiative's gated proposals move to a second batch vehicle (#248)

#228 — the initiative's first batch vehicle — was ruled and landed 2026-08-05, then
closed. Three gated proposals have accumulated since, all on **closed** threads:
#238's off-peak clause for the `just dispatch` row, #240's pointer-paragraph third
document, and #240's dead-allowlist swap. A closed thread is where the
twenty-second retro's pile comment went unfindable within two hours (#200 → the
standing pile #217), and the same failure shape applies to the initiative's own
gate. So the retro filed #248 as the second vehicle, carrying the three proposals
verbatim and a pointer to the finisher-permission decision that stays on #221. This
executes ADR-0063's split rather than amending it: nothing from #248 lands without
the human's ruling there, and this batch takes none of it.

## Decision 3: marker currency, with the prune-on-append

- Elimination-context ×11 → ×12: #239/#172's mutmut re-derivation appended (the
  filed "incompatible with our pytest config" verdict re-run rather than inherited,
  and corrected in both directions — the tool runs; its reporting cannot carry a
  floor); the oldest exemplar (#159) pruned to the journal's prune record per #201.
- Recovery runbook ×16 → ×17: crash cluster two — every in-flight track resumed
  from disk records, and #237's death-as-reviewer resumption judged the surviving
  data inconclusive rather than rounding it.
- Retro skill ×24 → ×25; process-status banner to twenty-five.

## What would overturn this

- **Decision 1**: the human ruling at review that the quality track belongs to the
  initiative's gate after all — the row then moves to #248 and the table entry is
  reverted pending that ruling; or the mutation gate leaving `just fast` (the row
  follows the recipe, ADR-0057).
- **Decision 2**: the human preferring accumulation on the tracking issue #221 over
  a dedicated vehicle — #248 then closes with its content posted to #221; the
  proposals themselves are unaffected either way, since nothing lands from either
  home without a ruling.
- **Decision 3**: any exemplar found misattributed at review — the count follows
  the list (`tools/check_validated_markers.py` gates the arithmetic; the
  attribution stays the human's to overturn).
