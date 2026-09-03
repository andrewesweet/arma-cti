### Fixed

- **A `named_author` review refusal now labels each potential profile with its source and keeps
  the source records in its found lines (#414).** The action previously rendered the parallel
  `authorship.records` values into a sentence promising profile names, so a dispatch id stood
  where a profile should have been and an interactive declaration was falsely described as a
  dispatch record. It now pairs each profile with `source=dispatch` or `source=declared` and
  its record; the found lines now carry the parallel profile and record fields for verification.
  Found while probing the issue's typed-refusal finding, which did not reproduce as described:
  every typed refusal a retired profile name produces matches the type its surface promises,
  so that half is declined in the issue's close, with the retirement walk's transitivity and
  its cycle stop pinned by test and the walk renamed to `profile_lineage` so its name stops
  claiming the whole chain is retired.
