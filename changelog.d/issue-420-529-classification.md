Fixed: A `529` (provider overload) from a lane endpoint now classifies as
`provider_error` instead of `unclassified`, so a transient provider outage
feeds the breaker's existing three-consecutive hold rather than counting
against the lane's work. The `503` mapping is unchanged.
