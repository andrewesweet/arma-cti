/*
 * Author: arma-cti
 * Carries out one effect the daemon has accepted. Runs on the server.
 *
 * The daemon owns the rules and the game owns the geometry (ADR-0012), which is
 * why an effect says "a rifle Squad for WEST" and never where it goes: the
 * manifest already knows where each side's Base is, and the daemon has no
 * business holding map coordinates.
 *
 * ## Why the answer is a verdict rather than a yes/no
 *
 * The pump acknowledges through a high-water mark, so a "no" holds up every
 * effect behind it. A bare `false` gave the pump no way to tell the two kinds of
 * no apart, and it treated both as the recoverable one: an effect this function
 * can *never* carry out — an effect name the addon does not know, a side that is
 * not playing, a side with no Base — came back on every 2 s poll forever and
 * nothing behind it was ever applied (#100). The Campaign then stops progressing
 * with both sides' Funds already spent, and says nothing.
 *
 * So a refusal is classified at the point that knows: `refused` is permanent —
 * the pump dead-letters it and moves on — and `deferred` is worth another poll.
 * Nothing here returns `deferred` today, and that is a statement rather than an
 * oversight: every way this function can fail is a fact about the effect or the
 * world's shape that the next poll will meet unchanged. The word exists so the
 * first genuinely transient failure has somewhere to go that is not an unbounded
 * retry, and so that the choice has to be made deliberately.
 *
 * Arguments:
 * 0: the effect <HASHMAP> — `effect`, `side`, `args`
 *
 * Return Value: <HASHMAP> the verdict — `outcome` one of "applied", "refused"
 * (permanent: acknowledge and dead-letter it) or "deferred" (transient: leave it
 * unacknowledged and try again), and `reason`, the word its FAIL line carries.
 */
params [["_effect", createHashMap, [createHashMap]]];

// The verdict, in the vocabulary above. `_refused` is every failure below; the
// reason is the same word the accompanying FAIL line names.
private _verdict = {
    params [["_outcome", "", [""]], ["_reason", "", [""]]];
    createHashMapFromArray [["outcome", _outcome], ["reason", _reason]]
};

// Unreachable in play — every call path into this starts on the server — but a
// sentinel that a caller could read as a domain refusal is one nobody can
// attribute (#113), so it says which of the two it is.
if (!isServer) exitWith {
    ["cti_fnc_effectApply"] call cti_fnc_offServer;
    ["refused", "off_server"] call _verdict
};

private _name = _effect getOrDefault ["effect", ""];
private _sideName = _effect getOrDefault ["side", ""];
private _args = _effect getOrDefault ["args", createHashMap];

// An Objective changing hands is announced as an effect and also reflected in
// every observe reply. The reply is what repaints the map; this exists so a
// capture is an event something can react to, not only a state to poll.
if (_name isEqualTo "objective_captured") exitWith {
    diag_log format ["CTI|effect_applied effect=%1 side=%2 objective=%3",
        _name, _sideName, _args getOrDefault ["objective", "?"]];
    ["applied"] call _verdict
};

// The two delegating effects still answer in booleans, because "settled" is the
// whole of what their callers need from them and neither has a failure the next
// poll would meet differently: an unreadable `campaign_won` is unreadable
// forever. So false becomes a permanent refusal here, at the one place that has
// to decide.
//
// The last effect any Campaign produces (#35). The daemon decided the Campaign
// was over; what is left is the world's half of it.
if (_name isEqualTo "campaign_won") exitWith {
    if ([_sideName, _args] call cti_fnc_campaignEnd) then { ["applied"] call _verdict }
    else { ["refused", "campaign_end_refused"] call _verdict }
};

if (_name isEqualTo "order_issued") exitWith {
    private _settled = [_args getOrDefault ["squad", ""],
        _args getOrDefault ["order", ""],
        _args getOrDefault ["place", ""]] call cti_fnc_orderApply;
    if (_settled) then { ["applied"] call _verdict }
    else { ["refused", "order_apply_refused"] call _verdict }
};

// A daemon and an addon out of step after a partial upgrade. Permanent: the same
// name arrives with the same meaning on every poll, and no amount of waiting
// teaches this addon what it is.
if (_name isNotEqualTo "squad_spawned") exitWith {
    diag_log format ["CTI|FAIL class=assertion_failed unknown_effect=%1", _name];
    ["refused", "unknown_effect"] call _verdict
};

private _side = switch (toUpper _sideName) do {
    case "WEST": { west };
    case "EAST": { east };
    default { sideUnknown };
};
if (_side isEqualTo sideUnknown) exitWith {
    diag_log format ["CTI|FAIL class=assertion_failed effect_unknown_side=%1", _sideName];
    ["refused", "effect_unknown_side"] call _verdict
};

// Through the index cti_fnc_worldInit derives beside the map (#109).
private _base = (missionNamespace getVariable ["cti_basesBySide", createHashMap])
    getOrDefault [toUpper _sideName, createHashMap];

if (count _base isEqualTo 0) exitWith {
    diag_log format ["CTI|FAIL class=assertion_failed no_base_for_side=%1", _sideName];
    // A map authors its Bases; a side without one is a world built wrongly, and
    // it will be built the same way on the next poll.
    ["refused", "no_base_for_side"] call _verdict
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
//
// The Squad is spawned either way: a Reserve Order that would not settle must
// not put the men back in the box, so this is reported and not retried. Retrying
// it would spawn the Squad a second time.
if ([_squadId, "reserve", ""] call cti_fnc_orderApply) exitWith { ["applied"] call _verdict };
diag_log format ["CTI|FAIL class=assertion_failed squad_spawned_without_reserve squad=%1", _squadId];
["refused", "squad_spawned_without_reserve"] call _verdict
