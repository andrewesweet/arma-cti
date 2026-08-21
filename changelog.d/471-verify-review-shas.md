### Changed

- `just review-loop author --sha` and `just review record --reviewed-sha` now ask Git's
  object database whether the supplied SHA names a commit, refusing `commit_not_found` when it
  does not. `author --repo` selects the repository, both commands use the existing `invalid_sha`
  wording, and `review record` validates that form before fetching. `commit_unreachable` has been
  removed: a valid commit need not be contained by a ref. Existing authorship and verdict records
  are not changed.
