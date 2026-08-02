# A single observation is a sufficient review trigger, and the class table is an assertion surface

Delegated-decision: yes
Date: 2026-08-02
Stood-in-for: human sign-off on changes to CLAUDE.md, the project skills, and the agent
process docs — the tenth retro's amendment batch (eight issues closed since `fa22f54`:
fixes #98/#99, #96/#97, #80/#102; reviews #107, #111; plus #104/#106 raised and the
#108–#118 findings)
Reviewed-by-human: pending
Claimed: comment on #116, 2026-08-02, after `git fetch origin` and a scan of open-issue
comments found no claim above 0036

## The decision

Five amendments.

1. **`docs/agents/issue-tracker.md`'s directed-review section gains the supplemental
   single-observation pass.** Twice on one day the human turned a single concrete
   sighting into a tightly scoped single-lens ticket, and both outperformed the broad
   pass on their dimension: two asides became #107 (the systematic engine-idiom sweep
   #56 never ran — six firm wiki-cited hits, two data structures accepted and four
   rejected against a stated bar) and one hand-rolled-guard sighting became #111 (all
   22 server guards unreachable, 17 dead sentinels, a probe green with its client leg
   unexercised — #116 — and a sign-off-gated convention proposal, #118). The sighting
   itself is the human being good at their job and no process text manufactures that;
   what the process *was* doing wrong is implying a review needs a whole-project
   occasion. The paragraph removes that assumption and adds one discipline the two
   instances shared: the observation supplies the scope, and the ticket does not widen
   beyond it.

2. **CLAUDE.md's probe paragraph gains the assert-your-staging sibling.** The world can
   refuse staging silently: the Functions Library `compileFinal`s every `cti_fnc_`, so
   `schema-stale`'s first draft assigned a stub, the engine ignored the assignment with
   one log line, and a green run tested the real function while reading as a stub test
   — caught only because the probe asserted outcomes, not staging (#80). Second surface
   of the shape in two waves: #83's review found the spike shell staging without
   checking it. One sentence beside the bet-on-the-decision rule, pointing at the tier
   doc's full write-up, which already existed and is not duplicated.

3. **`docs/regression-tier.md` records the lock and the host guard operating in anger.**
   The serialisation section's validated-in-anger sentence gains the queue side (the
   review-phase burn-down put three concurrent fix agents' regress runs through the one
   lock across an evening, cleanly), and the host-guard paragraph gains its first live
   firing: run `20260802T033020Z-contact-decay` met the human's live game and refused
   in 2 s, `infra_unavailable`, "arma3_x64.exe is in the Windows process list — that is
   a play session, not ours", before any server launched. Both were design promises;
   both are now observations with evidence paths.

4. **Marker moves**: failure classes `×6` → `×7` — the table became an assertion
   surface: three red-by-design probes name the class they expect (`schema-stale` →
   `schema_stale`, `daemon-restart` and `loop-watch` → `node_crashed`), the first time
   `schema_stale` has fired at all and the first time a class is something a probe
   demands rather than something a failure receives. Retro skill `×9` → `×10` (tenth
   use, no self-amendment needed). Probe-window stays `×6`, recovery runbook stays
   `×5`, elimination-context `×2`, convention-lands-with-instance `×1` — no qualifying
   use this wave.

5. **The vacuity convention is adopted but lands with #116's fix, not before it.**
   Third instance of a probe (or leg) reading green while asserting nothing — #38's
   vacuous drive, #107's dead computed massing value, #116's off-by-default client leg
   (with #96's honestly flagged vacuous `replied` leg alongside) — which is this
   project's bar for codifying. The rule: a probe's optional legs default on in the
   corpus run, and a leg that did not run surfaces in the verdict as `unverified`,
   never as green. Per CLAUDE.md's convention-lands-with-first-instance rule the doc
   sentence belongs in the same commit as the mechanism, so it is directed onto #116
   by comment rather than landed here.

## Rejected alternatives

- **A transferable rule from the wave's fix-agent reasoning quality** (restart refused
  for honesty on #102, freeze-not-announce on #96, status-not-error on #97, one lock
  rejected against a single-threaded server on the resend case on #98). Rejected:
  each rejection is recorded at its site (function header, ADR-0036, issue thread),
  which is the exemplar route ADR-0026 chose already working as designed — a rule
  distilled from four good judgements would be the over-prescription the retro skill
  warns against.
- **Landing the vacuity rule in the tier doc now.** Rejected: it would be a convention
  living only in a document, the exact failure the convention-lands-with-instance line
  exists to stop; #116's fix is its first instance and carries it.
- **A probe-window or timeout earn from #106.** Rejected: the campaign-end flake report
  *applies* the rules (refused quarantine, refused a bigger window, asked whether the
  assertion is aimed at the right subject) but the decision is open — an earn records
  a resolution, not a well-framed question.
- **Extending CLAUDE.md's lock parenthetical with the contention evidence.** Rejected:
  that sentence proves the release-on-death property, which contention does not bear
  on; the tier doc is where the serialisation story lives and it got both sentences.

## What would overturn this

- A single-observation ticket that sprawls, or whose findings are noise against the
  broad pass, would show the trigger sentence needs the occasion bar back.
- A staging refusal that outcome assertions do *not* catch would show the sibling
  sentence understates the problem and a runner staging-verification hook is needed
  (the tier doc already names the missing hook).
- #116's fix landing without the convention sentence — or the sentence landing while
  legs stay silently skippable — would show the ride-the-fix routing failed and the
  rule should have landed here after all.
- The human flipping this ADR to rejected unwinds the batch: every edit is one
  paragraph or sentence, named above, and reverts cleanly.
