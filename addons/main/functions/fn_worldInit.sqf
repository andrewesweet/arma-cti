/*
 * Author: arma-cti
 * Builds the world the Campaign is played on: every Objective marked with its
 * owner, both Bases visible. Server only — the markers created here are global.
 *
 * Every Objective starts Neutral. Ownership by presence and the income tick
 * arrive in a later ticket; this function only draws what the manifest
 * authored and records the owner each Objective starts under.
 *
 * Interior to the server's own call graph, so it carries no locality guard: its
 * one caller is `missions/cti.Stratis/initServer.sqf`, which the engine runs on
 * the server and nowhere else (#118, ADR-0040).
 *
 * The dedicated server writes no RPT file on Linux and `-profiles=` is broken
 * (ADR-0006), so stdout is the only log and every line here goes there.
 *
 * Arguments: none
 *
 * Return Value: <BOOL> true when the world is built. False is fatal: there is
 * nothing to play on, and the caller must not pretend otherwise.
 */
private _map = call cti_fnc_manifestLoad;
if (count _map isEqualTo 0) exitWith {
    // cti_fnc_manifestLoad has already logged which failure this is.
    diag_log "CTI|FAIL class=assertion_failed world_not_built";
    false
};

private _objectives = _map get "objectives";
private _bases = _map get "bases";
private _owners = createHashMap;

{
    private _id = _x get "id";
    private _radius = _x get "capture_radius";
    (_x get "position") params ["_east", "_north"];
    private _position = [_east, _north, 0];
    private _colour = ["NEUTRAL"] call cti_fnc_sideMarkerColour;

    // The capture area is drawn, not left to folklore: the radius a Squad has
    // to stand inside is the whole mechanic.
    // A global marker command broadcasts the marker's entire state, so every
    // change but the last is made locally and the last one publishes them all.
    private _area = createMarker [format ["cti_objective_%1_area", _id], _position];
    _area setMarkerShapeLocal "ELLIPSE";
    _area setMarkerBrushLocal "Border";
    _area setMarkerSizeLocal [_radius, _radius];
    _area setMarkerColor _colour;

    private _marker = createMarker [format ["cti_objective_%1", _id], _position];
    _marker setMarkerTypeLocal "mil_dot";
    _marker setMarkerTextLocal (_x get "display_name");
    _marker setMarkerColor _colour;

    _owners set [_id, "NEUTRAL"];
} forEach _objectives;

{
    (_x get "position") params ["_east", "_north"];
    private _marker = createMarker [format ["cti_base_%1", _x get "id"], [_east, _north, 0]];
    _marker setMarkerTypeLocal "b_hq";
    _marker setMarkerTextLocal (_x get "display_name");
    _marker setMarkerColor ([_x get "side"] call cti_fnc_sideMarkerColour);
} forEach _bases;

missionNamespace setVariable ["cti_map", _map, true];

// Two readings of the manifest nothing has to scan for (#109): a Place by its
// id, and a side's Base. Seven call sites walked the `objectives` and `bases`
// arrays looking for one or the other, one of them inside a per-Squad loop on a
// five-second sweep. Derived here rather than authored, so the manifest stays
// the single source and there is nothing to keep in step: the two id namespaces
// are already one, which `manifest._check_one_namespace` enforces before
// anything is played on, so the merge cannot collide.
private _placesById = createHashMap;
{ _placesById set [_x get "id", _x] } forEach (_objectives + _bases);
private _basesBySide = createHashMap;
{ _basesBySide set [toUpper (_x getOrDefault ["side", ""]), _x] } forEach _bases;
// Broadcast like the map itself: a client draws places too, and the index is a
// reading of data it already has.
missionNamespace setVariable ["cti_placesById", _placesById, true];
missionNamespace setVariable ["cti_basesBySide", _basesBySide, true];
missionNamespace setVariable ["cti_objectiveOwner", _owners, true];
// Squad id to group, filled as Squads are bought. An Order names a Squad, so
// this is what an Order is resolved through (#14).
missionNamespace setVariable ["cti_squads", createHashMap, true];

diag_log format ["CTI|world_built map=%1 world=%2 objectives=%3 bases=%4",
    _map get "id", _map get "world", count _objectives, count _bases];

true
