## Added

- `just observatory` now generates a compact committed landed-issue summary with short per-cell cost-state codes, and `just check` verifies it against a fresh rebuild with per-lane costs kept in their own meters. Dispatches on issues not yet landed stay outside the projection; later dispatches naming a landed issue update its row on regeneration.
