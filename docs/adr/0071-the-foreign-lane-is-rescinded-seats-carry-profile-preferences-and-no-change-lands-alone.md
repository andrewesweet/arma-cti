# The foreign lane is rescinded, seats carry profile preferences, and no change lands alone

Delegated-decision: no
Date: 2026-08-11
Reviewed-by-human: 2026-08-11 — every decision below is a ruling the human took
in session, in a `/grill-me` interview that ran the design tree to an empty
frontier and closed with an explicit confirmation of the consolidated statement.
Nothing here was decided on their behalf.
Claimed: after `git fetch origin` (origin/main at `76d0309`, topping at
ADR-0070) and a scan of all 47 open issues' bodies and comments for an ADR
number at or above 0071, which returned nothing.
Supersedes: ADR-0061 decisions 2, 3 and 4 (2026-08-06); the human's rulings on
#300 (2026-08-09), #258 and #217 item 9 (2026-08-06), #220 (2026-08-05) in
part, #242 ruling 2 (2026-08-06) in part; the Model roles mapping of 2026-08-04
and its amendment of 2026-08-05.

## Why this is a decision record and not a feature

ADR-0061 was written in the multi-provider initiative's first week, when the
lanes it admitted were new and their behaviour was a matter of inference. It
answered the question it faced — *how much may we trust a provider we have not
run?* — with a provenance rule: work leaves Claude only where a mechanical gate
catches a wrong answer, and a lane's authority is graded by the enforcement it
proves.

Five days and 112 dispatches later the question has changed. The lanes have run:
`claude-native` 48, `zai` 32, `codex` 32. Two retros have completed on a foreign
lane. Hook parity was proven against Codex's real denial path without a single
hook edited. The human's assessment, recorded in this session, is that they now
have a better handle on these providers' capabilities, and that the concept of a
foreign lane should be removed rather than refined.

The same session settled a second, independent question that had been implicit
in the project since the first multi-agent night: what stops a single model
instance from being both the author and the judge of its own work. The answer is
a review that no landing escapes, which the project could not have afforded to
state while its verification budget was governed by a rule forbidding any
additional pass.

Both are decisions about how work is allocated and judged, not features. This is
their record.

## The decision

Eight rulings.

### 1. The foreign lane is rescinded

ADR-0061 decisions 2, 3 and 4 are withdrawn, and the word *foreign* leaves the
vocabulary along with them.

- **Decision 2** ("work may leave Claude iff a mechanical gate catches a wrong
  answer") is withdrawn. Eligibility is no longer a property of provenance.
- **Decision 3** (review is admissible on a foreign lane because "a review lands
  nothing — its output is claims") is withdrawn twice over: the provenance
  premise is gone, and under ruling 4 below a review *blocks* a landing, so the
  stated reasoning had stopped being true regardless.
- **Decision 4** (a lane's authority is graded — "all hooks proven means full
  subagent authority, some hooks missing means worktree and commit only") is
  withdrawn. There is no ladder. A lane is judged capable of a kind of work and
  has full authority for it, or it is not and does not.

**Decision 5 survives and is strengthened by the loss of its neighbours.**
Profiles remain opaque `(lane, model, effort)` tokens; no cross-provider effort
scale exists; a level joins a list by being named and never by an ordering
inferred in code. With provenance gone, Decision 5 is the only thing standing
between this project and an invented ranking of providers.

**One carve-out, and it is provisional.** The orchestrator runs on Claude Code
with a Claude model. This is not a provenance rule dressed up: it is a statement
that the seat which decides what everything else does should not be moved before
a tested alternative exists. When the Codex orchestrator backup is built, Claude
becomes primary and Codex the last resort, and the carve-out ends. Until then it
is the only provenance rule the project holds, and it holds an end condition.

### 2. Seats carry ordered profile preferences, and a dispatch names a seat

The Model roles mapping bound one `(model, effort)` pair to each seat. It is
replaced by a preference list per seat, resolved at dispatch time.

| seat | preference (head first) | escalation |
|---|---|---|
| `planner` (new; absorbs `cti-implementer-xhigh`) | `codex-sol-xhigh`, `opus-xhigh` | `fable-high` |
| `implementer` | `codex-luna-max`, `zai-glm52-max`, `opus-low` | `codex-sol-high`, `opus-high` |
| `recon` (read-only) | `codex-luna-medium`, `haiku-medium` | — |
| `review` | mirrors the implementer's list | — |
| `retro` (see ruling 3) | `fable-high`, `opus-xhigh`, `codex-sol-xhigh` | — |
| `orchestrator` | `opus-xhigh` (Claude, provisional per ruling 1) | — |
| interlocutor | `opus-xhigh`, `codex-sol-xhigh` | — |

`just dispatch --seat S` resolves the first dispatchable profile, reading the
breaker and the off-peak rule as it already does, records **which profile it
chose and why**, and refuses when the whole list is unavailable. Naming a
profile directly remains possible; naming a seat is the ordinary path.

Three registry lines are new: `codex-luna-max`, `codex-luna-medium` and
`opus-low`. Luna enters on publication rather than on measurement, at the
human's ruling — its catalogue entry publishes `low` through `max` with a
default of `medium`, and it is described as a fast, affordable agentic coding
model.

The `mechanical` seat is **retired**. Once it shares `implementer`'s preference
list it is a second name for one choice, and the cheap tier that distinguished
it (sonnet at medium) is what this map replaces.

The seat split matters: today's `implementer` covers both working out what to do
and carrying out a detailed plan, and those belong in different places. `planner`
takes the first.

**Subagents spawned by an agent's own judgement are exempt from this map.** An
agent may spawn whatever model it judges useful. What is not exempt is
accountability: the **dispatched seat** remains the accountable instance, its
subagents' output is its own work, and ruling 4 binds it regardless of what it
spawned. Without that sentence, never-alone would be discharged by a parent
reviewing its own child.

### 3. Retros are their own kind of work, and they land nothing

A retro is not a tier and not an escalation. It is a category, on the ground
that improving the system of work is this project's most important task and
deserves its most capable instance.

A retro **identifies and researches improvements and files backlog items**. It
does not edit `CLAUDE.md`, `.claude/skills/` or `docs/agents/`. Each filed item
cites the run, issue or commit its finding came from, so a reader can check the
finding without a reviewer standing behind it.

Two consequences the `/retro` skill rewrite must handle rather than inherit.
Step 5's same-edit clause — the `×N` and its exemplar move together, written
after two recorded violations — assumed the retro lands, and the split it forbids
becomes structural once the edit happens later. So does the rule that a
convention lands with its first applied instance. Both need restating in terms
of the backlog item rather than the retro commit.

Never-alone does not apply to retros, because nothing lands.

### 4. No change lands alone

No single model instance may both propose and land a change.

**Scope is inverted.** Every landing is reviewed, except entries on a named
exemption list. Each exemption carries its reason beside it and is visible in
the diff — the shape `tools/mutation_smoke.py`'s `NO_PYTHON_SUBJECT` already
uses. The list is a gate, so under ruling 6's restatement of the conflict-of-
interest class, a diff touching the exemption list can never itself be exempt.
A path allowlist was rejected for failing open: a directory nobody thought of
would silently need no review, and a principle with holes is not this one.

**The loop.** The implementer self-reviews against a named checklist — gates
green, acceptance criteria ticked off one by one, diff read once end to end —
then pushes a review branch to `origin`. A reviewer in a different session, with
an eligible model and preferably a different one, reviews it. The reviewer
reports **everything it finds** and assigns each finding a severity of Critical,
High, Medium or Low. The implementer may dispute a finding's correctness and its
severity.

**Adjudication is per finding, not per round.** Each finding receives at most one
verdict from an arbiter drawn from the escalation set, and is then closed. This
is what makes the loop terminate by construction rather than by hope: there are
finitely many findings, each ends once, and a finding raised later is a new item
rather than a reopening. The arbiter is final; its errors are recoverable through
the post-landing review seat, which survives (below).

**The budget and its pre-declared default.** Three rounds of fixes. On
exhaustion, the action was decided in advance and is not an in-the-moment
judgement: the change lands, and every unresolved non-Low finding is filed as an
issue on the originating item. Nothing is silently dropped and nothing waits for
a human.

**The record.** The verdict lives on the issue thread; `just land` reads it and
gains a typed refusal for a landing that carries none. The exchange is a branch
pushed to `origin` — not a second agent reading a live worktree, which is #105's
shape exactly.

**Blocking prerequisite.** Critical, High, Medium and Low are four words with no
anchor. Before the first review runs, each gets a definition and one worked
example from this repository's history. Without them the loop's stop condition
means different things to instances from different model families, and the
measurement in ruling 6 would be inter-rater agreement on an undefined scale.

**Post-landing review survives.** It checks a landing against conventions, ADRs
and the close audit — *"a diff that is right and badly built, cites an ADR it
contradicts, or grows a convention sideways"* — which a diff-versus-item check
cannot see. It is also the autonomous arbiter's only appeal path.

**`CLAUDE.md`'s no-further-verification rule is amended, not deleted.** It stands,
with never-alone and the post-landing review seat named as its exceptions. The
rule is kept because without it "one more reviewer" is an argument available
again next week, and #220's measurement — that generation is the act this plan
meters — has not been overturned.

### 5. Escalation has two kinds, and its conditions are data

**Consultative escalation** borrows judgement and keeps control: ask a stronger
instance, keep the task, keep the context. Claude Code's Advisor tool is the
worked example — a server-side tool that consults a stronger model at a moment
the running model chooses, returning advice rather than taking over. Because it
does not transfer accountability, self-declared consultation does not drift and
needs no condition.

**Transferring escalation** hands the task to a higher profile. It is expensive,
it loses context, it changes who is accountable, and it fires only on a **named
condition**.

The condition list grows only at a retro, never by an agent's judgement in the
moment — the same discipline `.claude/hooks/deny-subagent-waits.py`'s measured
denial list already runs under. Its first entry: a review cycle still holding
non-Low findings after three rounds. Two more seed it: repeated non-convergence
on one kind of item, which is evidence the item was under-specified and should
be re-planned rather than re-fixed; and one clean retry with a different profile,
which distinguishes a bad implementation from a bad item.

**The conditions live as data in a tool and reach an agent as an emission when
one fires.** They are not resident prose in any harness's memory file. This is
#209's rule — where a rule-table already decides, an agent is not handed numbers
to reason about — and it is what lets the mechanism work identically on every
lane, because `just` is the command surface everywhere.

Consultative escalation is available only on Claude Code; Codex has no Advisor
equivalent. Codex-headed seats reach the same conditions by re-dispatch.

### 6. Judgement moves from an upfront bar to a retrospective observatory

`tools/admission.py`'s pre-registered bar is **dropped**. Its trial
pre-registration harness is **kept** — the two are separable, and the second has
no opinion about what is being trialled. The in-world surface list that `just
brief` derives the gate tier from needs a home before the module goes.

In its place, a mechanism that observes all work by all workers and is read over
time.

**It ranks on rework**: review rounds, escalations, arbiter invocations, dispute
outcomes, wall-clock, landings per issue. These are counts and they commensurate
across providers.

**It does not rank on spend.** Three meters — the Anthropic plan's five-hour
window, z.ai's prompt count, and Codex's absence of published terms — do not
convert into one another, and inventing a conversion would be Decision 5's error
one level up. Spend is reported per lane, beside the ranking, never inside it.

**It stratifies on pre-work signals only** — gate tier, routing class, issue
labels, the readiness report already kept on every dispatch record. Assignment is
not random: if harder issues go to one bucket, an unstratified comparison
measures the router and reads exactly like a profile finding. Outcome measures
are recorded beside the strata as description, explicitly marked, and never used
to stratify.

**It carries a containment column** — landings that bypassed `commit-msg`,
hand-edited a generated file, or modified an acceptance spec. This class is
invisible to rework rate by construction: a bypassed check produces *better*
numbers, not worse. It is a monitor and not a gate; if it never fires, that is
cheap evidence the concern was empty.

**It lives in `tools/ledger.py`** as an issue-level rollup and an aggregate view,
which fits what that module already is — a view over the OTel bus that never
writes to it. **The loop's events land with never-alone, not after it**: review
rounds leave no trace in a diff, so a loop shipped without emitting its round
count is a loop whose cost cannot be recovered.

**Its honest limit is stated in its own design**: roughly 20 to 30 landings per
profile before an escalation rate is distinguishable from noise. The first
readings will be tempting and worthless.

One property comes free. Arbiter severity against reviewer severity, per finding,
is the independent-classifier measurement the reviewer-assigns-severity design
needs — riding production, blind to nothing, with no extra apparatus. The
pre-registered hypothesis is that reviewer-assigned severity drifts downward as
round number rises; if it does not, the objection is dead and the design stands
unchanged.

### 7. Parity across harnesses is generated, not maintained

Both harness surfaces are generated from `tools/dispatch.py`'s registry, which
already holds the `(lane, model, effort)` token. The alternative — two
hand-maintained files and a check comparing them — is two sources plus a third
thing to keep current, and the interlocutor's pair is currently written in five
places for exactly that reason.

`tools/hook_parity.py` is the pattern: translate, never reimplement, and refuse
to emit an empty result where one was expected.

What is already cheap, verified in session: `AGENTS.md` and `CLAUDE.md` are one
symlinked file; Codex skills use the same `SKILL.md` convention, so skill parity
is a frontmatter translation; and `codex exec -s read-only` is the verifiable
counterpart of Claude's `plan` mode, which is what mechanically makes the review
seat unable to edit.

What is not, and is recorded as an accepted gap rather than solved: **Codex has
no seat-definition surface at all** — no `agents` directory, no config table
binding a named seat to a model and effort. Until one exists, a self-spawned
Codex subagent's model is unenforced, and this map's primary implementation lane
is the one that cannot enforce the seat concept the map is built from. Putting
the instructions in `AGENTS.md` was rejected: it fails open and says nothing,
which is how a weekly budget went once already.

Two further gaps are named without being closed here. The permission surfaces —
`.claude/settings.json`'s deny list against Codex's `prefix_rule` entries and
sandbox flags — overlap semantically and are syntactically unrelated, so a
command Claude denies has no automatic counterpart. And `codex exec` documents
`--dangerously-bypass-hook-trust`, which means Codex requires **persisted hook
trust** before enabled hooks run; whether `tools/hook_parity.py` establishes that
trust is unverified, and if it does not, the parity suite may be proving denial
in a configuration the dispatched lane does not run in. That is filed as a risk,
not asserted as a defect.

### 8. What this thread adds reaches agents by mechanism, not by resident prose

`AGENTS.md` is 178 lines — inside the documented 200-line target — and 7,950
words across 51 KB, because its lines are paragraphs. Two sections are 62% of
it. Every session on every lane in every worktree loads all of it.

So nothing this decision creates is written into it as prose. Conditions are data
emitted by a tool; seat surfaces are generated; the exemption list is a config
file; the severity anchors are a document read when a review runs. Reducing what
is already there is filed separately and sequenced after this work, on the
principle that a reduction pass should not begin by deleting what was just
written.

The `Supersedes:` field block trailer above is this decision's own first applied
instance, and `tools/check_adr_form.py` gains the check for it — so that *"tell
me every ruling that has been amended"* becomes a grep, as *"tell me every
decision made on my behalf"* already is.

## What the rescission does not take with it

`config/dispatch-routing-policy.json` is not deleted. Its seven classes do not
all rest on provenance, and separating them is the substance of this ADR rather
than an aside.

| class | disposition | why |
|---|---|---|
| 1 `gated_semantic_surfaces` | **dies as a routing rule** | its basis was provenance. The human sign-off gate on those surfaces is untouched — that gate was never this file |
| 2 `orchestration` | **survives unchanged, provisional** | ruling 1's carve-out |
| 3 `retros_and_adr_authorship` | **splits** | the retro half dies with ruling 3, since a retro lands nothing. ADR authorship survives, bound to the planner's list rather than to Claude |
| 4 `plausible_wrong_fix_goes_green` | **survives, remedy restated** | its reason was always gate coverage, not provenance. The remedy becomes route-to-planner-and-escalate |
| 5 `in_world_landings` | **survives** | capability: a dispatched session cannot run the full `just regress` corpus. True of any provider |
| 6 `gates_themselves` | **survives, reframed** | conflict of interest: *no instance authors the gate that judges it*. Reframing makes it bind Claude too |
| 7 `anthropic_plan_meter` | **survives** | instrument availability: only a Claude session can read the Anthropic meter |

Four of seven would exist in a single-provider project. That is the test this
re-founding was put to.

## What this costs, stated rather than discovered

- **Never-alone doubles the instances per landing at minimum**, and adds up to
  three fix rounds plus per-finding arbitration. The observatory is what will
  measure that cost, which means the decision to adopt precedes the evidence for
  it. This is a choice, not an oversight.
- **Retros filing rather than landing slows process change.** Each retro emits
  items that must be planned, implemented and reviewed; the backlog grows by
  construction.
- **Dropping the admission bar means a new profile enters on judgement**, and
  the observatory needs 20 to 30 landings before it can contradict that
  judgement. `codex-luna-max` becomes the implementer head with zero recorded
  runs here.
- **The Codex seat-definition gap is real and unclosed** (ruling 7).
- **Consultative escalation is unavailable on the lane that heads two seats.**

## What would overturn this

Each of these is a thing to look for, not a hypothetical.

- **Ruling 1** is overturned by a landing that is wrong in a way no gate caught
  and that the reviewer of ruling 4 also missed, traced to a provider's
  behaviour rather than to the item. That is the case provenance was protecting
  against, and it would mean the protection was load-bearing.
- **Ruling 4** is overturned by the observatory showing rework cost exceeding
  the defects the loop catches — measured in filed issues that would otherwise
  have landed. It is also weakened, short of overturned, if the three-round
  budget is exhausted routinely rather than rarely.
- **Ruling 6** is overturned by the containment column firing on landings the
  rework ranking rated well, which would show that outcome measurement cannot
  substitute for a gate on the axis it cannot see.
- **The severity design** is overturned by the pre-registered drift hypothesis
  holding: reviewer-assigned severity falling as round number rises, which would
  mean the party holding the stop condition has an interest in it and a neutral
  classifier is needed before round three.
- **Ruling 2** is weakened by a seat whose preference list never reaches past its
  head, which would mean the list is a single choice wearing a fallback.

## Sequencing

The pieces are interdependent and the order is a decision, not a convenience.

1. **This ADR**, alone. The moment `foreign` starts being deleted from 48 sites
   across 11 modules, the reasoning for which restrictions survive must already
   be written down, or it is reconstructed differently in each module. It is
   reviewed under ruling 4 by a second planner-list instance on a different
   provider, with the findings kept in its own thread as the convention's first
   worked example.
2. **The seat map** — three profiles, `--seat` resolution, generated seat
   surfaces. The only piece that delivers value before any other exists.
3. **The `foreign` removal** — the routing policy re-founded per the table above;
   the admission bar dropped after the trial harness and the in-world list are
   extracted.
4. **The severity anchors**, which block the next step.
5. **Never-alone** — branch exchange, verdict record, `just land`'s refusal, the
   self-review checklist, per-finding adjudication, the arbiter, the exemption
   list, and its telemetry events in the same landing.
6. **The observatory** — the rollup and the containment column.

The review loop is deliberately not first. It should not be the first thing to
land under a rule saying everything is reviewed, because it would have to review
itself.

Filed separately and sequenced after: the `AGENTS.md` reduction; the Codex
orchestrator backup that ends ruling 1's carve-out; and the parity work — the
Codex seat surface, the permissions read-across, and the hook-trust
verification.
