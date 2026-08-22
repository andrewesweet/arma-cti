### Added

- New dispatch records carry one typed `guidance_manifest` variant. Codex records `verified`
  from its instruction-delivery proof; Claude Code records `unattributable` because it has no
  bounded non-interactive loader capture. Historical records without either form remain
  `unknown`; an explicit unknown or a serialized value that constructs no variant is
  `unclassified`.
- `just ledger-sync` materializes guidance without copying its free text. Ordered sources carry
  path hashes and UTF-8 byte counts beside their content hashes and byte counts; the Codex
  version becomes a hash and byte count; launch context records only exact equality between
  persisted path strings as `recorded_worktree_match`.
- `GuidanceProof` has no public constructor. Its private factory validates supplied field types
  and shapes; captured `SourceRecord` values must also match their normalized content hash and
  newline-normalization byte bounds. Persisted source metadata remains shape-checked because the
  record intentionally stores no source body. Verified manifests separately require matching
  expected and delivered project/global byte counts and hashes.
- `just ledger-sync` contains every exception raised while reading and parsing one persisted
  dispatch record. Its guidance becomes `unclassified`, its one summary line carries
  `record_parse=failed`, and sync continues with other records. Failures after parsing remain
  errors.
