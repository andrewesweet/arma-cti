// Flies the observer's camera with nobody at the keyboard, and reads the body
// out of the world on both edges of the flight (#190).
//
// #178 landed the curator and proved the *assignment*; its own close-out said
// so plainly — "this run proved the assignment, not the keypress". #190 hangs
// the body's disappearance off that keypress, so a second run proving only that
// a variable was set would prove nothing new. This fixture is the keypress
// standing in: `openCuratorInterface` "force opens curator interface"
// (commands/openCuratorInterface.wiki) and `findDisplay 312 closeDisplay 2` is
// that page's own way of closing it again, both pushed onto the human's machine
// exactly the way the watcher itself is pushed. What it still cannot exercise is
// the Y key, which is engine-owned behaviour of an assigned curator; if Y does
// nothing in a human session, that is a finding against #178 and not against
// this.
//
// Deliberately **not** in spike/probes/, for the reason session-hold.sqf gives
// and #178's third criterion requires: the corpus must boot no curator, and
// corpus membership is by directory. It is probe-shaped — it asserts, and it
// types its failures — but it lives on the playtest path and runs by hand.
//
// Needs the headed Windows client, because the subject is a display that only
// exists on a machine with a screen:
//
//     CTI_WINDOWS_CLIENT=1 just probe spike/playtest/observer-flight.sqf 540
//
// ## The window, which is arithmetic and not a dial
//
// 540 s is the sum of this fixture's own bounds plus the bring-up in front of
// them: 20 (the world builds and both server loops turn once) + 180 (a client
// boots on the Windows host, connects and takes the one Commander slot — 25 s
// measured, and the bound is for a cold host) + 90 (the sweep creates a curator
// logic, assigns it, and the engine reflects the assignment: three sweep turns
// at 5 s, bounded far above) + 60 (the sweep pushes the body watcher and the
// watcher answers) + 60 + 60 (each edge of the flight: the client sees the
// display within 1 s, the server hides within 5) = 470, plus the ~13 s of
// server bring-up before the mission runs and the slack over it. Each wait
// below carries its own bound, so a run that loses one leg says which and stops
// there rather than spending the rest of the window on nothing.
//
// ## What it asserts, and what it deliberately does not
//
// The two engine states the human's ruling names — the body hidden, and its
// simulation off — read back off the server on both edges, plus the standing
// unit count, unmoved, because a camera that spawned something would be a
// different failure wearing the same clothes.
//
// It does not stage a firefight to watch the AI ignore the body. Two reasons,
// and they point the same way. An assertion on a firefight is a bet on a
// world-owned outcome, which is the thing docs/regression-tier.md's worked
// example forbids; and the enemy is nowhere near a Commander's own Base, so the
// assertion available here — that nobody knows about a body nobody could see
// anyway — would pass with the feature deleted. That is #116's vacuity, and an
// assertion that cannot fail is worse than the honest sentence: the AI
// consequence is the engine's documented consequence of simulation being off
// (commands/enableSimulation.wiki), and what this proves is that simulation is
// off.
//
// Runs on the server: initServer.sqf is what compiles the harness.
[] spawn {
    // The world built, so any FAIL below is this fixture's own.
    [20] call cti_probe_fnc_worldReady;

    // The human's machine, whichever slot it took. A headless client is not a
    // player in this sense and never gets a curator — observer.sqf's own filter.
    private _deadline = diag_tickTime + 180;
    private _unit = objNull;
    waitUntil {
        _unit = ((allPlayers - entities "HeadlessClient_F") select {
            getPlayerUID _x isNotEqualTo ""
        }) param [0, objNull];
        !isNull _unit || { diag_tickTime > _deadline }
    };
    if (isNull _unit) exitWith {
        // Not a result: the run sent no client, so nothing this fixture asks
        // about was ever in the world to ask (CLAUDE.md's failure-class table).
        diag_log "CTI|FAIL class=infra_unavailable observer_flight_no_client run_with=CTI_WINDOWS_CLIENT=1";
        diag_log "CTI|observer_flight probe_done reason=no_client";
    };

    private _uid = getPlayerUID _unit;
    // Counted from here rather than from world-ready: a Commander's own body is
    // a unit, and a baseline taken before he joined would make his arrival look
    // like something the camera spawned. It did, on this fixture's first run.
    private _standing = count allUnits;
    diag_log format ["CTI|observer_flight_client uid=%1 name=%2 units_alive=%3",
        _uid, name _unit, _standing];

    // The curator, *assigned and reflected*, which is what makes a camera
    // openable at all. Not merely `getAssignedCuratorLogic`: the first run of
    // this fixture opened on that and the second the sweep called assignCurator,
    // five seconds before the engine would admit to the assignment
    // (commands/getAssignedCuratorLogic.wiki's note, and the reason the sweep
    // separates `_assigning` from `_ready`). The camera never opened, the
    // watcher had nothing to see, and the body stayed in the world for a whole
    // sixty-second window. The fix is the condition, not the window.
    _deadline = diag_tickTime + 90;
    private _held = { (getAssignedCuratorUnit (getAssignedCuratorLogic _unit)) isEqualTo _unit };
    waitUntil { call _held || { diag_tickTime > _deadline } };
    if !(call _held) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed observer_flight_no_curator uid=%1 logic=%2",
            _uid, !isNull (getAssignedCuratorLogic _unit)];
        diag_log "CTI|observer_flight probe_done reason=no_curator";
    };

    // The watcher's first turn broadcasts unconditionally, so this is the push
    // having landed on the far machine — read back, not assumed (#80).
    _deadline = diag_tickTime + 60;
    waitUntil {
        (_unit getVariable ["cti_playtest_observerBody", "unset"]) isNotEqualTo "unset"
            || { diag_tickTime > _deadline }
    };
    if ((_unit getVariable ["cti_playtest_observerBody", "unset"]) isEqualTo "unset") exitWith {
        diag_log format [
            "CTI|FAIL class=assertion_failed observer_flight_watcher_silent uid=%1", _uid];
        diag_log "CTI|observer_flight probe_done reason=watcher_silent";
    };

    diag_log format ["CTI|observer_flight_grounded hidden=%1 simulation=%2 units_alive=%3",
        isObjectHidden _unit, simulationEnabled _unit, count allUnits];
    if (isObjectHidden _unit || { !(simulationEnabled _unit) }) then {
        diag_log format [
            "CTI|FAIL class=assertion_failed observer_flight_body_not_in_the_world_before_flight hidden=%1 simulation=%2",
            isObjectHidden _unit, simulationEnabled _unit];
    };

    // ---- into the camera
    //
    // Pushed as code rather than as a bare `remoteExec ["openCuratorInterface"]`
    // for one reason: the client's own view of the assignment is the one the
    // command needs, and only the client can wait on it. The line it logs is
    // what turns "the camera did not open" from a guess into a reading — the
    // first run had no such line and the two readings, a command that never
    // arrived and a command that arrived too early, were indistinguishable.
    diag_log format ["CTI|observer_flight_opening uid=%1", _uid];
    [[], {
        private _deadline = diag_tickTime + 30;
        waitUntil { !isNull (getAssignedCuratorLogic player) || { diag_tickTime > _deadline } };
        private _curator = !isNull (getAssignedCuratorLogic player);
        openCuratorInterface;
        diag_log format ["CTI|observer_flight_client_opened curator=%1", _curator];
    }] remoteExec ["spawn", _unit];

    _deadline = diag_tickTime + 60;
    waitUntil {
        (isObjectHidden _unit && { !(simulationEnabled _unit) }) || { diag_tickTime > _deadline }
    };
    private _hiddenInFlight = isObjectHidden _unit;
    private _simulatedInFlight = simulationEnabled _unit;
    private _standingInFlight = count allUnits;
    diag_log format [
        "CTI|observer_flight_flying hidden=%1 simulation=%2 units_alive=%3 curator_unit=%4",
        _hiddenInFlight, _simulatedInFlight, _standingInFlight,
        (getAssignedCuratorUnit (getAssignedCuratorLogic _unit)) isEqualTo _unit];
    if (!_hiddenInFlight) then {
        diag_log "CTI|FAIL class=assertion_failed observer_flight_body_still_visible_in_flight";
    };
    if (_simulatedInFlight) then {
        diag_log "CTI|FAIL class=assertion_failed observer_flight_body_still_simulated_in_flight";
    };
    if (_standingInFlight isNotEqualTo _standing) then {
        diag_log format [
            "CTI|FAIL class=assertion_failed observer_flight_unit_count_moved was=%1 now=%2",
            _standing, _standingInFlight];
    };

    // ---- and back out of it
    diag_log format ["CTI|observer_flight_closing uid=%1", _uid];
    [[], { findDisplay 312 closeDisplay 2 }] remoteExec ["spawn", _unit];

    _deadline = diag_tickTime + 60;
    waitUntil {
        (!(isObjectHidden _unit) && { simulationEnabled _unit }) || { diag_tickTime > _deadline }
    };
    private _hiddenAfter = isObjectHidden _unit;
    private _simulatedAfter = simulationEnabled _unit;
    diag_log format ["CTI|observer_flight_landed hidden=%1 simulation=%2 units_alive=%3",
        _hiddenAfter, _simulatedAfter, count allUnits];
    if (_hiddenAfter) then {
        diag_log "CTI|FAIL class=assertion_failed observer_flight_body_still_hidden_after_flight";
    };
    if (!_simulatedAfter) then {
        // The one that strands a Commander where he stood, so it is named for
        // what it does rather than for the flag it reads.
        diag_log "CTI|FAIL class=assertion_failed observer_flight_body_left_frozen_after_flight";
    };

    diag_log "CTI|observer_flight probe_done reason=flight_complete";
};
