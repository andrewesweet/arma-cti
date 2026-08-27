### Added

- A one-shot `just controller reconcile` command now reports normalized Control Facts, the
  conservative lifecycle state, and ordered Control Actions; `--dry-run` performs no mutation,
  while non-dry cycles persist planned, applied, and confirmed transitions in a rebuildable
  journal protected by a singleton scheduling lock. (#378)
