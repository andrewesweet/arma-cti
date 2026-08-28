#### Added

- An implementer briefing now renders the self-review protocol (ADR-0079 ruling 1, #588):
  a bounded in-session pass over the diff before handover, scoped to the `implementer` seat
  by name, imported from its one home in `tools/review_loop.py` rather than restated by the
  composer.

- `just review-loop` gains `self-round`, `self-converge`, `self-gate-fix` and `self-fail`,
  writing a per-issue self-review record beside the never-alone loop's state under
  `~/.arma-cti/review/`, atomically and outside every worktree. The block carries, per
  round, findings with category, reason and origin, and refutations with their evidence;
  the record names the commit it covers, admits gate-only commits with a reason, types a
  five-round failure, and answers cleanness per round by derivation. Every finding carries
  a stable id. Refusals are typed and exit non-zero.
