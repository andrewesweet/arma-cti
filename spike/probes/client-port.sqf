// probe: client-port
// issues: 21, 46, 116
// window: 420
// env: CTI_WINDOWS_CLIENT=1 CTI_PROBE_CLIENT=240
//
// #21 in-world probe: the leg between a real client and the Command Port's
// gateway, including the failure modes one accepted Purchase cannot reach.
//
// #12 built the gateway and #18 built the map UI that calls it; neither proved
// what happens between them. `human-commander.sqf` since drove one accepted
// Purchase from a headed client through the mode=1 whitelist and watched the
// Funds move, which settles the happy path and nothing else. This probe is the
// rest of the leg: the judgement's return trip for an accepted *and* a refused
// Command, the server's stamp beating a side the client lied about, a client
// the server has not assigned, payloads that are not Commands, and the
// whitelist refusing a call to anything but the gateway.
//
// A headless client cannot stand in for the caller. `remoteExecutedOwner`
// returns 0 for a call arriving from an HC by engine design (BIKI, vendored)
// and an HC holds no player unit to carry a UID, so it is neither attributable
// nor assignable (ADR-0025). This probe therefore declares the headed client in
// its own `env:` header and refuses to report anything when the run did not
// send one: a green pass with nobody in the Commander slot would be a pass
// about something smaller than the ticket.
//
// The window is 420 rather than the default 150 because the subject is longer,
// not because a shorter one was flaky: the client has to launch on the Windows
// host, connect and be swept into the Commander slot (24.7 s observed on #18's
// run, 240 s allowed for a cold start), and then six Commands cross the network
// and come back one after another, each polled to a 60 s ceiling.
//
// Assertions are made on Squad counts rather than on Funds wherever a refusal
// is the subject. Funds move on their own — every side draws a stipend each
// income tick — so "Funds unchanged" would be a clock race dressed up as a
// rule. A Squad appears only when a Purchase is accepted, and for the side the
// server stamped.
//
// #46 converted this probe's bring-up settle and deliberately left the other
// two alone. The 10 s the client waits after its two blocked calls, and the 15 s
// the server waits after that, are the irreducible kind: the claim is that
// nothing arrived, and an absence has no condition to wait on — only a length of
// time nothing has happened for (docs/regression-tier.md, "The honesty rule").
// Neither can become a watcher either, because a watcher on `nothing arrived`
// is the same dwell written differently. Both dwells are unchanged, so the
// evidence behind the whitelist claim is the evidence #21 landed.
[] spawn {
    private _extension = call cti_fnc_shimName;
    if (_extension isEqualTo "") exitWith {
        diag_log "CTI|FAIL class=infra_unavailable client_port_probe_no_shim";
        diag_log "CTI|client_port_probe_done";
    };

    private _rpc = {
        params ["_envelope"];
        private _raw = ((call cti_fnc_shimName) callExtension ["rpc_keepalive", [toJSON _envelope]]) # 0;
        fromJSON _raw
    };

    // One side's board as the daemon holds it: [funds, squads]. Read through
    // the same `view` verb the Commander's own picture comes from, so what the
    // probe checks and what the person would see are one answer.
    private _board = {
        params ["_for"];
        private _result = ([createHashMapFromArray [
            ["id", format ["client-port-probe-view-%1-%2", _for, round (diag_tickTime * 1000)]],
            ["verb", "view"],
            ["payload", createHashMapFromArray [["side", _for]]]
        ]] call _rpc) getOrDefault ["result", createHashMap];
        [_result getOrDefault ["funds", -1], count (_result getOrDefault ["squads", []])]
    };

    // The world built and both server loops turned once (#46, replacing a fixed
    // 20 s settle and keeping its 20 s as the deadline).
    [20] call cti_probe_fnc_worldReady;

    // ---------------------------------------------------------------- the caller
    private _waitFor = missionNamespace getVariable ["CTI_PROBE_CLIENT", 0];
    if (_waitFor <= 0) exitWith {
        // Not an assertion about the code: the run did not send the client this
        // probe is entirely about, so nothing was measured under conditions
        // anyone can read. Said in the leg grammar the harness scores (#116);
        // run.sh turns an unverified leg into infra_unavailable, which is the
        // class this line used to declare for itself.
        diag_log "CTI|LEG name=client_port_caller status=unverified reason=run_sent_no_headed_client";
        diag_log "CTI|client_port_probe_done";
    };

    private _deadline = diag_tickTime + _waitFor;
    waitUntil {
        count (missionNamespace getVariable ["cti_commanders", createHashMap]) > 0
            || { diag_tickTime > _deadline }
    };

    private _assigned = missionNamespace getVariable ["cti_commanders", createHashMap];
    if (count _assigned isEqualTo 0) exitWith {
        diag_log format ["CTI|FAIL class=timeout client_port_probe_no_client_assigned waited=%1 players=%2",
            _waitFor, count allPlayers];
        diag_log "CTI|LEG name=client_port_caller status=unverified reason=no_person_in_a_commander_slot";
        diag_log "CTI|client_port_probe_done";
    };

    private _side = (keys _assigned) # 0;
    private _uid = _assigned get _side;
    private _unit = objNull;
    { if (getPlayerUID _x isEqualTo _uid) exitWith { _unit = _x } } forEach allPlayers;
    if (isNull _unit) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed client_port_probe_assigned_uid_absent uid=%1", _uid];
        diag_log "CTI|LEG name=client_port_caller status=unverified reason=assigned_uid_holds_no_unit";
        diag_log "CTI|client_port_probe_done";
    };

    private _target = owner _unit;
    private _other = ["WEST", "EAST"] select (_side isEqualTo "WEST");
    diag_log format ["CTI|client_port_probe_commander side=%1 owner=%2 role=%3 other=%4",
        _side, _target, roleDescription _unit, _other];
    diag_log "CTI|LEG name=client_port_caller status=ran";

    // Drive one step on the client and wait for its own account of it. The
    // Command is built and sent on the client, by the client's own path, across
    // the mode=1 whitelist; the report comes back on a public variable rather
    // than a second remoteExec, because the whitelist is the thing under test
    // and a probe that widened it would be testing a mission that does not
    // ship. Server-to-client remoteExec is unrestricted, which is what lets the
    // probe press the key nobody is there to press.
    //
    // Every ack carries the step name it belongs to, so a late one from the
    // step before is discarded rather than read as this step's answer.
    // Each step of the leg says what became of it (#116, ADR-0037). The six
    // step exits below used to be bare `client_port_probe_done` lines: covered
    // in practice, because `_drive` logs a FAIL before returning [], but a bare
    // completion is a green verdict short-circuited and the cover was incidental
    // rather than structural. Now an abandoned step names itself unverified, the
    // steps that ran name themselves too, and the verdict carries the list —
    // so a pass says which of the six it is a pass about.
    private _legRan = {
        diag_log format ["CTI|LEG name=client_port_%1 status=ran", _this];
    };
    private _legLost = {
        diag_log format ["CTI|LEG name=client_port_%1 status=unverified reason=client_never_acked_the_step", _this];
        diag_log "CTI|client_port_probe_done";
    };

    private _drive = {
        params ["_step", "_code", ["_wait", 90]];
        cti_probeAck = nil;
        _code remoteExec ["call", _target];
        private _by = diag_tickTime + _wait;
        waitUntil {
            (!isNil "cti_probeAck" && { (cti_probeAck # 0) isEqualTo _step })
                || { diag_tickTime > _by }
        };
        if (isNil "cti_probeAck" || { (cti_probeAck # 0) isNotEqualTo _step }) exitWith {
            diag_log format ["CTI|FAIL class=timeout client_port_probe_client_silent step=%1", _step];
            []
        };
        private _ack = +cti_probeAck;
        diag_log format ["CTI|client_port_probe_ack step=%1 status=%2 code=%3 funds=%4 note=%5",
            _ack # 0, _ack # 1, _ack # 2, _ack # 4, _ack # 5];
        _ack
    };

    // ------------------------------------------------------- an accepted Command
    // The whole leg in one exchange: built on the client, judged on the server,
    // and the judgement back on the client that sent it — which is where
    // cti_fnc_portReply put it, and the only place it may be read from.
    ([_side] call _board) params ["_fundsBefore", "_squadsBefore"];
    ([_other] call _board) params ["_otherFundsBefore", "_otherSquadsBefore"];

    private _accepted = ["accepted", {
        [] spawn {
            cti_lastJudgement = nil;
            private _cmd = ["purchase", [["squad_type", "rifle"]]] call cti_fnc_command;
            [_cmd] remoteExec ["cti_fnc_portGateway", 2];
            private _by = diag_tickTime + 60;
            waitUntil { !isNil "cti_lastJudgement" || { diag_tickTime > _by } };
            private _judgement = missionNamespace getVariable ["cti_lastJudgement", createHashMap];
            private _reason = _judgement getOrDefault ["reason", createHashMap];
            cti_probeAck = [
                "accepted",
                _judgement getOrDefault ["status", "nothing-arrived"],
                _reason getOrDefault ["code", ""],
                _reason getOrDefault ["detail", ""],
                (_judgement getOrDefault ["result", createHashMap]) getOrDefault ["funds", -1],
                format ["sent side=%1", _cmd getOrDefault ["side", "?"]]
            ];
            publicVariable "cti_probeAck";
        };
    }] call _drive;

    if (_accepted isEqualTo []) exitWith { "accepted" call _legLost };
    if ((_accepted # 1) isNotEqualTo "ok") then {
        diag_log format ["CTI|FAIL class=assertion_failed client_port_probe_accepted_not_judged status=%1 code=%2",
            _accepted # 1, _accepted # 2];
    };

    ([_side] call _board) params ["_fundsAfter", "_squadsAfter"];
    if (_squadsAfter isNotEqualTo _squadsBefore + 1) then {
        diag_log format ["CTI|FAIL class=assertion_failed client_port_probe_accepted_no_squad before=%1 after=%2",
            _squadsBefore, _squadsAfter];
    };
    if (_fundsAfter >= _fundsBefore) then {
        diag_log format ["CTI|FAIL class=assertion_failed client_port_probe_accepted_free before=%1 after=%2",
            _fundsBefore, _fundsAfter];
    };
    diag_log format ["CTI|client_port_probe_accepted side=%1 funds=%2->%3 squads=%4->%5 judged_funds=%6",
        _side, _fundsBefore, _fundsAfter, _squadsBefore, _squadsAfter, _accepted # 4];
    "accepted" call _legRan;

    // ------------------------------------------------------------- a lying side
    // The client fills `side` in with the side it does not command. The gateway
    // overwrites it from the server's own assignment state and never validates
    // it (ADR-0012, ADR-0025), so the Squad has to arrive on the caller's own
    // side — and the side it asked for has to be untouched, which is the half an
    // assertion about the payload could not show.
    private _forged = ["forged", {
        [] spawn {
            private _by = diag_tickTime + 60;
            waitUntil { !isNil "cti_uiSide" || { diag_tickTime > _by } };
            private _mine = missionNamespace getVariable ["cti_uiSide", ""];
            private _lie = ["WEST", "EAST"] select (_mine isEqualTo "WEST");
            cti_lastJudgement = nil;
            private _cmd = ["purchase", [["squad_type", "rifle"]]] call cti_fnc_command;
            _cmd set ["side", _lie];
            [_cmd] remoteExec ["cti_fnc_portGateway", 2];
            _by = diag_tickTime + 60;
            waitUntil { !isNil "cti_lastJudgement" || { diag_tickTime > _by } };
            private _judgement = missionNamespace getVariable ["cti_lastJudgement", createHashMap];
            private _reason = _judgement getOrDefault ["reason", createHashMap];
            cti_probeAck = [
                "forged",
                _judgement getOrDefault ["status", "nothing-arrived"],
                _reason getOrDefault ["code", ""],
                _reason getOrDefault ["detail", ""],
                (_judgement getOrDefault ["result", createHashMap]) getOrDefault ["funds", -1],
                format ["%1 claimed %2", _mine, _lie]
            ];
            publicVariable "cti_probeAck";
        };
    }] call _drive;

    if (_forged isEqualTo []) exitWith { "forged" call _legLost };
    if ((_forged # 1) isNotEqualTo "ok") then {
        diag_log format ["CTI|FAIL class=assertion_failed client_port_probe_forged_refused status=%1 code=%2 detail=%3",
            _forged # 1, _forged # 2, _forged # 3];
    };
    if ((_forged # 5) isNotEqualTo format ["%1 claimed %2", _side, _other]) then {
        diag_log format ["CTI|FAIL class=assertion_failed client_port_probe_forged_wrong_lie note=%1 expected=%2",
            _forged # 5, format ["%1 claimed %2", _side, _other]];
    };

    ([_side] call _board) params ["_fundsForged", "_squadsForged"];
    ([_other] call _board) params ["_otherFundsForged", "_otherSquadsForged"];
    if (_squadsForged isNotEqualTo _squadsAfter + 1) then {
        diag_log format ["CTI|FAIL class=assertion_failed client_port_probe_forged_no_squad side=%1 before=%2 after=%3",
            _side, _squadsAfter, _squadsForged];
    };
    if (_otherSquadsForged isNotEqualTo _otherSquadsBefore) then {
        diag_log format ["CTI|FAIL class=assertion_failed client_port_probe_forged_landed_on_claimed_side side=%1 before=%2 after=%3",
            _other, _otherSquadsBefore, _otherSquadsForged];
    };
    diag_log format ["CTI|client_port_probe_stamp claimed=%1 stamped=%2 squads_%2=%3->%4 squads_%1=%5->%6",
        _other, _side, _squadsAfter, _squadsForged, _otherSquadsBefore, _otherSquadsForged];
    "forged" call _legRan;

    // ------------------------------------------------------ a caller nobody knows
    // The refusal a person meets when they reach the port from a machine the
    // server has not assigned. #18's probe could only ask this from the server,
    // where remoteExecutedOwner is 0; here it is asked from a real client, with
    // a real machine id, and the refusal has to travel back the way an accepted
    // judgement does.
    //
    // The assignment is taken away by overwriting the latched UID in the same
    // HashMap the assignment sweep holds, rather than by clearing the map: the
    // sweep latches once per side and skips a side already in it, so the side
    // stays occupied by a UID no player has and the sweep does not race the
    // probe to hand it back. The world is not touched.
    _assigned set [_side, "cti-client-port-probe-nobody"];
    diag_log format ["CTI|client_port_probe_unassigned side=%1 uid_was=%2", _side, _uid];

    private _unknown = ["unassigned", {
        [] spawn {
            cti_lastJudgement = nil;
            private _cmd = ["purchase", [["squad_type", "rifle"]]] call cti_fnc_command;
            [_cmd] remoteExec ["cti_fnc_portGateway", 2];
            private _by = diag_tickTime + 60;
            waitUntil { !isNil "cti_lastJudgement" || { diag_tickTime > _by } };
            private _judgement = missionNamespace getVariable ["cti_lastJudgement", createHashMap];
            private _reason = _judgement getOrDefault ["reason", createHashMap];
            cti_probeAck = [
                "unassigned",
                _judgement getOrDefault ["status", "nothing-arrived"],
                _reason getOrDefault ["code", ""],
                _reason getOrDefault ["detail", ""],
                (_judgement getOrDefault ["result", createHashMap]) getOrDefault ["funds", -1],
                ""
            ];
            publicVariable "cti_probeAck";
        };
    }] call _drive;

    ([_side] call _board) params ["_fundsUnknown", "_squadsUnknown"];
    _assigned set [_side, _uid];

    if (_unknown isEqualTo []) exitWith { "unassigned" call _legLost };
    if ((_unknown # 1) isNotEqualTo "rejected" || { (_unknown # 2) isNotEqualTo "wrong_side" }) then {
        diag_log format ["CTI|FAIL class=assertion_failed client_port_probe_unassigned_not_refused status=%1 code=%2",
            _unknown # 1, _unknown # 2];
    };
    // The gateway answers this one itself rather than asking the daemon, and
    // the two refusals are told apart by the words they come back in: the
    // daemon's wrong_side says one side may not command for another.
    if (((_unknown # 3) find "commands no side") < 0) then {
        diag_log format ["CTI|FAIL class=assertion_failed client_port_probe_unassigned_not_the_gateway detail=%1",
            _unknown # 3];
    };
    if (_squadsUnknown isNotEqualTo _squadsForged) then {
        diag_log format ["CTI|FAIL class=assertion_failed client_port_probe_unassigned_bought before=%1 after=%2",
            _squadsForged, _squadsUnknown];
    };
    "unassigned" call _legRan;

    // ------------------------------------------------------- payloads that are not Commands
    // Two shapes a client can send that cti_fnc_command would never build, sent
    // without it: something that is not a Command at all, and a Command by a
    // name nothing sells. Both have to come back as judgements rather than as
    // silence or as a broken gateway, and neither may move the board.
    private _junk = ["junk", {
        [] spawn {
            cti_lastJudgement = nil;
            ["this is not a Command"] remoteExec ["cti_fnc_portGateway", 2];
            private _by = diag_tickTime + 60;
            waitUntil { !isNil "cti_lastJudgement" || { diag_tickTime > _by } };
            private _judgement = missionNamespace getVariable ["cti_lastJudgement", createHashMap];
            private _reason = _judgement getOrDefault ["reason", createHashMap];
            cti_probeAck = [
                "junk",
                _judgement getOrDefault ["status", "nothing-arrived"],
                _reason getOrDefault ["code", ""],
                _reason getOrDefault ["detail", ""],
                -1,
                ""
            ];
            publicVariable "cti_probeAck";
        };
    }] call _drive;

    if (_junk isEqualTo []) exitWith { "junk" call _legLost };
    if ((_junk # 1) isNotEqualTo "rejected" || { (_junk # 2) isNotEqualTo "malformed_command" }) then {
        diag_log format ["CTI|FAIL class=assertion_failed client_port_probe_junk_not_refused status=%1 code=%2",
            _junk # 1, _junk # 2];
    };
    "junk" call _legRan;

    private _invented = ["invented", {
        [] spawn {
            cti_lastJudgement = nil;
            [createHashMapFromArray [
                ["command", "exfiltrate"],
                ["side", ""],
                ["args", createHashMap]
            ]] remoteExec ["cti_fnc_portGateway", 2];
            private _by = diag_tickTime + 60;
            waitUntil { !isNil "cti_lastJudgement" || { diag_tickTime > _by } };
            private _judgement = missionNamespace getVariable ["cti_lastJudgement", createHashMap];
            private _reason = _judgement getOrDefault ["reason", createHashMap];
            cti_probeAck = [
                "invented",
                _judgement getOrDefault ["status", "nothing-arrived"],
                _reason getOrDefault ["code", ""],
                _reason getOrDefault ["detail", ""],
                -1,
                ""
            ];
            publicVariable "cti_probeAck";
        };
    }] call _drive;

    if (_invented isEqualTo []) exitWith { "invented" call _legLost };
    if ((_invented # 1) isNotEqualTo "rejected" || { (_invented # 2) isNotEqualTo "unknown_command" }) then {
        diag_log format ["CTI|FAIL class=assertion_failed client_port_probe_invented_not_refused status=%1 code=%2",
            _invented # 1, _invented # 2];
    };
    "invented" call _legRan;

    ([_side] call _board) params ["_fundsJunk", "_squadsJunk"];
    if (_squadsJunk isNotEqualTo _squadsForged) then {
        diag_log format ["CTI|FAIL class=assertion_failed client_port_probe_junk_bought before=%1 after=%2",
            _squadsForged, _squadsJunk];
    };

    // --------------------------------------------------------------- the whitelist
    // The mechanical half of "no order path outside the port", asked of the
    // engine rather than of the config: this client has just proved it can
    // remoteExec the gateway, so a call it makes to anything else arriving
    // nowhere is the whitelist biting rather than a broken client.
    //
    // Both classes are tried, because a mission that locks Functions and leaves
    // Commands at the open default has a hole the size of the scripting-command
    // surface. Each attempt would leave an unmistakable mark on the server if it
    // landed: a mission-namespace variable, and cti_fnc_portReply's own
    // cti_lastJudgement, which the server never sets on itself. Both staying
    // unset is the observation.
    missionNamespace setVariable ["cti_probeBreachCommand", nil];
    missionNamespace setVariable ["cti_lastJudgement", nil];

    private _breach = ["breach", {
        [] spawn {
            // Each attempt in its own thread: a refused remoteExec that ends the
            // script it was called from would otherwise take the report with it,
            // and a silent client is a timeout rather than an observation.
            [] spawn {
                [missionNamespace, ["cti_probeBreachCommand", true]] remoteExec ["setVariable", 2];
            };
            [] spawn {
                [createHashMapFromArray [["status", "breach"]]] remoteExec ["cti_fnc_portReply", 2];
            };
            private _by = diag_tickTime + 10;
            waitUntil { diag_tickTime >= _by };
            cti_probeAck = ["breach", "attempted", "", "", -1, "setVariable and cti_fnc_portReply on the server"];
            publicVariable "cti_probeAck";
        };
    }] call _drive;

    if (_breach isEqualTo []) exitWith { "breach" call _legLost };

    // A grace beyond the client's own wait: the assertion is that nothing
    // arrives, and nothing arriving takes longer to establish than something
    // arriving does.
    private _settle = diag_tickTime + 15;
    waitUntil { diag_tickTime >= _settle };

    private _commandLanded = !isNil "cti_probeBreachCommand";
    private _functionLanded = !isNil "cti_lastJudgement";
    if (_commandLanded) then {
        diag_log "CTI|FAIL class=assertion_failed client_port_probe_command_whitelist_open remote=setVariable";
    };
    if (_functionLanded) then {
        diag_log "CTI|FAIL class=assertion_failed client_port_probe_function_whitelist_open remote=cti_fnc_portReply";
    };
    diag_log format ["CTI|client_port_probe_whitelist_bit setVariable_landed=%1 portReply_landed=%2",
        _commandLanded, _functionLanded];
    "breach" call _legRan;

    ([_side] call _board) params ["_fundsEnd", "_squadsEnd"];
    diag_log format ["CTI|client_port_probe_board side=%1 funds=%2 squads=%3", _side, _fundsEnd, _squadsEnd];

    diag_log "CTI|client_port_probe_done";
};
