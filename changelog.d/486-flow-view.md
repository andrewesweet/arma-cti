## Added

- **The observatory's flow view: lead time as percentiles, throughput as an exact
  count, and every open item's age against the historical band (#486).** One
  `work_items` row per issue joins the store's tables, carrying the issue's state and
  the two named points of its clock: `clock_start`, the issue's earliest dispatch
  start, and `clock_end`, the committer date of its landing commit. Lead time renders
  through one view, `flow_lead_time`, whose columns are nearest-rank percentiles
  (`p50_seconds` to `p95_seconds`) and the sample size and nothing else — the method
  is stated in the schema reference, and a test pins the values on a sample where
  nearest-rank and linear interpolation disagree at every percentile, so a change of
  method is a red rather than a silent drift; no mean can be emitted in that slot,
  because the view's column list is pinned exactly. A work item's state is derived
  from its dispatches' own `gate_outcome`: `landed`, `open` while a dispatch still
  runs, `abandoned` where a dispatch ended `not_a_result` — excluded from the
  lead-time distribution and counted separately in the coverage block — and `stopped`,
  the terminal residue without a failure class, the boundary #489's recorded terminal
  state will widen. The dispatches table gains the columns the derivation reads
  (`started_at`, `end_state_class`, `gate_outcome`, each null with its reason), the
  store's schema is now `cti.observatory/2` — and the schema is read, not just
  written: a store of any other version refuses by name at open (`schema_mismatch`,
  naming the version found and the version needed) rather than raising on a table
  that version never had. On an empty landed sample the view states `items` as 0
  with null percentiles, and the cookbook's flow entry — lead
  time, throughput per month, and open-item age against the band — runs against the
  shipped store in a test.
