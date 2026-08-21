The `/orchestrator-tick` command described an orchestrator that no longer existed. Its rules are corrected, and the promise it could not keep is withdrawn rather than restated.

The file was tracked for the first time by #468, having driven the orchestration loop from one untracked working copy since 2026-08-19. Reading it against the tooling it names found ten divergences; verifying those found an eleventh; three review rounds found a twelfth and a thirteenth, and each round found errors introduced by the round before it.

The changes that alter what an orchestrator does:

- The in-flight limit and its ruling are read from `just queue state` rather than named here. The file had said two; the live limit is five in any lane.
- Occupancy is by issue, not by tree: a landed-but-open issue still holds a slot, and closing it releases the slot while leaving the tree owed for retirement.
- The harvest acts belong to the seats that own them. Exchange belongs to a dispatch that produced a branch, and a verdict is derived only from a completed review dispatch, so a planner, recon or fable completion owes its report and nothing else. A retro completion does land, and its journal branch takes the same path as an implementation branch.
- Codex may take the implementer seat. The orchestrator seat remains the only one restricted to a single lane.
- The cross-lane rung is a preference rather than a bar, on that rung alone; every other landing refusal is unchanged, including the absolute one on a reviewer sharing the author's profile.
- A verdict survives a tool-recorded clean rebase, so a parallel landing does not orphan another branch's verdict.
- Honouring an issue's routing block by hand is named as this file's convention. #463 records those blocks as advisory and leaves their treatment open.

The file previously claimed that every binding rule cited where it was taken. Three review rounds each found that false in different places — uncited rules, citations to sources that did not contain the rule, and citations to a ruling's worked examples rather than to the ruling. The claim is withdrawn: a citation is now described as a lead to check rather than as proof, #217 is named as the source of most orchestration rulings, and #474 carries the work of making the distinction reliable.
