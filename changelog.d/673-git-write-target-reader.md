### Added

- **A conservative Git write-target reader for dispatch hooks (#673).** Known local reads remain
  free, common in-tree repository writes retain their assigned location, explicit `-C`,
  `--git-dir`, `--work-tree` and supported `cd` targets are resolved, and unknown or
  unresolvable shapes return the hook's fail-closed result. The hook integration enforces
  these checks at the Bash boundary.
