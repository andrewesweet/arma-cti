### Changed

- **`/orchestrator-tick` is reduced towards steps, commands and pointers, and
  factual defects in it are corrected (#643).** The harvest section now carries the
  review dispatch's completion edge without serialising the cohort: exchange, dispatch
  and arm `just watch` for every finished branch first, then wait on a single
  `just dispatch-follow` invocation over them all, and only then run `just review
  record`, which `tools/review_exchange.py` refuses as `no_review_dispatch` without a
  completed review dispatch. The post-landing review dispatch gets that same watcher and
  follower. Where `just watch-report` prints `action=refill-before-landing`, the refill
  section now runs before the harvest as well as before the landing, so the refill no
  longer waits behind a review. Review dispatches no longer
  compose a brief at all — `just brief` and `just dispatch` name different worktrees and
  #647 is cited as the blocked state, so they take the default brief until it lands. The
  landing section reads `ok=landed`, the key `tools/land.py` prints on success, rather
  than `landed=`. The turn top drops `--count N`, which cannot widen the candidate list
  past available WIP room, and section 4 now reads the eligible issues named by
  `considered.N=eligible` before ranking them. The `cti.dispatch-plan/1` line no longer
  claims #463 mandates applying a routing block by hand; it says nothing reads the block
  and its treatment is undecided. Rationale and code-restating prose elsewhere in the
  file is cut in favour of the pointer that owns the rule.
