# The allowlist is the gates' mechanical face, not their repeal

Delegated-decision: yes
Date: 2026-08-02
Stood-in-for: human sign-off on changes to CLAUDE.md, the project skills, and the agent
process docs — the eleventh retro's amendment batch (the review burn-down's completion:
~25 issues closed since `82fe67e` across the #74/#75 and #116/#119 waves and the Python
and SQF tail tracks, plus #120 raised here)
Reviewed-by-human: pending
Claimed: comment on #120, 2026-08-02, after `git fetch origin` (origin/main tops at
0037) and a scan of open-issue comments found no claim above 0037 — the #47 pool agent
had claimed none

## The decision

Five amendments. **The first is a change to CLAUDE.md's sign-off-gates paragraph itself
— read it first at review.**

1. **CLAUDE.md's gates paragraph reconciles the documents that disagreed on paper.** The
   #94 config review (findings 13–16) found `.claude/settings.json` pre-approving
   exactly the surfaces CLAUDE.md declares sign-off-gated: `Edit(docs/**)` covers the
   ADRs, and `Edit(CLAUDE.md)`, `Edit(CONTEXT.md)`, `Edit/Write(.claude/skills/**)` are
   named outright. The truth is that the allowlist is how the human's standing
   authorisation (ADR-0013) operates mechanically — every gated landing under it has
   carried a `Delegated-decision: yes` record — but on paper the two documents flatly
   contradicted. One sentence in the gates paragraph states the relationship: the
   allowlist is the authorisation's mechanical face, mechanical permission discharges
   nothing, and a gated change still lands only with the human's approval or an
   ADR-0013 record. This narrows nothing and widens nothing; it writes down the
   practice every delegated batch has already followed.

2. **The recovery runbook's briefing section gains the evidence-not-inference
   sentence.** One resumption briefing this cycle asserted from a worktree's "clean,
   zero ahead" that announced work had died uncommitted — but the agent had pushed and
   then continued, so the same evidence meant landed, not lost. The two-sided contract
   worked (the resumed agent's fetch-and-verify side caught it, corrected the
   orchestrator, and redid nothing), and the error cost nothing — but the mis-read is
   the project's recurring shape, an inference presented as observation (`pgrep -f`,
   `tasklist.exe`, the daemon-address defaults), appearing for the first time on the
   briefing side. One sentence: the briefing states what the evidence shows, not what
   it implies; landed-vs-lost is the resumed agent's to verify on wake.

3. **The issue-tracker closing section names the trailer bypass.** A `Closes #89`
   commit trailer auto-closed the issue on push with two acceptance boxes unticked,
   skipping the criterion-by-criterion closing audit the section requires; the agent
   noticed and reopened with an honest scope narrowing. One instance, self-corrected —
   but the mechanism *silently contradicts a written rule*, the same document-vs-
   mechanism shape as amendment 1, so the fix is a sentence, not trust: on an issue
   carrying acceptance criteria, reference the commit without a closing keyword and
   close by hand.

4. **CLAUDE.md's Contract names the scheduler adapter that exists.** The bare-`sleep`
   exception read "seeded PRNG and CBA scheduler adapters only" — an adapter that never
   existed, so six loops hand-rolled their pacing until #85 built
   `cti_fnc_everyInterval`, which is deliberately not CBA (its header records the
   dependency reasoning: CBA would put a runtime dependency on every machine to replace
   eleven lines of engine scheduler). The Contract now names the adapter that is, with
   the not-CBA pointer, so the exception stops naming a thing that does not exist.

5. **Marker moves** (each in the same edit as its exemplar, per the retro skill's
   step 5): recovery runbook `×5` → `×7`, amended (sixth and seventh briefed
   resumptions, both clean; the corrected-briefing instance is the resumed-agent side's
   first earn against a wrong briefing). Convention-lands-with-instance `×1` → `×2`
   (#116's fix landed the vacuity sentence with its first instance, exactly as the
   tenth retro routed it). Retro skill `×10` → `×11`, no self-amendment needed.
   Failure classes stay `×7`, probe-window `×6`, elimination-context `×2`,
   ADR-claiming `×4` — no qualifying use this cycle (this batch's own fetch-and-scan
   claim is the rule operating, not an earn).

Also raised, not an amendment: #120 — `block-no-verify.py`'s false positives on prose
quoting the flag are now a reproduced class, not a tolerated quirk (heredoc text
2026-07-30, an issue-comment body during the burn-down, and a third live denial while
filing #120 itself). The hook stays; the fix is code work with acceptance criteria,
including putting its decision logic under `just unit` per #83's precedent.

## Rejected alternatives

- **A "re-score after burn-down" step in the directed-review pattern.** The seven
  reviews scored 8.2–9.75 against a 9.5 target and the burn-down fixed every actionable
  finding within two days (resilience raised from ~5), so the achieved numbers are
  stale — but a standing re-score step is a further verification pass, which CLAUDE.md
  forbids adding, and ADR-0037's supplemental single-observation ticket already *is*
  the re-scoring vehicle whenever someone wants the number. Left to the next directed
  pass.
- **A rule from #119's teardown decision or the tail tracks' fix reasoning** (the host
  guard kept ownership-blind on principle; #101's force_limit measured against the
  10,240-byte wire rather than guessed; #117 elevated to the sign-off-gated convention
  proposal #118 rather than fixed ad hoc). Each is recorded at its site — guard header,
  probe header, proposal issue — which is the exemplar route working as designed.
- **Treating #89 as briefing-note only** (no doc change). Rejected for the reason in
  amendment 3: one self-corrected instance would earn a note, but a mechanism that
  silently bypasses a written audit earns the sentence that closes the contradiction.
- **Accepting the hook false positives a second time.** The 2026-07-30 acceptance was
  context-bound to one class with an obvious workaround; a reproduced second class plus
  a third live denial while documenting it is that elimination's context no longer
  holding.

## What would overturn this

- The human rejecting amendment 1's sentence — the gates paragraph reverts to its prior
  wording and the settings/CLAUDE.md contradiction goes back to the human to resolve
  the other way (e.g. by narrowing the allowlist).
- A delegated batch landing on a gated surface *without* an ADR-0013 record while
  citing the allowlist as permission would show the sentence read as a loosening, and
  it should be replaced by a mechanical gate instead (per #94 finding 15).
- A resumption briefing that states evidence faithfully and still corrupts the resumed
  work would show the contract needs more than the sentence.
- A closing-keyword trailer used deliberately on a criteria-free issue is fine; one
  landing on a criteria-carrying issue again would escalate the sentence to a hook.
- The human flipping this ADR to rejected unwinds the batch: every edit is one sentence
  or paragraph, named above, and reverts cleanly.
