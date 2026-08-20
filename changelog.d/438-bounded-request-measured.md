### Added

- **`tools/bounded_request.py`, unmeasured since it landed in #427, is measured by a test module
  (#438).** The module's whole job is that a read on `just land`'s serial path cannot hang, and
  nothing in `tests/` named it — a gap found by #370's selection rung on its first live firing
  and invisible to that rung ever after, because it asks only about introductions. Six tests,
  none reaching the internet: the resolver stall — the one place a socket timeout cannot reach,
  because no socket exists yet — is staged at the seam the module's own docstring names,
  `socket.getaddrinfo` replaced by a blocker (the same construction the landing rung's own test
  uses), and expires at the call's deadline with the worker provably still inside resolution; a
  429's `HTTPError` arrives with its code, its `retry-after` header and its body intact, and a
  refused connection still arrives as the `URLError` it always was; and a read that outlives its
  deadline is abandoned on a daemon thread whose late success lands in lists only that call held
  — pinned by a fresh read through the same module getting its own, byte-distinct answer. The
  module itself is unchanged: its first mutation figure is 3 mutants planted, 3 killed, none
  surviving.
