### Added

- New dispatch records carry one typed `guidance_manifest` variant. Codex records `verified`
  from its instruction-delivery proof; Claude Code records `unattributable` because it has no
  bounded non-interactive loader capture. Historical records without either form remain
  `unknown`; explicit unknown, malformed and contradictory records are `unclassified`.
- `just ledger-sync` materializes guidance without copying its free text. Ordered sources carry
  path hashes and UTF-8 byte counts beside their content hashes and byte counts; the Codex
  version becomes a hash and byte count; launch context becomes the closed
  `dispatch_worktree` category.
- `GuidanceProof` has no public constructor. Persisted overlong numeric versions and alternate
  launch-directory spellings become `unclassified` instead of raising or resolving two
  untrusted paths.
