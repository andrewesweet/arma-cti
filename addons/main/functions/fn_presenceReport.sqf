/*
 * Author: arma-cti
 * Reports what the world can see to the daemon on a loop. Runs on the server.
 *
 * Five things only, because they are the five nothing else can see: who is
 * standing inside each Objective's capture radius, what has become of each
 * Squad, what each side's leaders have seen of the other (#28), whether
 * each Base's HQ structure is still standing (#33), and who has died since the
 * last report (#39). The rest —
 * ownership, Funds, Orders, and what a sighting means — is the daemon's
 * (ADR-0012). The reply is the return leg on the same call rather than a second
 * channel with a cadence of its own — and it is the public picture alone (#27):
 * Objective ownership, which is what the markers are painted from. The server
 * is not a Commander, so no side's Funds, Squads or standing Orders cross to
 * it; a Commander's own view reaches its own client, and that is #18.
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
                ["squads", call cti_fnc_squadSample],
                ["contacts", call cti_fnc_contactSample],
                ["hq", call cti_fnc_hqSample],
                ["casualties", call cti_fnc_casualtySample]
            ]]
        ];

        private _raw = (_extension callExtension ["rpc_keepalive", [toJSON _envelope]]) # 0;

        // The engine caps a callExtension return at 10,240 bytes and truncates
        // in silence (ADR-0004). The public picture grows with the map's
        // Objective count rather than with the Campaign, so it has room to
        // spare on Stratis and is still worth watching on a bigger island.
        // Failing at nine tenths means it is found to be outgrowing one call
        // while there is still room to make it smaller — which is the fix, not
        // a chunking protocol invented in passing.
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
