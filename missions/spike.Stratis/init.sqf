// Runs on the server and on every client, including the headless client.

// Written into the mission by spike/run.sh at bring-up, so every machine learns
// the daemon's candidate addresses. Absent when the mission is run by hand.
if (fileExists "daemon_addrs.sqf") then {
    call compile preprocessFileLineNumbers "daemon_addrs.sqf";
};

// Defined everywhere so remoteExec can name it. The HC runs it and reports back.
CTI_SPIKE_HC_TASK = {
    private _reply = [clientOwner, diag_fps, count allUnits];
    cti_spike_hc_echo = _reply;
    publicVariableServer "cti_spike_hc_echo";
};

// The HC announces itself so the server-side harness has a positive signal:
// `entities "HeadlessClient_F"` and `allPlayers` both stay empty for an HC that
// holds no slot, so neither is a usable liveness check.
if (!isServer && {!hasInterface}) then {
    cti_spike_hc_online = clientOwner;
    publicVariable "cti_spike_hc_online";
    diag_log format ["SPIKE_HC|online owner=%1", clientOwner];
};

// ---------------------------------------------------------------- human client
// A real client is the only place the cross-compiled Windows .dll can be
// exercised, so the join test doubles as the shim's Windows load test. Reports
// back to the server so the result lands in one log rather than two.
if (hasInterface) then {
    [] spawn {
        waitUntil { !isNull player && {alive player} };

        private _probe = "cti_shim" callExtension ["ping", []];
        private _loaded = (_probe # 0) isEqualTo "pong";
        private _addr = "none";
        private _bench = "shim not loaded";
        private _echo = "shim not loaded";

        if (_loaded) then {
            // Whether mirrored-mode loopback reaches the WSL2 daemon from Windows
            // is the open question, so try loopback first and the LAN IP second.
            private _addrs = if (isNil "CTI_SPIKE_DAEMON_ADDRS") then {
                ["127.0.0.1:9099"]
            } else {
                CTI_SPIKE_DAEMON_ADDRS
            };
            {
                "cti_shim" callExtension ["addr", [_x]];
                private _try = ("cti_shim" callExtension
                    ["rpc_keepalive", ["{""id"":""client-probe"",""verb"":""ping""}"]]) # 0;
                if !(_try regexMatch ".*""error"".*") exitWith {
                    _addr = _x;
                    _echo = _try;
                    _bench = ("cti_shim" callExtension
                        ["bench", [20, true, "{""id"":""client-bench"",""verb"":""ping""}"]]) # 0;
                };
                _echo = _try;
            } forEach _addrs;
        };

        cti_spike_client_report = [
            profileName, productVersion, _loaded, _probe, _addr, _bench, _echo, diag_fps
        ];
        publicVariableServer "cti_spike_client_report";
        diag_log format ["SPIKE_CLIENT|%1", cti_spike_client_report];
    };
};
