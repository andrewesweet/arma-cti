### Added

- `just ledger-sync sync --behind` materialises only dispatch records whose ledger row is missing or behind the current schema, leaves current rows untouched, and reports the missing/stale/current split plus how many records remain behind, so the whole ledger can be brought level in one idempotent command.
- A ledger row written over a row at a different schema records that schema in `previous_schema`, so replacing an old reading is visible in the row itself.

### Fixed

- `just ledger-sync prune` now treats a raw export as taken only when a row at the current schema was materialised from it; an export behind a stale row is retained and the reason names the remedy, instead of the last copy of its telemetry being deletable while the row still needed correcting.
