# The human interlocutor is a slash command that carries its own seat, and a declared seat is checked

Delegated-decision: yes
Date: 2026-08-09
Stood-in-for: human sign-off on the CLAUDE.md Model-roles mapping and command table —
#255 names the mapping addition as a gate and the session was unattended
Reviewed-by-human: pending
Claimed: `docs/adr/` on `origin/main` (`e47035d`) topping at 0067, and a scan of open
issue bodies and the standing pile's comments finding no claim above it. The scan is
narrower than the rule asks — `gh search` and `gh api` are outside a dispatched
session's command vocabulary (#294), so open-issue *comments* other than #217's were
not swept. The rebase backstop is the fallback the rule already names.

Implements the human's ruling of 2026-08-06 on #242 (ruling 2): the human interface —
rulings intake, status, observations, issue raising — separates from the orchestration
standing loop and runs at **opus/xhigh**. #255 owns everything the ruling did not
settle, and the largest of those is stated in its own words: *the interface is
session-shaped, not dispatch-shaped, and a dispatched agent that ends cannot be talked
to. How that reconciles with the working-style rule that a turn does not block is the
open design question this issue must answer, not assume.*

## Decision 1: the interlocutor is a slash command in the human's own session, and the command carries the seat

The reconciliation is that there is nothing to reconcile, because the interlocutor is
not dispatched at all.

Claude Code's skill frontmatter carries `model` and `effort` (verified against
`code.claude.com/docs/en/slash-commands`, v2.1.224 on this box). So `/interlocutor`
invoked in the human's own session — CLI or Remote Control — sets that turn to
opus/xhigh without spawning anything. The working-style rule is untouched: no turn
blocks, because no turn is waiting on anything. The human types, the seat answers, the
human types again. That is a conversation, and it is the shape the ruling asked for.

The alternative — a `context: fork` skill running the seat as a subagent — was rejected
on the documentation's own terms: a forked skill "won't have access to your
conversation history", which is the one thing an interlocutor cannot do without.

**The mechanism has a limit, and it is stated here rather than discovered.** The docs
say the `model` override "applies for the rest of the current turn and is not saved to
settings; the session model resumes on your next prompt", and `effort` is documented as
applying "when this skill is active". So a single `/interlocutor` buys one turn at
opus/xhigh, not a session. For a conversation of any length the human sets the session
instead — `/model opus` and `/effort xhigh` — and both of those take an argument from
mobile and web, which is the documented form for Remote Control. The skill body says
so in its first lines, because a seat that silently reverts to the session's tier after
one exchange is the exact failure this project has already paid for once.

Whether `effort` in particular survives past the invoking turn is **not** verified. The
docs are explicit about `model` and ambiguous about `effort`, and nothing in a
dispatched session can observe its own effort level to settle it. It is written down as
unverified rather than assumed either way.

## Decision 2: an agent definition lands beside the command, for the dispatched case only

#255 asks for "an agent definition plus a slash command", and both land, but they are
not two routes to the same thing. `.claude/agents/cti-interlocutor.md` is the seat as
the Agent tool can reach it — a subagent dispatched *into* the interlocutor role, which
is what a `context: fork` skill or another session's `Agent` call would use. The
conversation the human actually has runs through the slash command in their own
session, per decision 1.

Two consequences, both mechanism rather than preference:

- **The seat is not dispatchable in the session that creates it.** The harness
  enumerates `.claude/agents/` once, at session start. `cti-interlocutor` becomes
  dispatchable in sessions started *after* it lands on `main` — and, for Remote Control,
  after the `claude-rc-arma-cti` server's next spawned session, since each is a fresh
  worktree of the repository.
- **Reachability from iOS is inherited, not built.** Remote Control is a window into a
  local session: `claude-rc-arma-cti.service` runs `claude remote-control --spawn
  worktree` rooted in this repository, so each mobile session is an ordinary Claude Code
  session in a worktree of it, with this repository's `.claude/` present. A project skill
  landed on `main` is therefore `/interlocutor` from the phone for the same reason it is
  from the terminal. Verified: the unit file and its launcher on this box, and the
  documented local-only command list (`/plugin`, `/resume`) which custom skills are not
  on. Not verified: nobody has typed it from the phone yet, because neither artefact can
  land from here (below).

## Decision 3: a declared seat is checked, because both declaration surfaces fail open

`.claude/agents/` exists because the Agent tool carries no effort parameter and a
subagent silently inherits its dispatcher's model — the mechanism that put every
implementation agent of 2026-08-04 on fable and took the bulk of a weekly budget.
Decision 1 adds a **second** place the same pair is declared.

Both fail open. Malformed frontmatter loads the body with empty metadata and the command
still works; an effort level that does not exist, or a key that has drifted below the
top level, leaves the seat running at the session's tier. Nothing refuses, nothing warns,
and the only trace is a cheaper tier than the mapping ratified — which is invisible in
exactly the way the 2026-08-04 spend was invisible.

So `just check` grows `check-seats` (`tools/check_seat_config.py`): every agent
definition declares a model and an effort from the ratified sets, and a skill declares
neither — inheriting the session, as this project's three existing skills do — or both,
validly. `inherit` is accepted as a skill's model and refused as an agent's, where
inheriting is the defect rather than the intent.

This is the convention-lands rule applied to decision 1: "effort is only real through
the definition" has been a sentence in `CLAUDE.md` since 2026-08-04 and has had no
mechanical face. It has one now, landing with the first seat that needed it.

## What this ADR does not land

Neither `.claude/agents/cti-interlocutor.md` nor `.claude/skills/interlocutor/SKILL.md`
is in this commit. A dispatched session cannot write under `.claude/` (#294), and both
paths were probed here rather than assumed: `.claude/agents/` refuses with the same
*"you haven't granted it yet"* ordinary permission ask that #294 recorded for
`.claude/skills/`, despite `Write(.claude/skills/**)` being in the project allowlist.
That extends #294's table from two paths to three and confirms `agents/` is the ordinary
ask rather than the harder `hooks/` classification.

Both files are published verbatim on #255 for the orchestrator to land, on the pattern
#273 and #279 used the same week. Until they land, the `check-seats` gate is green
because it checks the seats that exist rather than requiring a named one — deliberately,
so the check does not depend on the half of this work it cannot reach.

## What would overturn this

- **Decision 1**: the human finding a one-turn seat unusable in practice — if the
  session-level `/model opus` + `/effort xhigh` fallback proves to be what they actually
  type every time, the slash command is doing nothing and should be replaced by a
  `/config` default or a dedicated Remote Control session started at that tier. Equally,
  a measurement showing `effort` frontmatter does **not** persist past the invoking turn
  where the body implies it might, which would make the caveat the headline rather than
  a footnote.
- **Decision 2**: the human wanting one seat rather than two — the agent definition then
  goes, since the slash command is the route the ruling's four named uses actually take,
  and nothing has yet dispatched *into* the interlocutor role. Or the reverse: a first
  attempt from the phone failing, which would mean Remote Control's inheritance of the
  project's `.claude/` is not what the unit file and the docs say it is.
- **Decision 3**: `check-seats` firing on something that was correct — a legitimate seat
  spelling its model or effort in a form the checker's flat frontmatter read cannot see.
  The remedy is the checker, not a suppression; a seat that a gate cannot read is a seat
  a reader cannot trust either.
- **The Model-roles row** (the gated part of all three): the human declining the seat's
  place in the mapping, which reverts the row and leaves the two `.claude/` files
  unlanded, costing nothing already spent.
