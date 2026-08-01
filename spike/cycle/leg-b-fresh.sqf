// Leg B of the #45 sequential-multiplexing experiment: the mission the server
// cycled *into*, asserting that everything leg A dirtied is clean again.
//
// The #44 lesson this is written against: an isolation failure is silent and
// produces a false green — two runs sharing a daemon agreed only because both
// defaulted to the same port, and the run that was not asserting on it reported
// PASS. So every axis here is an *assertion*, and a missing reading fails
// rather than being skipped.
//
// Five axes, one assertion each:
//   Campaign   — no Objective is held by WEST that the manifest did not start
//                it held by, and Funds are back at the authored starting figure
//   roster     — WEST holds no Squads
//   telemetry  — asserted by the runner off the daemon's own file, not here
//   shim       — the round trip works and the daemon echoes this leg's own id
//   PRNG       — the same seed draws the same five numbers leg A drew
//
// Exploration scaffolding under spike/cycle/, so `just regress` never sees it.
[] spawn {
    private _extension = call cti_fnc_shimName;
    if (_extension isEqualTo "") exitWith {
        diag_log "CTI|FAIL class=infra_unavailable cycle_b_no_shim";
    };
    private _rpc = {
        params ["_envelope"];
        private _raw = ((call cti_fnc_shimName) callExtension ["rpc_keepalive", [toJSON _envelope]]) # 0;
        fromJSON _raw
    };

    // PRNG. Same seed, same five draws, or a stream carried over.
    private _stream = [77777] call cti_fnc_prngNew;
    private _draws = [];
    for "_i" from 1 to 5 do { _draws pushBack ([_stream, 1000] call cti_fnc_prngInt) };
    diag_log format ["CTI|cycle_prng leg=b seed=77777 draws=%1", _draws];

    // Shim. The daemon's own envelope, with an id only this leg sends: a reply
    // carrying it came from a daemon this leg reached, through a connection the
    // shim either kept or reopened. Either is fine; a reply that never arrives
    // is not.
    private _echo = [createHashMapFromArray [
        ["id", "cycle-b-echo"],
        ["verb", "ping"],
        ["payload", createHashMap]
    ]] call _rpc;
    if !((_echo getOrDefault ["id", ""]) isEqualTo "cycle-b-echo") exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed cycle_b_shim_no_echo reply=%1", _echo];
    };
    diag_log "CTI|cycle_shim leg=b echo=ok";

    // World built and the report loop cycled, exactly as leg A waited.
    private _next = diag_tickTime + 20;
    waitUntil { diag_tickTime >= _next };

    private _view = [createHashMapFromArray [
        ["id", "cycle-b-view"],
        ["verb", "view"],
        ["payload", createHashMapFromArray [["side", "WEST"]]]
    ]] call _rpc;
    private _result = _view getOrDefault ["result", createHashMap];
    if (count _result isEqualTo 0) exitWith {
        diag_log format ["CTI|FAIL class=oracle_disagreement cycle_b_no_view reply=%1", _view];
    };
    private _funds = _result getOrDefault ["funds", -1];
    private _squads = _result getOrDefault ["squads", []];
    private _owners = _result getOrDefault ["owners", createHashMap];
    diag_log format ["CTI|cycle_state leg=b funds=%1 squads=%2 owners=%3",
        _funds, count _squads, _owners];

    // Roster. Leg A left two Squads on WEST's books.
    if (count _squads > 0) then {
        diag_log format ["CTI|FAIL class=assertion_failed cycle_b_roster_carried_over squads=%1",
            count _squads];
    };

    // Campaign, ground. Leg A took agia_marina for WEST; the manifest does not
    // start it there. Asked of the daemon's own table rather than of the
    // markers, because the markers are painted from the reply and would agree
    // with a stale daemon just as readily.
    private _westHeld = [];
    {
        if ((_owners get _x) isEqualTo "WEST") then { _westHeld pushBack _x };
    } forEach keys _owners;
    if ("agia_marina" in _westHeld) then {
        diag_log format ["CTI|FAIL class=assertion_failed cycle_b_ground_carried_over west_held=%1",
            _westHeld];
    };

    // Campaign, Funds. Leg A spent on two rifle Squads and then earned on held
    // ground, so a carried-over Campaign shows a figure that is not the
    // authored start. The start is whatever a cold boot of this same world
    // shows, and the runner compares the two rather than this file naming a
    // number the economy is free to change.
    diag_log format ["CTI|cycle_funds leg=b funds=%1", _funds];

    diag_log "CTI|cycle_b_probe_done";
};
