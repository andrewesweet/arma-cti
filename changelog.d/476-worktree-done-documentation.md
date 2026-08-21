### Changed

- Corrected `just worktree done`'s inline safety documentation to state that each commit unreachable from `origin/main` requires `git cherry` nomination and byte-identical full-index binary diff bytes matching an upstream commit, while unreachable merges always refuse removal.
