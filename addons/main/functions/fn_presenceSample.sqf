/*
 * Author: arma-cti
 * Who is standing inside each Objective's capture radius. Runs on the server.
 *
 * Interior to the server's own call graph, so it carries no locality guard:
 * every path into it starts in `missions/cti.Stratis/initServer.sqf`, which the
 * engine runs on the server and nowhere else (#118, ADR-0040).
 *
 * A fact only the world can report. What it means — whether that is a capture,
 * a contest, or nothing — is decided in the daemon, where the rules are
 * testable (ADR-0012).
 *
 * Only living units on a playable side count. Dead bodies persist in the world
 * and would otherwise hold ground indefinitely; a wreck cannot capture a town.
 *
 * Arguments: none
 *
 * Return Value: <HASHMAP> Objective id -> ARRAY of side names present
 */
private _map = missionNamespace getVariable ["cti_map", createHashMap];
private _objectives = _map getOrDefault ["objectives", []];
private _presence = createHashMap;

{
    private _id = _x get "id";
    private _radius = _x get "capture_radius";
    (_x get "position") params ["_east", "_north"];
    private _centre = [_east, _north, 0];

    private _sides = [];
    {
        if (alive _x) then {
            private _side = str (side group _x);
            if (_side in ["WEST", "EAST"]) then {
                _sides pushBackUnique _side;
            };
        };
    } forEach (_centre nearEntities ["CAManBase", _radius]);

    _presence set [_id, _sides];
} forEach _objectives;

_presence
