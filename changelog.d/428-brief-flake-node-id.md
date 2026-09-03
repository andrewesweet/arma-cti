# Fixed

- `just brief` now takes an open flake's test from a `tests/…::…` node ID in the issue body
  when one is present, preferring it over a `test_` prefix match in the issue title, and
  reads that ID whole for the shapes this tree collects: class-scoped IDs
  (`…py::TestClass::test_method[…]`) keep their class segment and bracketed parameter ids
  keep their spaces, the shape
  `tests/unit/test_commands.py::test_a_payload_that_is_not_a_command_is_refused[a bare
  string is not a Command]` really collects — previously both truncated to an identifier no
  test answers to. The bound is stated, not silent: a bracket group is free of `]` and of
  newlines, so a parameter id that itself carries `]` is not read whole — the match stops at
  its first `]` and yields a prefix no test answers to — because pytest's explicit ids are
  free text with no grammar deciding where such an id ends, and matching greedily to the
  last `]` would instead swallow trailing prose and merge two bracketed IDs quoted on one
  line. The node-ID pattern reads the body alone; a title that happens to carry a
  full node ID no longer overrides a body that names none. #428's title names the module
  `test_stall_watch`, so briefs rendered `tests/unit/test_stall_watch.py::test_stall_watch`
  — a node ID that does not exist — and an agent meeting the real red had no test to quote
  under the flake-retry rule. When a body names several node IDs, the first in document
  order is used.
