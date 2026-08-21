### Fixed

- **All 19 `*args` recipes that still re-split values now preserve the caller's argument
  boundaries (#477).** Quoted phrases reach the wrapped command as one argument; separately
  supplied flags, values, and shell-expanded globs remain separate. The changed recipes are
  `check-arbiter`, `regress`, `mutation`, `worktree`, `land`, `review`, `dispatch`,
  `dispatch-follow`, `watch`, `watch-report`, `recover`, `breaker`, `trial`, `ledger-sync`,
  `brief`, `occupancy`, `prereqs`, `verdict`, and `review-loop`; the three recipes already using
  positional forwarding are unchanged.
