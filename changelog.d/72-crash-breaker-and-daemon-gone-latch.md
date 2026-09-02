## Fixed

- The in-world regression pool stops taking new work after two consecutive
  `node_crashed` verdicts and records the final count of probes not run after
  in-flight probes finish.
- The effect pump backs off daemon polls to a 10-second half-open cadence at
  its default interval after five consecutive transport failures;
  `cti_fnc_daemonCall` emits one `CTI|daemon_gone_latched` line and suppresses
  repeated transport lines until a daemon reply.
