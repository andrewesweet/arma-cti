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
 * Nothing is acknowledged until it has been carried out. An effect that fails
 * to apply stays on the outbox and comes back, rather than being lost between
 * the two.
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
params [["_interval", 2, [0]]];

if (!isServer) exitWith { scriptNull };

// Asked before the thread is started rather than inside it (#102): a loop enters
// the watchdog's register only once it is going to run, so a world with no shim
// gets this one `infra_unavailable` line and no pump rather than a registered
// pump the watchdog then reports dead thirty seconds later.
private _extension = call cti_fnc_shimName;
if (_extension isEqualTo "") exitWith {
    diag_log "CTI|FAIL class=infra_unavailable effect_pump_no_shim";
    scriptNull
};

// The heartbeat the watchdog reads (#102). Separate from `cti_effectDrain`
// below, because that counts what the wire carried and this counts that the loop
// is alive at all — a pump polling a dead daemon drains nothing and is turning.
private _beat = ["effect_pump", _interval] call cti_fnc_loopRegister;

private _pump = [_interval, _beat] spawn {
    params ["_interval", "_beat"];

    diag_log format ["CTI|effect_pump_started interval=%1", _interval];

    // The push path's running account, for whatever wants to read it back —
    // #17's probe does. Held in the mission namespace rather than logged alone,
    // because a probe cannot read the server log it is writing into.
    private _drain = createHashMapFromArray [
        ["polls", 0], ["drains", 0], ["applied", 0], ["max", 0], ["maxFrames", 0], ["deferred", 0]
    ];
    missionNamespace setVariable ["cti_effectDrain", _drain];

    while { true } do {
        private _next = diag_tickTime + _interval;
        waitUntil { diag_tickTime >= _next };
        _beat set ["turns", (_beat get "turns") + 1];
        _beat set ["at", diag_tickTime];

        private _answer = [
            format ["poll-%1", round (diag_tickTime * 1000)], "poll"
        ] call cti_fnc_daemonCall;
        _drain set ["polls", (_drain get "polls") + 1];

        // Every outcome that is not `ok` has already been classified and logged
        // by the call (#97): a shim error reply used to reach here shaped like a
        // HashMap with no `result` in it, so the pump read no messages, counted
        // the poll and looked healthy while the outbox stalled behind a daemon
        // that was not there.
        if ((_answer get "outcome") isNotEqualTo "ok") then { continue };

        private _messages = (_answer get "result") getOrDefault ["messages", []];

        private _startedFrame = diag_frameNo;
        private _applied = 0;
        private _highest = -1;
        {
            private _sequence = _x getOrDefault ["sequence", -1];
            // Stop at the first failure rather than acknowledging past it:
            // sequences are acknowledged through a high-water mark, so
            // skipping one would retire it unapplied.
            if !([_x getOrDefault ["message", createHashMap]] call cti_fnc_effectApply) exitWith {
                _drain set ["deferred", (_drain get "deferred") + 1];
                diag_log format ["CTI|effect_deferred sequence=%1", _sequence];
            };
            _applied = _applied + 1;
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
            diag_log format ["CTI|effect_drain handed=%1 applied=%2 frames=%3 max=%4",
                count _messages, _applied, _frames, _drain get "max"];
        };

        if (_highest >= 0) then {
            // The acknowledgement's own reply is read rather than dropped: it
            // is what retires the prefix, and an ack that never arrived leaves
            // the same effects to be applied twice on the next drain.
            private _acked = [
                format ["ack-%1", _highest], "ack",
                createHashMapFromArray [["through", _highest]]
            ] call cti_fnc_daemonCall;
            if ((_acked get "outcome") isEqualTo "ok") then {
                diag_log format ["CTI|effects_acked through=%1", _highest];
            } else {
                diag_log format ["CTI|effects_ack_unconfirmed through=%1 outcome=%2",
                    _highest, _acked get "outcome"];
            };
        };
    };
};

// The handle the watchdog reports `script_done` from, and the one a probe
// terminates to prove it does (#102). Written here because `spawn` is the only
// thing that has it and the body cannot be given it without a race.
_beat set ["script", _pump];
_pump
