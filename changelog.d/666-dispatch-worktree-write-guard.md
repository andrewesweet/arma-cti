### Fixed

- **Dispatched write hooks now reject targets in another checkout of this repository (#666).**
  Absolute, parent-relative, and symlink-resolved paths that escape the assigned worktree into
  the main or a sibling checkout are refused before a hook-covered file or shell write reaches it.
