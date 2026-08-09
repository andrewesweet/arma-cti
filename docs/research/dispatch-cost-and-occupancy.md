# What a dispatch costs the seat, and what actually holds occupancy down

**Outcome: the brief is not the bottleneck.** #295 filed the hypothesis that WIP
sawtooths because the orchestrator writes one task-specific brief half per
dispatch and cannot write them fast enough. Measured, the brief half costs the
seat **837 output tokens and about 30 seconds** — and over the block that
prompted the issue it accounts for **at most 5 of 669 lost agent-minutes**,
under 1%. **89% of the loss fell while the seat was asleep**, and the mechanism
that kept it asleep is that a refill cohort was followed to its *last*
completion rather than its first. One 120-minute sleep, behind one cohort,
accounts for 68% of the whole block's loss on its own.

The intervention that follows from this is small and it does not touch the
brief: `just dispatch-follow` now takes several ids and returns on the first of
them. The interventions that would have removed the seat's judgement are
rejected below, and the reason is that the measurement never justified them.

Issue #295. Written 2026-08-09.

## 1. The instruments, named

Two, and neither is an input-equivalents figure.

**Generation.** `usage.output_tokens` read from the orchestrator's own Claude
Code transcript,
`~/.claude/projects/-home-andre-code-github-com-andrewesweet-arma-cti/c155b437-7b01-4c58-a996-ce234b8e2fda.jsonl`,
covering **2026-08-06T20:53:54Z → 2026-08-09T10:24:09Z**. This plan meters
generation, not context (#218, #220, #232), so output tokens are the
spend-bearing quantity and nothing here is priced in characters ÷ 4.

One correction the transcript forces: Claude Code writes **one JSONL line per
content block**, and every line of a multi-block turn repeats that turn's
`usage`. Summed naively the session reads as 659,374 output tokens across 916
lines; deduplicated by `message.id` it is **397,442 across 642 turns**. The
naive figure is 66% too high. Anyone re-running this measurement has to
deduplicate first.

**Occupancy.** Wall-clock agent-minutes computed from
`~/.arma-cti/dispatches/*/dispatch.json` and `result.json`, which carry
`started_at` and `ended_at` per dispatch. `tools/occupancy.py` (`just occupancy`)
is that computation, landed with this study so the post-intervention arm is a
command rather than a hand-rolled `jq` session.

## 2. What a dispatch costs the seat

The seat performs a whole dispatch in **one turn, one `Bash` call**: `cd`,
`just worktree add`, `just brief N --out $SP/brief-N.md`, a heredoc appending the
task-specific half, `just dispatch --brief-file`, `just watch`, `just
watch-report`. So a dispatch's generation cost is exactly one turn's
`output_tokens`, and the step breakdown comes from contrasting turn populations
rather than from apportioning a single number.

| Turn population | n | Mean output tokens |
|---|---|---|
| Issued `just dispatch … --issue`, with a heredoc brief half | 60 | **1,468** |
| Issued `just dispatch … --issue`, no heredoc (brief file already written) | 31 | **631** |
| Every other turn in the session | 551 | **526** |

Reading down the table:

| Step | Output tokens | Share of a dispatch turn |
|---|---|---|
| The task-specific brief half | **837** (1,468 − 631) | 57% |
| Dispatch scaffolding — worktree, brief, dispatch, watch, watch-report | **105** (631 − 526) | 7% |
| Baseline turn cost — reasoning and narration any turn pays | **526** | 36% |
| The invariant brief half | **0** | 0% |

**The invariant half is already free.** `just brief` composes it from data
(#251): across the 58 briefs in `~/.arma-cti/dispatches/*/brief.md` that carry
its marker, the invariant half averages **1,688 characters, 30.4% of the brief**,
and the seat generates none of it. #251 has already taken the third of this
artefact that was takeable without judgement.

**Cross-check on the 837.** The heredoc bodies average **2,880 characters**
against **420** of surrounding command. 2,880 ÷ 837 = **3.44 characters per
output token**, which is the right band for English markdown and not a coincidence
two independently-derived quantities would land in. The contrast is measuring the
brief text and not some confounded difference in thinking.

**In spend.** At the ratified calibration — 30,209 output tokens per five-hour
point, 181,253 per seven-day point (`docs/agents/orchestration.md` §duty cycle,
from #258) — one brief half is **0.028 pp₅ₕ**. All 60 written across four days
come to **0.28 seven-day points**, against the 18 that remained at #258's filing:
**1.5% of the week's headroom**. The whole 397,442-token session is 2.19
seven-day points.

So the brief half is genuinely the largest *single* item in a dispatch turn, and
the issue was right about that. It is also, in absolute terms, small.

## 3. What actually holds occupancy down

Block: **2026-08-09T07:13Z → 10:24Z**, 191 minutes, WIP limit 5 throughout (the
limit was raised from 3 at 07:12:50 for #284's candidate block; the block starts
after that so the capacity line is one number).

```
series=11113333333331100000233333332222222222111111111111111111111111111111111
       1111111111111111111111111111111111111111111111111111111111111111111111
       111111111111111111111111111111111000001333332222111111111111111111
```

| Quantity | Agent-minutes |
|---|---|
| Capacity at the ruled limit | 955 |
| Used | 286 |
| **Lost** | **669** (70.1%) |
| Mean occupancy | **1.50 / 5** |

Now partition that loss by whether the seat was awake. Awake means a turn
timestamp in that minute; the seat took turns in **19** of the 191 minutes.

| | Minutes | Lost agent-minutes | Share of loss |
|---|---|---|---|
| Seat awake | 19 | 73 | 10.9% |
| **Seat asleep** | **172** | **596** | **89.1%** |

And the sleeps individually:

| Sleep | Duration | Lost agent-minutes | Share of loss |
|---|---|---|---|
| 07:32Z → 07:51Z | 20 min | 29 | 4.3% |
| **08:01Z → 10:00Z** | **120 min** | **458** | **68.5%** |
| 10:09Z → 10:35Z | 27 min | 96 | 14.4% |

*(Sleep windows are stated as minute offsets converted back to the clock; the
underlying series is minute-indexed from 07:13Z.)*

The 120-minute sleep is the sawtooth. At its start four of the five slots were
free and 48 issues were eligible. The seat was not deciding, not writing, and not
short of work. It was not running.

**Brief-writing, on the same scale.** Within the bursts, consecutive
dispatch turns are 27, 34 and 29 seconds apart. Ten dispatches fall in this
block, so all the brief-writing in it is about **5 minutes of wall clock — at
most 5 of the 669 lost agent-minutes, 0.7%**. Even taking the entire 73
lost-while-awake as brief cost, which over-counts by including judgement,
landings and gate reads, it is 10.9%.

**The 5× standard (#237) applied to the filed hypothesis.** #295's diagnosis —
"the sawtooth's trough is set by brief-writing throughput" — is wrong by roughly
**130×** against the outcome measure it names.

## 4. Why the seat was asleep: the cohort barrier

The seat's refill idiom was:

```sh
for d in d-…-a d-…-b d-…-c; do just dispatch-follow $d 2>&1 | tail -1; done
```

run as a **single** harness-tracked background task. `just dispatch-follow`
blocks until its one dispatch writes a result; a loop over three of them blocks
until the **last** does. One background task means one completion notification,
so the seat is woken once, by the slowest member.

That is what happened at 07:46:59Z. The cohort was `#256` (ended 07:53:03Z),
`#262` (08:03:47Z) and `#246` (09:48:02Z). Two slots freed within seventeen
minutes; the notification arrived **two hours and one minute later**, at
09:48:03Z, and the seat's next turn is 09:48:16Z. The human then had to ask, at
09:52:35Z, "Why is WIP not at five or oscillating rapidly to five? We have a long
ready work queue."

#278's underfill verdict was printed correctly throughout and could not help: it
prints at the top of a turn, and there was no turn.

### The barrier's cost across the corpus

Every backgrounded follower launch in the session, with the delay it imposed —
for each member, how long after its own completion the seat was actually woken:

| Follower launched | Members | Delayed wake |
|---|---|---|
| 08-08T16:44:54Z | 1 | 0 |
| 08-08T17:09:44Z | 1 | 0 |
| 08-08T19:28:22Z | 3 | 13 min 56 s |
| 08-08T21:00:10Z | 2 | 5 min 43 s |
| 08-08T21:25:50Z | 3 | 2 min 01 s |
| 08-08T21:41:54Z | 3 | 34 min 20 s |
| 08-08T22:07:13Z | 3 | 5 min 44 s |
| 08-09T02:05:22Z | 1 | 0 |
| 08-09T07:06:53Z + 07:14:25Z | 2 + 4, overlapping | 10 min 47 s |
| 08-09T07:46:59Z | 3 | **219 min 14 s** |

**Total: 292 agent-minutes of delayed wake**, all of it in the eight launches
that named more than one id, none of it in the three that named one. The
07:06/07:14 pair is collapsed because both followers were live at once and the
earlier one's wake is what the seat would have got; counting them separately
would have over-claimed by four minutes.

The contrast is observational rather than randomised, and the confound is stated
plainly: the three single-id launches have zero delay partly **by construction** —
one member cannot be late relative to itself. What the corpus establishes is the
size of the quantity the barrier is exposed to, which is the *spread* of a
cohort's run times. That spread is large here: dispatch durations in the window
run from 4 minutes to 122. A barrier over a population with that spread will keep
paying, and it paid 292 minutes in four days.

## 5. The intervention, and what it is judged by

**Landed: `just dispatch-follow a b c` returns on the first completion, naming
the rest as `pending=`.** `wait_for_first` selects across every recorded runner
pipe instead of one. A single id behaves exactly as before, down to the emitted
lines — the `pending=` line is omitted when there is no remainder, so nothing
that reads the old three-line completion has to change.

Against the measured corpus the counterfactual is exact where the records make it
exact: at 07:46:59Z the seat would have been woken at **07:53:03Z** instead of
09:48:02Z, ending the 120-minute sleep at its sixth minute. That is a
counterfactual, not a measurement, and it is labelled as one.

**The prospective arm is the seat's, and it is not run here.** A dispatched
session cannot run `just dispatch` (#294 records the command surface), so the
before/after over a fresh block of real dispatches has to be taken by the
orchestration seat. `just occupancy --since … --until … --limit 5` is the
instrument; §3's block is the control, and its headline numbers to beat are
**mean occupancy 1.50/5** and **669 lost agent-minutes over 191 minutes**. The
comparison is only fair over a block with comparable eligible depth — this one
ran with `eligible` never below 48, so eligibility was never the binding
constraint and a later block should state its own.

## 6. Rejected, and why

**Batching — prepare N worktrees and N briefs in one pass, dispatch together
(#295's candidate 3).** Rejected, and it is worth being explicit that this
candidate makes the measured defect *worse*. Batching dispatch is what creates a
cohort; a cohort followed as one unit is the barrier that cost 292 minutes. The
setup cost it would save is the 105 output tokens of scaffolding per dispatch —
7% of a dispatch turn, about 0.003 pp₅ₕ — bought by deepening the mechanism
responsible for 89% of the loss.

**`just dispatch --next`, composing the brief from the issue and the routing
verdict alone (#295's candidate 4).** Rejected on the measurement, before any
argument about judgement is needed: it targets 837 output tokens and 30 seconds
of the seat's turn, against a defect measured at 596 lost agent-minutes. The
throughput number it would move is not the number that is broken.

The judgement argument stands behind that and is the one that matters if the
first ever stops holding. The task-specific half is where the seat's reading of
the situation reaches the work, and in this week alone it stopped #256 flipping
ADR-0064's approval, gave #233 #222's reproduction method, licensed #246 to
conclude "not worth it", and told #244 not to move mechanism and numbers
together. Four saves in four days, none of which any composed brief would have
produced, because each depended on knowing something about the *other* work in
flight. An intervention that removed them would show as a throughput win and be a
regression, and the throughput win would have been 0.7% of the loss.

**Shortening the brief half (#295's candidate 1).** Rejected on the same
arithmetic, and on a second ground: the 837 tokens are the compressed remainder
after #251 already took the invariant 30%. What is left is the part that varies
per issue, which is the part that cannot be composed.

**Refill before landing rather than after (#295's candidate 2).** *Not*
rejected — but it is not this defect. The corrective is real, it is already
printed by #278's `action=refill-before-landing`, and mechanising it is worth
doing. It addresses the holes a close leaves, which are minutes; it does not
address a two-hour sleep, because the seat that would refill before landing was
not awake to land either. Left to its own issue rather than folded in here, so
that its effect can be measured against a block where the barrier is already
gone and it is not credited with the barrier's fix.

## 7. What this study could not measure, and what would settle it

- **Thinking tokens are billed but not stored.** 187 turns carry a `thinking`
  block whose text is empty in the transcript. The contrast design routes around
  this — thinking is in every population's baseline — but no step breakdown here
  can separate "the seat thought about the brief" from "the seat wrote it".
- **`.claude/hooks/` is unreachable from a dispatched session** (#294), so the
  cohort-loop idiom could not be *prevented* mechanically, only made unnecessary.
  A seat that still writes the loop by hand gets the old behaviour. If it
  recurs, the guard belongs in a hook and the hook belongs to the orchestrator.
- **One session, one seat, four days.** The 292-minute figure is this corpus's,
  and the mechanism generalises further than the number does.

## 8. Reproducing it

```sh
# The occupancy block (§3), from the dispatch records
just occupancy --since 2026-08-09T07:13Z --until 2026-08-09T10:24Z --limit 5

# The generation figures (§2), from the orchestrator's transcript.
# Deduplicate by message.id first — see §1.
cat ~/.claude/projects/-home-andre-code-github-com-andrewesweet-arma-cti/<session>.jsonl \
  | jq -s '[.[] | select(.type=="assistant") | select(.message.usage != null)]
           | group_by(.message.id)
           | map({ot: .[0].message.usage.output_tokens,
                  disp: (any(.[] | (.message.content // [])[]
                              | select(.type=="tool_use") | (.input.command // "");
                             test("just dispatch ") and test("--issue")))})
           | {n: length, ot: (map(.ot) | add)}'
```

Refs #295, #237, #251, #258, #276, #278, #280, #284, #294, #218, #220, #232.
