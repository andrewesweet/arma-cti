# The eval-corpus recipe and its command-table row land together, and the ruling that decided it was delegated

Delegated-decision: yes
Date: 2026-08-29
Stood-in-for: human sign-off on one edit to `AGENTS.md`'s command table — the new
`just eval-corpus` row — taken on #617's implementation round, on the same basis as
ADR-0076: tooling that lands lands its recipe and its table row in the same commit, and
the table sits on a human-gated file the agent cannot otherwise touch.
Reviewed-by-human: pending
Supersedes: none
Claimed: 0082 — after `git fetch origin` (`docs/adr/` on `origin/main` topping at 0081)
and a read of the open issues, which returned no ADR number at or above 0082. The blind
window CLAUDE.md records — a claim whose issue closes before its ADR lands — is covered
by the rebase backstop, per the claiming protocol.

## What happened

#617's runner is a `just` recipe; CLAUDE.md binds tooling that lands to its recipe and
table row in the same commit. Without the row, the instrument lands reachable only by
bypassing the command surface — the exact shape ADR-0076 refused for `gate-clock-history`.

## Decision

**Ruled on #617, under the standing authorisation: the row lands in the same commit as
the recipe.** The row states what `just eval-corpus` runs, its verdict shape (a rate
over stated repeats, worst class as the exit code), that its comparisons are never
netted, and that `--contract` prints the task↔runner contract derived from the runner.
Nothing else in the table moves; `check-command-table` confines the diff to data rows.

## What would overturn it

The human rejects the row or its wording: then the row goes, and with it the recipe it
describes stays reachable only off the command surface, and this ADR records the
reversal. Also overturning: a ruling that the eval corpus is not yet ready to sit in the
command table until #618 builds the gate — in which case the row is withdrawn while the
instrument itself stays, and the process finding is against this record regardless of
the substance.
