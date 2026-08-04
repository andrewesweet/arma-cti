// probe: reinforce
// issues: 123
// window: 420
// env: CTI_WINDOWS_CLIENT=1 CTI_PROBE_CLIENT=240
//
// #123 in-world probe: the Command Port's second principal (ADR-0040). A real
// client, in no Commander slot, leading a Squad, issuing Reinforce for that
// Squad and being refused for anything else.
//
// `client-port.sqf` proved the leg between a client and the gateway for the one
// principal the port had: a person the server has assigned to a Commander slot.
// This is the leg for the other one. What is new is not the transport — that is
// the same whitelisted call — but the stamp: the server resolves the caller to
// the Squad he leads (cti_fnc_leaderSquad) and the port holds him to it, so the
// three things worth watching in-world are that his own Squad's refill is
// accepted and the men actually arrive, that another Squad's is refused
// `not_your_squad`, and that a Purchase from the same caller is refused because
// Purchase stayed the Commander's.
//
// The caller is made a squad leader rather than found as one: the mission
// authors two playable slots and both are Commander slots (#18), so the client
// necessarily lands in one. The assignment is then taken away the way
// `client-port` takes it away — by overwriting the latched UID in the sweep's
// own HashMap, which the sweep skips rather than re-latches — and the person is
// joined to a bought Squad as its leader. That leaves exactly the machine state
// a squad-leader slot would: no Commander assignment, and a group carrying the
// `cti_squad` id the daemon minted.
//
// A headless client cannot stand in for the caller, for ADR-0025's reason:
// `remoteExecutedOwner` is 0 for a call from an HC by engine design and an HC
// holds no player unit. So this probe declares its headed client in its own
// `env:` header and reports nothing when the run did not send one.
//
// The window is 420 rather than the default 150 because the subject is longer,
// not because a shorter one was flaky, and for the same reasons `client-port`
// gives: the client has to launch on the Windows host, connect and be swept
// (240 s allowed for a cold start), and then three Commands cross the network
// and come back one after another, each polled to a 60 s ceiling, with the
// accepted one's effect having to reach the world through a 2 s poll after that.
//
// Assertions are made on men standing rather than on Funds. Funds move on their
// own — every side draws a stipend each income tick — so "Funds unchanged" would
// be a clock race dressed up as a rule, while a man appearing in a group is the
// effect this Command exists to cause.
//
// The client-side judge-and-ack scaffold below is the second copy in the corpus;
// `client-port.sqf` has the first. Kept rather than lifted into
// `spike/probe-prelude.sqf` because #86's rule for that file is that a helper
// earns its place by having been copied, and reconciling two probes that both
// drive a headed client is a change to a green probe made from a session that
// cannot run the tier cheaply. A third copy should move it.
[] spawn {
    private _extension = call cti_fnc_shimName;
    if (_extension isEqualTo "") exitWith {
        diag_log "CTI|FAIL class=infra_unavailable reinforce_probe_no_shim";
        diag_log "CTI|reinforce_probe_done";
    };

    // One side's board as the daemon holds it, through the same `view` verb the
    // Commander's own picture comes from: how many Squads it has, and how big
    // the daemon believes each one is.
    private _board = {
        params ["_for"];
        private _result = ([createHashMapFromArray [
            ["id", ["reinforce-probe-view", _for] call cti_fnc_requestId],
            ["verb", "view"],
            ["payload", createHashMapFromArray [["side", _for]]]
        ]] call cti_probe_fnc_rpc) getOrDefault ["result", createHashMap];
        private _sizes = createHashMap;
        {
            _sizes set [_x getOrDefault ["id", "?"], _x getOrDefault ["size", -1]];
        } forEach (_result getOrDefault ["squads", []]);
        _sizes
    };

    [20] call cti_probe_fnc_worldReady;

    // ---------------------------------------------------------------- the caller
    private _waitFor = missionNamespace getVariable ["CTI_PROBE_CLIENT", 0];
    if (_waitFor <= 0) exitWith {
        diag_log "CTI|LEG name=reinforce_caller status=unverified reason=run_sent_no_headed_client";
        diag_log "CTI|reinforce_probe_done";
    };

    ([_waitFor] call cti_probe_fnc_commanderSlot) params ["_side", "_uid", "_unit"];
    private _assigned = missionNamespace getVariable ["cti_commanders", createHashMap];
    if (_side isEqualTo "") exitWith {
        diag_log format ["CTI|FAIL class=timeout reinforce_probe_no_client_assigned waited=%1 players=%2",
            _waitFor, count allPlayers];
        diag_log "CTI|LEG name=reinforce_caller status=unverified reason=no_person_in_a_commander_slot";
        diag_log "CTI|reinforce_probe_done";
    };
    if (isNull _unit) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed reinforce_probe_assigned_uid_absent uid=%1", _uid];
        diag_log "CTI|LEG name=reinforce_caller status=unverified reason=assigned_uid_holds_no_unit";
        diag_log "CTI|reinforce_probe_done";
    };

    private _target = owner _unit;

    // ------------------------------------------------------------ two Squads
    // Bought through the port, which is the only way a Squad reaches the roster.
    {
        [format ["reinforce-probe-buy-%1", _x], _side, "rifle"] call cti_probe_fnc_buySquad;
    } forEach [1, 2];

    private _by = diag_tickTime + 60;
    private _squads = createHashMap;
    waitUntil {
        _squads = [_side] call cti_probe_fnc_squadsOf;
        count _squads >= 2 || { diag_tickTime > _by }
    };
    if (count _squads < 2) exitWith {
        diag_log format ["CTI|FAIL class=timeout reinforce_probe_squads_never_spawned have=%1", count _squads];
        diag_log "CTI|LEG name=reinforce_caller status=unverified reason=the_world_never_spawned_two_squads";
        diag_log "CTI|reinforce_probe_done";
    };

    private _ids = keys _squads;
    _ids sort true;
    private _mineId = _ids # 0;
    private _theirsId = _ids # 1;
    private _mine = _squads get _mineId;
    private _theirs = _squads get _theirsId;

    // Thinned while both groups are still the server's, which is where they are
    // bought: three men out of each, so each Squad is under the strength it was
    // bought at and has something for a Reinforce to put back. Deleted rather
    // than killed — what is under test is the refill, and a corpse is the
    // casualty path's subject, not this one's.
    {
        private _group = _x;
        { deleteVehicle _x } forEach ((units _group) select [0, 3]);
    } forEach [_mine, _theirs];

    // The person becomes the leader of one of them, which is the whole of what
    // makes him the second principal: cti_fnc_leaderSquad reads `cti_squad` off
    // the group the engine says he leads. `joinSilent` is global in argument and
    // effect, and `selectLeader` takes a local group — the Squad is the
    // server's until this moment, and becomes the client's by this line
    // (topics/Multiplayer_Scripting.wiki: an AI group with a player-leader is
    // local to the player's computer). That locality change is the reason the
    // effect stages its replacements in a group of its own.
    [_unit] joinSilent _mine;
    _mine selectLeader _unit;

    private _by = diag_tickTime + 30;
    waitUntil { leader _mine isEqualTo _unit || { diag_tickTime > _by } };
    if (leader _mine isNotEqualTo _unit) exitWith {
        diag_log format ["CTI|FAIL class=timeout reinforce_probe_leadership_never_passed squad=%1", _mineId];
        diag_log "CTI|LEG name=reinforce_caller status=unverified reason=the_person_never_led_the_squad";
        diag_log "CTI|reinforce_probe_done";
    };

    // And the assignment goes away, so the same person commands no side and is a
    // squad leader and nothing else.
    _assigned set [_side, "cti-reinforce-probe-nobody"];

    diag_log format ["CTI|reinforce_probe_caller side=%1 owner=%2 leads=%3 other=%4 mine_units=%5 theirs_units=%6 mine_local=%7",
        _side, _target, _mineId, _theirsId, count units _mine, count units _theirs, local _mine];
    diag_log "CTI|LEG name=reinforce_caller status=ran";

    // The daemon's own account of the two Squads, which is what its judgement
    // will be made against: it has to have taken the world's report of the
    // thinning before a Reinforce is anything but a no-op.
    private _by = diag_tickTime + 60;
    private _sizes = createHashMap;
    waitUntil {
        _sizes = [_side] call _board;
        ((_sizes getOrDefault [_mineId, 8]) < 8 && { (_sizes getOrDefault [_theirsId, 8]) < 8 })
            || { diag_tickTime > _by }
    };
    diag_log format ["CTI|reinforce_probe_thinned mine=%1 theirs=%2",
        _sizes getOrDefault [_mineId, -1], _sizes getOrDefault [_theirsId, -1]];

    // --------------------------------------------------------- the client's side
    // The same scaffold `client-port` uses: the judgement arrives on the client
    // through cti_fnc_portReply and can only be read there, so the client
    // unpacks it and publishes an ack the server reads.
    {
        cti_probeJudge = {
            params ["_step", ["_note", ""]];
            private _by = diag_tickTime + 60;
            waitUntil { !isNil "cti_lastJudgement" || { diag_tickTime > _by } };
            private _judgement = missionNamespace getVariable ["cti_lastJudgement", createHashMap];
            private _reason = _judgement getOrDefault ["reason", createHashMap];
            cti_probeAck = [
                _step,
                _judgement getOrDefault ["status", "nothing-arrived"],
                _reason getOrDefault ["code", ""],
                _reason getOrDefault ["detail", ""],
                (_judgement getOrDefault ["result", createHashMap]) getOrDefault ["cost", -1],
                _note
            ];
            publicVariable "cti_probeAck";
        };
    } remoteExec ["call", _target];

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
            diag_log format ["CTI|FAIL class=timeout reinforce_probe_client_silent step=%1", _step];
            []
        };
        private _ack = +cti_probeAck;
        diag_log format ["CTI|reinforce_probe_ack step=%1 status=%2 code=%3 cost=%4 note=%5",
            _ack # 0, _ack # 1, _ack # 2, _ack # 4, _ack # 5];
        _ack
    };

    private _legLost = {
        diag_log format ["CTI|LEG name=reinforce_%1 status=unverified reason=client_never_acked_the_step", _this];
        diag_log "CTI|reinforce_probe_done";
    };
    private _legRan = {
        diag_log format ["CTI|LEG name=reinforce_%1 status=ran", _this];
    };

    // Which Squad the client asks about is decided on the server and sent to it,
    // because the client has no map UI in this run and no business inventing an
    // id: what is under test is who may ask for what, not how the id was found.
    cti_reinforceProbeMine = _mineId;
    cti_reinforceProbeTheirs = _theirsId;
    publicVariable "cti_reinforceProbeMine";
    publicVariable "cti_reinforceProbeTheirs";

    // ------------------------------------------------------------- his own Squad
    private _standingBefore = count units _mine;
    private _own = ["own", {
        [] spawn {
            cti_lastJudgement = nil;
            private _cmd = ["reinforce", [["squad", cti_reinforceProbeMine]]] call cti_fnc_command;
            [_cmd] remoteExec ["cti_fnc_portGateway", 2];
            ["own", format ["asked for %1", cti_reinforceProbeMine]] call cti_probeJudge;
        };
    }] call _drive;

    if (_own isEqualTo []) exitWith { "own" call _legLost };
    if ((_own # 1) isNotEqualTo "ok") then {
        diag_log format ["CTI|FAIL class=assertion_failed reinforce_probe_own_refused status=%1 code=%2 detail=%3",
            _own # 1, _own # 2, _own # 3];
    };
    if ((_own # 4) <= 0) then {
        diag_log format ["CTI|FAIL class=assertion_failed reinforce_probe_own_cost_free cost=%1", _own # 4];
    };

    // The judgement is not the work (ADR-0012): the men arrive because the world
    // polled the outbox, so this waits for the group to grow rather than
    // believing the reply.
    private _by = diag_tickTime + 60;
    waitUntil { count units _mine >= 8 || { diag_tickTime > _by } };
    private _standingAfter = count units _mine;
    if (_standingAfter < 8) then {
        diag_log format ["CTI|FAIL class=timeout reinforce_probe_men_never_arrived squad=%1 before=%2 after=%3 local=%4",
            _mineId, _standingBefore, _standingAfter, local _mine];
    };
    diag_log format ["CTI|reinforce_probe_own squad=%1 units=%2->%3 cost=%4 leader_is_the_person=%5",
        _mineId, _standingBefore, _standingAfter, _own # 4, leader _mine isEqualTo _unit];
    "own" call _legRan;

    // ---------------------------------------------------------- another Squad
    private _theirsBefore = count units _theirs;
    private _other = ["other", {
        [] spawn {
            cti_lastJudgement = nil;
            private _cmd = ["reinforce", [["squad", cti_reinforceProbeTheirs]]] call cti_fnc_command;
            [_cmd] remoteExec ["cti_fnc_portGateway", 2];
            ["other", format ["asked for %1", cti_reinforceProbeTheirs]] call cti_probeJudge;
        };
    }] call _drive;

    if (_other isEqualTo []) exitWith { "other" call _legLost };
    if ((_other # 1) isNotEqualTo "rejected" || { (_other # 2) isNotEqualTo "not_your_squad" }) then {
        diag_log format ["CTI|FAIL class=assertion_failed reinforce_probe_other_not_refused status=%1 code=%2 detail=%3",
            _other # 1, _other # 2, _other # 3];
    };
    // The refusal is a refusal in the world too, not only in the reply.
    if (count units _theirs isNotEqualTo _theirsBefore) then {
        diag_log format ["CTI|FAIL class=assertion_failed reinforce_probe_other_refilled squad=%1 before=%2 after=%3",
            _theirsId, _theirsBefore, count units _theirs];
    };
    diag_log format ["CTI|reinforce_probe_other squad=%1 units=%2->%3 code=%4",
        _theirsId, _theirsBefore, count units _theirs, _other # 2];
    "other" call _legRan;

    // ------------------------------------------------- a Command that stayed the Commander's
    private _rosterBefore = count ([_side] call cti_probe_fnc_squadsOf);
    private _purchase = ["purchase", {
        [] spawn {
            cti_lastJudgement = nil;
            private _cmd = ["purchase", [["squad_type", "rifle"]]] call cti_fnc_command;
            [_cmd] remoteExec ["cti_fnc_portGateway", 2];
            ["purchase"] call cti_probeJudge;
        };
    }] call _drive;

    if (_purchase isEqualTo []) exitWith { "purchase" call _legLost };
    if ((_purchase # 1) isNotEqualTo "rejected" || { (_purchase # 2) isNotEqualTo "wrong_side" }) then {
        diag_log format ["CTI|FAIL class=assertion_failed reinforce_probe_purchase_not_refused status=%1 code=%2 detail=%3",
            _purchase # 1, _purchase # 2, _purchase # 3];
    };

    // A Squad appears only when a Purchase is accepted, so the roster is the
    // observation a reply alone could not make.
    private _by = diag_tickTime + 15;
    waitUntil { diag_tickTime >= _by };
    private _rosterAfter = count ([_side] call cti_probe_fnc_squadsOf);
    if (_rosterAfter isNotEqualTo _rosterBefore) then {
        diag_log format ["CTI|FAIL class=assertion_failed reinforce_probe_leader_bought before=%1 after=%2",
            _rosterBefore, _rosterAfter];
    };
    diag_log format ["CTI|reinforce_probe_purchase code=%1 squads=%2->%3",
        _purchase # 2, _rosterBefore, _rosterAfter];
    "purchase" call _legRan;

    private _end = [_side] call _board;
    diag_log format ["CTI|reinforce_probe_board side=%1 mine=%2 theirs=%3",
        _side, _end getOrDefault [_mineId, -1], _end getOrDefault [_theirsId, -1]];

    diag_log "CTI|reinforce_probe_done";
};
