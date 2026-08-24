### Fixed

- `just check` now mechanically guards the ADR-0013 command-table route: an
  authorised `AGENTS.md` diff must stay inside command-table rows, and every
  recipe named by a changed row must resolve in the candidate `justfile`.
  Typed confinement and resolution refusals keep the standing rule out of force
  until this leg is present; row-description truth remains semantic and
  unverified by the path scan (#544).
