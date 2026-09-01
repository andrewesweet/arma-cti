### Added

- **A positive Git and shell destination reader for dispatch hooks (#673).** Known local reads
  remain free, common in-tree repository writes retain their assigned location, explicit `-C`,
  `--git-dir`, `--work-tree` and supported `cd` targets are resolved, and unknown or
  unresolvable shapes refuse with the construct that could not be proved safe. Unsupported
  wrappers, environment assignments and nested interpreters remain outside the reader's claim;
  the hook integration enforces its positive checks at the Bash boundary.
