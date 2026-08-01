/*
 * Author: arma-cti
 * Carries each human Commander its own Observation. Runs on the server.
 *
 * Commander symmetry covers knowing as well as commanding (ADR-0012, amended
 * for #27), so the human reads the same `Campaign.observation(side)` the
 * in-process planner does. The daemon serves it under the `view` transport verb
 * and it is a projection by construction: that side's Funds, that side's Squads,
 * what that side has seen of the other as Contacts (#28), and the public
 * scoreboard of Objective ownership and Base HQ status (#35). There is no
 * unprojected picture for this to have asked for by mistake.
 *
 * The server asks and forwards; it never reads. `observe` already gives it the
 * public picture, which is all it needs to paint markers, and a server holding a
 * Commander's view would be an unprojected board sitting on the one machine both
 * Commanders talk to.
 *
 * Server-to-client remoteExec is unrestricted, so this needs nothing added to
 * the mission's mode=1 whitelist — the whitelist binds clients, and the only
 * thing on it stays the gateway (ADR-0012). Same direction and same reason as
 * cti_fnc_portReply.
 *
 * A side under an AI Commander has no view to hand out and the daemon refuses
 * it. That refusal is a Commander's mistake rather than a fault, so it goes to
 * the client that caused it through cti_fnc_portReply, in the port's own
 * rejection vocabulary — there is no human-only error channel.
 *
 * Arguments:
 * 0: seconds between pushes <NUMBER> (optional, default 5)
 *
 * Return Value: <SCRIPT> the push thread
 */
params [["_interval", 5, [0]]];

if (!isServer) exitWith { scriptNull };

[_interval] spawn {
    params ["_interval"];

    private _extension = call cti_fnc_shimName;
    if (_extension isEqualTo "") exitWith {
        diag_log "CTI|FAIL class=infra_unavailable commander_view_no_shim";
    };

    diag_log format ["CTI|commander_view_started interval=%1", _interval];

    // Refusals repeat every cycle for as long as the world is set up wrongly, so
    // each is said once per side rather than once per push.
    private _told = createHashMap;

    while { true } do {
        private _next = diag_tickTime + _interval;
        waitUntil { diag_tickTime >= _next };

        private _assigned = missionNamespace getVariable ["cti_commanders", createHashMap];
        {
            private _side = _x;
            private _uid = _y;

            // The Commander's current machine. Resolved per push because a
            // reconnection is a new machine id and the same Commander.
            private _target = 0;
            {
                if (getPlayerUID _x isEqualTo _uid) exitWith { _target = owner _x };
            } forEach allPlayers;

            if (_target > 0) then {
                private _envelope = createHashMapFromArray [
                    // Unique per request, for the reason cti_fnc_presenceReport
                    // gives: the daemon deduplicates on the whole line (#69,
                    // ADR-0034) and in-game time is not a clock that only
                    // advances.
                    ["id", format ["view-%1-%2", _side, round (diag_tickTime * 1000)]],
                    ["verb", "view"],
                    ["payload", createHashMapFromArray [["side", _side]]]
                ];
                private _raw = (_extension callExtension ["rpc_keepalive", [toJSON _envelope]]) # 0;

                // The engine caps a callExtension return at 10,240 bytes and
                // truncates in silence (ADR-0004). A Commander's view is the
                // observation most able to outgrow one call — and the fix when
                // it does is a smaller view, never a chunking protocol invented
                // in passing. This is the backstop rather than the guard: the
                // budget is enforced per map in `just unit` (ADR-0030), because
                // Contacts are keyed by place and so a view's size is settled by
                // the manifest before either side has bought anything.
                if (count _raw >= 9216) then {
                    diag_log format ["CTI|FAIL class=assertion_failed view_near_return_cap side=%1 chars=%2",
                        _side, count _raw];
                };

                private _reply = fromJSON _raw;
                if (_reply isEqualType createHashMap) then {
                    if ((_reply getOrDefault ["status", ""]) isEqualTo "ok") then {
                        _told deleteAt _side;
                        [_reply getOrDefault ["result", createHashMap]]
                            remoteExec ["cti_fnc_mapObservation", _target];
                    } else {
                        private _reason = _reply getOrDefault ["reason", createHashMap];
                        if (_side in _told) then { continue };
                        _told set [_side, true];
                        diag_log format ["CTI|commander_view_refused side=%1 code=%2 detail=%3",
                            _side,
                            _reason getOrDefault ["code", "?"],
                            _reason getOrDefault ["detail", ""]];
                        [_reply] remoteExec ["cti_fnc_portReply", _target];
                    };
                } else {
                    diag_log format ["CTI|FAIL class=oracle_disagreement view_reply_unreadable=%1", _raw];
                };
            };
        } forEach _assigned;
    };
};
