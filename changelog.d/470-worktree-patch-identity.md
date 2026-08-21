### Fixed

- `just worktree done` now removes a clean tree when every commit's patch is already on
  `origin/main` under another SHA, while still refusing `unlanded_work` with the number of
  commit patches absent from upstream.
