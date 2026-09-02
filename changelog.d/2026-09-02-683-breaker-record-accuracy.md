### Fixed

- **The pool crash breaker's durable record now says what it did (#683).** Four
  record-accuracy defects in #72's breaker are closed, none of them a behaviour change:
  the crash stop line counts the crash run it names rather than always the rule's
  threshold of two, so a three-crash run no longer reads "abandoned after 2" over three
  named probes; `CORPUS_CRASH_RULE`'s `failure_class` now carries a comment stating it is
  never the pool's exit class — a genuine crash trip exits on the `node_crashed` verdicts
  it collected, and typing that stop `infra_unavailable` would turn a result into a
  not-a-result; the `stop-decision-failure` marker write can no longer be downgraded by a
  later racing worker — a worker writes only when no marker stands or the standing one
  ranks lower in the failure-class table; and `$POOL_OUT/stop` has one writer, the merge,
  whose post-drain recount is the final rendering — the shell's redundant rewrite after
  the merge is deleted. `docs/regression-tier.md`'s merge section now states the marker,
  the `worst_class` overlay and the post-drain recount, which it had never carried.
