// probe: campaign-end
// issues: 35
// window: 750
// env: CTI_HOLD_HC=1 CTI_AI_SIDE=WEST,EAST CTI_AI_SEED=1,4
//
// #35 in-world probe: an unattended two-AI Campaign that actually ends.
//
// `just regress campaign-end` reads the block above. By hand:
//   CTI_HOLD_HC=1 CTI_AI_SIDE=WEST,EAST CTI_AI_SEED=1,4 \
//       just probe spike/probes/campaign-end.sqf 600
//
// This is #17's demo with an ending on it, and it ends by **Decapitation**. What
// no unit test can stand in for is the whole loop closing on the real topology:
// a Commander deciding on its own picture that the Campaign is worth ending, the
// Order crossing the real port, a real building coming down, the real report
// carrying that back, the daemon calling it, and the `campaign_won` effect
// crossing the real outbox into a world that acts on it — with two Commanders
// playing and nobody sending a Command.
//
// ---- what is engineered, and what is not
//
// Two things are engineered, both about *position* and neither about a rule.
//
//   1. The island. Once both Commanders have fielded a force, this spawns one
//      WEST rifleman inside each Objective's capture radius. They are real men
//      on real ground and the daemon takes the island from the reports it always
//      reads, thirty seconds per Objective. This is what brings the Campaign to
//      the state in which a Commander plays for Decapitation — ADR-0020's
//      predicted arc, "the first option for a Squad that has run out of ground
//      worth taking", built in #34.
//   2. The march. The Squad the Commander has itself ordered to Assault is put
//      on its approach 250 m out, from authored geometry — the same shortening
//      `spike/probes/base-assault.sqf` takes and for the same declared reason:
//      the two Bases are 4.4 km apart, which is forty minutes of engine walking
//      and nothing this probe is measuring.
//
// The second one waits for the enemy Base to be empty of EAST infantry first,
// and that wait is what makes the shortening honest rather than a thumb on the
// scale. Measured on 2026-08-01: staged the instant the Order landed, at t=40,
// the Squad arrived while EAST's three Squads were still standing on their own
// Base and had not yet marched out — 8 men dropped into 24, five dead in
// twenty-five seconds, and the run timed out with the HQ untouched. That is not
// a defeat the Campaign would ever have handed out. A Squad that actually
// walked the 4.4 km arrives around t=2600, by which time those Squads are long
// gone; teleporting it to 250 m at t=40 put it somewhere the Campaign could not
// have put it. Waiting for the Base to clear restores the conditions the
// shortened march stands in for. It does not make the Assault succeed — the HQ
// still has to be reached and worked on, and whatever EAST left behind is still
// there.
//
// Not engineered: the decision or the detection. Nothing here issues a Command.
// The Assault is the Commander's own, chosen off its own projected picture and
// carried through the port that is the only order path there is — this probe
// waits for it and refuses the run if it never comes. The HQ falls because a
// Squad worked on it, and the Campaign ends because the daemon read that.
//
// ---- why not Domination
//
// It was tried first, on 2026-08-01, and it lost a race that cannot be won: the
// staged island went WEST at t=40, and EAST's Commander marched on camp_rogain
// and contested it at t=511, 471 s into the 600 s the rule asks for. That is a
// Campaign behaving correctly and a probe that would be a coin toss, so it is
// not in the corpus. Nothing could shorten the wait either — `setAccTime` is
// disabled in multiplayer and `setTimeMultiplier` moves the in-game clock rather
// than `time`, which is what the rules are written in (both checked against the
// vendored wiki). The Domination timer is unit-tested against simulated clocks
// in `tests/unit/test_win_conditions.py`, which is where a ten-minute rule
// belongs.
//
// ---- the window
//
// Added up rather than guessed at: ~20 s for the world to settle, ~25 s for both
// Commanders to buy through the outbox, ~35 s for the island to fall and the
// next plan to land, ~200 s for EAST's three Squads to walk clear of their own
// Base (three of them were still standing on it at t=55, measured), ~150 s for
// the assaulting Squad to cover the staged 250 m at the pace an AWARE waypoint
// moves, 90 s of demolition (cti_fnc_baseAssault's durability placeholder), a
// report interval and an effect poll to carry it, and 40 s of watching the
// ended Campaign stay ended. About 590 s of subject; 750 s is that plus the
// engine's pathfinding around an airfield. If this ever needs *more*, the answer
// is not a bigger number: it is that the Squad is not arriving.
[] spawn {
    private _extension = call cti_fnc_shimName;
    if (_extension isEqualTo "") exitWith {
        diag_log "CTI|FAIL class=infra_unavailable end_probe_no_shim";
    };

    private _map = missionNamespace getVariable ["cti_map", createHashMap];
    private _objectives = _map getOrDefault ["objectives", []];
    private _bases = _map getOrDefault ["bases", []];
    if (count _objectives isEqualTo 0 || { count _bases isEqualTo 0 }) exitWith {
        diag_log "CTI|FAIL class=assertion_failed end_probe_no_map";
    };

    private _placeNamed = {
        params ["_id"];
        private _found = createHashMap;
        { if ((_x getOrDefault ["id", ""]) isEqualTo _id) exitWith { _found = _x } }
            forEach (_objectives + _bases);
        _found
    };
    private _target = ["csat_kamino"] call _placeNamed;
    private _hq = missionNamespace getVariable [_target getOrDefault ["hq", ""], objNull];
    if (isNull _hq) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed end_probe_no_hq name=%1",
            _target getOrDefault ["hq", ""]];
    };

    // ------------------------------------------------ topology
    // The MVP test topology is a dedicated server plus a headless client. A run
    // without the headless client is a different run, so it is refused rather
    // than reported as a pass.
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
        diag_log format ["CTI|FAIL class=infra_unavailable end_probe_no_headless_client users=%1 hint=%2",
            count allUsers, "is CTI_HOLD_HC=1 set?"];
    };

    // ------------------------------------------------ both sides are being played
    // Nobody sends a Command in this probe, here or below. What is waited for is
    // each Commander having bought something off its own picture — otherwise a
    // Campaign could be "won" against a side nobody was playing.
    private _sideOf = createHashMapFromArray [["WEST", west], ["EAST", east]];
    private _fielded = {
        params ["_name"];
        private _found = 0;
        {
            if (!isNull _y && { side _y isEqualTo (_sideOf get _name) }) then { _found = _found + 1 };
        } forEach (missionNamespace getVariable ["cti_squads", createHashMap]);
        _found
    };

    _deadline = diag_tickTime + 120;
    waitUntil {
        (["WEST"] call _fielded > 0 && { ["EAST"] call _fielded > 0 })
            || { diag_tickTime > _deadline }
    };
    if (["WEST"] call _fielded isEqualTo 0 || { ["EAST"] call _fielded isEqualTo 0 }) exitWith {
        diag_log format ["CTI|FAIL class=timeout end_probe_side_fielded_nothing west=%1 east=%2 hint=%3",
            ["WEST"] call _fielded, ["EAST"] call _fielded, "is CTI_AI_SIDE=WEST,EAST set?"];
    };
    diag_log format ["CTI|end_probe_commanders west=%1 east=%2 at=%3",
        ["WEST"] call _fielded, ["EAST"] call _fielded, time];

    // ------------------------------------------------ engineered start: the island
    // One WEST rifleman per Objective, one group each, and pinned. Eight men in
    // one group would form up on their leader and walk off seven of the eight;
    // one man told not to path stays where he was put. Nothing about the capture
    // is disabled — the daemon still has to read them standing there.
    private _staged = 0;
    {
        (_x get "position") params ["_east", "_north"];
        private _group = createGroup [west, true];
        private _man = _group createUnit ["B_Soldier_F", [_east, _north, 0], [], 0, "NONE"];
        if (!isNull _man) then {
            _man disableAI "PATH";
            _staged = _staged + 1;
        };
    } forEach _objectives;
    if (_staged < count _objectives) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed end_probe_staging_failed men=%1 objectives=%2",
            _staged, count _objectives];
    };

    // Read off the markers, which are painted from the daemon's own reply
    // (cti_fnc_presenceReport) — so this is the daemon's ownership rather than a
    // second opinion formed in here.
    _deadline = diag_tickTime + 180;
    private _allWest = {
        private _held = 0;
        { if (_y isEqualTo "WEST") then { _held = _held + 1 } }
            forEach (missionNamespace getVariable ["cti_objectiveOwner", createHashMap]);
        _held isEqualTo (count _objectives)
    };
    waitUntil { call _allWest || { diag_tickTime > _deadline } };
    if !(call _allWest) exitWith {
        diag_log format ["CTI|FAIL class=timeout end_probe_island_never_fell owners=%1",
            missionNamespace getVariable ["cti_objectiveOwner", createHashMap]];
    };
    diag_log format ["CTI|end_probe_island_held men=%1 at=%2", _staged, time];

    // ------------------------------------------------ the Commander decides
    // The part that is not this probe's: with no ground left worth taking, WEST's
    // Commander should reach for the other win condition on its own. Waited for
    // rather than arranged, and the run is refused if it never happens — an
    // Assault this probe had to ask for would prove nothing about a Commander.
    _deadline = diag_tickTime + 120;
    private _attackerId = "";
    private _attacker = grpNull;
    waitUntil {
        {
            private _order = _y getVariable ["cti_order", createHashMap];
            if ((_order getOrDefault ["order", ""]) isEqualTo "assault"
                && { (_order getOrDefault ["place", ""]) isEqualTo "csat_kamino" }
                && { !isNull _y }) exitWith {
                _attackerId = _x;
                _attacker = _y;
            };
        } forEach (missionNamespace getVariable ["cti_squads", createHashMap]);
        !isNull _attacker || { diag_tickTime > _deadline }
    };
    if (isNull _attacker) exitWith {
        diag_log format ["CTI|FAIL class=timeout end_probe_commander_never_assaulted squads=%1",
            count (missionNamespace getVariable ["cti_squads", createHashMap])];
    };
    diag_log format ["CTI|end_probe_assault_ordered squad=%1 at=%2 range=%3",
        _attackerId, time, (leader _attacker) distance2D (getPosATL _hq)];

    // ------------------------------------------------ let the defenders leave
    // EAST spawns its Squads on its own Base and its Commander marches them out
    // at the opening. A Squad put on the approach before they have gone is a
    // Squad dropped into an army — see the header: that was measured, and it
    // cost a run. Waited on as the ground actually being clear rather than as a
    // fixed delay, because how long three Squads take to walk off their own Base
    // is the engine's business and not a number to guess.
    private _hqAt = getPosATL _hq;
    private _defenders = {
        private _men = 0;
        {
            if (alive _x && { side group _x isEqualTo east }) then { _men = _men + 1 };
        } forEach (_hqAt nearEntities ["CAManBase", 400]);
        _men
    };
    _deadline = diag_tickTime + 300;
    waitUntil { call _defenders isEqualTo 0 || { diag_tickTime > _deadline } };
    if (call _defenders > 0) exitWith {
        // Not a probe fault: EAST has chosen to sit on its own Base, which is a
        // Campaign this probe cannot shorten and a finding worth the red.
        diag_log format ["CTI|FAIL class=timeout end_probe_base_never_cleared men=%1 at=%2",
            call _defenders, time];
    };
    diag_log format ["CTI|end_probe_base_clear at=%1 squad_men=%2",
        time, { alive _x } count units _attacker];

    // ------------------------------------------------ engineered start: the march
    // On the line between the enemy Base's HQ and the Objective the manifest
    // calls adjacent to that Base, 250 m out. Authored ground rather than a
    // bearing off somebody's facing — #28's lesson, which cost two probes.
    private _adjacent = [(_target getOrDefault ["adjacent", [""]]) # 0] call _placeNamed;
    if (count _adjacent isEqualTo 0) exitWith {
        diag_log "CTI|FAIL class=assertion_failed end_probe_no_adjacent_place";
    };
    (_adjacent get "position") params ["_fromEast", "_fromNorth"];
    private _runEast = _fromEast - (_hqAt # 0);
    private _runNorth = _fromNorth - (_hqAt # 1);
    private _span = sqrt ((_runEast * _runEast) + (_runNorth * _runNorth));
    private _approach = [
        (_hqAt # 0) + (_runEast / _span * 250),
        (_hqAt # 1) + (_runNorth / _span * 250),
        0
    ];
    {
        _x setPosATL [(_approach # 0) + (_forEachIndex * 4), _approach # 1, 0];
    } forEach units _attacker;
    diag_log format ["CTI|end_probe_staged_march squad=%1 at=%2 from=%3 range=%4",
        _attackerId, mapGridPosition _approach, _adjacent get "id",
        (leader _attacker) distance2D _hqAt];

    // ------------------------------------------------ the Campaign ends
    _deadline = diag_tickTime + 300;
    waitUntil {
        count (missionNamespace getVariable ["cti_campaignOutcome", createHashMap]) > 0
            || { diag_tickTime > _deadline }
    };
    private _outcome = missionNamespace getVariable ["cti_campaignOutcome", createHashMap];
    if (count _outcome isEqualTo 0) exitWith {
        diag_log format ["CTI|FAIL class=timeout end_probe_campaign_never_ended damage=%1 range=%2 men=%3 down=%4",
            damage _hq, (leader _attacker) distance2D _hqAt,
            { alive _x } count units _attacker,
            missionNamespace getVariable ["cti_hqDown", createHashMap]];
    };

    private _condition = _outcome getOrDefault ["condition", ""];
    private _side = _outcome getOrDefault ["side", ""];
    private _summary = _outcome getOrDefault ["summary", createHashMap];
    diag_log format ["CTI|end_probe_outcome side=%1 condition=%2 at=%3 damage=%4 elapsed=%5",
        _side, _condition, _outcome getOrDefault ["at", 0], damage _hq, time];

    if (_condition isNotEqualTo "decapitation") then {
        diag_log format ["CTI|FAIL class=assertion_failed end_probe_wrong_condition condition=%1 outcome=%2",
            _condition, _outcome];
    };
    if (_side isNotEqualTo "WEST") then {
        // The side that loses is the side whose Base fell, and csat_kamino is
        // EAST's. A winner of EAST here would mean the rule read `by` instead.
        diag_log format ["CTI|FAIL class=assertion_failed end_probe_wrong_winner side=%1", _side];
    };
    // The Campaign ended because a building actually came down, not because
    // something decided it had.
    if (damage _hq < 1) then {
        diag_log format ["CTI|FAIL class=oracle_disagreement end_probe_hq_still_standing damage=%1",
            damage _hq];
    };

    // The end screen's own numbers, off telemetry rather than off campaign state
    // (ADR-0023). A summary the world could not read is an end screen with
    // nothing on it.
    private _hqRows = _summary getOrDefault ["headquarters", []];
    if (count (_summary getOrDefault ["owners", createHashMap]) isEqualTo 0
        || { count _hqRows isEqualTo 0 }) then {
        diag_log format ["CTI|FAIL class=assertion_failed end_probe_summary_empty summary=%1", _summary];
    };
    diag_log format ["CTI|end_probe_summary winner=%1 objectives=%2 income=%3 commands=%4 squads_lost=%5 hq=%6",
        _summary getOrDefault ["winner", "?"],
        count (_summary getOrDefault ["owners", createHashMap]),
        _summary getOrDefault ["income", createHashMap],
        _summary getOrDefault ["commands", createHashMap],
        _summary getOrDefault ["squads_lost", "?"], _hqRows];

    // A won Campaign is over: both Commanders stand down and Funds stop moving,
    // so the world stops being handed things to do. The first twenty seconds are
    // given away rather than measured — effects already on the outbox when the
    // Campaign ended are still theirs to deliver, and counting those would be
    // counting the last cycle of a Campaign that was still being played.
    private _next = diag_tickTime + 20;
    waitUntil { diag_tickTime >= _next };
    private _drain = missionNamespace getVariable ["cti_effectDrain", createHashMap];
    private _applied = _drain getOrDefault ["applied", 0];
    _next = diag_tickTime + 20;
    waitUntil { diag_tickTime >= _next };
    _drain = missionNamespace getVariable ["cti_effectDrain", createHashMap];
    private _after = _drain getOrDefault ["applied", 0];
    if (_after > _applied) then {
        diag_log format ["CTI|FAIL class=assertion_failed end_probe_still_being_played was=%1 now=%2",
            _applied, _after];
    };
    // Still polling, though: a daemon that had stopped answering would look the
    // same from here as one that had nothing left to say.
    if ((_drain getOrDefault ["polls", 0]) <= 0) then {
        diag_log format ["CTI|FAIL class=assertion_failed end_probe_pump_stopped drain=%1", _drain];
    };
    diag_log format ["CTI|end_probe_quiet applied=%1 polls=%2 at=%3",
        _after, _drain getOrDefault ["polls", 0], time];

    diag_log "CTI|end_probe_done";
};
