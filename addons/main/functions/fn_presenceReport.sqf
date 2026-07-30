/*
 * Author: arma-cti
 * Reports presence to the daemon on a loop. Runs on the server.
 *
 * The report carries the in-game time rather than letting the daemon read a
 * clock. `time` stops when the Play Session does, so income accruing only
 * during a session falls out of the unit rather than needing a rule — and a
 * daemon whose clock is an argument is one whose rules can be tested.
 *
 * Sent on the synchronous path: the daemon's answer is a judgement about what
 * was reported and never waits on work, so it stays far inside the engine's
 * 1000 ms blocking-call stall cap (ADR-0005). The captures it produces come
 * back through the outbox like every other effect.
 *
 * Arguments:
 * 0: seconds between reports <NUMBER> (optional, default 5)
 *
 * Return Value: <SCRIPT> the reporting thread
 */
params [["_interval", 5, [0]]];

if (!isServer) exitWith { scriptNull };

[_interval] spawn {
    params ["_interval"];

    private _extension = call cti_fnc_shimName;
    if (_extension isEqualTo "") exitWith {
        diag_log "CTI|FAIL class=infra_unavailable presence_report_no_shim";
    };

    diag_log format ["CTI|presence_report_started interval=%1", _interval];

    while { true } do {
        private _next = diag_tickTime + _interval;
        waitUntil { diag_tickTime >= _next };

        private _envelope = createHashMapFromArray [
            ["id", format ["obs-%1", round time]],
            ["verb", "observe"],
            ["payload", createHashMapFromArray [
                ["time", time],
                ["presence", call cti_fnc_presenceSample]
            ]]
        ];

        private _raw = (_extension callExtension ["rpc_keepalive", [toJSON _envelope]]) # 0;
        private _reply = fromJSON _raw;
        if (_reply isEqualType createHashMap) then {
            private _owners = (_reply getOrDefault ["result", createHashMap])
                getOrDefault ["owners", createHashMap];
            // The daemon's view is authoritative, so the map is drawn from it
            // rather than from anything decided here.
            { [_x, _y] call cti_fnc_objectiveOwnerSet } forEach _owners;
        } else {
            diag_log format ["CTI|FAIL class=oracle_disagreement observe_reply_unreadable=%1", _raw];
        };
    };
};
