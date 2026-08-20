### Changed

- **The `gh` seam's own tests moved to a module that has no stand-in for it, so a seam test that
  reads a stand-in instead of the seam is now unrepresentable rather than policed (#440).**
  `tests/unit/test_land.py` replaces `close_issue` on every test it has, autouse, because a suite
  that reached the real `gh` would post to the tracker from whatever credentials the runner holds
  — and a test *of* `close_issue` written in that module read the same patched attribute, so it
  asserted against the stand-in and would pass whatever the function did. #439 shipped seven such
  tests and they were loud, because the stand-in returns `None` where five assertions wanted a
  string; loudness was the coincidence, not the protection, and no gate would have caught the
  variant whose expectations happened to match the stand-in's defaults. `tools/mutation_smoke.py`
  plants only in the lines a module's tests execute, so a vacuous seam test plants nothing and reds
  nothing. The seven tests now live in `tests/unit/test_land_close.py`, which has no `closer`
  fixture and no stand-in for the seam, so they call `land.close_issue` directly and reach the real
  function; `_CLOSE_ISSUE`, the import-time binding that worked around the fixture, is gone. They
  stay off the network by standing in one seam further down, at `subprocess.run`. The rejected
  alternative was a meta-test inspecting other tests' patch targets, which asserts on how tests are
  written rather than on what the code does and breaks on every refactor. `tests/unit/test_land.py`
  keeps its autouse fixture and both directions of its assertions — the landing path calls the seam
  on success and never on a shape that lands nothing. No behaviour change in `tools/land.py`.
