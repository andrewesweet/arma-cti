// probe: daemon-restart
// issues: 96, 97
// window: 150
// env: CTI_DAEMON_RESTART_ON=daemon_restart_probe_armed
// expect: node_crashed
//
// #96 and #97 in-world probe, RED BY DESIGN. A green run of this probe is the
// bug: it means the daemon was killed and restarted under a live Campaign and
// the world played on as if nothing had happened.
//
// `expect:` inverts the verdict for the regression tier, as it does for
// `manifest-missing`. The class here is `node_crashed`, because that is what
// cti_fnc_campaignLost logs and what the world is being asked to conclude: the
// process holding the whole Campaign died, nothing in the world can recover it,
// and the run is over. A run that ends any other way — `assertion_failed` from
// the probe below, or a pass — is the world failing to notice.
//
// `just regress daemon-restart`, or by hand
// `just probe spike/probes/daemon-restart.sqf`.
//
// How the fault is staged. The probe cannot kill a process, so `run.sh` does it:
// CTI_DAEMON_RESTART_ON names a line the probe writes, and when that line
// appears the harness kills the daemon, starts a fresh one on the same port and
// waits for its readiness line. Triggered on the probe's own line rather than on
// a clock, because the probe is what knows when it has a baseline worth losing.
//
// What the world is supposed to do about it, and what is asserted here:
//
//   during the outage   the shim answers `{"error": "..."}`, which is a HashMap
//                       and used to pass every loop's only type check as an
//                       empty success (#97). cti_fnc_daemonCall must call it
//                       `unreachable`, latch cti_daemon_down, and refuse to
//                       count the leg as replied.
//   after the restart   the fresh daemon carries a different epoch (#96). The
//                       world latched the first one it saw, so the change is
//                       visible, and the response is to freeze: cti_campaign_lost
//                       is set and every later call is refused without touching
//                       the wire, so no marker repaints to a stranger's Campaign.
//
// The evidence is gathered in the same frame the latch fires in. The harness
// stops waiting at the first FAIL line, so anything this probe wanted to say
// after a `waitUntil` that the latch ended would be a line in a log nobody read.
[] spawn {
    [20] call cti_probe_fnc_worldReady;

    // The world must already know who it is talking to. If this is empty the
    // epoch never reached the world at all and everything below is untestable,
    // so it is checked before the daemon is killed rather than inferred from
    // the silence afterwards.
    private _epoch = missionNamespace getVariable ["cti_daemon_epoch", ""];
    if (_epoch isEqualTo "") exitWith {
        diag_log "CTI|FAIL class=assertion_failed daemon_restart_probe_no_epoch_latched";
    };

    private _turns = missionNamespace getVariable ["cti_presenceReport", createHashMap];
    private _tally = missionNamespace getVariable ["cti_daemonCall", createHashMap];
    private _sentAtArm = _turns getOrDefault ["sent", 0];
    private _repliedAtArm = _turns getOrDefault ["replied", 0];

    // The line run.sh is waiting for. Everything after this happens against a
    // daemon that is dying or dead.
    diag_log format ["CTI|daemon_restart_probe_armed epoch=%1 sent=%2 replied=%3",
        _epoch, _sentAtArm, _repliedAtArm];

    // The probe does its own calling rather than watching the loops, for one
    // reason: the loops turn every 2 s and 5 s, and an outage shorter than a
    // report interval would make an assertion about the report loop vacuous.
    // A ping per frame is guaranteed to meet the outage.
    private _pings = 0;
    private _unreachable = 0;
    private _deadline = diag_tickTime + 60;
    waitUntil {
        _pings = _pings + 1;
        private _answer = [format ["restart-probe-%1", _pings], "ping"] call cti_fnc_daemonCall;
        if ((_answer get "outcome") isEqualTo "unreachable") then { _unreachable = _unreachable + 1 };
        _unreachable > 0 || { diag_tickTime > _deadline }
    };
    if (_unreachable isEqualTo 0) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed daemon_restart_probe_outage_unseen pings=%1",
            _pings];
    };
    private _repliedWhileDown = (missionNamespace getVariable ["cti_presenceReport", createHashMap])
        getOrDefault ["replied", 0];
    diag_log format ["CTI|daemon_restart_probe_saw_outage pings=%1 unreachable=%2 down=%3 replied=%4",
        _pings, _unreachable,
        missionNamespace getVariable ["cti_daemon_down", false], _repliedWhileDown];
    if !(missionNamespace getVariable ["cti_daemon_down", false]) exitWith {
        diag_log "CTI|FAIL class=assertion_failed daemon_restart_probe_outage_not_latched";
    };

    // Now the restart. The first call that reaches the fresh daemon is the one
    // that sees the new epoch, and it is this one, which is what puts the latch
    // and the evidence below in the same frame.
    _deadline = diag_tickTime + 90;
    waitUntil {
        _pings = _pings + 1;
        [format ["restart-probe-%1", _pings], "ping"] call cti_fnc_daemonCall;
        (missionNamespace getVariable ["cti_campaign_lost", false]) || { diag_tickTime > _deadline }
    };
    if !(missionNamespace getVariable ["cti_campaign_lost", false]) exitWith {
        // The whole point of #96, failing: the daemon was reborn and the world
        // went on playing against a Campaign it had never been in.
        diag_log format ["CTI|FAIL class=assertion_failed daemon_restart_probe_world_never_noticed "
            + "epoch_was=%1 epoch_now=%2 pings=%3",
            _epoch,
            missionNamespace getVariable ["cti_daemon_epoch", ""],
            _pings];
    };

    // Synchronous from here. cti_fnc_campaignLost has just written the run's
    // verdict line, and the harness is already on its way to reading the log.
    private _callsBefore = (missionNamespace getVariable ["cti_daemonCall", createHashMap])
        getOrDefault ["calls", 0];
    private _frozen = ["restart-probe-frozen", "ping"] call cti_fnc_daemonCall;
    private _callsAfter = (missionNamespace getVariable ["cti_daemonCall", createHashMap])
        getOrDefault ["calls", 0];
    _turns = missionNamespace getVariable ["cti_presenceReport", createHashMap];
    _tally = missionNamespace getVariable ["cti_daemonCall", createHashMap];

    diag_log format ["CTI|daemon_restart_probe_frozen outcome=%1 wire_calls_before=%2 after=%3",
        _frozen get "outcome", _callsBefore, _callsAfter];
    diag_log format ["CTI|daemon_restart_probe_counters sent=%1 replied=%2 replied_at_arm=%3 "
        + "replied_while_down=%4 calls=%5 ok=%6 unreachable=%7",
        _turns getOrDefault ["sent", 0], _turns getOrDefault ["replied", 0],
        _repliedAtArm, _repliedWhileDown,
        _tally getOrDefault ["calls", 0], _tally getOrDefault ["ok", 0],
        _tally getOrDefault ["unreachable", 0]];

    // A frozen world does not talk to the daemon at all: the refusal is local,
    // so the call count must not have moved.
    if ((_frozen get "outcome") isNotEqualTo "campaign_lost" || { _callsAfter != _callsBefore }) then {
        diag_log format ["CTI|FAIL class=assertion_failed daemon_restart_probe_not_frozen "
            + "outcome=%1 calls_before=%2 calls_after=%3",
            _frozen get "outcome", _callsBefore, _callsAfter];
    };
    // A failed leg is not a completed leg (#97). Vacuous only if the report loop
    // did not turn inside the outage, and the numbers above say which it was.
    if ((_turns getOrDefault ["replied", 0]) > _repliedWhileDown) then {
        diag_log format ["CTI|FAIL class=assertion_failed daemon_restart_probe_counted_a_dead_leg "
            + "replied_while_down=%1 replied_now=%2",
            _repliedWhileDown, _turns getOrDefault ["replied", 0]];
    };

    diag_log "CTI|daemon_restart_probe_done";
};
