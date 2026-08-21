### Fixed

- **All 19 `*args` recipes that still re-split values now preserve the caller's argument
  boundaries (#477).** Quoted phrases reach the wrapped command as one argument; separately
  supplied flags, values, and shell-expanded globs remain separate. The three recipes already
  using positional forwarding are unchanged.
