### Fixed

- The `surface_conflict` refusal now names the lowest-numbered conflicting issue as the holder from either side, and never refuses the holder itself, so two trees writing the same paths can no longer name each other and block every dispatch route.
