# The foreign lane is rescinded, seats carry profile preferences, and no change lands alone

Delegated-decision: no
Date: 2026-08-11
Reviewed-by-human: 2026-08-11 — every decision below is a ruling the human took
in session, in a `/grill-me` interview that ran the design tree to an empty
frontier, then six further rulings answering an independent review of this
document's first draft. Nothing here was decided on their behalf.
Claimed: after `git fetch origin` (origin/main at `76d0309`, topping at
ADR-0070) and a scan of all 47 open issues' bodies and comments for an ADR
number at or above 0071, which returned nothing.
Supersedes: ADR-0061 decisions 2, 3, 4 and 6 (2026-08-06), and the quality-floor
clause of its decision 1; the human's rulings on #300 (2026-08-09), on #258 and
#217 item 9 (2026-08-06), on #220 (2026-08-05) in part, and on #242 rulings 1
and 2 (2026-08-06) in part; the Model roles mapping of 2026-08-04 and its
amendment of 2026-08-05; and the binding-decisions basis of
`docs/review-dispatch.md`.

## Why this is a decision record and not a feature

ADR-0061 was written in the multi-provider initiative's first week, when the
lanes it admitted were new and their behaviour was inference. It answered the
question it faced — *how much may we trust a provider we have not run?* — with a
provenance rule: work leaves Claude only where a mechanical gate catches a wrong
answer, and a lane's authority is graded by the enforcement it proves.

Five days and 112 dispatches later the question has changed. The lanes have run:
`claude-native` 48, `zai` 32, `codex` 32. Three retros have completed off Claude,
the most recent on `codex-sol-max`. Hook parity was proven against Codex's real
denial path for shell commands, at exit code 2, without editing a hook — though
that result was later over-generalised and file-edit payloads did require three
hook changes, which is recorded here because the same over-generalisation is
available to this ADR. The human's assessment, taken in session, is that they now
have a better handle on these providers and that the concept of a foreign lane
should be removed rather than refined.

The same session settled a second question, implicit since the first multi-agent
night: what stops a single model instance being both the author and the judge of
its own work. The answer is a review no landing escapes — which the project could
not have stated while its verification budget was governed by a rule forbidding
any additional pass.

**This document is its own first evidence for the second decision.** Its first
draft was reviewed by an independent instance on another provider, which returned
49 claims. Seven asserted that the draft stated a falsehood; all seven were
verified and all seven were correct. The draft claimed a mechanical check that did
not exist, named a constant that does not exist, asserted a deny list that is not
there, and rested a routing class on a capability restriction the code
contradicts. None of that would have been caught by any gate this project runs.

## The decision

Eight rulings.

### 1. The foreign lane is rescinded

ADR-0061 decisions 2, 3 and 4 are withdrawn, and the word *foreign* leaves the
vocabulary with them.

- **Decision 2** ("work may leave Claude iff a mechanical gate catches a wrong
  answer") is withdrawn. Eligibility is no longer a property of provenance.
- **Decision 3** (review is eligible off Claude because "a review's output is
  claims, not commits") is withdrawn as a *provenance* rule. Its factual premise
  survives — a reviewer still lands nothing — but under ruling 4 a review now
  blocks a landing, so what changes is the blast radius of a false claim, and
  eligibility no longer needs the argument at all.
- **Decision 4** (a lane's authority is graded — "all hooks proven means full
  subagent authority, some hooks missing means worktree and commit only") is
  withdrawn. There is no ladder. A lane is judged capable of a kind of work and
  has full authority for it, or it is not and does not.
- **Decision 6** (admission is an absolute bar against the existing history) is
  withdrawn by ruling 6 below, and named here because the trailer is the record.
- **Decision 1's quality-floor clause** — "anything clearing its quality floor
  goes off Claude" — is withdrawn with the floor it refers to. Decision 1's
  metering requirement is untouched. Nothing upfront replaces the floor; ruling 6
  replaces it retrospectively, and that is a deliberate loss of an ex-ante check.

**Decision 5 survives and is strengthened by the loss of its neighbours.**
Profiles remain opaque `(lane, model, effort)` tokens; no cross-provider effort
scale exists; a level joins a list by being named, never by an ordering inferred
in code. With provenance gone, Decision 5 is the only thing standing between this
project and an invented ranking of providers.

**One carve-out, and it is provisional.** The orchestrator runs on Claude Code
with a Claude model — not provenance dressed up, but a statement that the seat
deciding what everything else does should not move before a tested alternative
exists. When the Codex orchestrator backup is built, Claude becomes primary and
Codex the last resort, and the carve-out ends. Until then it is the only
provenance rule the project holds, and it holds an end condition.

### 2. Seats carry ordered profile preferences, and a dispatch names a seat

The Model roles mapping bound one `(model, effort)` pair to each seat. It is
replaced by a preference list per seat, resolved at dispatch time.

| seat | preference, head first | escalation |
|---|---|---|
| `planner` (new; absorbs `cti-implementer-xhigh`) | `codex-sol-xhigh`, `opus-xhigh` | `fable-high` |
| `implementer` | `codex-luna-max`, `zai-glm52-max`, `opus-low` | `codex-sol-high`, `opus-high` |
| `recon` (read-only) | `codex-luna-medium`, `haiku-medium` | — |
| `review` | mirrors the implementer's list | — |
| `retro` (ruling 3) | `fable-high`, `opus-xhigh`, `codex-sol-xhigh` | — |
| `orchestrator` | `opus-xhigh`; Claude only, provisional per ruling 1 | — |
| interlocutor — **not dispatched** | `opus-xhigh`, `codex-sol-xhigh` | — |

`just dispatch --seat S` resolves the first dispatchable profile, reading the
breaker and the off-peak rule as it already does, records which it chose and why,
and refuses when a whole list is unavailable. Naming a profile directly remains
possible.

**The interlocutor row is not a dispatch route.** ADR-0068 makes that seat a slash
command the human invokes in their own session, and this ADR does not reverse it.
The row governs the pair the seat's own surfaces declare, and the Codex entry is
reachable only by the human opening a Codex session by hand — which needs the twin
surface named in ruling 7, without which the fallback silently drops the seat's
instructions.

**The Codex head of `implementer` is blocked, not live.** `tools/dispatch.py`
records a measured ceiling: no `writable_roots` set lets a Codex dispatch both
commit and run the gate, and "the gate half of #265 is a recorded ceiling rather
than an open question". Under this ADR's own binary rule an implementer that
cannot run its own gate is not an implementer. So lifting that ceiling is a
**blocking prerequisite** for `codex-luna-max` heading the list — the human's
ruling — and until it lifts, the head is `zai-glm52-max` followed by `opus-low`.
The alternative considered and rejected was gating Codex's output elsewhere, which
is "capable of implementing but not of gating" — precisely the ladder ruling 1
withdrew, arrived at quietly.

Three registry lines are new: Luna at maximum effort, Luna at its published
default of medium, and Opus at low effort. **Luna enters on publication rather
than measurement**, at the human's ruling — a named exception to `AGENTS.md`'s
validated measure-before-building rule, recorded as an exception rather than
presented as consistent with it. Its catalogue entry publishes five effort levels
and describes it as a fast, affordable agentic coding model; neither adjective has
been measured in this project.

The `mechanical` seat is **retired**, and not because it would share a preference
list — `review` shares one too and is retained. It is retired because it has no
distinct *kind of work* left once implementation moves down-tier: `review` names a
different activity with a different containment requirement, and `mechanical`
named a cheaper tier rather than a different job.

**Subagents spawned by an agent's own judgement are exempt from this map**, and
accountability is not. The dispatched seat remains the accountable instance and
ruling 4 binds it whatever it spawned. One consequence is recorded rather than
discovered: an in-session subagent shares its parent's resource block and **cannot
be ledgered at all** (ADR-0066), so a dispatched implementer that delegates its
substantive work books every outcome to its own profile. Ruling 6's rankings
inherit that as a known distortion.

**#242 ruling 1's pre-registered trial is superseded in part.** Its criteria and
records judge an orchestration seat at opus/high; this map sets opus/xhigh. The
accrued records cannot validate the new pair, and the trial is either restarted
against it or closed as inconclusive — not silently continued.

### 3. Retros are their own kind of work, and they land nothing

A retro is not a tier and not an escalation. It is a category, on the ground that
improving the system of work is this project's most important task.

A retro **identifies and researches improvements and files backlog items**. It
does not edit `AGENTS.md`, `.claude/skills/` or `docs/agents/`. Each filed item
cites the run, issue or commit its finding came from, so a reader can check the
finding without a reviewer.

The `/retro` skill currently instructs the opposite — its step 3 applies approved
diffs and its step 4 appends to the process log — so **the skill rewrite is a work
item in the sequencing**, not an implication. Two of its clauses need restating in
terms of the backlog item rather than the retro commit: step 5's same-edit rule
(the count and its exemplar move together, written after two recorded violations)
and the rule that a convention lands with its first applied instance. Both assumed
the retro lands.

Never-alone does not apply to retros, because nothing lands.

### 4. No change lands alone

**No single model instance may both propose a change and approve it for landing.**

The invariant is stated in the form the design delivers, which the first draft's
did not. The proposer may land its own approved change: the risk is not the
mechanical push but the judgement that the change is fit, and the review removes
exactly that. The alternatives were the reviewer landing — which would give a
read-only instance write authority and destroy the containment that makes the
review seat safe — and the orchestrator landing everything, a serial bottleneck.

**Scope is inverted.** Every landing is reviewed except entries on a named
exemption list, each carrying its reason beside it, visible in the diff — the
shape `tools/mutation_smoke.py`'s `NO_MUTABLE_SUBJECT` uses. The list is a gate,
so under ruling 6's restatement of the conflict-of-interest class a diff touching
it can never itself be exempt. A path allowlist was rejected for failing open.

**The loop.** The implementer self-reviews against a named checklist — gates
green, acceptance criteria ticked off one by one, diff read once end to end — then
pushes a review branch. A reviewer in a different session, eligible model,
different model preferred, reviews it. The reviewer reports **everything** and
assigns each finding a severity from `docs/agents/review-severity.md`. The
implementer may dispute correctness and severity.

**The verdict names the commit it reviewed.** It records the reviewed SHA, and the
landing refuses if the SHA it is asked to land is not the one the verdict names.
Without that, an amended or rebased branch lands on an earlier approval.

**Adjudication is per finding.** Each finding receives at most one arbiter verdict
from the escalation set and is then closed; a finding raised in a later round is a
new item, not a reopening. This bounds *re-argument*, not the total number of
findings — new rounds can produce new findings, and it is the round budget below,
not per-finding closure, that guarantees termination. The first draft claimed
otherwise.

**Three rounds, then escalate, then land.** At three rounds still holding non-Low
findings, ruling 5's transferring escalation fires and an arbiter adjudicates what
remains. Only then does the pre-declared default apply: the change lands, and
every finding the arbiter left unresolved is filed as an issue on the originating
item. Escalation precedes the default rather than competing with it, which is what
makes "a review blocks a landing" true in the sense that matters — nothing lands
carrying a live unadjudicated finding. The first draft ordered these two rulings
against each other.

**Post-landing review survives**, and it needs a new basis. `docs/review-dispatch.md`
rests on ADR-0061 Decision 3 and the admission bar, both withdrawn here. Its
substance is untouched — the claims contract, the citation requirement, the
orchestrator routing — and it is re-founded on this ruling instead. Its citation
floor moves with it; nothing in this ADR replaces it and nothing removes it.

**The review seat's containment must be forced, not defaulted.** `just dispatch`
defaults `--permission-mode` to `acceptEdits`, and only `plan` maps to Codex's
`--sandbox read-only`. A review dispatched at the default can edit. Seat resolution
sets the mode for `review` rather than leaving it to the caller.

**`AGENTS.md`'s no-further-verification rule is amended, not deleted**, with
never-alone and the post-landing review seat named as its exceptions. Until that
amendment lands, an agent following the always-loaded rules would be right to
refuse this loop — so the `AGENTS.md` amendment is a sequenced work item, not a
side effect. The rule is kept because without it "one more reviewer" is an
argument available again next week, and #220's measurement has not been overturned.

### 5. Escalation has two kinds, and its conditions are data

**Consultative escalation** borrows judgement and keeps control. Claude Code's
Advisor tool is the worked example: a server-side tool consulting a stronger model
at a moment the running model chooses, returning advice rather than taking over.
Because it transfers no accountability, self-declared consultation does not drift
and needs no condition.

**Transferring escalation** hands the task to a higher profile, and fires only on
a **named condition**. The list grows only at a retro — the discipline
`.claude/hooks/deny-subagent-waits.py`'s measured denial list already runs under.

Four conditions seed it: a review cycle still holding non-Low findings after three
rounds; repeated non-convergence on one kind of item, which is evidence the item
was under-specified and should be re-planned; one clean retry with a different
profile, distinguishing a bad implementation from a bad item; and **a diagnosis of
the #181 shape**, where a plausible wrong fix would also go green — which routing
class 4 orders and which must therefore be a condition ruling 5 permits.

**The conditions live as data in a tool and reach an agent as an emission when one
fires** — not resident prose in any harness's memory file. This is #209's rule:
where a rule-table already decides, an agent is not handed numbers to reason about.
The emission mechanism is a sequenced work item; without it the conditions are
prose with extra steps.

Consultative escalation is available only on Claude Code. Codex has no Advisor
equivalent and heads four seats under this map — planner, implementer once its
ceiling lifts, recon and review — so those reach the same conditions by
re-dispatch, at the cost re-dispatch carries.

### 6. Judgement moves from an upfront bar to a retrospective observatory

`tools/admission.py`'s pre-registered bar is **dropped**, withdrawing ADR-0061
Decision 6. Its trial pre-registration harness is kept — but it is not
opinion-free, and the first draft said it was. It hard-codes
`TRIAL_BAR_ID = "cti.admission.orchestration-trial/242"`, `TRIAL_N = 10` and
orchestration-specific gated prefixes. Generalising it is work in the sequencing,
not a property it already has. The in-world surface list that `just brief` derives
the gate tier from needs a home before the module goes.

In its place, a mechanism that observes work and is read over time.

**It ranks on rework**: review rounds, escalations, arbiter invocations, dispute
outcomes, landings per issue — counts, which commensurate across providers — and
records wall-clock beside them as a duration, which is not a count and varies with
queueing and task length.

**It does not rank on spend.** Three meters — the Anthropic plan's five-hour
window, z.ai's prompt count, and Codex's absence of published terms — do not
convert into one another, and inventing a conversion would be Decision 5's error
one level up. Spend is reported per lane, beside the ranking, never inside it.

**It reports and never routes.** Nothing in it excludes a profile, reroutes work,
or trips a breaker. That is the human's ruling and not an omission: the action on
a bad ranking is a human ruling at a retro. A threshold that acted automatically
would be the upfront bar rebuilt with extra steps.

**Its attribution boundary is stated, not assumed.** The ledger is
`dispatch_only`: the orchestrator's own turns carry no dispatch id and reach no
row, and in-session subagents share their parent's resource block and cannot be
ledgered at all. Its own words are "a known under-attribution and never a complete
one". So "all work by all workers" is false; the honest claim is *all dispatched
work, attributed to the dispatched seat*.

**It stratifies on pre-work signals only** — gate tier, routing class, issue
labels — and those must be **added to the dispatch record**, which today carries
`profile`, `seat` and a `readiness_advisories` string list and none of the three.
The first draft claimed the readiness report already served. Outcome measures are
recorded beside the strata as description, explicitly marked, never used to
stratify.

**Its containment column needs a source that does not yet exist.** A bypassed hook
leaves no durable fact in the commit, and the ledger deliberately records no
command body, so the column would sit empty and be misread as evidence that
bypasses did not occur. Either the bypass is made to leave a record or the column
is not built; an empty column is worse than no column.

**Two sampling problems are recorded rather than solved.** Seat resolution always
takes the head profile, so fallback profiles accumulate observations only during
breaker incidents — systematically confounded and never numerous. And the "20 to
30 landings" figure is an **estimate, not a measurement**: no power calculation,
base rate or effect size stands behind it, and saying so is required by the same
measure-before-building rule this ADR breaks once already, in ruling 2, by name.

**The arbiter-versus-reviewer comparison is not the free measurement the first
draft claimed.** The arbiter sees only findings that were *disputed*, and sees the
reviewer's rating when it rules. That is a selected, unblinded subset; it cannot
estimate agreement across all findings, and it cannot test severity drift. A real
test needs a blind classifier over an unselected sample, which is separate work,
or the hypothesis is dropped.

### 7. Parity across harnesses is generated where there is something to generate into

Both harnesses' surfaces are generated from `tools/dispatch.py`'s registry
**wherever the target surface exists**. `tools/hook_parity.py` is the pattern:
translate, never reimplement, and refuse to emit an empty result for an event that
had one — a conditional refusal, which is narrower than "never emits empty".

Already cheap, verified in session: `AGENTS.md` and `CLAUDE.md` are one symlinked
file; Codex skills use the same `SKILL.md` convention, so skill parity is a
frontmatter translation; and `codex exec -s read-only` is the counterpart of
Claude's `plan` mode, subject to ruling 4's requirement that the mode be forced.

**Codex has no seat-definition surface**, so there is nothing to generate into and
generation is not a claim this ADR can make for both harnesses. Until such a
surface exists, a self-spawned Codex subagent's model is unenforced, and the map's
intended primary implementation lane cannot enforce the seat concept the map is
built from. Instructions in `AGENTS.md` were rejected: they fail open silently.

Two corrections to the first draft's parity section. The permission surfaces do
not compare as stated — `.claude/settings.json` carries **only** a `permissions.allow`
list and no deny list; denials are implemented by hooks, so the read-across is
between Codex's `prefix_rule` entries and this project's hooks. And the hook-trust
risk is **withdrawn**: `--dangerously-bypass-hook-trust` is already passed on every
Codex dispatch, and the code records that the flag declines to re-prompt for trust
rather than disabling hooks.

### 8. What this decision adds reaches agents by mechanism, not resident prose

`AGENTS.md` is 178 lines — inside the documented 200-line target — and 7,950 words
across 51,146 bytes, because its lines are paragraphs. Two sections are 62% of it.
Every session on every lane in every worktree loads all of it.

So the conditions are data emitted by a tool, the seat surfaces are generated, the
exemption list is a config file, and the severity anchors are a document read when
a review runs. The `AGENTS.md` amendments this ADR does require are named in the
sequencing and are corrections, not additions.

The `Supersedes:` trailer is checked by `tools/check_adr_form.py` **as of this
commit**, with three pre-convention ADRs named in a grandfather list carrying their
reasons. The first draft claimed the check while it did not exist; that the claim
survived to a reviewer is the clearest available argument for the review this ADR
introduces.

A defect found on the way and filed rather than fixed here: `AGENTS.md` names that
exemption constant `NO_PYTHON_SUBJECT`; the constant is `NO_MUTABLE_SUBJECT`. The
first draft inherited the error from the file rather than the code.

## What the rescission does not take with it

`config/dispatch-routing-policy.json` is not deleted. Its classes do not all rest
on provenance, and separating them is the substance of this ADR.

| class | disposition | why |
|---|---|---|
| 1 `gated_semantic_surfaces` | **dies as a routing rule** | its basis was provenance. The human sign-off gate on those surfaces is untouched — that gate was never this file |
| 2 `orchestration` | **survives unchanged, provisional** | ruling 1's carve-out, and the only provenance rule left |
| 3 `retros_and_adr_authorship` | **splits** | the retro half dies with ruling 3. ADR authorship survives, bound to the planner's list rather than to Claude |
| 4 `plausible_wrong_fix_goes_green` | **survives, remedy restated** | gate coverage, not provenance. Remedy becomes route-to-planner-and-escalate, and ruling 5 carries the matching condition |
| 5 `in_world_landings` | **survives** | capability — but the restriction is this project's own foreground-wait hook applying to every dispatched session, not a provider's limit. The detached runner that would lift it is not specified here |
| 6 `gates_themselves` | **survives, reframed and widened** | conflict of interest: *no instance authors the gate that judges it*. Now binds Claude too — and its path list omits `tools/hook_parity.py`, `tools/check_adr_form.py`, `tools/ledger.py` and any gate not yet written, so the list must be widened or the rule silently does not fire |
| 7 `anthropic_plan_meter` | **deleted** | its stated basis is false: `tools/breaker.py` reads the meter over plain `urllib` at a fixed URL, with no Claude session involved |

Five classes survive. Four of them — ADR authorship, the #181 shape, in-world
landings, and gates-themselves — would exist in a single-provider project. The
fifth is the provisional orchestration carve-out. That is the test this
re-founding was put to, stated as a count of what survives rather than of what
was written down.

## What this costs, stated rather than discovered

- **Never-alone doubles the instances per landing at minimum**, plus up to three
  fix rounds and per-finding arbitration. The observatory measures that cost,
  which means adoption precedes the evidence for it. A choice, not an oversight.
- **A known severe defect can land.** The pre-declared default lands the change
  after escalation and arbitration, filing whatever remains. If the arbiter is
  wrong, a Critical finding lands as an open issue rather than a block. This is
  the price of a terminus that never waits for a human.
- **Retros filing rather than landing slows process change**, and the backlog
  grows by construction.
- **Dropping the bar means a new profile enters on judgement** with no ex-ante
  check, and the observatory needs an unmeasured number of landings before it can
  contradict that judgement.
- **The Codex seat-definition gap is real and unclosed**, and Codex heads four
  seats under this map.
- **Consultative escalation is unavailable on the lane heading four seats.**
- **The implementer head is blocked on #265's ceiling**, so ruling 2's headline
  allocation is not the one that runs on the day this lands.

## What would overturn this

- **Ruling 1** — a landing wrong in a way no gate caught and the reviewer missed,
  where the cause is traced to provider behaviour. Assignment is not random and
  there is no control arm, so a single instance will not identify it; what would
  overturn the ruling is a *rate* that survives stratification, not a case.
- **Ruling 2** — a seat whose preference list never reaches past its head, making
  the list a single choice wearing a fallback.
- **Ruling 3** — process improvements that stop landing at all, measured as filed
  retro items ageing without implementation.
- **Ruling 4** — filed-but-unresolved findings accumulating faster than the loop
  prevents defects. The comparison needs a common unit that does not yet exist, so
  the honest test is the simpler one: the three-round budget being exhausted
  routinely rather than rarely.
- **Ruling 5** — consultation rates that rise without a fall in transferring
  escalations, which would mean the cheap move is being used to avoid the
  expensive one rather than instead of being stuck.
- **Ruling 6** — the containment column firing on landings the rework ranking
  rated well, or the column never being built because no bypass leaves a record,
  which would show outcome measurement cannot substitute for a gate on the axis it
  cannot see.
- **Ruling 7** — a seat surface generated for one harness and hand-maintained for
  the other drifting, which is the failure the generation was adopted to prevent.
- **Ruling 8** — `AGENTS.md` growing anyway, measured in words rather than lines.
- **The severity design** — reviewer-assigned severity falling as round number
  rises, which would mean the party holding the stop condition has an interest in
  it. Testing this needs the blind classifier ruling 6 says is separate work.

## Sequencing

1. **This ADR**, alone, with the severity anchors and the `Supersedes:` check that
   ship in the same commit. It is re-reviewed by an independent instance on
   another provider before landing.
2. **The `AGENTS.md` corrections** the rulings require: the no-further-verification
   amendment, the Model roles replacement, the withdrawn provenance rules, and the
   `NO_MUTABLE_SUBJECT` name. Until these land, an agent reading the always-loaded
   rules is following the superseded ones.
3. **The seat map** — three profiles, seat resolution with the review seat's mode
   forced, the pre-work signals added to the dispatch record, and generated seat
   surfaces where a target surface exists.
4. **The provenance removal** — the routing policy re-founded per the table above
   including class 7's deletion and class 6's widened path list; the bar dropped
   after the trial harness and the in-world list are extracted.
5. **The `/retro` skill rewrite**, restating steps 3 to 5 in terms of the backlog
   item.
6. **Never-alone** — branch exchange, SHA-bound verdict record, the landing
   refusal, the self-review checklist, per-finding adjudication, the arbiter, the
   exemption list, and its telemetry events in the same landing.
7. **The escalation-condition mechanism** — the data surface and the emission.
8. **The observatory** — the rollup, and the containment column only if a bypass
   can be made to leave a record.

The review loop is deliberately not first: it should not be the first thing to
land under a rule saying everything is reviewed, because it would have to review
itself.

Filed separately: lifting #265's gate ceiling, which blocks the Codex implementer
head; the `AGENTS.md` reduction; the Codex orchestrator backup that ends ruling
1's carve-out; the Codex seat-definition surface; the blind classifier the severity
hypothesis needs; and the detached corpus runner that would lift routing class 5.
