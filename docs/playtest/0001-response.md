# Playtest 0001 — response

Fill in and leave it here; `/playtest-ingest` reads this file. Fragments are enough, and a blank
line is an answer too — it means you did not get to it.

- Date:
- Boot line worked as written: y / n —
- Minutes in the seat:

## Live notes (dictated during the session, verbatim)

- Some visual feedback on what location I've selected whilst issuing orders would improve
  usability
- As commander I should be able to see a marker per squad showing their location and strength
  (e.g. 4/8). It should update in near real-time.
- As commander I should be able to see the current orders for my squads visually on the map e.g.
  showing that squad is ordered to captured agia_marina
- I see squad 1's marker right on top of the Agia Marina marker and a warning that 'team foot -
  seen 72s ago' on top of that. None are legible because of the collission in label text location.
- Separately, I can't see markers for squads 2 and 3. I think they were killed, but I have not
  in-game feedback to confirm that. I can still tab through all three.

  _(Checked against the wire during the session: WEST-1, WEST-2 and WEST-3 were all alive at
  size 8 at that moment. They had no marker because each had `at: ""` — the marker is drawn at
  the Place a Squad stands in, and a Squad in open ground between Places is not drawn at all.
  So the Commander cannot tell a marching Squad from a dead one.)_

  Screenshots: `0001-marker-collision-zoomed-out.png`, `0001-marker-collision-zoomed-in.png`.
  They show the collision is not only between our own two markers — the Contact's red text
  `team foot — seen 498s ago` is drawn straight through **the engine's own town label**
  "Agia Marina". Marker text renders at the marker position, a Place's position is the town
  centre, and that is exactly where Arma prints the town name, so the two always collide.
  Red-on-terrain at that zoom is barely legible even where nothing overlaps.
- Recommendation: always paint own squad markers on the map even if they're not an an Objective
  or Base.

  _(Not a UI-only change: `SquadView.at` is an Objective id, a Base id, or empty, so the client
  has no position to paint between Places. Carrying a real position for a Commander's **own**
  Squads is symmetric — both Commanders would get it, and it is not enemy intelligence — so it
  does not touch the fog rule, which is about Contacts. ADR-0012's projection and the
  Observation wire both move.)_

- Squads 3 and 4 are at the nearest places to the EAST base. I've sent them both Assault orders
  that were accepted. I've got no way to get them to combine their offensive - they'll arrive at
  different times and attack independently. That feels like an area for improvement for both AI
  and human commanders.

  _(The Command vocabulary has no synchronisation primitive at all: `ORDERS` is capture, defend,
  assault, reserve, each naming one Squad and one Place, with no rally point, no wait-for, no
  simultaneous H-hour. The AI Commander has the same hole — the planner scores each Squad
  independently and its only cross-Squad term is a veto stopping two Squads taking the same
  Objective, which suppresses concentration rather than enabling it.)_

### Harness request (not a game finding)

- For playtesting, it would be useful if I could access a Zeus-style observer mode where I can
  fly-about without trigerring enemy AI and observe what my squads are doing first-hand. I'd be
  able to give richer feedback that way.

  _(Worked around live: the mission sets `enableDebugConsole = 1`, so `[] spawn BIS_fnc_camera`
  from the Esc console gives a free-fly camera that spawns no unit. Costs: the player's body
  stays killable while flying, the map UI is unreachable from the camera, and it is a typed
  incantation rather than an affordance. A curator module in the playtest mission would be the
  real answer, and belongs to the playtest harness rather than to the scenario.)_

## 1 — read the panel

- Could tell what you had and could do, unaided: y / n
- Hint panel legibility (1–5):
- Marker legibility (1–5):
- Picture ever wrong rather than late: y / n —
- What felt wrong:

## 2 — buy one, send it

- Click → verb → issued read as one action: y / n
- Ever pressed a number and did not know if anything happened: y / n
- Eye went to: hint / marker / world
- Five-second staleness: not at all / noticed it / it misled me
- What felt wrong:

## 3 — get refused, three ways

- `already_held` appeared: **y** — "already_held - passed"
- `wrong_ground` appeared: **y** — "wrong_ground - passed"
- `insufficient_funds` appeared: **y** — "insufficient_funds - passed"
- Read a: reason / red word
- Told you what to do instead: y / n
- Had to look at the log: y / n
- What felt wrong:

## 4 — play it out against EAST

- EAST came for your Base: y / n — minute:
- Earned / cheap / too late to matter:
- EAST abandoned ground it had just taken to raid you: y / n
- HQ worked on: y / n — 90 s felt too fast / about right / too slow; time to react: y / n
- Campaign ended: y / n — how:
- EAST as an opponent (1–5):
- What felt wrong:

## 5 — refill what the fight cost

- Price shown felt like a discount worth taking, against buying fresh: y / n
- 0.8 felt: too cheap / about right / too dear
- Refilling created a real decision (thin Squad forward vs walk it home): y / n
- Would refill rather than buy new: always / sometimes / never
- What felt wrong:

## Anything else

- Worth looking at in *every* future session (candidate perceptual-checklist items):
- Anything that made you want to stop playing:
