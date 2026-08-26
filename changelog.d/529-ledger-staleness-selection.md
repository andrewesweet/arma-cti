### Added

- `just ledger-sync sync --behind` materialises only dispatch records whose ledger row is missing or behind the current schema, leaves current rows untouched, and reports the missing/stale/current split plus how many records remain behind. It reduces the backlog idempotently; existing stale rows without a durable export are preserved and remain counted behind.
- A ledger row written over a prior row records its actual schema, `<schema_missing>`, or `<unreadable>` in `previous_schema`; new rows use null, and same-schema recomputes carry the current marker forward, so replacing an old reading is visible without breaking byte-stability.

### Fixed

- `just ledger-sync prune` now treats a raw export as taken only when a current row positively proves its dispatch identity, exact durable source path, source shape, and positive record count; missing, damaged, malformed or mismatched evidence refuses before deletion, and an export behind a stale row is retained with the remedy named.
