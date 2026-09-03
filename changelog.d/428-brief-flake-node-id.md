# Fixed

- `just brief` now takes an open flake's test from a `tests/…::test_…` node ID in the issue body when one is present, preferring it over a `test_` prefix match in the issue title. #428's title names the module `test_stall_watch`, so briefs rendered `tests/unit/test_stall_watch.py::test_stall_watch` — a node ID that does not exist — and an agent meeting the real red had no test to quote under the flake-retry rule. When a body names several node IDs, the first in document order is used.
