// probe: two-commanders
// issues: 17, 46
// window: 600
// env: CTI_HOLD_HC=1 CTI_AI_SIDE=WEST,EAST CTI_AI_SEED=1,4
//
// #17 in-world probe: both sides under an AI Commander, nobody watching.
//
// `just regress two-commanders` reads the block above. By hand:
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
//
// **This probe keeps its 180 s soak, and #46 decided so on purpose.** Every
// other fixed settle in the corpus was a proxy for a condition the world states,
// and was converted to a wait on that condition. This one is not a proxy: it is
// the window the number #17 asks for is measured in — the largest single drain
// the push path has been seen to carry with two Commanders on it — and an
// extremum shrinks with its window. Converting it to "exit when a side has
// closed ground" would end the probe at about forty seconds and report the
// maximum drain of forty seconds as though it were the maximum drain of a
// hundred and eighty. That is a conversion that weakens the evidence while
// looking like a speed-up, which is worse than the settle. So the 180 s is an
// explicit floor for the measurement, and the soak earns it back by watching the
// claims it used to sample once at the end.
[] spawn {
    private _extension = call cti_fnc_shimName;
    if (_extension isEqualTo "") exitWith {
        diag_log "CTI|FAIL class=infra_unavailable two_probe_no_shim";
    };

    private _map = missionNamespace getVariable ["cti_map", createHashMap];
    private _objectives = _map getOrDefault ["objectives", []];
    // Keyed by the side's name, which is also the name the daemon and the
    // manifest use, so nothing here needs a translation table. Every Squad the
    // world holds for one side, by Squad id, is `cti_probe_fnc_squadsOf` — four
    // probes had a copy of it (#86).
    private _sides = ["WEST", "EAST"];

    // ------------------------------------------------ topology
    // The MVP test topology is a dedicated server plus a headless client, and
    // #17 asks for the unattended run on it. A run without the headless client
    // is a different run, so it is refused rather than reported as a pass. Three
    // probes had this loop verbatim (#86); the count comes back and each still
    // refuses under its own name.
    private _headless = [120] call cti_probe_fnc_headlessClients;
    if (_headless isEqualTo 0) exitWith {
        diag_log format ["CTI|FAIL class=infra_unavailable two_probe_no_headless_client users=%1 hint=%2",
            count allUsers, "is CTI_HOLD_HC=1 set?"];
    };
    diag_log format ["CTI|two_probe_topology headless=%1 users=%2 at=%3",
        _headless, count allUsers, diag_tickTime];

    // ------------------------------------------------ both sides field a force
    // Nobody sends a Command here, and that is the whole test. The only input
    // either Commander gets is the report loop the world was already running.
    private _deadline = diag_tickTime + 120;
    private _bought = createHashMap;
    waitUntil {
        { _bought set [_x, [_x] call cti_probe_fnc_squadsOf] } forEach _sides;
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
                    _order getOrDefault ["place", ""]]];
            };
        } forEach ([_name] call cti_probe_fnc_squadsOf);
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
    //
    // #46 kept this soak and converted the corpus's other settles. It is the
    // extremum-bearing kind: the number below it exists to produce is the
    // largest single drain the push path has been seen to carry with two
    // Commanders on it (#17), and an extremum shrinks with the window it was
    // observed in. Exiting at the first Squad to close ground — the conversion
    // `ai-commander` took — would leave that number measured over about forty
    // seconds instead of a hundred and eighty, and quietly report a smaller
    // maximum as though it were the same evidence. So the 180 s stays as an
    // explicit floor for the measurement, stated here because the honesty rule
    // requires a floor to be stated.
    //
    // What the soak is *not* allowed to be is dead time. The two claims it used
    // to read once at the end — a force with no ceiling, and the pump still
    // turning — are evaluated on every pass of it instead, so they fail at the
    // instant they are violated rather than only if the violation happened to
    // survive to t+180. Over the same window that is strictly stronger, which is
    // the shape #43 gave `ai-commander`'s absence claims; here it costs nothing
    // at all, because the window is not moving.
    private _pollsBefore = (missionNamespace getVariable ["cti_effectDrain", createHashMap])
        getOrDefault ["polls", 0];
    private _soak = 180 max (missionNamespace getVariable ["CTI_PROBE_SOAK", 0]);
    diag_log format ["CTI|two_probe_soaking secs=%1 floor=%2 for=%3",
        _soak, 180, "the push-path extremum #17 asks to be measured"];
    private _runaway = false;
    private _pollsSeen = _pollsBefore;
    private _next = diag_tickTime + _soak;
    private _nextWatch = 0;
    waitUntil {
        if (diag_tickTime > _nextWatch) then {
            _nextWatch = diag_tickTime + 2;
            // Runaway spending has one shape the world can see: a force with no
            // ceiling. The scorer buys up to one Squad per Objective the map
            // has, and a Commander spending the other side's Funds — or its own
            // without counting — shows up here first. Said once per side, the
            // first time it is true.
            {
                private _fielded = [_x] call cti_probe_fnc_squadsOf;
                if (count _fielded > count _objectives && { !_runaway }) then {
                    _runaway = true;
                    diag_log format ["CTI|FAIL class=assertion_failed two_probe_runaway_force side=%1 squads=%2 objectives=%3",
                        _x, count _fielded, count _objectives];
                };
            } forEach _sides;
            _pollsSeen = (missionNamespace getVariable ["cti_effectDrain", createHashMap])
                getOrDefault ["polls", 0];
        };
        diag_tickTime >= _next
    };
    // Nothing deadlocked while nobody was sending it anything: the pump is still
    // polling a daemon that is still answering. A stopped world would otherwise
    // read as a quiet one.
    if (_pollsSeen <= _pollsBefore) then {
        diag_log format ["CTI|FAIL class=assertion_failed two_probe_pump_stopped before=%1 after=%2",
            _pollsBefore, _pollsSeen];
    };

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
                diag_log format ["CTI|two_probe_progress side=%1 squad=%2 place=%3 was=%4 now=%5 closed=%6",
                    _name, _x, _order getOrDefault ["place", ""], _was, _now, _was - _now];
                if (_was - _now > 50) then { _closed = _closed + 1 };
            };
        } forEach (_marching get _name);
        if (_closed isEqualTo 0) then {
            diag_log format ["CTI|FAIL class=assertion_failed two_probe_side_never_moved side=%1 marching=%2",
                _name, count (_marching get _name)];
        };
    } forEach _sides;

    // The runaway-force claim is not re-read here: it is watched throughout the
    // soak above, which fails at the first moment a side is over its ceiling
    // rather than only if it was still over it at the end. Read once more at the
    // end it would be weaker, not stronger — a force that ran away and was
    // reconciled back inside the window would pass.
    {
        diag_log format ["CTI|two_probe_ceiling side=%1 squads=%2 objectives=%3 runaway_seen=%4",
            _x, count ([_x] call cti_probe_fnc_squadsOf), count _objectives, _runaway];
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

    // Whether the pump was still turning is asserted above, off the count the
    // watch loop carried out of the soak.
    private _pollsAfter = _drain getOrDefault ["polls", 0];

    // ------------------------------------------------ what the island looked like
    {
        diag_log format ["CTI|two_probe_state side=%1 squads=%2", _x, count ([_x] call cti_probe_fnc_squadsOf)];
    } forEach _sides;
    diag_log format ["CTI|two_probe_owners owners=%1 polls=%2",
        missionNamespace getVariable ["cti_objectiveOwner", createHashMap], _pollsAfter];

    diag_log "CTI|two_probe_done";
};
