### Fixed

- The observatory projection now takes an issue's landing from its landings journal
  where the journal records a produced commit, keeping the git referencing-commit
  derivation as the fallback for issues no journal covers. A follow-up commit that
  credits an issue only in descriptive prose (`#N's …`) is no longer admitted as that
  issue's landing, so a settled issue's row and `lead_time_seconds` no longer move
  with every later mention; a journal that cannot answer — damaged, commit-less, or
  naming a commit the checkout lacks — reports its reason instead of falling back to
  the derivation. (#563)
