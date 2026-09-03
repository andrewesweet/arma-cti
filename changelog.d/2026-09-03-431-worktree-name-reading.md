# Fixed

- `just dispatch --worktree <name>` reads a bare name as a worktree name, under `.claude/worktrees/`, the same way `just worktree restore` reads it, instead of as a path relative to the caller's directory; explicit paths (absolute, `~`-led, dot-led or carrying a separator) resolve as before, and a `worktree_missing` refusal now names every path it looked at.
