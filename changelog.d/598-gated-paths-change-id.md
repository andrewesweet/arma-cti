### Changed

- `just gated-paths approve` accepts base-independent `--change-id` alongside `--content-id`, so unrelated commits can land between deriving an approval identifier and human approval without weakening the exact-change checks.
