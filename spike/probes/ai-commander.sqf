// probe: ai-commander
// issues: 16, 32, 43
// window: 300
// env: CTI_AI_SIDE=WEST
//
// #16 in-world probe: WEST plays itself, and the world does what it is told.
//
// `just regress ai-commander` reads the block above. By hand:
// `CTI_AI_SIDE=WEST just probe spike/probes/ai-commander.sqf 300`.
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
//
// #43 converted this probe's one fixed settle to an event-driven wait. It used
// to sleep 150 s and then ask whether anything had closed ground; it now asks
// continuously and stops the moment the answer is yes, with the same 150 s as
// the deadline it was always a proxy for. The exit fires on the claim being
// true, never on the world looking done: a run in which nothing moves waits the
// full 150 s and fails `assertion_failed` exactly as before. The two absence
// claims that shared that settle — a force with no ceiling, and a Commander
// playing EAST — became watchers rather than a single sample at the end; see
// docs/regression-tier.md, "Waiting for the subject", for why that is the only
// honest way to shorten a window an absence claim was sitting in.
//
// #32 added one claim to the same window rather than a probe of its own: the
// Order's ground field is now `place` end to end (ADR-0020), so the standing
// Order the world recorded is checked for carrying one. A rename that stopped
// at the daemon leaves it empty here, with the Squad marching on ground nobody
// named — which no unit test can see, because both halves of it pass alone.
[] spawn {
    private _extension = call cti_fnc_shimName;
    if (_extension isEqualTo "") exitWith {
        diag_log "CTI|FAIL class=infra_unavailable ai_probe_no_shim";
    };

    private _map = missionNamespace getVariable ["cti_map", createHashMap];
    private _objectives = _map getOrDefault ["objectives", []];

    // Four probes counted a side's Squads by hand (#86); this is the prelude's
    // copy, bound to the one side #16 is about.
    private _westSquads = { ["WEST"] call cti_probe_fnc_squadsOf };

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
        private _where = (_y # 0) getVariable ["cti_order", createHashMap]
            getOrDefault ["place", ""];
        // #32 renamed the Order's ground field `objective` -> `place` through
        // the whole wire. An empty one here is that rename half-done: the
        // effect crossed the outbox without the field the world reads, so the
        // Squad is marching on ground nobody named.
        if (_where isEqualTo "") then {
            diag_log "CTI|FAIL class=assertion_failed ai_probe_order_without_place";
        };
        if (_where in _sentTo) then {
            diag_log format ["CTI|FAIL class=assertion_failed ai_probe_two_squads_one_place place=%1",
                _where];
        };
        _sentTo pushBack _where;
    } forEach _marching;
    {
        _y params ["_group", "_range"];
        diag_log format ["CTI|ai_probe_marching squad=%1 place=%2 range=%3 waypoints=%4",
            _x, (_group getVariable ["cti_order", createHashMap]) getOrDefault ["place", ""],
            _range, count waypoints _group];
    } forEach _marching;

    // The two claims that used to be read once, when the fixed settle expired.
    // Both are claims that something is *absent*, and the strength of an absence
    // claim is the time it was observed for — so a probe that exits early cannot
    // simply keep them as end-of-window samples. They are evaluated on every
    // pass of the wait below instead, which fails the instant either is violated
    // rather than only if the violation survived to the end. Over the same
    // window that is strictly stronger; over a shorter one it is weaker in the
    // way every absence claim is, and both rules are unit-tested besides
    // (`squads.Roster.reconcile`, `tests/unit/test_daemon_planning.py`).
    private _runaway = false;
    private _bothSides = false;
    private _east = 0;
    private _watch = {
        // A Squad the world never spawned is not a Squad the world has lost
        // (`squads.Roster.reconcile`). Before that rule the Commander deleted
        // every Squad it bought in the window between judging the Purchase and
        // the effect pump carrying it out, counted itself short, and bought
        // another — so the symptom is a WEST force with no ceiling. The ceiling
        // is the map's, because that is what the scorer buys up to.
        private _fielded = call _westSquads;
        if (count _fielded > count _objectives && { !_runaway }) then {
            _runaway = true;
            diag_log format ["CTI|FAIL class=assertion_failed ai_probe_runaway_force squads=%1 objectives=%2 ids=%3",
                count _fielded, count _objectives, keys _fielded];
        };
        // One side, and #16 says one side. A Commander playing for EAST as well
        // would be #17 arriving early and unasked.
        _east = 0;
        {
            if (!isNull _y && { side _y isEqualTo east }) then { _east = _east + 1 };
        } forEach (missionNamespace getVariable ["cti_squads", createHashMap]);
        if (_east > 0 && { !_bothSides }) then {
            _bothSides = true;
            diag_log format ["CTI|FAIL class=assertion_failed ai_probe_commanded_both_sides east=%1", _east];
        };
    };

    // The claim: an Order the AI issued is being carried out. Measured as ground
    // closed rather than ground reached, so what is asserted is the thing the
    // window actually contains — and read continuously, so the probe ends when
    // the claim becomes true instead of when a clock says it probably has. 150 s
    // is the deadline, unchanged from the settle it replaces: it is how long a
    // Squad on foot may take to cover ground worth measuring, and a run that
    // never covers it fails at the same moment, in the same class, as before.
    private _waitedFrom = diag_tickTime;
    _deadline = diag_tickTime + 150;
    private _closed = 0;
    waitUntil {
        // `_watch` only watches (#84): it used to hand back the roster it had
        // just judged, so its caller could not tell which of the two jobs it was
        // reading. The roster is read where it is wanted, below.
        call _watch;
        _closed = 0;
        {
            _y params ["_group", "_was"];
            if (!isNull _group && { count units _group > 0 }) then {
                private _order = _group getVariable ["cti_order", createHashMap];
                if ((_was - (leader _group distance2D (_order get "position"))) > 50) then {
                    _closed = _closed + 1;
                };
            };
        } forEach _marching;
        _closed > 0 || { diag_tickTime > _deadline }
    };

    _closed = 0;
    {
        _y params ["_group", "_was"];
        if (!isNull _group && { count units _group > 0 }) then {
            private _order = _group getVariable ["cti_order", createHashMap];
            private _now = leader _group distance2D (_order get "position");
            diag_log format ["CTI|ai_probe_progress squad=%1 place=%2 was=%3 now=%4 closed=%5",
                _x, _order getOrDefault ["place", ""], _was, _now, _was - _now];
            if (_was - _now > 50) then { _closed = _closed + 1 };
        };
    } forEach _marching;
    private _waited = diag_tickTime - _waitedFrom;
    if (_closed isEqualTo 0) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed ai_probe_nothing_moved marching=%1 waited=%2",
            count _marching, _waited];
    };

    diag_log format ["CTI|ai_probe_state west=%1 east=%2 owners=%3 closed=%4 of=%5 waited=%6",
        count (call _westSquads), _east,
        missionNamespace getVariable ["cti_objectiveOwner", createHashMap],
        _closed, count _marching, _waited];

    diag_log "CTI|ai_probe_done";
};
