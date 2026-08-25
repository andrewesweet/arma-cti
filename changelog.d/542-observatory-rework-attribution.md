### Fixed

- The observatory rework denominator credits only dispatches with a successful
  end state alongside the issue's produced landing. Not-a-result and
  attribution-unknown dispatches are excluded with `landings_reason`, while
  the per-lane cost row documents `landed` as an issue outcome rather than lane
  production attribution. (#542)
