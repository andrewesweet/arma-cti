// Phase-1 Stratis mission, server side. Thin by design (ADR-0007): this asks
// the addon to build the world and reports what happened. No rules live here.
//
// The Linux dedicated server writes no RPT file and `-profiles=` is broken
// (ADR-0006), so stdout is the only log and every line goes there.

// Written into the mission by the harness at bring-up; absent when the mission
// is run by hand, which is why nothing here depends on it existing.
if (fileExists "harness.sqf") then {
    call compile preprocessFileLineNumbers "harness.sqf";
};

diag_log format ["CTI|mission_running world=%1 tickTime=%2", worldName, diag_tickTime];
diag_log format ["CTI|server_version=%1", productVersion];

if (isNil "cti_fnc_worldInit") then {
    diag_log "CTI|FAIL class=assertion_failed addon_functions_unresolved";
} else {
    private _built = call cti_fnc_worldInit;

    if (_built) then {
        // The manifest names one HQ structure per Base; Decapitation has nothing
        // to destroy if the mission did not place it under that name.
        {
            private _name = _x get "hq";
            private _hq = missionNamespace getVariable [_name, objNull];
            if (isNull _hq) then {
                diag_log format ["CTI|FAIL class=assertion_failed hq_missing base=%1 name=%2",
                    _x get "id", _name];
            } else {
                // Placed by eye in the editor file, so drop it onto the terrain
                // rather than leaving it floating or buried.
                private _at = getPosATL _hq;
                _hq setPosATL [_at # 0, _at # 1, 0];
                diag_log format ["CTI|hq base=%1 name=%2 type=%3 pos=%4",
                    _x get "id", _name, typeOf _hq, mapGridPosition _hq];
            };
        } forEach ((missionNamespace getVariable ["cti_map", createHashMap]) getOrDefault ["bases", []]);

        private _owners = missionNamespace getVariable ["cti_objectiveOwner", createHashMap];
        diag_log format ["CTI|objectives_marked count=%1 owners=%2",
            count _owners, values _owners];
    };
};

// Issue #8: a Windows client spawned, could not move, and reported "No message
// received" while the server logged nothing. Watching desync costs a sample
// every few seconds and turns the next join into evidence rather than a
// recollection. CTI_DESYNC_WATCH_SECS is set by the harness at bring-up.
private _watchFor = missionNamespace getVariable ["CTI_DESYNC_WATCH_SECS", 0];
if (_watchFor > 0) then {
    [_watchFor] call cti_fnc_desyncWatch;
    diag_log format ["CTI|desync_watch_started window=%1", _watchFor];
};

diag_log "CTI|done";
