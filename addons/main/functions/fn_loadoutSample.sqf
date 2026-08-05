/*
 * Author: arma-cti
 * Which kit each player has been granted. Runs on the server.
 *
 * Interior to the server's own call graph, so it carries no locality guard: its
 * one caller is `cti_fnc_presenceReport`, itself reachable only from
 * `missions/cti.Stratis/initServer.sqf` (#118, ADR-0041).
 *
 * One fact, and it is the one only the world can see: a player standing at his
 * own Base picked a kit off the menu. What that means and what survives a
 * session is the daemon's (ADR-0012, ADR-0056) — it is the snapshot that has to
 * carry the choice, so the choice is reported rather than kept here alone.
 *
 * Ids rather than the kit itself, deliberately. ADR-0008 regenerates everything
 * tactical at session boot and a `getUnitLoadout` array is mostly exactly that,
 * down to the rounds left in each magazine; the durable fact is which row of the
 * menu he took.
 *
 * No shape of its own in `cti_daemon.report`, for `presence`'s reason: this is a
 * map of ids to ids rather than a named object with fields.
 *
 * Arguments: none
 *
 * Return Value: <HASHMAP> player UID -> kit id. Empty before the watch has
 * started, and for a world nobody has joined, which are the same answer as far
 * as the daemon is concerned: nobody has chosen anything.
 */
+(missionNamespace getVariable ["cti_loadoutChosen", createHashMap])
