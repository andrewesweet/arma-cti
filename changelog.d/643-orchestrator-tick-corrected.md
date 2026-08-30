### Changed

- **`/orchestrator-tick` is rewritten as steps, commands and pointers (#643).**
  Rationale and worked examples are removed, and prose restating what the code
  does is replaced by the path, ADR, ruling or issue that owns the rule. The
  tick opens with a turn-top section — `just watch-report`, `just controller
  reconcile`, `just queue state` and `just queue next` — and runs the refill
  ahead of the harvest and the landing when `just watch-report` prints
  `action=refill-before-landing`. The harvest launches the whole review cohort
  before waiting on any of it: exchange, dispatch and arm `just watch` for
  every finished branch, then wait on a single `just dispatch-follow`
  invocation over them all, process the review that returns, land it and refill
  the freed capacity, and only then re-follow the remainder. Each `just watch`
  names the dispatch record's `result.json` as its subject rather than taking
  the default newest pool, and the review dispatch's watcher is armed over the
  issue's own worktree rather than the review's own tree. A
  `refill-before-landing` turn top now runs the refill only as far as arming
  that watcher, leaving the new dispatch to be followed with the harvest
  cohort. The post-landing review is written as its own pass — dispatch, watch,
  follow, then route its claims as `docs/review-dispatch.md` routes them — and
  runs neither `just review-loop sync` nor `just land`. An interactive
  author declares itself with `just review-loop author` before the first review
  dispatch, so reviewer resolution cannot resolve to the author. Review
  dispatches take the default brief until #647 lands, under the human's ruling
  of 2026-08-30 on #643. The landing section names `just land --audit-file`,
  its `--corpus` argument, the `ok=landed` and `gate_review=` lines to read,
  the exit-2 rerun, the post-landing review, `just trial close-audit` after the
  close it audits, and the `just observatory` commit that follows. The refill
  gives the continuation a step for each worktree state: `add` where there is
  no tree, `restore --ref` for work archived on a named remote ref, and `check`
  where a tree is already present. `just verdict` is given its pool rather than
  left to pick one. Section 4 ranks by kind, in place of the specific issue
  numbers that were eligible when the file was written.
