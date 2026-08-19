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
("All approved as read", the third of four approvals). Two amendments under
this sign-off, each marked inline at the passage it changes — **A1** (#361,
human ruling 2026-08-14) fills ruling 2's escalation column, strikes ruling
4's blanket `fable-high` fallback and adds the conflicted-head fall-through in
its place; **A2** (#368, human ruling 2026-08-14, recorded in full on #327)
re-founds the re-founding table's class 2 row on the route's seats, which is
what #327 landed at `0c7063e`. A1 changes **two** sentences of ruling 4 — it
strikes the blanket
`fable-high` fallback, and it rewrites the arbiter's seat from "the
implementer's seat's" to "the implementing seat's" — adds a third paragraph
that is new rule rather than reversal (the conflicted-head fall-through), and
fills four cells of ruling 2's table. Of those, only the struck fallback and the
filled cells are *stated* in the human's ruling; the arbiter-seat rewrite is
**inferred** from it, because filling `retro`'s cell is pointless on any other
reading and the ruling's own diagnosis correction presupposes it. Sound
inference, marked as one rather than presented as transcription. A2 corrects a
description of code that had already moved and reverses no decision. Both
passages are human sign-off surfaces and both rulings are that sign-off, quoted
on the issues named — with the inferred sentence flagged above as the one
passage the sign-off covers by implication rather than in words. Every profile id and
seat list below was re-derived from `tools/dispatch.py`'s registry and every
class-2 field from `config/dispatch-routing-policy.json` as this commit's tree
carries them, never pasted from a ruling comment.
Amended: 2026-08-17, not by a human ruling but under the human's standing
authorisation of that date — *"resolve all decisions and rulings on my behalf
in consultation with a fable/high advisor according to your collective best
judgement"* — exercised by the orchestrator seat on #397 after consulting a
`fable`/high advisor, and recorded as a delegated decision in ADR-0074 under
ADR-0013. One amendment, marked inline at the passage it changes — **A4**
(#397, orchestrator ruling 2026-08-17) strikes ruling 3's closing sentence,
*"Never-alone does not apply to retros, because nothing lands"*, and makes the
retro journal in `docs/process-log.md` the single named exception to "lands
nothing", with never-alone applying to that one artefact per cycle. It reverses
no other decision and adds no rule beyond the exception it names. The
`Reviewed-by-human:` line above covers the version at the 2026-08-15 sign-off
and does not reach A4; A4's human review is pending, tracked on ADR-0074.
Amended: 2026-08-18, on the human's instruction of that date recorded on #417.
One amendment, marked inline at the passage it changes — **A5** (#417) narrows
ruling 4's own binding rule: a verdict that names a moved SHA carries across a
rebase only where a tool-recorded clean rebase connects the two commits and the
diff's exact identity matches, replacing the first #417 build's patch-id carry,
which a review of that build disproved on both halves. It reverses no decision
— the verdict still names the commit it reviewed, and an amended branch still
rides no earlier approval; it makes the carry provable rather than assumed.
Applied by #417's rework in the same change as every operational surface that
states the rule, enumerated at the amended passage itself — #397 took an extra
round for stating a rule in the ADR and leaving an operational copy behind, and
a count here would be one more place for that to happen.
Amended: 2026-08-18, on the human's ruling of 2026-08-14 recorded in full on
#334, which states its own standing — *"this amends ADR-0071 ruling 4, a human
sign-off gate; this ruling is that sign-off."* One amendment, marked inline at
the passage it changes — **A7** (#372) adds the fourth adjudication route to
ruling 4: a finding at Medium or below may be adjudicated **accepted and filed**,
with the restrictions the ruling states. It adds a route and reverses no
decision; the three alternatives the ruling weighed and declined are recorded
with it. The ruling asked for this to ride the merged ADR-0071 landing of A1 and
A2 (#372's sequencing note); that landing went in on 2026-08-15, before the
ruling was filed as #372, so A7 opens the file again rather than riding it —
recorded here rather than hidden. The enforcement and the loop writer already
carried the route when A7 landed (#334 and #333), so this amendment brings the
decision record level with the code.
Amended: 2026-08-19, not by a human ruling but under the human's standing
authorisation of 2026-08-16 — *"resolve all required decisions and rulings
requiring human review by yourself using your own best judgement"* —
exercised by the orchestrator seat on #391, quoted in full on that thread, and
recorded as a delegated decision in ADR-0075 under ADR-0013. One amendment,
marked inline at the passage it changes — **A8** (#391, orchestrator ruling
2026-08-19) gives the rung the passage below said was unowned an owner and a
reader: `arbiter._walk_first` runs `enforcing_match` per candidate on inputs
the escalation derives itself — the policy off fetched `origin/main`, the
branch under review off `refs/heads/issue-<n>` — and the caller-supplied
`--routing-refusal` flag is deleted with no replacement seam. The ruling's
binding precondition, that no caller's already-supplied refusal be
double-applied, was discharged before the change: no caller ever passed the
flag, its only feeder being the flag itself, so nothing needed separating. It
reverses no decision this document records and adds no rule beyond moving an
existing rung's read from the caller into the walk. A8's human review is
pending, tracked on ADR-0075.
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
| `implementer` | `codex-luna-max`, `zai-glm52-max`, `opus-low` *(A6: live as written — and the z.ai entry is `zai-glm53-max` in the registry since `89fc445` re-named the current GLM model; the table keeps the name it was decided with and the registry is the authority)* | `codex-sol-high`, `opus-high` |
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
from outside that list would widen that allowance by the back door. **That
ground is superseded in this very document** — the trailer's "Supersedes: the
human's ruling on #300" is why #327 could delete `RETRO_APPROVED_PROFILES` and
its guards, so there is no live #300 allowance left to widen. The reasoning is
kept as transcribed because it is the human's own, and corrected here rather
than silently rewritten; the outcome is unaffected, since `opus-max` and
`fable-max` are registered profiles either way. A later seat's arbiter must not
be argued against #300's nine as a live constraint — that is the
elimination-context rule's own failure mode, inside the document that landed the
elimination (review round 1, claim 7).*

*It deliberately excludes `fable-high`, which is this seat's own preference head
and therefore the profile most likely to be conflicted. `orchestrator`'s entry
deliberately excludes `opus-xhigh`, which is the seat itself. Both entries hold
two profiles, head first, matching ruling 4's "*Head*, because those entries
hold two profiles".*

***The second profile is reachable, and the code is where to read the order.***
*The prose of ruling 4 below names only the preference list, which read alone
would leave an entry's tail unreachable — the gap A1's second pass recorded.
It is not the gap it appears to be, and the resolver landed before that pass
was written: `tools/arbiter.py`'s `_walk` at `1a5a7fb` (lines 120–132) walks
`(*seat.escalation, *seat.preference)` deduped — entry head, then entry tail,
then the preference list — so `retro`'s `fable-max` and `orchestrator`'s
`fable-xhigh`, the two tails this paragraph is about, are candidates whenever
their head is excluded. #326 is that walk's own cited proof, and it is a third
entry's: the **implementer** seat's dispatcher, meeting a routing-refused head,
landed on that entry's second profile `opus-high` — which neither of the two
entries here carries, and which the implementer's preference list does not carry
either (review round 2, claim 6). Read the walk, not this table's prose, for the
order (review round 1, claim 6; review round 2, claim 1's rule — checked at
`tools/arbiter.py:120`, `1a5a7fb`).*

*The registry carries these entries as of this commit:
`tools/dispatch.py`'s `SEATS` gives `retro` and `orchestrator` the escalation
tuples above, so `just dispatch --seat retro --list` prints them and
`seat_list_exhausted` names them. When A1 first landed at `eaabf9f` it did not,
and for one commit the ADR said what neither live surface said (review round 1,
claim 1). Nothing mechanical compares this table to the registry; the only tool
that reads this file is `tools/check_adr_form.py`, which checks form. That gate
is **#392's**, filed on review round 2's claim 5 and not built here. An earlier
pass called it "#354's shape", which is wrong and is corrected rather than
dropped: #354 is retro-proposal-versus-tree, a different pair of surfaces, and
this pair is ADR prose versus `SEATS`.*

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

*(Amendment A6, 2026-08-19, on the human's instruction of 2026-08-18 recorded on
#405: **the ceiling is lifted, and every sentence in this paragraph that said
"blocked" is history rather than current state.** The seventh arrangement — no
git directory a writable root at all — is the one that escaped the six measured:
Codex read-only-enforces `<root>/.git` inside every writable root, and where no
root is a git directory there is nothing to enforce, so the gate runs in the true
repository layout while the commit moves to the dispatcher, which is not
sandboxed. `SEAT_PROFILE_BLOCKS`' one entry —
`("implementer", "codex-luna-max")` — is gone with the ceiling, and the registry
heads `implementer` with `codex-luna-max` again, per the preference table above
and not per this paragraph's "until it lifts" ordering. What survives unchanged is
the binary rule this paragraph applied and the rejected alternative it records:
gating Codex's output elsewhere is still the graded ladder ruling 1 withdrew, and
the division of labour — the session gates, `harness_finish` commits — is the
arrangement that made the head live without touching it.)*

Three registry lines are new: Luna at maximum effort, Luna at its published
default of medium, and Opus at low effort. **Luna enters on publication rather
than measurement**, at the human's ruling — a named exception to `AGENTS.md`'s
validated measure-before-building rule, recorded as an exception rather than
presented as consistent with it. Its catalogue entry publishes five effort levels
and describes it as a fast, affordable agentic coding model; neither adjective has
been measured in this project.

**On `recon` that exception has no expiry, and the ADR should say so.** The
implementer head is at least gated and ranked once #265 lifts *(A6: it has
lifted, #405 — the head is live, and the sentence's contrast is what survives:
the implementer is now checked by the gate, while nothing will ever check this
one)*. `recon` is
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

**The choice deferred above is made, and the last sentence of this ruling is
struck.** It read: *"Never-alone does not apply to retros, because nothing
lands."*

The retro journal is the single named exception to "lands nothing", and
never-alone applies to it. One artefact per retro — the entry appended to
`docs/process-log.md` — lands under ruling 4 like any other change: a reviewing
instance in a different session, and a lander who may be the proposer.
Everything else a retro produces is a filed item.

*(Amendment A4, proposed on #397, 2026-08-17. It takes effect by landing: this
file is a human sign-off gate, so the sign-off that lands it is the ruling, and
until then the text sits on a branch rather than in the tree. #330's skill
rewrite settled the exception where this ruling said it belonged; what #397
found is that the three surfaces read **before** that skill — `AGENTS.md`'s
retro bullet, routing class 3's remedy and this sentence — still stated the
prohibition flat, so an agent met the old rule first and the new one only if it
got as far as the skill. They carry the exception now.)*

*The alternative was put and declined: exempt the journal from review, which
#330 named beside this one. It is cheaper per cycle, and it makes an exception
to never-alone rather than to lands-nothing. Three grounds against it.
`config/review-exemptions.json` states what may grow it — ruling 6's
pre-registered question, answered on evidence at a retro, "never as an agent's
convenience in the moment" — and a first entry added because a review round
looks expensive is that shape exactly. The journal is a **self-report**: the one
artefact written by the party with the strongest interest in how it reads, and
the only durable in-tree trace that the retro ran, so it is where an independent
read is worth most rather than least. And it is not narration —
`docs/process-log.md` is the archive of record for the exemplar prune (#201),
where reasoning cut from the always-loaded prefix survives in no other copy, so
a wrong or truncated entry loses it silently. One exception is also cheaper than
two: this makes one, to "lands nothing", and reuses the review that already runs
on every landing.*

*What it costs, stated rather than discovered: one review round per retro cycle,
over a diff of one terse appended entry, and a second dispatch where the retro
was itself dispatched. What it does not do: it does not make the retro an
implementer. It lands one path, `docs/process-log.md`, and only its own entry.
#294's bar on a dispatched session writing under `.claude/` does not reach it,
because the journal is not there.*

***The undispatched case is not a smaller cost, it is a refusal, and the rule
that follows is stated here rather than left to be met at the gate: the journal
lands only from a retro dispatched against a numbered issue.*** *`just land`'s
never-alone rung (#334, `tools/land_review.py`) refuses a tree that is not an
`issue-<n>` worktree by name — `review_issue_unknown`, "the rung cannot know
whose review to read" — and refuses an issue whose dispatch records place no
profile on the work as `authorship_unrecorded`; no flag skips either rung, and
`config/review-exemptions.json` is empty. An attended retro run in the human's
own session has neither a numbered tree nor a dispatch record, and the
sixteenth and twenty-first were attended, so this is a shape that has occurred
rather than a hypothetical. Its findings still file as normal; its journal entry
reaches `docs/process-log.md` through a dispatch against the retro's own issue,
or not at all.*

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
ruled on, an arbiter dismissal, or an **accepted and filed** finding (amendment
A7 below). The record is written by the dispatcher, not by
the reviewed agent.

Without that last clause the refusal asked only whether a review *happened*. A
proposer could dispatch a review, receive a Critical, do nothing, and land — no
forgery, every check satisfied, and the stop condition "nothing above Low remains
unadjudicated" enforced nowhere.

*(Amendment A7, 2026-08-18, on the human's ruling of 2026-08-14 recorded in full
on #334, which states its own standing: "this amends ADR-0071 ruling 4, a human
sign-off gate; this ruling is that sign-off." The list above held three routes,
and that left an implementer who **agreed** with a finding above Low two legal
moves only: fix it — another round — or dispute it, an arbiter only after three
fix rounds. Deferring was not a disposition at all, and #356 paid for that shape:
every finding in all four of its rounds was accepted, none disputed, and its
round-3 adjudication had to argue in prose why a Medium introduced by round 3 was
not an escalation, with four landings queued behind the branch. The ruling adds
the fourth route, transcribed: a finding at **Medium or below** may be adjudicated
**accepted and filed** — the implementer agrees the finding is real, states why
the fix does not belong in this diff, and files it as an issue on the originating
item **before** landing; the landing record carries it like any other
adjudication, naming the issue it became. Not available above Medium, and not
available where the defect is in the diff under review rather than conditional on
work outside it — "it only bites if someone later does X" is the test, and X must
be named. The alternatives were put and declined, so the choice is not
re-litigated: re-grading conditional harm as Low would make one level mean two
unrelated things, since the severity anchors ride blast radius and silence rather
than likelihood; raising the stop condition to "nothing above Medium" would land
#157's class of defect unfixed by default, a larger change than a scheduling
frustration should buy; and no change leaves round-3 prose explaining why the
escalation condition did not fire. The ruling asked for this amendment to ride
the merged ADR-0071 landing of A1 and A2 (#372's sequencing note); that landing
went in on 2026-08-15, before the ruling was filed as #372, so this amendment
opens the file again rather than riding it — recorded rather than hidden. The
route is enforced where the list above
is, #334's fourth criterion in `tools/land_review.py`, and written by `just
review-loop adjudicate --route accepted_and_filed` with the named condition and
the filed issue (#333); both landed carrying it, the ruling having been noted on
#334's thread before that check was built, so this amendment brings the decision
record level with the code that already enforces it.)*

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
*(Amendment A5, 2026-08-18, on the human's instruction of that date recorded on
#417, whose first build was reviewed Critical and reworked: the refusal is
not absolute over a moved SHA. A verdict also records the exact identity of the diff
it judged — a SHA-256 over `git diff --unified=0 origin/main...<sha>` with only the
line-number ranges of each hunk header normalised away (the section anchor after them
kept) and an `index` line flattened for a textual file but kept whole for a binary
change, whose blob hashes are its only content — and a landing carries the review across a rebase
only where **both** hold: the rebase's own outcome was recorded as clean by the tool
that ran it (`<review-root>/<issue>/rebases.json`, written by `just land --stage` and
`just land`), and the identity computed over the rebased tree equals the recorded one.
The first #417 build carried the review on `git patch-id --stable` alone and both
halves of that were disproved: patch-id strips whitespace, so a conflict resolved with
trailing whitespace the reviewer never saw cleared as "unchanged"; and patch-id hashes
context, so an upstream edit inside the surrounding lines refused the very carry the
mechanism existed to grant. Hashing the output cannot prove whether conflict resolution
occurred at all — only the rebase knows that, which is why its own record is one of the
two halves. A moved SHA with no recorded clean-rebase chain refuses `rebase_unproven`;
a verdict whose identity is missing or unreadable refuses `diff_id_unreadable`, which
is also the one-time re-review verdicts recorded before this amendment take. The rule
is stated in `docs/review-dispatch.md`, `tools/review_exchange.py`,
`tools/land_review.py`, `tools/land.py`, the `justfile`'s `review` recipe, the `just
review` row of `AGENTS.md` and the `CHANGELOG.md` entry — the whole list, because #397
took an extra round for amending the ADR and leaving an operational copy behind.)*

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

*(Amendment A1, third pass, 2026-08-15 — **this rule is implemented; the
present indicative is a description of code.** A1's second pass recorded it as
unperformed, and that was already false when written: `tools/arbiter.py` landed
at `d351a3f` under #333 and is on `origin/main` at `1a5a7fb`. Where to read it,
checked line by line at that SHA rather than recalled: `arbiter._walk`
(`tools/arbiter.py:120`) is the walk; `arbiter._walk_first`
(`tools/arbiter.py:135`) excludes on the registry, the caller's routing
refusals, the issue's dispatch records and the live dispatchability rungs, and
records every exclusion as `Exclusion(profile, reason, detail)`;
`arbiter.NO_ENTRY_REFUSAL` / `arbiter.EXHAUSTED_REFUSAL`
(`tools/arbiter.py:69–70`, a line each) are the two named refusals, neither
carrying a failure class; and `Resolution.unchecked` (the field at
`tools/arbiter.py:114`, on the `Resolution` class declared at `:104`) is the
`--reviewing` property carried over, set from `Authorship.complete` at `:175`
and `:180` so **every** incomplete read, not only the unreadable one, leaves the
resolution taken and unverifiable. The production caller is `tools/review_loop.py:1374`, which calls
`arbiter.resolve_dispatchable` on `just review-loop escalate`, prints the
refusal and each passed-over profile, and returns its refusal exit rather than
naming a profile nobody chose. `dispatch.escalation_head` still returns the
tabled head alone and is `tools/brief.py`'s briefing field — a briefing states
who the table names, which is not the same act as resolving an arbiter at an
escalation.*

***The trigger is wider than conflict of interest, and where it stops is
stated.*** *A1's second pass recorded the trigger as conflict alone and the
#326 case as unreachable; the implementation covers both. Routing refusals are
an exclusion rung in their own right — `arbiter._walk_first` takes a
caller-supplied `profile -> reason` mapping, fed from `just review-loop
escalate --routing-refusal` (`tools/review_loop.py:1266`), so #326's
class-6-refused head is passed over with its reason recorded rather than
resolved to. A tripped breaker, an exhausted quota and an off-peak window are
covered by a different rung: `arbiter.resolve_dispatchable` calls
`dispatch.candidate_refusal` (`tools/dispatch.py:2338` at `1a5a7fb`) per candidate, which is
the ladder's own admission, breaker, off-peak and credential rungs called rather
than restated. **What is not covered, stated rather than implied:** the routing
policy is not read by either module — `candidate_refusal`'s docstring says so
and gives the reason (a rung belongs to it only where it is a function of
`(lane, profile, seat)` alone) — so the routing exclusions are as good as the
caller's flags, and an escalation dispatched without them walks past a head the
policy would refuse. **This rung is uncovered and, as of round 3, unowned.**
Round 2 wrote "Owner: #326", and #326 closed on 2026-08-14 at 13:13Z, the day
before that line was written — `candidate_refusal`'s docstring named the same
closed issue. Naming a replacement owner is a decision rather than a repair, so
round 3 states the gap and files **#391** for the ownership question instead of
inventing one (review round 1, claim 4; review round 2, claim 2).*

*(Amendment A8, ruled on #391, 2026-08-19, under the human's standing
authorisation of 2026-08-16 and recorded as a delegated decision in
ADR-0075. The gap this passage states is closed: **#391 owns the rung, and
the walk reads the policy itself.** `arbiter._walk_first` now runs
`routing_policy.enforcing_match` per candidate — the landing read, the same
one `just land` runs — on inputs `just review-loop escalate` derives and no
caller declares: the policy read off fetched `origin/main` (never the diff
under judgement's own copy) and the branch under review read off the review
exchange's own ref `refs/heads/issue-<n>`, merge-base-relative. The
caller-supplied `--routing-refusal` flag this passage describes is deleted,
with no replacement seam — a flag a caller may not pass is the trust hole,
not the interface. The ruling's binding precondition, that no caller's
already-supplied refusal be double-applied by the new read, was discharged
before the change was built: no caller passed the flag, no document or brief
composer computes it, and its only feeder was the flag itself, so there was
nothing to separate. A rung that cannot read either input refuses the
escalation by name rather than resolving past it (#41: a check that could
not run is not a check that passed). Against the shipped policy the rung
excludes nobody, because since ADR-0073 no row refuses a landing — it runs
anyway, and a refusing row is one table edit away from being honoured.)*

***Copies of the arbiter rule are scattered, and this amendment reversed one.***
*The in-repo ones known to this pass. Four — `docs/agents/review-severity.md`, `config/escalation-conditions.json`,
`tools/escalation.py` and `tools/brief.py` — were swept to "the implementing
seat's" in the same commit as this paragraph, and `tools/brief.py` now takes the
arbiter from the briefed seat's entry rather than emitting the implementer's head
for every seat. The fifth is `dispatch.escalation_head`'s own docstring
(`tools/dispatch.py:648`), which round 1 of this issue's review wrote and which
sat **outside this enumeration** for two rounds while it claimed the fall-through
was unbuilt and cited this very passage — the passage the previous pass had
rewritten to say the opposite. It is corrected in round 3 and counted here, which
is the arbitration of 2026-08-15 on this thread; the arbitration's own finding is
that a hand-derived enumeration passes its blindness to the sweep that reads it,
and deriving the set instead of counting it is **#390's**. Until #390 lands that
derivation, this list is what successive passes have recalled, and nothing here
establishes it as the whole set. `tools/arbiter.py` is not on the list because it
is the authoritative surface rather than a copy of it. Also off-tree:
**#333's body**, which still carries the
struck blanket in a second form ("a seat whose escalation column is empty
arbitrates at the escalation tier") and an acceptance criterion demanding a rule
that yields a profile even for an empty column. #333 closed on 2026-08-15 at
17:38Z, and the risk this paragraph's second pass named did not materialise: the
implementation refuses instead, `arbiter.resolve` returning `arbiter_no_entry`
before any walk on an empty column (`tools/arbiter.py:204`, `1a5a7fb`). The stale
criterion survives on a closed issue, where nobody will implement to it; it is
recorded here rather than given an owner, because editing a closed issue's body
to match what its landing did is archaeology, not work (review round 1, claim 3;
outcome recorded on review round 2).)*

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

***That worked example does not follow from the table this amendment lands, and
is kept only because it is the human's own words.*** *Under the filled table
`retro`'s head is `opus-max`, and #318's records place `fable-high` (author) and
`opus-xhigh` (reviewer) on the work — not `opus-max`. The head is therefore
unconflicted, the fall-through never fires, and the rule resolves to **the same
`opus-max` the orchestrator chose by hand**. `codex-sol-xhigh` sits **fifth** in
the walk `tools/arbiter.py:120` performs — third is its position in `retro`'s
*preference list*, which is the exact confusion this paragraph exists to correct
(review round 2, claim 4). The walk is entry head `opus-max`, entry tail
`fable-max`, then the preference list `fable-high`, `opus-xhigh`,
`codex-sol-xhigh` — so it is reachable, but only once the two tabled profiles
and the two conflicted preference entries are all excluded, which #318's records
do not do. The rhetorical point survives intact: the choice stops being made in
the moment. The stated outcome does not, and this is the document's only worked
example of the new rule, so a reader calibrating on it would mis-predict every
case where the escalation head sits outside the preference list — which is both
filled rows. Correcting the ruling's own claim is the human's; flagged rather
than rewritten (review round 1, claim 5; the reachability half corrected against
the landed walk on review round 2, where A1's second pass had it unreachable).*

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
landing's record carries each finding above Low with its verdict — fixed,
accepted and filed naming the issue it became *(A7)*, upheld or dismissed — and
the dismissals go to the post-landing seat as an input beside
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
ceiling lifts *(A6: lifted, #405 — it heads it now)*, recon and review — so those
reach the same conditions by re-dispatch, at the cost re-dispatch carries.

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
`recon`, `planner` and `retro` land nothing by contract — `retro`'s journal
aside, one entry per cycle under A4, which is not an implementer's denominator
and is not ranked here either. Their rework is reported,
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
| 2 `orchestration` | **survives, re-founded on the route's seats** *(Amendment A2)* | it carries no lane rule at all. Its `required_seats` are `orchestrator`, `planner`, `implementer`, `review` and `recon` — the route that finishes orchestration work — and it refuses `retro` and `fable` on **every** lane, Claude's included, where the row this table originally described refused every seat off Claude and no seat on it. **This row is not ruling 1's carve-out and not a provenance rule.** That carve-out is `orchestrator_claude_only` in `tools/dispatch.py`'s seat table, and it is now the **only** keep-on-Claude rule the project holds: the policy's own, class 6's, was retired by ADR-0073 *(Amendment A3)*. See the A2 note under this table for what forced the shape, and for the two alternatives the human declined |
| 3 `retros_and_adr_authorship` | **splits, and the survivor needs a path it does not have** | the retro half dies with ruling 3. ADR authorship survives, bound to the planner's list rather than to Claude — but the class's only `landing_path_prefixes` entry is `docs/process-log.md`, which belongs to the half being killed, so the surviving half would enforce on issue phrases alone. It gains `docs/adr/` as its landing path, or it is a class that catches nothing |
| 4 `plausible_wrong_fix_goes_green` | **survives, remedy restated** | gate coverage, not provenance. Remedy becomes route-to-planner-and-escalate, and ruling 5 carries the matching condition |
| 5 `in_world_landings` | **narrowed to a subagent rule** | a *subagent* cannot hold the corpus's foreground wait, so a seat reached that way cannot gate its own in-world work. `just dispatch` already launches a **top-level** session, which the wait hook permits — it returns 0 where there is no `agent_id` — so the class does not restrict the dispatch route this ADR defines, and two drafts said it did. What remains is a real but much smaller rule about subagents |
| 6 `gates_themselves` | **survives, reframed, and now holds** *(Amendment A3)* | conflict of interest: *no instance authors the gate that judges it*. Binds Claude too, and takes class 1's two gate paths. Enforcement is a hard-coded path list and its coverage is far worse than the third draft admitted: of the seven gate tools `just check` runs it names **one**, `tools/mutation_smoke.py`; it omits `tools/check_adr_form.py` — **which this commit adds and then uses to judge the ADR in the same commit** — along with `check_seat_config`, `check_validated_markers`, `check_conflict_markers`, `check_source_symlink`, `export_command_schema`, `tools/breaker.py`, and the exemption list step 7 creates. Deriving the list from `just check` alone would still miss gates under `just unit`, `just mutation`, `just land` and `just regress`, so that filed item is stated as insufficient rather than as the fix. **The class was aspirational when this table was written — it named six paths and the invariant it asserted was enforced by nothing, while the refusal that actually fired was the older keep-on-Claude bar.** ADR-0073 (#406), on the human's instruction of 2026-08-18, retires that bar and enforces the invariant instead: the row refuses no route on any lane, and a landing whose diff touches these paths must carry a review verdict from a **different lane** than the author's — unchanged wherever a cross-lane reviewer exists, and degraded only by exhaustion *(ADR-0073 Amendment A1, #416)*: where every lane the registry carries is a lane the records place on the work, no such reviewer can be dispatched, so the requirement falls back to this ruling's own different-profile rule and the landing records `gate_review=lane_exhausted`. The coverage sentence above is unchanged and still true — the invariant now holds over exactly the paths this row names, and nowhere else |
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
count of what survives rather than of what was written down. Read as a claim about
*invariants*: class 6's invariant — no instance authors the gate that judges it —
would exist in a single-provider project, but its only live **refusal** would not,
since that refusal is lane-selected and clears on `claude-native`. The count is
about what each class is for, not about what would still fire (review round 1,
claim 10). *(Amendment A3 makes the qualification sharper rather than removing
it: the lane-selected refusal is gone and the invariant is enforced, but the
enforcement — a review from a different **lane** — is itself a multi-provider
mechanism, so in a single-provider project the class would still exist and still
fire nothing. What changed is that the gap is now in the enforcement's reach
rather than in its absence.)*

The one lane-selected refusal the policy still carries is class 6's
keep-on-Claude bar, which is a rule about the gates rather than a class resting
on provenance. It was kept until #331's exemption list gave that row's invariant
an enforcement of its own. *(Amendment A1, second pass, 2026-08-15, owner
corrected on the third: that condition is already spent and the bar is still
here. #331 closed at 07:43 on 2026-08-15 and `config/review-exemptions.json`
landed three minutes later at `8e771e3` — some ten hours before `eaabf9f`, the
commit that wrote the sentence above pointing forward at it. The same spent
pointer is in the policy the code reads, not only in this paragraph: class 6's
remedy at `config/dispatch-routing-policy.json:122` still says the invariant is
enforced by no refusal "until #331's never-alone exemption list lands". Whether
the bar survives deliberately or was forgotten is undecided, and the answer is a
decision rather than a reading. **Owner: #389**, filed for it — the second pass
named #333, which closed on 2026-08-15 at 17:38Z, so that owner was spent too
(review round 1, claim 8).)*

*(**Amendment A3, 2026-08-18, on the human's instruction of that date, recorded
in ADR-0073 and applied by #406.** The paragraph above is now history and is kept
as history: the policy carries **no** lane-selected refusal, because the
keep-on-Claude bar it describes is retired. #389's question — deliberate or
forgotten — is answered by the human rather than by an agent's reading, and the
answer is neither: the bar was not their intent in the first place. What replaces
it is the invariant with an enforcement of its own, in the never-alone rung this
ADR's ruling 4 already runs at every landing: a class-6 landing's review verdict
must come from a different lane than the author's. The bar's own defect is on the
record in ADR-0073 — it exempted the lane that authors nearly every gate change,
so the surface most at risk was the one the rule cleared, which this table's own
row 6 conceded in as many words. #331 is **narrowed rather than reopened**: its
substance is closed for this one class, and what it still owns is the coverage
question — the gates this row's path list does not name.)*

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
  prerequisite *(A6: this cost is spent, #405 — the ceiling is lifted and the head
  is live, so the lane enforces what the map requires of it; the seat-gap half
  below stands unchanged, and its reasoning about visible-only-in-a-bill failures
  is why it was never made blocking)*; the missing seat-definition surface — whose failure mode is
  *silent tier inheritance*, the one that consumed the bulk of a weekly budget on
  2026-08-04 — blocks nothing and is merely recorded. The inconsistency is
  deliberate: the ceiling is falsifiable by running a gate, while the seat gap is
  visible only in a bill, so blocking on it would stop the lane indefinitely with
  no test that could clear it. That is a reason, not a justification, and it is
  the weakest place in ruling 1's binary rule.
- **Consultative escalation is unavailable on the lane heading four seats.**
- **The implementer head is blocked on #265's ceiling**, so ruling 2's headline
  allocation is not the one that runs on the day this lands. *(A6, #405: no longer
  a cost — the ceiling lifted on the human's instruction of 2026-08-18, and the
  headline allocation is the one that runs.)*

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
head *(A6: done, #405 — the session gates and the harness commits, and
`SEAT_PROFILE_BLOCKS` is empty)*; the `AGENTS.md` reduction and its
`NO_PYTHON_SUBJECT` correction; the Codex
orchestrator backup that ends ruling 1's carve-out; the Codex seat-definition
surface; the blind classifier the severity hypothesis needs; the top-level
dispatched corpus runner that would lift routing class 5; `hook_parity`'s
fail-open on unsupported and malformed hook groups; and deriving class 6's path
list from what `just check` actually runs, so a gate written tomorrow is covered
by the rule that judges it.
