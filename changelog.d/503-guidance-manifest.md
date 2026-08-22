### Added

- New dispatch records carry a `guidance_manifest` constructed as one typed variant. Codex
  records `verified` from its existing #502 delivery proof; Claude Code records
  `unattributable` because it has no bounded non-interactive loader capture. Each variant
  fixes every state-dependent field, including its harness, provenance, loader outcome,
  source shape and, where present, reason.
- Codex CLI releases are parsed into numeric version components, and launch directories are
  resolved before serialization. Historical launch directories must resolve to their
  dispatch worktree; rejected legacy metadata is classified without copying its text into
  `ledger.json`.
- `just ledger-sync` derives the harness from the dispatch lane registry and materializes the
  manifest without writing dispatch evidence. Records with neither manifest nor legacy proof
  are `unknown`; explicit unknown, malformed and contradictory records are `unclassified`.
