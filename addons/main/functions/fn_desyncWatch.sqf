/*
 * Author: arma-cti
 * Watches connected clients for desync and returns a verdict, for issue #8.
 *
 * The phase-0 symptom was a Windows client that spawned, could not move, and
 * reported "No message received after N seconds" while the server logged
 * nothing at all. "A client stays responsive for a sustained period" was
 * therefore a subjective acceptance criterion. This makes it mechanical: sample
 * every connected non-headless user's desync over a window and report the worst
 * reading, so a config change can be judged rather than felt.
 *
 * Runs on the server; the client is where the symptom shows but the server is
 * the only place that can measure it. Every line goes to stdout, because a
 * Linux server writes no RPT file (ADR-0006).
 *
 * Arguments:
 * 0: how long to watch, in seconds <NUMBER> (optional, default 300)
 * 1: seconds between samples <NUMBER> (optional, default 5)
 *
 * Return Value: <SCRIPT> the watching thread. Its verdict lines are the result.
 */
params [["_window", 300, [0]], ["_interval", 5, [0]]];

if (!isServer) exitWith { scriptNull };

[_window, _interval] spawn {
    params ["_window", "_interval"];

    private _deadline = diag_tickTime + _window;
    private _worst = createHashMap;
    private _samplesTaken = 0;
    private _sawAnyone = false;

    while { diag_tickTime < _deadline } do {
        // Suspends until the next frame rather than spinning, and never a
        // fixed sleep — the CLAUDE.md contract bans those in SQF outright.
        private _next = diag_tickTime + _interval;
        waitUntil { diag_tickTime >= _next || { diag_tickTime >= _deadline } };

        private _samples = call cti_fnc_networkSample;
        _samplesTaken = _samplesTaken + 1;
        {
            _x params ["_name", "_uid", "_state", "_headless", "_ping", "_bandwidth", "_desync"];
            // Every connected client counts, headless included. A headless
            // client on the server's own machine cannot show this symptom, but
            // one launched on the Windows host crosses exactly the boundary
            // under suspicion — and since the verdict is a maximum, a quiet
            // local client cannot hide a noisy remote one.
            _sawAnyone = true;
            private _key = format ["%1/%2", _name, _uid];
            _worst set [_key, ((_worst getOrDefault [_key, 0]) max _desync)];
            diag_log format [
                "CTI|desync_sample name=%1 uid=%2 headless=%3 state=%4 ping=%5 bandwidth=%6 desync=%7",
                _name, _uid, _headless, _state, _ping, _bandwidth, _desync];
        } forEach _samples;
    };

    if (!_sawAnyone) exitWith {
        // No client, no evidence. Saying "no desync" here would be the same
        // mistake as reading silence as a pass.
        diag_log format ["CTI|desync_verdict result=no_client samples=%1 window=%2",
            _samplesTaken, _window];
    };

    // `selectMax` over the readings themselves (`commands/selectMax.wiki`): the
    // verdict is the worst any one client saw, and the accumulator that said so
    // was four lines of the engine's own command.
    private _peak = selectMax values _worst;
    diag_log format ["CTI|desync_verdict result=%1 peak=%2 per_client=%3 samples=%4 window=%5",
        ["desynced", "steady"] select (_peak < 1), _peak, _worst, _samplesTaken, _window];
};
