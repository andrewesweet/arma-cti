### Fixed

- The committed observatory projection now selects an issue's `landed_sha` by the
  landing commits' Git committer dates, with an explicit full-SHA tie-break for equal
  instants, instead of selecting the lexicographically greatest SHA. (#561)
