### Added

- **`just review-queue` prints the ADR review queue (#351).** The count and the file list of
  `docs/adr/` records carrying `Reviewed-by-human: pending`, from the line-anchored match only,
  so a prose mention of the marker inside an approved ADR is never counted — the hand-typed
  unanchored grep had over-reported the queue 6-for-1 twice, once inside the retro skill's
  step 3 and once from the orchestration seat outside it (#209: where a rule-table already
  decides, an agent is not handed the job of remembering). A report, not a gate: exit 0
  whatever the depth.
