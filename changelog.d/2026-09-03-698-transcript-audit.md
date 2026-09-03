Added: `tools/transcript_audit.py` checks a measurement record against the dispatch
transcript that produced it (#698). It recovers every tool invocation and output from the
session transcript, renders a deterministic `transcript-audit` block the record carries, and
`verify` refuses a block that was edited, a missing or duplicated block, and prose that
names a full SHA or a backticked `git` command no transcript row carries — both #695 shapes
(omitted invocation, substituted SHA) are caught and pinned by tests named for the case.
`docs/agents/measurement-records.md` records the route decision — generate-and-verify over
author-composed citations, a `just check` gate leg, and obligation-only — with what the
durable transcript holds, and `docs/review-dispatch.md` carries the review obligation
"read the transcript, not just the record" beside the paste-discipline rule. Codex
transcripts are unsupported and refuse `harness_unsupported`; the checker is opt-in at
review, never a gate leg.
