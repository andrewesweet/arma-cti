### Added

- **`just dispatch` refuses a half-failed brief by name (#349).** Composing a brief and
  dispatching it are two operations, and the first can half-fail silently (#316's four
  instances: a splice died, the placeholder or a stale lane note went out anyway). Before
  anything is written or launched, the dispatcher checks the brief it is about to send:
  `brief_placeholder` when a line still opens one of the composer's unfilled fields (the
  `> **TO BE WRITTEN BY THE ORCHESTRATOR.**` blockquote prefix the composer renders; a
  mention of the placeholder text in prose does not refuse), `brief_route_marker_missing`
  when the brief carries no composer route marker at all — a brief this composer did not
  write, or one whose composition half-failed and lost the marker the composer emits last —
  and `brief_lane_mismatch` when that marker names a seat, lane or profile other than what
  the dispatch resolved (an `unresolved` field cannot mismatch). Prose is never a route
  claim, so a carried handoff or gate report quoting a prior brief's route does not
  refuse. The marker emitter and the placeholder prefix are owned by `tools/dispatch.py`
  and imported by `tools/brief.py`, so composer and gate cannot drift. Nothing is launched
  on any refusal.
