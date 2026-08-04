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
// Staging is asserted before the subject is waited on (#80's rule): the world
// can refuse a thinning silently — a report could arrive late, or the Squad
// could walk out of the Base's 150 m radius — so the daemon's own board is read
// through the `view` verb until it carries the five-man Squad at the Base. Only
// then does the probe wait on the decision. The board scaffold is the second
// copy of `reinforce.sqf`'s `_board`; a third copy should move it into
// spike/probe-prelude.sqf (#86's rule).
//
// The window is 300, which is this arithmetic and not a flake allowance:
// 20 s for the world and both server loops (cti_probe_fnc_worldReady), 90 s for
// the AI's first Purchase to be decided and the Squad to stand in the world
// (ai-commander.sqf's own allowance for its first two), 60 s for the next
// report to carry the thinning onto the daemon's board, 90 s for the refill to
// be decided on the following cycle, judged, and the men landed by the 2 s
// effect pump — 260 s, plus engine-noise slack. The thinning itself is free:
// the men are deleted the moment the Squad appears, ~149 m of radius before
// `at` stops reading as the Base.
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

    // One side's board as the daemon holds it, through the same `view` verb the
    // Commander's own picture comes from: each Squad's size and coarse place.
    private _board = {
        params ["_for"];
        private _result = ([createHashMapFromArray [
            ["id", ["ai-reinforce-probe-view", _for] call cti_fnc_requestId],
            ["verb", "view"],
            ["payload", createHashMapFromArray [["side", _for]]]
        ]] call cti_probe_fnc_rpc) getOrDefault ["result", createHashMap];
        private _squads = createHashMap;
        {
            _squads set [
                _x getOrDefault ["id", "?"],
                [_x getOrDefault ["size", -1], _x getOrDefault ["at", ""]]
            ];
        } forEach (_result getOrDefault ["squads", []]);
        [_squads, _result getOrDefault ["funds", -1]]
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
    diag_log format ["CTI|ai_reinforce_probe_thinned squad=%1 was=%2 now=%3 at=%4",
        _squadId, _boughtAs, count units _group, mapGridPosition leader _group];

    // ------------------------------------------- the daemon knows, at the Base
    // The staging assertion: the refill decision reads the Observation, so the
    // board has to carry the five-man Squad standing at the Base before the
    // decision is anything this probe may wait on. The world can refuse this
    // silently — that is exactly why it is asserted rather than assumed.
    _deadline = diag_tickTime + 60;
    private _held = [];
    private _funds = -1;
    waitUntil {
        (["WEST"] call _board) params ["_seen", "_purse"];
        _held = _seen getOrDefault [_squadId, [-1, ""]];
        _funds = _purse;
        ((_held # 0) < _boughtAs && { (_held # 1) isEqualTo "nato_airbase" })
            || { diag_tickTime > _deadline }
    };
    if ((_held # 0) >= _boughtAs || { (_held # 1) isNotEqualTo "nato_airbase" }) exitWith {
        diag_log format ["CTI|FAIL class=timeout ai_reinforce_probe_thinning_never_reported squad=%1 size=%2 at=%3",
            _squadId, _held # 0, _held # 1];
        diag_log "CTI|ai_reinforce_probe_done";
    };
    diag_log format ["CTI|ai_reinforce_probe_staged squad=%1 size=%2 at=%3 funds=%4",
        _squadId, _held # 0, _held # 1, _funds];

    // ---------------------------------------------------------- the decision
    // The subject: the AI Commander refills the Squad. The men arrive because
    // the planner issued Reinforce, the port accepted it, and the pump carried
    // `squad_reinforced` — no other path adds a man to a Squad, and this run
    // has no client to have asked. Waited on the world rather than the reply
    // (ADR-0012: the judgement is never the work), like `reinforce.sqf`.
    _deadline = diag_tickTime + 90;
    waitUntil {
        (!isNull _group && { count units _group >= _boughtAs })
            || { diag_tickTime > _deadline }
    };
    (["WEST"] call _board) params ["_seenAfter", "_fundsAfter"];
    private _standing = if (isNull _group) then { 0 } else { count units _group };
    if (_standing < _boughtAs) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed ai_reinforce_probe_never_refilled squad=%1 standing=%2 board=%3 funds=%4",
            _squadId, _standing, _seenAfter getOrDefault [_squadId, [-1, ""]], _fundsAfter];
        diag_log "CTI|ai_reinforce_probe_done";
    };

    diag_log format ["CTI|ai_reinforce_probe_refilled squad=%1 units=%2->%3->%4 board=%5 funds=%6",
        _squadId, _boughtAs, _held # 0, _standing,
        _seenAfter getOrDefault [_squadId, [-1, ""]], _fundsAfter];

    diag_log "CTI|ai_reinforce_probe_done";
};
