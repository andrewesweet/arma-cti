### Fixed

- **The pool crash breaker's durable record now says what it did (#683).** Four
  record-accuracy defects in #72's breaker are closed, none of them a behaviour change:
  the crash stop line counts the crash run it names rather than always the rule's
  threshold of two, so a three-crash run no longer reads "abandoned after 2" over three
  named probes; `CORPUS_CRASH_RULE`'s `failure_class` now carries a comment stating it is
  never the pool's exit class — a genuine crash trip exits on the `node_crashed` verdicts
  it collected, and typing that stop `infra_unavailable` would turn a result into a
  not-a-result; a worker that could not read the stop decision now writes its own
  `stop-decision-failures/<probe>` candidate file instead of one shared marker, and
  `pool_merge` stands the worst class among the candidates by its own severity table, so
  no racing worker can overwrite or downgrade another's record; and the shell's rewrite
  of `$POOL_OUT/stop` from the merge's summary output is deleted — the merge's post-drain
  recount is that file's final write, the five worker writes that create it standing
  unchanged. `docs/regression-tier.md`'s merge section now states the candidate files,
  the `worst_class` overlay and the post-drain recount, which it had never carried.
