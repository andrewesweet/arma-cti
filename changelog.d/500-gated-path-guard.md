### Fixed

- `just check` now refuses a path-identifiable human sign-off change unless the current diff carries a changed ADR-0013 delegated-decision record or the gate finds a versioned, issue-bound record for that path's exact baseline and resulting bytes. The hook, check leg, and retained trial audit read one path catalogue; the Claude hook remains registered and keeps its immediate generated-file and acceptance-spec refusals. Every check verdict states that it does not judge content or quality, prove human identity, or recognise semantic gates. (#500)
