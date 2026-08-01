// Leg A of the #45 sequential-multiplexing experiment: dirty every kind of
// state a cycled mission could inherit, record what it looks like dirty, then
// ask the server to switch missions from inside the world.
//
// Exploration scaffolding, not a corpus probe: it lives under spike/cycle/ so
// `just regress` never picks it up (docs/regression-tier.md: membership is by
// directory).
//
// The four kinds of state, and how this leg dirties each:
//   Campaign  — captures agia_marina, so an Objective changes hands
//   roster    — buys two rifle Squads through the Command Port
//   telemetry — the buys and the capture are rows in the daemon's file
//   PRNG      — draws from a fixed seed and logs the draw, so leg B can be
//               compared against it rather than against a number in a comment
[] spawn {
    private _extension = call cti_fnc_shimName;
    if (_extension isEqualTo "") exitWith {
        diag_log "CTI|FAIL class=infra_unavailable cycle_a_no_shim";
    };
    private _rpc = {
        params ["_envelope"];
        private _raw = ((call cti_fnc_shimName) callExtension ["rpc_keepalive", [toJSON _envelope]]) # 0;
        fromJSON _raw
    };

    // The seeded PRNG, drawn from a fixed seed. Whatever this is, leg B must
    // draw the same — a stream that carried over would not.
    private _stream = [77777] call cti_fnc_prngNew;
    private _draws = [];
    for "_i" from 1 to 5 do { _draws pushBack ([_stream, 1000] call cti_fnc_prngInt) };
    diag_log format ["CTI|cycle_prng leg=a seed=77777 draws=%1", _draws];

    // World built, effect pump polled, report loop cycled — waited on the
    // world's own counters with the old 20 s settle kept as the deadline, which
    // is #46's rule. It was a raw dwell here for as long as cycle.sh staged the
    // legs without spike/probe-prelude.sqf and this function did not exist in
    // this world (#81).
    [20] call cti_probe_fnc_worldReady;

    // Roster: two Squads on WEST's books.
    for "_i" from 1 to 2 do {
        [createHashMapFromArray [
            ["id", format ["cycle-a-buy-%1", _i]],
            ["verb", "command"],
            ["payload", createHashMapFromArray [
                ["command", "purchase"],
                ["side", "WEST"],
                ["args", createHashMapFromArray [["squad_type", "rifle"]]]
            ]]
        ]] call _rpc;
    };
    private _deadline = diag_tickTime + 60;
    waitUntil {
        count (missionNamespace getVariable ["cti_squads", createHashMap]) >= 2
            || { diag_tickTime > _deadline }
    };
    private _squads = missionNamespace getVariable ["cti_squads", createHashMap];
    if (count _squads < 2) exitWith {
        diag_log format ["CTI|FAIL class=timeout cycle_a_no_squads held=%1", count _squads];
    };

    // Campaign: ground changes hands. Planted rather than marched — what is
    // being dirtied is the daemon's ownership table, not the Order path.
    private _map = missionNamespace getVariable ["cti_map", createHashMap];
    private _objective = ((_map getOrDefault ["objectives", []]) select {
        (_x get "id") isEqualTo "agia_marina"
    }) # 0;
    (_objective get "position") params ["_east", "_north"];
    private _group = createGroup west;
    _group createUnit ["B_Soldier_F", [_east, _north, 0], [], 0, "NONE"];

    _deadline = diag_tickTime + 120;
    waitUntil {
        ((missionNamespace getVariable ["cti_objectiveOwner", createHashMap])
            getOrDefault ["agia_marina", ""]) isEqualTo "WEST"
            || { diag_tickTime > _deadline }
    };
    private _owner = (missionNamespace getVariable ["cti_objectiveOwner", createHashMap])
        getOrDefault ["agia_marina", ""];
    if !(_owner isEqualTo "WEST") exitWith {
        diag_log format ["CTI|FAIL class=timeout cycle_a_no_capture owner=%1", _owner];
    };

    // The dirty picture, off the daemon rather than off our own memory of
    // having dirtied it. `view` is the side-scoped observation
    // (addons/main/functions/fn_commanderView.sqf).
    private _view = [createHashMapFromArray [
        ["id", "cycle-a-view"],
        ["verb", "view"],
        ["payload", createHashMapFromArray [["side", "WEST"]]]
    ]] call _rpc;
    private _result = _view getOrDefault ["result", createHashMap];
    diag_log format ["CTI|cycle_state leg=a funds=%1 squads=%2 owners=%3",
        _result getOrDefault ["funds", -1],
        count (_result getOrDefault ["squads", []]),
        _result getOrDefault ["owners", createHashMap]];
    diag_log "CTI|cycle_a_probe_done";

    // The switch, from inside the world. serverCommand's alternate syntax runs
    // on the server with the config's serverCommandPassword standing in for an
    // admin login (commands/serverCommand.wiki).
    //
    // Logged before the call rather than after: the runner restarts the daemon
    // on this line, and after the call there may be no world left to log from.
    diag_log "CTI|cycle_switch_requested to=ctycle1.Stratis";
    private _accepted = "ctispike" serverCommand "#mission ctycle1.Stratis";
    diag_log format ["CTI|cycle_switch_returned accepted=%1", _accepted];
};
