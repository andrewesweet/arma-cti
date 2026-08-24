### Fixed

- `check-observatory` now reports an explicit `observatory_summary=skipped state=unrecorded` and lets later `just check` legs run when a dispatched implementer cannot read the external observatory sources. Non-dispatched source refusals and committed-summary byte mismatches remain red. (#557)
