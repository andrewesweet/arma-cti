# The gate-clock history recipe and the check leg land their own rows, and the ruling that decided it was delegated

Delegated-decision: yes
Date: 2026-08-20
Stood-in-for: human sign-off on two edits to AGENTS.md's command table, a human sign-off gate in
CLAUDE.md's list — the new `just gate-clock-history` row, and the `just check` row's purpose cell
gaining the gate-clock anchor check — taken on #446's fix round
Reviewed-by-human: pending
Supersedes: none
Claimed: 0076 — after `git fetch origin` (`docs/adr/` on `origin/main` topping at 0075) and a read
of the open issues most likely to carry a concurrent claim (#442, #445, #447, #448, #450–#458),
which returned no ADR number at or above 0076. The blind window CLAUDE.md records — a claim whose
issue closes before its ADR lands — is covered by the rebase backstop, per the claiming protocol

## What happened

#446's fix round gave `tools/gate_clock.py` two surfaces it had shipped without: a `check` verb
wired into `just check` as a `check-gate-clock` leg (a half-edited anchor file must be a red
rather than a line nobody is obliged to read), and a `history` verb with no `just` recipe at all —
reachable only by bypassing the command surface, which CLAUDE.md binds: interact through `just`
only, and tooling that lands lands its recipe and table row in the same commit.

## Decision

**Ruled on #446, under the standing authorisation: both rows land in the same commit as the
recipes.** The new row states what `just gate-clock-history` reads and that it never gates; the
`just check` row's purpose cell gains the anchor-check leg alongside its siblings. Nothing else in
the table moves.

## What would overturn it

The human rejects either surface: say the anchor check does not belong in `just check` (or belongs
behind a different leg), or that the history verb should not have a top-level recipe at all — then
the row goes, the recipe goes with it, and this ADR records the reversal. Also overturning: the
human rules the table edit should have waited for sign-off rather than riding the ADR-0013
authorisation, in which case the process finding is against this record regardless of the
substance.
