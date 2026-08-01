// probe: contacts
// issues: 28, 46
// window: 240
//
// #28 in-world probe: WEST reports what it saw of EAST, and nothing of who EAST is.
//
// `just regress contacts`, or by hand `just probe spike/probes/contacts.sqf 240`.
// Appended to the generated harness at bring-up, never packed into the mission.
//
// The window is raised above the default 150 s because acquisition is a natural
// process with a wide spread, and it is this probe's setup rather than its
// subject. At 150 m the first cut of this probe found six men in seconds on two
// runs and not at all within 90 s on two others. The answer to that was not a
// longer wait at the same range — a flaky probe waited out is still flaky — but
// the geometry the decay probe had already shown to be reliable: closer, and
// with both Squads watching. The deadline is sized to match, and the hold to the
// deadline.
//
// Both sides present, because that is what the acceptance criterion asks for
// and what no unit test can stand in for: the engine's own knowledge model is
// the source, and whether it acquires a man at 150 m is a question only the
// engine answers. The daemon's half — banding, ageing, the removal rule — is
// unit-tested; what is tested here is the half that lives in the world.
//
// #46 converted both of this probe's fixed settles: the bring-up one to the
// shared world-ready wait, and the 30 s knowledge-spread hold to a wait on the
// overlap it was buying. Each keeps its old number as the deadline, so a run in
// which the world never comes up, or in which the two leaders never come to know
// a man in common, reaches the same assertions at the same instant it used to.
[] spawn {
    private _extension = call cti_fnc_shimName;
    if (_extension isEqualTo "") exitWith {
        diag_log "CTI|FAIL class=infra_unavailable contacts_probe_no_shim";
    };

    private _rpc = {
        params ["_envelope"];
        private _raw = ((call cti_fnc_shimName) callExtension ["rpc_keepalive", [toJSON _envelope]]) # 0;
        fromJSON _raw
    };

    // The world built and both server loops turned once (#46, replacing a fixed
    // 20 s settle and keeping its 20 s as the deadline).
    [20] call cti_probe_fnc_worldReady;

    // Two WEST Squads rather than one: several leaders share knowledge of the
    // same men, so a sample that did not deduplicate would report each of them
    // twice and band a fire team as a squad. One leader could not catch that.
    private _wanted = 2;
    for "_i" from 1 to _wanted do {
        [createHashMapFromArray [
            ["id", format ["contacts-probe-buy-%1", _i]],
            ["verb", "command"],
            ["payload", createHashMapFromArray [
                ["command", "purchase"],
                ["side", "WEST"],
                ["args", createHashMapFromArray [["squad_type", "rifle"]]]
            ]]
        ]] call _rpc;
    };

    // The purchase is judged on the call; the Squad arrives through the outbox,
    // so wait for the world to hold it rather than assuming the pump has run.
    private _deadline = diag_tickTime + 60;
    waitUntil {
        count (missionNamespace getVariable ["cti_squads", createHashMap]) >= _wanted
            || { diag_tickTime > _deadline }
    };
    private _squads = missionNamespace getVariable ["cti_squads", createHashMap];
    if (count _squads < _wanted) exitWith {
        diag_log format ["CTI|FAIL class=timeout contacts_probe_no_squads bought=%1 held=%2",
            _wanted, count _squads];
    };
    private _leader = leader ((values _squads) # 0);
    diag_log format ["CTI|contacts_probe_bought squads=%1 leader_at=%2",
        count _squads, mapGridPosition _leader];

    // Enemy for them to see. Spawned rather than bought: EAST's own Base is
    // 4.4 km away, and what is under test is the sighting path rather than the
    // purchase one. Close enough to be acquired in daylight, and told not to
    // shoot — a firefight would change the head count under the assertion, and
    // the count is the assertion.
    private _planted = 6;
    private _east = createGroup [east, true];
    private _muster = _leader getRelPos [100, 0];
    for "_i" from 1 to _planted do {
        _east createUnit ["O_Soldier_F", _muster, [], 15, "FORM"];
    };
    // Observers woken, enemy held still. A Squad in Reserve is at the engine's
    // default behaviour with its weapons down and is a poor witness — see
    // `spike/probes/contact-decay.sqf`, which sat at `knows_east=0` for 120 s
    // until its observers were put in AWARE. That is the posture a Squad under a
    // Capture or Defend Order is in anyway. The planted men may not fire back
    // and may not die, because the head count is what the assertions are made of.
    { _x setBehaviour "AWARE" } forEach values _squads;
    _east setCombatMode "BLUE";
    { _x allowDamage false } forEach units _east;
    diag_log format ["CTI|contacts_probe_planted side=EAST units=%1 at=%2 date=%3",
        count units _east, mapGridPosition _muster, date];

    // Wait for the engine to acquire them. A deadline rather than a `reveal`:
    // revealing would hand the knowledge model the answer, and the knowledge
    // model is the thing under test.
    // Walked round the compass until somebody sees them, for the reason
    // `spike/probes/contact-decay.sqf` records: a bearing off the leader's
    // facing is a guess about line of sight, and on an airfield it lands behind
    // a hangar often enough to matter. This arranges for there to be something
    // to see; the engine still decides whether it sees it.
    private _bearings = [0, 45, 90, 135, 180, 225, 270, 315];
    private _attempt = 0;
    private _nextMove = 0;

    _deadline = diag_tickTime + 150;
    private _report = createHashMap;
    waitUntil {
        if (diag_tickTime > _nextMove) then {
            _nextMove = diag_tickTime + 15;
            private _where = _leader getRelPos [100, _bearings select (_attempt mod 8)];
            {
                _x setPosATL [(_where # 0) + (_forEachIndex * 3), (_where # 1), 0];
            } forEach units _east;
            _attempt = _attempt + 1;
        };
        _report = (call cti_fnc_contactSample) getOrDefault ["WEST", createHashMap];
        count (_report getOrDefault ["seen", []]) > 0 || { diag_tickTime > _deadline }
    };

    if (count (_report getOrDefault ["seen", []]) isEqualTo 0) exitWith {
        diag_log "CTI|FAIL class=timeout contacts_probe_never_acquired";
    };

    // Wait for the overlap itself. Deduplication is only tested by two leaders
    // knowing some of the same men, and the first sighting cannot overlap with
    // anything — so what this used to buy with a 30 s hold it now waits for by
    // name (#46), with the 30 s kept as the deadline. Asked of the engine rather
    // than of the sampler, because the sampler is what the overlap is about to
    // be used to test; a run where the overlap never forms carries on at 30 s
    // into exactly the assertions it did before, and the log line says which
    // kind of run it was.
    private _overlapDeadline = diag_tickTime + 30;
    private _overlap = 0;
    private _knownBy = {
        params ["_who"];
        private _ids = [];
        {
            if ((_x # 2) isEqualTo east) then {
                private _id = netId (_x # 1);
                if !(_id in _ids) then { _ids pushBack _id };
            };
        } forEach (_who targetsQuery [objNull, east, "", [], 0]);
        _ids
    };
    // On a 1 s tick, not every frame: `targetsQuery` is CPU-intensive by the
    // wiki's own word and this probe measures that cost a few lines below, so a
    // free-running poll would be loading the thing it is about to time.
    private _nextLook = 0;
    waitUntil {
        if (diag_tickTime > _nextLook) then {
            _nextLook = diag_tickTime + 1;
            private _first = [leader ((values _squads) # 0)] call _knownBy;
            private _second = [leader ((values _squads) # 1)] call _knownBy;
            _overlap = count (_first select { _x in _second });
        };
        _overlap > 0 || { diag_tickTime > _overlapDeadline }
    };
    diag_log format ["CTI|contacts_probe_overlap men=%1 waited=%2",
        _overlap, 30 - (_overlapDeadline - diag_tickTime)];

    // Sampled here rather than reused from the wait, so the sample and the raw
    // query below read the engine at the same moment and can be compared.
    _report = (call cti_fnc_contactSample) getOrDefault ["WEST", createHashMap];
    private _seen = _report getOrDefault ["seen", []];

    // What each leader actually knows, read straight from the engine, so the
    // sampler is checked against its own source rather than against what it
    // reports. `targetsQuery` ranks by the side asked for instead of filtering
    // by it, and returns own troops at accuracy 0.01 — the bug this probe
    // found, and the reason the raw list is worth keeping in the evidence.
    private _plantedIds = (units _east) apply { netId _x };
    private _believedEnemy = [];
    {
        private _who = leader _x;
        {
            _x params ["_accuracy", "_target", "_targetSide", "_targetType", "", "_targetAge"];
            private _id = netId _target;
            if (_targetSide isEqualTo east && { !(_id in _believedEnemy) }) then {
                _believedEnemy pushBack _id;
            };
            diag_log format ["CTI|contacts_probe_raw leader=%1 netId=%2 side=%3 type=%4 age=%5 accuracy=%6 planted=%7 real_side=%8",
                name _who, _id, str _targetSide, _targetType, _targetAge,
                _accuracy, _id in _plantedIds,
                if (isNull _target) then { "null" } else { str side _target }];
        } forEach (_who targetsQuery [objNull, east, "", [], 0]);
    } forEach (values _squads);

    // Nothing of our own is reported as the enemy. The engine's own answer is
    // what is checked, not the sampler's rendering of it: everything WEST
    // believes to be EAST has to be one of the men actually planted.
    private _notPlanted = _believedEnemy select { !(_x in _plantedIds) };
    if (count _notPlanted > 0) then {
        diag_log format ["CTI|FAIL class=assertion_failed contacts_probe_own_troops_reported=%1", _notPlanted];
    };

    // Deduplicated across leaders, and only enemies counted. Not `== planted`:
    // the knowledge model acquires men one at a time and reporting three of six
    // is the feature, so what is asserted is that the sampler never reports
    // more men than are standing there. Sixteen WEST riflemen are in range, so
    // a sampler that leaked its own side, or counted a man once per leader that
    // knows him, would run past six rather than under it.
    if (count _seen > _planted) then {
        diag_log format ["CTI|FAIL class=assertion_failed contacts_probe_not_deduplicated seen=%1 planted=%2 believed=%3",
            count _seen, _planted, count _believedEnemy];
    };
    // The sharper form: one sighting per man WEST believes to be an enemy, no
    // matter how many of its leaders know him. The count on the right is
    // gathered from the engine by a different route than the sampler took, so
    // agreeing is a result rather than an identity.
    if !(count _seen isEqualTo count _believedEnemy) then {
        diag_log format ["CTI|FAIL class=assertion_failed contacts_probe_sample_disagrees seen=%1 believed=%2",
            count _seen, count _believedEnemy];
    };
    diag_log format ["CTI|contacts_probe_acquired of_planted=%1 planted=%2 leaders=%3 sightings=%4",
        count _believedEnemy, _planted, count _squads, count _seen];

    // Every sighting carries a place, a perceived kind and an age, and nothing
    // else. The absence is the claim, so it is read off the payload itself.
    {
        private _keys = keys _x;
        if !(count _keys isEqualTo 3 && { "at" in _keys && "kind" in _keys && "age" in _keys }) then {
            diag_log format ["CTI|FAIL class=assertion_failed contacts_probe_sighting_keys=%1", _keys];
        };
    } forEach _seen;

    // The acceptance criterion, asserted rather than assumed absent: EAST is
    // standing there under a Squad id the world knows, and what WEST reports
    // still cannot be traced to it.
    private _rendered = toJSON _report;
    private _eastIds = (keys _squads) select { _x select [0, 5] isEqualTo "EAST-" };
    private _leaked = ([_eastIds, ["EAST"]] select (count _eastIds isEqualTo 0))
        select { _rendered find _x >= 0 };
    if (count _leaked > 0) then {
        diag_log format ["CTI|FAIL class=assertion_failed contacts_probe_identity_leaked=%1", _leaked];
    };
    diag_log format ["CTI|contacts_probe_seen count=%1 at=%2 kinds=%3 observed=%4",
        count _seen,
        _seen apply { _x get "at" },
        _seen apply { _x get "kind" },
        _report getOrDefault ["observed", []]];

    // The cost measurement #28 asks for, at the count that matters: the design
    // calls `targetsQuery` once per squad leader per report, and the wiki says
    // the command is CPU-intensive. Measured per call and scaled to the 32
    // leaders a full Campaign fields, against the 5 s report interval.
    private _sample = diag_codePerformance [{ _this targetsQuery [objNull, east, "", [], 0] }, _leader, 1000];
    _sample params ["_millis", "_cycles"];
    diag_log format ["CTI|contacts_probe_cost ms_per_call=%1 cycles=%2 ms_at_32_leaders=%3 targets=%4",
        _millis, _cycles, _millis * 32, count (_leader targetsQuery [objNull, east, "", [], 0])];

    // And the whole sampler, which is what actually runs on the server frame.
    private _whole = diag_codePerformance [{ call cti_fnc_contactSample }, nil, 100];
    diag_log format ["CTI|contacts_probe_sampler_cost ms_per_call=%1 cycles=%2 leaders=%3",
        _whole # 0, _whole # 1, count _squads];

    diag_log "CTI|contacts_probe_done";
};
