### Changed

- **A gate landing's downgrade record now names every free lane it considered, and the bar on
  each one it rejected (#427).** `gate_review=same_lane_chosen` printed only the lanes that were
  reachable, so a partially barred landing — one free lane open, another inside its off-peak
  window — could not say whether the missing lane had been asked and rejected or never asked at
  all. Both records now carry `barred_lanes=`, `none` where every free lane was reachable, and
  the record is the safety property the whole downgrade rests on.

### Fixed

- **The breaker read inside `just land`'s never-alone rung can reach the network, and now says
  so and can be suppressed (#427).** Reading a free lane's dispatchability goes through
  `dispatch.lane_bar`, which asks z.ai's own quota endpoint for a lane held open on availability
  with no published boundary — the lane's own self-healing path, disclosed in #426 as a state-file
  write alone. The call is bounded where it fires (one request, no retry, a 10 s deadline over the
  whole call, every failure a typed unavailable reading), the live reader stays the default so a
  landing's record is what a dispatch would have met, and `LaneReach.quota_reader` is the seam
  every test now hands a refusing reader through — so no `just fast` run reaches a provider to
  decide a landing record.
- **That bound now covers name resolution, which a socket timeout never did (#427).**
  `urlopen`'s `timeout` starts once the hostname has resolved, so a stalled `getaddrinfo` escaped
  it entirely and could hold `just land` for as long as the resolver hung. Every HTTP read the
  breaker and the OTel exporter make now goes through `tools/bounded_request.py`, whose deadline
  is the whole call's: a stall in resolution, connect or body expires alike, the read is abandoned
  on a daemon thread rather than waited for, and the expiry lands in each caller's existing
  unavailable direction rather than reading as a lane that answered.
- **`lane_bar`'s rung order is pinned by a test (#427).** A lane can be barred by its breaker, the
  human's off-peak window and a missing credential at once, and the first one wins; nothing
  asserted that order, so a reordering would silently change which bar a dispatch refuses with and
  which one a landing record carries.
