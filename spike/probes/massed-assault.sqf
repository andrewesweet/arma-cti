// probe: massed-assault
// issues: 38, 110
// window: 480
// env: CTI_HOLD_HC=1 CTI_AI_SIDE=WEST,EAST CTI_AI_SEED=1,4
//
// #38 in-world probe: a Commander that finds a Base defended sends a force at
// it, not a Squad.
//
// `just regress massed-assault` reads the block above. By hand:
//   CTI_HOLD_HC=1 CTI_AI_SIDE=WEST,EAST CTI_AI_SEED=1,4 \
//       just probe spike/probes/massed-assault.sqf 480
//
// ADR-0027 is the rule. The unit tier feeds the planner a Contact it wrote
// itself; what only the world can show is the loop — real men standing on a real
// Base, acquired by a real leader through the engine's own knowledge model,
// banded by the sampler, carried to the daemon as a Contact with an age on it,
// read as a demand for force, and answered with Orders for several Squads at one
// Place crossing the real port. Nothing in that chain is mocked here, and none
// of it is asked for.
//
// ---- what is engineered, and what is not
//
// Three things, all about *position*, none about a rule — the same licence
// `campaign-end` and `base-assault` take.
//
//   1. The island. One WEST rifleman inside each Objective's capture radius, so
//      the Campaign reaches the state where a Commander plays for the enemy HQ.
//      The daemon still has to read them standing there.
//   2. The garrison. Eight EAST riflemen spawned on their own Base *after*
//      EAST's own Squads have marched out of it, laid in a line across the
//      approach 25 m out and standing. They are what makes this Base defended
//      rather than empty. They are not Squads, report to nobody, and are seen
//      only if WEST's men actually see them. Eight rather than a round company
//      because the band and the strength have to agree: a line of twelve that a
//      leader can see all of is a defence the band cannot describe, and it cost
//      a run. They are held still, told not to shoot and made unkillable, which
//      is `contacts.sqf`'s licence taken for `contacts.sqf`'s reason.
//   3. The march, twice. The two Bases are 4.4 km apart — forty minutes of
//      engine walking, and nothing this probe measures. Squads under the Assault
//      are put 100 m out on the line between the HQ and the Objective the
//      manifest calls adjacent to that Base, abreast across the approach.
//
// Not engineered: the Contact, the count, or the decision. Nobody tells the
// daemon there is a garrison — WEST's leader has to acquire it. Nobody tells the
// planner how many Squads to send. What this probe waits on is the **picture**:
// it reads the same sighting list the daemon bands (`cti_fnc_contactSample`),
// and only once WEST has acquired enough for a band above a team does it require
// the Orders to name more than one Squad, and no more than the table's ceiling.
//
// The three numbers that bounds each side of come from the daemon's own tables,
// read through `cti_fnc_commandSchema` (#110): the sighting floor of the `squad`
// band, that band's entry in `ASSAULT_MASS`, and the heaviest entry in it. They
// used to be written out in SQF under a comment saying there was no path from a
// Python table into a mission; there is, this project built it, and a retuned
// table now changes what the probe means rather than silently not changing it.
//
// ---- where this probe stops, and why
//
// It stops at the decision, and the garrison does not fight. Both of those are
// one choice, made against measurements rather than for convenience: whether a
// mass wins a firefight is a coin toss the engine tosses, and the same staging
// both won and lost it on 2026-08-01. A probe gating on which way that landed
// would be a flake generator, and a fighting garrison puts a dying observer and
// a moving head count underneath an assertion about a band — one run lost the
// staged Squad before the sampler's next tick and no Contact formed at all. That
// an Assault can raze an HQ is `base-assault`'s claim and a Campaign ending on
// one is `campaign-end`'s, both green in this corpus.
//
// The seven runs this probe's shape was found in, and the finding that came out
// of them — WEST saw four of twelve, brought a `squad` band's mass at a
// platoon's worth of men and lost, which is the price of #28 under-counting on
// purpose and not a bug in either — are written up in #38 and worked through in
// docs/regression-tier.md rather than kept here.
//
// ---- what would make this red, and what each red would mean
//
// Nobody acquired anything: the geometry is wrong, and the fix is geometry. One
// Squad against a band above a team, or more than the table's ceiling: the
// threat model is broken, which is this probe's whole point. Assault called off
// with a force of eight: the decline branch firing where it should not. The mass
// falling below its size a minute later: it massed and thrashed, which is
// `commitment` failing to hold what the threat model built.
//
// ---- the window
//
// Added up rather than guessed at: ~20 s for the world to settle, ~25 s for both
// Commanders to buy through the outbox, ~35 s for the staged island to fall and
// the next plan to land, ~20 s for the first Assault to be decided, ~200 s for
// EAST's own Squads to walk clear of their own Base (measured on #35), ~30 s for
// the engine to acquire eight men a hundred metres in front of the staged Squad
// (two seconds, measured, with room for a far worse draw), ~30 s for that to
// become a Contact, cross to the daemon and come back as Orders, and 60 s of
// watching the mass stay massed. About 420 s of subject; 480 is that plus the
// engine's pathfinding around an airfield. If this ever needs *more*, the answer
// is not a bigger number: it is that acquisition or the mass is not arriving,
// and the evidence lines say which.
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

    // Places by id off the index `cti_fnc_worldInit` derives beside `cti_map`
    // (#109), rather than the linear scan this and two other probes each carried
    // a copy of.
    private _target = ["csat_kamino"] call cti_probe_fnc_placeNamed;
    private _hq = missionNamespace getVariable [_target getOrDefault ["hq", ""], objNull];
    if (isNull _hq) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed mass_probe_no_hq name=%1",
            _target getOrDefault ["hq", ""]];
    };
    private _hqAt = getPosATL _hq;

    // ------------------------------------------------ what the world is asked about
    // Squads under the Assault this probe is watching, by id.
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

    // What WEST's own eyes make of this Base, off the list the daemon is handed:
    // no `reveal`, no ground truth, nothing the engine did not report.
    private _sightedAtBase = {
        private _report = (call cti_fnc_contactSample) getOrDefault ["WEST", createHashMap];
        private _here = 0;
        {
            if ((_x getOrDefault ["at", ""]) isEqualTo "csat_kamino") then { _here = _here + 1 };
        } forEach (_report getOrDefault ["seen", []]);
        _here
    };

    // Living EAST infantry anywhere near the Base.
    private _eastMen = {
        private _men = 0;
        {
            if (alive _x && { side group _x isEqualTo east }) then { _men = _men + 1 };
        } forEach (_hqAt nearEntities ["CAManBase", 400]);
        _men
    };

    // ------------------------------------------------ state the phases share
    private _deadline = 0;
    private _headless = 0;
    private _staged = 0;
    private _first = [];
    private _adjacent = createHashMap;
    private _approach = [];
    private _dir = 0;
    private _garrison = grpNull;
    private _defenders = 0;
    private _staffed = [];
    private _sighted = 0;
    private _bandFloor = 0;
    private _wanted = 0;
    private _ceiling = 0;
    private _mass = [];

    // Everything below goes on the one vector from the HQ towards the adjacent
    // Objective, so the garrison faces the way the attack comes and the attack
    // comes the way the garrison faces. `_dir - 90` is the perpendicular the
    // hand-rolled `[-y, x]` unit vector used to spell out; the offsets are all
    // non-negative, so the line is laid from one end rather than from the middle.
    private _putOnApproach = {
        params ["_squads", "_lane"];
        private _placed = [];
        {
            _x params ["_id", "_group"];
            // Abreast across the approach rather than strung out along it, so
            // every Squad has the same view of the Base and the same walk in.
            {
                private _spot = _approach getPos [(_lane * 40) + (_forEachIndex * 4), _dir - 90];
                _x setPosATL [_spot # 0, _spot # 1, 0];
            } forEach units _group;
            _placed pushBack _id;
            _lane = _lane + 1;
        } forEach _squads;
        _placed
    };

    // ------------------------------------------------ the phases
    // Ten of them, in order, each answering "carry on?". They used to be one
    // 380-line anonymous body (#86); naming them is the whole change, and each
    // still refuses in its own words and its own class.

    // The MVP test topology is a dedicated server plus a headless client. A run
    // without one is a different run, so it is refused rather than passed.
    private _awaitTopology = {
        _headless = [120] call cti_probe_fnc_headlessClients;
        if (_headless isEqualTo 0) exitWith {
            diag_log format ["CTI|FAIL class=infra_unavailable mass_probe_no_headless_client users=%1 hint=%2",
                count allUsers, "is CTI_HOLD_HC=1 set?"];
            false
        };
        true
    };

    // Both sides bought something off their own picture, or a Campaign could be
    // played against a side nobody was playing.
    private _awaitBothCommanders = {
        _deadline = diag_tickTime + 120;
        waitUntil {
            (count (["WEST"] call cti_probe_fnc_squadsOf) > 0
                && { count (["EAST"] call cti_probe_fnc_squadsOf) > 0 })
                || { diag_tickTime > _deadline }
        };
        private _west = count (["WEST"] call cti_probe_fnc_squadsOf);
        private _east = count (["EAST"] call cti_probe_fnc_squadsOf);
        if (_west isEqualTo 0 || { _east isEqualTo 0 }) exitWith {
            diag_log format ["CTI|FAIL class=timeout mass_probe_side_fielded_nothing west=%1 east=%2 hint=%3",
                _west, _east, "is CTI_AI_SIDE=WEST,EAST set?"];
            false
        };
        diag_log format ["CTI|mass_probe_commanders west=%1 east=%2 at=%3", _west, _east, time];
        true
    };

    // One man per Objective, one group each, pinned. Eight in one group would
    // form up on their leader and walk off seven of them. Ownership is then read
    // off the markers, which are painted from the daemon's own reply — the
    // daemon's ownership rather than a second opinion formed in here.
    private _stageIsland = {
        _staged = 0;
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
            false
        };

        private _allWest = {
            private _held = 0;
            { if (_y isEqualTo "WEST") then { _held = _held + 1 } }
                forEach (missionNamespace getVariable ["cti_objectiveOwner", createHashMap]);
            _held isEqualTo (count _objectives)
        };
        _deadline = diag_tickTime + 180;
        waitUntil { call _allWest || { diag_tickTime > _deadline } };
        if !(call _allWest) exitWith {
            diag_log format ["CTI|FAIL class=timeout mass_probe_island_never_fell owners=%1",
                missionNamespace getVariable ["cti_objectiveOwner", createHashMap]];
            false
        };
        diag_log format ["CTI|mass_probe_island_held men=%1 at=%2", _staged, time];
        true
    };

    // Not this probe's part: with no ground left worth taking, WEST should reach
    // for the other win condition on its own. Waited for, refused if it never
    // comes — an Assault this probe had to ask for would prove nothing.
    private _awaitFirstAssault = {
        _deadline = diag_tickTime + 120;
        waitUntil { count (call _raiders) > 0 || { diag_tickTime > _deadline } };
        _first = call _raiders;
        if (count _first isEqualTo 0) exitWith {
            diag_log format ["CTI|FAIL class=timeout mass_probe_commander_never_assaulted squads=%1",
                count (missionNamespace getVariable ["cti_squads", createHashMap])];
            false
        };
        diag_log format ["CTI|mass_probe_assault_ordered squads=%1 at=%2",
            _first apply { _x # 0 }, time];
        true
    };

    // The garrison below is staged, and staging it under EAST's own Squads would
    // make the picture theirs rather than the probe's — #35 measured what a Squad
    // put on the approach before they had gone runs into. Waited on as the ground
    // being clear, then proceeded either way: whether EAST's Commander leaves a
    // rear guard is its own business, and a run where it left two men behind is a
    // Campaign being played rather than a probe fault. What it must not do is put
    // a firefight under an assertion about a band, so whatever is still standing
    // is silenced and made unkillable alongside the garrison — one rule for
    // everything at this Base, and the rule is that it is there to be *seen*.
    private _clearTheBase = {
        _deadline = diag_tickTime + 300;
        waitUntil { call _eastMen isEqualTo 0 || { diag_tickTime > _deadline } };
        private _leftBehind = call _eastMen;
        {
            if (side group _x isEqualTo east) then {
                _x setCombatMode "BLUE";
                _x allowDamage false;
            };
        } forEach (_hqAt nearEntities ["CAManBase", 400]);
        diag_log format ["CTI|mass_probe_base_clear left_behind=%1 at=%2", _leftBehind, time];
        true
    };

    // The line between the HQ and the Objective the manifest calls adjacent to
    // this Base. Authored ground rather than a bearing off somebody's facing —
    // #28's lesson, which cost two probes. 100 m rather than 250 is the range
    // `contacts.sqf` measured as reliable where 150 was flaky.
    private _layApproach = {
        _adjacent = [(_target getOrDefault ["adjacent", [""]]) # 0] call cti_probe_fnc_placeNamed;
        if (count _adjacent isEqualTo 0) exitWith {
            diag_log "CTI|FAIL class=assertion_failed mass_probe_no_adjacent_place";
            false
        };
        // The run/span/normalise/perpendicular block this used to be is two
        // engine commands the wiki ships (#108, #86): see
        // `cti_probe_fnc_approach`.
        ([_hqAt, _adjacent get "position", 100] call cti_probe_fnc_approach)
            params ["_at", "_bearing"];
        _approach = _at;
        _dir = _bearing;
        true
    };

    // Eight men on their own Base, told not to path so they stay on it, laid in
    // a line across the approach on the attack's side of the HQ and standing.
    // The first cut put them in a ring around it and half of them spent the run
    // behind the building — #28's hangar, with the HQ as the hangar. A garrison
    // facing the way the enemy comes is also what a garrison is, so this is the
    // geometry being honest rather than being helpful.
    //
    // Held still, told not to shoot, and unable to die, for `contacts.sqf`'s
    // stated reason: here the head count *is* the band, and the band is what the
    // mass is read from.
    private _stageGarrison = {
        _garrison = createGroup [east, true];
        _defenders = 0;
        // Laid from the left end of the line rather than from its middle, so
        // every step along it is a positive distance on a bearing.
        private _lineFrom = (_hqAt getPos [25, _dir]) getPos [21, _dir + 90];
        for "_i" from 0 to 7 do {
            private _spot = _lineFrom getPos [_i * 6, _dir - 90];
            private _man = _garrison createUnit
                ["O_Soldier_F", [_spot # 0, _spot # 1, 0], [], 0, "NONE"];
            if (!isNull _man) then {
                _man disableAI "PATH";
                _man setUnitPos "UP";
                _man setDir _dir;
                _man setCombatMode "BLUE";
                _man allowDamage false;
                _defenders = _defenders + 1;
            };
        };
        if (_defenders isEqualTo 0) exitWith {
            diag_log "CTI|FAIL class=assertion_failed mass_probe_garrison_failed";
            false
        };
        _garrison setBehaviour "AWARE";
        _garrison setCombatMode "BLUE";
        diag_log format ["CTI|mass_probe_garrison men=%1 at=%2 grid=%3",
            _defenders, time, mapGridPosition _hqAt];

        _staffed = [_first, 0] call _putOnApproach;
        diag_log format ["CTI|mass_probe_staged_march squads=%1 at=%2 from=%3 grid=%4",
            _staffed, time, _adjacent get "id", mapGridPosition _approach];
        true
    };

    // The doctrine tables, off the same export the daemon's own catalogue rides
    // (#110, ADR-0017). The floor of the `squad` band is the first sighting count
    // that wants more than one Squad; that band's `ASSAULT_MASS` entry is how
    // many it wants; the table's heaviest entry is the most any band could ask
    // for. All three used to be written out in SQF.
    private _readDoctrine = {
        private _schema = call cti_fnc_commandSchema;
        private _echelons = _schema getOrDefault ["echelons", []];
        private _assaultMass = _schema getOrDefault ["assault_mass", createHashMap];
        { if ((_x # 1) isEqualTo "squad") exitWith { _bandFloor = _x # 0 } } forEach _echelons;
        _wanted = _assaultMass getOrDefault ["squad", 0];
        _ceiling = 0;
        if (count _assaultMass > 0) then { _ceiling = selectMax (values _assaultMass) };
        if (_bandFloor <= 0 || { _wanted <= 0 } || { _ceiling <= 0 }) exitWith {
            diag_log format ["CTI|FAIL class=schema_stale mass_probe_schema_without_doctrine echelons=%1 assault_mass=%2",
                _echelons, _assaultMass];
            false
        };
        diag_log format ["CTI|mass_probe_doctrine band_floor=%1 wanted=%2 ceiling=%3",
            _bandFloor, _wanted, _ceiling];
        true
    };

    // The world's part, waited for on the sampler's own answer rather than
    // assumed, and waited on until it is worth asserting about: the `squad`
    // band's floor is the first band that wants more than one Squad. Below that
    // the Commander correctly sends one, which is true and proves nothing, so the
    // probe would rather say the geometry failed.
    private _awaitAcquisition = {
        _deadline = diag_tickTime + 300;
        _sighted = 0;
        waitUntil {
            _sighted = call _sightedAtBase;
            _sighted >= _bandFloor || { diag_tickTime > _deadline }
        };
        if (_sighted < _bandFloor) exitWith {
            diag_log format ["CTI|FAIL class=timeout mass_probe_never_acquired seen=%1 of=%2 floor=%3 range=%4 at=%5",
                _sighted, _defenders, _bandFloor,
                (leader ((_first # 0) # 1)) distance2D _hqAt, time];
            false
        };
        diag_log format ["CTI|mass_probe_acquired seen=%1 of=%2 wanted=%3 at=%4",
            _sighted, _defenders, _wanted, time];
        true
    };

    // The criterion. Whatever band WEST's own eyes produced, it is a band above a
    // team, and a band above a team is more than one Squad. Nothing here asks for
    // it.
    //
    // Asserted as a range rather than an equality, and the reason is the clock:
    // this reads the sampler at one instant and the daemon banded its own sample
    // up to a report interval earlier, so a count sitting on a band boundary
    // would make an exact match a coin toss. The exact band-to-mass relation is
    // the unit tier's claim, on 200 seeds.
    private _awaitMass = {
        _deadline = diag_tickTime + 120;
        _mass = _first;
        waitUntil {
            _mass = call _raiders;
            count _mass >= _wanted || { count _mass isEqualTo 0 } || { diag_tickTime > _deadline }
        };
        if (count _mass isEqualTo 0) exitWith {
            // The decline branch, fired where it should not: eight Squads is
            // more than this garrison's band can want. Correct behaviour on a
            // force too small to mass, wrong here, and the trace's
            // `assault csat_kamino` row says which band it read.
            diag_log format ["CTI|FAIL class=assertion_failed mass_probe_assault_called_off squads=%1 seen=%2 at=%3",
                count (["WEST"] call cti_probe_fnc_squadsOf), _sighted, time];
            false
        };
        if (count _mass < _wanted) exitWith {
            diag_log format ["CTI|FAIL class=assertion_failed mass_probe_under_massed sent=%1 wanted=%2 seen=%3 at=%4",
                count _mass, _wanted, _sighted, time];
            false
        };
        if (count _mass > _ceiling) exitWith {
            // Above the table's heaviest entry there is nothing a band could
            // have asked for, so this is the detail rule taking Squads it was
            // not owed.
            diag_log format ["CTI|FAIL class=assertion_failed mass_probe_over_massed sent=%1 ceiling=%2 seen=%3 at=%4",
                count _mass, _ceiling, _sighted, time];
            false
        };
        diag_log format ["CTI|mass_probe_massed squads=%1 sent=%2 seen=%3 at=%4",
            _mass apply { _x # 0 }, count _mass, _sighted, time];

        // Everything the Commander added goes on the same line, for the same
        // declared reason as the first: the 4.4 km is not what is being measured.
        private _reinforcements = _mass select { !((_x # 0) in _staffed) };
        private _brought = [_reinforcements, 1] call _putOnApproach;
        diag_log format ["CTI|mass_probe_staged_reinforcements squads=%1 at=%2", _brought, time];
        true
    };

    // The last assertion, and deliberately not the fight. What has to hold is
    // that the mass is an Order and not a flicker: the Base stays named by a
    // force for as long as the force is closing with it, rather than being
    // unpicked by the next plan. A threat model that massed and then thrashed
    // would be worse than one that never massed.
    //
    // The **strength** is what is watched, not the membership, and that is a
    // correction this probe earned: a first cut required the same Squads and went
    // red when one was swapped for another. The swap was the planner being right
    // about a picture this probe had made — teleporting a Squad onto the approach
    // puts it in open ground, where it is measured from its own Base 4.4 km away,
    // so a Squad still standing on the Objective next door is genuinely the
    // cheaper trip. Staging cannot both shorten a march and expect the scorer not
    // to notice.
    private _watchTheMass = {
        private _steady = diag_tickTime + 60;
        private _held = _wanted;
        waitUntil {
            _held = _held min (count (call _raiders));
            _held < _wanted || { diag_tickTime > _steady }
        };
        if (_held < _wanted) exitWith {
            diag_log format ["CTI|FAIL class=assertion_failed mass_probe_mass_unpicked held=%1 wanted=%2 at=%3",
                _held, _wanted, time];
            false
        };
        _mass = call _raiders;

        // The state the mass was left in, as evidence rather than as a verdict —
        // where the force is, how much of it there is, and what it is looking at.
        // The garrison cannot die here, so a damaged HQ or a thinned defence
        // would both be surprises worth seeing in the log rather than assertions.
        private _attackers = 0;
        { _attackers = _attackers + ({ alive _x } count units (_x # 1)) } forEach _mass;
        diag_log format ["CTI|mass_probe_prosecuting sent=%1 attackers=%2 defenders=%3 damage=%4 range=%5 at=%6",
            count _mass, _attackers, { alive _x } count units _garrison, damage _hq,
            (leader ((_mass # 0) # 1)) distance2D _hqAt, time];
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
        // Doctrine first, though it is not read until acquisition: it is a read
        // of a gated generated file, and a stale one should cost this probe a
        // second rather than eight minutes.
        ["topology", _awaitTopology],
        ["doctrine", _readDoctrine],
        ["both_commanders", _awaitBothCommanders],
        ["island", _stageIsland],
        ["first_assault", _awaitFirstAssault],
        ["base_clear", _clearTheBase],
        ["approach", _layApproach],
        ["garrison", _stageGarrison],
        ["acquisition", _awaitAcquisition],
        ["mass", _awaitMass],
        ["commitment", _watchTheMass]
    ];
    if (_stopped isNotEqualTo "") exitWith {
        diag_log format ["CTI|mass_probe_stopped phase=%1 at=%2", _stopped, time];
    };

    diag_log "CTI|mass_probe_done";
};
