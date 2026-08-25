### Fixed

- Observatory regeneration now emits `added=unknown moved=unknown removed=unknown` when
  the existing landed-issues projection is unreadable, rather than comparing against
  empty text and publishing definite row counts (#580).
