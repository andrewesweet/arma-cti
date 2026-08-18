# The retro journal lands under never-alone, and the ruling that decided it was delegated

Delegated-decision: yes
Date: 2026-08-17
Stood-in-for: human sign-off on an amendment to a landed ADR — ADR-0071 ruling 3, whose closing
sentence A4 strikes — and on the retro-seat wording in `AGENTS.md` (`CLAUDE.md` is the committed
symlink to it) that carries the same exception to the surface an agent reads before the skill;
both are human sign-off gates in CLAUDE.md's list, taken on #397
Reviewed-by-human: pending
Supersedes: none — the decision it records is ADR-0071 amendment A4, which is marked inline in
that file at the passage it changes and indexed in its `Amended:` header; this ADR records the
delegation, and supersedes and amends nothing on its own account
Claimed: 0074 — originally 0073, claimed against `docs/adr/` on `origin/main` topping at 0072
(`be3d846`), and renumbered on the review of this branch after #406 landed its own ADR-0073
(`51c2ffe`, 2026-08-18) first: the collision the original claim's rebase backstop exists to
catch, found late because the branch rebased over #406's landings without renumbering. The
renumber's scan: `git fetch origin` (`docs/adr/` on `origin/main` topping at 0073) and a sweep
of all 100 open issues' bodies and comments for an ADR number at or above 0074, which returned
nothing. The scan was checked against a known answer rather than trusted empty: the same comment
query for 0073 returns issue 397, and for ADR-0071 returns issue 317. One live blind spot,
recorded rather than papered over — #394's fix round is ruled to write an ADR-0013 record of
its own and has not claimed a number on its thread, so it may claim 0074 concurrently. The
rebase backstop is what catches that, per CLAUDE.md's claiming protocol

## What happened

ADR-0071 ruling 3 ended *"Never-alone does not apply to retros, because nothing lands"*, and
also deferred one question to the `/retro` skill rewrite: whether the journal entry in
`docs/process-log.md` becomes a filed item or the single named exception to "lands nothing".
#330 settled it as the exception and flagged, rather than resolved, the contradiction that
creates with the ruling's closing sentence — leaving the conflict standing on the record and
naming two remedies, an ADR amendment or the human ruling the journal exempt from review.

#397 found that the three surfaces an agent reads *before* that skill still stated the
prohibition flat, so an agent met the old rule first and the new one only if it read that far.
Fixing them requires choosing between the two remedies, because the surfaces cannot state a
resolution the record does not have.

## Decision

**Option 1: the exception stands, and never-alone applies to it.** ADR-0071 ruling 3's closing
sentence is struck by amendment A4; the journal entry lands under ruling 4 like any other change
— a reviewing instance in a different session, a lander who may be the proposer — and everything
else a retro produces is still a filed item.

The alternative — a first entry on `config/review-exemptions.json` exempting the journal from
review — is declined. Three grounds are recorded in A4 itself. A fourth, found in review and
decisive on its own: the exemption route needs the amendment **as well**. Ruling 3's stated
reason for the exemption from never-alone is that nothing lands, and under the exemption route
the journal still lands and is merely unreviewed, so the sentence is false either way and has to
be struck under either option. The two mechanisms are therefore not a trade-off; one is a
superset of the other, costing an amendment plus a first entry on a list whose own text says it
ships empty.

## Why this was taken under the standing authorisation rather than referred

The human's standing authorisation of 2026-08-17 — *"resolve all decisions and rulings on my
behalf in consultation with a fable/high advisor according to your collective best judgement"* —
covers exactly this residue: a choice #330 identified, both of whose branches were already
written down, blocking four surfaces from agreeing with each other. A `fable`/high advisor was
consulted before the ruling, per the authorisation's terms. Recording it here rather than
letting the amendment stand alone is ADR-0013's rule, quoted: *"A decision taken under the
authorisation but not recorded this way is out of policy, and the fix is to write the missing
ADR, not to widen the index."*

**`docs/adr/0071-…:3`'s `Delegated-decision: no` is deliberately untouched.** That marker scopes
the original rulings, which the human took in session across five reviews; it does not scope an
amendment taken six days later, and flipping it would misreport the provenance of every ruling
in that file. The delegation's greppable trace is this file.

## What would overturn this

Stated so a reviewer can disagree by pointing at evidence rather than at taste (ADR-0019).

1. **The human rejecting A4 at sign-off**, in favour of the exemption route or of dropping the
   exception entirely. This ADR is a stand-in for that sign-off, not a substitute for it.
2. **ruling 6's pre-registered question answered "no" at a retro** — that pre-landing review of
   gated work finds no defect the gates and post-landing review would not. That is the one cause
   `config/review-exemptions.json` admits for its own growth, and it would make the exemption
   route admissible on its own terms rather than by an agent's convenience. It cannot arrive
   before the observatory (#336) exists to produce it.
3. **A review round on a journal diff that cannot do its job.** The entry is one terse appended
   paragraph, and the claim behind option 1 is that an independent read of a self-report is worth
   most where the writer has the strongest interest in how it reads. Several cycles of journal
   reviews returning no finding at all, against post-landing reads that do find something, would
   be evidence the round is theatre on this artefact specifically.
4. **The refusal path proving to cost a journal entry rather than delay one.** A4 states that the
   journal lands only from a retro dispatched against a numbered issue, because `just land`'s
   never-alone rung refuses an unnumbered tree and an issue with no dispatch records. If attended
   retros recur and their entries go unwritten rather than re-dispatched, the constraint is
   buying the archive of record less than it costs it, and the exemption route gets stronger.

## Scope

This records one delegated ruling. It does not decide the residue A4 creates elsewhere: the
`/retro` skill's step 4 still tells its reader the conflict is open, and `tools/ledger.py` still
books the `retro` seat as landing nothing. Both are filed as their own items against #397, and
neither is settled here.
