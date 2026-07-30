/*
 * Author: arma-cti
 * Reports what the world can see to the daemon on a loop. Runs on the server.
 *
 * Two things only, because they are the two nothing else can see: who is
 * standing inside each Objective's capture radius, and what has become of each
 * Squad. The reply is the whole strategic picture (#15) — ownership, Funds and
 * every Squad's standing Order — so the return leg is this call's answer rather
 * than a second channel with a cadence of its own.
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
                ["presence", call cti_fnc_presenceSample],
                ["squads", call cti_fnc_squadSample]
            ]]
        ];

        private _raw = (_extension callExtension ["rpc_keepalive", [toJSON _envelope]]) # 0;

        // The engine caps a callExtension return at 10,240 bytes and truncates
        // in silence (ADR-0004). The reply carries the whole strategic picture
        // (#15), so it is the one reply that can grow into that cap. Failing at
        // nine tenths of it means the observation is found to be outgrowing one
        // call while there is still room to make it smaller — which is the fix,
        // not a chunking protocol invented in passing.
        if (count _raw >= 9216) then {
            diag_log format ["CTI|FAIL class=assertion_failed observation_near_return_cap chars=%1", count _raw];
        };

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
