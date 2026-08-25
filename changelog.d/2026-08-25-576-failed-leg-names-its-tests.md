### Added

- **A failed python unit leg's gate-clock row now carries the failing tests' node ids
  (#576).** A red leg used to leave only a status integer, and pytest's own `lastfailed`
  cache is erased by the next green run — exactly when someone looks — which is how three
  reds in one night were filed as one class of "unattributable flake" when the one that was
  read in time turned out to be a deterministic failure. The gate-clock runner now mints a
  per-leg file, exports its path in `CTI_GATE_CLOCK_FAILED_FILE`, and the unit suite's
  conftest writes the failed and errored node ids there at summary time; a failed leg copies
  them onto its row, where no later run erases them. A green leg writes nothing, so records
  do not grow for healthy runs. The payload is capped at twenty ids and a longer run's list
  closes with an entry counting the omitted rest, so a truncated list never reads as
  complete. `just mutation` strips the export from its judges, whose kills are failing tests
  by design and would otherwise misattribute onto the mutation leg.
