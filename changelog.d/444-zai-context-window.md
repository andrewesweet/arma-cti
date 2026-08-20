### Fixed

- **The `zai` lane declares its real context window, so a GLM session no longer compacts at a
  fifth of what the provider holds (#444).** Claude Code does not recognise `glm-5.3`, assumes
  200,000 tokens and auto-compacts against that assumption; measured across the transcript
  archive, that compacted 34 of 129 GLM sessions against 12 of 1,286 everywhere else, with 45
  sessions peaking in the 150k–200k band — pressed flat against a ceiling that is not the
  provider's. Measured live against the endpoint on 2026-08-20, `glm-5.3` accepted 1,049,169
  input tokens and refused 1,052,969, so the lane now declares 1,000,000 through
  `CLAUDE_CODE_MAX_CONTEXT_TOKENS` and the warning goes quiet in a control-and-treatment run.
  A round million rather than the measured figure: it sits below the accepted floor with margin
  for a serving tokeniser that counts a request slightly differently from `/count_tokens`.

### Added

- **`Lane.context_window`, the one place a lane's window is written (#444).** Zero means the
  runner already knows its own models, which is `claude-native`'s answer and why that lane
  declares nothing rather than restating a figure Claude Code would win any disagreement with.
  The variable joins `LANE_OWNED` for a base URL's reason — it decides when a child compacts, so
  inheriting it would make that a property of the shell that dispatched.
- **The ceiling the fix does not cover, named in the registry beside the number (#444).** The
  variable is session-wide rather than per-model, measured by watching the same treatment silence
  the `glm-4.7` warning too, and the haiku slot's own window is smaller — 200,729 accepted,
  256,467 refused. A haiku-slot subagent is therefore told it has a million tokens, and z.ai's
  refusal arrives as an HTTP 200 carrying `model_context_window_exceeded` with an empty content
  block rather than as an error. Exposure measured at 3 transcripts peaking at 74,567 tokens, so
  this lands as a named ceiling rather than a mechanism; pointing the haiku slot at `glm-5.3`
  is the fix if that headroom is ever spent.
