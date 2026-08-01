// probe: time-acceleration
// issues: 40
// window: 240
//
// #40 in-world probe: what, if anything, accelerates simulation on the tier's
// own topology — a Linux dedicated server on 2402-2406 with one headless client
// and no human client anywhere.
//
// `just regress time-acceleration`, or by hand
// `just probe spike/probes/time-acceleration.sqf 240`.
//
// The wiki says `setAccTime` is "disabled in multiplayer"
// (docs/reference/arma-wiki/commands/setAccTime.wiki, `|mp=`), and #35 read that
// as closing the question. It does not, quite: the sentence has been in the page
// since Operation Flashpoint and says nothing about *why*. If the restriction is
// about fairness between human clients, a server whose only client is a script
// might not be covered by it. That is a guess either way, so this probe asks the
// engine instead.
//
// Three measurements, each against `diag_tickTime` — real seconds since game
// start, unaffected by anything this probe does:
//
//   1. `setAccTime` on the server: does `accTime` read back, and does `time`
//      advance faster than the wall?
//   2. Does *simulation* accelerate? A rifleman walking a fixed heading covers
//      metres per real second; four times the acceleration should be four times
//      the ground. This is the measurement that matters, because `time` is only
//      a clock and what a test wants shortened is the world.
//   3. `setTimeMultiplier 60`: confirms in-world what #35 read — the in-game
//      clock (`dayTime`) moves and `time` does not, so every rule we write in
//      `time` runs at wall speed regardless.
//
// The window is the subject added up: ~20 s for the world to settle, two 15 s
// clock samples, two 30 s walking samples, and the bring-up. Nothing here waits
// on the daemon, an Order, or another node.
//
// The probe asserts the *inconsistencies* rather than the answer: a run where
// `accTime` reads back 4 while the world stays at 1x is a different finding from
// one where the command is simply ignored, and both are findings. It goes red
// only if the engine contradicts itself or the measurement never completes, so
// the numbers on the `CTI|acc_` lines are the deliverable.
[] spawn {
    // Wall-clock rate of an arbitrary sampler, in units per real second.
    private _rate = {
        params ["_sampler", "_seconds"];
        private _t0 = diag_tickTime;
        private _v0 = call _sampler;
        private _until = _t0 + _seconds;
        waitUntil { diag_tickTime >= _until };
        private _elapsed = diag_tickTime - _t0;
        if (_elapsed <= 0) exitWith { -1 };
        ((call _sampler) - _v0) / _elapsed
    };

    private _missionTime = { time };

    // Let the world finish building before measuring anything about it.
    private _settled = diag_tickTime + 20;
    waitUntil { diag_tickTime >= _settled };

    diag_log format ["CTI|acc_start accTime=%1 timeMultiplier=%2 isServer=%3 isMP=%4 players=%5",
        accTime, timeMultiplier, isServer, isMultiplayer, count allPlayers];

    // ---------------------------------------------------------------- 1: clock
    private _clockBase = [_missionTime, 15] call _rate;
    diag_log format ["CTI|acc_clock_baseline accTime=%1 time_per_wall_second=%2", accTime, _clockBase];

    setAccTime 4;
    private _readBack = accTime;
    private _clockFast = [_missionTime, 15] call _rate;
    diag_log format ["CTI|acc_clock_accelerated requested=4 accTime_readback=%1 time_per_wall_second=%2 ratio=%3",
        _readBack, _clockFast, (if (_clockBase > 0) then { _clockFast / _clockBase } else { -1 })];

    // ------------------------------------------------------------ 2: the world
    // A rifleman walking is the cheapest honest proxy for simulation rate: it is
    // pathfinding, animation and AI cadence all at once, and it is the thing a
    // probe actually waits on. CARELESS + FULL so the pace is the engine's, not
    // a reaction to something in the terrain.
    setAccTime 1;
    private _map = missionNamespace getVariable ["cti_map", createHashMap];
    private _objectives = _map getOrDefault ["objectives", []];
    if (count _objectives isEqualTo 0) exitWith {
        diag_log "CTI|FAIL class=infra_unavailable acc_no_map";
        diag_log "CTI|acc_probe_done";
    };
    private _origin = (_objectives # 0) get "position";
    _origin params ["_east", "_north"];
    // Walk at another authored Objective rather than a bearing off the unit's
    // facing: #28's lesson is that a guessed heading lands in a hangar or the
    // sea, and authored ground is ground. The furthest one, so neither sample
    // measures an arrival.
    private _target = _origin;
    {
        private _candidate = _x get "position";
        if ((_candidate distance2D _origin) > (_target distance2D _origin)) then {
            _target = _candidate;
        };
    } forEach _objectives;
    if ((_target distance2D _origin) < 500) exitWith {
        diag_log "CTI|FAIL class=infra_unavailable acc_no_walkable_target";
        diag_log "CTI|acc_probe_done";
    };

    private _group = createGroup west;
    private _walker = _group createUnit ["B_Soldier_F", [_east, _north, 0], [], 0, "NONE"];
    _group setBehaviour "CARELESS";
    _group setSpeedMode "FULL";
    _group setCombatMode "BLUE";
    _walker doMove _target;
    private _walked = diag_tickTime + 5;
    waitUntil { diag_tickTime >= _walked };

    private _walkRate = {
        params ["_seconds"];
        private _from = getPosATL _walker;
        private _t0 = diag_tickTime;
        private _until = _t0 + _seconds;
        waitUntil { diag_tickTime >= _until };
        private _elapsed = diag_tickTime - _t0;
        (_from distance2D (getPosATL _walker)) / _elapsed
    };

    private _metresBase = [30] call _walkRate;
    diag_log format ["CTI|acc_walk_baseline accTime=%1 metres_per_wall_second=%2 alive=%3",
        accTime, _metresBase, alive _walker];

    setAccTime 4;
    private _metresFast = [30] call _walkRate;
    diag_log format ["CTI|acc_walk_accelerated accTime_readback=%1 metres_per_wall_second=%2 ratio=%3",
        accTime, _metresFast, (if (_metresBase > 0) then { _metresFast / _metresBase } else { -1 })];
    setAccTime 1;

    // ------------------------------------------------- 3: the other clock (#35)
    private _dayBase = [{ dayTime }, 10] call _rate;
    setTimeMultiplier 60;
    private _dayFast = [{ dayTime }, 10] call _rate;
    private _timeUnderMultiplier = [_missionTime, 10] call _rate;
    setTimeMultiplier 1;
    diag_log format ["CTI|acc_timeMultiplier dayTime_hours_per_wall_second base=%1 at60=%2 ratio=%3 time_per_wall_second=%4 (baseline %5)",
        _dayBase, _dayFast, (if (_dayBase > 0) then { _dayFast / _dayBase } else { -1 }),
        _timeUnderMultiplier, _clockBase];

    deleteVehicle _walker;
    deleteGroup _group;

    // The probe is red only when the engine contradicts itself: a clock that
    // reads accelerated while the ground it simulates does not is the one result
    // no reading of the wiki predicts, and it needs a human before anyone builds
    // on it.
    private _clockMoved = _clockBase > 0 && { _clockFast / _clockBase > 1.5 };
    private _worldMoved = _metresBase > 0 && { _metresFast / _metresBase > 1.5 };
    if !(_clockMoved isEqualTo _worldMoved) then {
        diag_log format ["CTI|FAIL class=oracle_disagreement acc_clock_and_world_disagree clock=%1 world=%2",
            _clockMoved, _worldMoved];
    };

    diag_log "CTI|acc_probe_done";
};
