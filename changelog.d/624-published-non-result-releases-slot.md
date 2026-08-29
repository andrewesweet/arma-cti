### Fixed

- A typed non-result now releases its Work Item scheduling slot once the
  dispatcher's `result.json` has been read, so a run that ended in
  `quota_exhausted`, `provider_refused` or `infra_unavailable` no longer holds
  its Work Item ineligible forever; the re-dispatch the failure-class table
  requires is schedulable again. The delivery collector records the published
  result as a Work Run fact (`result_published`), and the controller releases
  the slot on that recorded fact rather than inferring it from state and
  recovery kind (#624).
