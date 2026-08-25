#### Fixed

- A red leg in `just check` no longer hides the legs behind it (#566): every
  leg of a recorded recipe runs whatever the legs before it did, so one
  unrelated red — an `observatory_summary=stale` projection, say — costs the
  reader neither `ruff`, `ty`, `clippy`, `rustfmt`, `gitleaks` nor the HEMTT
  lints. The recipe still fails on any red leg, exiting the first red leg's
  own status. The one skip the runner knows is declared, not positional:
  `just fast` declares `mutation` to depend on `unit`, and a skipped leg
  records `not_run` with the reason beside it on the row and on the run's own
  line. A red run now pays the wall a green one always did, where it used to
  stop at the first red.
