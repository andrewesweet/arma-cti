### Fixed

- The landed-SHA derivation's possessive narrowing now carries its own number-boundary
  guards, so a commit admitted to an issue's referencing set through a possessive credit
  (`#N's …`) can no longer become that issue's landing through the `#N` inside a longer
  number in the same message (`lands #555` answering for #55). A partially damaged
  landings journal answering from its readable rows is pinned as the decided behaviour,
  and the observatory regeneration now reports how many projection rows it added, moved
  and removed, so a commit message quotes the rebuild's count rather than its author's
  reading of the diff. (#571)
