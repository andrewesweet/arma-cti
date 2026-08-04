# The untyped class gets its table row, and the daemon's world-facing half gets a boundary

Delegated-decision: yes
Date: 2026-08-04
Stood-in-for: human sign-off on CLAUDE.md changes (a failure-class table row, a
status-marker upgrade) and the retro skill's marker (eighteenth retro's
amendment batch, session unattended)
Reviewed-by-human: 2026-08-04
Claimed: comment on #184, 2026-08-04, after `git fetch origin` (docs/adr/ on
origin/main topping at 0049) and a scan of open-issue comments finding no
claim above 0049

Amendment batch for the eighteenth retro (scheduled: five closes since
`85d17cd` — #168, #171, #178, #174, #145 — plus #183/#184 filed same-session
and the ADR-0048 claim collision renumbered to 0049). Full findings:
`docs/process-log.md`, entry 2026-08-04 (eighteenth retro). One batch ADR for
the cycle, deliberately: with the review queue at four (0046–0049), folding
#184's resolution into this record was weighed against minting a second ADR
and chosen for it.

## Decisions

1. **`untyped_harness_failure` gets a row in the failure-class table,
   resolving #184 by its option (a).** #171 (`36d5358`) made the class
   emitted, ranked and the default wherever a class is missing, which turned
   the preamble's "untyped red = harness bug" from a description of an
   absence into a class a reader can meet in a `verdict.json` — and "read the
   class before anything else" must not land on a class with no row. The row
   states what the code already decided: harness bug, fix the harness first,
   the verdict says nothing about the code under test; and it outranks
   everything, `infra_unavailable` included, because `spike/regress.sh`'s
   severity ladder sends any unknown class to 90 against
   `infra_unavailable`'s 80 (exit code 8). The row documents a landed
   decision rather than making a new one, which is what makes it safe to
   take in the human's stead. The preamble sentence stays: it is the row's
   reasoning, and it also covers the nameless case the class now defaults
   for.

2. **The daemon's world-facing half is defined where the tier's design
   lives.** The phrase appears in CLAUDE.md's gate row, ADR-0016 and
   `docs/regression-tier.md`, and was defined in none of them. #145's diff
   touched `Outbox.push` — by its own close "the one path every world effect
   takes (ADR-0012)" — and landed with `just fast` alone, on openly stated
   reasoning: wire byte-identical, all five producers proven conformant, and
   the issue's criterion 4 naming `just fast` as the tier. The reasoning is
   probably true, and it is still an equivalence argument, which is the
   argument form the gate's surface-based design exists to preclude ("the
   expensive failures to date have been the unselected kind") — and an
   issue's acceptance criteria cannot stand down a standing gate. The fix is
   the missing definition, not a charge of bypass: one sentence in
   `docs/regression-tier.md`'s cost-control section names the boundary
   (anything that builds, validates, serialises or hands over what crosses
   the extension wire — the port's dispatch and refusals, the outbox, the
   command/effect codec) and states that it gates on surface, not on a
   predicted wire. A comment on #145 records the residual exposure: the
   landed daemon has not run the corpus, the next full-corpus run covers it,
   and a daemon red there should suspect the push guard first.

3. **ADR-claiming upgrades ×5 → ×6 on its first blind-window collision.**
   #171 claimed 0048 by comment at 16:30Z with the prescribed scan honestly
   returning nothing — the seventeenth retro's 0048 claim sat on #168,
   posted seventeen minutes earlier, but #168 had closed at 16:20Z and the
   rule scans open issues, so the claim had closed out of view before its
   ADR landed (16:35Z). The collision was found on the rebase and #171
   landed as 0049 with references updated, exactly as prescribed. The
   exemplar records the blind window rather than widening the scan: the
   rebase backstop is what holds, at the priced cost of one renumber, and
   the twelfth retro's central-file reasoning applies unchanged.

4. **Markers.** Retro skill ×17 → ×18 (eighteenth run, unattended, no
   self-amendment needed), count and exemplar in the same edit per step 5's
   clause.

## What would overturn this

- Decision 1: the human preferring #184's option (b) — the preamble is the
  row and the table stays eight classes — or wanting the class renamed or
  re-ranked; the row is one line to remove or reword.
- Decision 2: the human drawing the world-facing boundary elsewhere (for
  example, only the extension callback surface, leaving the outbox and codec
  ungated), or judging that #145's equivalence reasoning should be an
  accepted gate-discharge form; the sentence in regression-tier.md is the
  thing to redraw.
- Decision 3: a recurrence showing the blind window costs more than a
  renumber — a collision reaching `main` unresolved, or claims routinely
  landing on issues that close within minutes — which would reopen widening
  the scan to recently closed issues.
- Decision 4: the human judging any of the cycle's evidence misread, per the
  standing terms of the retro's sign-off gate.

## Why one ADR and not two

The queue the human reviews is per-ADR, and #184's resolution is one row
whose semantics the code already carries; a dedicated ADR would add a queue
entry to say what decision 1 says here. The orchestrator's dispatch asked
this retro to weigh exactly that proportionality, and this is the weighing.
