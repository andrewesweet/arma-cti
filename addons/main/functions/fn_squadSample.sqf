/*
 * Author: arma-cti
 * What the world alone knows about each Squad. Runs on the server.
 *
 * Two facts only: how many of it are still standing, and where it is. Its side,
 * what it is and what it was told to do are the daemon's (ADR-0012), and
 * reporting them from here would be inventing a second answer to a question
 * that already has one.
 *
 * Position is coarse on purpose (ADR-0008): the id of the Objective or Base the
 * Squad is standing on, and empty for the open ground between them. A Commander
 * reasons about places, not coordinates, and a strategic observation that
 * carried coordinates would be a tactical one.
 *
 * A Squad the world has lost is simply absent, which is how the daemon learns
 * it is gone.
 *
 * Arguments: none
 *
 * Return Value: <HASHMAP> Squad id -> HASHMAP of `size` and `at`
 */
if (!isServer) exitWith { createHashMap };

private _map = missionNamespace getVariable ["cti_map", createHashMap];
private _objectives = _map getOrDefault ["objectives", []];
private _bases = _map getOrDefault ["bases", []];
private _seen = createHashMap;

{
    private _squadId = _x;
    private _group = _y;
    if (!isNull _group) then {
        private _living = { alive _x } count units _group;
        if (_living > 0) then {
            // Open ground between places is an honest answer here, so no
            // nearest-place fallback: a Squad that is marching is marching.
            private _at = [getPosATL leader _group, _objectives, _bases] call cti_fnc_placeOf;

            _seen set [_squadId, createHashMapFromArray [["size", _living], ["at", _at]]];
        };
    };
} forEach (missionNamespace getVariable ["cti_squads", createHashMap]);

_seen
