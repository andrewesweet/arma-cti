# A gated human reviewer satisfies never-alone, and the mechanism does not know it yet

Delegated-decision: no
Date: 2026-08-25
Supersedes: ADR-0071 ruling 4's unstated assumption that the verdict clearing a landing comes
from a model instance. The ruling's constraint is on unilateral action, not on the reviewer's
substrate, and this record says so rather than leaving the narrower reading to be inferred from
the tooling that implements it
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

This is a statement about what the rule was always for, recorded because the narrower reading —
that only a model instance can clear a landing — was never written down anywhere and was
therefore being inferred from the tooling. A rule inferred from its implementation is a rule
that changes whenever the implementation does.

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

## The gap between this ruling and the mechanism

**There is no path today by which a human verdict can be recorded, and this ADR does not build
one.** `review_exchange.record_verdict` accepts the issue, the reviewed SHA, the findings and
the diff identity, and deliberately accepts nothing about who reviewed; the identity comes from
`derive_binding`. `just land` then refuses `no_verdict` where no readable verdict record exists.
So a human review satisfies the rule and does not satisfy the gate.

Stated rather than smoothed over, because the direction of the mismatch matters: the mechanism
is **stricter** than the policy, so it fails closed. Nothing lands wrongly while the gap is open;
some things simply cannot land the way this ruling permits. Until the path exists, a landing is
cleared by a dispatched instance as before, and a human review is additional assurance on top.

### What building the path must argue, not assume

A declared reviewer is a declaration, and #322's reasoning was that the reviewing identity must
**not** be declarable — which is why `derive_binding` exists and why `review-loop author
--profile` declares an *author* and never a reviewer. A mechanical mirror of that verb would
walk into the reasoning it was built against.

The distinguishing argument is available and must be made explicitly in whatever records it: a
human declaring their own review is a different trust class from an agent declaring a peer's,
because the human is the authority the gates already defer to and has no dispatch to
misattribute. A future reader will find `derive_binding`'s own comment saying identity is never
declared, and is entitled to an answer that is written down rather than reconstructed.

The work is not scoped here. It is review-and-adjudication machinery, so it sits outside the
autonomous improvement allowlist #377 defines and arrives by a human's hand or not at all.
