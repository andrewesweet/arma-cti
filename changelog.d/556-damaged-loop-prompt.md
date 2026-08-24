### Fixed

- One `loop.json` that will not read no longer collapses the turn-top terminus
  prompts to a single `unreadable` line: the prompts for loops that were read
  still appear, and the damaged loop is named in its own
  `review_terminus=unreadable path=<issue>/loop.json` line.
