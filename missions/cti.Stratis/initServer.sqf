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

// Without these, a client that connects but never enters the mission is
// indistinguishable from one that never connected at all.
onPlayerConnected {
    diag_log format ["CTI|player_connected name=%1 id=%2 uid=%3 owner=%4 jip=%5",
        _name, _id, _uid, _owner, _jip];
};
onPlayerDisconnected {
    diag_log format ["CTI|player_disconnected name=%1 id=%2", _name, _id];
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

        // Effects the daemon has accepted arrive here, through the outbox, for
        // both Commanders alike. Started after the world is built because an
        // effect has nowhere to land until the Bases exist.
        [] call cti_fnc_effectPump;

        // Every death, written down as it happens (#39). Started before the
        // report loop, because a death between the two would be a death nobody
        // recorded — and the whole point is that the record has no holes in it
        // that have to be guessed at afterwards.
        [] call cti_fnc_casualtyWatch;

        // The world reports who is standing where; the daemon decides what
        // that means and pays for it.
        [] call cti_fnc_presenceReport;

        // Who commands each side, when the Commander is a person (#18), and
        // that person's own Observation on their own map. Started after the
        // world is built because a view names places, and before anyone can
        // join because a Commander slot can be taken at any moment.
        [] call cti_fnc_commanderAssign;
        [] call cti_fnc_commanderView;

        // An Order outlives the waypoint that carried it, and the leader who
        // was carrying it.
        [] call cti_fnc_orderEnforce;

        // A Squad under an Assault Order brings the enemy HQ down, and an HQ
        // that falls is said so once (#33). Started after the HQ check above,
        // because the sweep's whole subject is those structures.
        [] call cti_fnc_baseAssault;

        // The curated loadout menu, the Base-only rule that grants a pick off
        // it, and the kit a player keeps through a respawn (#172, ADR-0056).
        // Started after the world is built, because "at his own Base" is a
        // reading of the manifest cti_fnc_worldInit indexes.
        [] call cti_fnc_loadoutWatch;

        // Something watches the seven loops above (#102). Started last, because a
        // watchdog registered before the loops it watches would sweep a register
        // that is still filling; started at all, because a scripting error in
        // any one of them kills that loop alone and used to do it in silence.
        [] call cti_fnc_loopWatch;
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

// The load generator that gives a joining client something to simulate used to
// live here, behind CTI_DESYNC_LOAD, and in the addon as `cti_fnc_desyncLoad`.
// It is `spike/desync-load.sqf` now, staged into the harness by the run that
// asks for it and shipped in nothing (#128, ADR-0045): the watcher above is
// diagnostics the mission is entitled to carry, and the loader is an
// investigation tool that spawns thirty-two WEST soldiers on the first four
// Objectives — which capture-by-presence turns into half the island.

diag_log "CTI|done";
