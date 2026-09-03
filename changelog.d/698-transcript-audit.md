# Added

- `tools/transcript_audit.py` checks a measurement record against the dispatch transcript
  that produced it (#698): it extracts the tool invocations the session transcript holds,
  rendering an invocation whose output never arrived as a missing-output row rather than
  dropping it, and renders a deterministic `transcript-audit` block whose header binds the
  record to its producing transcript by file name and full SHA-256. `verify` reads that
  bound transcript, refuses `transcript_changed` where its content has moved, and refuses
  `record_block_modified`, `record_block_missing` and `record_block_ambiguous`, plus
  `claim_not_in_transcript` where the prose names a full SHA or a backticked `git` command
  no transcript row supports. Verification searches the full command and output text;
  only the rendered cells are bounded. The tool's surface is `just transcript-audit`, and
  `--record -` reads the record from stdin. Both #695 shapes — an omitted invocation and
  a substituted SHA — are caught and pinned by tests named for the case.
  `docs/agents/measurement-records.md` records what the durable transcript holds and the
  route decision; `docs/review-dispatch.md` carries the review obligation beside the
  paste-discipline rule.
