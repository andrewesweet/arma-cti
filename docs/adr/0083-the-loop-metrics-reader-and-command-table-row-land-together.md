# The loop metrics reader and command-table row land together

Delegated-decision: yes
Date: 2026-09-01
Stood-in-for: human sign-off on one edit to `AGENTS.md`'s command table — the new
`just loop-metrics` row — under the ADR-0013 command-table route. The reader and its
recipe are described by that row and land in the same commit.
Reviewed-by-human: pending
Supersedes: none
Claimed: 0083 — `origin/main` in this checkout tops at ADR-0082; `git fetch origin` was
attempted but the Codex sandbox refused its `FETCH_HEAD` write. A scan of all issue
comments found no ADR-0083 claim. The rebase backstop remains the final collision check.

## What happened

#602 needs an on-demand read of the dispatch, review-loop and stock records already on
the box. The command must be reachable through `just`, while the command table is a
human-gated surface. The issue explicitly excludes the controller, live dispatch and
MLflow from this reader.

## Decision

Under the standing authorisation, the `just loop-metrics` row may land with its recipe.
The row describes the reader's metric families, intervals and variance, explicit
uncertainty, end-window stock/flow distinction, Delivery Gap quality boundary and
read-only zero-gating behaviour. `check-command-table` must confirm that the changed
table line is a data row and that the named recipe exists at the same commit.

The reader accepts version-1 review records and the version-2 `self_review` block from
#589. A self-review finding is matched to an independent finding only by the same
non-empty id, the same issue and one unique independent occurrence. Different ids,
missing identities and duplicate independent identities remain unmatched or ambiguous;
the reader does not invent a line-level or semantic match. Catch fraction is emitted as
an upper bound, and self-review absence is never counted as zero.

The reader does not write a projection or alter any source. Metric values, missing
evidence and insufficient observations never change its exit status; malformed command
arguments are still reported by argparse. No world-facing surface is involved, so the
Arma corpus is not part of this work item's gate.

## What would overturn it

The human rejects the command-table wording or rules that the reader belongs behind the
controller. In that case the row and recipe are withdrawn together, and this record is
the process finding against the delegated decision; the durable reader's metric design
would need its own ruling before it is exposed through another command surface.
