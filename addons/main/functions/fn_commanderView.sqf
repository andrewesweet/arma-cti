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
#include "\cti\addons\main\script_component.hpp"

params [["_interval", 5, [0]]];

// The entry point of a supervised loop, which ADR-0041 keeps guarded: this is the
// one call site a future restart would re-enter, and the thread it starts is
// inventoried by name rather than by caller (#118).
SERVER_ONLY(scriptNull);

// Asked before the thread is started rather than inside it (#102): a loop enters
// the watchdog's register only once it is going to run.
private _extension = call cti_fnc_shimName;
if (_extension isEqualTo "") exitWith {
    diag_log "CTI|FAIL class=infra_unavailable commander_view_no_shim";
    scriptNull
};

diag_log format ["CTI|commander_view_started interval=%1", _interval];

// Refusals repeat every cycle for as long as the world is set up wrongly, so
// each is said once per side rather than once per push.
private _told = createHashMap;

// Paced, heartbeated and watched by the one adapter every loop in the addon
// runs on (#85).
["commander_view", _interval, [_told], {
    params ["_told"];

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
            // Unique per request, for the reason cti_fnc_presenceReport gives:
            // the daemon deduplicates on the whole line (#69, ADR-0034).
            private _answer = [
                ["view", _side] call cti_fnc_requestId,
                "view", createHashMapFromArray [["side", _side]]
            ] call cti_fnc_daemonCall;

            switch (_answer get "outcome") do {
                case "ok": {
                    _told deleteAt _side;
                    [_answer get "result"] remoteExec ["cti_fnc_mapObservation", _target];
                };
                // A side under an AI Commander has no view to hand out and the
                // daemon refuses it. That is a Commander's mistake, so it goes
                // to the client that caused it in the port's own rejection
                // vocabulary — said once per side, because the refusal repeats
                // for as long as the world is set up wrongly.
                case "rejected": {
                    if !(_side in _told) then {
                        private _reason = _answer get "reason";
                        _told set [_side, true];
                        diag_log format ["CTI|commander_view_refused side=%1 code=%2 detail=%3",
                            _side,
                            _reason getOrDefault ["code", "?"],
                            _reason getOrDefault ["detail", ""]];
                        [_answer get "reply"] remoteExec ["cti_fnc_portReply", _target];
                    };
                };
                // Anything else is the daemon failing or absent, and it has
                // already been classified and logged by the call. It is
                // emphatically not forwarded: a shim error object used to take
                // this branch and be pushed to the human as if it were a port
                // judgement, rendering as `? — ? —` (#97).
                default {};
            };
        };
    } forEach _assigned;
}] call cti_fnc_everyInterval
