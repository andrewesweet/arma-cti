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

// Through the index cti_fnc_worldInit derives beside the map (#109), so this is
// a lookup rather than a scan over both lists concatenated.
private _ground = (missionNamespace getVariable ["cti_placesById", createHashMap])
    getOrDefault [_place, createHashMap];
if (count _ground isEqualTo 0) exitWith { [] };

(_ground get "position") params ["_east", "_north"];
[_east, _north, 0]
