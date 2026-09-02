### Fixed

- **The pool crash breaker's durable record now says what it did (#683).** Four
  record-accuracy defects in #72's breaker are closed; the crash-trip semantics —
  which adjacent runs of crashes trip the breaker, and at what threshold — are
  unchanged, while the record they leave is deliberately not: the crash stop line
  counts the crash run it names rather than always the rule's threshold of two, so a
  three-crash run no longer reads "abandoned after 2" over three named probes;
  `CORPUS_CRASH_RULE`'s `failure_class` now carries a comment stating it is
  never the pool's exit class — a genuine crash trip exits on the `node_crashed` verdicts
  it collected, and typing that stop `infra_unavailable` would turn a result into a
  not-a-result; a worker that could not read the stop decision now writes its own
  `stop-decision-failures/<probe>` candidate file instead of one shared marker, and
  `pool_merge` stands the worst class among the candidates by its own severity table —
  accepting only `infra_unavailable` and `untyped_harness_failure`, the two ways a stop
  decision can fail, so a corrupt candidate reading any other class is an untyped red
  rather than a greener verdict — so no racing worker can overwrite or downgrade
  another's record; a pool whose evidence directories could not be created now refuses
  naming them rather than always the claims path; the merge now reads a stopped
  pool whose evidence explains nothing — all-pass rows, no mem-stop, no
  stop-decision candidate — as `untyped_harness_failure` rather than green, so a
  stop record that failed to be written can no longer read as health; and the shell's
  rewrite of `$POOL_OUT/stop` from the merge's summary output is deleted — the merge's
  post-drain recount is that file's final write, the five shell writes that create it
  (four from workers, one from the starvation watch) standing unchanged. The worker's
  candidate write reports its own failure where it fails, no longer load-bearing under
  the merge-side invariant. `docs/regression-tier.md`'s merge section now states the candidate files,
  the `worst_class` overlay and the post-drain recount, which it had never carried.
