### Changed

- **`/orchestrator-tick` is reduced to steps, commands and pointers (#643).** Every
  explanation, rationale, worked example and assertion about what the code does is
  deleted; a rule owned by `docs/agents/orchestration.md`, `docs/review-dispatch.md`,
  `docs/agents/review-severity.md` or `AGENTS.md` is now a pointer to it. The steps and
  commands are kept, with their flags checked against the justfile and the tools they
  invoke. Three step-level corrections come with the reduction: the review dispatch is
  ordered after the exchange and passes no `--brief-file`, since the review seat runs in
  a dispatch-owned disposable worktree while `just brief` composes an `issue-N` tree; a
  turn top printing `action=refill-before-landing` now refills before it lands; and the
  file no longer names a live issue as an example of a gate-clock drift line.
