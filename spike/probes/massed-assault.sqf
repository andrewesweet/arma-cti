// probe: massed-assault
// issues: 38
// window: 780
// env: CTI_HOLD_HC=1 CTI_AI_SIDE=WEST,EAST CTI_AI_SEED=1,4
//
// #38 in-world probe: a *defended* enemy Base falls, to a Commander that sent
// more than one Squad at it.
//
// `just regress massed-assault` reads the block above. By hand:
//   CTI_HOLD_HC=1 CTI_AI_SIDE=WEST,EAST CTI_AI_SEED=1,4 \
//       just probe spike/probes/massed-assault.sqf 780
//
// `campaign-end` already shows a Campaign ending by Decapitation, against a Base
// this probe's predecessor had to wait until it was *empty*. #35 measured what
// happens against one that is not: eight men dropped into three EAST Squads,
// five dead in twenty-five seconds, the HQ untouched. The scorer sent one Squad
// because assignment gave every Place one, and a Base is not a Place one Squad
// can take. ADR-0027 is the answer and this is the half of it no unit test can
// stand in for.
//
// The unit tier feeds the planner a Contact it wrote itself. What only the world
// can show is the loop: real men standing on a real Base, acquired by a real
// leader through the engine's own knowledge model, banded by the sampler,
// carried to the daemon as a Contact with an age on it, read as a demand for
// force, and answered with Orders for several Squads at one Place crossing the
// real port. Nothing in that chain is mocked here, and none of it is asked for.
//
// ---- what is engineered, and what is not
//
// Three things, all about *position*, none about a rule — the same licence
// `campaign-end` and `base-assault` take, and stated the same way.
//
//   1. The island. One WEST rifleman inside each Objective's capture radius, so
//      the Campaign reaches the state where a Commander plays for the enemy HQ.
//      The daemon still has to read them standing there.
//   2. The garrison. EAST riflemen spawned on their own Base and told not to
//      path, *after* EAST's own Squads have marched out of it. They are what
//      makes this Base defended rather than empty, and they are put there rather
//      than waited for because whether EAST's Commander leaves a rear guard is
//      its own business and not something to hang a probe on. They are not
//      Squads, report to nobody, and are seen only if WEST's men actually see
//      them.
//   3. The march, twice. The two Bases are 4.4 km apart — forty minutes of
//      engine walking, and nothing this probe measures. The first Squad the
//      Commander orders to Assault is put 250 m out on the line between the HQ
//      and the Objective the manifest calls adjacent to that Base, exactly as
//      `campaign-end` does; the Squads the Commander then adds are put on the
//      same line when it adds them.
//
// Not engineered: the Contact, the count, or the decision. Nobody tells the
// daemon there is a garrison — WEST's leader has to acquire it. Nobody tells the
// planner how many Squads to send; `ASSAULT_MASS` reads the band the sampler
// produced, and this probe only counts what came out. Nothing here issues a
// Command, and an Assault that never masses is a red rather than a nudge.
//
// ---- what would make this red, and what each red would mean
//
// No second Squad, with the first still under Orders: the Contact never reached
// the planner, or the band did not demand more. Assault called off altogether:
// a force of eight declined, which against this garrison is wrong and is the
// decline branch firing where it should not. HQ standing at the deadline: the
// mass arrived and lost, which is `ASSAULT_MASS` set too low and the number
// flagged for sign-off in #38 being the thing that is wrong.
//
// ---- the window
//
// Added up rather than guessed at: ~20 s for the world to settle, ~25 s for both
// Commanders to buy through the outbox, ~35 s for the staged island to fall and
// the next plan to land, ~20 s for the first Assault to be decided, ~200 s for
// EAST's Squads to walk clear of their own Base (measured on #35), ~150 s for
// the first Squad to cover the staged 250 m at the pace an AWARE waypoint moves,
// ~20 s for the sighting to become a Contact, cross to the daemon and come back
// as Orders, ~150 s for the rest of the mass to cover the same 250 m, ~60 s of
// fighting through a garrison, 90 s of demolition (cti_fnc_baseAssault's
// durability placeholder), and a report interval to carry the HQ down. That is
// about 620 s of subject; 780 is that plus the engine's pathfinding around an
// airfield, which is the part nobody can predict to the second. If this ever
// needs *more*, the answer is not a bigger number: it is that the mass is not
// arriving, and that is the bug.
[] spawn {
    private _extension = call cti_fnc_shimName;
    if (_extension isEqualTo "") exitWith {
        diag_log "CTI|FAIL class=infra_unavailable mass_probe_no_shim";
    };

    private _map = missionNamespace getVariable ["cti_map", createHashMap];
    private _objectives = _map getOrDefault ["objectives", []];
    private _bases = _map getOrDefault ["bases", []];
    if (count _objectives isEqualTo 0 || { count _bases isEqualTo 0 }) exitWith {
        diag_log "CTI|FAIL class=assertion_failed mass_probe_no_map";
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
        diag_log format ["CTI|FAIL class=assertion_failed mass_probe_no_hq name=%1",
            _target getOrDefault ["hq", ""]];
    };
    private _hqAt = getPosATL _hq;

    // ------------------------------------------------ topology
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
        diag_log format ["CTI|FAIL class=infra_unavailable mass_probe_no_headless_client users=%1 hint=%2",
            count allUsers, "is CTI_HOLD_HC=1 set?"];
    };

    // ------------------------------------------------ both sides are being played
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
        diag_log format ["CTI|FAIL class=timeout mass_probe_side_fielded_nothing west=%1 east=%2 hint=%3",
            ["WEST"] call _fielded, ["EAST"] call _fielded, "is CTI_AI_SIDE=WEST,EAST set?"];
    };
    diag_log format ["CTI|mass_probe_commanders west=%1 east=%2 at=%3",
        ["WEST"] call _fielded, ["EAST"] call _fielded, time];

    // ------------------------------------------------ engineered start: the island
    // One man per Objective, one group each, pinned. Eight in one group would
    // form up on their leader and walk off seven of them.
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
        diag_log format ["CTI|FAIL class=assertion_failed mass_probe_staging_failed men=%1 objectives=%2",
            _staged, count _objectives];
    };

    // Read off the markers, painted from the daemon's own reply — the daemon's
    // ownership rather than a second opinion formed in here.
    _deadline = diag_tickTime + 180;
    private _allWest = {
        private _held = 0;
        { if (_y isEqualTo "WEST") then { _held = _held + 1 } }
            forEach (missionNamespace getVariable ["cti_objectiveOwner", createHashMap]);
        _held isEqualTo (count _objectives)
    };
    waitUntil { call _allWest || { diag_tickTime > _deadline } };
    if !(call _allWest) exitWith {
        diag_log format ["CTI|FAIL class=timeout mass_probe_island_never_fell owners=%1",
            missionNamespace getVariable ["cti_objectiveOwner", createHashMap]];
    };
    diag_log format ["CTI|mass_probe_island_held men=%1 at=%2", _staged, time];

    // ------------------------------------------------ who is under the Assault
    private _raiders = {
        private _found = [];
        {
            private _order = _y getVariable ["cti_order", createHashMap];
            if (!isNull _y
                && { (_order getOrDefault ["order", ""]) isEqualTo "assault" }
                && { (_order getOrDefault ["place", ""]) isEqualTo "csat_kamino" }) then {
                _found pushBack [_x, _y];
            };
        } forEach (missionNamespace getVariable ["cti_squads", createHashMap]);
        _found
    };

    // ------------------------------------------------ the Commander decides
    // Not this probe's part: with no ground left worth taking, WEST should reach
    // for the other win condition on its own. Waited for, refused if it never
    // comes — an Assault this probe had to ask for would prove nothing.
    _deadline = diag_tickTime + 120;
    waitUntil { count (call _raiders) > 0 || { diag_tickTime > _deadline } };
    private _first = call _raiders;
    if (count _first isEqualTo 0) exitWith {
        diag_log format ["CTI|FAIL class=timeout mass_probe_commander_never_assaulted squads=%1",
            count (missionNamespace getVariable ["cti_squads", createHashMap])];
    };
    diag_log format ["CTI|mass_probe_assault_ordered squads=%1 at=%2",
        _first apply { _x # 0 }, time];

    // ------------------------------------------------ let EAST's own Squads leave
    // The garrison below is staged, and staging it under EAST's own Squads would
    // make this a fight against both. #35 measured what a Squad put on the
    // approach before they had gone runs into. Waited on as the ground actually
    // being clear rather than as a fixed delay.
    private _eastMen = {
        private _men = 0;
        {
            if (alive _x && { side group _x isEqualTo east }) then { _men = _men + 1 };
        } forEach (_hqAt nearEntities ["CAManBase", 400]);
        _men
    };
    _deadline = diag_tickTime + 300;
    waitUntil { call _eastMen isEqualTo 0 || { diag_tickTime > _deadline } };
    if (call _eastMen > 0) exitWith {
        diag_log format ["CTI|FAIL class=timeout mass_probe_base_never_cleared men=%1 at=%2",
            call _eastMen, time];
    };
    diag_log format ["CTI|mass_probe_base_clear at=%1", time];

    // ------------------------------------------------ engineered start: the garrison
    // Twelve men on their own Base, told not to path so they stay on it. Twelve
    // rather than a round company: what the band comes out as is what WEST's
    // leader manages to see, and inflating the number to force a band would be
    // arranging the answer. Whatever it sees is what the mass is read from, and
    // this probe asserts the relation rather than the number.
    private _garrison = createGroup [east, true];
    private _defenders = 0;
    for "_i" from 0 to 11 do {
        private _angle = _i * 30;
        private _spot = [
            (_hqAt # 0) + (15 * sin _angle),
            (_hqAt # 1) + (15 * cos _angle),
            0
        ];
        private _man = _garrison createUnit ["O_Soldier_F", _spot, [], 0, "NONE"];
        if (!isNull _man) then {
            _man disableAI "PATH";
            _defenders = _defenders + 1;
        };
    };
    if (_defenders isEqualTo 0) exitWith {
        diag_log "CTI|FAIL class=assertion_failed mass_probe_garrison_failed";
    };
    _garrison setBehaviour "COMBAT";
    diag_log format ["CTI|mass_probe_garrison men=%1 at=%2 grid=%3",
        _defenders, time, mapGridPosition _hqAt];

    // ------------------------------------------------ the approach line
    // On the line between the HQ and the Objective the manifest calls adjacent
    // to this Base, 250 m out. Authored ground rather than a bearing off
    // somebody's facing — #28's lesson, which cost two probes.
    private _adjacent = [(_target getOrDefault ["adjacent", [""]]) # 0] call _placeNamed;
    if (count _adjacent isEqualTo 0) exitWith {
        diag_log "CTI|FAIL class=assertion_failed mass_probe_no_adjacent_place";
    };
    (_adjacent get "position") params ["_fromEast", "_fromNorth"];
    private _runEast = _fromEast - (_hqAt # 0);
    private _runNorth = _fromNorth - (_hqAt # 1);
    private _span = sqrt ((_runEast * _runEast) + (_runNorth * _runNorth));
    private _approach = [
        (_hqAt # 0) + (_runEast / _span * 250),
        (_hqAt # 1) + (_runNorth / _span * 250)
    ];
    private _putOnApproach = {
        params ["_squads", "_lane"];
        private _placed = [];
        {
            _x params ["_id", "_group"];
            {
                _x setPosATL [
                    (_approach # 0) + (_lane * 30) + (_forEachIndex * 4),
                    (_approach # 1) + (_lane * 10),
                    0
                ];
            } forEach units _group;
            _placed pushBack _id;
            _lane = _lane + 1;
        } forEach _squads;
        _placed
    };

    private _staffed = [_first, 0] call _putOnApproach;
    diag_log format ["CTI|mass_probe_staged_march squads=%1 at=%2 from=%3 grid=%4",
        _staffed, time, _adjacent get "id", mapGridPosition _approach];

    // ------------------------------------------------ the Commander reinforces
    // The criterion. The first Squad is now where it can see the Base; what the
    // planner does with what it sees is ADR-0027, and it has to come out as more
    // Squads named on this one Place. Nothing below asks for that.
    private _wanted = 2;
    _deadline = diag_tickTime + 240;
    private _mass = _first;
    waitUntil {
        _mass = call _raiders;
        count _mass >= _wanted || { count _mass isEqualTo 0 } || { diag_tickTime > _deadline }
    };
    if (count _mass isEqualTo 0) exitWith {
        // The decline branch, fired where it should not: eight Squads is more
        // than this garrison's band can want. Correct behaviour on a force too
        // small to mass, wrong here, and the trace's `assault csat_kamino` row
        // in the daemon telemetry says which band it read.
        diag_log format ["CTI|FAIL class=assertion_failed mass_probe_assault_called_off squads=%1 at=%2",
            ["WEST"] call _fielded, time];
    };
    if (count _mass < _wanted) exitWith {
        diag_log format ["CTI|FAIL class=timeout mass_probe_never_massed sent=%1 wanted=%2 at=%3 range=%4",
            count _mass, _wanted, time,
            (leader ((_first # 0) # 1)) distance2D _hqAt];
    };
    diag_log format ["CTI|mass_probe_massed squads=%1 sent=%2 at=%3",
        _mass apply { _x # 0 }, count _mass, time];

    // Everything the Commander added goes on the same line, for the same
    // declared reason as the first: the 4.4 km is not what is being measured.
    private _reinforcements = _mass select { !((_x # 0) in _staffed) };
    private _brought = [_reinforcements, 1] call _putOnApproach;
    diag_log format ["CTI|mass_probe_staged_reinforcements squads=%1 at=%2", _brought, time];

    // ------------------------------------------------ the Base falls
    _deadline = diag_tickTime + 300;
    waitUntil {
        count (missionNamespace getVariable ["cti_campaignOutcome", createHashMap]) > 0
            || { diag_tickTime > _deadline }
    };
    private _outcome = missionNamespace getVariable ["cti_campaignOutcome", createHashMap];
    if (count _outcome isEqualTo 0) exitWith {
        diag_log format ["CTI|FAIL class=timeout mass_probe_base_never_fell damage=%1 attackers=%2 defenders=%3 at=%4",
            damage _hq,
            count (_mass select { { alive _x } count units (_x # 1) > 0 }),
            { alive _x && { side group _x isEqualTo east } } count (_hqAt nearEntities ["CAManBase", 400]),
            time];
    };

    private _condition = _outcome getOrDefault ["condition", ""];
    private _side = _outcome getOrDefault ["side", ""];
    diag_log format ["CTI|mass_probe_outcome side=%1 condition=%2 at=%3 damage=%4 elapsed=%5",
        _side, _condition, _outcome getOrDefault ["at", 0], damage _hq, time];

    if (_condition isNotEqualTo "decapitation") then {
        diag_log format ["CTI|FAIL class=assertion_failed mass_probe_wrong_condition condition=%1 outcome=%2",
            _condition, _outcome];
    };
    if (_side isNotEqualTo "WEST") then {
        diag_log format ["CTI|FAIL class=assertion_failed mass_probe_wrong_winner side=%1", _side];
    };
    // The Campaign ended because a building came down, not because something
    // decided it had.
    if (damage _hq < 1) then {
        diag_log format ["CTI|FAIL class=oracle_disagreement mass_probe_hq_still_standing damage=%1",
            damage _hq];
    };
    // And it came down against a Base that was actually held. A garrison that
    // had evaporated before the mass arrived would make this a second
    // `campaign-end` rather than this probe.
    diag_log format ["CTI|mass_probe_defence_at_the_end alive=%1 of=%2",
        { alive _x } count units _garrison, _defenders];

    diag_log "CTI|mass_probe_done";
};
