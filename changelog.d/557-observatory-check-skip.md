### Fixed

- `check-observatory` now repairs a clean stale projection from its in-memory rebuild in a dispatched implementer worktree, so later `just check` legs run without requiring the external observatory cache to be writable. Uncommitted hand edits remain red; committed hand edits are indistinguishable from staleness and may be overwritten by implementer repair. Source refusals and other seats remain red. (#557)
