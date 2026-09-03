# The #694 review-row correction lands under the command-table route

Delegated-decision: yes
Date: 2026-09-03
Stood-in-for: human sign-off on the `AGENTS.md` `just review` command-table row as
corrected by #694, under the ADR-0013 command-table route. The diff changes one row's
clause order so the remote-SHA verification attaches to the push it belongs to; the
`review` recipe resolves in the justfile at this commit.
Reviewed-by-human: pending
Supersedes: none
Claimed: 0085 — `git fetch origin` was run and `origin/main` holds ADR-0084 as the
highest; a scan of open issue comments found no ADR-0085 claim.

## What happened

#688's rewrite of the `just review` row inserted the `exchange_outside_issue_worktree`
refusal clause in front of the remote-SHA verification clause, so the row attributes
that verification to the refusal path. It belongs to the push:
`tools/review_exchange.py` returns the refusal at line 245 before any remote read,
and the push verifies `remote_ref_sha` against the pushed HEAD afterwards. #694
corrects the clause order. The diff is confined to command-table data rows and is
therefore exactly the shape #544's standing rule routes without per-hunk approval,
which is how #688's own rows landed with ADR-0084 in the same commit.

## Decision

Under the standing authorisation, the corrected `just review` row may land without a
separate per-hunk approval, on the command-table route's own confinement: the checker
derives that every changed line sits inside a table row and that the row's recipe
resolves in the candidate justfile. Never-alone review is unchanged and still applies.

## What would overturn it

A human reads the corrected row and finds the verification clause still misplaced, or
finds the reordering changed the row's meaning beyond the clause move #694 describes.
Either finding overturns this authorisation and reverts the row, and the diff then
travels the direct-approval path instead.
