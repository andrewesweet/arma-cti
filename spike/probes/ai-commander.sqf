// #16 in-world probe: WEST plays itself, and the world does what it is told.
//
// Run with `CTI_AI_SIDE=WEST just probe spike/probes/ai-commander.sqf 300`.
// Without the environment variable the daemon comes up under nobody's command
// and this probe correctly finds nothing — which is the point of the flag.
//
// The window is raised above the default 150 s for the reason the justfile
// allows: the subject is a Squad marching, and marching takes as long as it
// takes. What is *not* asserted is arrival. The WEST Base is 1,073 m from the
// nearest Objective it touches, and infantry under a SAD waypoint cover that in
// something over twelve minutes — so a probe that waited for a capture would be
// a thirteen-minute probe measuring the engine's walking speed. Ground actually
// changing hands is what `tests/unit/test_daemon_planning.py` drives end to end
// in milliseconds, and it is the daemon's rule rather than the world's.
//
// What no unit test can stand in for is the half that lives here: that Commands
// nobody sent reach the world at all, and that an Order the AI issued travels
// the same outbox and lands on the same waypoints as one a human issued
// (ADR-0012). The unit tier can prove the planner decided something; only this
// can prove a Squad started walking because of it.
[] spawn {
    private _extension = call cti_fnc_shimName;
    if (_extension isEqualTo "") exitWith {
        diag_log "CTI|FAIL class=infra_unavailable ai_probe_no_shim";
    };

    private _map = missionNamespace getVariable ["cti_map", createHashMap];
    private _objectives = _map getOrDefault ["objectives", []];

    private _westSquads = {
        private _found = createHashMap;
        {
            if (!isNull _y && { side _y isEqualTo west }) then { _found set [_x, _y] };
        } forEach (missionNamespace getVariable ["cti_squads", createHashMap]);
        _found
    };

    // Nobody sends a Command here, and that is the whole test. The only input
    // the daemon gets is the report loop the world was already running.
    private _deadline = diag_tickTime + 90;
    private _bought = createHashMap;
    waitUntil {
        _bought = call _westSquads;
        count _bought >= 2 || { diag_tickTime > _deadline }
    };
    if (count _bought < 2) exitWith {
        diag_log format ["CTI|FAIL class=timeout ai_probe_never_bought squads=%1 hint=%2",
            count _bought, "is CTI_AI_SIDE set?"];
    };
    diag_log format ["CTI|ai_probe_bought squads=%1 ids=%2 after=%3",
        count _bought, keys _bought, diag_tickTime];

    // Wait for an Order to reach the world. Reserve is what a Squad is spawned
    // under, so it does not count: what is being waited for is the Commander
    // having decided something and the effect having carried it.
    _deadline = diag_tickTime + 60;
    private _marching = createHashMap;
    waitUntil {
        _marching = createHashMap;
        {
            private _order = _y getVariable ["cti_order", createHashMap];
            if ((_order getOrDefault ["order", ""]) isEqualTo "capture") then {
                _marching set [_x, [_y, leader _y distance2D (_order get "position")]];
            };
        } forEach (call _westSquads);
        // Two rather than one: a single Squad marching says an Order arrived,
        // and two say the Commander is running a side rather than a Squad —
        // which is also the first thing that could send them both to the same
        // Objective. They are bought a report apart, so this costs seconds.
        count _marching >= 2 || { diag_tickTime > _deadline }
    };
    if (count _marching < 2) exitWith {
        diag_log format ["CTI|FAIL class=timeout ai_probe_no_capture_orders marching=%1",
            count _marching];
    };
    private _sentTo = [];
    {
        private _where = (_y # 0) getVariable ["cti_order", createHashMap] get "objective";
        if (_where in _sentTo) then {
            diag_log format ["CTI|FAIL class=assertion_failed ai_probe_two_squads_one_objective objective=%1",
                _where];
        };
        _sentTo pushBack _where;
    } forEach _marching;
    {
        _y params ["_group", "_range"];
        diag_log format ["CTI|ai_probe_marching squad=%1 objective=%2 range=%3 waypoints=%4",
            _x, (_group getVariable ["cti_order", createHashMap]) get "objective",
            _range, count waypoints _group];
    } forEach _marching;

    // Long enough for a Squad on foot to have covered ground worth measuring,
    // and short enough not to be waiting for it to arrive.
    private _next = diag_tickTime + 150;
    waitUntil { diag_tickTime >= _next };

    // The claim: an Order the AI issued is being carried out. Measured as ground
    // closed rather than ground reached, so what is asserted is the thing the
    // window actually contains.
    private _closed = 0;
    {
        _y params ["_group", "_was"];
        if (!isNull _group && { count units _group > 0 }) then {
            private _order = _group getVariable ["cti_order", createHashMap];
            private _now = leader _group distance2D (_order get "position");
            diag_log format ["CTI|ai_probe_progress squad=%1 objective=%2 was=%3 now=%4 closed=%5",
                _x, _order get "objective", _was, _now, _was - _now];
            if (_was - _now > 50) then { _closed = _closed + 1 };
        };
    } forEach _marching;
    if (_closed isEqualTo 0) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed ai_probe_nothing_moved marching=%1",
            count _marching];
    };

    // A Squad the world never spawned is not a Squad the world has lost
    // (`squads.Roster.reconcile`). Before that rule the Commander deleted every
    // Squad it bought in the window between judging the Purchase and the effect
    // pump carrying it out, counted itself short, and bought another — so the
    // symptom is a WEST force with no ceiling. The ceiling is the map's, because
    // that is what the scorer buys up to.
    private _west = call _westSquads;
    if (count _west > count _objectives) then {
        diag_log format ["CTI|FAIL class=assertion_failed ai_probe_runaway_force squads=%1 objectives=%2 ids=%3",
            count _west, count _objectives, keys _west];
    };

    // One side, and #16 says one side. A Commander playing for EAST as well
    // would be #17 arriving early and unasked.
    private _east = 0;
    {
        if (!isNull _y && { side _y isEqualTo east }) then { _east = _east + 1 };
    } forEach (missionNamespace getVariable ["cti_squads", createHashMap]);
    if (_east > 0) then {
        diag_log format ["CTI|FAIL class=assertion_failed ai_probe_commanded_both_sides east=%1", _east];
    };

    diag_log format ["CTI|ai_probe_state west=%1 east=%2 owners=%3 closed=%4 of=%5",
        count _west, _east,
        missionNamespace getVariable ["cti_objectiveOwner", createHashMap],
        _closed, count _marching];

    diag_log "CTI|ai_probe_done";
};
