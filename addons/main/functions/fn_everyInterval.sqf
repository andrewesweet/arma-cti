/*
 * Author: arma-cti
 * Runs one body on a cadence, forever, and keeps the world's account of it.
 * Runs wherever its caller does, which in play is the server.
 *
 * The addon's six long-running loops were six copies of the same eleven lines:
 * register a heartbeat, spawn, pace with `diag_tickTime` and `waitUntil`, stamp
 * the beat at the top of the turn, write the handle back on the beat once
 * `spawn` returns one (#85). Copying that is how a loop ends up unwatched, or
 * paced by something that is not the clock the rest of them use.
 *
 * ## The scheduler adapter the contract names
 *
 * CLAUDE.md bans a bare `sleep` or `random` in SQF and allows "seeded PRNG and
 * CBA scheduler adapters only". The PRNG half has existed since Phase 1
 * (cti_fnc_prngNew and kin); this is the other half, and until now the exception
 * named a thing that did not exist, so every loop hand-rolled the pacing the
 * adapter was supposed to own. That is the debt this discharges.
 *
 * It is not CBA's `CBA_fnc_addPerFrameHandler`. The addon requires `A3_Data_F`
 * and nothing else (config.cpp), so reaching for CBA here would add a runtime
 * dependency on every machine — server, headless client and player — to replace
 * eleven lines of engine scheduler we already run on. What the contract is
 * actually after is that a cadence is one reviewed adapter rather than a habit,
 * and a `waitUntil` on `diag_tickTime` gives that without the dependency: it
 * suspends until the next frame rather than blocking, and it is measured against
 * a clock that does not stop when the world is paused. If the addon ever takes a
 * CBA dependency for other reasons, this is the one function that changes.
 *
 * ## What it does not do
 *
 * It does not restart a body that died, and cti_fnc_loopWatch's header says why
 * at length: a loop dies from the state it met on that turn, and re-entering the
 * same body against the same state is a crash loop reporting a recovery each
 * time round. This registers the heartbeat that lets the watchdog say so.
 *
 * ## Retiring, which is not dying
 *
 * A loop with nothing left to do returns "retire" and stops. The distinction
 * matters because the watchdog's whole job is to notice a loop that has gone
 * quiet: a loop that simply stopped turning would be announced as a death on
 * every screen. So retirement is said out loud, recorded on the heartbeat, and
 * skipped by cti_fnc_loopWatch — a loop is either turning, retired on purpose,
 * or dead, and the three are told apart by the loop itself rather than guessed
 * at from a clock.
 *
 * It also takes no first-turn shortcut of its own. A body that must act before
 * its first wait says so with `_atOnce`, because the difference between "sweep,
 * then wait" and "wait, then sweep" is one the caller can see and this cannot.
 *
 * Arguments:
 * 0: the loop's name <STRING> — the word its watchdog FAIL line will carry
 * 1: seconds between turns <NUMBER>
 * 2: what to hand the body each turn <ANY> (optional, default [])
 * 3: the body <CODE> — called with argument 2 as `_this`, once per turn. Exit it
 *    with `exitWith` rather than `continue`: it is a called block and not the
 *    loop itself, which is what keeps the heartbeat out of its early exits.
 *    Return "retire" from it to stop the loop for good — see below.
 * 4: take the first turn before the first wait <BOOL> (optional, default false)
 *
 * Return Value: <SCRIPT> the loop's thread, already written onto its heartbeat.
 */
params [
    ["_name", "", [""]],
    ["_interval", 5, [0]],
    ["_arguments", []],
    ["_body", {}, [{}]],
    ["_atOnce", false, [false]]
];

// Registered out here rather than from inside the thread, for the reason
// cti_fnc_loopRegister gives: `spawn` returns to the caller and the body starts
// on some later frame, so a loop that registered itself could not be handed its
// own handle without a race.
private _beat = [_name, _interval] call cti_fnc_loopRegister;

private _thread = [_interval, _beat, _arguments, _body, _atOnce] spawn {
    params ["_interval", "_beat", "_arguments", "_body", "_atOnce"];

    private _first = _atOnce;
    while { true } do {
        if (_first) then {
            _first = false;
        } else {
            // Suspends until the next frame rather than spinning, and never a
            // fixed sleep: the contract bans those in SQF outright.
            private _next = diag_tickTime + _interval;
            waitUntil { diag_tickTime >= _next };
        };

        // Stamped at the top of the turn rather than at the bottom (#102): a
        // loop killed mid-turn never takes another, so the stamp stops either
        // way, and stamping first keeps the heartbeat out of the body's own
        // early exits — the effect pump abandons the rest of its turn whenever
        // the daemon does not answer, and a heartbeat at the bottom would have
        // reported a silent daemon as a dead pump.
        _beat set ["turns", (_beat get "turns") + 1];
        _beat set ["at", diag_tickTime];

        if ((_arguments call _body) isEqualTo "retire") exitWith {
            _beat set ["retired", true];
            diag_log format ["CTI|loop_retired name=%1 turns=%2",
                _beat get "name", _beat get "turns"];
        };
    };
};

// The handle the watchdog reports `script_done` from, and the one #102's probe
// terminates to prove it does.
_beat set ["script", _thread];
_thread
