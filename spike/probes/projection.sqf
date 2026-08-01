// probe: projection
// issues: 27
// window: 150
//
// #27 in-world probe: the server takes the public picture and still repaints.
//
// `just regress projection`, or by hand
// `just probe spike/probes/projection.sqf`. Appended to the generated
// harness at bring-up, never packed into the mission — the mission is the thing
// under test, and a probe that ships in it is one that ships.
[] spawn {
    private _extension = call cti_fnc_shimName;
    if (_extension isEqualTo "") exitWith {
        diag_log "CTI|FAIL class=infra_unavailable projection_probe_no_shim";
    };

    // Let the world finish building and the report loop get a cycle in.
    private _next = diag_tickTime + 20;
    waitUntil { diag_tickTime >= _next };

    // Ground a side holds is the thing the reply has to keep carrying. Spawned
    // here rather than bought and walked: what is under test is the marker path,
    // not the Order path, and agia_marina is 2 km from the NATO base.
    private _map = missionNamespace getVariable ["cti_map", createHashMap];
    private _objective = ((_map getOrDefault ["objectives", []]) select {
        (_x get "id") isEqualTo "agia_marina"
    }) # 0;
    (_objective get "position") params ["_east", "_north"];
    private _group = createGroup west;
    private _unit = _group createUnit ["B_Soldier_F", [_east, _north, 0], [], 0, "NONE"];
    diag_log format ["CTI|projection_probe_planted at=%1 alive=%2",
        mapGridPosition _unit, alive _unit];

    // capture_seconds is 30 and reports run every 5, so a minute is generous.
    private _deadline = diag_tickTime + 90;
    waitUntil {
        private _owners = missionNamespace getVariable ["cti_objectiveOwner", createHashMap];
        (_owners getOrDefault ["agia_marina", ""]) isEqualTo "WEST"
            || { diag_tickTime > _deadline }
    };
    private _owner = (missionNamespace getVariable ["cti_objectiveOwner", createHashMap])
        getOrDefault ["agia_marina", ""];
    if !(_owner isEqualTo "WEST") exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed projection_probe_marker_stuck owner=%1", _owner];
    };
    diag_log "CTI|projection_probe_repainted objective=agia_marina owner=WEST";

    // And what the reply actually carried. Read here rather than inferred from
    // the marker: absence is the claim, and only the raw document can show it.
    private _envelope = createHashMapFromArray [
        ["id", "projection-probe"],
        ["verb", "observe"],
        ["payload", createHashMapFromArray [
            ["time", time],
            ["presence", call cti_fnc_presenceSample]
        ]]
    ];
    private _raw = (_extension callExtension ["rpc_keepalive", [toJSON _envelope]]) # 0;
    private _reply = fromJSON _raw;
    if !(_reply isEqualType createHashMap) exitWith {
        diag_log format ["CTI|FAIL class=oracle_disagreement projection_probe_unreadable=%1", _raw];
    };

    private _result = _reply getOrDefault ["result", createHashMap];
    private _keys = keys _result;
    diag_log format ["CTI|projection_probe_reply keys=%1 bytes=%2", _keys, count _raw];
    private _private = _keys select { _x in ["side", "funds", "squads", "paid", "lost"] };
    if (count _private > 0) then {
        diag_log format ["CTI|FAIL class=assertion_failed projection_probe_private_keys=%1", _private];
    };
    if !("owners" in _keys) then {
        diag_log "CTI|FAIL class=assertion_failed projection_probe_no_owners";
    };

    diag_log "CTI|projection_probe_done";
};
