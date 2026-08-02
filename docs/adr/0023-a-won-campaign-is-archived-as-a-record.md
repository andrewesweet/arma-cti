# A won Campaign is archived as a record of what happened, not a state to resume

Delegated-decision: yes
Date: 2026-08-01
Stood-in-for: snapshot schema semantics — what `docs/mvp-scope.md`'s word "archived" means at
ADR-0008's persistence boundary, and what a completed Campaign leaves behind for Phase 2 to
inherit (#35)
Reviewed-by-human: 2026-08-02

`docs/mvp-scope.md` (2026-07-30) says that on victory the Campaign is "marked complete, end screen
with summary from telemetry, archived; fresh Campaign next session". #35 has to build that, and
"archived" is the one word in the sentence that does not decide itself. ADR-0008 splits persistence
into strategic state that a snapshot carries and tactical state that is regenerated; an archive is
neither of those things, and choosing its shape in passing would hand Phase 2 a format nobody
decided.

**An archive is a record, never a save.** What is written when a Campaign is won is a
telemetry-sourced summary of what happened: winner, condition, the in-game moment, the Base that
fell, the board as it finally stood, income paid per side, Commands accepted per side, Squads lost,
and the HQ destruction rows. Nothing reads it back — not the daemon, not a later session, not a
rule. It is evidence and an end screen, in the same category as the telemetry file it sits beside
and is built from.

**"A fresh Campaign next session" is therefore structural rather than a rule.** Nothing in the
archive is loadable, so the next boot has nothing to resume and starts a new Campaign by
construction. The alternative — archiving a resumable snapshot and then remembering not to resume
it — makes the freshness a thing that can be forgotten, and the forgetting is silent.

**Reading telemetry to build the summary does not cross ADR-0003.** That decision makes the
snapshot authoritative for *campaign state*: the point is that no rule may consult a log. A summary
is consulted by nobody and no Campaign resumes from it. The reason to source it from telemetry
rather than from live campaign state is the opposite of laziness: an end screen assembled from
state could say something the log does not, and a Campaign with two accounts of itself has none.

**The summary counts rather than lists.** It rides the `campaign_won` effect to the world, and a
`callExtension` return truncates past 10,240 bytes in silence (ADR-0004), so a summary whose length
tracked the length of the Campaign would fail on exactly the long Campaigns worth summarising.

**Consequences for Phase 2.** When snapshots arrive, victory is expected to *delete or retire* the
resumable snapshot and write this record; the two are separate artefacts with separate lifetimes and
separate schemas, and neither is a version of the other. ADR-0008's amendment that "Base
alive/destroyed" arrives with Phase 2 is superseded for the Observation: HQ status is public in
every view from Phase 1, because ADR-0012's #27 amendment already made it a public fact and
`docs/mvp-scope.md` makes the win conditions the scoreboard. The snapshot half of that line stands.

**Rejected.** *(a) Archive the snapshot* — makes the archive a save that must not be loaded, which
is a rule to remember rather than a shape that cannot be got wrong, and freezes a Phase-2 schema
inside a Phase-1 ticket. *(b) No archive, telemetry is enough* — the telemetry file is per-run
scaffolding that the harness truncates at bring-up, so "the record of every Campaign ever played"
would live in a file whose first act each session is to empty itself. *(c) Build the summary from
live campaign state* — cheaper, and it gives the end screen and the log licence to disagree.
*(d) Put the summary in a database* — nothing reads it back; a file per Campaign is the whole
requirement, and anything more is a query interface nobody has asked for.

**What would overturn this.** A Phase-2 requirement to *continue* a completed Campaign — a second
season on the same board, say — would need a resumable artefact at the end of a Campaign, and this
is the decision to revisit rather than to work around. Playtest wanting a campaign history browser
would not: that reads these records, which is what they are for.
