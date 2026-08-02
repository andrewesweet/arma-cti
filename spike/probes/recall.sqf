// probe: recall
// issues: 104
// window: 480
// env: CTI_AI_SIDE=WEST CTI_AI_SEED=1
//
// #104 in-world probe: a company standing on ground we hold turns a Squad round,
// and a platoon does not.
//
// `just regress recall` reads the block above. By hand:
//   CTI_AI_SIDE=WEST CTI_AI_SEED=1 just probe spike/probes/recall.sqf 480
//
// ADR-0031 is the rule. It named `homeland` out loud, replaced eight summed
// weights with a product of eight considerations, and reported one behaviour
// that changed in degree: the recall radius grew from 160 m to 1.15 km, because
// under the curves a company on held ground is worth the Place's whole value to
// stand on (`hold` reaches 1.0 at a company) where a platoon is worth a third of
// it. The human signed off both flagged placeholders — the radius and
// `homeland = 10.0` — on 2026-08-01, on a 200-seed pytest sweep. #49's four-probe
// pass then confirmed the scorer's traces end to end in-world and could not show
// this one thing: `hold` never exceeded 0.114 in any run, because no company ever
// stood on ground WEST held, so no Squad was ever offered the turn-round. This
// probe stages that condition rather than hoping for it.
//
// ---- what is engineered, and what is not
//
// Three things, all about *position* and *ownership* — the board, never the
// decision. `campaign-end` and `massed-assault` are the precedent for each.
//
//   1. The board. One pinned WEST rifleman inside the capture radius of
//      Agia Marina, Camp Tempest and Girna, so WEST holds three Objectives and
//      the Commander is playing a mid-Campaign rather than an opening. The
//      daemon still has to read them standing there: ownership is waited for on
//      `cti_objectiveOwner`, which is painted from the daemon's own reply. They
//      are not Squads and report to nobody, so they hold ground and see nothing.
//   2. The watchers. WEST's Squads are put in open ground 400 m off Agia Marina
//      on the line towards the Place the manifest calls adjacent to it — Camp
//      Tempest, read off the manifest rather than written out — and held there.
//      Authored ground rather than a bearing off somebody's facing, which is
//      #28's lesson and cost two probes. Open ground on purpose:
//      a Squad standing *in* a Place is measured from that Place, and one
//      between Places is measured from the Base it was bought at (`_options`),
//      which is what makes the march this probe interrupts a 1,073 m one — the
//      authored Base-to-Agia-Marina edge, inside ADR-0031's approved 1.15 km and
//      6.7 times the 160 m the summed scorer would have recalled from.
//   3. The men. EAST riflemen in a ring around the watchers, 24 first and 40
//      more after, standing, told not to shoot, unable to die and unable to
//      path. That is `contacts.sqf`'s licence taken for `contacts.sqf`'s reason:
//      here the head count *is* the band, and the band is the whole subject.
//      They are outside Agia Marina's 200 m capture radius and nearer to it than
//      to anything else, so they are filed at Agia Marina by `cti_fnc_placeOf`
//      without contesting the ground the assertion needs WEST to hold.
//
// Not engineered: the Contact, the band, or the Order. Nobody tells the daemon
// there are men at Agia Marina — WEST's own leaders have to acquire them, through
// the engine's knowledge model and the same sampler the daemon bands
// (`cti_fnc_contactSample`). Nobody tells the Commander to turn anything round.
// The two band floors are read from the daemon's own table through
// `cti_fnc_commandSchema` (#110), so a retuned `contacts.ECHELONS` changes what
// this probe means rather than silently not changing it.
//
// ---- the assertion, and why it is the Order rather than the march
//
// CLAUDE.md: bet on the decision the code owns. The Commander owns the Order; it
// does not own how long eight men take to walk a kilometre, and a probe that
// waited for the walk would be measuring the engine's pathfinding with a
// scoring rule's name on it. So both halves are read off `cti_order`, the
// standing Order the effect pump landed on the group — the daemon's decision as
// it reaches the world:
//
//   - **Negative, at a platoon**: for 45 s, no Squad that held a Capture Order
//     when the band was reached is given `defend agia_marina`. Evaluated on
//     every pass rather than once at the end, because the strength of an absence
//     claim is the time it was observed for.
//   - **Positive, at a company**: one of those Squads is, within 60 s, and its
//     leader is outside the Objective's capture radius — a Squad turning round,
//     not a Squad already standing there.
//
// The negative is restricted to Squads that were capturing on purpose. A
// Commander with more Squads than there is ground left for parks the surplus on
// the best thing going, and at a platoon that can honestly be a quiet garrison;
// what ADR-0020 pinned, and what this asserts, is that a *marching* Squad is not
// turned round by a platoon.
//
// ---- why this board, measured rather than assumed
//
// The three held Objectives are not decoration. The recall competes against
// whatever the Squad was already doing, and `momentum` is worth 0.2 to the
// standing Order, so a Squad already ordered to a near Objective outbids the
// turn-round. Running the real planner offline over the board this probe stages
// (WEST holding Agia Marina, Camp Tempest and Girna; Squads in open ground;
// settle, then a platoon Contact, then a company Contact from the platoon state)
// gives the assertion above on **every seed of 0..29 at every roster size from
// two to six Squads**, and both halves fail on some seeds if Camp Tempest or
// Girna is left capturable. At seven Squads the surplus rule above starts to
// bite, and seven Squads costs 700 Funds — starting 300 plus 35 a minute on
// three held Objectives is eleven minutes, so the window closes first.
//
// ---- what would make this red, and what each red would mean
//
// Nobody acquired anything: the geometry is wrong, and the fix is geometry —
// the ring is re-laid every 30 s and closer each time for exactly that reason
// (#28's lesson, which cost two probes). A Squad turned round by the platoon:
// `hold` is too steep, or `homeland`/`hold_floor` have drifted, and the 200-seed
// sweep is wrong about a boundary a human signed off. No Squad turned round by
// the company: the recall does not survive contact with the world, which is the
// one thing #49 could not rule out.
//
// ---- the window
//
// Added up rather than guessed at: ~20 s for the world to settle, ~60 s for the
// Commander to buy off its own picture, ~75 s for three Objectives to change
// hands at `capture_seconds` plus a report, ~90 s for the engine to acquire nine
// of twenty-four men in a ring at 80 m, 45 s of watching a Squad not turn round,
// ~120 s to acquire twenty-five of sixty-four, and 60 s for the Contact to cross
// to the daemon and come back as an Order. 470 s of subject; 480 is that. If it
// ever needs more, the answer is not a bigger number: acquisition is not
// arriving, and the evidence lines say so.
//
// Measured at **110 s and 114 s** on two consecutive greens, 2026-08-02: both
// acquisitions landed in about two seconds, so what the corpus actually pays is
// the 45 s of watching a Squad not turn round plus the board changing hands. The
// two acquisition deadlines stay where they are because #28's history is that
// acquisition is the thing that varies, and a deadline sized to a good draw is
// how a probe becomes a flake.
[] spawn {
    private _extension = call cti_fnc_shimName;
    if (_extension isEqualTo "") exitWith {
        diag_log "CTI|FAIL class=infra_unavailable recall_probe_no_shim";
    };

    private _map = missionNamespace getVariable ["cti_map", createHashMap];
    private _objectives = _map getOrDefault ["objectives", []];
    if (count _objectives isEqualTo 0) exitWith {
        diag_log "CTI|FAIL class=assertion_failed recall_probe_no_map";
    };

    // The ground the recall is to, and the two Places whose Capture would outbid
    // it. Held for the reason the header gives, and named here so the board this
    // probe stages is one list rather than three.
    private _ground = "agia_marina";
    private _board = ["agia_marina", "camp_tempest", "girna"];

    [20] call cti_probe_fnc_worldReady;

    // ------------------------------------------------ what the world is asked about
    // What WEST's own eyes make of the held ground, off the list the daemon is
    // handed: no `reveal`, no ground truth, nothing the engine did not report.
    private _sightedHere = {
        private _report = (call cti_fnc_contactSample) getOrDefault ["WEST", createHashMap];
        private _here = 0;
        {
            if ((_x getOrDefault ["at", ""]) isEqualTo _ground) then { _here = _here + 1 };
        } forEach (_report getOrDefault ["seen", []]);
        _here
    };

    // Every WEST Squad's standing Order as the world holds it, keyed by Squad id.
    private _standingOrders = {
        private _orders = createHashMap;
        {
            private _order = _y getVariable ["cti_order", createHashMap];
            _orders set [_x, [
                _order getOrDefault ["order", ""],
                _order getOrDefault ["place", ""]
            ]];
        } forEach (["WEST"] call cti_probe_fnc_squadsOf);
        _orders
    };

    // The Squads that are marching on purpose, which is what the two assertions
    // are made about.
    private _capturing = {
        private _marching = [];
        {
            if ((_y # 0) isEqualTo "capture") then { _marching pushBack _x };
        } forEach (call _standingOrders);
        _marching
    };

    // Which of those Squads has been given the turn-round, and where its leader
    // is standing when it was.
    private _recalled = {
        params ["_watched"];
        private _turned = [];
        {
            private _order = _y getVariable ["cti_order", createHashMap];
            if (_x in _watched
                && { (_order getOrDefault ["order", ""]) isEqualTo "defend" }
                && { (_order getOrDefault ["place", ""]) isEqualTo _ground }) then {
                _turned pushBack [_x, _y];
            };
        } forEach (["WEST"] call cti_probe_fnc_squadsOf);
        _turned
    };

    // ------------------------------------------------ state the phases share
    private _deadline = 0;
    private _platoonFloor = 0;
    private _companyFloor = 0;
    private _here = createHashMap;
    private _centre = [];
    private _stand = [];
    private _watchers = [];
    private _planted = [];
    private _laid = 0;
    private _nudges = 0;
    private _sighted = 0;
    private _marching = [];

    // One ring of EAST riflemen round the watchers, at the radius given. Told not
    // to path so they stay where they were put, not to shoot and not to die, for
    // `contacts.sqf`'s stated reason: the head count is the band.
    private _layRing = {
        params ["_men", "_radius"];
        private _group = createGroup [east, true];
        private _laidHere = 0;
        for "_i" from 0 to (_men - 1) do {
            private _spot = _stand getPos [_radius, (360 / _men) * _i];
            private _man = _group createUnit
                ["O_Soldier_F", [_spot # 0, _spot # 1, 0], [], 0, "NONE"];
            if (!isNull _man) then {
                _man disableAI "PATH";
                _man setUnitPos "UP";
                _man setDir ((getPosATL _man) getDir _stand);
                _man setCombatMode "BLUE";
                _man allowDamage false;
                _planted pushBack [_man, _radius];
                _laidHere = _laidHere + 1;
            };
        };
        _group setBehaviour "AWARE";
        _group setCombatMode "BLUE";
        _laid = _laid + _laidHere;
        _laidHere
    };

    // Re-lay every planted man on a fresh bearing and a little closer. #28's
    // lesson: a leader that has acquired nothing across a whole window is looking
    // at a building, and re-placing is the fix rather than waiting longer. The
    // offset is arithmetic on the attempt count, never a draw — a bare `random`
    // is out of contract, and a probe that walked a different circle each run
    // would not be re-runnable evidence.
    private _relay = {
        _nudges = _nudges + 1;
        {
            _x params ["_man", "_radius"];
            private _closer = (_radius - (_nudges * 10)) max 50;
            private _spot = _stand getPos
                [_closer, ((360 / (count _planted)) * _forEachIndex) + (_nudges * 17)];
            _man setPosATL [_spot # 0, _spot # 1, 0];
            _man setDir ((getPosATL _man) getDir _stand);
        } forEach _planted;
        diag_log format ["CTI|recall_probe_relaid attempt=%1 men=%2 seen=%3 at=%4",
            _nudges, count _planted, call _sightedHere, time];
    };

    // Wait for WEST's own eyes to reach a band floor, re-laying the ring rather
    // than waiting longer when they do not.
    private _awaitBand = {
        params ["_floor", "_by"];
        private _until = diag_tickTime + _by;
        private _nextRelay = diag_tickTime + 30;
        private _nextLog = 0;
        waitUntil {
            _sighted = call _sightedHere;
            if (_sighted < _floor && { diag_tickTime > _nextRelay }) then {
                _nextRelay = diag_tickTime + 30;
                call _relay;
            };
            if (diag_tickTime > _nextLog) then {
                _nextLog = diag_tickTime + 10;
                diag_log format ["CTI|recall_probe_watching seen=%1 floor=%2 planted=%3 at=%4",
                    _sighted, _floor, _laid, time];
            };
            _sighted >= _floor || { diag_tickTime > _until }
        };
        _sighted >= _floor
    };

    // ------------------------------------------------ the phases
    // Each answers "carry on?", each refuses in its own words and its own class.

    // The two band floors, off the same export the daemon's own catalogue rides
    // (#110, ADR-0017). Read first though they are not used until the ring is
    // laid: a stale export should cost this probe a second rather than six
    // minutes.
    private _readDoctrine = {
        private _echelons = (call cti_fnc_commandSchema) getOrDefault ["echelons", []];
        { if ((_x # 1) isEqualTo "platoon") exitWith { _platoonFloor = _x # 0 } } forEach _echelons;
        { if ((_x # 1) isEqualTo "company") exitWith { _companyFloor = _x # 0 } } forEach _echelons;
        if (_platoonFloor <= 0 || { _companyFloor <= _platoonFloor }) exitWith {
            diag_log format ["CTI|FAIL class=schema_stale recall_probe_schema_without_bands echelons=%1",
                _echelons];
            false
        };
        diag_log format ["CTI|recall_probe_doctrine platoon=%1 company=%2",
            _platoonFloor, _companyFloor];
        true
    };

    // The Commander has to have bought something off its own picture, or there is
    // nothing to turn round. Two rather than one: with a single Squad the board
    // below leaves it a Capture worth more than the turn-round, which is a
    // Commander being right and this probe proving nothing.
    private _awaitCommander = {
        _deadline = diag_tickTime + 60;
        waitUntil {
            count (["WEST"] call cti_probe_fnc_squadsOf) >= 2 || { diag_tickTime > _deadline }
        };
        private _fielded = count (["WEST"] call cti_probe_fnc_squadsOf);
        if (_fielded < 2) exitWith {
            diag_log format ["CTI|FAIL class=timeout recall_probe_commander_fielded_nothing squads=%1 hint=%2",
                _fielded, "is CTI_AI_SIDE=WEST set?"];
            false
        };
        diag_log format ["CTI|recall_probe_commander squads=%1 at=%2", _fielded, time];
        true
    };

    // One man per Objective on the board, one group each, pinned. Three in one
    // group would form up on their leader and walk two of them off the ground
    // they are there to hold. Ownership is then read off `cti_objectiveOwner`,
    // which the server paints from the daemon's own reply — the daemon's
    // ownership rather than a second opinion formed in here.
    private _holdTheBoard = {
        private _put = 0;
        {
            private _place = [_x] call cti_probe_fnc_placeNamed;
            if (count _place isEqualTo 0) exitWith {
                diag_log format ["CTI|FAIL class=assertion_failed recall_probe_no_such_place place=%1", _x];
            };
            (_place get "position") params ["_east", "_north"];
            private _group = createGroup [west, true];
            private _man = _group createUnit ["B_Soldier_F", [_east, _north, 0], [], 0, "NONE"];
            if (!isNull _man) then {
                _man disableAI "PATH";
                _man allowDamage false;
                _put = _put + 1;
            };
        } forEach _board;
        if (_put < count _board) exitWith {
            diag_log format ["CTI|FAIL class=assertion_failed recall_probe_board_staging_failed men=%1 places=%2",
                _put, count _board];
            false
        };

        private _allHeld = {
            private _owners = missionNamespace getVariable ["cti_objectiveOwner", createHashMap];
            private _held = 0;
            { if ((_owners getOrDefault [_x, ""]) isEqualTo "WEST") then { _held = _held + 1 } }
                forEach _board;
            _held isEqualTo (count _board)
        };
        _deadline = diag_tickTime + 75;
        waitUntil { call _allHeld || { diag_tickTime > _deadline } };
        if !(call _allHeld) exitWith {
            diag_log format ["CTI|FAIL class=timeout recall_probe_board_never_held owners=%1",
                missionNamespace getVariable ["cti_objectiveOwner", createHashMap]];
            false
        };
        diag_log format ["CTI|recall_probe_board_held places=%1 at=%2", _board, time];
        true
    };

    // Where everything below stands: 400 m off the held Objective on the line
    // towards the Place the manifest calls adjacent to it. Authored ground rather
    // than a bearing off somebody's facing — #28's lesson — and far enough out
    // that the watchers are in open ground and the ring is outside the capture
    // radius, which is what keeps the ground WEST's while the men are seen at it.
    private _layTheGround = {
        _here = [_ground] call cti_probe_fnc_placeNamed;
        private _towards = [(_here getOrDefault ["adjacent", [""]]) # 0] call cti_probe_fnc_placeNamed;
        if (count _here isEqualTo 0 || { count _towards isEqualTo 0 }) exitWith {
            diag_log "CTI|FAIL class=assertion_failed recall_probe_no_adjacent_place";
            false
        };
        (_here get "position") params ["_east", "_north"];
        _centre = [_east, _north, 0];
        (_towards get "position") params ["_thatEast", "_thatNorth"];
        ([_centre, [_thatEast, _thatNorth, 0], 400] call cti_probe_fnc_approach) params ["_at"];
        _stand = [_at # 0, _at # 1, 0];
        diag_log format ["CTI|recall_probe_ground place=%1 towards=%2 stand=%3 range=%4",
            _ground, _towards get "id", mapGridPosition _stand, _stand distance2D _centre];
        true
    };

    // WEST's Squads, put where they can see the ground they hold and held there.
    // Spread round the standing point facing outwards, because the engine shares
    // a sighting instantly inside a group and the leader is what the sampler
    // asks: eight men looking eight ways is the coverage, not the leader's own
    // arc. Pinned, silenced and unkillable for the same reason the ring is —
    // what is asserted is the Order they are given, and a firefight underneath
    // an assertion about a band is what cost `massed-assault` three runs.
    private _stageWatchers = {
        _watchers = [];
        {
            private _squad = _x;
            private _group = _y;
            {
                private _spot = _stand getPos [15, (360 / 8) * _forEachIndex];
                _x setPosATL [_spot # 0, _spot # 1, 0];
                _x setDir (_stand getDir (getPosATL _x));
                _x disableAI "PATH";
                _x setUnitPos "UP";
                _x setCombatMode "BLUE";
                _x allowDamage false;
            } forEach units _group;
            _group setBehaviour "AWARE";
            _watchers pushBack _squad;
        } forEach (["WEST"] call cti_probe_fnc_squadsOf);
        if (count _watchers isEqualTo 0) exitWith {
            diag_log "CTI|FAIL class=assertion_failed recall_probe_no_watchers";
            false
        };
        diag_log format ["CTI|recall_probe_watchers squads=%1 at=%2 orders=%3",
            _watchers, mapGridPosition _stand, call _standingOrders];
        true
    };

    // The platoon. Twenty-four men, so the band cannot reach a company however
    // well WEST sees: the negative below is only worth making if the thing it
    // says did not happen could not have been a company all along.
    private _stagePlatoon = {
        private _men = [24, 80] call _layRing;
        if (_men < 24) exitWith {
            diag_log format ["CTI|FAIL class=assertion_failed recall_probe_ring_failed men=%1", _men];
            false
        };
        if !([_platoonFloor, 90] call _awaitBand) exitWith {
            diag_log format ["CTI|FAIL class=timeout recall_probe_never_acquired_platoon seen=%1 floor=%2 planted=%3 relaid=%4",
                _sighted, _platoonFloor, _laid, _nudges];
            false
        };
        diag_log format ["CTI|recall_probe_platoon_band seen=%1 of=%2 floor=%3 at=%4",
            _sighted, _laid, _platoonFloor, time];
        true
    };

    // The negative, and the reason the whole staging is worth doing: the relation
    // ADR-0020 pinned and ADR-0031 kept — a Commander that turns round for every
    // sighting is the one ADR-0014 rejected.
    private _watchNoRecall = {
        _marching = call _capturing;
        if (count _marching isEqualTo 0) exitWith {
            diag_log format ["CTI|FAIL class=assertion_failed recall_probe_nothing_was_marching orders=%1",
                call _standingOrders];
            false
        };
        // Forty-five *continuous* seconds of a platoon being ignored. A sighting
        // list is a live reading and a man can drop off it for a moment, so a dip
        // below the floor restarts the clock rather than failing: the claim is
        // about a band that was there, and a run that never holds one for 45 s
        // has not staged the band rather than found the Commander out.
        private _turned = [];
        private _restarts = 0;
        private _until = diag_tickTime + 45;
        private _giveUp = diag_tickTime + 150;
        waitUntil {
            _turned = [_marching] call _recalled;
            _sighted = call _sightedHere;
            if (_sighted < _platoonFloor) then {
                _until = diag_tickTime + 45;
                _restarts = _restarts + 1;
            };
            count _turned > 0 || { diag_tickTime > _until } || { diag_tickTime > _giveUp }
        };
        if (count _turned > 0) exitWith {
            diag_log format ["CTI|FAIL class=assertion_failed recall_probe_platoon_recalled squad=%1 seen=%2 floor=%3 at=%4",
                (_turned # 0) # 0, _sighted, _platoonFloor, time];
            false
        };
        if (diag_tickTime > _until) then {
            diag_log format ["CTI|recall_probe_platoon_ignored squads=%1 seen=%2 held_for=%3 restarts=%4 at=%5",
                _marching, _sighted, 45, _restarts, time];
        } else {
            diag_log format ["CTI|FAIL class=timeout recall_probe_platoon_band_never_steady seen=%1 floor=%2 restarts=%3 planted=%4",
                _sighted, _platoonFloor, _restarts, _laid];
        };
        diag_tickTime > _until
    };

    // The company. Forty more men on a wider ring, which is what takes the band
    // over its floor without moving anything the negative was made of.
    private _stageCompany = {
        private _men = [40, 110] call _layRing;
        if (_men < 40) exitWith {
            diag_log format ["CTI|FAIL class=assertion_failed recall_probe_second_ring_failed men=%1", _men];
            false
        };
        if !([_companyFloor, 120] call _awaitBand) exitWith {
            diag_log format ["CTI|FAIL class=timeout recall_probe_never_acquired_company seen=%1 floor=%2 planted=%3 relaid=%4",
                _sighted, _companyFloor, _laid, _nudges];
            false
        };
        diag_log format ["CTI|recall_probe_company_band seen=%1 of=%2 floor=%3 at=%4",
            _sighted, _laid, _companyFloor, time];
        true
    };

    // The claim. One of the Squads that was marching when the band arrived is
    // given the turn-round, and it is given it while standing off the ground —
    // a Squad recalled, rather than a Squad that was already there.
    private _awaitRecall = {
        _marching = call _capturing;
        if (count _marching isEqualTo 0) exitWith {
            diag_log format ["CTI|FAIL class=assertion_failed recall_probe_nothing_left_marching orders=%1",
                call _standingOrders];
            false
        };
        private _before = call _standingOrders;
        private _turned = [];
        _deadline = diag_tickTime + 60;
        waitUntil {
            _turned = [_marching] call _recalled;
            count _turned > 0 || { diag_tickTime > _deadline }
        };
        if (count _turned isEqualTo 0) exitWith {
            diag_log format ["CTI|FAIL class=assertion_failed recall_probe_company_ignored marching=%1 seen=%2 orders=%3 at=%4",
                _marching, _sighted, call _standingOrders, time];
            false
        };

        (_turned # 0) params ["_squad", "_group"];
        private _range = (leader _group) distance2D _centre;
        private _radius = [_here] call cti_fnc_placeRadius;
        if (_range <= _radius) exitWith {
            // Inside the capture radius it is a garrison holding its ground,
            // which is true and is not this claim. The staging put it 400 m out,
            // so this is the staging having drifted rather than a finding.
            diag_log format ["CTI|FAIL class=assertion_failed recall_probe_recalled_from_the_ground_itself squad=%1 range=%2 radius=%3",
                _squad, _range, _radius];
            false
        };

        diag_log format ["CTI|recall_probe_recalled squad=%1 was=%2 now=defend %3 range=%4 seen=%5 squads=%6 at=%7",
            _squad, _before getOrDefault [_squad, ["", ""]], _ground, _range, _sighted,
            count (["WEST"] call cti_probe_fnc_squadsOf), time];
        true
    };

    // ------------------------------------------------ run them
    // Each phase has already logged its own FAIL and its own class; this only
    // says where the probe stopped, so the evidence names the phase as well as
    // the assertion.
    private _stopped = "";
    {
        _x params ["_name", "_phase"];
        if !(call _phase) exitWith { _stopped = _name };
    } forEach [
        ["doctrine", _readDoctrine],
        ["commander", _awaitCommander],
        ["board", _holdTheBoard],
        ["ground", _layTheGround],
        ["watchers", _stageWatchers],
        ["platoon", _stagePlatoon],
        ["no_recall", _watchNoRecall],
        ["company", _stageCompany],
        ["recall", _awaitRecall]
    ];
    if (_stopped isNotEqualTo "") exitWith {
        diag_log format ["CTI|recall_probe_stopped phase=%1 at=%2", _stopped, time];
    };

    diag_log "CTI|recall_probe_done";
};
