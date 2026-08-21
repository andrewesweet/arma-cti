### Fixed

- `just worktree done` now permits an unreachable commit only when `git cherry` nominates
  it and its byte-exact Git diff matches a commit on `origin/main`; patch-ID matches alone
  and merge commits still refuse removal.
