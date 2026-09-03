### Fixed

- **A `named_author` review refusal no longer quotes dispatch ids where it promises profile
  names (#414).** The action told a caller the profile they named "is a profile this issue's
  own dispatch records carry", then printed the record identifiers those profiles were read
  from — so the sentence named ids, not profiles, in exactly the slot that said profiles. It
  now prints the profiles (`authorship.potential`); the ids stay on the found lines, where a
  reader follows them. Found while probing the issue's typed-refusal finding, which did not
  reproduce as described: every typed refusal a retired profile name produces matches the
  type its surface promises, so that half is declined in the issue's close, with the
  retirement walk's transitivity and its cycle stop pinned by test and the walk renamed to
  `profile_lineage` so its name stops claiming the whole chain is retired.
