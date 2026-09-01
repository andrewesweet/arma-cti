### Fixed

- Standalone `delivery.json` observations cannot release a scheduling slot through
  `recovery_kind` or reach the completion branch through `landed_sha`. Which delivery
  fields carry scheduling authority remains open and is held by #671. (#661)
