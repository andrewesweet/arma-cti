# Running the orchestration seat

> Status: written 2026-08-08 under #267. Ruled into existence by the human on #217
> (decision 5, 2026-08-05T21:50Z), sequenced to now by the human on #217 (2026-08-06)
> because the condition #242 attached — a convention lands with its first applied
> instance, not in a design document — was met when #250–#253 landed 05:02–05:51Z
> that day. This is the *operating* half: the rules a dispatching seat must not get
> wrong in the moment. It is not the design study; the study is its input.

## What this is, and what it is not

This runbook says **how the orchestrator seat is actually run**, after a week of
rulings scattered across issue threads. Its input is
`docs/orchestration-design.md` (`84cb8bd`, the study commissioned for #242), which
asked what the orchestrator does and what of it could be factored into tools. The
two are deliberately separate: the study reasons about the mechanism; this document
states the operating rules. **Cite the study; do not restate it.** Deleting the study
would not leave this runbook incoherent.

The always-loaded surface — `CLAUDE.md` — already carries the rules every agent on
every lane must hold (the working-style, model-roles, failure-class and command-table
sections). This document carries the rules only the dispatching seat can act on, and
it is read on demand, not resident. Where a rule here and a rule in `CLAUDE.md` say
the same thing, `CLAUDE.md` is authoritative; this document points at it rather than
quoting it.

## The seat and its model

The standing loop runs at **opus/high** per #242 ruling 1, which the human executed
directly in `CLAUDE.md`'s Model-roles section: the line reading "the orchestration
standing loop also runs here and dispatches fable for retros; ADR, `CONTEXT.md` and
schema semantics; retro evidence banking; and the #181-shaped diagnosis call." Check
that section as landed rather than this document — the human executed the seat change
there, not here.

The inversion this represents — run the loop at opus/high and **dispatch fable for the
named episodic acts**, rather than holding the scarcest seat all day and delegating
the loop out of it — is under a **pre-registered trial** whose criterion lives in the
design study §6 and whose urgency was measured on #258: ten consecutive dispatch
cycles from an opus/high orchestration seat, failing on any one of five clauses
(a dispatch into a freeze or reservation the policy recorded; an `infra_unavailable`,
`quota_exhausted`, `provider_refused` or `untyped_harness_failure` treated as a result;
a landing recorded against an issue its dispatch could not have made; a gated surface
edited without approval or an ADR-0013 record; a ruling with drafting slack transcribed
onto a gated semantic surface from the seat rather than dispatched). Its recording
surface was `just admission trial-report`, folded into `just watch-report` (#260); the
recipe is now `just trial report` and it is silent, because **ADR-0071 ruling 2 closed
that trial as inconclusive** (#328). Its cycles are kept as history, it is not
restarted, and the observatory does not subsume it — the observatory measures rework and
sees none of those five criteria, so they now go unmeasured. That is a loss rather than
a substitution. `just trial bar` prints the five by name.

The orchestrator seat is **ineligible on every foreign lane** (ADR-0061 Decision 2).
The standing retro allowance — the human's nine-profile ruling of 2026-08-09 on #300,
which superseded #217's time-boxed widening before it lapsed at `2026-08-10T14:00Z` —
covers only retros on the `codex` lane; it does not reach this seat.

## The duty cycle, and its arithmetic

Ruled on #258: the standing loop is **duty-cycled**, not run continuously, and the
target is **two-thirds of the remaining seven-day headroom** — about **40 hours of
continuous-equivalent orchestration** — to quota renewal at **14:00 Monday
2026-08-10**.

The figure is a target the seat checks itself against, not a feeling. State the
arithmetic so a later reader re-derives it against a different quota rather than
inheriting a number whose context has moved (calibration `claude/218-2026-08-05`,
measured on the orchestrator's own transcript, from #258's answer):

- **30,209 output tokens per five-hour point; 181,253 per seven-day point.**
- **904 output tokens per minute** of orchestration.
- At filing, **18 seven-day points** remained. Continuous orchestration across the
  **92.6 hours** to renewal is 5.02 M output tokens — **27.7 points, 1.5× the
  remaining quota** — so a loop left to run itself flat spends the whole window and
  leaves nothing for anything else.
- Two-thirds of 18 points is **12 points**; 12 × 181,253 = 2.18 M tokens; ÷ 904 per
  minute ≈ **2,406 minutes ≈ 40 hours**.

Re-derive against the live meter (`just watch-report` carries the breaker read; the
ledger carries per-dispatch `cap_fraction`). Confounds stated on #258: the meter
includes the human's non-project use; the 83-minute sample that produced 904 was an
unusually busy stretch with three dispatches launching.

**The honest thing this document must record.** The seat ran the queue one-deep for
long stretches on 2026-08-07/08 while 54 issues were eligible, and the human had to
correct it twice. `#278` is the mechanism that now surfaces this at the top of the
turn (see below); `#276` and retro 27's bank carry the evidence. A runbook that
described the seat as it *should* run, rather than as it *did*, would be the wrong
document.

It happened again on 2026-08-09 and the human corrected it a third time, so #295
measured it rather than exhorting against it: the seat used **286 of 955** ruled
agent-minutes over a 191-minute block, mean occupancy **1.50 of 5**, and **89% of the
loss fell while the seat was not running at all**. The cause was mechanical — a cohort
followed to its last completion instead of its first — and it is fixed in
`just dispatch-follow` below. What that leaves the seat responsible for is small and
worth naming: the loss while *awake* was 73 agent-minutes over 19 minutes of turns.

## The top-of-turn sequence

1. **`just watch-report`** — leads, because CLAUDE.md already puts this read at the
   top of an orchestrator's turn. It runs four reads in order: the **lane breakers**
   first (#226) — one line per lane that is not dispatchable, silent otherwise; then
   the **queue's underfill verdict** (#278) — `queue=underfilled …
   action=refill-before-landing` when eligible work can fill ruled capacity, silent
   when capacity is full or no candidate survives; then the **watcher findings**
   (#198); then the **orchestration-seat trial** report (#260), one line when it has
   failed, silent while clean. Silence is the clean read; a verdict, never a
   dashboard of numbers (#209).
2. **`just queue state`** then **`just queue next`** — the candidate with its
   derivation (the freeze, the WIP limit, the packages, the in-flight list), or a
   named refusal. The queue selects and prints; **it never dispatches** (ADR-0053).
   `next=` names a **selection, not a routing decision**: it may point at an issue
   that is corpus-bound and so undispatchable to any foreign lane — `#18` was named
   while in that state. The queue's job ends at pointing; routing onto a lane is the
   seat's, behind the breaker and the human's off-peak rule. Nothing judges the
   route's quality upfront: ADR-0071 ruling 6 dropped the admission bar and #328
   removed it from `just dispatch`, and what replaces it is retrospective and not
   built yet.
3. **Judgement** — is that candidate the right next thing, given the human's live
   intent this session. This, and not the queue, is the step that decides.
4. **`just brief N`**, then write the variable half — the task, the scope, the ground
   truth, and the reason for a non-default seat. This is the real work of the turn;
   an unedited brief is obviously unfinished by construction. Before writing it, read the
   issue body and its latest comments; an explicit human ruling is ground truth, and
   neither the title nor the seat's memory may widen it. Measured at **837 output
   tokens and about 30 seconds**, 57% of a dispatch turn's generation and 0.028 pp₅ₕ
   (#295). Do not spend that as a reason to write less of it: over the block where the
   seat's occupancy collapsed, all the brief-writing in it was worth under 1% of the
   loss, and the same four days' briefs are what stopped #256 flipping ADR-0064's
   approval and licensed #246 to conclude "not worth it".
5. **Dispatch.**
6. On completion: paste `just verdict`, run `just trial close-audit`, **judge the close**.
7. Episodically: the retro, the rulings intake, the evidence banking.

## What the seat holds, and what it dispatches

The orchestrator holds the wait — that is what the seat is for. A subagent, by
contrast, **ends rather than waiting**: foreseeably long work is dispatched detached,
the agent arms `just watch`, writes a handoff per `docs/agents/handoff.md`, and stops
there, because a background completion nobody is billed to wake is the stall shape
(CLAUDE.md working style; #218's measurement retired the cache arithmetic that rule
once rested on).

A wait that genuinely cannot be decomposed has **one sanctioned fallback**: a
dispatched session — `just dispatch --lane claude-native` — with `just watch` armed at
dispatch and the result read from the ledger (#218 ruling, decision 1). The seat
itself holds waits in the foreground; a dispatched session is the escape hatch for the
waits a subagent cannot satisfy by ending.

**The single-shot contract (#279).** A dispatched session has no second turn for a
background completion or a question. Run awaited work in the foreground; decide
routine ambiguities, act, and record the reasoning; if a choice is genuinely the
human's, finish the unambiguous part and state exactly what remains. The guard refuses
**backgrounding, never waiting** — holding a long foreground wait is what a dispatched
session is *for* (#218). Two dispatches on 2026-08-08 ended the wrong way before this
was made explicit: one left its gate uncommitted with "awaiting completion
notification" (`just land` refused `dirty_tree`), one asked whether to run
`git checkout --` with no caller listening.

**`just dispatch-follow <id> [<id> …]` (#280, #295).** Restores the completion edge
*inside a live orchestrator session*: a harness-attached follower that exits when a
dispatch writes its result, printing the dispatch id and result path from the record,
and whose exit re-invokes the seat. It has no timeout and classifies nothing — a runner
that disappears without a result is `finding=runner_disappeared`, and stall judgement
stays with `just watch`. **It cannot survive the session ending.** Cross-session
autonomy requires the scheduled-agent mechanism that is with the human and is explicitly
out of scope; do not imply autonomy the mechanism does not provide.

**Follow a cohort in one invocation; never loop one follower per id inside one
background task.** The loop is a barrier: it returns when the *slowest* member finishes,
so it produces one wake, and every slot the faster members freed stays empty until then.
`just dispatch-follow a b c` returns on the **first** of them and prints `pending=` for
the rest, which is the wake the seat actually needs — something freed a slot, come and
refill it. Re-follow the remainder in the same turn.

The rule is measured, not tidy-minded (#295, `docs/research/dispatch-cost-and-occupancy.md`).
Over 2026-08-06/09 the loop delayed the seat's wake by **292 agent-minutes**, once by
**115 minutes** on a single cohort: at 07:46:59Z on 2026-08-09 the seat followed three
dispatches that ended at 07:53, 08:03 and 09:48, was woken at 09:48, and slept through
two freed slots with 48 issues eligible. Over that block the seat used **286 of 955**
ruled agent-minutes, and **89% of the 669 lost fell while it was asleep** — against at
most 5 attributable to writing briefs. #278's `action=refill-before-landing` was printed
correctly throughout and could not help: it prints at the top of a turn, and there was no
turn.

## The review function

Confirmed on #217 (2026-08-06) and stated in the design study §7: **the gates
review**; the foreign lane is the **second lens** of one pass, not a second pass
(ADR-0061 Decision 3); the orchestrator keeps **claim spot-checks only**. Three
constraints:

- **Sampled, never standing.** A spot-check on every close is a standing second pass
  wearing another name. CLAUDE.md bars added verification passes, and #220 re-based
  that from a quality rule to a first-order cost rule — an extra pass is pure
  generation, and generation is what this plan meters.
- **Opus/high** — a judgement behind gates.
- **It reviews claims, not code.** Architecture and design taste are the per-issue
  review lens (#240) and the periodic deep pass (#139). The mechanical half of a
  close — SHA on main, SHA inside the dispatch's window, corpus owed and quoted,
  evidence path resolvable — is computed by `just trial close-audit`, not re-read by
  hand.

## The tools, and when the seat reaches for each

Half of what this runbook used to hold in prose was factored into tools by #242. This
section says when the seat reaches for each; the recipes' own headers say what they
do.

| When | Tool | What it gives the seat |
|---|---|---|
| Turn-top | `just watch-report` | Breakers, queue underfill, watcher findings, trial — one read |
| Choosing work | `just queue state` / `next` / `check --issue N` | The next dispatchable issue with its derivation, or a named refusal |
| Recording a ruling | `just queue freeze/open/wip/package … --ruling "…"` | The freeze, WIP limit and carve-outs written to a file `just dispatch` reads per dispatch — never memory |
| Before dispatch | `just brief N` | The invariant half composed from data; the seat writes the variable half |
| Dispatching | `just dispatch --lane … --profile … --seat … --issue N` | Hand work to a lane, return at once with a dispatch id |
| Following a dispatch | `just dispatch-follow <id> [<id> …]` | The within-session completion edge — **the first** of the ids, never a loop over a cohort (#280, #295) |
| Asking whether occupancy held | `just occupancy --since … --until … --limit N` | One window's agent-minutes: capacity, used, lost. `just queue state` counts what is in flight now and so cannot show a sawtooth (#295) |
| At dispatch | `just watch <name> <worktree> [subject]` | Arm the detached stall watcher |
| On a finished pool | `just verdict [pool-dir]` | The record a close quotes — **paste verbatim, never retype the SHA or evidence path** (#219) |
| Judging a close | `just trial close-audit --issue N` | The six checkable claims over a close, computed and cited. It concludes nothing further: the bar that read two of them into criteria was dropped by #328 |
| Quoting spend | `just ledger-sync show --dispatch <id>` | The per-dispatch row, in `cap_fraction`, before quoting a dispatch's cost |
| Recovering | `just recover check <name>` / `just recover brief <issue\|worktree>` | The runbook's two computable procedures (#253) |
| Landing | `just land` | The landing protocol — **paste its output verbatim, never retype it** |

## The landing half

Landing is most of the seat's real work, and the lane decides how much of it the seat
does by hand.

- **Codex, under #265's confirmed ceiling, commits but cannot gate.** The orchestrator
  gates and lands its work by hand and states that in the close; twelve closes now say
  so. ADR-0061 Decision 4 is the rule: a lane that has not proven its hooks gets
  worktree and commit only; landing is done by another seat.
- **z.ai commits, gates and lands unaided.** Its implementer route accrued clean
  assessments against the admission bar and never reached that bar's `N`, so it was
  never admitted and never failed; the frozen record is
  `~/.arma-cti/admission/zai.zai-glm52-max.implementer.json`. That is history, not a
  standing — the bar is dropped (ADR-0071 ruling 6, #328) and no route is judged before
  it is dispatched.
- **The corpus is a permanent Claude-seat obligation.** `just regress` appears in no
  allowlist entry, and a foreign lane cannot run the gate its own change owes. Anything
  touching `addons/`, `missions/`, `extension/`, the daemon's world-facing half or a
  manifest needs a full-corpus run before landing — on this seat, not delegated (#258,
  finding 2).

## What the seat must not do

- **Draft gated-surface work in its own tree while subagents are live.** ADR-0061
  reached `origin/main` unreviewed through the #105 worktree collision — the shape of
  an unreviewed ADR draft sitting in a worktree that landed. Gated-surface drafting
  (ADRs, `CLAUDE.md`, `CONTEXT.md`, schema semantics) dispatches to fable; the seat
  does not hold it.
- **Never write a brief's task, scope or ground truth from the issue body alone.** Read the
  thread first, and name the comment each pre-derived decision comes from, so that a body
  the thread has superseded shows up in the brief rather than being resolved silently.
  #25's brief asked for implementation at `opus-xhigh`, named the full corpus and offered
  ADR-0013's standing authorisation, after nine rulings on its own thread had converted the
  issue to a decision ticket with no production code; the dispatched agent read the thread,
  built nothing and said why. The same shape is recorded once before, on #234. Both were
  caught by the agent, not by the seat.
- **Dispatch off a table the human has not agreed.** The class rule is the policy; any
  routing table is its first applied instance, never the policy itself (#258 ruling 1).
- **Interpret a `quota_exhausted` or `provider_refused` stop.** Neither is a result;
  the verdict says nothing about the code under test. Re-dispatch to another lane, or
  queue until the window resets; record a refusal against its profile; escalate when N
  consecutive refusals trip the quality breaker (ADR-0061 Decisions 7 and 8; the
  failure-class table).
- **Re-run a flake past the one sanctioned retry.** The `flake_quarantine` row: if an
  exact quarantined test is the only red, quote its issue and re-run once; a second
  red, or any other red, is yours.
- **Transcribe a ruling with drafting slack onto a gated semantic surface from the
  seat itself.** Route to `cti-implementer` or above (#217 decision 4).
- **Claim a criterion an agent reserved for the seat.** The close's criterion-by-
  criterion audit records what was done; a criterion an agent left for the orchestrator
  is claimed only when the orchestrator has actually done it.
- **`export ANTHROPIC_BASE_URL`** into a shell, a profile, or `~/.claude/settings.json`.
  Lane environments are assembled per invocation by `just dispatch` and nowhere else —
  a global redirect captures every Claude Code session on this box, this one included.
- **Run a generated sudo script.** `just prereqs sudo-script` *generates* the one root
  script the initiative needs, to be read; it is never run from here.
- **Extend, invent or guess a breaker's wait.** A lane reopens at a boundary its
  provider published, on evidence it is serving again, or by a human's hand — never on
  a timer this project chose.
- **Treat `infra_unavailable` as a result.** Stop; do not interpret.

## Context hygiene

The one-line rule the design study §8 yields, carried here as the operating form: an
orchestrator's turn opens with `just watch-report` and `just queue next`, and holds
nothing between turns that either would re-derive — the queue ordering, the freeze and
carve-outs, the WIP limit, the in-flight set, briefing boilerplate, pool details and
evidence paths are all rendered and read, not carried. What the seat holds, and no tool
should try to: the human's live intent this session, the cycle's shape, the open
rulings, and which issues are *about* the same thing where no `Blocked-by:` line has
been written.

## Consistency with AGENTS.md (acceptance criterion 2)

Checked against `AGENTS.md`'s Working-style and Model-roles sections as landed at the
time of writing (`04d6d55`): the seat (opus/high, fable dispatched for named acts), the
hold-the-wait / end-don't-wait split, the single-shot shape, the no-added-pass review
function, the breaker-wait and `infra_unavailable` rules, and the
`ANTHROPIC_BASE_URL` prohibition all restate `AGENTS.md` rules and point at them rather
than overriding them. No conflict found.

One item this section originally carried as a **proposal for the sign-off gate**
(acceptance criterion 5) — the pointer from `AGENTS.md` to this document — has since
gone through that gate and landed at `b2d9006`: `AGENTS.md`'s Agent-skills section now
reads "The orchestration seat's operating rules live in `docs/agents/orchestration.md`;
read it before dispatching." (Stale "unlanded proposal" wording corrected under #297.)

A second item from #295 — a row for `AGENTS.md`'s command table, landing with its recipe
as the convention requires — is no longer waiting on that gate. The human approved it
**in substance** on 2026-08-14 (#217, "Human ruling — the piled command-table rows are
approved in substance; the text is re-derived, never pasted"), stating that `AGENTS.md`
being a sign-off gate is what that ruling discharges. What is outstanding is a
derivation-and-landing pass, not a human decision: the wording is derived from the
recipe's own behaviour at landing time and reviewed under ADR-0071 ruling 4, never pasted
from the text below, which stands only as the intent that was approved:

> | `just occupancy --since T --until T --limit N` | One window's seat occupancy in
> agent-minutes from the dispatch records: capacity under the ruled WIP limit, used,
> lost, and the per-minute series. Reads; carries no verdict, because it cannot see the
> queue | No | Judging whether an occupancy intervention held, before and after |

Refs #105, #198, #209, #217, #218, #219, #220, #240, #242, #250, #251, #252, #253,
#258, #260, #265, #276, #278, #279, #280, #294, #295, ADR-0042, ADR-0053, ADR-0057,
ADR-0061.
