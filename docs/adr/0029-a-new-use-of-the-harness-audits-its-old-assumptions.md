# A new use of the harness audits the assumptions its old use shared with the code

Delegated-decision: yes
Date: 2026-08-01
Stood-in-for: human sign-off on changes to CLAUDE.md and the project skills — the seventh retro's amendment batch (five issues: #38, #43, #21, #36, #44)
Reviewed-by-human: pending

## The decision

Two related sentences land where their readers work, and the retro starts surfacing the
human's review-queue depth.

1. **The exploration-as-audit pattern is recorded in `docs/regression-tier.md`**, beside
   the #44 finding it generalises: a capability exploration doubles as an audit of the
   assumptions the current harness shares with the code it tests — budget for what it
   flushes out and report it as a first-class finding, not a detour.
2. **The assert-the-decision rule gets a one-line pointer in CLAUDE.md's probe
   paragraph**, beside the probe-window rule it is the sibling of: a probe bets on the
   decision the code under test owns, never on a world-owned outcome such as a firefight.
3. **The retro skill's step 3 now reports the `Reviewed-by-human: pending` count each
   retro.** Sixteen ADRs (0013–0028) sit pending, growing roughly four per cycle; the
   queue's depth was visible only to whoever thought to grep. Clearing it stays entirely
   the human's cadence — the amendment makes the number visible, nothing more.

## The evidence

- **Exploration-as-audit, two instances.** Building the serial runner (#23) found the
  harness mistyping every in-world failure `assertion_failed`. Running two slots at once
  (#44) found the shim resolving its daemon from `CTI_DAEMON_ADDR`, which the harness
  never set — latent in every serial run because the defaults agreed, and surfaced as two
  runs silently merging, one slot reporting PASS on the other's world. Neither defect was
  reachable by the use the harness already had.
- **Assert the decision, one expensive lesson.** #38 burned seven probe runs on a
  fighting garrison: a mass that won, a mass that lost, and a run where the observing
  Squad died before the sampler ticked so the decision was unobservable. The fix —
  `massed-assault` asserts Contact, band, force and Orders, and leaves the fight to
  `base-assault` and `campaign-end` — is documented at length in the tier doc by #38's own
  landing; what was missing was the one-line rule where probe authors start.

## The rest of the batch this ADR records

Applied at the same retro, under the same standing authorisation:

- **`docs/agents/recovery.md`**: gains its status marker, `validated ×2` — first two real
  uses (one death mid-Arma-run on #21, one silent stall), both briefed to the document,
  both clean — and a "Recognising death" amendment the second use exposed: an agent can
  stop mid-turn with its run still live and a completion notification firing anyway;
  that is death with live work, and the live run's eventual output is still not a result
  (ADR-0022).
- **Marker corrections in CLAUDE.md**: the ADR-0026 batch recorded probe-window ×4 and
  ADR-claiming ×3, but only the exemplars were appended — the ×N labels stayed at ×3/×2.
  Corrected to match the process log.
- **Marker bump**: probe-window rule ×4 → ×5 (#43: `two-commanders` was deliberately not
  converted to an event-driven exit because its soak carries #17's measured drain
  extremum, which shrinks with its window — the rule's reasoning applied as a reason not
  to shorten).
- **retro skill**: `validated ×6` → `×7`, self-amended (the queue-depth sentence).

## Deliberately not decided

- **A failure class for a false green.** #44's merged run reported PASS on another
  slot's world — "the harness lied green" — and nothing typed it. Weighed and declined:
  the classes type verdicts the harness emits, and a harness lying green cannot classify
  its own lie; a class nothing can emit is decoration. The real defence is structural and
  already recorded where it will be built — #47's "a slot boundary is only real where
  something reads it", every per-slot value with a named consumer.
- **A rule for how explorations conclude.** #40 closed don't-build, #44 closed
  ADR-plus-follow-up with the port precondition explicitly left to the human, #43 closed
  convert-in-place — three different right endings, all reached unprompted under the
  existing decision-ticket and cost-control text. Three correct conclusions are evidence
  the triage needs no more words.
- **Anything about tripwires.** #36 landed four minutes ahead of the 30-minute trigger
  the tier doc set two cycles earlier — the pattern's first firing, already recorded in
  that doc by #36's own landing.
- **A mechanism for marker counts.** The ×N drift above is the cost of hand-maintained
  counts; one instance, caught by the process log at the next retro, which is the
  mechanism working.

## Overturned by

- A capability exploration that lands finding nothing while a shared-assumption defect
  ships anyway — then the sentence is comfort, not audit, and the defence has to be
  structural (named consumers, world-identity in verdicts) everywhere, not just in #47.
- The queue-depth report changing nothing across several retros while the queue grows —
  then visibility was not the constraint, and the process should ask the human for a
  cadence rather than a number.
- A probe that honestly asserts a decision and still flakes on acquiring the Contact that
  feeds it — then the boundary between "decision" and "world-owned" is drawn wrong, and
  the rule needs the #28 treatment (readiness, geometry) rather than repetition.
