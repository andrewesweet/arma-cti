/*
 * Author: arma-cti
 * Watches the loops the world runs on, and says so when one stops. Server only.
 *
 * #102: the play surface is six spawned loops (effect pump, presence report,
 * commander assign, commander view, order enforce, base assault) and a scripting
 * error inside any of them — including inside anything they call — kills that one
 * script and nothing else. The world then keeps running, one organ short and
 * saying nothing: effects judged and paid for but never spawned, income and
 * captures stopped, Squads drifting off Orders. Nothing read the counters the
 * loops were already keeping, so the only recovery was the human noticing and
 * restarting the mission, and nothing told them to.
 *
 * SQF has no try/catch across a scheduled spawn — an error is not catchable from
 * outside the script it kills — so the practical shape is heartbeat and
 * watchdog. Each loop registers with cti_fnc_loopRegister and stamps `at` at the
 * end of every completed turn; this sweep compares that stamp against the loop's
 * own declared cadence and reports the ones that have gone quiet.
 *
 * ## Why nothing is restarted
 *
 * #102 suggested restarting dead loops, on the grounds that each rebuilds its
 * state from the mission namespace. Declined, and the reason is ADR-0036's:
 * a world that recovers by pretending is worse than one that stops.
 *
 * - A loop dies from a scripting error thrown by the state it met on that turn.
 *   Re-entering the same body against the same state throws the same error, so a
 *   restart is a crash loop that reports a recovery each time round.
 * - The counters are not namespace-backed. A second `spawn` of the pump or the
 *   report loop rebuilds `cti_effectDrain` and `cti_presenceReport` from zero,
 *   and those are read as evidence — by the probe prelude's world-ready wait, by
 *   #17's push-path report, by this watchdog. A restart would silently reset the
 *   record of how much work the world had done, which is the #97 failure again:
 *   limping while the instruments read healthy.
 * - What a dead loop costs is not undone by starting a new one. The captures,
 *   effects and Order re-assertions that never happened while it was dead stay
 *   never-happened, and the daemon's picture and the world's have already
 *   diverged by the time anybody notices.
 *
 * So this reports and does not repair: one typed FAIL line naming the loop, and
 * one caption on every screen. In the harness that FAIL ends the run with
 * `node_crashed`, which is the right verdict — a probe whose world lost an organ
 * mid-run has not measured what it thought it measured, and CLAUDE.md's table
 * says collect and escalate. In play it is the same news, in words a player can
 * act on, following cti_fnc_campaignLost's precedent (#96): the world does not
 * end itself, and the human is told what broke and that a restart is the fix.
 *
 * The world is *not* frozen the way a lost Campaign freezes it. A dead loop is
 * one organ, not a Campaign belonging to a different daemon: what still works
 * still works, and stopping it would destroy the evidence of what was running
 * when it died.
 *
 * ## Who watches this
 *
 * Nobody, and that is the design rather than an oversight: supervision that needs
 * supervising is worse than none. This loop is deliberately the simplest in the
 * addon — no extension call, no engine query beyond the clock, no function call
 * inside the sweep — so that the class of fault it exists to catch is one it does
 * not have. It registers itself so `cti_loops` is a complete inventory, and skips
 * itself when judging: a watchdog cannot report its own death, and pretending
 * otherwise would be the lie the rest of this function exists to refuse.
 *
 * A loop that never started is not watched either, because a loop registers from
 * inside its own thread: absence from `cti_loops` means it exited before its
 * first turn, and each of those exits already logs its own reason
 * (`infra_unavailable` for a missing shim, `schema_stale` for a missing export).
 * This is for the loops that started and then stopped, which is the case nothing
 * covered.
 *
 * Arguments:
 * 0: seconds between sweeps <NUMBER> (optional, default 10)
 *
 * Return Value: <SCRIPT> the watchdog thread
 */
params [["_interval", 10, [0]]];

if (!isServer) exitWith { scriptNull };

private _beat = ["loop_watch", _interval] call cti_fnc_loopRegister;

private _watch = [_interval, _beat] spawn {
    params ["_interval", "_beat"];

    diag_log format ["CTI|loop_watch_started interval=%1", _interval];

    while { true } do {
        private _next = diag_tickTime + _interval;
        waitUntil { diag_tickTime >= _next };

        _beat set ["turns", (_beat get "turns") + 1];
        _beat set ["at", diag_tickTime];

        private _now = diag_tickTime;
        {
            private _name = _x;
            private _watched = _y;

            // A retired loop is one that finished on purpose and said so
            // (cti_fnc_everyInterval), not one that went quiet. Announcing it
            // would put "PART OF THE WORLD HAS STOPPED" on every screen for a
            // job that is simply done.
            if (_name isNotEqualTo "loop_watch"
                && { !(_watched get "dead") }
                && { !(_watched getOrDefault ["retired", false]) }) then {
                private _silent = _now - (_watched get "at");
                // Three turns, and never less than half a minute. The cadences
                // run from 2 s to 10 s and a server under load hitches for
                // longer than the fastest of them, so a multiplier alone would
                // report a busy frame as a death. Thirty seconds is late enough
                // that nothing healthy reaches it and early enough that a human
                // hears about it in the same minute it happened.
                private _grace = ((_watched get "cadence") * 3) max 30;
                if (_silent > _grace) then {
                    _watched set ["dead", true];
                    // `scriptDone` separates the two ways a loop goes quiet:
                    // true is a script that ended — the scripting error this
                    // exists for — and false is one still sitting in a wait it
                    // will not come out of.
                    diag_log format ["CTI|FAIL class=node_crashed loop_dead=%1 silent=%2 "
                        + "cadence=%3 turns=%4 script_done=%5",
                        _name, _silent, _watched get "cadence", _watched get "turns",
                        scriptDone (_watched get "script")];
                    // Clients only (-2): the server has no screen, and
                    // server-to-client remoteExec needs no whitelist entry
                    // (ADR-0012). Same direction and reason as
                    // cti_fnc_campaignLost's caption.
                    [format ["PART OF THE WORLD HAS STOPPED (%1). The Campaign is no longer "
                        + "being played in full. Restart the mission.", _name],
                        "PLAIN DOWN", 1] remoteExec ["titleText", -2];
                };
            };
        } forEach (missionNamespace getVariable ["cti_loops", createHashMap]);
    };
};

// Registered like the loops it watches, so `cti_loops` is a complete inventory.
_beat set ["script", _watch];
_watch
