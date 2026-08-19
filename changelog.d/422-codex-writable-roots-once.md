### Fixed

- **Codex dispatch plans now resolve their writable cache roots once and reuse that result for both refusal and argv construction (#422).** A later resolution can no longer silently remove the cache grant after the planner accepted it; the single resolution either produces the exact tuple placed on the child argv or refuses the dispatch.
