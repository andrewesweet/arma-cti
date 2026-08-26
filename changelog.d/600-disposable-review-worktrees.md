### Changed

- Review and recon dispatches run gates in dispatch-owned disposable worktrees; Codex receives workspace-write only for that run's cwd and the existing measured tool-cache roots, and the worktree is removed on completion, failure, stop, or observed runner disappearance.
