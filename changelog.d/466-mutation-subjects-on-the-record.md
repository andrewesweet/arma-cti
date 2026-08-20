#### Added

- The gate-duration record carries `mutation_targets`: how many targets
  `just mutation` will do work on in the tree the run gated — the test modules
  `tools/mutation_smoke.py`'s `in_scope` selects, minus the ones its
  `NO_MUTABLE_SUBJECT` list excuses, plus its Rust arm counted as one. It is
  obtained at record time by asking those names of the tier, is never declared
  by a flag, and both recording recipes write it. The recorder's own line now
  names the count beside the test count, and `just gate-clock-history`'s
  per-recipe line names the green runs that carried no target and the green runs
  that predate the field, each clause appearing only where that count is
  nonzero.

#### Changed

- `just fast`'s drift comparison reads only green runs that gave the mutation
  tier a target, and `just gate-clock-history` applies that same filter before
  taking the recipe's median and span. Only the filter is shared: the comparison
  also drops every row before the anchor's `set` moment and the history never
  has, so a re-set anchor leaves the two reading different rows; and where both
  take their median over the last ten rows they hold, the history's span covers
  every row it kept rather than that window.

  Every other leg of both recipes prices the whole tree
  whatever the diff holds, so `just mutation` is the one leg whose cost the diff
  moves and a run without a target for it is systematically cheaper; admitted to
  the window, such a run drags the median down, which is the direction that
  makes a real slowdown read as ordinary. `just unit` records the count and
  compares on it not at all, its own legs being diff-independent.

  The count is of the selected targets the tier will do work on — every target
  `in_scope` selects except the ones `NO_MUTABLE_SUBJECT` excuses — rather than
  of mutants planted or of every target selected. How many mutants a run planted
  is settled inside a run the recorder cannot see, while selecting a target
  already commits the tier to one coverage-instrumented pytest pass of that
  module before it can know whether there is anything to plant on. The exempt
  targets are the one place where that does not hold, so they are subtracted:
  `in_scope` selects them like any other and `just mutation` then prints their
  `-- exempt:` line and moves on without running them, so counting them would
  have admitted a floor-priced run to the window carrying a code run's count.

  The count is not a docs-only flag and is not read as one. A change to a
  product module that adds or rewrites no test module counts zero as well,
  because the tier plants nothing against that either and the run costs what a
  docs-only run costs.

  Records written before this change carry no count, read as unclassified, and
  leave that window alongside the zero rows. `just fast` therefore reports
  `insufficient_sample` until five green runs carrying a target have been
  recorded at or after its anchor's `set` moment. The anchor itself is
  unchanged.
