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

    while { true } do {
        private _next = diag_tickTime + _interval;
        waitUntil { diag_tickTime >= _next };

        private _envelope = createHashMapFromArray [
            ["id", format ["poll-%1", round (diag_tickTime * 1000)]],
            ["verb", "poll"]
        ];
        private _raw = (_extension callExtension ["rpc_keepalive", [toJSON _envelope]]) # 0;
        private _reply = fromJSON _raw;
        if (_reply isEqualType createHashMap) then {
            private _messages = (_reply getOrDefault ["result", createHashMap])
                getOrDefault ["messages", []];

            private _highest = -1;
            {
                private _sequence = _x getOrDefault ["sequence", -1];
                // Stop at the first failure rather than acknowledging past it:
                // sequences are acknowledged through a high-water mark, so
                // skipping one would retire it unapplied.
                if !([_x getOrDefault ["message", createHashMap]] call cti_fnc_effectApply) exitWith {
                    diag_log format ["CTI|effect_deferred sequence=%1", _sequence];
                };
                _highest = _sequence;
            } forEach _messages;

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
