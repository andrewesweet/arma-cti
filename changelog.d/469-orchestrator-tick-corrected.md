The `/orchestrator-tick` command described an orchestrator that no longer existed in eleven places, and now cites where each rule was taken.

The file was tracked for the first time by #468, having driven the orchestration loop from one untracked working copy since 2026-08-19. Reading it against the tooling it names found ten divergences; verifying those against the code found an eleventh.

The corrections that change what an orchestrator does:

- The in-flight limit is five, any lane, and the file now reads it from `just queue state` rather than restating a number. It had said two.
- Codex may take the implementer seat. `IMPLEMENTER_PREFERENCE` heads with `codex-luna-max`.
- The cross-lane rung is a preference, not a bar, since #426. Read as a bar it parks landable branches.
- A verdict survives a tool-recorded clean rebase, since #417, so a second landing does not automatically orphan another branch's verdict.
- The in-flight count reads worktrees and dispatch records, not worktrees alone.

Each rule now carries the issue, ADR or source path it was taken from, so a reader can tell a recorded ruling from an invented one. Sentences with no citation are marked as description rather than ruling.
