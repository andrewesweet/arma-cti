// probe: loop-watch
// issues: 102
// window: 180
// expect: node_crashed
//
// #102 in-world probe, RED BY DESIGN. A green run of this probe is the bug.
//
// `expect: node_crashed` inverts the verdict: the run passes when the watchdog
// declares a loop dead and fails when it does not. The FAIL line the watchdog
// writes is the assertion — there is nothing to assert after it, because the
// runner ends the wait at the first FAIL exactly as it does for
// `manifest-missing`.
//
// `just regress loop-watch`, or by hand
// `just probe spike/probes/loop-watch.sqf 180`. The raw verdict is
// FAIL / node_crashed, carrying cti_fnc_loopWatch's own report:
//
//   FAIL class=node_crashed loop_dead=order_enforce silent=41.2 cadence=10
//       turns=7 script_done=true
//
// Why it exists. The world runs on eight spawned loops and a scripting error in
// any one of them kills that loop and nothing else, silently, for the rest of
// the session (#102). The fault cannot be staged from Python and cannot be
// staged from the daemon: it is an engine-level death of one scheduled script
// inside a world that carries on. So the probe murders a loop directly —
// `terminate` on the handle the loop registered — and asks whether anything
// noticed. `terminate` ends the script the same way an unhandled error does,
// which is what makes it a fair stand-in: the handle completes, `scriptDone`
// answers true, and no beat is ever stamped again. What it does not reproduce is
// the error line the engine would print beside it, and the watchdog does not
// read that line, so nothing under test depends on the difference.
//
// `order_enforce` is the victim because nothing else in the world reads it: the
// pump and the report loop carry the counters the probe prelude waits on, and
// killing one of those would take the world-ready wait down with it and prove
// nothing about the watchdog.
//
// The window is 180 rather than 150 and the extra 30 s is the watchdog's own
// grace: it declares a loop dead after three cadences or half a minute,
// whichever is longer, and the victim's cadence is 10 s. Worst case is 10 s
// since the last beat, plus 30 s of grace, plus a 10 s sweep interval before the
// sweep that catches it — 50 s of subject, on top of bring-up and a turn of the
// loop observed first. Sized to what is being measured, per CLAUDE.md.
[] spawn {
    // The world built and the loops turning. The register is filled from inside
    // each loop's own thread, so this wait is also what makes the inventory
    // below a fact rather than a race.
    [20] call cti_probe_fnc_worldReady;

    private _loops = missionNamespace getVariable ["cti_loops", createHashMap];
    diag_log format ["CTI|loop_watch_probe_register loops=%1", keys _loops];

    // Every loop the mission starts, plus the watchdog itself. A loop missing
    // here is one that registered nothing and is therefore unwatched, which is
    // the bug this probe would otherwise walk straight past.
    private _want = ["effect_pump", "presence_report", "commander_assign",
        "commander_view", "order_enforce", "base_assault", "loadout_watch",
        "squad_leader_watch", "loop_watch"];
    private _missing = _want select { !(_x in _loops) };
    if (_missing isNotEqualTo []) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed loop_watch_probe_unregistered=%1", _missing];
    };

    private _victim = _loops get "order_enforce";
    private _script = _victim get "script";
    if (scriptDone _script) exitWith {
        diag_log "CTI|FAIL class=assertion_failed loop_watch_probe_victim_already_done";
    };

    // It has to be beating before it is killed: a loop that never turned proves
    // nothing about a watchdog that reports loops which stop turning. Its cadence
    // is 10 s, so two of them is the deadline.
    private _before = _victim get "turns";
    private _deadline = diag_tickTime + 25;
    waitUntil { (_victim get "turns") > _before || { diag_tickTime > _deadline } };
    if ((_victim get "turns") <= _before) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed loop_watch_probe_victim_not_beating turns=%1",
            _victim get "turns"];
    };
    diag_log format ["CTI|loop_watch_probe_victim_alive turns=%1 at=%2",
        _victim get "turns", _victim get "at"];

    terminate _script;
    diag_log format ["CTI|loop_watch_probe_terminated loop=order_enforce done=%1 at=%2",
        scriptDone _script, diag_tickTime];

    // From here the watchdog is the thing under test and its FAIL line is the
    // verdict. Waited on rather than assumed so the evidence records how long it
    // took; if it never comes, the run ends at the window as `timeout`, which is
    // not the expected class and is therefore red — the right answer for a
    // supervisor that did not supervise.
    private _by = diag_tickTime + 60;
    waitUntil { (_victim get "dead") || { diag_tickTime > _by } };
    diag_log format ["CTI|loop_watch_probe_noticed dead=%1 silent=%2",
        _victim get "dead", diag_tickTime - (_victim get "at")];

    // The rest of the world is still running: a watchdog that reported one dead
    // loop by taking the others down with it would pass the assertion above and
    // be worse than the bug. Read from the report loop, which is the one whose
    // death stops income and captures.
    private _report = _loops get "presence_report";
    diag_log format ["CTI|loop_watch_probe_survivors presence_report_turns=%1 dead=%2",
        _report get "turns", _report get "dead"];
    if (_report get "dead") then {
        diag_log "CTI|FAIL class=assertion_failed loop_watch_probe_took_the_world_with_it";
    };

    diag_log "CTI|loop_watch_probe_done";
};
