# The ledger-sync row gains the staleness selection, and its prune column tightens to schema currency

Delegated-decision: yes
Date: 2026-08-25
Stood-in-for: human sign-off on one edit to AGENTS.md's command table, a human sign-off gate in
CLAUDE.md's list — the `just ledger-sync` row gaining `--behind`, the staleness selection's
description, and the prune cell's tightening from "a row has already taken" to "a row at the
current schema has already taken" — taken on #529's build (#531)
Reviewed-by-human: pending
Supersedes: none
Claimed: 0081 — after `git fetch origin` (`docs/adr/` on `origin/main` topping at 0078) and a scan
of open issues for claimed numbers, which found ADR-0079 claimed on #592 and ADR-0080 on #586 and
#588, and nothing at or above 0081; the claim was then posted as a comment on #529 before writing

## What happened

#529 found the dispatch ledger materialised for 6 of 691 dispatches, with nothing that reports
how far behind it has fallen and a prune rule that would delete the raw export behind a stale
row — the only material a corrected row could be rebuilt from once the rotating capture has
turned over. The build (#531) gives the sync a staleness selection (`sync --behind`), makes the
summary report the missing/stale/current split, and tightens prune's "taken" test to require a
row at the current schema. Its acceptance criteria require a command-table row covering the
selection to land in the same commit, and CLAUDE.md binds a landed recipe change to its table
row anyway.

## Decision

**Ruled on #529's build, under the standing authorisation: the `just ledger-sync` row is updated
in the same commit as the behaviour.** The row's syntax cell gains `[--behind]`; the purpose cell
describes the selection and the tightened prune condition; the "Run when" cell adds running
`sync --behind` routinely, since it writes nothing when the ledger is level. Nothing else in the
table moves, and the recipe named by the row exists unchanged in the justfile at the same commit.

## What would overturn it

The human rejects the surface: say the staleness selection should not be advertised in the table,
should carry a different name, or the routine-run guidance overstates the habit — then the row
reverts and this ADR records the reversal. Also overturning: the human rules the table edit
should have waited for direct sign-off rather than riding the ADR-0013 command-table route, in
which case the process finding is against this record regardless of the substance.
