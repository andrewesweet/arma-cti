// probe: two-commanders
// issues: 17
// window: 600
//
// #17 in-world probe: both sides under an AI Commander, nobody watching.
//
// Run with:
//   CTI_HOLD_HC=1 CTI_AI_SIDE=WEST,EAST CTI_AI_SEED=1,4 \
//       just probe spike/probes/two-commanders.sqf 600
//
// A longer unattended soak, for evidence of what the Campaign does rather than
// only that it runs:
//   CTI_PROBE_SOAK=600 CTI_HOLD_HC=1 CTI_AI_SIDE=WEST,EAST CTI_AI_SEED=1,4 \
//       just probe spike/probes/two-commanders.sqf 900
//
// Three environment flags, and the probe fails loudly without each rather than
// quietly measuring nothing: `CTI_AI_SIDE` names the sides under command,
// `CTI_AI_SEED` the pair of seeds that Campaign replays from, and
// `CTI_HOLD_HC=1` brings up the headless client this ticket's topology names.
//
// The window is above the default 150 s for the reason the justfile allows: the
// subject is two sides marching on each other, and marching takes as long as it
// takes. What is *not* asserted is arrival — the Bases are over a kilometre from
// the nearest Objective they touch, so a probe waiting for a capture would be
// measuring the engine's walking speed. Ground *closed* is what is asserted, as
// in #16, and ownership changing hands is unit-tested end to end in
// milliseconds.
//
// What no unit test can stand in for is everything here: that two Commanders
// nobody is watching both reach the world, that the effects of both travel one
// outbox without either starving, that the push path has room for two at once,
// and that neither side sits still.
[] spawn {
    private _extension = call cti_fnc_shimName;
    if (_extension isEqualTo "") exitWith {
        diag_log "CTI|FAIL class=infra_unavailable two_probe_no_shim";
    };

    private _map = missionNamespace getVariable ["cti_map", createHashMap];
    private _objectives = _map getOrDefault ["objectives", []];
    // Keyed by the side's name, which is also the name the daemon and the
    // manifest use, so nothing here needs a translation table.
    private _sideOf = createHashMapFromArray [["WEST", west], ["EAST", east]];
    private _sides = ["WEST", "EAST"];

    // Every Squad the world holds for one side, by Squad id.
    private _squadsOf = {
        params ["_name"];
        private _side = _sideOf get _name;
        private _found = createHashMap;
        {
            if (!isNull _y && { side _y isEqualTo _side }) then { _found set [_x, _y] };
        } forEach (missionNamespace getVariable ["cti_squads", createHashMap]);
        _found
    };

    // ------------------------------------------------ topology
    // The MVP test topology is a dedicated server plus a headless client, and
    // #17 asks for the unattended run on it. A run without the headless client
    // is a different run, so it is refused rather than reported as a pass.
    private _deadline = diag_tickTime + 120;
    private _headless = 0;
    waitUntil {
        _headless = 0;
        {
            private _info = getUserInfo _x;
            if (count _info > 7 && { _info # 7 }) then { _headless = _headless + 1 };
        } forEach allUsers;
        _headless > 0 || { diag_tickTime > _deadline }
    };
    if (_headless isEqualTo 0) exitWith {
        diag_log format ["CTI|FAIL class=infra_unavailable two_probe_no_headless_client users=%1 hint=%2",
            count allUsers, "is CTI_HOLD_HC=1 set?"];
    };
    diag_log format ["CTI|two_probe_topology headless=%1 users=%2 at=%3",
        _headless, count allUsers, diag_tickTime];

    // ------------------------------------------------ both sides field a force
    // Nobody sends a Command here, and that is the whole test. The only input
    // either Commander gets is the report loop the world was already running.
    _deadline = diag_tickTime + 120;
    private _bought = createHashMap;
    waitUntil {
        { _bought set [_x, [_x] call _squadsOf] } forEach _sides;
        (count (_bought get "WEST") >= 2 && { count (_bought get "EAST") >= 2 })
            || { diag_tickTime > _deadline }
    };
    private _short = [];
    {
        if (count (_bought get _x) < 2) then { _short pushBack _x };
    } forEach _sides;
    if (count _short > 0) exitWith {
        diag_log format ["CTI|FAIL class=timeout two_probe_side_fielded_nothing sides=%1 west=%2 east=%3 hint=%4",
            _short, count (_bought get "WEST"), count (_bought get "EAST"),
            "is CTI_AI_SIDE=WEST,EAST set?"];
    };
    {
        diag_log format ["CTI|two_probe_bought side=%1 squads=%2 ids=%3 at=%4",
            _x, count (_bought get _x), keys (_bought get _x), diag_tickTime];
    } forEach _sides;

    // ------------------------------------------------ both sides are ordered out
    // Reserve is what a Squad is spawned under, so it does not count: what is
    // waited for is each Commander having decided something and the effect
    // having carried it. Two per side rather than one, because one says an
    // Order arrived and two say a side is being played.
    private _marchingOf = {
        params ["_name"];
        private _found = createHashMap;
        {
            private _order = _y getVariable ["cti_order", createHashMap];
            if ((_order getOrDefault ["order", ""]) isEqualTo "capture") then {
                _found set [_x, [_y, leader _y distance2D (_order get "position"),
                    _order get "objective"]];
            };
        } forEach ([_name] call _squadsOf);
        _found
    };

    _deadline = diag_tickTime + 90;
    private _marching = createHashMap;
    waitUntil {
        { _marching set [_x, [_x] call _marchingOf] } forEach _sides;
        (count (_marching get "WEST") >= 2 && { count (_marching get "EAST") >= 2 })
            || { diag_tickTime > _deadline }
    };
    _short = [];
    {
        if (count (_marching get _x) < 2) then { _short pushBack _x };
    } forEach _sides;
    if (count _short > 0) exitWith {
        diag_log format ["CTI|FAIL class=timeout two_probe_side_never_marched sides=%1 west=%2 east=%3",
            _short, count (_marching get "WEST"), count (_marching get "EAST")];
    };

    // One Squad per Objective, per side. Two Squads of one side sent to the same
    // ground take it twice over and leave the rest of the island alone — and at
    // two sides it is also the first thing a Commander reading the *other's*
    // roster would get wrong.
    {
        private _name = _x;
        private _sentTo = [];
        {
            private _where = _y # 2;
            if (_where in _sentTo) then {
                diag_log format ["CTI|FAIL class=assertion_failed two_probe_two_squads_one_objective side=%1 objective=%2",
                    _name, _where];
            };
            _sentTo pushBack _where;
        } forEach (_marching get _name);
        diag_log format ["CTI|two_probe_marching side=%1 squads=%2 objectives=%3",
            _name, count (_marching get _name), _sentTo];
    } forEach _sides;

    // ------------------------------------------------ leave it alone
    // Long enough for infantry to have covered ground worth measuring, and
    // short enough not to be waiting for arrival. The unattended part: nothing
    // below sends anything, it only reads.
    //
    // CTI_PROBE_SOAK raises it, and only that: every assertion below holds at
    // the 180 s this probe is sized to, and the longer window buys evidence of
    // what a Campaign left alone *does* — ground changing hands takes about
    // nine minutes of marching — rather than making anything pass that did not.
    private _pollsBefore = (missionNamespace getVariable ["cti_effectDrain", createHashMap])
        getOrDefault ["polls", 0];
    private _soak = 180 max (missionNamespace getVariable ["CTI_PROBE_SOAK", 0]);
    diag_log format ["CTI|two_probe_soaking secs=%1", _soak];
    private _next = diag_tickTime + _soak;
    waitUntil { diag_tickTime >= _next };

    // ------------------------------------------------ neither side is stuck
    // Ground closed rather than ground reached, per side. A side that has not
    // closed a metre in three minutes is either deadlocked or in a stalemate,
    // and from outside those look the same — which is why the assertion is
    // "somebody moved" rather than "somebody arrived".
    {
        private _name = _x;
        private _closed = 0;
        {
            _y params ["_group", "_was"];
            if (!isNull _group && { count units _group > 0 }) then {
                private _order = _group getVariable ["cti_order", createHashMap];
                private _now = leader _group distance2D (_order get "position");
                diag_log format ["CTI|two_probe_progress side=%1 squad=%2 objective=%3 was=%4 now=%5 closed=%6",
                    _name, _x, _order get "objective", _was, _now, _was - _now];
                if (_was - _now > 50) then { _closed = _closed + 1 };
            };
        } forEach (_marching get _name);
        if (_closed isEqualTo 0) then {
            diag_log format ["CTI|FAIL class=assertion_failed two_probe_side_never_moved side=%1 marching=%2",
                _name, count (_marching get _name)];
        };
    } forEach _sides;

    // Runaway spending has one shape the world can see: a force with no
    // ceiling. The scorer buys up to one Squad per Objective the map has, and a
    // Commander spending the other side's Funds — or its own without counting —
    // shows up here first.
    {
        private _fielded = [_x] call _squadsOf;
        if (count _fielded > count _objectives) then {
            diag_log format ["CTI|FAIL class=assertion_failed two_probe_runaway_force side=%1 squads=%2 objectives=%3",
                _x, count _fielded, count _objectives];
        };
    } forEach _sides;

    // ------------------------------------------------ the push path, at two sides
    // The number #17 asks to be measured and recorded: the largest single drain
    // against the engine's hundred-per-frame ceiling (ADR-0004). Failing *at*
    // the cap rather than past it, because a drain that reached it has already
    // been carrying work across frames.
    private _drain = missionNamespace getVariable ["cti_effectDrain", createHashMap];
    private _biggest = _drain getOrDefault ["max", 0];
    diag_log format ["CTI|two_probe_push_path polls=%1 drains=%2 applied=%3 max=%4 maxFrames=%5 deferred=%6 headroom=%7",
        _drain getOrDefault ["polls", 0], _drain getOrDefault ["drains", 0],
        _drain getOrDefault ["applied", 0], _biggest, _drain getOrDefault ["maxFrames", 0],
        _drain getOrDefault ["deferred", 0],
        [100 / (_biggest max 1), "unmeasured"] select (_biggest isEqualTo 0)];
    if (_biggest >= 100) then {
        diag_log format ["CTI|FAIL class=assertion_failed two_probe_push_path_at_cap max=%1 cap=%2",
            _biggest, 100];
    };

    // Nothing has deadlocked: the pump is still polling a daemon that is still
    // answering. A stopped world would otherwise read as a quiet one.
    private _pollsAfter = _drain getOrDefault ["polls", 0];
    if (_pollsAfter <= _pollsBefore) then {
        diag_log format ["CTI|FAIL class=assertion_failed two_probe_pump_stopped before=%1 after=%2",
            _pollsBefore, _pollsAfter];
    };

    // ------------------------------------------------ what the island looked like
    {
        diag_log format ["CTI|two_probe_state side=%1 squads=%2", _x, count ([_x] call _squadsOf)];
    } forEach _sides;
    diag_log format ["CTI|two_probe_owners owners=%1 polls=%2",
        missionNamespace getVariable ["cti_objectiveOwner", createHashMap], _pollsAfter];

    diag_log "CTI|two_probe_done";
};
