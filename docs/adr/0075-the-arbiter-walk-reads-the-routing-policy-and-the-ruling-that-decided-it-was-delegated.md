# The arbiter walk reads the routing policy itself, and the ruling that decided it was delegated

Delegated-decision: yes
Date: 2026-08-19
Stood-in-for: human sign-off on an amendment to a landed ADR — ADR-0071 ruling 4's routing-rung
passage, which amendment A8 rewrites — and on the two ownership statements that named closed #326 as
the rung's owner (`tools/dispatch.py`'s `candidate_refusal` docstring and the ADR passage itself);
the ADR amendment is a human sign-off gate in CLAUDE.md's list, taken on #391
Reviewed-by-human: pending
Supersedes: none — the decision it records is ADR-0071 amendment A8, which is marked inline in that
file at the passage it changes and indexed in its `Amended:` header; this ADR records the
delegation, and supersedes and amends nothing on its own account
Claimed: 0075 — after `git fetch origin` (`docs/adr/` on `origin/main` topping at 0074) and a sweep
of all 114 open issues' bodies for an ADR number at or above 0075, which returned two hits that
were numbers below the claim on opening and no live claim; the comment threads most likely to carry
a concurrent claim (#394, the live ADR-0013 thread 0074's own blind-spot note names; #417; #418)
were read as well and carry none. The blind window CLAUDE.md records — a claim whose issue closes
before its ADR lands — is covered by the rebase backstop, per the claiming protocol

## What happened

ADR-0071 ruling 4's arbiter walk excluded on routing refusals a *caller* supplied:
`arbiter._walk_first` took a `profile -> reason` mapping, fed from `just review-loop escalate
--routing-refusal`, and no other feeder existed. Round 3 of #361 recorded the consequence plainly:
the rung was "uncovered and, as of round 3, unowned" — an escalation dispatched without the flags
walks past a head the policy would refuse, a check that did not run reading as one that passed, on
the arbiter path that #318 and #361 had each already cost a full cycle.

Two surfaces named an owner, and both named **#326**, which had closed on 2026-08-14 before either
line was written: `tools/dispatch.py`'s `candidate_refusal` docstring and the ADR passage. Naming a
replacement owner was correctly treated as a decision rather than a repair, so #391 was filed for
the ownership question instead of an owner being invented.

## Decision

**Ruled on #391, under the standing authorisation: #391 is the owner, and the rung moves into the
walk.** The two pointers naming closed #326 are repointed at #391 — no existing issue is drafted in
as a substitute owner, because that is what produced the defect the first time. On substance, the
walk reads the routing policy for the issue itself rather than trusting flags a caller may or may
not pass: `arbiter._walk_first` runs `routing_policy.enforcing_match` per candidate — the landing
read, the same one `just land` runs — on inputs `just review-loop escalate` derives and no caller
declares. The policy is read off fetched `origin/main`, never the diff under judgement's own copy
(the trust rule `tools/land.py`'s `_routing_inputs` already states); the branch under review is
read off the review exchange's own ref `refs/heads/issue-<n>`, merge-base-relative. The
`--routing-refusal` flag is deleted, with no replacement seam — a flag a caller may not pass is the
trust hole, not the interface.

The ruling carried a **binding precondition**: establish first whether any current caller passes
those flags correctly, because a walk that reads the policy itself must not double-apply a refusal
a caller already supplied; if not separable, stop and report rather than ship a double refusal. It
was discharged before the change was built, and the discharge is the simplest case: **no caller
passed the flag.** Its only feeder was the flag itself; no document, brief composer or orchestration
instruction computes the mapping, and the tests passed empty ones. With no caller-supplied refusal
in existence there is nothing to double-apply, and the flag is deleted outright.

A rung that cannot read either input refuses the escalation by name rather than resolving past it
(#41: a check that could not run is not a check that passed) — an absent exchange ref and an
unreadable policy are facts and refuse; git that cannot be reached is a not-a-result. Against the
shipped policy the rung excludes nobody, because since ADR-0073 no row refuses a landing; it runs
anyway, and a refusing row is one table edit away from being honoured.

## Why this was taken under the standing authorisation rather than referred

The human's standing order of 2026-08-16 — *"resolve all required decisions and rulings requiring
human review by yourself using your own best judgement"* — covers exactly this residue: an ownership
decision #361's round 3 explicitly declined to take in the loop's own rounds, blocking a gap that
had already been stated on the record for a cycle. The orchestrator took the ruling on #391 and it
is quoted in full there; it is recorded as an orchestrator ruling, not a human one, so a later
reader can tell which authority it carries. Recording it here rather than letting the amendment
stand alone is ADR-0013's rule: a decision taken under the authorisation but not recorded is out of
policy, and the fix is to write the missing ADR.

ADR-0071's `Delegated-decision: no` marker is deliberately untouched, for 0074's own reason: it
scopes the original rulings the human took in session, not an amendment taken days later, and
flipping it would misreport the provenance of every ruling in that file. The delegation's greppable
trace is this file.

## What would overturn this

Stated so a reviewer can disagree by pointing at evidence rather than at taste (ADR-0019).

1. **The human rejecting A8 at sign-off.** This ADR is a stand-in for that sign-off, not a
   substitute for it.
2. **A caller the precondition's discharge missed.** The ruling's precondition rested on no caller
   passing `--routing-refusal`; a live script or brief that computed the mapping would have made
   the change a double refusal for that caller, which is the outcome the ruling said to stop and
   report rather than ship. None was found — the feeder was the flag alone — but a missed one is
   the named ground for reversal.
3. **The derived read proving the wrong read.** The walk uses `enforcing_match` — the landing read
   over the diff's own paths — rather than `advisory_match`, the dispatch-time issue-body read. The
   grounds: the #326 case the rung exists for was a diff-paths refusal, the deleted flag's own help
   text said "the diff's own paths", and the advisory read is seat-bound, so on a fixed seat it
   would refuse uniformly across every candidate rather than exclude any — not an exclusion rung at
   all, and a miscasting of the arbiter as a route taking the work. A live case where a refusal
   ought to have followed the issue body would reopen that choice.
4. **The trust split costing more than it holds.** The escalation derives inputs from git on every
   call, and an escalation that cannot read them now refuses where it previously resolved. If that
   refusal fires on arrangements the exchange protocol actually produces — an exchange ref shaped
   other than `refs/heads/issue-<n>`, a policy path moved — the cost is real escalations refused,
   and the input derivation, not the rung, is what would need revisiting.

## Scope

This records one delegated ruling and moves one rung's read. It does not decide what
`candidate_refusal` admits — the routing policy stays out of that function on its own stated rule
(a rung belongs there only where it is a function of `(lane, profile, seat)` alone), and the
walk-side read does not widen that rule. It does not widen routing class 6's path list or answer
ADR-0071's filed coverage question, and it does not touch the advisory read `just dispatch` runs.
