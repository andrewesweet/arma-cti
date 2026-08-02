/*
 * Author: arma-cti
 * Gives one Squad its standing Order and makes the world act on it. Server only.
 *
 * An Order is standing, not a waypoint consumed and forgotten (#14). Waypoints
 * belong to the group rather than to whoever is leading it, so replacing them
 * here is what makes an Order outlive the leader who was carrying it: the
 * engine promotes a new leader and the group keeps the same destination. The
 * Order is also recorded on the group so cti_fnc_orderEnforce can re-assert it
 * once the engine considers the waypoint done.
 *
 * The four Orders are distinct in the world, not labels on the same behaviour:
 * Capture searches the ground it is sent to, Defend goes there and stays,
 * Assault closes with the enemy Base's HQ structure and works on it until it
 * falls, and Reserve falls back on the Squad's own Base and holds its fire.
 *
 * The daemon owns the rules and the game owns the geometry (ADR-0012), so an
 * Order names a Place and this looks up where that is. A Place is either kind
 * of authored ground (ADR-0020), so both lists are searched: an Order naming a
 * Base that only looked through the Objectives would find no ground and be
 * dropped, which is what #32 left behind for #33.
 *
 * Arguments:
 * 0: Squad id <STRING>
 * 1: order <STRING> — "capture", "defend", "assault" or "reserve"
 * 2: Place id <STRING> — an Objective or a Base; empty for Reserve
 *
 * Return Value: <BOOL> whether the effect is settled. False leaves it on the
 * outbox to be delivered again.
 */
params [["_squadId", "", [""]], ["_order", "", [""]], ["_place", "", [""]]];

if (!isServer) exitWith { false };

private _group = (missionNamespace getVariable ["cti_squads", createHashMap])
    getOrDefault [_squadId, grpNull];
if (isNull _group || { count units _group isEqualTo 0 }) exitWith {
    // A Squad can be wiped out between the Order being judged and the effect
    // arriving. Refusing the effect would wedge the pump on a Squad that is
    // never coming back, so this is carried out as far as the world allows.
    diag_log format ["CTI|order_no_squad squad=%1 order=%2", _squadId, _order];
    true
};

// Both readings come from the indexes cti_fnc_worldInit derives beside the map
// (#109). A Place is an Objective or a Base (ADR-0020) and the two share one id
// namespace, which `manifest._check_one_namespace` enforces before anything is
// played on — so one lookup cannot find two answers.
private _ground = if (_order isEqualTo "reserve") then {
    // Reserve is the absence of a destination, so the Squad falls back on its
    // own Base rather than standing wherever its last Order left it.
    (missionNamespace getVariable ["cti_basesBySide", createHashMap])
        getOrDefault [toUpper str (side _group), createHashMap]
} else {
    (missionNamespace getVariable ["cti_placesById", createHashMap])
        getOrDefault [_place, createHashMap]
};

private _destination = _ground getOrDefault ["position", []];
private _label = _ground getOrDefault ["display_name", ""];
// The ground the Squad has to stand on to take or hold a Place is also how far
// it may drift before cti_fnc_orderEnforce sends it back. Assault sets its own
// below: it is not held by standing in the Base but by working on one building.
private _radius = [_ground] call cti_fnc_placeRadius;

if (count _destination isEqualTo 0) exitWith {
    diag_log format ["CTI|FAIL class=assertion_failed order_without_ground squad=%1 order=%2 place=%3",
        _squadId, _order, _place];
    true
};

_destination params ["_east", "_north"];
private _at = [_east, _north, 0];

// An Assault is aimed at one building rather than at a Place: the HQ structure
// the manifest names, which the mission places and initServer.sqf refuses to
// play without. Its own position is authored data, so the Squad is sent to the
// building itself rather than to a Base position it may be tens of metres from
// — and never to a bearing off anybody's facing (#28).
private _hq = objNull;
if (_order isEqualTo "assault") then {
    _hq = missionNamespace getVariable [_ground getOrDefault ["hq", ""], objNull];
    if (isNull _hq) then {
        // The world was built without the thing Decapitation destroys. Reported
        // rather than worked around: the Squad still goes to the Base, so the
        // Order is not silently dropped, but nothing there can fall.
        diag_log format ["CTI|FAIL class=assertion_failed order_without_hq squad=%1 place=%2 name=%3",
            _squadId, _place, _ground getOrDefault ["hq", ""]];
    } else {
        _at = getPosATL _hq;
        // The ground an Assault is held by: at the HQ, rather than merely
        // inside the Base. Wide enough for a Squad in formation around a
        // building — the engine keeps a group spread over tens of metres and
        // will not walk it into a wall — and well inside the 150 m that counts
        // as standing in the Base. It is the distance cti_fnc_orderEnforce lets
        // the Squad drift, and cti_fnc_baseAssault's own reach matches it,
        // because "still under this Order" and "still working on the HQ" are
        // the same question asked twice.
        _radius = 75;
    };
};

// Replacing the waypoints is what makes a new Order supersede the last one.
// Backwards, because deleting shifts every index above it down.
for "_i" from (count waypoints _group) - 1 to 0 step -1 do {
    deleteWaypoint [_group, _i];
};

// Behaviour rides on the waypoint rather than being set on the group: the
// engine applies it when the waypoint becomes active, so it travels with the
// Order instead of being state something else has to remember to undo.
private _first = _group addWaypoint [_at, -1];
_first setWaypointCompletionRadius _radius;

switch (_order) do {
    case "capture": {
        // Seek and Destroy: move onto the Objective, then search it. The
        // Campaign's capture rule does the rest — presence in the radius is
        // what takes ground, so the Squad only has to get there and hold on.
        _first setWaypointType "SAD";
        _first setWaypointBehaviour "AWARE";
        _first setWaypointCombatMode "RED";
        _first setWaypointSpeed "NORMAL";
    };
    case "defend": {
        _first setWaypointType "MOVE";
        _first setWaypointBehaviour "AWARE";
        // Fire at will, keep formation: a garrison that chases is not a
        // garrison, and an Objective is only held by standing on it.
        _first setWaypointCombatMode "YELLOW";
        _first setWaypointSpeed "NORMAL";

        private _hold = _group addWaypoint [_at, -1];
        _hold setWaypointType "HOLD";
        _hold setWaypointCompletionRadius _radius;
    };
    case "assault": {
        // Two waypoints, because the engine's Destroy waypoint is about the
        // building and not about getting to it: "this waypoint type works best
        // when it is attached to an object", and a group that cannot bring the
        // object down "will move within range of being able to identify the
        // object, then wait until it is destroyed" (topics/Waypoints.wiki).
        // Waiting at identification range is not close enough to work on it, so
        // the Squad is walked onto the HQ first and set on it second.
        _first setWaypointType "MOVE";
        // Onto the building rather than into range of it. A completion radius
        // as wide as the Order's ground would end the walk the moment the
        // leader was within it, and the first run of `base-assault` did exactly
        // that: the Squad stopped at 40 m, went to the Destroy waypoint, and
        // stood there shooting at a building with one man close enough to be
        // working on it.
        _first setWaypointCompletionRadius 20;
        _first setWaypointBehaviour "AWARE";
        _first setWaypointCombatMode "RED";
        _first setWaypointSpeed "NORMAL";

        private _press = _group addWaypoint [_at, -1];
        _press setWaypointType "DESTROY";
        _press setWaypointCompletionRadius _radius;
        _press setWaypointBehaviour "AWARE";
        _press setWaypointCombatMode "RED";
        if (!isNull _hq) then { _press waypointAttachObject _hq };
    };
    default {
        _first setWaypointType "MOVE";
        // A Squad in Reserve is not looking for a fight.
        _first setWaypointBehaviour "SAFE";
        _first setWaypointCombatMode "GREEN";
        _first setWaypointSpeed "LIMITED";
    };
};

_group setCurrentWaypoint _first;

_group setVariable ["cti_order", createHashMapFromArray [
    ["order", _order],
    ["place", _place],
    ["position", _at],
    ["radius", _radius]
], true];

// Compliance is voluntary for a player-led Squad (#14), so the Order is shown
// rather than imposed. The engine's own task framework does it: a task owned by
// the group reaches whoever is in it, carries the ground as its destination,
// and does nothing at all for an all-AI Squad.
[_group, format ["cti_order_%1", _squadId],
    [format ["Standing Order: %1 %2.", _order, _label], format ["%1 %2", toUpper _order, _label], ""],
    _at, "ASSIGNED", 1, true] call BIS_fnc_taskCreate;

diag_log format ["CTI|order_applied squad=%1 side=%2 order=%3 place=%4 waypoints=%5 leader=%6",
    _squadId, str (side _group), _order, _place, count waypoints _group, name leader _group];

true
