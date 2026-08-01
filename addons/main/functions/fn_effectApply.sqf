/*
 * Author: arma-cti
 * Carries out one effect the daemon has accepted. Runs on the server.
 *
 * The daemon owns the rules and the game owns the geometry (ADR-0012), which is
 * why an effect says "a rifle Squad for WEST" and never where it goes: the
 * manifest already knows where each side's Base is, and the daemon has no
 * business holding map coordinates.
 *
 * Arguments:
 * 0: the effect <HASHMAP> — `effect`, `side`, `args`
 *
 * Return Value: <BOOL> whether it was carried out. False means the effect stays
 * unacknowledged and will be delivered again.
 */
params [["_effect", createHashMap, [createHashMap]]];

if (!isServer) exitWith { false };

private _name = _effect getOrDefault ["effect", ""];
private _sideName = _effect getOrDefault ["side", ""];
private _args = _effect getOrDefault ["args", createHashMap];

// An Objective changing hands is announced as an effect and also reflected in
// every observe reply. The reply is what repaints the map; this exists so a
// capture is an event something can react to, not only a state to poll.
if (_name isEqualTo "objective_captured") exitWith {
    diag_log format ["CTI|effect_applied effect=%1 side=%2 objective=%3",
        _name, _sideName, _args getOrDefault ["objective", "?"]];
    true
};

// The last effect any Campaign produces (#35). The daemon decided the Campaign
// was over; what is left is the world's half of it.
if (_name isEqualTo "campaign_won") exitWith {
    [_sideName, _args] call cti_fnc_campaignEnd
};

if (_name isEqualTo "order_issued") exitWith {
    [_args getOrDefault ["squad", ""],
        _args getOrDefault ["order", ""],
        _args getOrDefault ["place", ""]] call cti_fnc_orderApply
};

if (_name isNotEqualTo "squad_spawned") exitWith {
    diag_log format ["CTI|FAIL class=assertion_failed unknown_effect=%1", _name];
    false
};

private _side = switch (toUpper _sideName) do {
    case "WEST": { west };
    case "EAST": { east };
    default { sideUnknown };
};
if (_side isEqualTo sideUnknown) exitWith {
    diag_log format ["CTI|FAIL class=assertion_failed effect_unknown_side=%1", _sideName];
    false
};

private _map = missionNamespace getVariable ["cti_map", createHashMap];
private _base = [];
{
    if ((_x getOrDefault ["side", ""]) isEqualTo toUpper _sideName) exitWith { _base = _x };
} forEach (_map getOrDefault ["bases", []]);

if (count _base isEqualTo 0) exitWith {
    diag_log format ["CTI|FAIL class=assertion_failed no_base_for_side=%1", _sideName];
    false
};

(_base get "position") params ["_east", "_north"];
private _unitType = ["O_Soldier_F", "B_Soldier_F"] select (_side isEqualTo west);
private _size = _args getOrDefault ["size", 8];

private _group = createGroup [_side, true];
for "_i" from 1 to _size do {
    _group createUnit [_unitType, [_east, _north, 0], [], 30, "FORM"];
};

// The daemon minted the id; the world records which group answers to it, so an
// Order naming that Squad has something to reach (#14).
private _squadId = _args getOrDefault ["squad", ""];
(missionNamespace getVariable ["cti_squads", createHashMap]) set [_squadId, _group];
_group setVariable ["cti_squad", _squadId, true];

diag_log format ["CTI|effect_applied effect=%1 side=%2 squad=%3 squad_type=%4 units=%5 base=%6",
    _name, _sideName, _squadId, _args getOrDefault ["squad_type", "?"],
    count units _group, _base get "id"];

// A new Squad is in Reserve until it is told otherwise, which is the daemon's
// view of it too. Applying it here rather than assuming it means a Squad
// standing at its Base is under an Order like any other, not a special case.
[_squadId, "reserve", ""] call cti_fnc_orderApply
