## Added

- Added a contract-first paired guidance evaluator with direct retrieval, routine implementation,
  and adversarial conflict cases, explicit capture states, quality-first scoring, and separate
  prompt-corpus storage.
- Added a committed six-cell control pair at baseline `f6f9963c87df59a333c8d3db93f9fa7d09fb860b`
  and `just guidance-eval` replay coverage. Guidance provenance is derived from #503 manifests;
  Codex remains `expected_chain_only` and Claude remains `unattributable`.
