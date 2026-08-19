## Fixed

- The mutation gate's kill count was not repeatable: one module measured 16/20
  and 15/20 at the same SHA, with the hash seed pinned as well as unpinned. The
  cause was test selection — durations measured afresh each run jitter past the
  cost grain, and the cumulative per-mutant wall-clock bound cut inside that
  jitter, moving 532 of 874 covered lines' selections between two measurements
  of an unchanged module. Selection membership now takes every reaching test
  under a per-test ceiling and no longer reads the clock at all; every spawned
  subprocess also runs under one pinned `PYTHONHASHSEED`. The module's
  determinism claims are restated with the bound that actually holds — a rate
  is fixed up to one kill, which is what `SLACK` now says it absorbs.
