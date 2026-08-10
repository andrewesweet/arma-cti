/*
 * Author: arma-cti
 * Who is occupying a squad-leader slot, and for which side. Runs on the server.
 *
 * Interior to the server's own call graph, so it carries no locality guard: its
 * one caller is `cti_fnc_presenceReport`, itself reachable only from
 * `missions/cti.Stratis/initServer.sqf` (#118, ADR-0041).
 *
 * One fact, and it is one only the world can see: a player has taken the
 * squad-leader role. What that means — that a dedicated roster Squad is minted
 * at own Base, composition-unassigned, and suspended when he disconnects before
 * its first fill — is the daemon's (ADR-0012, ADR-0070). It rides the report
 * rather than the Command Port because it is not a Command: no Funds move and
 * the rules judge nothing. `cti_fnc_loadoutSample` is the precedent, down to
 * this shape.
 *
 * Player UID rather than unit or machine id, for ADR-0025's reason: respawn
 * hands the player a new unit and reconnection a new machine id, and neither is
 * a change of who is leading.
 *
 * No shape of its own in `cti_daemon.report`, for `presence`'s reason: this is a
 * map of ids to a closed vocabulary rather than a named object with fields.
 *
 * The watch that fills `cti_squadLeaders` is the mission and lifecycle work of
 * #311/#312, which is where a squad-leader slot first exists at all — the
 * Phase-1 mission is two Commander slots and a headless client (ADR-0007). Until
 * then the honest answer is the empty one, which is the same answer as a world
 * nobody has joined: nobody is leading a Squad.
 *
 * Arguments: none
 *
 * Return Value: <HASHMAP> player UID -> side name, as the daemon spells it.
 */
+(missionNamespace getVariable ["cti_squadLeaders", createHashMap])
