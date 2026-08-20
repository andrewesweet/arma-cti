### Fixed

- `just check` now refuses any `.claude/settings.json` `Bash(just ...)` grant whose recipe
  does not exist or whose recipe cannot be read. Recipe aliases resolve through just's own
  parser, dump failures are typed, and recipes granted nowhere remain valid because they may
  be orchestrator-only (#448).
