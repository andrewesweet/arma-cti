### Changed

- `just review-loop author --sha` and `just review record --reviewed-sha` now ask Git's
  object database whether the supplied SHA names a commit, then refuse separately when that
  SHA names no commit or no ref contains the commit. `author --repo` selects the repository,
  and both commands use the existing `invalid_sha` wording before any fetch. Existing authorship
  and verdict records are not changed.
