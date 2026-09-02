### Added

- **`just dispatch` refuses a half-failed brief by name (#349).** Composing a brief and
  dispatching it are two operations, and the first can half-fail silently (#316's four
  instances: a splice died, the placeholder or a stale lane note went out anyway). The
  dispatcher now reads the brief it is about to send and refuses `brief_placeholder` —
  quoting the offending line — when the brief still carries its composer's placeholder
  marker, or `brief_lane_mismatch` when a route claim in the brief (a seat heading, the
  seat opening, or the identity sentence naming lane and profile) contradicts the
  dispatch's own resolved seat, lane and profile. The mismatch scan reads only the
  brief's own statement of its route: the two blocks the composer carries verbatim — the
  handoff body and a review brief's gate report — quote prior briefs, so a carried
  `## Seat:` line is evidence about another dispatch and does not refuse. The marker is
  one authority, shared with `tools/brief.py`, so the composer and the gate cannot
  drift. Nothing is launched on either refusal.
