// probe: contact-decay
// issues: 28
// window: 300
//
// #28 in-world probe: a Contact outlives the engine forgetting the men it was made of.
//
// Run with `just probe spike/probes/contact-decay.sqf 300`.
//
// The hold window is raised from the default 150 s because the subject is the
// engine's 120 s knowledge decay, and no window shorter than that can contain
// it. Sized to what is being measured rather than extended until something
// passes — see the note on the `probe` recipe in the justfile. If this ever
// fails at 300 s, the answer is not 450.
//
// What is under test is the half that lives in the world. The daemon's rule —
// keep a Contact nobody has looked at, and let its age grow — is unit-tested in
// `tests/unit/test_contacts.py`. What no unit test can assert is the premise
// that rule rests on: that the engine really does forget, and that when it has,
// our sampler reports the place as neither seen nor observed, so the removal
// rule stays silent and the daemon's memory is what carries the Contact.
[] spawn {
    private _extension = call cti_fnc_shimName;
    if (_extension isEqualTo "") exitWith {
        diag_log "CTI|FAIL class=infra_unavailable decay_probe_no_shim";
    };

    private _sample = {
        (call cti_fnc_contactSample) getOrDefault ["WEST", createHashMap]
    };

    private _next = diag_tickTime + 20;
    waitUntil { diag_tickTime >= _next };

    // Two Squads rather than one, for the eyes. Acquisition is a natural process
    // with real spread — a single Squad missed six men at 140 m for over 90 s on
    // one run and found them in seconds on the next — and the subject here is
    // what happens *after* acquisition, so the setup is made reliable rather
    // than waited out.
    private _wanted = 2;
    for "_i" from 1 to _wanted do {
        [createHashMapFromArray [
            ["id", format ["decay-probe-buy-%1", _i]],
            ["verb", "command"],
            ["payload", createHashMapFromArray [
                ["command", "purchase"],
                ["side", "WEST"],
                ["args", createHashMapFromArray [["squad_type", "rifle"]]]
            ]]
        ]] call {
            params ["_envelope"];
            ((call cti_fnc_shimName) callExtension ["rpc_keepalive", [toJSON _envelope]]) # 0
        };
    };

    private _deadline = diag_tickTime + 60;
    waitUntil {
        count (missionNamespace getVariable ["cti_squads", createHashMap]) >= _wanted
            || { diag_tickTime > _deadline }
    };
    private _squads = missionNamespace getVariable ["cti_squads", createHashMap];
    if (count _squads < _wanted) exitWith {
        diag_log format ["CTI|FAIL class=timeout decay_probe_no_squad held=%1", count _squads];
    };
    private _group = (values _squads) # 0;

    // Enemy for them to see, at the Base they are standing on, so the Contact
    // lands on a named place. Told not to shoot: a firefight would remove the
    // men by killing them, and what is under test is the engine forgetting them
    // while they are still standing there.
    private _east = createGroup [east, true];
    private _muster = (leader _group) getRelPos [100, 0];
    for "_i" from 1 to 6 do {
        _east createUnit ["O_Soldier_F", _muster, [], 15, "FORM"];
    };
    // The observers are woken but not silenced, and the distinction cost two
    // runs. A Squad sitting in Reserve is at the engine's default behaviour with
    // its weapons down, and never acquired six men at 90 m across 120 s —
    // `knows_east=0` for the whole window. Telling it not to shoot does not help
    // either. AWARE is the posture a Squad under a Capture or Defend Order is
    // actually in, so putting the observers in it is making the probe resemble
    // the game rather than handing the knowledge model its answer.
    { _x setBehaviour "AWARE" } forEach values _squads;
    // The targets are the ones held still: they may not fire, and they may not
    // die, because what is under test is WEST forgetting men who are still
    // standing there.
    _east setCombatMode "BLUE";
    { _x allowDamage false } forEach units _east;

    diag_log format ["CTI|decay_probe_planted units=%1 at=%2 leader_at=%3 range=%4 leader_alive=%5",
        count units _east, mapGridPosition _muster, mapGridPosition (leader _group),
        (leader _group) distance2D _muster, alive (leader _group)];

    // Walk the enemy round the compass until somebody sees them. A bearing off
    // the leader's facing is a guess about line of sight, and on an airfield it
    // lands behind a hangar often enough to matter: three runs sat at
    // `knows_east=0` for the whole window with the men standing 90 m away and
    // nothing between them but a building. Re-placing rather than waiting longer
    // is the fix, because the wait was never the problem. Nothing here tells the
    // knowledge model anything — it arranges for there to be something to see,
    // and the engine still decides whether it sees it.
    private _bearings = [0, 45, 90, 135, 180, 225, 270, 315];
    private _attempt = 0;
    private _nextMove = 0;

    _deadline = diag_tickTime + 150;
    private _report = createHashMap;
    private _nextLog = 0;
    waitUntil {
        if (diag_tickTime > _nextMove) then {
            _nextMove = diag_tickTime + 15;
            private _bearing = _bearings select (_attempt mod (count _bearings));
            private _where = (leader _group) getRelPos [100, _bearing];
            {
                _x setPosATL [(_where # 0) + (_forEachIndex * 3), (_where # 1), 0];
            } forEach units _east;
            _attempt = _attempt + 1;
            diag_log format ["CTI|decay_probe_placing attempt=%1 bearing=%2 at=%3",
                _attempt, _bearing, mapGridPosition _where];
        };
        _report = call _sample;
        if (diag_tickTime > _nextLog) then {
            _nextLog = diag_tickTime + 10;
            private _who = leader _group;
            diag_log format ["CTI|decay_probe_waiting seen=%1 knows_any=%2 knows_east=%3 range=%4 east_alive=%5 knowsAbout=%6",
                count (_report getOrDefault ["seen", []]),
                count (_who targetsQuery [objNull, sideUnknown, "", [], 0]),
                count ((_who targetsQuery [objNull, east, "", [], 0]) select {
                    (_x # 2) isEqualTo east
                }),
                _who distance2D (leader _east),
                { alive _x } count units _east,
                _who knowsAbout (units _east # 0)];
        };
        count (_report getOrDefault ["seen", []]) > 0 || { diag_tickTime > _deadline }
    };
    private _seen = _report getOrDefault ["seen", []];
    if (count _seen isEqualTo 0) exitWith {
        diag_log "CTI|FAIL class=timeout decay_probe_never_acquired";
    };
    private _place = (_seen # 0) get "at";
    private _acquiredAt = diag_tickTime;
    diag_log format ["CTI|decay_probe_acquired place=%1 seen=%2 observed=%3",
        _place, count _seen, _report getOrDefault ["observed", []]];

    // Walk the observers off, so the place stops being observed. This is the
    // case the daemon's rule is for: nobody is looking, so nothing can report
    // the absence that would clear the Contact. Teleported rather than ordered
    // there — what is under test is the knowledge model, not the Order path, and
    // a Squad marching for ten minutes would spend the window getting there.
    private _girna = ((missionNamespace getVariable ["cti_map", createHashMap])
        getOrDefault ["objectives", []]) select { (_x get "id") isEqualTo "girna" };
    ((_girna # 0) get "position") params ["_east2", "_north2"];
    // Every observer, not just the one whose sighting was read: a Squad left
    // behind would go on watching the place and clear the Contact honestly,
    // which is the other rule and not this one.
    // Spread by index rather than at random: a probe with a PRNG in it is a
    // probe that can fail differently twice, and the contract bans a bare
    // `random` for exactly that reason.
    {
        {
            _x setPosATL [_east2 + (_forEachIndex * 3), _north2 + (_forEachIndex * 3), 0];
        } forEach units _x;
    } forEach values _squads;
    diag_log format ["CTI|decay_probe_withdrew squads=%1 to=%2 enemy_left_at=%3",
        count _squads, mapGridPosition (leader _group), _place];

    // Past the engine's 120 s, with margin for the report cadence.
    _next = diag_tickTime + 140;
    waitUntil { diag_tickTime >= _next };

    _report = call _sample;
    _seen = _report getOrDefault ["seen", []];
    private _observed = _report getOrDefault ["observed", []];
    private _stillSeen = _seen select { (_x get "at") isEqualTo _place };
    private _elapsed = diag_tickTime - _acquiredAt;

    // The sighting has aged out. Not because the engine forgot — it does not,
    // and finding that out is what this probe was worth: `targetsQuery` went on
    // returning the men at age 133 s after 140 s out of sight, so a sampler
    // asking for any age would report a memory forever and the daemon's removal
    // rule could never fire. The bound is ours, asked for explicitly, and this
    // is the assertion that it is actually being asked for.
    if (count _stillSeen > 0) then {
        diag_log format ["CTI|FAIL class=assertion_failed decay_probe_still_reported place=%1 after=%2s ages=%3",
            _place, _elapsed, _stillSeen apply { _x get "age" }];
    };

    // And nothing reports the absence. This is what keeps the daemon's Contact
    // alive: observed absence clears, and nobody is there to observe it.
    if (_place in _observed) then {
        diag_log format ["CTI|FAIL class=assertion_failed decay_probe_place_still_observed place=%1 observed=%2",
            _place, _observed];
    };

    // The enemy never moved, which is the point: they are still standing there
    // and WEST simply no longer knows it.
    diag_log format ["CTI|decay_probe_decayed place=%1 after=%2s seen=%3 observed=%4 enemy_alive=%5",
        _place, _elapsed, count _seen, _observed, { alive _x } count units _east];

    diag_log "CTI|decay_probe_done";
};
