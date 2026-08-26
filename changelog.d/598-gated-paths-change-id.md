### Changed

- `just gated-paths approve` accepts a base-independent, byte-exact `--change-id` alongside `--content-id`, so unrelated commits can land between deriving an approval identifier and human approval while preserving exact approval matching and the existing carry checks.
