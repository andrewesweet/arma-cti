#### Fixed

- The two review loops' state is no longer observably conflated: the stored loop carries
  `independent_opened`, so `sync` records a first verdict as round zero even where a
  self-review-only `loop.json` already exists, a clean first verdict is an observed round
  zero rather than no record at all, and `open` refuses a second open of an independent
  round zero opened clean. Stored self-review blocks asserting a state no writer produces
  — a sixth round, a premature or mistyped failure, convergence without a clean last
  round, gate fixes without convergence, non-list collections — are refused typed and
  non-zero, and a duplicate id across a round's findings and refutations is refused at
  the write that caused it.

#### Added

- An implementer briefing now renders the self-review protocol (ADR-0079 ruling 1, #588):
  a bounded in-session pass over the diff before handover, scoped to the `implementer` seat
  by name, imported from its one home in `tools/review_loop.py` rather than restated by the
  composer.

- `just review-loop` gains `self-round`, `self-converge`, `self-gate-fix` and `self-fail`,
  writing a per-issue self-review record beside the never-alone loop's state under
  `~/.arma-cti/review/`, atomically and outside every worktree. The block carries, per
  round, findings with category, reason and origin, and refutations with their evidence;
  the record names whatever commit the caller passes as the commit it covers, admits
  gate-only commits with a reason, types a five-round failure, and answers cleanness per
  round by derivation. Every finding carries an id unique across the record — a matching
  key for the dismissal-miss reader (#602), never a content-derived identity. Refusals are
  typed and exit non-zero, including a stored block asserting a state no writer produces.
