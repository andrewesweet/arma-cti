# The foreign lane is rescinded, seats carry profile preferences, and no change lands alone

Delegated-decision: no
Date: 2026-08-11
Reviewed-by-human: 2026-08-11 — signed off after five independent reviews. Every
decision below is a ruling the human took in session: a `/grill-me` interview that
ran the design tree to an empty frontier, then further rulings after each review
(49, 29, 43, 28 and 13 claims, on `codex-sol-xhigh`, `codex-sol-max` twice,
`opus-xhigh` and `fable-high`, the last scoped to the reasoning rather than the
text). The document changed substantially under each, so this line covers the
version at this commit and not merely the first draft. Nothing here was decided on
their behalf.
Claimed: after `git fetch origin` (origin/main at `76d0309`, topping at
ADR-0070) and a scan of all 47 open issues' bodies and comments for an ADR
number at or above 0071, which returned nothing.
Amended: 2026-08-15, after human review, on two rulings taken in the
decision-clearing sessions indexed on #217 and signed off there on 2026-08-15
("All approved as read", the third of four approvals). Two amendments, each
marked inline at the passage it changes — **A1** (#361, human ruling
2026-08-14) fills ruling 2's escalation column, strikes ruling 4's blanket
`fable-high` fallback and adds the conflicted-head fall-through in its place;
**A2** (#368, human ruling 2026-08-14, recorded in full on #327) re-founds the
re-founding table's class 2 row on the route's seats, which is what #327 landed
at `0c7063e`. A1 reverses one sentence of ruling 4 and fills four cells of
ruling 2's table; A2 corrects a description of code that had already moved and
reverses no decision. Both passages are human sign-off surfaces and both
rulings are that sign-off, quoted on the issues named. Every profile id and
seat list below was re-derived from `tools/dispatch.py`'s registry and every
class-2 field from `config/dispatch-routing-policy.json` as this commit's tree
carries them, never pasted from a ruling comment.
Supersedes: ADR-0061 decisions 2, 3, 4 and 6 (2026-08-06)
Supersedes: ADR-0061 decision 1's quality-floor clause (2026-08-06)
Supersedes: ADR-0009's rule that a retro *applies* the process changes it finds — the retro remains where process change originates
Supersedes: the human's ruling on #300 (2026-08-09)
Supersedes: the human's rulings on #258 and #217 item 9 (2026-08-06)
Supersedes: the human's ruling on #220 (2026-08-05), in part
Supersedes: the human's #242 rulings 1 and 2 (2026-08-06), in part
Supersedes: the Model roles mapping of 2026-08-04 and its amendment of 2026-08-05
Supersedes: the binding-decisions basis of `docs/review-dispatch.md`

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

**The two decisions are one move, and reading them as independent is what made
the second look unmotivated.** ADR-0061's answer to the ungated surface — where no
mechanical gate catches a wrong answer — was a provenance rule: keep it on Claude,
keep it on fable. Ruling 1 removes that protection. Ruling 4 supplies its
replacement. Never-alone is not primarily a quality tax on gated code; it is
**what makes rescinding provenance defensible**, and it earns that on exactly the
surface provenance used to guard.

**This document is its own evidence, and only for that half.** Five independent
reviews — on `codex-sol-xhigh`, `codex-sol-max` twice, `opus-xhigh` and
`fable-high` — returned 49, 29, 43, 28 and 13 claims. Seven of the first round's
asserted the draft stated a falsehood; all seven were verified and all seven were
correct. The draft claimed a mechanical check that did not exist, named a constant
that does not, asserted a deny list that is not there, and rested a routing class
on a capability the code contradicts. No gate this project runs would have caught
any of it.

But that evidence is from reviews of **ungated semantic prose**, and the
elimination-context rule applies to this ADR as readily as to anything else. So
the ruling is scoped to what the evidence supports:

- On **ungated surfaces** — ADRs, specs, conventions, planning, retro findings —
  never-alone is evidenced, by this document's own history.
- On **gated code** it is adopted on judgement, and the question is
  **pre-registered rather than assumed**: does pre-landing review of gated work
  find defects that the gates and post-landing review would not have? Post-landing
  findings on landings that passed pre-landing review are the observable, and
  ruling 6 records them. If the answer is no, the exemption list of ruling 4 is
  where that goes — which is what turns that list from a hole into the mechanism
  by which this rule shrinks on evidence.

**The admission bar is abandoned deliberately, and this is the departure.**
ADR-0061 Decision 6 pre-registered that bar so that observed lane behaviour could
not move it, and its own amendment A7 records all 24 routes on probation with none
admitted — **the bar never adjudicated once**. Dropping it after 112 dispatches is
the move pre-registration exists to prevent, taken knowingly by the human's ruling
rather than arrived at without noticing. What is being traded is an ex-ante check
that never ran for a retrospective one that cannot run yet.

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
  blocks a landing, and **the asymmetry it rested on inverts**. Decision 3 argued
  that a review's false positives are checkable and its false negatives merely
  cost an uncaught advisory finding. Once the verdict is the gate, a false
  negative is a defect that lands *with a clean review attached*, silently and
  with reach — a High by this project's own anchor. That is the cost of promoting
  review from advice to gate, and it falls on the side Decision 3 called safe.
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

**That end condition will be reached with no observation behind it**, and the two
rulings that produce this should be read together rather than apart. The
orchestrator is the one seat provenance still protects, and it is also the one
seat ruling 6 structurally cannot see — its turns carry no dispatch id and reach
no ledger row. So when the backup exists, the decision to end the carve-out is
another judgement call, made on exactly as much evidence as this one. Saying so
now is cheaper than discovering it then.

### 2. Seats carry ordered profile preferences, and a dispatch names a seat

The Model roles mapping bound one `(model, effort)` pair to each seat. It is
replaced by a preference list per seat, resolved at dispatch time.

| seat | preference, head first | escalation |
|---|---|---|
| `planner` (new; absorbs `cti-implementer-xhigh`) | `codex-sol-xhigh`, `opus-xhigh` | `fable-high` |
| `implementer` | `codex-luna-max`, `zai-glm52-max`, `opus-low` | `codex-sol-high`, `opus-high` |
| `recon` (read-only) | `codex-luna-medium`, `haiku-medium` | — never escalates (A1) |
| `review` | the implementer's list, resolved to the first profile that is **not** the one being reviewed, preferring a different lane | the implementer's escalation head |
| `retro` (ruling 3) | `fable-high`, `opus-xhigh`, `codex-sol-xhigh` | `opus-max`, `fable-max` (A1) |
| `orchestrator` | `opus-xhigh`; Claude only, provisional per ruling 1 | `opus-max`, `fable-xhigh` (A1) |
| interlocutor — **not dispatched** | `opus-xhigh`, `codex-sol-xhigh` | — not dispatched (A1) |

*(Amendment A1, 2026-08-15, on the human's ruling of 2026-08-14 recorded at
#361: the escalation column had four empty cells, and the question put was
whether an arbiter should be **derived** with exclusions or **tabled**. The
answer was to table it — "amend ruling 2's table, give every seat an entry" —
data rather than logic, and the answer readable in one table rather than
computed. Asked which cells, the human ruled "retro and orchestrator only".*

*`retro`'s entry is drawn from the nine profiles the human approved for retros
on 2026-08-09 (#300): arbitrating a retro is retro work, and taking the arbiter
from outside that list would widen that allowance by the back door. It
deliberately excludes `fable-high`, which is this seat's own preference head and
therefore the profile most likely to be conflicted. `orchestrator`'s entry
deliberately excludes `opus-xhigh`, which is the seat itself. Both entries hold
two profiles, head first, matching ruling 4's "*Head*, because those entries
hold two profiles".*

*`recon` and the interlocutor are marked not-applicable rather than given
profiles, because neither can produce the thing an arbiter adjudicates: `recon`
is read-only and lands nothing, so no never-alone loop runs over its output, and
this ruling states plainly that the interlocutor row is not a dispatch route.
Marked, not left blank — after ruling 4's blanket fallback is struck below, an
empty cell is a refusal, so "no entry" and "never needs one" had to stop looking
the same.*

*One seat `tools/dispatch.py` registers is deliberately absent from this table
and stays absent: `fable`, whose preference is `fable-high` alone. Ruling 3
hands retros to `retro` without deleting it, and closing that overlap is #329's
and #330's, not this amendment's — so under the struck fallback the `fable` seat
has no arbiter and an escalation from it refuses, which is the accepted
consequence recorded in ruling 4 rather than an oversight here.)*

`just dispatch --seat S` resolves the first dispatchable profile, reading the
breaker and the off-peak rule as it already does, records which it chose and why,
and refuses when a whole list is unavailable. Naming a profile directly remains
possible — and **a refusal attaches to a `(profile, seat)` pair, not to the
resolution path**, so `--profile` is a way of choosing, never a way around. The
pair matters: a profile blocked for a seat that must commit and gate is not
thereby blocked for a read-only seat that does neither.

**The interlocutor row is not a dispatch route.** ADR-0068 makes that seat a slash
command the human invokes in their own session, and this ADR does not reverse it.
The row governs the pair the seat's own surfaces declare, and the Codex entry is
reachable only by the human opening a Codex session by hand — which needs the twin
surface named in ruling 7, without which the fallback silently drops the seat's
instructions.

**The planner does not gate or land**, and the seat table's "absorbs
`cti-implementer-xhigh`" means it inherits that seat's *tier*, not its contract.
A planner works out what to do; an implementer carries it out, gates it and lands
it. So the ceiling below does not reach the planner head. This is spelled out
because the second review read the absorption as inheriting the whole contract,
which the text permitted.

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

**On `recon` that exception has no expiry, and the ADR should say so.** The
implementer head is at least gated and ranked once #265 lifts. `recon` is
read-only, so no gate reads its output; it lands nothing, so ruling 6 never ranks
it; and the admission bar that would have judged it is dropped. Nothing in this
design will ever check that profile — and recon output is what an orchestrator
routes on, so a wrong answer there propagates into decisions rather than into a
diff. The mitigation available is cheap and is adopted: **a recon claim that
decides a routing choice is cited**, so the orchestrator can check the citation
rather than trust the summary. That is the same move ruling 3 makes for retro
findings, for the same reason.

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
accrued records cannot validate the new pair, so **the trial is closed as
inconclusive** and its records kept as history. Closing it is a step in the
sequencing, not a later choice for whoever notices.

It is closed rather than restarted, and **not** because the observatory replaces
it — that claim was made in the third draft and is withdrawn. The trial measures
five orchestration-process criteria, among them honouring a freeze and refusing to
treat `quota_exhausted` as a result; the observatory measures rework and sees none
of them. What is being accepted is that those five criteria go unmeasured, which
is a loss, not a substitution.

### 3. Retros are their own kind of work, and they land nothing

A retro is not a tier and not an escalation. It is a category, on the ground that
improving the system of work is this project's most important task — and that
ground supports the *category*, not the prohibition. The prohibition rests on a
different reason, which the third draft left unstated: **finding and implementing
are different jobs**, and a retro that lands its own findings is the
propose-and-approve shape ruling 4 forbids everywhere else. ADR-0009's assignment
of process change to retros survives; what is withdrawn is the retro *applying*
what it finds.

A retro **identifies and researches improvements and files backlog items**. It
lands nothing — stated as the rule, not as a list of surfaces, because the third
draft's list named `AGENTS.md`, `.claude/skills/` and `docs/agents/` and thereby
left `docs/process-log.md`, `CONTEXT.md` and `docs/adr/` unprohibited, all three
of which retros have landed. Each filed item cites the run, issue or commit its
finding came from, so a reader can check the finding without a reviewer.

One consequence to settle in the skill rewrite rather than leave implied: the
retro journal in `docs/process-log.md` is itself a landing. Either the journal
entry becomes one of the filed items, or the journal is the single named
exception to "lands nothing" — and that choice belongs in the rewrite with its
reason, not here as an omission.

The `/retro` skill currently instructs the opposite — its step 3 applies approved
diffs and its step 4 appends to the process log — so **the skill rewrite is a work
item in the sequencing**, not an implication. Two of its clauses need restating in
terms of the backlog item rather than the retro commit: step 5's same-edit rule
(the count and its exemplar move together, written after two recorded violations)
and the rule that a convention lands with its first applied instance. Both assumed
the retro lands.

Never-alone does not apply to retros, because nothing lands.

### 4. No change lands alone

**No single model instance may both propose a change and produce the review
verdict that clears it.**

Three roles, because the first two drafts collapsed them and the invariant kept
escaping as a result. The **proposer** authors the change. The **reviewer**
produces the verdict — the judgement that the change is fit, with its findings and
severities. The **lander** executes `just land`; it decides nothing, and it may be
the proposer. The first draft said "propose and land", which forbade the wrong
act; the second said "propose and approve", which named the right act and then
specified a refusal that could not tell who had performed it.

**The enforcement is derived, not declared, and its reach is narrower than the
invariant.** A verdict that merely *states* a reviewing dispatch id is data the
proposer controls: it can paste any real id, and where authorship spans two
dispatches — a recovery amending a branch — the branch's own id is the second
one, so the first can review its own work and the strings differ. Two rounds of
review found both holes.

So `just land` does not read a claimed id. It requires that a **review dispatch
record exists** for the SHA being landed, under `~/.arma-cti/dispatches/`, whose
seat is `review` and whose recorded end state is a completed run; that its id is
absent from the dispatches that authored the branch; and — the part the fourth
review found missing — that **every finding that run reported above Low carries an
adjudication**, whether the implementer's accepted fix, a dispute the arbiter
ruled on, or an arbiter dismissal. The record is written by the dispatcher, not by
the reviewed agent.

Without that last clause the refusal asked only whether a review *happened*. A
proposer could dispatch a review, receive a Critical, do nothing, and land — no
forgery, every check satisfied, and the stop condition "nothing above Low remains
unadjudicated" enforced nowhere.

**What this cannot do, stated plainly.** Every dispatch runs as the same user, so
an agent determined to forge an evidence directory can. This is the same limit the
credentials design already records — it protects against the accident and the
shortcut, not against a deceptive agent. The invariant is therefore a **convention
with a mechanical floor**, not a guarantee, and calling it more than that is what
the first three drafts did.

The alternatives were the reviewer landing, which would give a read-only instance
write authority and destroy the containment that makes the review seat safe; the
orchestrator landing everything, a serial bottleneck; and using the tracker's
actor as the identity oracle, which fails because every dispatch runs as the same
user.

**Scope is inverted.** Every landing is reviewed except entries on a named
exemption list, each carrying its reason beside it, visible in the diff — the
shape `tools/mutation_smoke.py`'s `NO_MUTABLE_SUBJECT` uses. The list is a gate,
so under **routing class 6**'s restatement below — no instance authors the gate
that judges it — a diff touching it can never itself be exempt. A path allowlist
was rejected for failing open.

**The loop.** The implementer self-reviews against a named checklist — gates
green, acceptance criteria ticked off one by one, diff read once end to end — then
pushes a review branch. A reviewer in a different session, eligible model,
different model preferred, reviews it. The reviewer reports **everything** and
assigns each finding a severity from `docs/agents/review-severity.md`. The
implementer may dispute correctness and severity.

**The verdict names the commit it reviewed.** It records the reviewed SHA, and the
landing refuses if the SHA it is asked to land is not the one the verdict names.
Without that, an amended or rebased branch lands on an earlier approval.

**The arbiter is the head of the implementing seat's escalation entry** — a
function of the work, not of who happened to review it, using a column the seat
table already has, and keeping arbitration proportional to the tier the work was
done at. *Head*, because those entries hold two profiles and "the escalation
entry" would have left the same ambiguity as "the escalation set" it replaced:
two callers, two arbiters, one finding. *(Amendment A1, 2026-08-15: "the
implementer's seat's" read as the `implementer` row specifically, which would
have made every other row's entry unreachable — including the `retro` entry the
same amendment adds, on the case that prompted it. The seat meant is whichever
one did the work, which is what "a function of the work" already says.)*

**Where the tabled head is a profile the work's own records place on it, the
tool falls through the seat's preference list.** It walks that list to the first
profile no dispatch record places on the work, **records what it excluded and
why**, and **refuses by name** when the list is exhausted rather than defaulting
to a profile nobody chose. Two properties carry over from `--reviewing`'s
resolution and carry into the implementation with it: dispatch records are a
*potential*-author set and never proof, since nothing on a record names the
commits a run produced; and where a record could not be read, the route is
marked unchecked while everything read is still excluded.

**The blanket fallback is struck.** It read: *"A seat whose escalation column is
empty arbitrates at `fable-high`."*

*(Amendment A1, 2026-08-15, on the human's ruling of 2026-08-14 recorded at
#361, which also fills ruling 2's table above. The struck sentence cited the
`orchestrator` and `recon` rows as its motivating cases, and its stated worry —
that the loop would have no terminus for the seat that runs it — is answered by
the table now naming that seat's arbiter outright.*

*What the sentence actually did on the case that exercised it is the reason it
went. This issue was filed believing the retro seat had no head to take; it had
one, because the rule was general and the retro row's column was empty. The real
defect was worse: `fable-high` authored every round of retro 30, so the ADR's own
default resolved to **the proposer**. The orchestrator silently declined a
default that would have had the author arbitrate its own work and substituted
`opus-max` by hand — an instance inventing a rule at the moment the rule was
needed, on an escalation against the orchestrator's own instruction. So the gap
was never a missing table cell; it was that arbitration carried no
conflict-of-interest exclusion where `--reviewing` resolution already had one.
The fall-through above is that exclusion. Applied to #318 it would have resolved
the retro seat to `codex-sol-xhigh` — `fable-high` authored, `opus-xhigh`
reviewed — rather than to the `opus-max` chosen by hand; neither is obviously
right, and the point of the rule is that the choice stops being made in the
moment by the party under review.*

*With every dispatchable row filled, the sentence covered only cells marked
not-applicable, and keeping it would have put two rules that can disagree in one
document — a blanket `fable-high` beside a retro entry that deliberately avoids
`fable-high`. **Consequence accepted at the time of ruling: a seat added later
with no escalation entry resolves to nothing and refuses.** That is the correct
failure under #361's own acceptance criterion, and it means adding a seat now
requires deciding its arbiter.)*

**And the reviewer must not be the reviewed profile.** The `review` seat resolves
down the implementer's list to the first profile that is not the one under review,
preferring a different lane. Without that rule both seats resolve to the same head
and every review is same-model — which would make never-alone a ritual, since the
whole argument for it, and every finding in this document's own four reviews,
rests on the second instance being genuinely different. "Different model
preferred" was a word nothing read.

**Adjudication is per finding.** Each finding receives at most one arbiter verdict
and is then closed; a finding raised in a later round is a
new item, not a reopening. This bounds *re-argument*, not the total number of
findings — new rounds can produce new findings, and it is the round budget below,
not per-finding closure, that guarantees termination. The first draft claimed
otherwise.

**Three fix rounds, then escalate, then land.** A round is one *fix-and-re-review*
cycle; the first review is round zero, so escalation fires after the third
re-review — four reviews in total. The count is stated because "three rounds" was
ambiguous by one and a tool has to decide it.

At that point ruling 5's transferring escalation fires and an arbiter adjudicates
what remains. Only then does the pre-declared default apply: the change lands, and
**every finding the arbiter did not dismiss is filed as an issue** on the
originating item — not only the ones it left unresolved. An upheld Critical is
closed by the arbiter's verdict, so a rule that filed only the unresolved would
lose exactly the finding that most needs a trace.

**And every dismissal is recorded and handed to post-landing review.** The
landing's record carries each finding above Low with its verdict — fixed, upheld
or dismissed — and the dismissals go to the post-landing seat as an input beside
the SHA and the close audit. Dismissals stay on the issue thread rather than
becoming issues, so this adds no tracker noise and no pass.

The reason is that without it this ADR retains a rule against the #181 shape while
manufacturing a fresh instance of it. An arbiter wrongly dismissing a real
Critical is precisely a plausible wrong answer going green with nothing downstream
firing — routing class 4's definition. It is also the case where this document
claims post-landing review is the appeal path, a claim that was **empty** until
now, because that seat reviews a diff and had no way to learn what had been
dismissed. This does not make the arbiter safe. It converts an invisible loss into
a delayed and visible one, which is an improvement and not a fix. Escalation precedes the default rather than competing with it, which is what
makes "a review blocks a landing" true in the sense that matters — nothing lands
carrying a live unadjudicated finding. The first draft ordered these two rulings
against each other.

**Post-landing review survives**, and it needs a new basis and a new destination.
`docs/review-dispatch.md` rests on ADR-0061 Decision 3 and the admission bar, both
withdrawn here, and it does more than cite them: its closing section routes a
confirmed finding *into* the bar as an `unclean` reason, and accounts the
reviewer's own dispatch against a per-profile citation floor held there. Removing
the bar therefore removes two live operations, not two references. Both move to
the observatory of ruling 6 — a confirmed post-landing finding becomes a rework
observation on the reviewed profile, and the citation floor becomes a reported
column on the reviewing one. That rehoming is a step in the sequencing. The claims
contract, the citation requirement and the orchestrator's routing are untouched.

**The review seat's containment must be forced, not defaulted.** `just dispatch`
defaults `--permission-mode` to `acceptEdits`, which is writable, so a review
dispatched at the default can edit. Seat resolution sets the mode for `review`
rather than leaving it to the caller. (On the Codex lane both `plan` and `default`
map to `--sandbox read-only`; the writable default is the argument parser's, not
the sandbox mapping's — see ruling 7.)

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

Four conditions seed it, each stated as something a tool can decide rather than
something an agent judges — which is what "data" means here and what the first
draft's wording did not deliver:

- a review cycle holding a finding above Low after three fix rounds;
- **two** consecutive items sharing a routing class each reaching that same
  three-round state, which is evidence the *items* are under-specified and the
  next one is re-planned rather than re-fixed;
- an item whose second implementation attempt, from a clean base on a different
  profile, itself reaches the three-round state — the *retry's outcome*, which is
  what distinguishes a bad implementation from a bad item. The third draft made
  the retry itself the condition, which fires only after the transfer it was meant
  to trigger and tells nobody anything;
- an issue declaring routing class 4, the #181 shape, where a plausible wrong fix
  would also go green — which that class's remedy orders and which must therefore
  be a condition this ruling permits.

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

**It reports rework, and ranks on one primary key.** The measures are review
rounds, escalations, arbiter invocations, dispute outcomes and landings per issue
— counts, which commensurate across providers — plus wall-clock beside them as a
duration, which is not a count and varies with queueing and task length. Five
dimensions do not order themselves: a profile with two rounds and no escalation
against one with one round and one escalation has no winner without a conversion,
and inventing one is Decision 5's error again. So **fix rounds per landing is the
ranking key** and everything else is reported beside it, unranked. A different key
is a ruling, not a preference.

The key is defined only where its denominator exists: it ranks **profiles in the
`implementer` seat**, the only seat this map leaves that reaches `just land`
— `mechanical` is retired by ruling 2 and naming it here was a leftover. A
profile with no landings has no ranking, not a ranking of infinity, and `review`,
`recon`, `planner` and `retro` land nothing by contract. Their rework is reported,
never ranked. An implementer whose work never lands is a zero denominator too, and
shows as an unranked row with its rounds visible rather than as a division.

**What the key attributes and what causes it are not the same**, and this is a
second known distortion beside the subagent one. Rounds are booked to the
implementer profile, while this ADR's own second escalation condition says a
repeated three-round state is evidence the *item* was under-specified — caused
upstream, by planning. So a profile paired with a weak planner ranks badly for
someone else's defect. Stratifying on routing class and gate tier helps and does
not solve it, and apportioning rework between implementer and planner would be
exactly the conversion Decision 5 forbids. The key is therefore read as **where
rework appears**, never as who caused it.

**And what it can never measure is never-alone's benefit.** Rounds, escalations
and instances are costs; defects-prevented has no counterfactual and no control
arm, so the loop's value is not an observable in general. The one narrower
question that *is* observable is the one pre-registered above — post-landing
findings on landings that passed pre-landing review — and it is the only evidence
this design will ever produce about whether the loop earns its cost on gated code.

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
translate, never reimplement.

**It has no refusal at all**, and three drafts said otherwise in three different
ways. `translate` contains no `raise` and no error return; an event whose entries
are all dropped is skipped by `if not rows: continue`, so an event carrying only
unsupported types, an event with a malformed group, and an event absent from
settings are indistinguishable — all three yield an empty result silently. The
module's own docstring claims the refusal and the code does not implement it. So
the pattern being adopted here is "translate, never reimplement", and nothing
more; the floor it was credited with is filed as a defect, and a generated surface
built on it inherits fail-open silence until that is fixed.

Already cheap, verified in session: `AGENTS.md` and `CLAUDE.md` are one symlinked
file; Codex skills use the same `SKILL.md` convention, so skill parity is a
frontmatter translation; and `codex exec -s read-only` is the counterpart of
Claude's `plan` mode. On the Codex lane both `plan` **and** `default` already map
to `--sandbox read-only` — the third draft said only `plan` did — but the argument
parser's own default is `acceptEdits`, which is writable, so ruling 4's
requirement that the review seat's mode be *forced* stands unchanged.

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
commit**, and the check's own history is the argument for this ADR's ruling 4. The
first draft claimed the check while it did not exist. The second landed it with a
`rescind|supersede` detector that missed every one of this ADR's four principal
withdrawals — because they say "withdrawn" — so it fired on one incidental
sentence and looked like it worked, and its anti-vacuity test passed on that
sentence. It also carried a three-entry grandfather list described as complete
which was in fact the three ADRs the narrow detector happened to see; twenty
earlier ADRs amend or supersede a ruling in their prose. Two independent reviews
found those, in sequence. No gate this project runs could have.

A third draft widened the verbs and added a negation guard, and a third review
defeated that too: "deleted" — which this ADR itself uses for routing class 7 —
"dropped", "overturned" and "retired" were all outside the list; *"the Model roles
mapping is replaced"* matched no governance noun; a wrapped line separated the two
words it needed together; and *"withdrawn without changing decision 5"* was
discarded by the negation guard as an operative withdrawal.

**So the trigger is gone.** Every ADR from 0071 carries a `Supersedes:` line —
one per superseded ruling, or the single line `Supersedes: none`. Nothing infers
intent from prose, because three attempts established that a regex cannot. The
cost is one line per future ADR; the gain is a check with no vocabulary to miss,
no wrapping to break on, and no negation to invert. One line per target rather
than a wrapped list, because the promise is that `rg '^Supersedes:'` returns the
amended set, and a continuation line answers no such grep.

The **cutoff at 0071** replaced a named grandfather list for a reason worth
keeping: a named list names exceptions to a rule that otherwise applies, and here
the rule did not exist yet. Its known gap is stated in the code — an ADR below the
cutoff that is later amended to withdraw something is not covered, and closing
that would mean reading git history in a form check.

**What this trades, said plainly.** The check now verifies a *declaration*, not a
fact. An ADR that withdraws a ruling in its body and writes `Supersedes: none`
passes, and `rg '^Supersedes:'` then returns a lie. The previous versions at least
attempted to notice that, and failed at it in four different ways. So the promise
is narrower than "the grep returns the amended set": it returns **what each ADR
declared**, and a false declaration is caught at human review or not at all. That
is a worse guarantee honestly stated, in place of a better one that did not work.

`AGENTS.md` also names that exemption constant `NO_PYTHON_SUBJECT` where the code
says `NO_MUTABLE_SUBJECT`; the tool's own documentation said it twice and is
corrected in this commit. `AGENTS.md` is a sign-off surface, so its copy is filed
rather than fixed here.

## What the rescission does not take with it

`config/dispatch-routing-policy.json` is not deleted. Its classes do not all rest
on provenance, and separating them is the substance of this ADR.

| class | disposition | why |
|---|---|---|
| 1 `gated_semantic_surfaces` | **dies as a routing rule, except two paths that move to class 6** | its basis was provenance, and the human sign-off gate on those surfaces is untouched — that gate was never this file. But `.claude/hooks/` and `.claude/settings.json` are the denial layer and the permission allowlist, i.e. **gates**, and class 1's list was the only routing rule naming them. Deleting the class outright would let an instance author the hook that judges it with nothing firing, so both paths move to class 6 rather than falling out |
| 2 `orchestration` | **survives, re-founded on the route's seats** *(Amendment A2)* | it carries no lane rule at all. Its `required_seats` are `orchestrator`, `planner`, `implementer`, `review` and `recon` — the route that finishes orchestration work — and it refuses `retro` and `fable` on **every** lane, Claude's included, where the row this table originally described refused every seat off Claude and no seat on it. **This row is not ruling 1's carve-out and not a provenance rule.** That carve-out is `orchestrator_claude_only` in `tools/dispatch.py`'s seat table; the policy's own surviving keep-on-Claude bar is class 6's, below. See the A2 note under this table for what forced the shape, and for the two alternatives the human declined |
| 3 `retros_and_adr_authorship` | **splits, and the survivor needs a path it does not have** | the retro half dies with ruling 3. ADR authorship survives, bound to the planner's list rather than to Claude — but the class's only `landing_path_prefixes` entry is `docs/process-log.md`, which belongs to the half being killed, so the surviving half would enforce on issue phrases alone. It gains `docs/adr/` as its landing path, or it is a class that catches nothing |
| 4 `plausible_wrong_fix_goes_green` | **survives, remedy restated** | gate coverage, not provenance. Remedy becomes route-to-planner-and-escalate, and ruling 5 carries the matching condition |
| 5 `in_world_landings` | **narrowed to a subagent rule** | a *subagent* cannot hold the corpus's foreground wait, so a seat reached that way cannot gate its own in-world work. `just dispatch` already launches a **top-level** session, which the wait hook permits — it returns 0 where there is no `agent_id` — so the class does not restrict the dispatch route this ADR defines, and two drafts said it did. What remains is a real but much smaller rule about subagents |
| 6 `gates_themselves` | **survives, reframed, and does not yet hold** | conflict of interest: *no instance authors the gate that judges it*. Now binds Claude too, and takes class 1's two gate paths. Enforcement is a hard-coded path list and its coverage is far worse than the third draft admitted: of the seven gate tools `just check` runs it names **one**, `tools/mutation_smoke.py`; it omits `tools/check_adr_form.py` — **which this commit adds and then uses to judge the ADR in the same commit** — along with `check_seat_config`, `check_validated_markers`, `check_conflict_markers`, `check_source_symlink`, `export_command_schema`, `tools/breaker.py`, and the exemption list step 7 creates. Deriving the list from `just check` alone would still miss gates under `just unit`, `just mutation`, `just land` and `just regress`, so that filed item is stated as insufficient rather than as the fix. **The class is aspirational: today it names six paths and the invariant it asserts is not enforced.** |
| 7 `anthropic_plan_meter` | **deleted** | its basis does not hold. The class's own paths are `tools/quota_tap.sh` and a usage fixture, and the meter itself is read by `tools/breaker.py` over plain `urllib` at a fixed URL with no Claude session involved. `quota_tap.sh` is a Claude Code status-line integration, which is a reason to keep it working on Claude, not a routing rule about who may author it |

*(Amendment A2, 2026-08-15, on the human's ruling of 2026-08-14 recorded in full
at #327 and filed as #368. The question put was how the ADR and the code stop
contradicting each other, against four resolutions. **Answer: amend the ADR; the
code stays as landed.** Widening class 2 further, and deleting it outright, were
both put and both declined — recorded here so the question is not re-litigated.*

*The row's shape was forced by two of this ADR's own landed rulings rather than
chosen by an implementer. **Ruling 2** puts the planner outside gating and
landing; **ruling 4** requires a reviewing instance. Against those, the one-seat
row #327's second round wrote left an orchestration issue plannable by nobody,
landable by nobody and reviewable by nobody — the deadlock its third round hit,
with **#331** the concrete casualty, since that issue's body carries
`Routing-class: orchestration` and could have been dispatched only to the one
seat that must not review its own landing. `recon` joined on the ground that a
seat which authors, lands and reviews nothing cannot take the work, so refusing
it protected nothing while barring a cheap read-only sweep.*

*Two arguments were put to the human against keeping the row at all and were not
taken; they belong here rather than being lost. The row's remaining selection is
**thin** — it refuses `retro` and `fable` and nothing else — and the policy's own
remedy says so. And it **conflicts with a live instruction**: `AGENTS.md`'s Model
roles paragraph sends process docs to a `fable` seat, and
`docs/agents/orchestration.md` is a process doc by `AGENTS.md`'s own Orchestration
seat section, so this row refuses to route that file where that paragraph sends
it. Closing that overlap is #329's and #330's; until one lands, the conflict
stands on the record.*

*What this costs the paragraph below: the original counted five survivors and
called the fifth a provenance carve-out, which this row is no longer. The count
is unchanged and its reading is not.)*

Five classes survive, and **all five would exist in a single-provider project** —
ADR authorship, the #181 shape, in-world landings, gates-themselves, and
orchestration, now founded on which seats can finish the work rather than on
which lane may take it. That is the test this re-founding was put to, stated as a
count of what survives rather than of what was written down. The one lane-selected
refusal the policy still carries is class 6's keep-on-Claude bar, which is a rule
about the gates rather than a class resting on provenance, and it is kept only
until #331's exemption list gives that row's invariant an enforcement of its own.

## What this costs, stated rather than discovered

- **Never-alone doubles the instances per landing at minimum**, plus up to three
  fix rounds and per-finding arbitration. The observatory measures that cost,
  which means adoption precedes the evidence for it. A choice, not an oversight.
- **A known severe defect can land, and an unknown one can land silently.** The
  pre-declared default lands the change after escalation and arbitration, filing
  whatever the arbiter left unresolved. Two different losses sit here. A finding
  the arbiter leaves open lands as a tracked issue — visible. A real Critical the
  arbiter *rejects* is closed, not filed, so it lands with no trace at all; the
  only remaining catch is the post-landing review seat. That is the price of a
  terminus that never waits for a human, and it is why post-landing review is
  retained rather than absorbed.
- **Retros filing rather than landing slows process change**, and the backlog
  grows by construction.
- **Dropping the bar means a new profile enters on judgement** with no ex-ante
  check, and the observatory needs an unmeasured number of landings before it can
  contradict that judgement.
- **Two lanes cannot enforce something this map requires, and only one of them
  blocks anything.** The gate ceiling makes the Codex implementer head a blocking
  prerequisite; the missing seat-definition surface — whose failure mode is
  *silent tier inheritance*, the one that consumed the bulk of a weekly budget on
  2026-08-04 — blocks nothing and is merely recorded. The inconsistency is
  deliberate: the ceiling is falsifiable by running a gate, while the seat gap is
  visible only in a bill, so blocking on it would stop the lane indefinitely with
  no test that could clear it. That is a reason, not a justification, and it is
  the weakest place in ruling 1's binary rule.
- **Consultative escalation is unavailable on the lane heading four seats.**
- **The implementer head is blocked on #265's ceiling**, so ruling 2's headline
  allocation is not the one that runs on the day this lands.

## What would overturn this

- **Ruling 1 is not falsifiable at this project's scale, and that is stated rather
  than dressed up.** The obvious falsifier — a rate of provider-caused defects
  that survives stratification — cannot be obtained: ADR-0061 Decision 6 recorded,
  with figures, that lane-level marginal effects are not estimable here, ever, on
  arm count alone (RouteLLM needed 65,000 comparisons). Withdrawing that decision
  does not make the arithmetic false. So this ruling rests on the human's
  judgement, checked by cases rather than by rates: a landing wrong in a way no
  gate caught and no reviewer found, traced to provider behaviour, is a reason to
  re-open it — one such case, not a significant one. Calling that statistical
  evidence would be self-sealing, which ADR-0019 exists to prevent.
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

**Every step below is reviewed by an independent instance before it lands**, from
step 1 onward, honoured by procedure until step 7 makes it a refusal.

**The interval is a period of stated inconsistency, not a clean transition**, and
pretending otherwise would be the "two rules that cannot both be followed" this
project rates High. From step 1 the trailer withdraws ADR-0061's decisions and
ruling 4 binds; until step 5 `AGENTS.md` still forbids the loop, so an agent
reading the always-loaded rules would be right to refuse it; until step 7 no
refusal enforces it; the admission bar dies at step 4 and the observatory replacing
it arrives at step 8. For that window the project runs on the new rules by
agreement and the old ones by machinery, and the reconciliation is that **a human
is sequencing these landings deliberately** rather than agents discovering the
conflict one at a time. If that ceases to be true — if the steps are dispatched
concurrently or the sequence stalls part-way — the window stops being a transition
and becomes the defect.

1. **This ADR**, alone, with the severity anchors and the `Supersedes:` check that
   ship in the same commit.
2. **The seat map** — three profiles, seat resolution with the review seat's mode
   forced and the profile-level refusals attached, the pre-work signals added to
   the dispatch record, generated seat surfaces where a target surface exists, and
   #242's trial closed as inconclusive.
3. **The escalation-condition mechanism** — the data surface and the emission,
   ahead of both its consumers rather than after them.
4. **The provenance removal** — the routing policy re-founded per the table above,
   including class 7's deletion and class 4's restated remedy, which is one of
   those consumers; the bar dropped after the trial harness, the in-world list,
   and `docs/review-dispatch.md`'s two operations are rehomed.
5. **The documents the rulings contradict**, all in one landing and **after** the
   mechanisms that make them true: `AGENTS.md`'s no-further-verification
   amendment, Model roles replacement, withdrawn provenance rules and
   `NO_MUTABLE_SUBJECT` name; `docs/agents/orchestration.md`, which still commands
   opus/high, calls #242's trial live and declares the orchestrator ineligible on
   every foreign lane — and which `AGENTS.md` requires a dispatching seat to read;
   and `docs/multi-provider-dispatch.md`, which still calls ADR-0061 binding,
   routes review findings to the admission bar, and forbids registering an
   unmeasured profile. Two earlier drafts sequenced the `AGENTS.md` half *before*
   the mechanisms and omitted the other two documents entirely, which would have
   left agents following new rules that the surviving machinery refuses.
6. **The `/retro` skill rewrite**, restating steps 3 to 5 in terms of the backlog
   item.
7. **Never-alone** — branch exchange, the verdict record carrying the reviewed SHA
   and the reviewing dispatch id, the landing refusal on both, the self-review
   checklist, per-finding adjudication, the arbiter, the exemption list, and its
   telemetry events in the same landing.
8. **The observatory** — the rollup on rounds per landing, and the containment
   column only if a bypass can be made to leave a record.

The review loop is deliberately not first: it should not be the first thing to
land under a rule saying everything is reviewed, because it would have to review
itself.

Filed separately: lifting #265's gate ceiling, which blocks the Codex implementer
head; the `AGENTS.md` reduction and its `NO_PYTHON_SUBJECT` correction; the Codex
orchestrator backup that ends ruling 1's carve-out; the Codex seat-definition
surface; the blind classifier the severity hypothesis needs; the top-level
dispatched corpus runner that would lift routing class 5; `hook_parity`'s
fail-open on unsupported and malformed hook groups; and deriving class 6's path
list from what `just check` actually runs, so a gate written tomorrow is covered
by the rule that judges it.
