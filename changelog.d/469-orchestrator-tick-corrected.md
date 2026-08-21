The `/orchestrator-tick` command described an orchestrator that no longer existed, and now marks which of its rules are recorded rulings and which are the file's own convention.

The file was tracked for the first time by #468, having driven the orchestration loop from one untracked working copy since 2026-08-19. Reading it against the tooling it names found ten divergences; verifying those against the code found an eleventh; reviewing the correction found a twelfth and six new errors introduced by the correction itself.

The changes that alter what an orchestrator does:

- The in-flight limit is five in any lane. The file now reads the limit and its ruling from `just queue state` instead of carrying its own copy, which had said two.
- Occupancy is by issue, not by tree: a landed-but-open issue still holds a slot, and closing it releases the slot while leaving the tree owed for retirement.
- Codex may take the implementer seat; `IMPLEMENTER_PREFERENCE` heads with `codex-luna-max`. The orchestrator seat remains the only one restricted to a single lane.
- The cross-lane rung is a preference rather than a bar, on that rung alone; every other landing refusal is unchanged, including the absolute one on a reviewer sharing the author's profile.
- A verdict survives a tool-recorded clean rebase, so a parallel landing does not orphan another branch's verdict.

Rules that bind now cite an issue, an ADR or the implementing path. Sentences with no citation say that they are the file's convention rather than a recorded ruling.
