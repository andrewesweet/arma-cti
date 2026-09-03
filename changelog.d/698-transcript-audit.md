# Added

- `tools/transcript_audit.py` checks a measurement record against the dispatch transcript
  that produced it (#698): it recovers every tool invocation and output from the session
  transcript, renders a deterministic `transcript-audit` block the record carries, and
  `verify` refuses an edited, missing or duplicated block, plus prose naming a full SHA or
  a backticked `git` command no transcript row carries. Both #695 shapes — an omitted
  invocation and a substituted SHA — are caught and pinned by tests named for the case.
  `docs/agents/measurement-records.md` records what the durable transcript holds and the
  route decision; `docs/review-dispatch.md` carries the review obligation beside the
  paste-discipline rule.
