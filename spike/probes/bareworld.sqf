// probe: bareworld
// issues: 23
// window: 150
//
// #23 in-world probe: the Phase-1 world stands up, and the six things only a
// live engine can answer for are true of it.
//
// `just regress bareworld`, or by hand `just probe spike/probes/bareworld.sqf`.
//
// The default 150 s window is right: nothing here waits on a natural process.
// The two waits are for loops the mission started at bring-up to complete a
// cycle each, at 2 s and 5 s intervals; they are synchronisation on observable
// state, and if either ran out the answer would be to find out why the loop
// stopped, not to widen the window.
//
// This is the corpus member the design calls bareworld, and it is a probe file
// rather than a bare mission run (ADR-0021). A mission with nothing appended
// has no completion line a runner can wait on — only `CTI|done`, which fires
// before the loops it just started have polled once — so waiting on it would
// have meant a fixed sleep afterwards, and a sleep is the one thing the
// Contract will not take. Everything asserted below is the world's own; the
// probe adds no state to it.
//
// What no unit test can stand in for, and what would otherwise be unprotected
// in Phase 1. Three of these assertions live today only in `spike.Stratis`,
// the Phase-0 measurement mission, which nothing runs per issue: the addon
// resolving by name on a dedicated server, the seeded PRNG against the real
// engine, and the daemon echoing a request id back through `callExtension`.
// The other three — the world the manifest describes actually getting built,
// and each of the two server loops actually turning — had never been asserted
// anywhere when this landed.
[] spawn {
    // 1. The addon loaded. CfgFunctions compiles per machine, so a name that
    // does not resolve here means the addon never reached this one.
    if (isNil "cti_fnc_prngSelfTest" || { isNil "cti_fnc_shimName" }) exitWith {
        diag_log "CTI|FAIL class=assertion_failed bareworld_addon_functions_unresolved";
    };

    private _extension = call cti_fnc_shimName;
    if (_extension isEqualTo "") exitWith {
        diag_log "CTI|FAIL class=infra_unavailable bareworld_probe_no_shim";
    };
    diag_log format ["CTI|bareworld_shim name=%1", _extension];

    // 2. The seeded PRNG, against the engine rather than a model of it. ADR-0011
    // rejects an offline SQF runtime, so determinism, seed truncation and the
    // inclusive upper bound have nowhere else to be checked.
    private _prngFailures = call cti_fnc_prngSelfTest;
    if (_prngFailures isEqualTo []) then {
        diag_log "CTI|bareworld_prng_selftest=pass";
    } else {
        diag_log format ["CTI|FAIL class=assertion_failed bareworld_prng_selftest=%1", _prngFailures];
    };

    // 3. The synchronous round trip, in the daemon's real envelope. The shim's
    // own transport errors carry no echoed id, so a reply carrying this one
    // came from the daemon and can be matched to the request.
    private _quote = """";
    private _sent = "bareworld-1";
    private _raw = (_extension callExtension ["rpc_keepalive",
        ["{" + _quote + "id" + _quote + ":" + _quote + _sent + _quote
            + "," + _quote + "verb" + _quote + ":" + _quote + "ping" + _quote + "}"]]) # 0;
    diag_log format ["CTI|bareworld_sync_reply=%1", _raw];
    if ((_raw find (_quote + "id" + _quote + ":" + _quote + _sent + _quote)) < 0) then {
        diag_log "CTI|FAIL class=assertion_failed bareworld_daemon_did_not_echo_the_request_id";
    };

    // 4. The world the manifest describes is the world that got built.
    private _map = missionNamespace getVariable ["cti_map", createHashMap];
    private _objectives = _map getOrDefault ["objectives", []];
    private _bases = _map getOrDefault ["bases", []];
    diag_log format ["CTI|bareworld_map objectives=%1 bases=%2", count _objectives, count _bases];
    if (count _objectives isEqualTo 0 || { count _bases isEqualTo 0 }) exitWith {
        diag_log "CTI|FAIL class=assertion_failed bareworld_world_not_built";
    };

    // 5. The effect pump is turning. `polls` is the pump's own running account,
    // held in the mission namespace because a probe cannot read the server log
    // it is writing into. Three polls at a 2 s interval, so a minute is ample.
    private _deadline = diag_tickTime + 60;
    waitUntil {
        ((missionNamespace getVariable ["cti_effectDrain", createHashMap])
            getOrDefault ["polls", 0]) >= 3
            || { diag_tickTime > _deadline }
    };
    private _polls = (missionNamespace getVariable ["cti_effectDrain", createHashMap])
        getOrDefault ["polls", 0];
    diag_log format ["CTI|bareworld_effect_pump polls=%1", _polls];
    if (_polls < 3) exitWith {
        diag_log format ["CTI|FAIL class=timeout bareworld_effect_pump_stalled polls=%1", _polls];
    };

    // 6. The presence report went out and the daemon answered it. Ownership is
    // painted from the reply alone (#27), so an Objective carrying an owner is
    // proof the whole leg ran: report out, judgement back, marker repainted.
    _deadline = diag_tickTime + 60;
    waitUntil {
        count (missionNamespace getVariable ["cti_objectiveOwner", createHashMap])
            >= count _objectives
            || { diag_tickTime > _deadline }
    };
    private _owners = missionNamespace getVariable ["cti_objectiveOwner", createHashMap];
    diag_log format ["CTI|bareworld_owners count=%1 of=%2 values=%3",
        count _owners, count _objectives, values _owners];
    if (count _owners < count _objectives) exitWith {
        diag_log format ["CTI|FAIL class=timeout bareworld_presence_leg_incomplete owners=%1 objectives=%2",
            count _owners, count _objectives];
    };

    diag_log "CTI|bareworld_probe_done";
};
