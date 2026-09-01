### Fixed

- Eval-corpus reports now use a deterministic `CaseState` declaration-order tie-break
  when `unclassified` and `quarantined` share a severity, and task files that use
  `unclassified` as `expected_class` are refused as invalid.
