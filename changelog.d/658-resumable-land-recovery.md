### Changed

- **`just land` can resume its post-push half after exit 2 (#658).** Run
  `just land --resume --audit-file FILE` after the named `merge_command=`. The mode accepts a
  clean worktree whose `HEAD` is already on `origin/main`, performs the same fast-forward step
  when the main checkout still needs it, posts the supplied audit as one comment, and closes only
  from that comment's successful posting receipt. It does not re-run the gate or push again; exit 2
  still means the work is on `origin/main` with a step outstanding.
