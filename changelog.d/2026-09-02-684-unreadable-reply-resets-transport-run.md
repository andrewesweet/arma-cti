# Fixed

- A reply that arrived but could not be parsed now ends `cti_fnc_daemonCall`'s
  run of consecutive transport errors, so an outage following a truncated reply
  is announced in the `CTI|` log instead of being silent behind a latch no
  recovery had cleared (#684).
