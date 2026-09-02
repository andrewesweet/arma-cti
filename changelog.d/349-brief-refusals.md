### Added

- **`just dispatch` reads a brief's placeholders and route marker at fixed positions (#349).** Composing
  a brief and dispatching it are two operations, and the first can half-fail silently
  (#316's four instances: a splice died, the placeholder or a stale lane note went out
  anyway). Before anything is written or launched, the dispatcher reads the brief it is
  about to send at two fixed positions: `brief_placeholder` on the composer's
  unfilled-field structure inside the region the composer writes unfilled fields —
  between its task heading and its Single-shot heading — and `brief_route_marker_missing`
  when the brief's final line is not the composer's route marker
  (`<!-- cti-brief-route ... -->`). The marker names the seat, and the lane and profile
  when the composing `just brief` was given `--lane`/`--profile`; the gate compares the
  marker's three values against the route this dispatch resolved, refusing
  `brief_lane_mismatch` on any difference, and a field spelled `unresolved` is no claim.
  The marker emitter, the placeholder prefix and the two bounding headings are owned by
  `tools/dispatch.py` and imported by `tools/brief.py`, so composer and gate cannot drift.
  Nothing is launched on any refusal.
