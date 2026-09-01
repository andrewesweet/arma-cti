### Fixed

- The foreseeable-wait grader classifies recognized dispositions and reports unmatched
  prose as `unclassified`; its shipped cases pin both graded dispositions and misses.
- The eval runner reports `unclassified` answers separately and calculates rates over
  graded answers only, making the report's denominator and incomplete grading explicit.
- Frozen eval-context reductions pin their derivation source sha256 and refuse to run
  at corpus-run preflight when the live source has changed; the imperatives-only arm is
  refreshed from the current `AGENTS.md`.
- `just prereqs check` resolves bubblewrap with the eval runner's search path and prints
  a runnable install command when it is missing.
