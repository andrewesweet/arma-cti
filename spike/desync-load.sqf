// Puts a simulation load on a joining client, for the #8 investigation.
//
// Staged by `spike/run.sh` into the generated harness when CTI_DESYNC_LOAD is
// set, and shipped in nothing. It used to be `addons/main/functions/
// fn_desyncLoad.sqf`, called from `missions/cti.Stratis/initServer.sqf`: an
// investigation tool present in every build, one environment variable away from
// spawning thirty-two WEST soldiers on the first four Objectives in a Campaign a
// person was playing. #19's audit named that as one of the Command Port's three
// holes and #128 moved it here, under the rule run.sh already states for probes
// — the mission is the thing under test, and a tool that lives in it is one that
// ships (ADR-0045).
//
// Why it exists at all: an idle client barely exchanges anything — its sampled
// bandwidth falls to zero and its ping reads as the engine's "no measurement"
// sentinel — so a clean desync reading from one proves the connection stayed up,
// not that the link carries a player's traffic. Putting AI on the far side of
// that link makes the server stream real simulation across the same boundary a
// player would use.
//
// Not gameplay, and mutually exclusive with a Campaign: capture is by presence,
// so the soldiers it spawns hand WEST half the island. That is the reason it is
// opt-in, and now also the reason it is not in the build.
//
// Runs on the server: the harness is called from initServer.sqf, which the
// engine runs there and nowhere else (ADR-0041).
[] spawn {
    // The harness runs at the top of initServer.sqf, before the world is built,
    // so this waits for the Objectives it spawns onto rather than reading an
    // empty map. Same helper every probe uses, and the same deadline.
    [20] call cti_probe_fnc_worldReady;

    private _deadline = diag_tickTime + 120;
    waitUntil { count allUsers > 0 || { diag_tickTime > _deadline } };
    if (count allUsers isEqualTo 0) exitWith {
        diag_log "CTI|desync_load skipped=no_client";
    };

    private _groupCount = 4;
    private _unitCount = 8;

    // Index 1 of getUserInfo is the client's owner id, which is what
    // setGroupOwner wants; index 7 says whether it is headless.
    //
    // A headless client is loaded by handing it ownership, because it simulates
    // what it owns and nothing else. A headed client needs the opposite: the AI
    // stay server-owned, and the client pays for receiving their updates, which
    // is the traffic a player actually carries. So ownership transfer is
    // conditional and the spawning is not.
    private _target = -1;
    {
        private _info = getUserInfo _x;
        if (count _info > 7 && {_info # 7}) then { _target = _info # 1 };
    } forEach allUsers;

    private _map = missionNamespace getVariable ["cti_map", createHashMap];
    private _objectives = _map getOrDefault ["objectives", []];
    if (count _objectives isEqualTo 0) exitWith {
        diag_log "CTI|desync_load skipped=no_objectives";
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

        // The one exemption from ADR-0039's ban on setGroupOwner, and it travels
        // with the file: these groups are throwaway load traffic for the #8
        // investigation, never Squads under Orders, so nothing here goes near
        // fn_orderApply's local waypoint calls. tools/check_sqf_bans.py enforces
        // the ban and names this file.
        if (_target >= 0 && {_group setGroupOwner _target}) then {
            _transferred = _transferred + 1;
        };
    };

    diag_log format ["CTI|desync_load groups=%1 units_each=%2 transferred=%3 owner=%4 mode=%5",
        _groupCount, _unitCount, _transferred, _target,
        ["server_owned", "handed_to_headless"] select (_target >= 0)];
};
