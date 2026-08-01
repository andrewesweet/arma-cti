// Holds the world open for a human play session, and nothing else.
//
// Deliberately **not** in spike/probes/: `just regress` runs every .sqf in that
// directory, and a fixture whose whole job is to sit for half an hour would add
// half an hour of nothing to every corpus run. It asserts nothing, so it is not
// a probe — it is the thing `just probe` needs in order to keep a world up.
//
// Why it exists at all: without a harness extra, `--hold` waits for a client to
// connect, sees it enter the mission, and then tears the world down. That is
// right for the join test hold mode was built for and useless for a playtest.
// `just probe <file>` waits instead for a line containing `probe_done`, so the
// window a person plays in is this file's window.
//
// The wait is not a timeout stretched to make anything pass: the subject *is* a
// person playing for a set time, and the only two ways that ends are the clock
// running out or the Campaign being won. It is sized by CTI_PROBE_SOAK so the
// session length lives on the boot line rather than in this file.
//
// Runs on the server: initServer.sqf is what compiles the harness.
[] spawn {
    private _window = 1800;
    if (!isNil "CTI_PROBE_SOAK" && { CTI_PROBE_SOAK > 0 }) then { _window = CTI_PROBE_SOAK };
    private _deadline = diag_tickTime + _window;
    diag_log format ["CTI|playtest_session opened window=%1", _window];

    // A won Campaign ends the session early — there is nothing left to play, and
    // #35 broadcasts the outcome the moment it is decided.
    waitUntil { !isNil "cti_campaignOutcome" || { diag_tickTime > _deadline } };

    diag_log format ["CTI|playtest_session probe_done reason=%1 at=%2",
        ["window_closed", "campaign_won"] select (!isNil "cti_campaignOutcome"),
        round diag_tickTime];
};
