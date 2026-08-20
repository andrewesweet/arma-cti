### Fixed

- **A red in the bounded-request resolver test no longer reds its neighbour (#443).**
  `test_a_stalled_resolver_expires_at_the_calls_deadline_not_the_sockets` released its stalled
  resolver in a `finally` that followed the `pytest.raises` block rather than wrapping it, so any
  outcome other than `TimeoutError` propagated with the event unset and left a worker blocked for
  the full 30 s backstop under the name `_workers()` keys on — and the abandonment test, which
  reads that same worker table, then failed for a reason that was never its own. Reproduced
  before the fix by asserting the wrong exception type and running the suite: three reds, the
  deliberate one, the neighbour's, and a temporary in-process proof of the leak. With the
  `pytest.raises` inside the `try`, the same deliberate red leaves one red and 5,082 passes, and
  no blocked worker behind it. The module's two suppressions now carry the constraint each one
  rests on — `BaseHTTPRequestHandler` fixing the `format` parameter's name, and `_request`
  building only URLs this file staged, loopback or the never-resolved `.invalid` host, which the
  old `S310` reason described as loopback alone. Two assertions were strengthened to check what
  their docstrings already claimed: the abandonment's `TimeoutError` type is now read before the
  release, where it is the delivered outcome rather than a captured object re-checked after
  nothing could have changed it, and the workers-ended assertion runs over the workers that call
  started rather than over a `_workers()` list that would satisfy it by being empty.
