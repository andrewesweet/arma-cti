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

// Asked before the thread is started rather than inside it (#102): a loop enters
// the watchdog's register only once it is going to run.
private _extension = call cti_fnc_shimName;
if (_extension isEqualTo "") exitWith {
    diag_log "CTI|FAIL class=infra_unavailable presence_report_no_shim";
    scriptNull
};

// The heartbeat the watchdog reads (#102). Separate from the round-trip counters
// below: a report loop talking to a dead daemon completes no leg and is still
// alive, and only one of those two is the watchdog's business.
private _beat = ["presence_report", _interval] call cti_fnc_loopRegister;

private _reporter = [_interval, _beat] spawn {
    params ["_interval", "_beat"];

    diag_log format ["CTI|presence_report_started interval=%1", _interval];

    // The report loop's own running account, the counterpart to the effect
    // pump's `cti_effectDrain` and there for the same reason: something outside
    // the loop needs to know it has turned, and the server log is not readable
    // from inside the world. `sent` counts reports that left, `replied` reports
    // whose answer came back and was applied — so a wait on `replied` rising is
    // a wait on the whole leg, out and back, rather than on a clock (#46).
    private _turns = createHashMapFromArray [["sent", 0], ["replied", 0]];
    missionNamespace setVariable ["cti_presenceReport", _turns];

    while { true } do {
        private _next = diag_tickTime + _interval;
        waitUntil { diag_tickTime >= _next };
        _beat set ["turns", (_beat get "turns") + 1];
        _beat set ["at", diag_tickTime];

        // The whole report, built through the schema the daemon reads it with
        // (#74). Which five things the world reports and what each is called is
        // one declaration in `cti_daemon.report`, exported into the same JSON
        // the Command catalogue rides in, rather than a list here that has to
        // be kept in step with a list there.
        private _payload = ["payload", [
            ["time", time],
            ["presence", call cti_fnc_presenceSample],
            ["squads", call cti_fnc_squadSample],
            ["contacts", call cti_fnc_contactSample],
            ["hq", call cti_fnc_hqSample],
            ["casualties", call cti_fnc_casualtySample]
        ]] call cti_fnc_reportObject;

        _turns set ["sent", (_turns get "sent") + 1];
        // In-game second and real millisecond both: the daemon answers a line it
        // has already answered from its record rather than folding the report
        // twice (#69, ADR-0034), so an id has to be unique per request. In-game
        // time alone is not — it stops when the world is paused and accelerates
        // when it is not.
        private _answer = [
            format ["obs-%1-%2", round time, round (diag_tickTime * 1000)],
            "observe", _payload
        ] call cti_fnc_daemonCall;

        // `replied` means the whole leg, out and back, and now it says so. It
        // used to be incremented for any reply shaped like a HashMap — which a
        // shim transport error is (#97) — so a dead daemon counted as a
        // completed round trip and every waiter reading this counter was told
        // the loop was healthy while nothing was being reported at all.
        if ((_answer get "outcome") isNotEqualTo "ok") then { continue };

        private _owners = (_answer get "result") getOrDefault ["owners", createHashMap];
        // The daemon's view is authoritative, so the map is drawn from it
        // rather than from anything decided here.
        { [_x, _y] call cti_fnc_objectiveOwnerSet } forEach _owners;
        // Counted after the judgement has been applied, not on receipt: what
        // a waiter wants to know is that the leg completed, and the marker
        // repaint is the last thing in it.
        _turns set ["replied", (_turns get "replied") + 1];
    };
};

// The handle the watchdog reports `script_done` from (#102).
_beat set ["script", _reporter];
_reporter
