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

[_interval] spawn {
    params ["_interval"];

    private _extension = call cti_fnc_shimName;
    if (_extension isEqualTo "") exitWith {
        diag_log "CTI|FAIL class=infra_unavailable effect_pump_no_shim";
    };

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

        private _envelope = createHashMapFromArray [
            ["id", format ["poll-%1", round (diag_tickTime * 1000)]],
            ["verb", "poll"]
        ];
        private _raw = (_extension callExtension ["rpc_keepalive", [toJSON _envelope]]) # 0;
        private _reply = fromJSON _raw;
        _drain set ["polls", (_drain get "polls") + 1];

        // The engine caps a callExtension return at 10,240 bytes and truncates
        // in silence (ADR-0004), and a truncated poll reply is broken JSON with
        // effects lost past the cut. The daemon bounds a drain at nine tenths of
        // the cap and hands the rest over on the next poll (#67), so this is the
        // backstop rather than the guard: reaching it means the daemon's bound
        // did not hold, which is a fault rather than a busy world.
        if (count _raw >= 9216) then {
            diag_log format ["CTI|FAIL class=assertion_failed poll_near_return_cap chars=%1",
                count _raw];
        };

        if (_reply isEqualType createHashMap) then {
            // An error reply carries no `result`, so reading messages out of it
            // would find none and the pump would look idle while the outbox
            // stalled. `oversized_message` is the one the daemon raises when a
            // single effect cannot cross one return at all (#67) — loud, and
            // the effect stays on the outbox until it is made smaller.
            private _status = _reply getOrDefault ["status", ""];
            if (_status isNotEqualTo "ok") then {
                private _error = _reply getOrDefault ["error", createHashMap];
                diag_log format ["CTI|FAIL class=assertion_failed poll_refused error=%1 detail=%2",
                    _error getOrDefault ["class", "?"],
                    _error getOrDefault ["detail", ""]];
                continue;
            };

            private _messages = (_reply getOrDefault ["result", createHashMap])
                getOrDefault ["messages", []];

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
                private _ack = createHashMapFromArray [
                    ["id", format ["ack-%1", _highest]],
                    ["verb", "ack"],
                    ["payload", createHashMapFromArray [["through", _highest]]]
                ];
                _extension callExtension ["rpc_keepalive", [toJSON _ack]];
                diag_log format ["CTI|effects_acked through=%1", _highest];
            };
        } else {
            diag_log format ["CTI|FAIL class=oracle_disagreement poll_reply_unreadable=%1", _raw];
        };
    };
};
