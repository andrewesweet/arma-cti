## Added

- Added an evidence-source contract to the paired guidance evaluator. Subprocess file changes,
  process exits, and elapsed time are observable; reported commands, gate outcomes, and refusals
  are soft; unavailable safety fields make a live run incomplete, while unavailable usage stays
  explicit telemetry. The six committed fixture cells are counted separately as self-reported,
  with zero observed or mixed passes.
- Added two-artifact replay comparison for model profile, effort, permissions, harness version,
  guidance reference and dispatch ID, timestamps, prompt and run identity, provider argv hash,
  working directory, timeout, captured child environment, and the corpus, contract, and parsed
  guidance-manifest identities. Each guidance reference is bound to the provider and dispatch ID
  recorded by its runs: all runs using it must agree, its caller-supplied provider must match, and
  its caller-supplied record path must open a record carrying that dispatch ID before the run's
  provider selects the #503 parser. Output labels an observation difference guidance-only among
  recorded inputs only when that bound, parsed manifest identity changes, every changed input is a
  guidance input, and no input is unavailable. Every compared non-guidance difference is named as
  a confounder, every relaxed replay-integrity check is printed with its reason, caller-declared
  manifest hashes never drive attribution, and unrecorded external state remains outside it.
- Replaced inherited subprocess environments with an explicit allowlist. A live run records the
  exact child environment: allowlisted process basics, fresh `CTI_DISPATCH_*` values, and fresh
  `cti.*` OpenTelemetry attributes. Parent values outside the allowlist—including
  `ANTHROPIC_*`, `OPENAI_*`, `CODEX_*`, and `OTEL_SERVICE_*` values—are absent, and the parent's
  `OTEL_RESOURCE_ATTRIBUTES` value is replaced. Live output creation also refuses an existing
  path.
- Kept the six-cell control pair at baseline
  `f6f9963c87df59a333c8d3db93f9fa7d09fb860b`; its runs now record the guidance dispatch IDs used
  to bind their #503 manifest reads, with Codex `expected_chain_only` and Claude `unattributable`.
