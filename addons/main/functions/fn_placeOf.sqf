/*
 * Author: arma-cti
 * Which authored place a position is at. Runs anywhere.
 *
 * A Commander reasons about places, not coordinates (ADR-0008), so every
 * position the world reports is reduced to one before it leaves the server.
 * The manifest holds the geometry; this is the one reading of it, because two
 * would be two answers to where something is standing.
 *
 * Bases carry no authored radius — they are not captured, only lost to
 * Decapitation — so cti_fnc_placeRadius stands one in, and it is the same
 * reading an Order is given for the ground it names.
 *
 * Arguments:
 * 0: position <ARRAY> in [x, y] or [x, y, z]
 * 1: objectives <ARRAY> of manifest Objective HashMaps
 * 2: bases <ARRAY> of manifest Base HashMaps
 * 3: fall back to the nearest place <BOOL> (optional, default false)
 *
 * Return Value: <STRING> an Objective id, a Base id, or "" for open ground
 */
params ["_position", "_objectives", "_bases", ["_nearest", false, [false]]];

_position params ["_east", "_north"];
private _where = [_east, _north, 0];
private _at = "";

{
    (_x get "position") params ["_placeEast", "_placeNorth"];
    if (_where distance2D [_placeEast, _placeNorth, 0] <= ([_x] call cti_fnc_placeRadius)) exitWith {
        _at = _x get "id";
    };
} forEach _objectives;

if (_at isEqualTo "") then {
    {
        (_x get "position") params ["_placeEast", "_placeNorth"];
        if (_where distance2D [_placeEast, _placeNorth, 0] <= ([_x] call cti_fnc_placeRadius)) exitWith {
            _at = _x get "id";
        };
    } forEach _bases;
};

// Open ground is an honest answer about our own Squads, and no answer at all
// about a Contact: a Commander cannot act on "somewhere between two towns", and
// filing every sighting under a place is what keeps Contacts bounded by the map
// rather than by how far the enemy has spread out.
if (_at isEqualTo "" && _nearest) then {
    private _closest = 1e10;
    {
        (_x get "position") params ["_placeEast", "_placeNorth"];
        private _range = _where distance2D [_placeEast, _placeNorth, 0];
        if (_range < _closest) then {
            _closest = _range;
            _at = _x get "id";
        };
    } forEach (_objectives + _bases);
};

_at
