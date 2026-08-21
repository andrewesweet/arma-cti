### Changed

- `just review-loop author --sha` and `just review record --reviewed-sha` now ask Git's
  object database whether the supplied SHA names a commit, then refuse separately when that
  SHA names no commit or the commit is not reachable from the current `HEAD`. Existing
  authorship and verdict records are not changed.
