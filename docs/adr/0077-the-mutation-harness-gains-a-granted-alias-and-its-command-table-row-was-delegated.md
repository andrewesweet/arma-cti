# The mutation harness gains a granted alias, and its command table row was delegated

Delegated-decision: yes
Date: 2026-08-19
Stood-in-for: human sign-off on `AGENTS.md`'s command table (`CLAUDE.md` is the committed
symlink to it) — the new `just mutation-compare` row, and the `just mutation` row's wording
for `--report` and `SURVIVES_BY_DESIGN` — both human sign-off gates in CLAUDE.md's list,
taken on #371 by the dispatched implementer d-20260819-032929-8d939f
Reviewed-by-human: pending
Supersedes: none — no prior decision covers the alias or the row; the grant this rides on
(`Bash(just mutation-compare:*)`) predates it as a permission fact only
Claimed: 0077 — scanned after `git fetch origin` with `docs/adr/` on `origin/main` topping at
0074 (`6e85b10`), then all 100 open issues' bodies and comments swept for an ADR number at or
above 0075. Two claims found, both below this one: ADR-0075, held by #392's unlanded branch
and referenced from the #391 and #340 threads, and ADR-0076, recorded on #340's thread as a
landed-pending delegation. Nothing at or above 0077 anywhere. The sweep's known blind spot is
CLAUDE.md's own: it reads open issues, so a claim whose issue closes before its ADR lands is
invisible to it — the rebase backstop catches that, as it did for #171

## What happened

#371 exists because `tools/brief.py`'s surviving mutants went unnameable through every round
of #325: the mutation harness writes mutated source in place, the sandbox refused that to both
the implementing and the reviewing seat, and neither `--report` nor an exhaustive pass was
available to anyone asked to judge the survivors.

The fix has two halves, and only one of them is ungated. `justfile` gains the
`mutation-compare` recipe, fronting `tools/mutation_smoke.py` under the standing
`Bash(just mutation-compare:*)` grant — a permission fact from 2bd3e8f whose recipe was never
built, which is precisely the gap. The other half is the row that table's own rule demands:
*"landing such tooling means landing its recipe and table row in the same commit"*, and the
table sits on `AGENTS.md`, a human sign-off gate. The `just mutation` row's text must change
with the same landing or it stops describing the tool: `--report` now names every survivor a
green floor tolerates, and `SURVIVES_BY_DESIGN` is a second named escape beside
`NO_MUTABLE_SUBJECT`. CLAUDE.md names this exact situation and its remedy: where an agent
cannot land the row with the recipe, *"the row follows through the sign-off gate — human
approval or an ADR-0013 record — rather than lagging silently"*.

The row also cannot wait for the human without recreating the lag that rule was written
after: #198/#199 proposed their rows and ADR-0057 landed them, and in the interim the table
described recipes that did not exist. Here the failure would be the mirror of it — a recipe
that exists and no row names, on the one command a dispatched session can type and `just
mutation` it cannot.

## Decision

The `just mutation-compare` row lands in the same change as the recipe it fronts, and the
`just mutation` row's `--report` and escape-list wording is updated to match the tool as
landed. Both edits are this delegation's entire scope.

## Why this was taken under the standing authorisation rather than referred

The human's authorisation of 2026-08-19 (#217): *"I empower and authorise you to make
decisions on my behalf. Use your best judgement."* It removes the need to wait; it keeps
ADR-0013's recording requirement in full, which this file is. The session taking the decision
is single-shot and dispatched: it has no second turn and nobody to approve a prompt, so
"refer it" would have meant landing the recipe with no row — the silent lag the table's own
rule forbids — or landing nothing and leaving #371's capability work half done. The
unambiguous half (recipe, harness fix, tests, docs where not gated) landed regardless; this
record covers only the gated text.

## What would overturn this

Stated so a reviewer can disagree by pointing at evidence rather than at taste (ADR-0019).

1. **The human rejecting the row's wording at sign-off.** This ADR is a stand-in for that
   sign-off, not a substitute for it; `grep -rl "^Reviewed-by-human: pending" docs/adr/`
   returns it.
2. **The `Bash(just mutation-compare:*)` grant being narrowed or removed.** The recipe would
   then front a permission that no longer exists, the row would promise a dispatched session
   something it cannot type, and both the row and the recipe should go together rather than
   either stand misdescribing the other.
3. **A better name being ruled for the alias.** The name is the grant's, kept deliberately
   (#371's justfile comment records why: renaming spends a permission change and buys
   nothing). A human ruling that the name misleads is a wording change to this row and the
   recipe's, not a structural one.
4. **#353's unlanded contract half landing a competing paragraph.** The seat-capability
   section in `docs/review-dispatch.md` states the sampled-or-exhaustive paste rule from
   #353's ruling because main's copy of that contract did not yet carry it; if #353's branch
   lands its own statement of the rule, the two merge and the capability table stays — the
   section's purpose is orthogonal to the paste rule it sits beside.

## Scope

This records the gated-text delegation only. The `justfile` recipe, the harness changes to
`tools/mutation_smoke.py`, the tests, `CHANGELOG.md`, and the seat-capability section in
`docs/review-dispatch.md` are not sign-off gated and ride on #371's own acceptance criteria,
not on this record.
