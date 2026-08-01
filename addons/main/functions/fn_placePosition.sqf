/*
 * Author: arma-cti
 * Where an authored place is. Runs anywhere.
 *
 * The inverse of cti_fnc_placeOf, and the other half of the same rule: a
 * Commander names places and the manifest holds the geometry (ADR-0008,
 * ADR-0020), so anything that has to put a place on a screen reads it from the
 * manifest rather than carrying coordinates of its own.
 *
 * Arguments:
 * 0: an Objective id, a Base id, or "" <STRING>
 *
 * Return Value: <ARRAY> the position in [x, y, 0], or [] when the map has no
 * such place. Callers must treat [] as "nothing to draw".
 */
params [["_place", "", [""]]];

if (_place isEqualTo "") exitWith { [] };

private _map = missionNamespace getVariable ["cti_map", createHashMap];
private _at = [];

{
    if ((_x get "id") isEqualTo _place) exitWith {
        (_x get "position") params ["_east", "_north"];
        _at = [_east, _north, 0];
    };
} forEach ((_map getOrDefault ["objectives", []]) + (_map getOrDefault ["bases", []]));

_at
