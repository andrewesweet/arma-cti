# A measurement record checked against its transcript

**Outcome: the transcript already holds what the record claims, it is mechanically
recoverable, and the chosen route is a checker — `tools/transcript_audit.py` — plus the
review obligation it makes cheap. The author-side discipline that failed on #691 and #695
stays retired.**

Two issues and thirteen review rounds paid for one lesson: a measurement record composed by
the agent that produced it is a self-report. #695's record substituted a corrected SHA for
the one its transcript shows being run, and omitted the invocation that returned
`fatal: invalid upstream`; explicit instruction in two briefs did not prevent either, because
nothing checked the write-up against the run. This document is #698's answer.

## What the durable transcript actually contains

Two stores exist, and neither alone is the record:

- **The dispatch record**, `~/.arma-cti/dispatches/<id>/` — `dispatch.json` (argv, seat,
  lane, profile, worktree, base SHA), `dispatch.log` (the runner's stdout/stderr), and the
  bounded final response. The review half of #695 itself says what this cannot answer:
  *"Review delivery captured only the bounded final-response section from child stdout.
  Output outside its markers and output on other streams were not posted."*
- **The session transcript**, `~/.claude/projects/<worktree-slug>/<uuid>.jsonl` — one JSON
  event per line, written by Claude Code for `claude --print` sessions exactly as for
  interactive ones. Every tool invocation is an `assistant` event carrying a `tool_use`
  block (`name`, `input`, a `tool_use_id`), every output is a `user` event carrying the
  matching `tool_result`, and both events carry `timestamp`, `sessionId`, and the worktree
  as `cwd`.

Recoverability was measured from inside a dispatched session on 2026-09-03 (this issue's own
run, worktree `issue-698`): `wc -l`, `\grep`, `head -c` and glob expansion over the absolute
transcript path all ran under `acceptEdits`, while `ls` on the same directory, `python3 -c`
and `uv run python tools/…` were refused — the dated shape `docs/agents/dispatched-session-commands.md`
already records. A reviewer resolves any row mechanically: `sed -n 14p <transcript>` prints
the event behind it. Line numbers are stable — the file is append-only within a session.

The one genuine gap is **the mapping**. The dispatch record does not name its session
transcript, and `claude --print` prints the bounded final response, so no durable field
connects dispatch id to session uuid. What connects them today is derivation: one session
holds a worktree at a time (the #105 protocol), so the newest `*.jsonl` in the worktree's
project directory is that session's transcript. `find_transcript` derives it, and its
refusals name the rung that stopped: `transcript_not_found`, `transcript_unreadable`,
`transcript_malformed` (a line that does not parse — fail closed, never skip), and
`harness_unsupported` where no `tool_use` event is found, because a transcript with no
invocations is not evidence of a clean run, it is a transcript this module cannot read.

## The route: generate and verify, not cite or trust

Chosen: **the record carries a generated `transcript-audit` block, and a checker regenerates
it.** `tools/transcript_audit.py`:

- `emit` derives the transcript from the worktree, extracts every invocation it can recover,
  and prints the block — one row per invocation, each row carrying its transcript line,
  timestamp, tool, command and output, with named truncation (`…`) in the rendered cells.
  An invocation whose `tool_result` never arrived renders a **missing-output row**, never a
  silent drop: dropping it would re-create the omission this checker exists to catch.
  Deterministic by construction: no generation timestamp, so a re-run over the same
  transcript renders byte-identically.
- `verify` reads the transcript the record's block binds itself to — the block header names
  the transcript file and its full SHA-256 — refuses `transcript_changed` where that file's
  content has moved since the record was rendered, regenerates the block and refuses
  `record_block_modified` (a block that was edited — omission is this code's shape: the
  #695 test removes the `fatal: invalid upstream` row and verify goes red),
  `record_block_missing`, `record_block_ambiguous`, and — over the prose outside the block
  — `claim_not_in_transcript` for a full SHA or a backticked `git` command no transcript row
  carries. Both #695 shapes are caught, and both are pinned by tests named for the case
  (`test_six_nine_five_*`).

Why the alternatives lost:

- **A record that cites transcript offsets, composed by the author.** The citation is still
  composed by the agent that produced the run — the exact act that failed twice. And a
  checker that resolves citations still needs the complete invocation list to see what was
  *not* cited, so the citation route buys the same extraction code for a weaker guarantee.
  The block makes the list complete by construction; the author annotates prose around it
  and cannot delete a row without `record_block_modified`.
- **A gate leg in `just check`.** Two refusals: adding a leg means a `CLAUDE.md`
  command-table row and justfile recipe, which is a human-gated surface this issue was never
  given; and the decisive records are issue comments, which no repo-side gate can see. The
  checker is opt-in at review instead, where the reviewer already holds the record and the
  worktree.
- **A stated review obligation alone.** It was the fallback, not the answer: it is
  unenforced, and enforcement-by-obligation is the shape that ran thirteen rounds. It
  survives as the complement — `docs/review-dispatch.md` now carries "Read the transcript,
  not just the record" beside the paste-discipline rule — because a reviewer with the tool
  still has to reach for it.

**Where the tool may run** is the constraint that shaped the convention. A dispatched
session could not run it on 2026-09-03 (`uv run python tools/…` refused, measured). So:

- **Strong form** — a tool-generated `transcript-audit` block in the record, verified at
  review by `just transcript-audit verify --record <file> --worktree <path>`.
  The reviewer's or orchestrator's session, where approvals exist, runs it.
- **Citation form** — where emit could not run, the record's invocation evidence is cited to
  transcript lines with verbatim quotes, and the record says so plainly. A record with
  neither form is unaudited and says nothing about what ran.

The convention lands with its first applied instance: **#698's own close** carries the
citation form, extracted mechanically from this session's transcript, posted on the issue
beside the gate report.

## Limits, named

- **Codex dispatches are unsupported** — a different transcript shape, refused
  `harness_unsupported` rather than guessed at. Until a reader exists for it, a Codex
  measurement record's invocation evidence is citation-form only.
- **Not a gate leg.** The checker never blocks a landing; it sharpens a review. Making it
  one is the `CLAUDE.md` change above, taken deliberately not now.
- **Heads are bounded in the rendered rows only.** Command and output cells truncate at
  named limits (200/400 characters) with `…`; the row is a pointer to the transcript line,
  not a replacement for it. Verification searches the full command and output text, so a
  claim resolved by text past the rendered bound is still found — the scan does not accuse
  a claim the transcript carries merely because rendering bounded it.
- **The newest-JSONL derivation is `emit`'s, and its residual gap is stated.** `verify` never
  runs the derivation: the record's block binds itself to its producing transcript by file
  name and full SHA-256, so a later retry or fix session in the same worktree does not
  become the producer `verify` reads, and a transcript whose content has moved refuses
  `transcript_changed`. What the binding cannot guarantee is the *first* selection: `emit`
  takes the newest JSONL, which names the wrong session only where two sessions overlap one
  worktree, which the #105 protocol forbids — if it happens anyway, the block still carries
  the full digest of whatever file it was rendered from, so the record says exactly which
  transcript it is bound to and a reader can name the wrongness rather than discover it.
- **The record can also arrive as stdin** — `--record -`, for the reviewer holding a record
  that reached them as comment text. The record text is read, never written; the same
  checks run over it.
- **The transcript format is Claude Code's own**, not a contract this repo holds. A format
  change refuses `harness_unsupported` or `transcript_malformed` — a loud gap, not a silent
  pass.

## Using it

    just transcript-audit emit   --worktree <path> [--projects-root D]
    just transcript-audit verify --record <file> --worktree <path>
    just transcript-audit verify --record - --worktree <path>     # record on stdin

Exit 0 with `record_audit=ok rows=<n>` when the record holds; exit 1 with one
`record_audit=red code=…` line per problem, or `record_audit=refused code=…` where the
audit could not answer at all. Read-only: it writes nothing and gates nothing.

The citation form's first applied instance — the appendix on #698's thread — was found
inaccurate at review (grep counts read as event counts; a hand-taken digest that did not
cover the stated line count; outcome coordinates pointing at the invocation line rather
than the output line), and was corrected by regenerating it with this tool. The form
stays: where `emit` cannot run, a record's invocation evidence is cited to transcript
lines with verbatim quotes, and the record says so plainly — but the citation is now
checked the same way, by regenerating it, before the record is quoted.
