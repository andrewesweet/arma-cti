## Fixed

- Eight statements about the mutation gate that its code did not support, all
  text and no behaviour. `ratchet_floor`'s docstring named a dropped mutant's
  cause as "its graft changed nothing, or no test reaches its line"; a graft
  that changed nothing compiles and survives, and the second half is unreachable
  for a chosen mutant, so the cause is now the one `graft` has — a graft that
  will not compile, or on the shell arm will not parse. The same docstring
  counted four release cases against a condition with five and now counts five,
  naming the hand-edited row with no sample. The determinism claims no longer
  assert a three-kill bound as derived: the three clock-reads are stated as
  compounding, with no bound on how many kills they can move between them
  derived, and one of them costing more than one kill is no longer implied — a
  straddling test leaves the selection of every line it reached, the over-ceiling
  fallback runs per line, and machine load is a condition of the whole run.
  `BUDGET_S` no longer cites the shell arm's §3 as the precedent for where its
  size is recorded; §3 sizes `SHELL_FLOOR` and records no budget. `#435`'s
  changelog fragment claimed "every spawned subprocess" runs under one pinned
  `PYTHONHASHSEED` where the code pins only every Python subprocess this gate
  spawns, and the same widened claim in two docstrings is narrowed with it. The
  research note's §0 now excludes the `BUDGET_S` survey from its 2026-08-05
  reading and dates it to `1a140df`, and §7's cost row is tied to the tree it was
  measured on. A test comment attributing a changed denominator to the budget is
  replaced by the causes that remain, the budget having refused since #435 round
  2.
