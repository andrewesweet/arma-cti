### Changed

- **`/orchestrator-tick` is reduced to steps, commands and pointers, and its
  factual defects are corrected (#643).** Rationale, worked examples and prose
  restating what the code does give way to the path, ADR, ruling or issue that
  owns the rule. The tick now opens with a turn-top section — `just
  watch-report`, `just controller reconcile`, `just queue state` and `just queue
  next` — and runs the refill ahead of the harvest and the landing when `just
  watch-report` prints `action=refill-before-landing`. The harvest launches the
  whole review cohort before waiting on any of it: exchange, dispatch and arm
  `just watch` for every finished branch, then wait on a single `just
  dispatch-follow` invocation over them all, process the review that returns,
  and only then re-follow the remainder. An interactive author declares itself
  with `just review-loop author` before the first review dispatch, so reviewer
  resolution cannot resolve to the author. Review dispatches take the default
  brief until #647 lands, under the human's ruling of 2026-08-30 on #643. The
  landing section names `just land --audit-file`, its `--corpus` argument, the
  `ok=landed` and `gate_review=` lines it prints, the exit-2 rerun, the
  post-landing review and the `just observatory` commit that follows it. `just
  verdict` is given its pool rather than left to pick one. Section 4 ranks by
  kind, in place of the specific issue numbers that were eligible when the file
  was written.
