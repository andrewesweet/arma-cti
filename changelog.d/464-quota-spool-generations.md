### Fixed

- **The quota spool keeps generations instead of destroying its own history on every
  roll (#464).** `tools/quota_tap.sh` rolled over exactly once, so each roll overwrote
  the single backup and everything older than the previous generation was gone. The
  spool is the only per-session record of cost, tokens, duration and lines changed for
  sessions no dispatch covers — the orchestrator's turns and the human's interactive
  ones — because the ledger's attribution is `dispatch_only` and the orchestration seat
  has no row anywhere. A roll now shifts each generation down by one before the live
  spool becomes `.1`, and the oldest is dropped, so the file is a bounded history rather
  than a two-generation window. `CTI_QUOTA_KEEP` sets how many rolled generations are
  kept and defaults to 8, which is about 72 MB beside the unchanged 8 MB cap. The cap,
  the fail-open guards and the downstream hand-off are untouched.

- **Four tests drive the real script rather than reimplementing its arithmetic**, since a
  test that recomputed the generation shuffle would agree with itself whatever the shell
  did. They pin both directions: that content moves down the generations in order and the
  live spool holds only the newest payload, and that a spool under its cap does not roll
  and the oldest generation is dropped rather than accumulating. A fourth holds the tap to
  its actual job, passing the payload downstream unchanged.
