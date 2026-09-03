### Changed

- **`docs/agents/dispatched-session-commands.md` gains a dated section recording one
  observed git capability of a dispatched session: `git commit --amend` succeeded for a
  dispatched implementer on the `zai` lane (2026-09-03, #691) — at least three observed
  successes, grounded in the dispatch records of the amending runs, all three under the
  `acceptEdits` permission mode.**
  The section also states, demonstrated rather than inferred, what the brief must say to
  obtain the rewrite: "Amend HEAD; do not add a commit." — carried by dispatch
  `d-20260903-135450-be1c90` — with its measured bounds
  (lane `zai`, mode `acceptEdits`, HEAD only, before review).
  The document's lane caveat now scopes the command-surface rows to `claude-native` and
  the git-verb claim to `zai`. The wider command-permission mapping is unmeasured, and
  #695 holds it.
