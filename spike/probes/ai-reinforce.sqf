// probe: ai-reinforce
// issues: 150, 191
// window: 300
// env: CTI_AI_SIDE=WEST
//
// #150/#191 in-world probe: the AI Commander Reinforces (human ruling,
// 2026-08-04). An understrength Squad standing at its own Base, on a side under
// an AI Commander, is refilled with nobody issuing anything — the planner's own
// use of ADR-0040's Command, crossing the same port and the same outbox as the
// squad-leader Reinforce `reinforce.sqf` already proves the wire for.
//
// The bet is on the decision the planner owns, never on a world-owned outcome
// (docs/regression-tier.md): the staged condition is a thinned Squad inside the
// Base's radius, and the claim is that the Commander decides to refill it —
// observed as the men arriving in the group, because a Reinforce is the only
// path that adds men to a Squad and no client is connected to this run to have
// asked for one. What the unit tier already proves in milliseconds (the choice:
// refill over fresh Squad, the force-limit and cap triggers, the trace rows,
// seeds 0-29 through the real port) is not re-asserted here; what only this
// world can show is that a Reinforce nobody sent reaches it at all.
//
// Staging is asserted before the subject is waited on (#80's rule), and how it
// is asserted was corrected by this probe's own first corpus run
// (20260804T203321Z): the draft read the daemon's board through the `view`
// verb, and an AI-commanded side has no view to hand out — the daemon refused
// every ask `wrong_side` ("WEST is under an AI Commander and has no human view
// to hand out") while the refill it was waiting to see had already been issued
// at t=10. So the staging assertion rides what the world can honestly know
// (the casualties pattern, #46): the Squad reads five men at the Base through
// `cti_fnc_placeOf` — the same reading `cti_fnc_squadSample` reports with —
// and then a report that *began after* the thinning has had its judgement
// applied (`cti_presenceReport`'s `sent`/`replied` counters), which is the
// report that carried the five onto the daemon's roster.
//
// The window is 300, which is this arithmetic and not a flake allowance:
// 20 s for the world and both server loops (cti_probe_fnc_worldReady), 90 s
// for the AI's first Purchase to be decided and the Squad to stand in the
// world (ai-commander.sqf's own allowance for its first two), 15 s for a
// report begun after the thinning to complete its leg (casualties' own
// deadline for the same wait), and 90 s for the refill to be decided on a
// following cycle, judged, and the men landed by the 2 s effect pump — 215 s
// of deadlines, plus engine-noise slack. The thinning itself is free: the men
// are deleted the moment the Squad appears, ~149 m of the Base's 150 m radius
// before `at` stops reading as the Base. On the first corpus run the decision
// came at t=10, five seconds after the Squad was bought.
//
// The men are deleted rather than killed, as `reinforce.sqf` thins: what is
// under test is the refill decision, and a corpse is the casualty path's
// subject. Funds are asserted on nowhere, for that probe's stated reason — the
// stipend moves them on its own clock. And the timeline cannot starve the
// purse: the thinning is visible to the daemon on the report that would have
// bought the second Squad, so at least 200 Funds stand against a 30-Fund
// refill when the choice is first made.
[] spawn {
    private _extension = call cti_fnc_shimName;
    if (_extension isEqualTo "") exitWith {
        diag_log "CTI|FAIL class=infra_unavailable ai_reinforce_probe_no_shim";
        diag_log "CTI|ai_reinforce_probe_done";
    };

    [20] call cti_probe_fnc_worldReady;

    // ------------------------------------------------------- the staged Squad
    // Nobody buys it: the AI Commander's own first Purchase is the Squad under
    // test, which is what makes this the planner's probe rather than the wire's.
    private _deadline = diag_tickTime + 90;
    private _squads = createHashMap;
    waitUntil {
        _squads = ["WEST"] call cti_probe_fnc_squadsOf;
        count _squads >= 1 || { diag_tickTime > _deadline }
    };
    if (count _squads < 1) exitWith {
        diag_log format ["CTI|FAIL class=timeout ai_reinforce_probe_never_bought squads=%1 hint=%2",
            count _squads, "is CTI_AI_SIDE set?"];
        diag_log "CTI|ai_reinforce_probe_done";
    };

    private _ids = keys _squads;
    _ids sort true;
    private _squadId = _ids # 0;
    private _group = _squads get _squadId;
    private _boughtAs = count units _group;

    // Thinned while it is still standing in its Base's radius, from the rear so
    // the leader the engine reports positions off is untouched.
    { deleteVehicle _x } forEach ((units _group) select [(count units _group) - 3, 3]);

    // The world's own account of what it will report: five men, at the Base,
    // read through the same `cti_fnc_placeOf` call `cti_fnc_squadSample` makes.
    // If the Squad has already walked out of the radius the staging is broken
    // and nothing downstream means anything, so it is said here rather than
    // discovered as a refill that never came.
    private _map = missionNamespace getVariable ["cti_map", createHashMap];
    private _at = [
        getPosATL leader _group,
        _map getOrDefault ["objectives", []],
        _map getOrDefault ["bases", []]
    ] call cti_fnc_placeOf;
    if (_at isNotEqualTo "nato_airbase") exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed ai_reinforce_probe_thinned_off_base squad=%1 at=%2 grid=%3",
            _squadId, _at, mapGridPosition leader _group];
        diag_log "CTI|ai_reinforce_probe_done";
    };
    diag_log format ["CTI|ai_reinforce_probe_thinned squad=%1 was=%2 now=%3 at=%4",
        _squadId, _boughtAs, count units _group, _at];

    // ------------------------------------------- the daemon knows, at the Base
    // A report that began after the thinning has had its judgement applied —
    // the report that carried the five-man Squad onto the daemon's roster,
    // which is the picture the refill decision reads. The casualties pattern
    // (#46), against the report loop's own counters, and 15 s is that probe's
    // own deadline for the same leg.
    private _turns = missionNamespace getVariable ["cti_presenceReport", createHashMap];
    private _sentBefore = _turns getOrDefault ["sent", 0];
    _deadline = diag_tickTime + 15;
    waitUntil {
        private _now = missionNamespace getVariable ["cti_presenceReport", createHashMap];
        (_now getOrDefault ["replied", 0]) > _sentBefore || { diag_tickTime > _deadline }
    };
    private _after = missionNamespace getVariable ["cti_presenceReport", createHashMap];
    if ((_after getOrDefault ["replied", 0]) <= _sentBefore) exitWith {
        diag_log format ["CTI|FAIL class=timeout ai_reinforce_probe_thinning_never_reported sent_before=%1 replied=%2",
            _sentBefore, _after getOrDefault ["replied", 0]];
        diag_log "CTI|ai_reinforce_probe_done";
    };
    diag_log format ["CTI|ai_reinforce_probe_staged squad=%1 standing=%2 at=%3 sent=%4 replied=%5",
        _squadId, count units _group, _at,
        _after getOrDefault ["sent", 0], _after getOrDefault ["replied", 0]];

    // ---------------------------------------------------------- the decision
    // The subject: the AI Commander refills the Squad. The men arrive because
    // the planner issued Reinforce, the port accepted it, and the pump carried
    // `squad_reinforced` — no other path adds a man to a Squad, and this run
    // has no client to have asked. Waited on the world rather than any reply
    // (ADR-0012: the judgement is never the work), like `reinforce.sqf`.
    _deadline = diag_tickTime + 90;
    waitUntil {
        (!isNull _group && { count units _group >= _boughtAs })
            || { diag_tickTime > _deadline }
    };
    private _standing = if (isNull _group) then { 0 } else { count units _group };
    if (_standing < _boughtAs) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed ai_reinforce_probe_never_refilled squad=%1 standing=%2",
            _squadId, _standing];
        diag_log "CTI|ai_reinforce_probe_done";
    };

    diag_log format ["CTI|ai_reinforce_probe_refilled squad=%1 units=%2->%3->%4 leader_at=%5",
        _squadId, _boughtAs, _boughtAs - 3, _standing, mapGridPosition leader _group];

    diag_log "CTI|ai_reinforce_probe_done";
};
