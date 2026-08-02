# Arma CTI

A personal Capture the Island scenario for Arma 3, developed primarily by autonomous agents with maximal automated testing.

## Language

**Campaign**:
The persistent strategic state of one Capture the Island playthrough, surviving across Play Sessions.
_Avoid_: Game, save, world

**Play Session**:
A period during which the Arma process is running and the Campaign is live. The Campaign exists between Play Sessions; the Arma world does not.
_Avoid_: Server uptime, match

**Commander**:
The decision-maker issuing strategic orders for one side through the Command Port. Human or AI — either may command either side; both sides may be AI-commanded while the player leads a squad.
_Avoid_: General, HQ, OPCOM

**Command Port**:
The single interface through which every Commander (human or AI) issues orders. No order path exists outside it.
_Avoid_: Command API, order bus

**Command**:
One Commander instruction sent through the Command Port: Purchase, Order, or Reinforce.
_Avoid_: message, request, packet; "command" unqualified for engine scripting commands (say "scripting command")

**Objective**:
A capturable point of interest on a map's manifest, with a stable authored ID and an owner (side, Neutral, or Contested). MVP uses towns only; the concept is not town-specific.
_Avoid_: Town, sector, zone, POI

**Squad**:
The unit of command. Purchased whole, ordered whole; leadership passes to the engine AI on leader death, but a player squad leader reclaims leadership on respawn. A Squad is owned by the server for its whole life and is never transferred off it, because the Order path runs through scripting commands that are local to the owner (ADR-0039).
_Avoid_: Group (reserved for the engine's group concept), team, fireteam

**Order**:
A Commander's standing instruction to one Squad, naming a Place or nothing: Capture(Objective), Defend(Objective or own Base), Assault(enemy Base), or Reserve. An Order survives leader death. A player-led Squad receives Orders but compliance is voluntary.
_Avoid_: Task (reserved for the engine task system), waypoint, directive

**Assault**:
Order kind: close with the enemy Base and destroy its HQ structure — Decapitation as an Order. Only the enemy Base is assaultable; an Objective is captured, never assaulted.
_Avoid_: attack, raid, rush; destroy (reserved for the engine's Destroy waypoint)

**Place**:
Any authored ground an Order or a coarse position can name: an Objective or a Base, by its manifest id. Nothing else is a Place — the open ground between them has no name.
_Avoid_: location, position (reserved for coordinates), target (reserved for the engine's targeting)

**Observation**:
The strategic picture at one moment as **one** Commander may know it: every Objective's owner, that Commander's own Funds, and each of its own Squads with composition type, member count, standing Order and coarse position. What it knows of the enemy is Contacts, never roster entries. Assembled by the daemon from what it decides plus the facts only the world can see — how many of a Squad are standing, the ground underfoot, the Sightings its leaders report, and an HQ falling. Deliberately the same set the Campaign snapshot persists (ADR-0008): nothing tactical, and places rather than coordinates.
_Avoid_: State, world state, telemetry; snapshot (reserved for the persisted Campaign)

**Contact**:
What one side has seen of the other, as it appears in that side's Observation: aggregated per place, carrying an estimated echelon (team, squad, platoon, company), a posture (foot, motorised, mechanised, armoured, air), any notable assets, and how long ago it was seen. Reported by squad leaders from what their units actually observed. A Contact never names an enemy Squad or its Order — it says what was seen, never what the enemy is or intends. Observing a place and finding nobody clears its Contact.
_Avoid_: Sighting (that is the raw world-side input a Contact is banded from, never a synonym for the Contact itself), blip, intel; enemy Squad (a Contact is not one); target (reserved for the engine's targeting)

**Sighting**:
One enemy thing one side's leaders currently know about, as the world reports it: a place, a perceived kind, and an age. The raw input a Contact is banded from; it crosses the boundary and goes no further — an Observation carries Contacts, never Sightings.
_Avoid_: Contact (the banded output, not a synonym); spotting

**Funds**:
Per-side currency. Earned as income from held Objectives, spent through the Command Port.
_Avoid_: Money, resources, supply

**Stipend**:
Small flat Funds amount paid to each side every income tick regardless of Objectives held, so no side can be economically locked out.
_Avoid_: Basic income, allowance

**Base**:
A side's fixed, pre-placed home location. Site of Purchase, Reinforce, and free rearm; its destruction is a loss condition. Addressable by Order — Defend by its own side, Assault by the enemy — yet not an Objective: it has no owner by presence and pays no income.
_Avoid_: HQ, main base, spawn

**Purchase**:
Commander verb: spend Funds to create a new Squad at own Base.
_Avoid_: Buy, recruit, build

**Domination**:
Victory by owning every Objective simultaneously for a sustained grace period within one Play Session.
_Avoid_: Total control, map win

**Decapitation**:
Victory by destroying the enemy Base's HQ structure.
_Avoid_: Base kill, HQ rush

**Reinforce**:
Port verb, usable by squad leader or Commander: refill a Squad at own Base to its purchased composition, costing Funds pro-rata. Ammo and equipment restock is free at Base and is not a port verb.
_Avoid_: Resupply, heal, replen
