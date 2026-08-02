/*
 * Author: arma-cti
 * Puts a simulation load on a headless client, for the #8 investigation.
 *
 * An idle headless client barely exchanges anything — its sampled bandwidth
 * falls to zero and its ping reads as the engine's "no measurement" sentinel —
 * so a clean desync reading from one proves the connection stayed up, not that
 * the link carries a player's traffic. Transferring AI groups to it makes the
 * server stream real simulation across the same boundary a player would use.
 *
 * Not gameplay: this exists to make a diagnostic honest, and nothing in the
 * Campaign calls it.
 *
 * Runs on the server, and interior to its call graph, so it carries no locality
 * guard: its one caller is `missions/cti.Stratis/initServer.sqf`, which the
 * engine runs on the server and nowhere else (#118, ADR-0041).
 *
 * Arguments:
 * 0: groups to hand over <NUMBER> (optional, default 4)
 * 1: units per group <NUMBER> (optional, default 8)
 *
 * Return Value: <NUMBER> groups actually transferred
 */
params [["_groupCount", 4, [0]], ["_unitCount", 8, [0]]];

// Index 1 of getUserInfo is the client's owner id, which is what setGroupOwner
// wants; index 7 says whether it is headless.
//
// A headless client is loaded by handing it ownership, because it simulates
// what it owns and nothing else. A headed client needs the opposite: the AI
// stay server-owned, and the client pays for receiving their updates, which is
// the traffic a player actually carries. So ownership transfer is conditional
// and the spawning is not.
private _target = -1;
{
    private _info = getUserInfo _x;
    if (count _info > 7 && {_info # 7}) then { _target = _info # 1 };
} forEach allUsers;

private _map = missionNamespace getVariable ["cti_map", createHashMap];
private _objectives = _map getOrDefault ["objectives", []];
if (count _objectives isEqualTo 0) exitWith {
    diag_log "CTI|desync_load skipped=no_objectives";
    0
};

private _transferred = 0;
for "_i" from 0 to (_groupCount - 1) do {
    private _objective = _objectives select (_i % (count _objectives));
    (_objective get "position") params ["_east", "_north"];
    private _spawn = [_east, _north, 0];

    private _group = createGroup [west, true];
    for "_u" from 1 to _unitCount do {
        _group createUnit ["B_Soldier_F", _spawn, [], 50, "FORM"];
    };

    // Somewhere to walk to, so the units keep generating updates rather than
    // standing still and going quiet like the client they are meant to load.
    private _destination = _objectives select ((_i + 1) % (count _objectives));
    (_destination get "position") params ["_toEast", "_toNorth"];
    _group move [_toEast, _toNorth, 0];

    // The one exemption from ADR-0039's ban on setGroupOwner: these groups are
    // throwaway load traffic for the #8 investigation, never Squads under
    // Orders, so nothing here goes near fn_orderApply's local waypoint calls.
    // tools/check_sqf_bans.py enforces the ban and names this file.
    if (_target >= 0 && {_group setGroupOwner _target}) then {
        _transferred = _transferred + 1;
    };
};

diag_log format ["CTI|desync_load groups=%1 units_each=%2 transferred=%3 owner=%4 mode=%5",
    _groupCount, _unitCount, _transferred, _target,
    ["server_owned", "handed_to_headless"] select (_target >= 0)];

_transferred
