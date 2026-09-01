### Fixed

- The foreseeable-wait grader now honours a foreground wait stated before later
  handoff language, and its shipped cases pin that disposition.
- Frozen eval-context reductions pin their derivation source sha256 and refuse to run
  when the live source has changed; the imperatives-only arm is refreshed from the
  current `AGENTS.md`.
- `just prereqs check` resolves bubblewrap with the eval runner's search path and prints
  a runnable install command when it is missing.
