### Fixed
- The mutation gate's pre-flight refusal now reports pytest's stderr alongside the stdout tail and caps the durations table's rows in that tail, so a red pre-flight carries the failing assertion that classifies the red instead of only per-test duration rows (#680).
