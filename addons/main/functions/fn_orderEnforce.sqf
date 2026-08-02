/*
 * Author: arma-cti
 * Keeps standing Orders standing. Runs on the server.
 *
 * The engine completes a waypoint and moves on; an Order does not (#14). A
 * Squad that finished searching an Objective, or that chased a contact off it,
 * has stopped doing what it was told while still being under orders to do it.
 * This sweep notices that and re-asserts the Order — which is also what carries
 * an Order across a leader's death once the engine has promoted a replacement.
 *
 * Re-asserted only when the Squad has run out of waypoints *and* has drifted
 * off the ground it was sent to. Standing on the Objective with nothing left to
 * do is a Squad obeying its Order, and resetting it every sweep would interrupt
 * the AI for nothing.
 *
 * Arguments:
 * 0: seconds between sweeps <NUMBER> (optional, default 10)
 *
 * Return Value: <SCRIPT> the sweep thread
 */
params [["_interval", 10, [0]]];

if (!isServer) exitWith { scriptNull };

// The heartbeat the watchdog reads (#102), registered before the thread starts
// so the handle can be written onto it without a race.
private _beat = ["order_enforce", _interval] call cti_fnc_loopRegister;

private _sweep = [_interval, _beat] spawn {
    params ["_interval", "_beat"];

    diag_log format ["CTI|order_enforce_started interval=%1", _interval];

    while { true } do {
        private _next = diag_tickTime + _interval;
        waitUntil { diag_tickTime >= _next };
        _beat set ["turns", (_beat get "turns") + 1];
        _beat set ["at", diag_tickTime];

        private _squads = missionNamespace getVariable ["cti_squads", createHashMap];
        private _lost = [];

        {
            private _squadId = _x;
            private _group = _y;

            if (isNull _group || { count units _group isEqualTo 0 }) then {
                _lost pushBack _squadId;
            } else {
                private _standing = _group getVariable ["cti_order", createHashMap];
                if (count _standing > 0) then {
                    private _done = (currentWaypoint _group) >= (count waypoints _group);
                    private _adrift = (leader _group distance2D (_standing get "position"))
                        > (_standing get "radius");
                    if (_done && _adrift) then {
                        [_squadId, _standing get "order", _standing get "place"]
                            call cti_fnc_orderApply;
                        diag_log format ["CTI|order_reasserted squad=%1 order=%2 leader=%3",
                            _squadId, _standing get "order", name leader _group];
                    };
                };
            };
        } forEach _squads;

        // Deleted after the sweep rather than during it: a HashMap being walked
        // is not one to remove keys from.
        {
            _squads deleteAt _x;
            diag_log format ["CTI|squad_lost squad=%1", _x];
        } forEach _lost;
    };
};

// The handle the watchdog reports `script_done` from, and the one #102's probe
// terminates to prove it does.
_beat set ["script", _sweep];
_sweep
