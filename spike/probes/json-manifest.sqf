// probe: json-manifest
// issues: 22
// window: 150
//
// #22 in-world probe: the addon reads the authored JSON, and the world it
// builds from it is the same world.
//
// `just regress json-manifest`, or by hand
// `just probe spike/probes/json-manifest.sqf`. Appended to the generated
// harness at bring-up, never packed into the mission.
//
// The default 150 s window is right: the subject is a file being read at
// mission start and a Purchase being judged on the synchronous path. Nothing
// here waits on a natural process except the effect pump carrying the bought
// Squad into the world, which is frame-bound.
//
// What no unit test can stand in for. Python parses the same file with
// `json.loads` and always could; the claim ADR-0017 rests on is that *Arma*
// parses it — that `loadFile` reaches inside a packed PBO without file
// patching, that `fromJSON` turns the authored document into the HashMap
// shape `cti_fnc_worldInit` and `cti_fnc_command` already read, and that
// numbers, nested objects and arrays survive the crossing. None of that is
// visible from Python, and the old generated-SQF path never had to answer it.
//
// So the assertions are deliberately about values, not counts alone: an
// Objective's capture radius, a Base's HQ name, a display name with a space in
// it, and the marker actually painted on the map from those values.
[] spawn {
    private _extension = call cti_fnc_shimName;
    if (_extension isEqualTo "") exitWith {
        diag_log "CTI|FAIL class=infra_unavailable json_probe_no_shim";
    };

    private _rpc = {
        params ["_envelope"];
        private _raw = ((call cti_fnc_shimName) callExtension ["rpc_keepalive", [toJSON _envelope]]) # 0;
        fromJSON _raw
    };

    // Let the world finish building.
    private _next = diag_tickTime + 20;
    waitUntil { diag_tickTime >= _next };

    // ------------------------------------------------ the manifest crossed
    private _map = missionNamespace getVariable ["cti_map", createHashMap];
    if (count _map isEqualTo 0) exitWith {
        diag_log "CTI|FAIL class=assertion_failed json_probe_no_map";
    };

    private _objectives = _map getOrDefault ["objectives", []];
    private _bases = _map getOrDefault ["bases", []];
    diag_log format ["CTI|json_probe_loaded id=%1 world=%2 objectives=%3 bases=%4",
        _map getOrDefault ["id", ""], _map getOrDefault ["world", ""],
        count _objectives, count _bases];

    if (count _objectives isEqualTo 0 || {count _bases isEqualTo 0}) exitWith {
        diag_log "CTI|FAIL class=assertion_failed json_probe_manifest_empty";
    };

    // Values, not just shape. A parse that produced eight empty HashMaps would
    // pass a count check and fail every one of these.
    private _tempest = (_objectives select { (_x getOrDefault ["id", ""]) isEqualTo "camp_tempest" });
    if (count _tempest isEqualTo 0) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed json_probe_no_camp_tempest ids=%1",
            _objectives apply { _x getOrDefault ["id", ""] }];
    };
    _tempest = _tempest # 0;

    // A number the authored file carries and nothing else does, a display name
    // with a space in it, and a two-element position array.
    private _radius = _tempest getOrDefault ["capture_radius", 0];
    private _name = _tempest getOrDefault ["display_name", ""];
    private _position = _tempest getOrDefault ["position", []];
    if !(_radius isEqualTo 121) then {
        diag_log format ["CTI|FAIL class=assertion_failed json_probe_radius=%1 wanted=121", _radius];
    };
    if !(_name isEqualTo "Camp Tempest") then {
        diag_log format ["CTI|FAIL class=assertion_failed json_probe_display_name=%1", _name];
    };
    if !(count _position isEqualTo 2 && {(_position # 0) isEqualType 0}) then {
        diag_log format ["CTI|FAIL class=assertion_failed json_probe_position=%1", _position];
    };
    // A nested array inside a nested object: the deepest thing in the document.
    if !("agia_marina" in (_tempest getOrDefault ["adjacent", []])) then {
        diag_log format ["CTI|FAIL class=assertion_failed json_probe_adjacent=%1",
            _tempest getOrDefault ["adjacent", []]];
    };
    diag_log format ["CTI|json_probe_values radius=%1 name=%2 position=%3 adjacent=%4",
        _radius, _name, _position, _tempest getOrDefault ["adjacent", []]];

    // The Base's HQ name is what Decapitation resolves against, and it is a
    // string only the authored file holds.
    private _west = (_bases select { (_x getOrDefault ["side", ""]) isEqualTo "WEST" });
    if (count _west isEqualTo 0) exitWith {
        diag_log "CTI|FAIL class=assertion_failed json_probe_no_west_base";
    };
    if !(((_west # 0) getOrDefault ["hq", ""]) isEqualTo "cti_hq_west") then {
        diag_log format ["CTI|FAIL class=assertion_failed json_probe_hq=%1",
            (_west # 0) getOrDefault ["hq", ""]];
    };

    // ------------------------------------------------ Objectives marked
    // The visible half: every Objective in the file has both its dot and its
    // capture area on the map, drawn from the parsed values.
    private _missing = [];
    {
        private _id = _x getOrDefault ["id", ""];
        private _dot = format ["cti_objective_%1", _id];
        private _area = format ["cti_objective_%1_area", _id];
        if (markerType _dot isEqualTo "" || {markerShape _area isEqualTo ""}) then {
            _missing pushBack _id;
        };
    } forEach _objectives;
    {
        private _marker = format ["cti_base_%1", _x getOrDefault ["id", ""]];
        if (markerType _marker isEqualTo "") then { _missing pushBack (_x getOrDefault ["id", ""]) };
    } forEach _bases;
    if (_missing isNotEqualTo []) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed json_probe_unmarked=%1", _missing];
    };
    // The marker carries the authored display name and the authored radius, so
    // the map a Commander looks at is the document, not a default.
    private _size = markerSize "cti_objective_camp_tempest_area";
    if !((markerText "cti_objective_camp_tempest") isEqualTo "Camp Tempest" && {(_size # 0) isEqualTo 121}) then {
        diag_log format ["CTI|FAIL class=assertion_failed json_probe_marker text=%1 size=%2",
            markerText "cti_objective_camp_tempest", _size];
    };
    diag_log format ["CTI|json_probe_marked objectives=%1 bases=%2 tempest_area=%3",
        count _objectives, count _bases, _size];

    // ------------------------------------------------ the schema crossed
    private _schema = call cti_fnc_commandSchema;
    if (count _schema isEqualTo 0) exitWith {
        diag_log "CTI|FAIL class=assertion_failed json_probe_no_schema";
    };
    private _catalogue = _schema getOrDefault ["commands", createHashMap];
    if !("purchase" in _catalogue && {"order" in _catalogue}) then {
        diag_log format ["CTI|FAIL class=assertion_failed json_probe_catalogue=%1", keys _catalogue];
    };
    if !("insufficient_funds" in (_schema getOrDefault ["rejection_codes", []])) then {
        diag_log format ["CTI|FAIL class=assertion_failed json_probe_codes=%1",
            _schema getOrDefault ["rejection_codes", []]];
    };
    // The price table is read by the UI for display and by nothing else, so a
    // number arriving as a string would show up nowhere until a Play Session.
    private _rifle = (_schema getOrDefault ["squads", createHashMap]) getOrDefault ["rifle", createHashMap];
    if !((_rifle getOrDefault ["price", ""]) isEqualType 0) then {
        diag_log format ["CTI|FAIL class=assertion_failed json_probe_price_not_a_number=%1",
            _rifle getOrDefault ["price", ""]];
    };
    diag_log format ["CTI|json_probe_schema commands=%1 codes=%2 rifle_price=%3",
        keys _catalogue, count (_schema getOrDefault ["rejection_codes", []]),
        _rifle getOrDefault ["price", -1]];

    // Read once, cached: the second call must be the same document rather than
    // a second trip to disk that happens to agree.
    if !((call cti_fnc_commandSchema) isEqualTo _schema) then {
        diag_log "CTI|FAIL class=assertion_failed json_probe_schema_not_cached";
    };

    // cti_fnc_command builds against that schema. A Command it refuses to build
    // is one the parsed catalogue did not carry.
    private _built = ["purchase", [["squad_type", "rifle"]]] call cti_fnc_command;
    if (count _built isEqualTo 0) exitWith {
        diag_log "CTI|FAIL class=assertion_failed json_probe_command_not_built";
    };

    // ------------------------------------------------ the port still judges
    private _reply = [createHashMapFromArray [
        ["id", "json-probe-buy"],
        ["verb", "command"],
        ["payload", createHashMapFromArray [
            ["command", "purchase"],
            ["side", "WEST"],
            ["args", createHashMapFromArray [["squad_type", "rifle"]]]
        ]]
    ]] call _rpc;
    if !(_reply isEqualType createHashMap) exitWith {
        diag_log "CTI|FAIL class=oracle_disagreement json_probe_unreadable_reply";
    };
    private _status = _reply getOrDefault ["status", ""];
    if !(_status isEqualTo "ok") exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed json_probe_purchase_status=%1 reply=%2",
            _status, _reply];
    };
    diag_log format ["CTI|json_probe_purchase_accepted result=%1",
        _reply getOrDefault ["result", createHashMap]];

    // A judgement is only a judgement if it can also say no. The daemon prices
    // the Squad from the same table the schema exported, so a Purchase of
    // something that is not in it must be refused with a typed code.
    private _refusal = [createHashMapFromArray [
        ["id", "json-probe-nonsense"],
        ["verb", "command"],
        ["payload", createHashMapFromArray [
            ["command", "purchase"],
            ["side", "WEST"],
            ["args", createHashMapFromArray [["squad_type", "battleship"]]]
        ]]
    ]] call _rpc;
    private _code = (_refusal getOrDefault ["reason", createHashMap]) getOrDefault ["code", ""];
    if !((_refusal getOrDefault ["status", ""]) isEqualTo "rejected") then {
        diag_log format ["CTI|FAIL class=assertion_failed json_probe_nonsense_not_refused=%1", _refusal];
    };
    if !(_code in (_schema getOrDefault ["rejection_codes", []])) then {
        diag_log format ["CTI|FAIL class=assertion_failed json_probe_untyped_refusal=%1", _code];
    };
    diag_log format ["CTI|json_probe_refusal code=%1", _code];

    // The Squad arrives through the outbox, so wait for the world to hold it
    // rather than assuming the pump has run.
    private _deadline = diag_tickTime + 60;
    waitUntil {
        count (missionNamespace getVariable ["cti_squads", createHashMap]) > 0
            || { diag_tickTime > _deadline }
    };
    private _squads = missionNamespace getVariable ["cti_squads", createHashMap];
    if (count _squads isEqualTo 0) exitWith {
        diag_log "CTI|FAIL class=timeout json_probe_no_squad_spawned";
    };
    diag_log format ["CTI|json_probe_squad_arrived squads=%1 leader_at=%2",
        count _squads, mapGridPosition (leader ((values _squads) # 0))];

    // ------------------------------------------------ the loud failure
    // cti_fnc_manifestLoad refuses a missing manifest, and the harness treats
    // any CTI|FAIL as a failed run — so calling it for a world with no file
    // would redden this probe by design. What is checked here instead is the
    // engine behaviour that guard rests on, which is the part that could
    // silently differ: loadFile on a path that is not in any PBO returns the
    // empty string rather than the last file read, or a script error, or a
    // stale cache. The guard branch itself is exercised by a separate
    // deliberately-red run (see #22).
    private _absent = loadFile "cti\addons\main\manifests\atlantis.json";
    if !(_absent isEqualTo "") then {
        diag_log format ["CTI|FAIL class=assertion_failed json_probe_absent_file_returned=%1 bytes=%2",
            _absent select [0, 40], count _absent];
    };
    // And an unparseable document is not a HashMap, which is what the second
    // guard branch tests. The comparison is taken once and named: fromJSON
    // returns nil on a document it cannot read, and an inline `nil isEqualType`
    // inside a format argument list reports as neither true nor false.
    private _garbage = fromJSON "{""bases"": [";
    private _garbageIsMap = !isNil "_garbage" && {_garbage isEqualType createHashMap};
    if (_garbageIsMap) then {
        diag_log "CTI|FAIL class=assertion_failed json_probe_garbage_parsed_as_object";
    };
    diag_log format ["CTI|json_probe_guards absent_bytes=%1 garbage_is_hashmap=%2",
        count _absent, str _garbageIsMap];

    diag_log "CTI|json_probe_done";
};
