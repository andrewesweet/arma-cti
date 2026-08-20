#### Changed

- The unit tier runs on pytest-xdist's work-stealing scheduler (`--dist worksteal`)
  instead of the default `--dist load`, which never rebalances: the run's wall clock
  was set by the unluckiest worker's blind consecutive block of tests, a block whose
  size grows with the test count. Same collection and same assertions — 5,154 tests
  collected and passed before, 5,155 after (the one new test asserts the
  configuration itself). Measured 2026-08-20, kernel monotonic clock: the
  `just unit` tier's wall read a median of 150.45 s over four runs on
  `--dist load` and 71.25 s over ten on work-stealing, and a whole `just fast`
  162.05 s over two runs against 93.6 s over four. These endpoints were not
  load-controlled and the arms ran sequentially, not interleaved — every
  `load` row 15:37–15:47Z, every work-stealing row 15:50–16:15Z, 1-minute load
  across the post-set rows 0.25–5.49 with `foreign_gate_processes` 0 each time.
  The evidence supports a real, large step — same-SHA `load` rows at 148–159 s
  against work-stealing rows at 69–75 s, plus an independent run at 69.6 s —
  and the new ~71 s expectation; it does not isolate the full 2.11× ratio as
  scheduler-caused, because the session's green `unit` walls under `--dist load`
  include a 134.56 s run alongside the 148–159 s rows above — same recipe, same
  scheduler, all before the change — so the ratio's numerator is one position
  in a spread the scheduler did not cause.
