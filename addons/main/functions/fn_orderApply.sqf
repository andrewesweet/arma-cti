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
 * The three Orders are distinct in the world, not labels on the same behaviour:
 * Capture searches the ground it is sent to, Defend goes there and stays, and
 * Reserve falls back on the Squad's own Base and holds its fire.
 *
 * The daemon owns the rules and the game owns the geometry (ADR-0012), so an
 * Order names an Objective and this looks up where that is.
 *
 * Arguments:
 * 0: Squad id <STRING>
 * 1: order <STRING> — "capture", "defend" or "reserve"
 * 2: Objective id <STRING> — empty for Reserve
 *
 * Return Value: <BOOL> whether the effect is settled. False leaves it on the
 * outbox to be delivered again.
 */
params [["_squadId", "", [""]], ["_order", "", [""]], ["_objective", "", [""]]];

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

private _map = missionNamespace getVariable ["cti_map", createHashMap];
private _destination = [];
private _label = "";
private _radius = 0;

if (_order isEqualTo "reserve") then {
    // Reserve is the absence of a destination, so the Squad falls back on its
    // own Base rather than standing wherever its last Order left it.
    private _side = str (side _group);
    {
        if ((_x getOrDefault ["side", ""]) isEqualTo _side) exitWith {
            _destination = _x get "position";
            _label = _x get "display_name";
            _radius = 100;
        };
    } forEach (_map getOrDefault ["bases", []]);
} else {
    {
        if ((_x getOrDefault ["id", ""]) isEqualTo _objective) exitWith {
            _destination = _x get "position";
            _label = _x get "display_name";
            // The ground the Squad has to stand on to take or hold it is the
            // capture radius, so that is also how far it may drift before
            // cti_fnc_orderEnforce sends it back.
            _radius = _x get "capture_radius";
        };
    } forEach (_map getOrDefault ["objectives", []]);
};

if (count _destination isEqualTo 0) exitWith {
    diag_log format ["CTI|FAIL class=assertion_failed order_without_ground squad=%1 order=%2 objective=%3",
        _squadId, _order, _objective];
    true
};

_destination params ["_east", "_north"];
private _at = [_east, _north, 0];

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
    ["objective", _objective],
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

diag_log format ["CTI|order_applied squad=%1 side=%2 order=%3 objective=%4 waypoints=%5 leader=%6",
    _squadId, str (side _group), _order, _objective, count waypoints _group, name leader _group];

true
