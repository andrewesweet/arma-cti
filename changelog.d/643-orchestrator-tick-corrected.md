### Changed

- **`/orchestrator-tick` is reduced towards steps, commands and pointers, and four
  factual defects in it are corrected (#643).** The harvest section now carries the
  review dispatch's completion edge: arm `just watch`, wait on `just dispatch-follow`,
  and only then run `just review record`, which `tools/review_exchange.py` refuses as
  `no_review_dispatch` without a completed review dispatch. Review dispatches no longer
  compose a brief at all — `just brief` and `just dispatch` name different worktrees and
  #647 is cited as the blocked state, so they take the default brief until it lands. The
  landing section reads `ok=landed`, the key `tools/land.py` prints on success, rather
  than `landed=`. The turn top drops `--count N`, which cannot widen the candidate list
  past available WIP room, and section 4 now reads the eligible issues named by
  `considered.N=eligible` before ranking them. The `cti.dispatch-plan/1` line no longer
  claims #463 mandates applying a routing block by hand; it says nothing reads the block
  and its treatment is undecided. Rationale and code-restating prose elsewhere in the
  file is cut in favour of the pointer that owns the rule.
