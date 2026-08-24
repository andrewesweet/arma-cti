# The Work Run's interior is specified, acceptance is executable, and cost is measured in dollars per landed Work Item

Delegated-decision: no
Date: 2026-08-24
Supersedes: none
Reviewed-by-human: the human's authorisation of 2026-08-24 in the session that produced this
record — "I'm the owner and I authorise our approach", given after a design conversation that
began from telemetry and ended in three rulings, and confirmed piece by piece as each was put
Claimed: 0079 — after `git fetch origin` (`docs/adr/` on `origin/main` topping at 0078) and a
scan of every open issue body plus a `gh search issues` query for `ADR-0079` and `ADR-0080`,
both returning nothing. The usual blind window applies to a claim living only in a comment the
search did not surface; the landing rebase is the backstop

Three rulings, taken together because they are one decision about how work is verified and how
that verification is paid for. Each amends a rule that a sign-off gate protects, so each is
recorded here rather than left as an unmarked edit.

## Ruling 1 — a Work Run's interior is a specified pipeline, and the rule against additional verification passes admits it

CLAUDE.md holds that beyond never-alone and the post-landing review, no further verification
passes, re-checks or verifier subagents may be added. The human's ruling on #220 re-based that
from a quality rule to a **first-order cost rule**: an extra pass is pure generation, and
generation is the act this plan meters.

That rule is amended, not repealed. An implementer may run a bounded self-review inside its own
Work Run, before handing the candidate to the independent reviewer. No dispatch, no subagent —
CLAUDE.md's separate prohibition on spawning a subagent to check your own work is untouched, and
the reason it gives still holds: such a subagent books its outcome to the spawning profile and
cannot be ledgered.

### What the exchange buys

Reconstructing every issue's dispatch history in time order, as at 2026-08-24: 184 issues, 400
implementer dispatches, 294 review dispatches. Of the 106 issues that reached review, **73.6%
went to the reviewer after exactly one implementer dispatch**, only **22.6% cleared in one
round**, and **67.9% needed two or more review dispatches**. Across the corpus there were 243
implementer-to-review handoffs and 156 returns: **64.2% of handoffs come back**, and that is a
floor, because a fix made in an interactive session leaves no dispatch record.

The cause is not agents skipping a step. There is no step: nothing in the briefing composer, in
`docs/review-dispatch.md` or in CLAUDE.md asks an implementer to re-read its own work before
invoking the assessor. The nearest thing forbids one form of self-review without prescribing
another.

So the trade is a bounded number of in-session rounds — generation only, no dispatch, no extra
gate run — against a measured 67.9% rate of needing a second review dispatch, each costing an
implementer dispatch, a review dispatch and a gate run.

### Why the vertices exit the way they do

The design's shape follows from one finding in the literature rather than from taste. The TACL
survey of self-correction finds that no prior work demonstrates successful self-correction from
feedback a prompted model generates about itself, except in tasks exceptionally suited to it,
and that self-correction works where **reliable external feedback** exists. Huang et al. find
intrinsic self-correction can degrade performance outright.

Checking a claim against an external oracle is not self-judgement. Re-running a computation,
opening a citation, running the gate, comparing a diff against a written plan — the feedback is
sourced outside the model even though the model fetches it. The failure case is "review your
work and tell me if it is good".

The governing constraint, which every vertex's exit criteria must satisfy: **an exit criterion
must be answerable by consulting something outside the reasoning that produced the artefact, and
a vertex that can only offer self-judgement is not a gate.**

### The evidence, including its limits

The protocol was run against its own specification twice, and **failed to converge both times**.
The round histories are on #535 and are the only evidence behind the design's ordering rules.
Splitting the findings by origin is what produced them: discovery of pre-existing defects
converged in both runs (12, then 1, 4, 1, 0; and 3, 1, 0, 0, 1) while defects introduced by the
loop's own fixes did not (0, 2, 1, 3, 2; and 0, 3, 2, 1, 0). A stopping rule counting both
streams together cannot terminate while fixes create findings at the rate they close them.

Both runs were on prose, by the instance that wrote it, with no independence at all. Prose
regenerates its whole review surface with every fix in a way a diff does not, so the injection
rate observed may say nothing about code. **No threshold in this design is derived from those
runs**, and none should be.

## Ruling 2 — acceptance criteria are executable specifications, in Gherkin, over a closed vocabulary

Every behavioural acceptance criterion is carried as an executable specification. The
specification language is **Gherkin's structure** — a standard grammar with a free parser, which
agents author without training — with the **domain vocabulary closed against `CONTEXT.md`'s
Language section**, so a domain term that does not resolve fails at authoring time rather than
at runtime.

Gherkin alone was rejected for the job it does not do. Its grammar constrains *structure* and
leaves step text as free prose, bound to code by expression matching; an unmatched step is a
runtime failure, not a parse failure. For an artefact that is a contract between agent sessions
that is the wrong half to constrain, because two sessions can write structurally valid Gherkin
with incompatible step text and discover it only when something runs. Robot Framework constrains
vocabulary natively and was the runner-up; controlled natural languages — Attempto, SBVR — are
the formal end of the same axis and are too heavy, having no runner ecosystem here.

The expensive half of a vocabulary-first design already exists in this repository:
`CONTEXT.md`'s Language section is an agreed, maintained glossary that `tools/brief.py` already
reads **at run time rather than copying**, and whose contents were measured rather than
hand-tuned. No second machine-readable source is needed: the section's form —
term, definition, `_Avoid_` list — is a two-line regex.

### Three layers, three owners

A step definition does two jobs, and conflating them is why ownership felt wrong in both
directions.

| layer | owner | changes when |
|---|---|---|
| Scenario prose, in ratified terms | ticket creation | required behaviour changes |
| Step signature / domain driver interface | gated, like the glossary | the domain gains a new situation |
| Driver implementation | the Work Run | the implementation changes |

Ticket creation writes prose and never writes code. Because step text may use only ratified
terms, two tickets describing the same situation produce the same step text, so step definitions
become a **shared driver library** rather than per-ticket code — which is also the defence
against the step-explosion failure that free-prose Gherkin projects are known for.

A genuinely new step means a genuinely new domain situation, so it takes the glossary's gate. A
specification may declare a **provisional** term or step with its definition; the lint accepts
it and records it as provisional, and **the Work Item cannot land until it is ratified into
`CONTEXT.md` or removed**. Naming the debt rather than letting it vanish is the same discipline
LeSS applies to undone work.

The `_Avoid_` lists are the mechanical half and need no convention at all: a hit is a hard
error.

## Ruling 3 — cost is measured in US dollars per landed Work Item, per lane

`docs/research/token-efficiency-plan-currency.md` measured this plan's currency and is not
overturned: output weighs 33.10 percentage points of a five-hour window per million tokens
against cache reads at ≤ 0.0095 and cache writes at < 0.0096, and the meter counts neither
requests nor sessions. **That remains the right currency for deciding what to spend a fixed
subscription on.**

It is the wrong currency for deciding whether to hold the subscription at all. Plan points are
incommensurable across providers — ADR-0061 Decision 5 already says so — and a question like
"should this month go to z.ai or to a larger Codex tier" has no answer in them. That question is
real and recurring, so a second unit is needed rather than a replacement.

The unit is **US dollars per landed Work Item, per lane**, priced at each provider's published
list rates for the tokens actually billed. It is comparable across providers, and it is
capability-inclusive: a weaker model's extra attempts appear in the numerator while its failures
never reach the denominator. That second property is what makes it honest, because a per-token
dollar comparison silently assumes the models are interchangeable, which ADR-0061 Decision 5
denies. Pricing the z.ai lane's actual volumes at each provider's rates returned $625 per thirty
days at GLM-5.3's own rates, $1,574 at Sol's, and $63 at Luna's — a range that ranks cache-read
prices rather than capability, and would read as "the $80 subscription is not worth it" only by
pretending a much smaller model would have produced the same tokens.

Purchasing needs a second number besides the value ratio: **the wall-hit rate**. A plan at ten
times value that is never exhausted justifies no upgrade; a plan at twice value that blocks work
daily might.

`tools/ledger.py` carries `list_price_usd` with the note *"API list price, not plan spend. Never
a decision input."* That prohibition is **re-scoped, not deleted**: never a decision input for
ranking work within a plan, and the correct input for deciding whether to hold the plan.

### The precondition

Accurate capture across every lane is a precondition of this ruling, not a follow-up. Known
gaps at the time of writing: the Codex lane sums a cumulative series declared DELTA and folds in
a non-agent series (#525/#526); the ledger is materialised for 6 of 691 dispatches (#529/#531);
no rate table carries effective dates, though OpenAI cut two GPT-5.6 tiers on 2026-07-30; the
orchestrator's own turns carry no dispatch id and are a known under-attribution; and work
written in interactive sessions produces no row at all.

One gap turned out smaller than feared. Cache TTL is not a recorded attribute, but it is
derivable: Claude Code requests the one-hour TTL on a subscription and **subagents use the
five-minute TTL even there**, and `query_source` distinguishes `main` from `subagent` on every
token datapoint. Subagents are 5.59% of this project's cache writes, so pricing every write at
the one-hour rate overstates by **2.10%**, not the double-digit figure first estimated.

## What these rulings do not change

Never-alone is untouched: no single model instance may both propose a change and produce the
verdict that clears it, and the reviewer remains a separately dispatched instance in its own
session. The self-review specified by ruling 1 **precedes** that review and never substitutes
for it — the shape ADR-0071 ruling 4 forbids, and which #376 names in its own words as a verdict
that must not "become self-review under another name".

The post-landing review, the deterministic gates, the failure-class table and `just land`'s
criterion audit are all unchanged.

## Where this sits in the system of work

#376 states the target: eight processes, of which process 4 is Work Delivery. #377 is its MVP
walking skeleton, and its Out of Scope names "replacing the existing post-#317 inner Work
Delivery loop". Both leave the **interior** of a Work Run to the agent — #377's own stories say
each Work Run derives its own local implementation plan, and #381 says the controller observes
delivery rather than recreating it.

Ruling 1 specifies that interior and nothing outside it, with one exception recorded rather than
hidden: the handover refusal that makes the requirement mechanical touches post-#317 machinery
that #377 wants frozen. Ruling 2 belongs to ticket creation, which is why it must land before
#379 publishes obligations in another form. Ruling 3 belongs to the evidence process, which #384
owns and #387 reads.

Ruling 1's evaluation is not built here. #385, #386 and #387 already are the improvement loop,
including the separation of proposal from activation authority, and this design's kill criterion
is an input to the disposition #387 computes rather than a second mechanism beside it. Its
near-term form — sessions per landed Work Item against the frozen baseline above — needs no
ledger and can run from the dispatch records alone; the dollar form waits on the precondition.

Neither ruling 1 nor ruling 2 could be activated by #377's autonomous improvement cycle: its
allowlist covers prompt templates, agent briefing text and non-authoritative observatory
definitions, and explicitly excludes gates, review and adjudication rules, and landing authority.
These are exactly the class of change that MVP is forbidden from making by itself, which is why
they arrive with a human's authorisation attached.
