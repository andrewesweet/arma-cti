# The transcript-audit tool and command-table row land together

Delegated-decision: yes
Date: 2026-09-03
Stood-in-for: human sign-off on one edit to `AGENTS.md`'s command table — the new
`just transcript-audit` row — under the ADR-0013 command-table route. The tool and its
recipe are described by that row and land in the same commit.
Reviewed-by-human: pending
Supersedes: none
Claimed: 0086 — `origin/main` in this checkout tops at ADR-0085; `git fetch origin` ran
2026-09-03 in worktree `issue-698`, and #698's thread names no other claim above 0085.

## What happened

#698's checker (`tools/transcript_audit.py`) landed without its command surface: the
review's first round refused the direct `uv run python tools/…` invocation documented in
`docs/agents/measurement-records.md` as a command-surface violation, because `CLAUDE.md`
requires landed tooling to bring its `just` recipe and its command-table row in the same
commit. The command table is a human-gated surface, and the standing authorisation's
mechanical face — the `.claude/settings.json` allowlist — discharges nothing by itself.

## Decision

Under the standing authorisation, the `just transcript-audit` row may land with its
recipe. The row describes what the tool derives and refuses — the emit-side newest-JSONL
derivation, the missing-output row for an invocation whose `tool_result` never arrived,
the block's name-plus-full-SHA-256 binding to its producing transcript,
`transcript_changed`, `record_block_modified`, `record_block_missing`,
`record_block_ambiguous` and `claim_not_in_transcript` — that cell values are bounded
while verification searches the full text, that `--record -` reads the record from
stdin, and that it reads and never gates.

The round-one review also refused the record-to-producer binding and the checker's
silent drop of an unmatched trailing invocation; both are fixed in the same diff, and
this record covers the command surface they make necessary. `check-command-table` must
confirm that the changed table line is a data row and that the named recipe exists at
the same commit.

## What would overturn it

The human rejects the command-table wording, or rules that the checker belongs behind a
gate leg after all — a deliberate choice this issue declined twice and recorded in
`docs/agents/measurement-records.md`. In that case the row and recipe are withdrawn
together, and this record is the process finding against the delegated decision; the
checker itself is read-only and would survive the withdrawal of its surface.
