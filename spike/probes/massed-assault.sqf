// probe: massed-assault
// issues: 38
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
//      them. They are also held still and told not to shoot, which is
//      `contacts.sqf`'s licence taken for `contacts.sqf`'s reason and is the
//      subject of the last section below.
//   3. The march, twice. The two Bases are 4.4 km apart — forty minutes of
//      engine walking, and nothing this probe measures. The first Squad the
//      Commander orders to Assault is put 100 m out on the line between the HQ
//      and the Objective the manifest calls adjacent to that Base, and the
//      Squads the Commander then adds go on the same line when it adds them.
//
// Not engineered: the Contact, the count, or the decision. Nobody tells the
// daemon there is a garrison — WEST's leader has to acquire it. Nobody tells the
// planner how many Squads to send. What this probe waits on is the **picture**:
// it reads the same sighting list the daemon bands (`cti_fnc_contactSample`),
// and only once WEST has acquired enough for a band above a team does it require
// the Orders to name more than one Squad, and no more than the table's ceiling.
// The exact band-to-mass relation is the unit tier's claim on 200 seeds, and the
// reason it is not asserted here is stated where it is computed.
//
// ---- the first cut asserted a number, and the world does not owe it one
//
// It ran twice on 2026-08-01 and the two runs disagreed with the same setup:
// PASS in 341 s with the Contact banded `platoon` and three Squads sent, then
// `timeout ... sent=1 wanted=2` at 430 s with the same twelve men staged in the
// same place and the Contact banded `team`. The planner was right both times —
// it sent one Squad for a team and three for a platoon, which is the rule. What
// was wrong was the probe: it required at least two Squads, which is a claim
// about how many of twelve men one leader happens to acquire, and that is the
// engine's business. `spike/probes/contacts.sqf` records the same lesson from
// #28 ("six men found in seconds on two runs and not at all within 90 s on two
// others") and the same remedy — geometry, never a longer wait.
//
// So three things changed, none of them the deadline's job:
//
//   - The garrison is on the **approach side** of the HQ, spread across the line
//     the attack comes down and standing rather than at the engine's default
//     stance. Twelve men in a ring at 15 m put half of them behind the building,
//     which is #28's "lands behind a hangar often enough to matter" with the
//     hangar being the HQ itself.
//   - The stage point is **100 m**, not 250 m, which is the range
//     `contacts.sqf` measured as reliable where 150 m was flaky.
//   - **Acquisition is waited for explicitly**, on the sampler's own answer,
//     before anything is asserted about Orders. That is the world's part of the
//     subject, and the first cut budgeted twenty seconds for something the
//     second run showed taking minutes.
//
// That fixed it, measurably: the third run acquired four men **eleven seconds**
// after staging and the Commander massed four seconds later, against minutes of
// crawling at 250 m. It also cost that run the fight — sixteen men walked at a
// facing, alerted line of twelve across open ground and all sixteen died without
// taking one. Two things came out of that, and only the second is this probe's:
//
//   - **A finding for the sign-off in #38**, recorded rather than tuned away:
//     WEST saw four of the twelve, so it brought a `squad` band's mass at a
//     platoon's worth of men and lost. `ASSAULT_MASS` is a doctrine table over
//     *observed* strength, and #28 under-counts on purpose — this is the price
//     of that, in men, and it is not a bug in either.
//   - **The garrison is eight**, not twelve, and the approach is 100 m rather
//     than 150. A line of twelve that a leader can see all of is a defence the
//     band cannot describe, and a hundred and fifty metres of open airfield in
//     front of it decides the fight before the mass is relevant. Eight is a
//     garrison whose band and whose strength agree, which is what makes the
//     Assault's outcome about the mass rather than about the walk.
//
// ---- where this probe stops, and why
//
// It stops at the decision, and the garrison does not fight. Both of those are
// one choice, made against measurements rather than for convenience.
//
// Whether a mass wins a firefight is a coin toss the engine tosses. The same
// staging on 2026-08-01 won it — five of eight defenders down, the HQ 39% gone —
// and lost it, all sixteen attackers dead and the garrison untouched. A probe
// that gated on which way that landed would be a flake generator, and this tier
// does not average two runs into a pass. The run after those two showed the
// second cost: the lone staged Squad was killed before the sampler's next tick,
// so no Contact formed at all and the *decision* could not be observed either.
// A fighting garrison puts a dying observer and a moving head count underneath
// an assertion about a band.
//
// So the garrison is `contacts.sqf`'s planted enemy — visible, still, and
// neither shooting nor dying — and what is asserted is the loop that only the
// world can show: real men on a real Base, acquired by a real leader through the
// engine's own knowledge model, banded by the real sampler, read as a demand for
// force by the real planner, answered with Orders for several Squads across the
// real port. That an Assault can raze an HQ is `base-assault`'s claim and a
// Campaign ending on one is `campaign-end`'s, both green in this corpus, and
// neither needs saying twice.
//
// The coin toss is itself worth reading before ADR-0027's numbers are signed
// off, and it is written up in #38 rather than tuned away: at
// `ASSAULT_MASS["squad"] = 2`, sixteen men against a squad-banded Base is not a
// force that reliably takes it.
//
// ---- what would make this red, and what each red would mean
//
// Nobody acquired anything: the geometry above is wrong again, and the fix is
// geometry again. One Squad against a band above a team, or more than the
// table's ceiling: the threat model is broken, which is this probe's whole
// point. Assault called off with a force of eight: the decline branch firing
// where it should not. The mass falling below its size a minute later: it massed
// and thrashed, which is `commitment` failing to hold what the threat model
// built.
//
// ---- the window
//
// Added up rather than guessed at, and *smaller* than the first cut's 780,
// because the subject shrank when the fight came out of it: ~20 s for the world
// to settle, ~25 s for both Commanders to buy through the outbox, ~35 s for the
// staged island to fall and the next plan to land, ~20 s for the first Assault
// to be decided, ~200 s for EAST's own Squads to walk clear of their own Base
// (measured on #35), ~30 s for the engine to acquire eight men a hundred metres
// in front of the staged Squad (two seconds, measured, with room for a far worse
// draw), ~30 s for that to become a Contact, cross to the daemon and come back
// as Orders, and 60 s of watching the mass stay massed. About 420 s of subject;
// 480 is that plus the engine's pathfinding around an airfield. If this ever
// needs *more*, the answer is not a bigger number: it is that acquisition or the
// mass is not arriving, and the evidence lines say which.
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
    // make the picture theirs rather than the probe's. #35 measured what a Squad
    // put on the approach before they had gone runs into. Waited on as the
    // ground actually being clear rather than as a fixed delay — and then
    // proceeded either way, for the reason below.
    private _eastMen = {
        private _men = 0;
        {
            if (alive _x && { side group _x isEqualTo east }) then { _men = _men + 1 };
        } forEach (_hqAt nearEntities ["CAManBase", 400]);
        _men
    };
    _deadline = diag_tickTime + 300;
    waitUntil { call _eastMen isEqualTo 0 || { diag_tickTime > _deadline } };
    // Advisory, not a verdict: whether EAST's Commander leaves a rear guard is
    // its own business, and a run where it left two men behind is a Campaign
    // being played rather than a probe fault. It went red on exactly that once.
    // What it must not do is put a firefight under an assertion about a band, so
    // whatever is still standing there is silenced and made unkillable
    // alongside the staged garrison below — one rule for everything at this
    // Base, and the rule is that it is there to be *seen*.
    private _leftBehind = call _eastMen;
    {
        if (side group _x isEqualTo east) then {
            _x setCombatMode "BLUE";
            _x allowDamage false;
        };
    } forEach (_hqAt nearEntities ["CAManBase", 400]);
    diag_log format ["CTI|mass_probe_base_clear left_behind=%1 at=%2", _leftBehind, time];

    // ------------------------------------------------ the approach line
    // On the line between the HQ and the Objective the manifest calls adjacent
    // to this Base. Authored ground rather than a bearing off somebody's facing
    // — #28's lesson, which cost two probes. Everything below is placed off this
    // one vector, so the garrison faces the way the attack comes and the attack
    // comes the way the garrison faces.
    private _adjacent = [(_target getOrDefault ["adjacent", [""]]) # 0] call _placeNamed;
    if (count _adjacent isEqualTo 0) exitWith {
        diag_log "CTI|FAIL class=assertion_failed mass_probe_no_adjacent_place";
    };
    (_adjacent get "position") params ["_fromEast", "_fromNorth"];
    private _runEast = _fromEast - (_hqAt # 0);
    private _runNorth = _fromNorth - (_hqAt # 1);
    private _span = sqrt ((_runEast * _runEast) + (_runNorth * _runNorth));
    // Unit vector towards the approach, and its perpendicular, so a line of men
    // can be laid across the approach rather than around the building.
    private _towards = [_runEast / _span, _runNorth / _span];
    private _across = [-(_towards # 1), _towards # 0];
    private _stagedAt = 100;
    private _approach = [
        (_hqAt # 0) + ((_towards # 0) * _stagedAt),
        (_hqAt # 1) + ((_towards # 1) * _stagedAt)
    ];

    // ------------------------------------------------ engineered start: the garrison
    // Eight men on their own Base, told not to path so they stay on it. Eight
    // rather than a round company: what the band comes out as is what WEST's
    // leader manages to see, and inflating the number to force a band would be
    // arranging the answer. Eight is also the size at which the band and the
    // strength agree — see the header, where twelve did not and it cost a run.
    //
    // Laid in a line across the approach, 25 m out on the attack's side of the
    // HQ, standing. The first cut put them in a ring around it and half of them
    // spent the run behind the building — #28's hangar, with the HQ as the
    // hangar. A garrison facing the way the enemy comes is also what a garrison
    // is, so this is the geometry being honest rather than being helpful.
    private _garrison = createGroup [east, true];
    private _defenders = 0;
    for "_i" from 0 to 7 do {
        private _offset = (_i - 3.5) * 6;
        private _spot = [
            (_hqAt # 0) + ((_towards # 0) * 25) + ((_across # 0) * _offset),
            (_hqAt # 1) + ((_towards # 1) * 25) + ((_across # 1) * _offset),
            0
        ];
        private _man = _garrison createUnit ["O_Soldier_F", _spot, [], 0, "NONE"];
        if (!isNull _man) then {
            _man disableAI "PATH";
            _man setUnitPos "UP";
            _man setDir ((_towards # 0) atan2 (_towards # 1));
            // Held still and told not to shoot, and neither able to die —
            // `contacts.sqf` plants its men the same way and for the same
            // reason: "the planted men may not fire back and may not die,
            // because the head count is what the assertions are made of". Here
            // the head count *is* the band, and the band is what the mass is
            // read from. A garrison that fights would put a dead observer,
            // a shrinking head count and a moving band underneath an assertion
            // about none of those, which is how the run before this one ended:
            // the staged Squad was killed before the sampler's next tick and no
            // Contact ever formed. What this costs is the fight, and this probe
            // does not assert the fight — see below.
            _man setCombatMode "BLUE";
            _man allowDamage false;
            _defenders = _defenders + 1;
        };
    };
    if (_defenders isEqualTo 0) exitWith {
        diag_log "CTI|FAIL class=assertion_failed mass_probe_garrison_failed";
    };
    _garrison setBehaviour "AWARE";
    _garrison setCombatMode "BLUE";
    diag_log format ["CTI|mass_probe_garrison men=%1 at=%2 grid=%3",
        _defenders, time, mapGridPosition _hqAt];
    private _putOnApproach = {
        params ["_squads", "_lane"];
        private _placed = [];
        {
            _x params ["_id", "_group"];
            // Abreast across the approach rather than strung out along it, so
            // every Squad has the same view of the Base and the same walk in.
            {
                private _offset = (_lane * 40) + (_forEachIndex * 4);
                _x setPosATL [
                    (_approach # 0) + ((_across # 0) * _offset),
                    (_approach # 1) + ((_across # 1) * _offset),
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

    // ------------------------------------------------ WEST acquires the garrison
    // The world's part, waited for on the sampler's own answer rather than
    // assumed. `cti_fnc_contactSample` is exactly what the daemon is handed, so
    // reading it here is reading the Commander's input and not a second opinion:
    // no `reveal`, no ground truth, nothing the engine did not report.
    //
    // Waited on until it is worth asserting about — four sightings is the floor
    // of the `squad` band and therefore the first band that wants more than one
    // Squad. Below that the Commander correctly sends one, which is true and
    // proves nothing, so the probe would rather say the geometry failed.
    private _sightedAtBase = {
        private _report = (call cti_fnc_contactSample) getOrDefault ["WEST", createHashMap];
        private _here = 0;
        {
            if ((_x getOrDefault ["at", ""]) isEqualTo "csat_kamino") then { _here = _here + 1 };
        } forEach (_report getOrDefault ["seen", []]);
        _here
    };
    _deadline = diag_tickTime + 300;
    private _sighted = 0;
    waitUntil {
        _sighted = call _sightedAtBase;
        _sighted >= 4 || { diag_tickTime > _deadline }
    };
    if (_sighted < 4) exitWith {
        diag_log format ["CTI|FAIL class=timeout mass_probe_never_acquired seen=%1 of=%2 range=%3 at=%4",
            _sighted, _defenders, (leader ((_first # 0) # 1)) distance2D _hqAt, time];
    };
    // What the daemon should make of that, by `cti_daemon.contacts.ECHELONS`'
    // thresholds and `cti_daemon.planner.ASSAULT_MASS`' table — written out
    // because there is no path from a Python table into a mission. It is logged
    // and asserted **as a range**, not as an equality, and the reason is the
    // clock rather than a lack of nerve: this reads the sampler at one instant
    // and the daemon banded its own sample up to a report interval earlier, so
    // a count sitting on a band boundary would make an exact match a coin toss.
    // The exact band-to-mass relation is the unit tier's claim, on 200 seeds.
    // What is asserted here is the half no unit test can make: that a Contact
    // the world produced brought more than one Squad, and no more than the
    // table's ceiling.
    private _wanted = 1;
    if (_sighted >= 4) then { _wanted = 2 };
    if (_sighted >= 9) then { _wanted = 3 };
    if (_sighted >= 25) then { _wanted = 4 };
    private _ceiling = 4;
    diag_log format ["CTI|mass_probe_acquired seen=%1 of=%2 wanted=%3 at=%4",
        _sighted, _defenders, _wanted, time];
    _wanted = 2;

    // ------------------------------------------------ the Commander reinforces
    // The criterion. Whatever band WEST's own eyes produced, it is a band above
    // a team, and a band above a team is more than one Squad. Nothing below asks
    // for it.
    _deadline = diag_tickTime + 120;
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
        diag_log format ["CTI|FAIL class=assertion_failed mass_probe_assault_called_off squads=%1 seen=%2 at=%3",
            ["WEST"] call _fielded, _sighted, time];
    };
    if (count _mass < _wanted) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed mass_probe_under_massed sent=%1 wanted=%2 seen=%3 at=%4",
            count _mass, _wanted, _sighted, time];
    };
    if (count _mass > _ceiling) exitWith {
        // Above the table's heaviest entry there is nothing a band could have
        // asked for, so this is the detail rule taking Squads it was not owed.
        diag_log format ["CTI|FAIL class=assertion_failed mass_probe_over_massed sent=%1 ceiling=%2 seen=%3 at=%4",
            count _mass, _ceiling, _sighted, time];
    };
    diag_log format ["CTI|mass_probe_massed squads=%1 sent=%2 seen=%3 at=%4",
        _mass apply { _x # 0 }, count _mass, _sighted, time];

    // Everything the Commander added goes on the same line, for the same
    // declared reason as the first: the 4.4 km is not what is being measured.
    private _reinforcements = _mass select { !((_x # 0) in _staffed) };
    private _brought = [_reinforcements, 1] call _putOnApproach;
    diag_log format ["CTI|mass_probe_staged_reinforcements squads=%1 at=%2", _brought, time];

    // ------------------------------------------------ the mass is a standing Order
    // The last assertion, and deliberately not the fight. What has to hold is
    // that the mass is an Order and not a flicker: the Base stays named by a
    // force for as long as the force is closing with it, rather than being
    // unpicked by the next plan. A threat model that massed and then thrashed
    // would be worse than one that never massed.
    //
    // The **strength** is what is watched, not the membership, and that is a
    // correction this probe earned: a first cut required the same Squads and
    // went red at t=211 when one of them was swapped for another. The swap was
    // the planner being right about a picture this probe had made — teleporting
    // a Squad onto the approach puts it in open ground, where it is measured
    // from its own Base 4.4 km away, so a Squad still standing on the Objective
    // next door is genuinely the cheaper trip. Staging cannot both shorten a
    // march and expect the scorer not to notice.
    private _steady = diag_tickTime + 60;
    private _held = _wanted;
    waitUntil {
        _held = _held min (count (call _raiders));
        _held < _wanted || { diag_tickTime > _steady }
    };
    if (_held < _wanted) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed mass_probe_mass_unpicked held=%1 wanted=%2 at=%3",
            _held, _wanted, time];
    };
    _mass = call _raiders;

    // The state the mass was left in, as evidence rather than as a verdict —
    // where the force is, how much of it there is, and what it is looking at.
    // The garrison cannot die here, so a damaged HQ or a thinned defence would
    // both be surprises worth seeing in the log rather than assertions.
    private _attackers = 0;
    { _attackers = _attackers + ({ alive _x } count units (_x # 1)) } forEach _mass;
    diag_log format ["CTI|mass_probe_prosecuting sent=%1 attackers=%2 defenders=%3 damage=%4 range=%5 at=%6",
        count _mass, _attackers, { alive _x } count units _garrison, damage _hq,
        (leader ((_mass # 0) # 1)) distance2D _hqAt, time];

    diag_log "CTI|mass_probe_done";
};
