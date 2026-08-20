## Fixed

- The mutation gate's kill count was not repeatable: one module measured 16/20
  and 15/20 at the same SHA, with the hash seed pinned as well as unpinned. The
  cause was test selection — durations measured afresh each run jitter past the
  cost grain, and the cumulative per-mutant wall-clock bound cut inside that
  jitter, moving 532 of 874 covered lines' selections between two measurements
  of an unchanged module. Selection membership now takes every reaching test
  under a per-test ceiling and reads the clock only there — at that ceiling
  boundary, and in the over-ceiling fallback that keeps one cheapest test for a
  line all of whose tests are over it; every spawned subprocess also runs under
  one pinned `PYTHONHASHSEED`. The
  per-module budget was re-sized against a measured survey so the cap, not the
  clock, decides how many mutants run — and a loop the budget still cuts short
  now refuses rather than reporting a rate on the smaller denominator the clock
  chose. The module's determinism claims are restated with the bound that
  actually holds — three clock-reads can each still flip one kill — and `SLACK`
  now takes one of them as a stated tolerance rather than a derived bound.
