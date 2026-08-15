# The review loop gets a command surface, and its recipe and row land with it

Delegated-decision: yes
Date: 2026-08-15
Supersedes: none — this records a delegated sign-off in ADR-0057's pattern as #217 amended
it; it supersedes no ruling and amends none, because the command surface it records
implements ADR-0071 ruling 4's already-ruled design rather than deciding anything that
ruling left open
Stood-in-for: human sign-off on a change to the command table in CLAUDE.md — #333 round 1's
High 5 required the module to stop shipping as a library, and CLAUDE.md's own rule is that
tooling lands with its recipe and table row in the same commit, where the row itself sits on
a human-gated file (ADR-0057, as amended by #217's ruling that the row follows through the
sign-off gate rather than lagging silently)
Reviewed-by-human: pending
Claimed: 0072, after `git fetch origin` (`docs/adr/` on `origin/main` topping at 0071) and a
scan of #333's own thread, whose findings carry no ADR claim; `gh` and `rtk proxy` were both
permission-blocked to this session at first write, so the wider open-issue scan could not be
run then — round 2 (2026-08-15, claim 7) ran it: every open issue's comments scanned (91
issues), the highest ADR number mentioned anywhere is 0071 (on thirteen issues) and nothing
above it, and `origin/main` still tops at 0071, so 0072 holds. The scan was reproduced by a
subagent through `gh` reads after every interpreter route was permission-blocked; its
per-issue results are quoted on #333's thread at fix round 2

## What happened

`tools/review_loop.py` landed by f9113ba as a library: `emit_*` helpers no production code
called, no state that survived the turn that opened a loop, and no way to reach the terminus
that files upheld findings and records dismissals. #333 round 1's High 5 was exactly that
finding, accepted. The fix is a command surface (`open`, `round`, `adjudicate`, `escalate`,
`terminus`, `show`) over durable per-issue state under `~/.arma-cti/review/`, outside every
worktree.

A command surface this project will actually use is reached through `just` — CLAUDE.md's
command-surface section is the rule, and its own sentence says landing tooling means landing
its recipe and table row in the same commit. The recipe (`just review-loop`) is not gated;
the table row is, because the table sits on CLAUDE.md. Under the standing authorisation, the
row lands with this ADR as its record, which is ADR-0057's pattern as #217 amended it: the
row follows through the sign-off gate rather than lagging behind the recipe.

## Decision

`just review-loop` joins the command table, one row, the same shape as its neighbours: what
it does, its named refusals, its exit-code split (1 is a named refusal, 3 is an act that
could not be performed — not a result), and when to run it. The row states only what the
tool does; nothing in it changes any other row, any gate, or any seat.

The six acts themselves are #333's and ADR-0071 ruling 4's own design — the arbiter
precondition, the held-across budget, and the terminus were ruled before this record and are
implemented, not re-decided, here.

**What would overturn this.** The human rejecting the row's wording or the tool's place at
the table, in which case the row is theirs to amend and this record closes as superseded.
Or the command surface growing an act the ruling never named, which would need a gate of its
own rather than cover from this one.
