## Fixed

- The in-world regression pool stops after two consecutive `node_crashed`
  verdicts, saying "abandoned after 2 consecutive node_crashed, N probe(s) not
  run" in the summary the way it already says it for `infra_unavailable`, and
  the world's daemon calls go quiet about a dead daemon after five consecutive
  transport errors — one `CTI|daemon_gone_latched` line instead of an identical
  transport error at every loop's poll cadence for the rest of a probe window.
