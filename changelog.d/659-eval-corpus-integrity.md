### Fixed

- The foreseeable-wait grader classifies recognized dispositions and reports unmatched
  prose as `unclassified`; its shipped cases pin both graded dispositions and misses.
- Frozen eval-context reductions pin their derivation source sha256 and refuse to run
  when the live source has changed; the imperatives-only arm is refreshed from the
  current `AGENTS.md`.
- `just prereqs check` resolves bubblewrap with the eval runner's search path and prints
  a runnable install command when it is missing.
