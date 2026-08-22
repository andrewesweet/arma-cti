## Added

- Added contract-bound case checks to the paired guidance evaluator. Routine and adversarial
  fixture cells score file, command, gate, and refusal observations; the retrieval answer is
  explicitly self-reported soft evidence.
- Changed replay handling to report equal and differing inputs, differing observations, and
  unexplained differences instead of rejecting the first mismatch.
- Added a fresh per-case subprocess `cti.*` and OpenTelemetry identity, with parent identities
  removed, and made live output creation refuse an existing path.
- Kept the six-cell control pair at baseline
  `f6f9963c87df59a333c8d3db93f9fa7d09fb860b`; provenance remains derived from #503 manifests,
  with Codex `expected_chain_only` and Claude `unattributable`.
- Deferred the existing `FBT003` suppression and duplicated run construction as filing-grade
  follow-up work.
