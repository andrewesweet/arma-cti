/*
 * Author: arma-cti
 * A long-running loop says it exists, and hands out the counter it will beat on.
 * Runs wherever the loop does, which in play is the server.
 *
 * The world runs on six spawned loops and nothing watched any of them (#102). An
 * SQF error anywhere in a loop's body — or in anything it calls — terminates that
 * script and only that script, so the world carried on looking healthy with its
 * effects never applying, or its income stopped, or its Squads drifting off
 * Orders, for the rest of the session. This is the half of the fix the loops
 * themselves carry: a name, a cadence, a handle, and a counter that only a
 * completed turn advances.
 *
 * The loop stamps `at` when it takes a turn — the first thing after the wait
 * that paces it, not the last thing in the body. A loop killed mid-turn never
 * takes another, so the stamp stops either way, and stamping at the top keeps
 * the heartbeat out of the body's own early-exit paths: the effect pump
 * `continue`s past the rest of its turn whenever the daemon does not answer, and
 * a heartbeat at the bottom would have reported a silent daemon as a dead pump.
 *
 * A heartbeat rather than `scriptDone`, because a loop wedged forever inside a
 * `waitUntil` is not done and is just as dead to the world. `scriptDone` is
 * recorded beside it anyway: "terminated" and "stuck" want different
 * investigations and only the handle can tell them apart.
 *
 * Kept in `cti_loops` on the mission namespace, server-local: a probe cannot read
 * the server log it is writing into, and the watchdog is not the only thing that
 * wants to know a loop turned. Not broadcast — a client has nothing to do with
 * the server's threads, and the news a client needs arrives as the watchdog's
 * caption.
 *
 * Called *before* the loop is spawned, and handed the beat to keep: a loop that
 * registered itself from inside its own thread could not be given its handle
 * without a race, because `spawn` returns to the caller and the body starts on
 * some later frame. So the caller registers, passes the beat into the spawn, and
 * writes the handle onto it the moment `spawn` gives one back. `script` is
 * therefore scriptNull for the instant between those two statements, and nothing
 * reads it until a loop has been silent for thirty seconds.
 *
 * The other half of that order matters as much: a loop registers only once it is
 * going to run. Every guard that can refuse to start one — no shim, no schema —
 * belongs above the registration, so that "in the register" means "was alive",
 * and the watchdog never reports a death for a loop that was never born.
 *
 * Arguments:
 * 0: the loop's name <STRING> — the word its FAIL line will carry
 * 1: seconds between its turns <NUMBER>
 *
 * Return Value: the loop's beat <HASHMAP>, held by reference — the loop mutates
 * it in place and `cti_loops` sees every turn.
 */
params [["_name", "", [""]], ["_cadence", 5, [0]]];

private _loops = missionNamespace getVariable ["cti_loops", createHashMap];
// Set unconditionally rather than only when absent: writing the same HashMap
// back costs nothing and there is then no order in which the first loop to
// register can find the register missing.
missionNamespace setVariable ["cti_loops", _loops];

private _beat = createHashMapFromArray [
    ["name", _name],
    ["cadence", _cadence],
    // Written by the caller as soon as `spawn` hands one back.
    ["script", scriptNull],
    ["turns", 0],
    ["at", diag_tickTime],
    // Latched by the watchdog when it gives up on this loop, so a death is
    // announced once rather than every sweep for the rest of the session.
    ["dead", false]
];
_loops set [_name, _beat];

diag_log format ["CTI|loop_registered name=%1 cadence=%2", _name, _cadence];
_beat
