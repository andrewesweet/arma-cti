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

The always-loaded surface — `CLAUDE.md`, which is the committed symlink to `AGENTS.md`
and not a second copy of it — already carries the rules every agent on every lane must
hold (the working-style, seats-and-profiles, failure-class and command-table
sections). This document carries the rules only the dispatching seat can act on, and
it is read on demand, not resident. Where a rule here and a rule in `CLAUDE.md` say
the same thing, `CLAUDE.md` is authoritative; this document points at it rather than
quoting it.

## The seat and its model

The seat is a row in `tools/dispatch.py`'s `SEATS`, and that registry is what a reader
should check rather than a pair written here (ADR-0071 ruling 2; `just dispatch --list`
prints it). Two facts about the row are operating rules rather than registry trivia:

- **The `orchestrator` row carries `claude_only`, and it is the only row that does.**
  ADR-0071 ruling 1 rescinds provenance as a basis for eligibility and takes the word
  *foreign* out of the vocabulary; the carve-out that survives is this one, on the
  ground that the seat deciding what everything else does should not move before a
  tested alternative exists. It is **provisional and carries an end condition** — it
  ends when the Codex orchestrator backup is built — and the ADR records that the end
  condition will be reached with no observation behind it, because this is the one seat
  the observatory structurally cannot see: the seat's own turns carry no dispatch id and
  reach no ledger row.
- **The seat's escalation column is empty, so it arbitrates at `fable-high`** (ADR-0071
  ruling 4). The orchestrator authors changes routinely, and without that default the
  never-alone loop has no terminus for the seat that runs it.

**#242's pre-registered trial is closed as inconclusive** (ADR-0071 ruling 2). Its
criteria and records judged an orchestration seat at one pair and the seat map sets
another, so the accrued records cannot validate the new one; they are kept as history.
The trial is **not** replaced by the observatory, and saying so would be the third
draft's withdrawn claim: it measured five orchestration-process criteria — among them
honouring a freeze and refusing to treat `quota_exhausted` as a result — and the
observatory measures rework and sees none of them. Those five go unmeasured, which is a
loss rather than a substitution. The harness has moved to `tools/trial.py` and the
recording surface folded into `just watch-report` (#260) is now `just trial report`,
which is silent against a closed trial (#328); `just trial bar` prints the five criteria
by name, so a reader meets the list rather than a count. A clean read from either now
vouches for nothing.

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
   (#198); then the **orchestration-seat trial** report (#260), which is now silent
   always, the trial being closed (#328). Silence is the clean read; a verdict, never
   a dashboard of numbers (#209).
2. **`just queue state`** then **`just queue next`** — the candidate with its
   derivation (the freeze, the WIP limit, the packages, the in-flight list), or a
   named refusal. The queue selects and prints; **it never dispatches** (ADR-0053).
   `next=` names a **selection, not a routing decision**: it may point at an issue
   whose routing class refuses the seats or lanes otherwise available — `#18` was named
   while corpus-bound. The queue's job ends at pointing; routing is the seat's, behind
   the routing policy, the breaker and the off-peak rule. Nothing judges the route's
   quality upfront: ADR-0071 ruling 6 dropped the admission bar and #328 removed it
   from `just dispatch`, and what replaces it is retrospective and not built yet.
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

**Reviewing is a seat now, and it is not this one.** ADR-0071 ruling 4 lands no change
alone: every landing is reviewed by an instance in a different session that did not
author it, dispatched at `--seat review` with `--reviewing <profile>`, and the review
seat's containment is forced rather than defaulted. That is not an added pass the seat
may skip or absorb — it is one of the two exceptions `CLAUDE.md`'s no-further-
verification rule now names, and the orchestrator is bound by it for the changes it
authors itself like anyone else.

What survives of #217's confirmation (2026-08-06, design study §7) is the *residue*
after that seat exists: **the gates review**, a second provider over one diff is the
**second lens** of one pass rather than a second pass, and the orchestrator keeps
**claim spot-checks only**. ADR-0061 Decision 3 is withdrawn as a provenance rule and
is no longer what licenses the second lens; provider diversity is (ADR-0071 ruling 4,
and the review seat's own resolution rule, which prefers a different lane). Three
constraints on the spot-check:

- **Sampled, never standing.** A spot-check on every close is a standing second pass
  wearing another name, and never-alone's review does not make one available. CLAUDE.md
  bars added verification passes beyond its two named exceptions, and #220 re-based
  that from a quality rule to a first-order cost rule — an extra pass is pure
  generation, and generation is what this plan meters.
- **At the seat's own tier** — a judgement behind gates, and no reason to name a pair
  the registry already holds.
- **It reviews claims, not code.** Architecture and design taste are the review seat's
  (#240) and the periodic deep pass's (#139). The mechanical half of a close — SHA on
  main, SHA inside the dispatch's window, corpus owed and quoted, evidence path
  resolvable — is computed by `just trial close-audit`, not re-read by hand.

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
| Dispatching the review | `just dispatch --seat review --reviewing <profile> …` | Never-alone's second instance. Resolution returns neither that profile nor any other the issue's dispatch records place on the work, prefers a different lane, and forces the read-only mode. Those records are a *potential*-author set, so the route is `reviewing_checked` and never `reviewing_verified` |
| Handing the branch over | `just review exchange N` / `just review record …` / `just review show <id>` | The implementer pushes `refs/heads/issue-N`, the reviewer takes it with `just worktree restore --ref`, and the verdict is written beside the reviewing dispatch's record — its identity derived from those records, never declared (#332) |
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
  so. ADR-0061 Decision 4's graded ladder is withdrawn (ADR-0071 ruling 1), so this is
  no longer a rule about proven hooks — it is a **measured ceiling**: no `writable_roots`
  set lets a Codex dispatch both commit and run the gate, and the mechanism is isolated
  in `docs/multi-provider-dispatch.md`. Under the binary rule that replaces the ladder,
  a profile that cannot run its own gate is not an implementer, which is why lifting the
  ceiling is a blocking prerequisite for the Codex head of that seat's list.
- **z.ai commits, gates and lands unaided.** Its admission-bar standing is no longer the
  thing that says so: ruling 6 withdraws the bar and #328 removed the mechanism. That
  route accrued clean assessments and never reached the bar's `N`, so it was never
  admitted and never failed; the frozen record at
  `~/.arma-cti/admission/zai.zai-glm52-max.implementer.json` is history rather than a
  standing, and no route is judged before it is dispatched.
- **The corpus cannot be run from a subagent, on any lane.** This is a subagent rule and
  not a lane rule, so it names no seat and refuses no dispatch route: routing class 5 is
  narrowed to what a *subagent* cannot do — hold the corpus's foreground wait
  (`.claude/hooks/deny-subagent-waits.py`) — so a seat reached that way cannot gate its own
  in-world work. `just dispatch` launches a top-level session, which the wait hook permits,
  so the class carries `"refuses": false` and bars nothing. The obligation the seat keeps
  is therefore an obligation to *see the corpus run*, not to run it here. Anything
  touching `addons/`, `missions/`, `extension/`, the daemon's world-facing half or a manifest still needs a full-corpus
  run before landing (#258, finding 2), and that class's two path lists remain the one
  authority for what an in-world surface is.

## What the seat must not do

- **Land a change alone.** No single model instance may both propose a change and
  produce the verdict that clears it (ADR-0071 ruling 4), and the seat holds no
  exemption from that. The **lander** may be the proposer; the **reviewer** may not.
- **Draft gated-surface work in its own tree while subagents are live.** ADR-0061
  reached `origin/main` unreviewed through the #105 worktree collision — the shape of
  an unreviewed ADR draft sitting in a worktree that landed. Where that drafting goes
  is no longer "to fable": ADR authorship is routing class 3, which appoints `planner`
  to author, `implementer` to land and `review` to review, on any lane, and refuses
  `orchestrator`, `fable` and `retro`; orchestration's own process docs — this file
  among them, by `CLAUDE.md`'s Agent-skills section — are routing class 2, which admits
  that same route plus `orchestrator` and refuses `retro` and `fable`. Either way the
  seat does not hold the drafting. **Neither class is inferred from the path** — neither
  row carries path prefixes, and the policy's own coverage note says a seat-bound class is
  checked at dispatch only, since a landing has no seat to check. It does **not** follow
  that a class fires only when the issue declares it: both rows also carry `issue_phrases`,
  and `tools/routing_policy.py` matches each as a plain casefolded substring of the issue
  text, so an issue merely *mentioning* ADR authorship fires class 3 without declaring
  anything (#329 review round 2, F7 — the earlier wording said "declared on the issue and
  never inferred", which overstated it). What the paragraph above is, either way, is an
  instruction to the seat rather than a claim that a refusal reliably exists: an issue that
  neither declares a class nor happens to carry a matching phrase is classified by nothing.
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
  seat itself.** Dispatch it (#217 decision 4). "Or above" is not a comparison this
  project makes — profiles are opaque tokens and no cross-provider effort scale exists
  (ADR-0061 Decision 5, which survives ADR-0071) — so route it to the seat whose kind of
  work it is and let that seat's preference list resolve the profile.
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

Re-checked under #329 against `AGENTS.md`'s Working-style and Seats-and-profiles
sections as this landing leaves them: the seat (a `claude_only` registry row and an
empty escalation column, no pair restated here), the hold-the-wait / end-don't-wait
split, the single-shot shape, never-alone and the residual spot-check, the breaker-wait
and `infra_unavailable` rules, and the `ANTHROPIC_BASE_URL` prohibition all restate
`AGENTS.md` rules and point at them rather than overriding them. No conflict found.

**One inconsistency is stated rather than resolved**, because resolving it is not this
document's to do. ADR-0071 rulings 2 and 6 close #242's trial and withdraw the admission
bar, and both mechanisms are still live in `tools/admission.py` and still folded into
`just watch-report`; #328 removes them. Until it lands, this runbook records the decision
and the seat reads those outputs as history rather than as a verdict. That window is the
"period of stated inconsistency" the ADR's own sequencing names, and it stops being a
transition and becomes a defect if the sequence stalls part-way.

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
#258, #260, #265, #276, #278, #279, #280, #294, #295, #320, #321, #322, #324, #325,
#326, #327, #328, #329, #331, #332, ADR-0042, ADR-0053, ADR-0057, ADR-0061, ADR-0071.
