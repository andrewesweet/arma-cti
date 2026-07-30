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
            private _where = getPosATL leader _group;
            private _at = "";

            {
                (_x get "position") params ["_east", "_north"];
                if (_where distance2D [_east, _north, 0] <= (_x get "capture_radius")) exitWith {
                    _at = _x get "id";
                };
            } forEach _objectives;

            if (_at isEqualTo "") then {
                // Bases have no authored radius — they are not captured, only
                // lost to Decapitation — so a Squad counts as at its Base when
                // it is close enough to be standing in it.
                {
                    (_x get "position") params ["_east", "_north"];
                    if (_where distance2D [_east, _north, 0] <= 150) exitWith {
                        _at = _x get "id";
                    };
                } forEach _bases;
            };

            _seen set [_squadId, createHashMapFromArray [["size", _living], ["at", _at]]];
        };
    };
} forEach (missionNamespace getVariable ["cti_squads", createHashMap]);

_seen
