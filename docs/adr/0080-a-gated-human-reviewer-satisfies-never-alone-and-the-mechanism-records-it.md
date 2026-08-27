# A gated human reviewer satisfies never-alone, and the mechanism records it

Delegated-decision: no
Date: 2026-08-25
Supersedes: ADR-0071 ruling 4's narrower reading that only a model instance can clear a landing —
a reading ADR-0071's text supports, but which this record rules is not what never-alone was for.
The ruling's constraint is on unilateral action, not on the reviewer's substrate, and this record
says so rather than leaving that narrower reading to be inferred from the tooling that implements
it
Supersedes: none otherwise — ADR-0071 rulings 1 through 7 stand, `review_same_profile` remains
absolute, and the derived reviewing identity for an agent reviewer is untouched
Reviewed-by-human: the human's ruling of 2026-08-25 — "Never alone requires that a single actor
does not both propose and enact a change unilaterally. Both a separate agent actor (a different
agent instance) and a human actor (me) acting as gated reviewers satisfy the 'not unilaterally'
constraint" — given on being told that no mechanical path exists for a human verdict
Claimed: 0080 — after `git fetch origin` (`docs/adr/` on `origin/main` topping at 0078), a scan
of open issue bodies, and a `gh search issues` query for `ADR-0080` returning nothing. 0079 is
this session's, pushed to `refs/heads/adr-0079` and cited in comments on #379, #382, #383, #384,
#387, #526, #531 and #535

## The ruling

Never-alone bars a single actor from both proposing a change and enacting it unilaterally. Two
kinds of actor satisfy the constraint as gated reviewers: **a different agent instance**, as
before, and **the human**.

This is a statement about what the rule was always for, recorded because ADR-0071's text and the
tooling supported the narrower reading — that only a model instance can clear a landing — even
though that reading was not what never-alone was for. A rule inferred from its implementation is a
rule that changes whenever the implementation does.

## Why this is not a weakening

The property never-alone protects is that nobody clears their own work. A human reviewing an
agent's change is not that agent, is not in that agent's session, and has no stake in the
change passing. On the axis the rule cares about, a human reviewer is at least as independent
as a second model instance, and on one axis strictly more so: a model reviewer shares a
training distribution with the author and a human does not.

What would be a weakening, and is not permitted here: the author declaring itself reviewed.
`review_same_profile` is untouched and remains absolute, and a human who wrote a change cannot
review it either — the constraint is on the actor, not on the actor's kind.

## What this does not reach

**The sign-off gates are orthogonal and unchanged.** CLAUDE.md's list of human-gated surfaces —
`CONTEXT.md` terms, ADRs, acceptance specs, this file, the project skills — is about *authority
to decide*. Never-alone is about *not deciding alone*. A human approving a gated change has
exercised the first and, if they also reviewed it, the second; the two are satisfied separately
and neither implies the other.

**The derived identity for agent reviewers stays derived.** Where a dispatched instance reviews,
`derive_binding` continues to read the identity from the records the dispatcher wrote, taking
nothing from the caller.

## How the mechanism implements this ruling

**The mechanism now implements this ruling.** `review_exchange.record_human_verdict` records a
human verdict bound to the exact reviewed SHA and diff identity; `just land` accepts it and emits
`reviewer_kind=declared review_dispatch=none`. The dispatched-session refusal and
author-cannot-review check remain, and the agent path still derives its reviewing identity from
the dispatch records.

The human route is separate from the agent route and retains the same mechanical floor: a missing,
unreadable or incorrectly bound human record does not clear a landing, and a human reviewer whose
profile the issue's records place on the work is refused. The mechanism therefore implements the
policy without weakening `review_same_profile` or the derived identity of agent reviews.

### What the path preserves

A declared reviewer is a declaration, and #322's reasoning still governs the agent path: the
reviewing identity must **not** be declarable, which is why `derive_binding` exists and why
`review-loop author --profile` declares an *author* and never an agent reviewer. The human route
is a distinct trust class rather than a mechanical mirror of that path.

The distinguishing argument is recorded in the mechanism: a human declaring their own review is a
different trust class from an agent declaring a peer's, because the human is the authority the
gates already defer to and has no dispatch to misattribute. The separate human-verdict record
labels that route `reviewer_kind=declared`, while the agent record keeps its derived identity.

The implementation was not scoped here. It is review-and-adjudication machinery, so it arrived
separately by a human's hand as #586, outside the autonomous improvement allowlist #377 defines.
