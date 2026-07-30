// Phase-0 spike harness. Runs on the dedicated server only.
// Every result line is prefixed SPIKE| so the harness can grep the RPT.

CTI_SPIKE_LOG = { diag_log ("SPIKE|" + _this) };

// Connection diagnostics: without these a client that connects but never enters
// the mission is indistinguishable from one that never connected at all.
onPlayerConnected {
    diag_log format ["SPIKE|player_connected name=%1 id=%2 uid=%3 owner=%4 jip=%5",
        _name, _id, _uid, _owner, _jip];
};
onPlayerDisconnected {
    diag_log format ["SPIKE|player_disconnected name=%1 id=%2", _name, _id];
};

// A human client reports its own shim probe here, so the Windows .dll load test
// and the join test produce one log rather than two.
"cti_spike_client_report" addPublicVariableEventHandler {
    diag_log format ["SPIKE|client_report %1", _this # 1];
};

("mission_running tickTime=" + str diag_tickTime) call CTI_SPIKE_LOG;
("server_version=" + str productVersion) call CTI_SPIKE_LOG;

// ---------------------------------------------------------------- addon functions
// CfgFunctions compiles on every machine that loads the addon, so a name that
// does not resolve here means the addon never loaded — the check that issue #9
// asks for, on a dedicated server rather than in the editor.
//
// The PRNG assertions run here because SQF has no offline runtime tier
// (ADR-0011 rejects SQF-VM), so determinism, seed truncation and the inclusive
// upper bound can only be checked against the live engine.
if (isNil "cti_fnc_prngSelfTest") then {
    "FAIL class=assertion_failed addon_functions_unresolved" call CTI_SPIKE_LOG;
} else {
    private _prngFailures = call cti_fnc_prngSelfTest;
    if (_prngFailures isEqualTo []) then {
        (format ["prng_selftest=pass shim_name_fn=%1", call cti_fnc_shimName]) call CTI_SPIKE_LOG;
    } else {
        (format ["FAIL class=assertion_failed prng_selftest=%1", _prngFailures]) call CTI_SPIKE_LOG;
    };
};

// ---------------------------------------------------------------- extension name
// The engine appends _x64 on the 64-bit Linux server exactly as it does on
// Windows, so SQF says "cti_shim" and the engine opens cti_shim_x64.so.
private _ext = "";
{
    if (_ext isEqualTo "") then {
        private _probe = _x callExtension ["ping", []];
        (format ["probe name=%1 result=%2", _x, _probe]) call CTI_SPIKE_LOG;
        if ((_probe # 0) isEqualTo "pong") then { _ext = _x };
    };
} forEach ["cti_shim", "cti_shim_x64"];

if (_ext isEqualTo "") exitWith {
    "FAIL extension_not_loaded" call CTI_SPIKE_LOG;
    "done" call CTI_SPIKE_LOG;
};
("extension_name=" + _ext) call CTI_SPIKE_LOG;
("string_form_ping=" + (_ext callExtension "ping")) call CTI_SPIKE_LOG;

// ---------------------------------------------------------------- FFI overhead
// callExtension is synchronous, so 2000 no-I/O calls in one frame amortise the
// engine-side marshalling cost past diag_tickTime's resolution.
private _iterations = 2000;
private _t0 = diag_tickTime;
for "_i" from 1 to _iterations do { _ext callExtension "ping" };
private _stringUs = ((diag_tickTime - _t0) * 1e6) / _iterations;

_t0 = diag_tickTime;
for "_i" from 1 to _iterations do { _ext callExtension ["ping", []] };
private _arrayUs = ((diag_tickTime - _t0) * 1e6) / _iterations;

(format ["ffi_us_per_call string=%1 array=%2 iterations=%3", _stringUs, _arrayUs, _iterations]) call CTI_SPIKE_LOG;

// ---------------------------------------------------------------- daemon round trip
// Measured inside the extension: SQF's clock is too coarse for a single call.
// The shim times the round trip but does not decide what is asked, so the
// payload is a request the daemon actually answers.
private _benchPayload = "{""id"":""spike-bench"",""verb"":""ping""}";
("bench_fresh=" + ((_ext callExtension ["bench", [50, false, _benchPayload]]) # 0)) call CTI_SPIKE_LOG;
("bench_keepalive=" + ((_ext callExtension ["bench", [50, true, _benchPayload]]) # 0)) call CTI_SPIKE_LOG;

// One synchronous call in the daemon's real envelope, to prove the id survives
// the round trip: the shim's own transport errors carry no `status`, so a reply
// that has one came from the daemon and can be matched to the request.
private _sync = _ext callExtension ["rpc_keepalive", ["{""id"":""spike-1"",""verb"":""ping""}"]];
("sync_reply=" + str _sync) call CTI_SPIKE_LOG;

private _quote = """";
private _echoedId = _quote + "id" + _quote + ":" + _quote + "spike-1" + _quote;
if (((_sync # 0) find _echoedId) < 0) then {
    "FAIL class=assertion_failed daemon_did_not_echo_the_request_id" call CTI_SPIKE_LOG;
};

// ---------------------------------------------------------------- callback path
// End-to-end as gameplay sees it: callExtension returns immediately, the reply
// arrives on the next engine callback drain. Spans frames, so diag_tickTime is fine.
cti_spike_sent = createHashMap;
cti_spike_latencies = [];

addMissionEventHandler ["ExtensionCallback", {
    params ["_name", "_function", "_data"];
    if (_name isNotEqualTo "cti_shim") exitWith {};
    private _sentAt = cti_spike_sent getOrDefault [_function, -1];
    if (_sentAt < 0) exitWith {
        diag_log format ["SPIKE|callback_unmatched function=%1", _function];
    };
    cti_spike_latencies pushBack ((diag_tickTime - _sentAt) * 1000);
}];

private _callbacks = 20;
for "_i" from 1 to _callbacks do {
    private _id = format ["job%1", _i];
    cti_spike_sent set [_id, diag_tickTime];
    _ext callExtension ["rpc_async", [_id, format ["{""id"":""%1"",""verb"":""ping""}", _id]]];
};

// Bounded wait with an explicit timeout verdict — never a blind sleep that
// hides a hang (CLAUDE.md contract).
private _deadline = diag_tickTime + 30;
waitUntil { (count cti_spike_latencies >= _callbacks) || (diag_tickTime > _deadline) };

if (count cti_spike_latencies < _callbacks) then {
    (format ["FAIL class=timeout callbacks_received=%1 expected=%2",
        count cti_spike_latencies, _callbacks]) call CTI_SPIKE_LOG;
} else {
    private _sorted = +cti_spike_latencies;
    _sorted sort true;
    private _n = count _sorted;
    private _sum = 0;
    { _sum = _sum + _x } forEach _sorted;
    (format ["callback_ms n=%1 min=%2 p50=%3 max=%4 mean=%5",
        _n, _sorted # 0, _sorted # (floor (_n / 2)), _sorted # (_n - 1), _sum / _n]) call CTI_SPIKE_LOG;
};

// ---------------------------------------------------------------- headless client
// The harness starts the HC once it sees mission_running above, so wait for it
// here rather than sampling an empty server.
// `allUsers` lists connection-level users even while `allPlayers` is empty, and
// `getUserInfo` index 6 is the client state, 7 the headless flag — so this says
// which rung a stuck client is actually on instead of leaving us to guess.
CTI_SPIKE_USERS = {
    if (isNil "allUsers") exitWith { "allUsers unavailable" };
    private _out = [];
    {
        private _info = if (isNil "getUserInfo") then { ["getUserInfo unavailable"] } else {
            getUserInfo _x
        };
        _out pushBack _info;
    } forEach allUsers;
    str _out
};

private _hcDeadline = diag_tickTime + 60;
private _hcSeenAt = -1;
private _nextProbe = 0;
waitUntil {
    if (!isNil "cti_spike_hc_online" && {_hcSeenAt < 0}) then { _hcSeenAt = diag_tickTime };
    if (diag_tickTime > _nextProbe) then {
        _nextProbe = diag_tickTime + 10;
        ("users " + ([] call CTI_SPIKE_USERS)) call CTI_SPIKE_LOG;
    };
    (_hcSeenAt > 0) || (diag_tickTime > _hcDeadline)
};
(format ["hc_online=%1 hc_owner=%2 seen_at=%3 hc_entities=%4 allplayers=%5",
    _hcSeenAt > 0,
    if (isNil "cti_spike_hc_online") then {"none"} else {str cti_spike_hc_online},
    _hcSeenAt,
    count (entities "HeadlessClient_F"),
    count allPlayers]) call CTI_SPIKE_LOG;
if (_hcSeenAt < 0) then { "WARN headless_client_never_ran_mission_scripts" call CTI_SPIKE_LOG };

// Prove the HC is usable as a synthetic-player harness: make it run code and
// report back. This is the capability the Arma test tier depends on.
if (_hcSeenAt > 0) then {
    cti_spike_hc_echo = nil;
    private _t = diag_tickTime;
    [] remoteExec ["CTI_SPIKE_HC_TASK", cti_spike_hc_online];
    private _echoDeadline = diag_tickTime + 30;
    waitUntil { !isNil "cti_spike_hc_echo" || (diag_tickTime > _echoDeadline) };
    if (isNil "cti_spike_hc_echo") then {
        "FAIL class=timeout hc_remote_exec_never_returned" call CTI_SPIKE_LOG;
    } else {
        (format ["hc_remote_exec_ms=%1 payload=%2",
            (diag_tickTime - _t) * 1000, str cti_spike_hc_echo]) call CTI_SPIKE_LOG;
    };
};

// Server-side frame rate under this load, for the record.
(format ["server_fps=%1 diag_fps=%2", diag_fps, diag_fpsMin]) call CTI_SPIKE_LOG;

"done" call CTI_SPIKE_LOG;
