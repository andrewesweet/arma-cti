### Fixed

- `just check` now refuses any `.claude/settings.json` `Bash(just ...)` grant whose recipe
  does not exist. Recipe aliases resolve through just's own parser, while recipes granted
  nowhere remain valid because they may be orchestrator-only (#448).
