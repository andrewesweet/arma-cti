# A free ride is issued, not asked for, and crosses no wire

Delegated-decision: yes
Date: 2026-08-05
Reviewed-by-human: pending
Claimed: comment on #170, 2026-08-04, after `git fetch origin`; renumbered from
0059 unchanged on the rebase, where 0058 (#175) had landed and nothing above it
was claimed.

The human ruled the gameplay on 2026-08-03, quoted in #170: "I find yomping
repeatedly to targets to be boring gameplay. I think squad leaders (or AI
commander on behalf of squad leaders) should be able to access the weakest, most
basic form of motorised transport sufficient for their squad size for free at
all times. A civilian open truck perhaps?" Confirmed unchanged in the guided
decision-capture session of 2026-08-04, alongside #150.

That settles cost, availability, tier and size. It leaves four things the
implementation cannot avoid deciding, and this ADR takes them in the human's
stead: what a catalogue row is, what "free" means for the architecture, who may
mount the vehicle, and how the ruling's second principal — the AI Commander's
Squads — comes to actually ride.

## Ruling 1 — the ladder is authored weakest first and read first-match

"The weakest, most basic form of motorised transport **sufficient for their
squad size**" is not a constant, it is a rule with an ordering in it. So the
authored document is a ladder — `addons/main/catalogue/transport.json`,
ADR-0056's pattern and directory — and the rule is: take the first rung that
seats the Squad.

**Authored order is the doctrine, not a derived one.** `cti_daemon.motorpool`
refuses a file whose seat counts run backwards, rather than sorting them, for
the reason ADR-0056 authors a menu rather than generating one: which of two
equally-seated vehicles is the more basic is a design judgement and nothing in
the numbers says. Sorting silently would also hide an authoring mistake.

Two rungs today, and both are vanilla, unarmed and civilian — which is the whole
of what "weakest tier" can mean when the Squad drives itself:

| id | seats | class | |
|---|---|---|---|
| `offroad` | 6 | `C_Offroad_01_F` | the bottom rung |
| `open_truck` | 17 | `C_Truck_02_transport_F` | Zamak Transport (Civilian), open bed |

The shipped economy sells only eight-man Squads, so today every Squad is issued
the open truck — the human's own suggested concrete, taken literally. The
Offroad rung is not dead data: it is what makes the ruling's "sufficient for
their squad size" a rule that can be read rather than a constant, it is the rung
a Squad of six or fewer gets the day #6 authors one, and `weakest_for` is tested
against it.

`C_Van_01_transport_F` was weighed as an intermediate rung and declined. Its
thirteen seats are ten firing positions and two cargo, so it seats a Squad only
by putting most of it out of the windows; and the human asked for an open truck.

**Size is the Squad's purchased strength, not the men standing.** A vehicle
sized to today's casualties is one seat short the moment the Squad is
Reinforced, and the Squad that then walks is the one that just got its men back.
`cti_fnc_effectApply` records `cti_squadSize` on the group at spawn, beside the
`cti_squadType` it already records and for the same reason its own comment
gives: deriving the number a second time from the exported schema would be a
second answer to a question the spawning code already knows (#159's invented 8
is what a guess cost last time).

Rejected: **deriving the vehicle from a formula over seats.** It buys nothing —
there are two rungs — and it would make the classname a computed thing rather
than an authored one, which is the arrangement ADR-0017 exists to avoid.

## Ruling 2 — free, therefore not a Command, and therefore not on any wire

ADR-0056 drew the first half of this line for a kit: no Funds move, so nothing
is judged, so no fourth Command is minted and CONTEXT.md's Command vocabulary is
untouched. The same holds here and for the same reasons — no price table entry,
no Ledger call, no Judgement, no new spending principal beside ADR-0040's two.

This ADR draws the second half, which ADR-0056 did **not** need: the transport
crosses **no wire at all**.

- Not a **Command**: nothing is asked for, so there is nothing to judge.
- Not an **Effect**: an Effect is a world change the daemon accepted (CONTEXT.md),
  and the daemon accepted nothing.
- Not on the **Observation**: CONTEXT.md's Observation is a closed, human-gated
  list, and a Commander plans against ground, Funds, his own Squads and
  Contacts. Which truck a Squad has is none of those, and it is never a
  constraint on a decision — it is free and always available, so no plan can
  turn on it.
- Not on the **observe report**: a kit reaches the daemon because the *snapshot*
  has to carry it. This has no snapshot half.
- Not in the **snapshot**: ADR-0008 persists strategic state and regenerates
  tactical state at session boot. A vehicle standing on the ground is tactical
  in exactly the sense ADR-0008 names — ammo, damage, position — and the watch
  re-issues one on the first sweep of a resumed Campaign anyway, which is
  cheaper and more correct than persisting a wreck.

So the whole feature is world-side, which is ADR-0012's split applied honestly:
the daemon owns the rules and the game owns the geometry, and a vehicle judged
by no rule is geometry.

What the daemon keeps is one thing, and it runs in `just unit` rather than in a
Campaign. `config/economy.json` owns how many men a Squad is bought at (#159)
and `transport.json` owns how many a vehicle carries; neither file can check the
pair alone, and a ladder whose largest rung seats seven would be a Squad
marching off with a man left at the Base, discovered in a Play Session.
`motorpool.capacity_covers` is that check. The module is named `motorpool` and
not `transport` because `cti_daemon.transport` is already the TCP wire.

## Ruling 3 — issued by a watch, because nobody asks

"At all times" is a standing condition, not an event, so it is a watch and not a
hook — ADR-0056's reasoning for the loadout and #189's for `selectLeader`. One
rule, swept every ten seconds: *this Squad is standing at its own Base and has
no vehicle here, so give it one.* That covers a Squad the moment it is bought, a
Squad whose truck was destroyed, a Squad that abandoned one across the island
and marched home, and a Campaign resumed once #4 lands. A spawn hook would cover
the first of the four and need company for the other three.

**Nobody asking is what serves both of the ruling's principals with one rule.**
The parenthetical — "or AI commander on behalf of squad leaders" — would
otherwise be a planner change, a Command, or both. It is neither: an AI-led
Squad and a player-led one are issued a vehicle by the same sweep precisely
because neither of them had to ask for it. No planner change, no port entry,
nothing added to the CfgRemoteExec whitelist, which stays one function long
(ADR-0025's consequence).

**At the Base, and only there**, which is where restock and Reinforce already
are (ADR-0040's pinned line) and where the loadout menu is (ADR-0056). Free
things happen where a side's men are already going. The reading is
`cti_fnc_placeOf` off the leader's position — the same call `cti_fnc_squadSample`
reports a Squad's position with — so "at Base" means here what it means on the
Observation.

**One per Squad, and having one means having one *here*.** A truck abandoned at
an Objective is a truck the Squad would have to walk back to, which is the
yomping the ruling ends, so it does not count and a fresh one is issued. The old
one is disowned and deleted — except when somebody is in it, when it is released
onto the map and said out loud, because `commands/deleteVehicle.wiki` is
explicit that deleting an occupied vehicle "may lead to all sorts of bugs and
ghost objects left on the map". It cannot be one of this Squad's own men: the
Squad is at its Base, which is what earned it the new vehicle.

## Ruling 4 — who may mount it: anybody, and the AI rides by the engine's own rule

**Ownership is bookkeeping, not permission.** The engine has no side- or
group-scoped vehicle lock: `lock` and `setVehicleLock` distinguish a player from
an AI subordinate and nothing else, and `commands/lock.wiki` records that a lock
"will not stop player getting into or out of vehicle via script commands". So
the record of which Squad a truck belongs to says which vehicle to replace, and
never who may drive. A stolen truck is a thing that happened in a Play Session,
not a rule violation.

**The AI rides by the engine's own mechanism, and this is why no Order changes.**
`groupName addVehicle vehicleName` puts the truck into the group's own vehicle
pool — the command's own words are "adds a specified vehicle for use by a
specified AI led group" — and `topics/Waypoints.wiki` states the consequence for
the Move waypoint `cti_fnc_orderApply` already lays: "Groups will automatically
board any transport vehicles they own if the next waypoint is far enough away."
So the AI Commander's Squads ride with no waypoint change, no Order vocabulary
change, and nothing new on the wire. Rejected, in consequence: laying GET IN /
GET OUT waypoints ourselves, which would put a transport decision inside the
Order path where the daemon could see it and would make the Order a Command
about vehicles.

**A player-led Squad gets the truck and not the mechanism, deliberately.**
`addVehicle` and `leaveVehicle` are both `arg= local` (vendored wiki) and an AI
group with a player leader is local to that player's machine
(`topics/Multiplayer_Scripting.wiki`), so the server asks neither of a group it
does not own. That is not a gap papered over:
`topics/AI_Group_Vehicle_Management.wiki` records that the mechanism "has no
effect on AI lead by a player Group Leader" in any case, and a player squad
leader does not need it — he drives. Reaching him would mean a `remoteExec` to
the client, which is a widening of the audited surface ADR-0056 already named as
needing its own decision. The ruling's word for him is *access*, and access is a
truck standing at his Base with nobody's name on it.

## Consequences

- One authored document, `addons/main/catalogue/transport.json`, shipped in the
  PBO where `loadFile` reaches it and validated in Python over the same bytes —
  ADR-0056's pattern, with one difference stated above: the daemon is a
  *validator* here rather than a runtime reader, because nothing about the truck
  is a rule.
- The world runs an eighth supervised loop, `transport_watch`, registered and
  watched like the other seven.
- `cti_fnc_effectApply` records `cti_squadSize` on a group at spawn. One line,
  and the only change to an existing world-facing function.
- **`engine_drift` gains an emitter.** #71 records that nothing in the project
  can produce the class. `cti_fnc_transportIssue` counts the seats the engine
  actually gave it (`fullCrew` with `includeEmpty`) against the authored number,
  and a vehicle that no longer carries the Squad is the Arma build having moved
  under an authored fact — which is what the class is for, and not ours to
  "fix". This does not close #71; it is one emitter where there were none.
- **March times fall, and the tuning they were measured against did not.**
  ADR-0027's `ASSAULT_MASS` window and ADR-0031's `reach_km` bookend were
  measured on Stratis with Squads on foot; `proximity` is still kilometres and
  no scorer value moves, but the tempo those values were tuned to does. The
  first playtest after this should be read with that in mind, and #187's
  concentration prototype is where a re-measurement would land.
- CONTEXT.md is not edited. No term changes, no new Command, no Observation
  field. Whether "transport" deserves a glossary entry of its own — it is
  already in the vocabulary as a Contact *posture* — is the human's call at
  review.
- `docs/mvp-scope.md` carries the ruling's quote and the distinction it forces:
  the free truck is a bare unarmed civilian vehicle the Squad drives itself, and
  the priced "transport +50" Squad type stays what it was — a crewed transport
  asset, still unauthored in `config/economy.json`. The scope edit is the
  human's own words; the sentence distinguishing the two is this ADR's.

## What would overturn this

- **Ruling 1's ladder.** The human saying at review that he meant one vehicle
  for every Squad regardless of size collapses the ladder to a constant and
  makes `capacity_covers` pointless. A playtest finding that the Zamak is the
  wrong feel — too capable, too slow, too conspicuous — is a rung swap and not
  an overturn; the file is one edit.
- **Ruling 2's no-wire position.** Anything that makes the truck a *constraint*
  breaks it: pricing it post-MVP, capping how many a side may hold, or a
  Commander decision that turns on whether a Squad is mounted. Any of those puts
  it on the Observation and probably makes it a Command, and #136's
  spending-consideration framework is where the first would land.
- **Ruling 3's Base-only rule.** A playtest finding that a Squad wants a fresh
  vehicle at a captured Objective is a new decision to take, not a tune of this
  one — it would put a rule on ground the Reinforce comparison does not cover,
  which is exactly what ADR-0056 said about re-kitting away from Base.
- **Ruling 3's replacement rule.** Trucks accumulating on the map, or a
  release that a player meets as a vehicle that will not go away, argues for
  deleting the old one unconditionally with the crew moved out first
  (`moveOut` + `unassignVehicle`, which `commands/leaveVehicle.wiki` names as
  the reliable form).
- **Ruling 4's hands-off AI.** An in-world run showing AI Squads not boarding —
  the wiki's own sentence is the evidence this rests on, and
  `topics/AI_Group_Vehicle_Management.wiki` flags parts of that machinery as
  unclear — forces explicit GET IN waypoints in `cti_fnc_orderApply`, with the
  cost Ruling 4 rejected them for. `spike/probes/transport.sqf` is what would
  show it.
- **The march-time consequence.** A playtest or a re-measurement showing the
  Campaign now resolves before a Commander can react argues for slowing the
  ladder — a lower top speed, or a rung the AI will not drive off-road — rather
  than for withdrawing the ride the human asked for.
