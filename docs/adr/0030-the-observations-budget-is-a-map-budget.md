# The Observation's budget belongs to the map, not to the Squad count

Delegated-decision: yes
Date: 2026-08-01
Stood-in-for: human sign-off on an ADR-0012-adjacent wire-format decision — #26's ceiling, re-measured after #27, #28 and #35 moved it
Reviewed-by-human: 2026-08-02

## The decision

The Observation's size budget is checked per **map**, at authoring time, against the worst case
that map's manifest admits. `budget.squad_ceiling` (`observation.squad_ceiling` until #78) answers "how many Squads a side can this
island carry", `just unit` refuses a manifest that cannot answer at all, and the SQF guard in
`cti_fnc_commanderView` stays as the backstop it always was rather than the place the problem is
found.

Nothing else changes. The wire format keeps its keys, the Observation stays one whole picture, and
the only encoding change taken is that a Contact's age is truncated to whole seconds where it
is computed.

## Why the question changed

#26 was filed against a document that carried both sides' rosters, and concluded: *the island's
size is nearly irrelevant; the binding constraint is Squad count*, about 35 a side. Three changes
since have inverted that.

#27 removed the enemy roster from a Commander's view entirely and dropped the per-Squad `side`
field with it. #28 filled the hole with **Contacts** — at most one per place. #35 added HQ status,
54 bytes, bounded by the map's two Bases.

The enemy term therefore stopped growing with enemy force size and started growing with **place
count**, and place count is the map. Measured on the worst case each schema field admits, envelope
included, against the 9,216-byte guard:

| Objectives | bytes with no Squads at all | Squads a side before the guard |
|---|---|---|
| 8 (Stratis) | 1,611 | 71 |
| 20 | 3,425 | 52 |
| 30 | 4,941 | 38 |
| 40 | 6,451 | 24 |
| 50 | 7,969 | 11 |
| 60 (Altis-ish) | 9,475 | **none** |
| 90 | 14,039 | **none** |

The last two rows are the finding. A sixty-Objective island spends its entire budget on the ground
itself: there is no Squad count small enough, and an empty Campaign on a freshly loaded map would
truncate. #26's worry about Altis was right and its diagnosis was wrong — the economy was never the
mechanism, the geography was, and it arrived by a route that did not exist when the issue was
written.

That is why the check is per map. A ceiling expressed in Squads is a number nobody is in a position
to enforce: it depends on a manifest, it is settled before play begins, and the thing that violates
it is an authoring act rather than a purchase. `just unit` is where authoring acts are judged.

## What was taken, and what was not

**Taken: truncating a Contact's age.** The subtraction that produces an age renders as
`47.29999999999927` — seventeen characters, once per place. The planner reads it as a freshness
ratio against a window measured in minutes, so nothing downstream can tell. Truncated in
`Contacts.aged_to` rather than in `serialise`, so the document stays a rendering of what the
Commander holds rather than a lossy version of it. It removes false precision that was never true.

This ADR first took a tenth of a second. The human's review of it (#134, 2026-08-02) narrowed that
to a **whole** second, on the ADR's own reasoning: a window measured in minutes cannot tell a tenth
from a whole any more than it could tell a tenth from the raw float, and whole seconds are cheaper
on the wire the ADR exists to defend. **Truncated, not rounded** — an age that rounded up would
read younger than the Contact is, and a Commander told a sighting is fresher than it was is the
wrong direction to be wrong in. The per-map table above was re-measured against the narrower form.

**Not taken: positional encoding** (#26's own first lever — dropping the repeated keys, so a Squad
reads `["WEST-12","weapons",8,"capture","kavala","kavala"]`). Measured at 60 Objectives and 32
Squads it cuts 11,932 bytes to 8,172, and re-keying the owners map by side takes it to 7,770 — a
real 35%. It is not taken now for two reasons. Stratis sits at 1,611 bytes of a 9,216-byte budget,
so there is nothing to buy. And 35% buys one band of island size and not the one that matters: a
ninety-place map is still over the guard afterwards. It would be spending the wire's readability —
every SQF reader, every log, #18's map UI — on a reprieve rather than a fix.

The trigger for revisiting is mechanical rather than a judgement call: the per-map test failing
when a second map is authored.

**Not taken: capping how many Contacts a Commander carries.** This is the only lever that actually
scales to a ninety-place island, because it is the only one that stops the enemy term tracking the
map. It is also not a size optimisation — it decides what a Commander is allowed to know, which is
a gameplay decision behind CLAUDE.md's sign-off gate. Named here so that a future large map has a
lever to reach for, and deliberately left unreached.

**Not taken: raising the cap.** 10,240 is the engine's number (ADR-0004), not ours.

**Not taken: splitting the Observation by change rate, paginating, or chunking.** #26's acceptance
criterion is that the Observation stays a whole picture, and ADR-0012 puts chunking in the shim's
framing layer for Phase 2 to decide against the snapshot schema. **Delta observations** stay
rejected on #26's own reasoning: a delta is an event, and losing one corrupts the picture rather
than being superseded by the next.

## Consequences

`INTACT` and `DESTROYED` move from `campaign.py` to `observation.py`, which is where the document
that carries them is defined and where the budget has to know how wide the widest word is;
`campaign` re-exports them, so `campaign.INTACT` still reads. The worst case is assembled from each
vocabulary where that vocabulary lives — echelons and postures and assets from `contacts`, Order
kinds from `squads`, owner states from `commands`, Squad types from the economy table — so a new
asset or a longer Order kind widens the budget by itself rather than by someone remembering to.

A second map is now a thing `just unit` has an opinion about. `docs/mvp-scope.md` ships one map, so
nothing in MVP is affected; the point is that the map after it cannot be authored into a silent
truncation.

The budget is measured in Python against a guard that fires in SQF. A test holds the two literals
together rather than a convention.

Not confirmed in-world: these are wire-size measurements, which is what the truncation is a
function of, so a probe would be measuring `json.dumps` twice. What a probe would add is
confirmation that the SQF guard fires where the Python budget says it should, and that is worth
folding into whatever next exercises `cti_fnc_commanderView` rather than queueing on its own.
