/*
 * Author: arma-cti
 * Drains the daemon's outbox and carries out what it finds. Runs on the server.
 *
 * Poll-and-ack rather than an unsolicited push: the shim's exchange writes one
 * line and reads exactly one line, so a line the daemon sent unbidden would be
 * read as the reply to the next request. The daemon holds every effect until
 * its sequence number is acknowledged and replays anything unacknowledged
 * (ADR-0005), which is what makes at-most-once callback delivery survivable.
 *
 * Nothing is acknowledged until it has been carried out, or until it has been
 * refused for good. An effect that fails to apply for a reason another poll
 * could clear stays on the outbox and comes back, rather than being lost between
 * the two; an effect that can never be carried out is dead-lettered — said
 * loudly, acknowledged, and got out of the way of everything behind it (#100).
 *
 * Stopping at the first failure whatever its kind was the earlier reading, and
 * it wedges: the ack is a high-water mark, so one effect this world can never
 * apply — an unknown effect name after a partial upgrade, a side with no Base —
 * held up Squad spawns, Orders and `campaign_won` itself for the rest of the
 * session, on a 2 s retry, while both sides' Funds were already spent. The
 * classification is cti_fnc_effectApply's, because it is the only thing that
 * knows which of the two it met.
 *
 * The synchronous path is used deliberately: a poll asks the daemon for work it
 * already holds, so it never waits on anything and stays far inside the 1000 ms
 * blocking-call stall cap. No ExtensionCallback handler is involved, so the
 * ordering hazard it carries does not arise here.
 *
 * What one drain carried is counted into `cti_effectDrain` as it goes: the
 * engine drains at most 100 callbacks per frame (ADR-0004) and two Commanders
 * double what arrives here (#17), so the largest single drain is the number
 * that bounds this path. Counted in the world rather than inferred from the
 * daemon's side of it, because what matters is how many effects one frame was
 * asked to carry out.
 *
 * Arguments:
 * 0: seconds between polls <NUMBER> (optional, default 2)
 *
 * Return Value: <SCRIPT> the pump thread
 */
#include "\cti\addons\main\script_component.hpp"

params [["_interval", 2, [0]]];

// The entry point of a supervised loop, which ADR-0040 keeps guarded: this is the
// one call site a future restart would re-enter, and the thread it starts is
// inventoried by name rather than by caller (#118).
SERVER_ONLY(scriptNull);

// Asked before the thread is started rather than inside it (#102): a loop enters
// the watchdog's register only once it is going to run, so a world with no shim
// gets this one `infra_unavailable` line and no pump rather than a registered
// pump the watchdog then reports dead thirty seconds later.
private _extension = call cti_fnc_shimName;
if (_extension isEqualTo "") exitWith {
    diag_log "CTI|FAIL class=infra_unavailable effect_pump_no_shim";
    scriptNull
};

diag_log format ["CTI|effect_pump_started interval=%1", _interval];

// The push path's running account, for whatever wants to read it back — #17's
// probe does. Held in the mission namespace rather than logged alone, because a
// probe cannot read the server log it is writing into. Separate from the
// heartbeat the watchdog reads: that counts what the wire carried and the beat
// counts that the loop is alive at all — a pump polling a dead daemon drains
// nothing and is turning.
private _drain = createHashMapFromArray [
    ["polls", 0], ["drains", 0], ["applied", 0], ["max", 0], ["maxFrames", 0],
    ["deferred", 0], ["dead", 0]
];
missionNamespace setVariable ["cti_effectDrain", _drain];

// How many polls each still-unacknowledged sequence has been deferred on. The
// backstop under the classification rather than a second copy of it: a transient
// failure that is not actually clearing looks exactly like a permanent one
// misfiled as transient, and neither should be able to retry in silence for the
// rest of a session.
private _deferrals = createHashMap;
// Three minutes at the default cadence. Long enough that nothing the world is
// genuinely waiting on — a Squad still spawning, a client still joining — is
// called stuck, short enough that a human hears about it inside a Play Session
// rather than after one.
private _stuckAfter = 90;

// Paced, heartbeated and watched by the one adapter every loop in the addon
// runs on (#85).
["effect_pump", _interval, [_drain, _deferrals, _stuckAfter], {
    params ["_drain", "_deferrals", "_stuckAfter"];

    private _answer = [["poll"] call cti_fnc_requestId, "poll"] call cti_fnc_daemonCall;
    _drain set ["polls", (_drain get "polls") + 1];

    // Every outcome that is not `ok` has already been classified and logged
    // by the call (#97): a shim error reply used to reach here shaped like a
    // HashMap with no `result` in it, so the pump read no messages, counted
    // the poll and looked healthy while the outbox stalled behind a daemon
    // that was not there.
    //
    // `exitWith` rather than `continue`: this is the turn's body called by
    // cti_fnc_everyInterval and not the loop itself, and the heartbeat is
    // already stamped above it.
    if ((_answer get "outcome") isNotEqualTo "ok") exitWith {};

    private _messages = (_answer get "result") getOrDefault ["messages", []];

    private _startedFrame = diag_frameNo;
    private _applied = 0;
    private _highest = -1;
    // What this drain refused for good, carried into the acknowledgement so
    // the daemon writes the row: the world's log is the world's, and a dead
    // letter is a fact about the Campaign that belongs in its record too.
    private _dead = [];
    {
        private _sequence = _x getOrDefault ["sequence", -1];
        private _message = _x getOrDefault ["message", createHashMap];
        private _verdict = [_message] call cti_fnc_effectApply;
        private _outcome = _verdict getOrDefault ["outcome", "deferred"];

        // A transient failure stops the drain rather than being acknowledged
        // past it: sequences are acknowledged through a high-water mark, so
        // skipping one would retire it unapplied.
        if (_outcome isEqualTo "deferred") exitWith {
            _drain set ["deferred", (_drain get "deferred") + 1];
            private _key = str _sequence;
            private _times = (_deferrals getOrDefault [_key, 0]) + 1;
            _deferrals set [_key, _times];
            diag_log format ["CTI|effect_deferred sequence=%1 reason=%2 times=%3",
                _sequence, _verdict getOrDefault ["reason", ""], _times];
            // Said once, at the threshold: a queue that has not moved in
            // three minutes is a wedged Campaign whatever the classification
            // said, and repeating the line every poll would bury it.
            if (_times isEqualTo _stuckAfter) then {
                diag_log format ["CTI|FAIL class=assertion_failed effect_stuck sequence=%1 "
                    + "reason=%2 deferrals=%3 behind=%4",
                    _sequence, _verdict getOrDefault ["reason", ""], _times,
                    (count _messages) - _applied];
            };
        };

        if (_outcome isEqualTo "refused") then {
            // Acknowledged, not retried — and never quietly. The effect is
            // lost on purpose, which is a worse thing to be silent about
            // than the stall it replaces.
            private _reason = _verdict getOrDefault ["reason", ""];
            _drain set ["dead", (_drain get "dead") + 1];
            diag_log format ["CTI|FAIL class=assertion_failed effect_dead_letter sequence=%1 "
                + "effect=%2 side=%3 reason=%4",
                _sequence, _message getOrDefault ["effect", "?"],
                _message getOrDefault ["side", "?"], _reason];
            _dead pushBack createHashMapFromArray [
                ["sequence", _sequence],
                ["effect", _message getOrDefault ["effect", "?"]],
                ["reason", _reason]
            ];
        } else {
            _applied = _applied + 1;
        };
        _deferrals deleteAt (str _sequence);
        _highest = _sequence;
    } forEach _messages;

    if (count _messages > 0) then {
        // Frames rather than seconds: the cap this is measured against
        // is per frame, so what a drain cost is how many frames it
        // spanned and how many effects it carried in them.
        private _frames = (diag_frameNo - _startedFrame) max 1;
        _drain set ["drains", (_drain get "drains") + 1];
        _drain set ["applied", (_drain get "applied") + _applied];
        _drain set ["max", (_drain get "max") max _applied];
        _drain set ["maxFrames", (_drain get "maxFrames") max _frames];
        diag_log format ["CTI|effect_drain handed=%1 applied=%2 dead=%3 frames=%4 max=%5",
            count _messages, _applied, count _dead, _frames, _drain get "max"];
    };

    if (_highest >= 0) then {
        // The acknowledgement's own reply is read rather than dropped: it
        // is what retires the prefix, and an ack that never arrived leaves
        // the same effects to be applied twice on the next drain.
        private _acked = [
            format ["ack-%1", _highest], "ack",
            createHashMapFromArray [["through", _highest], ["dead", _dead]]
        ] call cti_fnc_daemonCall;
        if ((_acked get "outcome") isEqualTo "ok") then {
            diag_log format ["CTI|effects_acked through=%1", _highest];
        } else {
            diag_log format ["CTI|effects_ack_unconfirmed through=%1 outcome=%2",
                _highest, _acked get "outcome"];
        };
    };
}] call cti_fnc_everyInterval
