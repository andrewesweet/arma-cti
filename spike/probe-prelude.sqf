// Shared probe scaffolding, appended to the generated harness by spike/run.sh
// ahead of the probe itself. It lives here rather than in spike/probes/ because
// corpus membership is by directory (docs/regression-tier.md, "What runs"): a
// file in there is a probe, and this asserts nothing.
//
// Not in the addon either. Nothing here is game code; it is what a probe needs
// to know when the world is ready to be asked questions, and the addon is the
// thing under test.
//
// The `cti_probe_fnc_` prefix keeps it out of the addon's `cti_fnc_` namespace,
// which CfgFunctions owns.

// Wait for the world to be built and for both server loops to have turned once,
// with the caller's deadline. #46 converted eight probes' identical 20 s "let
// the world finish building and the report loop get a cycle in" settles to this
// call, at the same 20 s: the settle was always a proxy for three conditions the
// world states out loud, so a passing run now leaves at ~6 s and a run in which
// a loop never turns carries on at 20 s exactly as it did before, into the same
// assertions and the same class.
//
// The three: the manifest's world is built (`cti_map` holds Objectives), the
// effect pump has polled the daemon (`cti_effectDrain`), and a presence report
// has gone out and had its judgement applied (`cti_presenceReport`, added for
// this). All three are our own counters, which is what makes waiting on them as
// good as an event — we write them.
//
// Arguments:
// 0: deadline in seconds <NUMBER> (optional, default 20 — the settle it replaced)
//
// Return Value: <NUMBER> seconds waited
cti_probe_fnc_worldReady = {
    params [["_by", 20, [0]]];

    private _from = diag_tickTime;
    private _deadline = _from + _by;
    private _polls = 0;
    private _replied = 0;
    private _objectives = 0;
    waitUntil {
        _objectives = count ((missionNamespace getVariable ["cti_map", createHashMap])
            getOrDefault ["objectives", []]);
        _polls = (missionNamespace getVariable ["cti_effectDrain", createHashMap])
            getOrDefault ["polls", 0];
        _replied = (missionNamespace getVariable ["cti_presenceReport", createHashMap])
            getOrDefault ["replied", 0];
        (_objectives > 0 && { _polls > 0 } && { _replied > 0 })
            || { diag_tickTime > _deadline }
    };

    private _waited = diag_tickTime - _from;
    // Logged rather than asserted on: this is the probe's runway, and every
    // probe that calls it has its own assertions about the world immediately
    // after. A world that was not ready in `_by` fails in those, as it did when
    // this was a sleep — the line is here so the evidence says which it was.
    diag_log format ["CTI|probe_world_ready waited=%1 deadline=%2 objectives=%3 polls=%4 reports=%5",
        _waited, _by, _objectives, _polls, _replied];
    _waited
};
