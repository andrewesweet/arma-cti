// probe: human-commander
// issues: 18, 46, 116
// window: 420
// env: CTI_WINDOWS_CLIENT=1 CTI_PROBE_CLIENT=240
//
// #18 in-world probe: the human Commander's path, as far as a world with no
// human in it can be made to answer for it.
//
// `just regress human-commander`, or by hand
// `just probe spike/probes/human-commander.sqf`.
//
// What this can and cannot settle, stated up front so nobody reads more out of
// a green run than is in it. The dedicated-server-plus-headless-client topology
// has no person in a Commander slot, and a headless client cannot stand in for
// one: `remoteExecutedOwner` returns 0 for a call arriving from a headless
// client by engine design (BIKI, vendored), and a headless client holds no
// player unit to carry a UID, so it can be neither attributed nor assigned. So
// this probe asserts everything up to and including the gateway's refusal of an
// unassigned caller, the view the daemon serves a Commander, and the identity
// between what the UI can say and what the port judges. What it cannot assert
// is a rendered map with a person clicking on it, and that is the human's play
// session rather than a longer window.
//
// The client leg is on in the corpus and declared in the `env:` header above,
// not left to a caller to remember (ADR-0037, #116). It used to default off:
// CTI_PROBE_CLIENT was 0 unless someone set it, so every corpus run of this
// probe finished green having never crossed the machine boundary that the
// second half of the ticket is entirely about. A leg that is optional in
// practice is a leg nobody runs.
//
// The window is 420 rather than the default 150 because the subject grew with
// it, not because a shorter one was flaky: the client has to launch on the
// Windows host, connect and be swept into the Commander slot (240 s allowed for
// a cold start, 24.7 s observed on #18's run), and the accepted Purchase is then
// polled to a 60 s ceiling with a 30 s wait on the client's own report after it.
//
// Run by hand without a client — `just probe spike/probes/human-commander.sqf` —
// this probe reports its client leg `unverified` and the run is
// infra_unavailable. That is the honest answer to "nothing was measured", and it
// is the same answer the tier gives for any other condition it could not read.
[] spawn {
    private _extension = call cti_fnc_shimName;
    if (_extension isEqualTo "") exitWith {
        diag_log "CTI|FAIL class=infra_unavailable human_commander_probe_no_shim";
    };

    private _rpc = {
        params ["_envelope"];
        private _raw = ((call cti_fnc_shimName) callExtension ["rpc_keepalive", [toJSON _envelope]]) # 0;
        fromJSON _raw
    };

    // The world built and both server loops turned once (#46, replacing a fixed
    // 20 s settle and keeping its 20 s as the deadline).
    [20] call cti_probe_fnc_worldReady;

    // ---------------------------------------------------------------- whitelist
    // The mission's own config, read out of the running mission rather than out
    // of the file it was packed from. "No additional function is whitelisted to
    // make the UI work" is a claim about what shipped, and this is where what
    // shipped can be asked.
    private _remote = missionConfigFile >> "CfgRemoteExec";
    private _functionsMode = getNumber (_remote >> "Functions" >> "mode");
    private _commandsMode = getNumber (_remote >> "Commands" >> "mode");
    private _whitelisted = configProperties [_remote >> "Functions", "isClass _x", true]
        apply { configName _x };

    diag_log format ["CTI|human_commander_probe_whitelist functions=%1 commands=%2 classes=%3",
        _functionsMode, _commandsMode, _whitelisted];

    if (_functionsMode isNotEqualTo 1 || { _commandsMode isNotEqualTo 1 }) then {
        diag_log format ["CTI|FAIL class=assertion_failed human_commander_probe_remoteexec_open functions=%1 commands=%2",
            _functionsMode, _commandsMode];
    };
    if (_whitelisted isNotEqualTo ["cti_fnc_portGateway"]) then {
        diag_log format ["CTI|FAIL class=assertion_failed human_commander_probe_whitelist_grew classes=%1",
            _whitelisted];
    };

    // ---------------------------------------------------------------- vocabulary
    // The guarantee #18 exists for, asked mechanically: what the map UI can say
    // is read out of the same schema the port judges by, so an Order the human
    // can express and the AI cannot would be a fork of the wire format. Run on
    // the server because cti_fnc_mapVerbs reads the schema and nothing else —
    // the machine it runs on is not part of the answer.
    private _schema = call cti_fnc_commandSchema;
    private _verbs = call cti_fnc_mapVerbs;
    private _uiOrders = (_verbs select { (_x # 1) isEqualTo "order" }) apply { _x # 2 };
    private _uiBuys = (_verbs select { (_x # 1) isEqualTo "purchase" }) apply { _x # 2 };
    private _portOrders = _schema getOrDefault ["orders", []];
    private _portBuys = keys (_schema getOrDefault ["squads", createHashMap]);
    _portBuys sort true;

    diag_log format ["CTI|human_commander_probe_vocabulary ui_orders=%1 ui_buys=%2", _uiOrders, _uiBuys];

    if (_uiOrders isNotEqualTo _portOrders) then {
        diag_log format ["CTI|FAIL class=assertion_failed human_commander_probe_order_vocabulary ui=%1 port=%2",
            _uiOrders, _portOrders];
    };
    if (_uiBuys isNotEqualTo _portBuys) then {
        diag_log format ["CTI|FAIL class=assertion_failed human_commander_probe_buy_vocabulary ui=%1 port=%2",
            _uiBuys, _portBuys];
    };

    // ---------------------------------------------------------------- gateway
    // An unassigned caller is refused, and the refusal is the port's own word
    // rather than a dead click. Called here on the server, where
    // remoteExecutedOwner is 0 — which is the same answer the engine gives for a
    // headless client, and the reason the accepted case needs a person.
    private _before = ([createHashMapFromArray [
        ["id", "human-commander-probe-view-before"],
        ["verb", "view"],
        ["payload", createHashMapFromArray [["side", "WEST"]]]
    ]] call _rpc) getOrDefault ["result", createHashMap];

    private _sent = [["purchase", [["squad_type", "rifle"]]] call cti_fnc_command]
        call cti_fnc_portGateway;
    if (_sent) then {
        diag_log "CTI|FAIL class=assertion_failed human_commander_probe_unassigned_accepted";
    } else {
        diag_log "CTI|human_commander_probe_unassigned_refused";
    };

    private _after = ([createHashMapFromArray [
        ["id", "human-commander-probe-view-after"],
        ["verb", "view"],
        ["payload", createHashMapFromArray [["side", "WEST"]]]
    ]] call _rpc) getOrDefault ["result", createHashMap];
    if ((_after getOrDefault ["funds", -1]) isNotEqualTo (_before getOrDefault ["funds", -2])) then {
        diag_log format ["CTI|FAIL class=assertion_failed human_commander_probe_refused_command_spent before=%1 after=%2",
            _before getOrDefault ["funds", "?"], _after getOrDefault ["funds", "?"]];
    };

    // ---------------------------------------------------------------- the view
    // Both sides buy, so a leak has something to leak. Sent as Commands on the
    // wire because that is how the world's own effects arrive, and the Squads
    // have to exist for the view to carry any.
    {
        [createHashMapFromArray [
            ["id", format ["human-commander-probe-buy-%1", _x]],
            ["verb", "command"],
            ["payload", createHashMapFromArray [
                ["command", "purchase"],
                ["side", _x],
                ["args", createHashMapFromArray [["squad_type", "rifle"]]]
            ]]
        ]] call _rpc;
    } forEach ["WEST", "EAST"];

    private _reply = [createHashMapFromArray [
        ["id", "human-commander-probe-view"],
        ["verb", "view"],
        ["payload", createHashMapFromArray [["side", "WEST"]]]
    ]] call _rpc;

    if !((_reply getOrDefault ["status", ""]) isEqualTo "ok") exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed human_commander_probe_view_refused reply=%1", _reply];
        diag_log "CTI|LEG name=human_commander_client status=unverified reason=view_refused_before_the_leg";
        diag_log "CTI|human_commander_probe_done";
    };

    private _view = _reply getOrDefault ["result", createHashMap];
    private _keys = keys _view;
    diag_log format ["CTI|human_commander_probe_view side=%1 funds=%2 squads=%3 keys=%4",
        _view getOrDefault ["side", "?"],
        _view getOrDefault ["funds", "?"],
        count (_view getOrDefault ["squads", []]),
        _keys];

    private _missing = ["side", "funds", "squads", "contacts", "owners", "hq"] select { !(_x in _keys) };
    if (_missing isNotEqualTo []) then {
        diag_log format ["CTI|FAIL class=assertion_failed human_commander_probe_view_incomplete missing=%1", _missing];
    };
    if ((_view getOrDefault ["side", ""]) isNotEqualTo "WEST") then {
        diag_log format ["CTI|FAIL class=assertion_failed human_commander_probe_view_wrong_side side=%1",
            _view getOrDefault ["side", "?"]];
    };

    // Per-side isolation, asked of the raw document rather than of a field:
    // EAST bought a Squad in the same breath WEST did, and nothing WEST is
    // handed may name it. The public halves are lifted out first — Objective
    // ownership and Base HQ status are public in every view on purpose (#27,
    // #35), so a town EAST holds says "EAST" in WEST's picture by design and
    // leaving it in would make this assertion a test of who holds what.
    private _private = +_view;
    _private deleteAt "owners";
    _private deleteAt "hq";
    private _raw = toJSON _private;
    if ((_raw find "EAST") > -1) then {
        diag_log format ["CTI|FAIL class=assertion_failed human_commander_probe_view_leaks_enemy raw=%1", _raw];
    };
    if (count (_view getOrDefault ["squads", []]) isNotEqualTo 1) then {
        diag_log format ["CTI|FAIL class=assertion_failed human_commander_probe_view_squads=%1",
            count (_view getOrDefault ["squads", []])];
    };

    // ---------------------------------------------------------------- the client leg
    // The half only a person can answer for, and the half the corpus now runs.
    // The harness launches a headed client on the Windows host and stages
    // CTI_PROBE_CLIENT with the seconds this probe may wait for it to be swept
    // into a Commander slot; the probe then drives that client, which is as
    // close to a person as a machine gets.
    //
    // Every exit from here on names the leg and what became of it. `status=ran`
    // is claimed once, at the bottom, after the client has actually answered —
    // so nothing on the way out of this block can leave the verdict saying the
    // leg happened.
    private _waitFor = missionNamespace getVariable ["CTI_PROBE_CLIENT", 0];
    if (_waitFor <= 0) exitWith {
        diag_log "CTI|LEG name=human_commander_client status=unverified reason=run_sent_no_headed_client";
        diag_log "CTI|human_commander_probe_done";
    };

    private _deadline = diag_tickTime + _waitFor;
    waitUntil {
        count (missionNamespace getVariable ["cti_commanders", createHashMap]) > 0
            || { diag_tickTime > _deadline }
    };

    private _assigned = missionNamespace getVariable ["cti_commanders", createHashMap];
    diag_log format ["CTI|human_commander_probe_client_leg players=%1 assigned=%2 waited=%3",
        count allPlayers, keys _assigned, _waitFor];

    if (count _assigned isEqualTo 0) exitWith {
        diag_log "CTI|FAIL class=timeout human_commander_probe_no_client_assigned";
        diag_log "CTI|LEG name=human_commander_client status=unverified reason=no_person_in_a_commander_slot";
        diag_log "CTI|human_commander_probe_done";
    };

    private _commanded = (keys _assigned) # 0;
    private _uid = _assigned get _commanded;
    private _unit = objNull;
    { if (getPlayerUID _x isEqualTo _uid) exitWith { _unit = _x } } forEach allPlayers;
    if (isNull _unit) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed human_commander_probe_assigned_uid_absent uid=%1", _uid];
        diag_log "CTI|LEG name=human_commander_client status=unverified reason=assigned_uid_holds_no_unit";
        diag_log "CTI|human_commander_probe_done";
    };
    private _target = owner _unit;
    diag_log format ["CTI|human_commander_probe_commander side=%1 owner=%2 role=%3",
        _commanded, _target, roleDescription _unit];

    private _funded = (([createHashMapFromArray [
        ["id", "human-commander-probe-client-before"],
        ["verb", "view"],
        ["payload", createHashMapFromArray [["side", _commanded]]]
    ]] call _rpc) getOrDefault ["result", createHashMap]) getOrDefault ["funds", -1];

    // Driving the client rather than standing in for it: the Command is built on
    // the client, by the client's own UI path, and crosses the network through
    // the mode=1 whitelist. Server-to-client remoteExec is unrestricted, which
    // is what lets the probe press the key nobody is there to press. The report
    // comes back on a public variable rather than a second remoteExec, because
    // the whitelist is the thing under test and a probe that widened it would be
    // testing a mission that does not ship.
    {
        [] spawn {
            // The push loop runs on its own cadence, so the view may be one
            // interval behind the assignment that triggered it.
            private _by = diag_tickTime + 30;
            waitUntil { !isNil "cti_uiSide" || { diag_tickTime > _by } };

            cti_probeReport = [
                missionNamespace getVariable ["cti_uiSide", ""],
                (missionNamespace getVariable ["cti_view", createHashMap]) getOrDefault ["funds", -1],
                count ((missionNamespace getVariable ["cti_view", createHashMap])
                    getOrDefault ["squads", []]),
                !isNil "cti_uiStarted"
            ];
            publicVariable "cti_probeReport";

            [["purchase", [["squad_type", "rifle"]]] call cti_fnc_command]
                remoteExec ["cti_fnc_portGateway", 2];
        };
    } remoteExec ["call", _target];

    // The judgement is what the daemon did with it, read where the daemon keeps
    // it rather than off a log line: the Command was accepted for the side the
    // *server* stamped, which is the whole of attribution.
    private _spentBy = diag_tickTime + 60;
    private _now = _funded;
    waitUntil {
        _now = (([createHashMapFromArray [
            ["id", format ["human-commander-probe-client-poll-%1", round diag_tickTime]],
            ["verb", "view"],
            ["payload", createHashMapFromArray [["side", _commanded]]]
        ]] call _rpc) getOrDefault ["result", createHashMap]) getOrDefault ["funds", -1];
        _now isNotEqualTo _funded || { diag_tickTime > _spentBy }
    };

    if (_now isEqualTo _funded) then {
        diag_log format ["CTI|FAIL class=assertion_failed human_commander_probe_client_command_lost side=%1 funds=%2",
            _commanded, _funded];
    } else {
        diag_log format ["CTI|human_commander_probe_client_command side=%1 funds=%2->%3",
            _commanded, _funded, _now];
    };

    private _reportBy = diag_tickTime + 30;
    waitUntil { !isNil "cti_probeReport" || { diag_tickTime > _reportBy } };
    if (isNil "cti_probeReport") then {
        diag_log "CTI|FAIL class=assertion_failed human_commander_probe_client_silent";
    } else {
        cti_probeReport params ["_clientSide", "_clientFunds", "_clientSquads", "_clientUI"];
        diag_log format ["CTI|human_commander_probe_client_view side=%1 funds=%2 squads=%3 ui=%4",
            _clientSide, _clientFunds, _clientSquads, _clientUI];
        if (_clientSide isNotEqualTo _commanded) then {
            diag_log format ["CTI|FAIL class=assertion_failed human_commander_probe_client_no_view side=%1 expected=%2",
                _clientSide, _commanded];
        };
        if !(_clientUI) then {
            diag_log "CTI|FAIL class=assertion_failed human_commander_probe_client_ui_not_started";
        };
    };

    diag_log "CTI|LEG name=human_commander_client status=ran";
    diag_log "CTI|human_commander_probe_done";
};
