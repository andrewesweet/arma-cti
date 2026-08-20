#### Changed

- The unit tier runs on pytest-xdist's work-stealing scheduler (`--dist worksteal`)
  instead of the default `--dist load`, which never rebalances: the run's wall clock
  was set by the unluckiest worker's blind consecutive block of tests, a block whose
  size grows with the test count. Same collection and same assertions — 5,154 tests
  collected and passed before, 5,155 after (the one new test asserts the
  configuration itself). Measured on a quiet box, 2026-08-20, kernel monotonic
  clock: the `just unit` tier's wall fell from a median of 150.45 s over four runs
  to 71.25 s over ten, and a whole `just fast` from 162.05 s over two runs to
  93.6 s over four.
