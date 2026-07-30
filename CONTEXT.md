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
The unit of command. Purchased whole, ordered whole; leadership passes to the engine AI on leader death, but a player squad leader reclaims leadership on respawn.
_Avoid_: Group (reserved for the engine's group concept), team, fireteam

**Order**:
A Commander's standing instruction to one Squad: Capture(Objective), Defend(Objective), or Reserve. An Order survives leader death. A player-led Squad receives Orders but compliance is voluntary.
_Avoid_: Task (reserved for the engine task system), waypoint, directive

**Funds**:
Per-side currency. Earned as income from held Objectives, spent through the Command Port.
_Avoid_: Money, resources, supply

**Stipend**:
Small flat Funds amount paid to each side every income tick regardless of Objectives held, so no side can be economically locked out.
_Avoid_: Basic income, allowance

**Base**:
A side's fixed, pre-placed home location. Site of Purchase, Reinforce, and free rearm; its destruction is a loss condition.
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
