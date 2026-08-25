### Fixed

- **A failed leg's recorded test ids now keep "named none" apart from "could not tell"
  (#576 round 2).** The first landing collapsed them: an empty, missing or unreadable id
  file all became no `failed_tests` key, so a failure whose evidence channel broke read
  identically to one that completed and genuinely named no failing test — the exact
  indistinguishability #576 exists to close, reintroduced inside its fix. A failed leg now
  records an empty list when its id file was read cleanly and named nothing, and no key at
  all only when the file was missing or unreadable, so the absent key means "no claim" and
  never "an answer of zero". The codec also enforces the field's failed-only invariant in
  both directions: `failed_tests` is dropped at serialise and ignored at read on any leg
  that did not fail, so a future writer cannot attach failing-test ids to a passing or
  skipped leg.
