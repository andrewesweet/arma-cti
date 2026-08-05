// probe: dead-principal
// issues: 188
// window: 870
// env: CTI_WINDOWS_CLIENT=1 CTI_PROBE_CLIENT=240
//
// #188 in-world probe: ADR-0052's rulings 3 and 5 at the Command Port's door. A
// real client, killed by the server, refused `caller_dead` when he Commands and
// still served his `view` while he is dead; the same client, alive again,
// accepted on the same path; and the same client as the port's *other*
// principal — a squad leader — refused with the same code, which is the
// asymmetry ruling 5 exists to forbid.
//
// The refusal is the gateway's own and the daemon never sees the Command, so
// there is nothing here a Python test could have asked. What can only be asked
// in-world is the question the ADR left open and told this issue to probe rather
// than inherit: **what the server's owner-to-unit match sees while a player is
// dead.** `commands/allPlayers.wiki` says the list carries dead players, and
// cti_fnc_portGateway, cti_fnc_commanderSide and cti_fnc_commanderView all
// resolve the calling machine through it — so if a corpse stopped matching, the
// refusal would silently not fire and the view would silently stop. Both are
// read out loud below (`dead_principal_probe_match`) before either is asserted
// on, so a failure names which of the three resolutions moved.
//
// A headless client cannot stand in for the caller, for ADR-0025's reason:
// `remoteExecutedOwner` is 0 for a call from an HC by engine design and an HC
// holds no player unit. So this probe declares its headed client in its own
// `env:` header and reports every leg `unverified` when the run did not send
// one.
//
// **The death is held open on purpose, and that is arrangement rather than
// patience.** `missions/cti.Stratis/description.ext` sets `respawnDelay = 5`, so
// a player is back on his feet five seconds after dying and no cross-network
// judgement can be relied on to land inside that. The client is told
// `setPlayerRespawnTime 120` before each kill (`eff= local`, so it is set on the
// machine it belongs to), which makes the dead window 120 s against the 45 s
// ceiling a dead-window step is driven to — the arrangement strictly dominates
// the step's own deadline, so no assertion here can be defeated by a respawn
// arriving early. It is not a wait for a flaky assertion to come good: every
// dead-window leg asserts the caller was *still dead* when its judgement
// arrived, so a respawn that beat a leg is a red rather than a quiet pass.
//
// The window is 870 rather than the default 150 because the subject is that
// long, term by term: 20 s for the world to build, 240 s for a cold client to
// launch on the Windows host and be swept into the Commander slot (the
// allowance `client-port` and `reinforce` use; 24.7 s observed on #18's run),
// 60 s to buy and thin the Squad the second principal will lead, 45 s to arm the
// respawn hold and see the kill land, 45 s for the refused Command and 30 s for
// the view that has to keep arriving under it, 165 s for the held respawn to
// actually come round (120 s held, 45 s margin), 90 s for the same caller's
// accepted Command, 60 s to hand him the Squad and see leadership pass, 45 s to
// arm and kill him a second time and 45 s for the Reinforce that is refused.
// That is 845 s of deadlines; 870 leaves the probe's own logging inside it. The
// only irreducible cost is the 120 s of watching a dead man stay dead.
//
// Assertions are on the judgement's `code` and on the world's own count of men
// and Squads, never on a firefight: what the code under test owns is which
// refusal a caller earns, and nothing here asks the world to decide anything.
//
// The client-side judge-and-ack scaffold below is the third copy in the corpus
// (`client-port.sqf` has the first, `reinforce.sqf` the second, and that one's
// header says a third copy should lift it into `spike/probe-prelude.sqf`). It is
// still a copy here, deliberately and not silently: reconciling it means editing
// two green headed-client probes whose own corpus runs are this issue's landing
// gate, which would put #188 behind a refactor it does not need. The debt is
// filed rather than dropped — see the follow-up issue named on #188.
//
// `just regress dead-principal`, or by hand
// `just probe spike/probes/dead-principal.sqf`.
[] spawn {
    // Every leg this probe owes an answer for. A leg is struck off when it has
    // been measured; anything still standing at an early exit is reported
    // `unverified`, which the harness reads as infra_unavailable (ADR-0037,
    // #116). Kept as a list rather than written out per exit so a leg cannot be
    // forgotten at one of them, which is the whole failure the rule is about.
    private _owed = ["refused", "view", "revived", "leader"];
    private _ran = {
        params ["_leg"];
        private _at = _owed find _leg;
        if (_at >= 0) then { _owed deleteAt _at };
        diag_log format ["CTI|LEG name=dead_principal_%1 status=ran", _leg];
    };
    private _bail = {
        params ["_why"];
        {
            diag_log format ["CTI|LEG name=dead_principal_%1 status=unverified reason=%2", _x, _why];
        } forEach _owed;
        diag_log "CTI|dead_principal_probe_done";
    };

    private _extension = call cti_fnc_shimName;
    if (_extension isEqualTo "") exitWith {
        diag_log "CTI|FAIL class=infra_unavailable dead_principal_probe_no_shim";
        ["the_world_had_no_shim"] call _bail;
    };

    [20] call cti_probe_fnc_worldReady;

    // ---------------------------------------------------------------- the caller
    private _waitFor = missionNamespace getVariable ["CTI_PROBE_CLIENT", 0];
    if (_waitFor <= 0) exitWith {
        ["run_sent_no_headed_client"] call _bail;
    };

    ([_waitFor] call cti_probe_fnc_commanderSlot) params ["_side", "_uid", "_unit"];
    private _assigned = missionNamespace getVariable ["cti_commanders", createHashMap];
    if (_side isEqualTo "") exitWith {
        diag_log format ["CTI|FAIL class=timeout dead_principal_probe_no_client_assigned waited=%1 players=%2",
            _waitFor, count allPlayers];
        ["no_person_in_a_commander_slot"] call _bail;
    };
    if (isNull _unit) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed dead_principal_probe_assigned_uid_absent uid=%1", _uid];
        ["assigned_uid_holds_no_unit"] call _bail;
    };

    private _target = owner _unit;
    diag_log format ["CTI|dead_principal_probe_caller side=%1 owner=%2 uid=%3 role=%4",
        _side, _target, _uid, roleDescription _unit];

    // The same resolution the gateway performs, asked from the probe so that
    // what it sees is on the record beside every judgement. This is the ADR's
    // open question and #188's "probe it, do not inherit a guess": the answer
    // is logged while the caller is alive and again while he is dead.
    private _matched = {
        params ["_machine"];
        private _found = objNull;
        { if (owner _x isEqualTo _machine) exitWith { _found = _x } } forEach allPlayers;
        _found
    };
    private _picture = {
        params ["_when", "_machine"];
        private _found = [_machine] call _matched;
        ([_machine] call cti_fnc_leaderSquad) params ["_ledSide", "_ledSquad"];
        diag_log format ["CTI|dead_principal_probe_match when=%1 owner=%2 matched=%3 alive=%4 uid=%5 commands=%6 leads=%7/%8 players=%9",
            _when, _machine, !isNull _found, alive _found, getPlayerUID _found,
            [_machine] call cti_fnc_commanderSide, _ledSide, _ledSquad, count allPlayers];
        _found
    };
    ["alive", _target] call _picture;

    // ------------------------------------------------- the Squad he will lead
    // Bought and thinned now, before any of it matters, so that the respawn hold
    // below is the only thing anyone waits on. Thinned rather than left full for
    // a vacuity reason: a Reinforce for a Squad at the strength it was bought at
    // would be refused `already_held` by the daemon even from a living caller,
    // so "no men arrived" would prove nothing about the door. Deleted rather
    // than killed, as `reinforce` does — the refill is the subject, not corpses.
    [format ["dead-principal-probe-buy-%1", _side], _side, "rifle"] call cti_probe_fnc_buySquad;

    private _by = diag_tickTime + 60;
    private _roster = createHashMap;
    waitUntil {
        _roster = [_side] call cti_probe_fnc_squadsOf;
        count _roster >= 1 || { diag_tickTime > _by }
    };
    if (count _roster < 1) exitWith {
        diag_log format ["CTI|FAIL class=timeout dead_principal_probe_squad_never_spawned have=%1", count _roster];
        ["the_world_never_spawned_a_squad"] call _bail;
    };

    private _squadId = (keys _roster) # 0;
    private _squad = _roster get _squadId;
    { deleteVehicle _x } forEach ((units _squad) select [0, 3]);
    diag_log format ["CTI|dead_principal_probe_squad id=%1 units=%2", _squadId, count units _squad];

    // --------------------------------------------------------- the client's side
    // The judgement arrives on the client through cti_fnc_portReply and can only
    // be read there, so the client unpacks it and publishes an ack the server
    // reads. Every ack carries the step it belongs to, so a late one from the
    // step before is discarded rather than read as this step's answer.
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
                (_judgement getOrDefault ["result", createHashMap]) getOrDefault ["funds", -1],
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
            diag_log format ["CTI|FAIL class=timeout dead_principal_probe_client_silent step=%1", _step];
            []
        };
        private _ack = +cti_probeAck;
        diag_log format ["CTI|dead_principal_probe_ack step=%1 status=%2 code=%3 funds=%4 note=%5",
            _ack # 0, _ack # 1, _ack # 2, _ack # 4, _ack # 5];
        _ack
    };

    // Hold the next respawn open and kill him. The hold is a literal inside the
    // block rather than a value published ahead of it, so nothing here depends
    // on a publicVariable and a remoteExec arriving in the order they were sent.
    // `setPlayerRespawnTime` is `eff= local` and covers the next respawn only,
    // which is why this is armed again before the second death.
    private _kill = {
        params ["_tag", "_body"];
        cti_deadProbeArmed = nil;
        {
            setPlayerRespawnTime 120;
            cti_deadProbeArmed = playerRespawnTime;
            publicVariable "cti_deadProbeArmed";
        } remoteExec ["call", _target];

        private _by = diag_tickTime + 30;
        waitUntil { !isNil "cti_deadProbeArmed" || { diag_tickTime > _by } };
        if (isNil "cti_deadProbeArmed") exitWith {
            diag_log format ["CTI|FAIL class=timeout dead_principal_probe_hold_never_armed tag=%1", _tag];
            false
        };
        diag_log format ["CTI|dead_principal_probe_hold tag=%1 respawn_time=%2", _tag, cti_deadProbeArmed];

        _body setDamage 1;
        // #80's lesson: the staging is asserted to have taken effect before
        // anything is read through it. A world that refused the kill would
        // otherwise leave every assertion below testing a living caller and
        // reading as if it had tested a dead one.
        private _by = diag_tickTime + 15;
        waitUntil { !alive _body || { diag_tickTime > _by } };
        if (alive _body) exitWith {
            diag_log format ["CTI|FAIL class=assertion_failed dead_principal_probe_kill_refused tag=%1 damage=%2",
                _tag, damage _body];
            false
        };
        true
    };

    // ------------------------------------------------ a dead Commander Commands
    if !(["commander", _unit] call _kill) exitWith {
        ["the_caller_could_not_be_killed"] call _bail;
    };
    private _dead = ["dead-commander", _target] call _picture;

    private _rosterBefore = count ([_side] call cti_probe_fnc_squadsOf);
    private _refused = ["refused", {
        [] spawn {
            cti_lastJudgement = nil;
            private _cmd = ["purchase", [["squad_type", "rifle"]]] call cti_fnc_command;
            [_cmd] remoteExec ["cti_fnc_portGateway", 2];
            ["refused", "purchase while dead"] call cti_probeJudge;
        };
    }, 45] call _drive;

    if (_refused isEqualTo []) exitWith { ["client_never_acked_the_step"] call _bail };
    if ((_refused # 1) isNotEqualTo "rejected" || { (_refused # 2) isNotEqualTo "caller_dead" }) then {
        diag_log format ["CTI|FAIL class=assertion_failed dead_principal_probe_commander_not_refused status=%1 code=%2 detail=%3",
            _refused # 1, _refused # 2, _refused # 3];
    };
    // The refusal has to be about aliveness rather than about who was asking. A
    // dead Commander typed `wrong_side` would mean the check had drifted below
    // principal resolution, which is the one ordering ADR-0052 fixes.
    if ((_refused # 2) isEqualTo "wrong_side") then {
        diag_log "CTI|FAIL class=assertion_failed dead_principal_probe_refusal_resolved_first code=wrong_side";
    };
    // Still dead when the judgement came back, so the refusal is a fact about
    // the dead window and not about a caller who had already got up.
    if (alive ([_target] call _matched)) then {
        diag_log "CTI|FAIL class=assertion_failed dead_principal_probe_commander_respawned_mid_step";
    };
    // And a refusal in the world too, not only in the reply.
    private _rosterAfter = count ([_side] call cti_probe_fnc_squadsOf);
    if (_rosterAfter isNotEqualTo _rosterBefore) then {
        diag_log format ["CTI|FAIL class=assertion_failed dead_principal_probe_dead_commander_bought before=%1 after=%2",
            _rosterBefore, _rosterAfter];
    };
    diag_log format ["CTI|dead_principal_probe_commander code=%1 squads=%2->%3 corpse_matched=%4",
        _refused # 2, _rosterBefore, _rosterAfter, !isNull _dead];
    ["refused"] call _ran;

    // -------------------------------------------- and still watches while dead
    // Ruling 3's other half, and the one that would fail silently: the view is
    // pushed by cti_fnc_commanderView every interval, so the honest question is
    // whether a *fresh* one lands while he is dead. The client drops the picture
    // it holds and waits for the server to give it another.
    cti_deadProbeView = nil;
    {
        [] spawn {
            cti_view = nil;
            private _by = diag_tickTime + 30;
            waitUntil { !isNil "cti_view" || { diag_tickTime > _by } };
            cti_deadProbeView = [
                !isNil "cti_view",
                (missionNamespace getVariable ["cti_view", createHashMap]) getOrDefault ["side", ""],
                alive player
            ];
            publicVariable "cti_deadProbeView";
        };
    } remoteExec ["call", _target];

    private _by = diag_tickTime + 45;
    waitUntil { !isNil "cti_deadProbeView" || { diag_tickTime > _by } };
    if (isNil "cti_deadProbeView") exitWith {
        diag_log "CTI|FAIL class=timeout dead_principal_probe_view_never_reported";
        ["client_never_reported_its_view"] call _bail;
    };
    private _view = +cti_deadProbeView;
    if !(_view # 0) then {
        diag_log format ["CTI|FAIL class=assertion_failed dead_principal_probe_view_stopped side=%1 client_alive=%2",
            _view # 1, _view # 2];
    };
    if ((_view # 1) isNotEqualTo _side) then {
        diag_log format ["CTI|FAIL class=assertion_failed dead_principal_probe_view_wrong_side got=%1 want=%2",
            _view # 1, _side];
    };
    if (_view # 2) then {
        diag_log "CTI|FAIL class=assertion_failed dead_principal_probe_view_read_while_alive";
    };
    diag_log format ["CTI|dead_principal_probe_view arrived=%1 side=%2 client_alive=%3",
        _view # 0, _view # 1, _view # 2];
    ["view"] call _ran;

    // ------------------------------------------------------ and then gets up
    private _by = diag_tickTime + 165;
    waitUntil { alive ([_target] call _matched) || { diag_tickTime > _by } };
    private _living = [_target] call _matched;
    if (!alive _living) exitWith {
        diag_log format ["CTI|FAIL class=timeout dead_principal_probe_never_respawned held=120 matched=%1",
            !isNull _living];
        ["the_caller_never_came_back"] call _bail;
    };
    ["respawned", _target] call _picture;

    private _rosterBefore = count ([_side] call cti_probe_fnc_squadsOf);
    private _revived = ["revived", {
        [] spawn {
            cti_lastJudgement = nil;
            private _cmd = ["purchase", [["squad_type", "rifle"]]] call cti_fnc_command;
            [_cmd] remoteExec ["cti_fnc_portGateway", 2];
            ["revived", "purchase after respawn"] call cti_probeJudge;
        };
    }] call _drive;

    if (_revived isEqualTo []) exitWith { ["client_never_acked_the_step"] call _bail };
    if ((_revived # 1) isNotEqualTo "ok") then {
        diag_log format ["CTI|FAIL class=assertion_failed dead_principal_probe_revived_refused status=%1 code=%2 detail=%3",
            _revived # 1, _revived # 2, _revived # 3];
    };
    // A Squad appears only when a Purchase is accepted, so the roster is the
    // observation the reply alone could not make.
    private _by = diag_tickTime + 60;
    waitUntil { count ([_side] call cti_probe_fnc_squadsOf) > _rosterBefore || { diag_tickTime > _by } };
    private _rosterAfter = count ([_side] call cti_probe_fnc_squadsOf);
    if (_rosterAfter <= _rosterBefore) then {
        diag_log format ["CTI|FAIL class=timeout dead_principal_probe_revived_squad_never_arrived before=%1 after=%2",
            _rosterBefore, _rosterAfter];
    };
    diag_log format ["CTI|dead_principal_probe_revived status=%1 squads=%2->%3",
        _revived # 1, _rosterBefore, _rosterAfter];
    ["revived"] call _ran;

    // ---------------------------------------------- the port's other principal
    // The same person, no longer commanding anything, leading the Squad bought
    // above: the machine state a squad-leader slot would leave, made the way
    // `reinforce` makes it. The assignment is taken away by overwriting the
    // latched UID in the sweep's own HashMap, which the sweep skips rather than
    // re-latches.
    _assigned set [_side, "cti-dead-principal-probe-nobody"];
    [_living] joinSilent _squad;
    _squad selectLeader _living;

    private _by = diag_tickTime + 30;
    waitUntil { leader _squad isEqualTo _living || { diag_tickTime > _by } };
    if (leader _squad isNotEqualTo _living) exitWith {
        diag_log format ["CTI|FAIL class=timeout dead_principal_probe_leadership_never_passed squad=%1", _squadId];
        ["the_person_never_led_the_squad"] call _bail;
    };

    // The staging asserted before it is read through, again: while he is alive
    // the server resolves him as the second principal. Without this the refusal
    // below could be a caller who was never a principal at all, which is a
    // different sentence.
    ([_target] call cti_fnc_leaderSquad) params ["_ledSide", "_ledSquad"];
    if (_ledSquad isNotEqualTo _squadId) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed dead_principal_probe_leader_not_resolved got=%1/%2 want=%3",
            _ledSide, _ledSquad, _squadId];
        ["the_server_never_resolved_him_as_a_squad_leader"] call _bail;
    };
    diag_log format ["CTI|dead_principal_probe_leader_staged squad=%1 side=%2 units=%3 local=%4",
        _ledSquad, _ledSide, count units _squad, local _squad];

    cti_deadProbeSquad = _squadId;
    publicVariable "cti_deadProbeSquad";

    if !(["leader", _living] call _kill) exitWith {
        ["the_squad_leader_could_not_be_killed"] call _bail;
    };
    // What ADR-0052 says a post-resolution check would have seen, on the record
    // rather than asserted: the engine passes `leader` to the successor, so the
    // dead man resolves as no principal at all and would have been typed
    // `wrong_side`. Logged, because succession is the engine's behaviour and
    // this probe bets only on the decisions our own code owns.
    ["dead-leader", _target] call _picture;

    private _standingBefore = count units _squad;
    private _leaderStep = ["leader", {
        [] spawn {
            cti_lastJudgement = nil;
            private _cmd = ["reinforce", [["squad", cti_deadProbeSquad]]] call cti_fnc_command;
            [_cmd] remoteExec ["cti_fnc_portGateway", 2];
            ["leader", format ["asked for %1", cti_deadProbeSquad]] call cti_probeJudge;
        };
    }, 45] call _drive;

    if (_leaderStep isEqualTo []) exitWith { ["client_never_acked_the_step"] call _bail };
    if ((_leaderStep # 1) isNotEqualTo "rejected" || { (_leaderStep # 2) isNotEqualTo "caller_dead" }) then {
        diag_log format ["CTI|FAIL class=assertion_failed dead_principal_probe_leader_not_refused status=%1 code=%2 detail=%3",
            _leaderStep # 1, _leaderStep # 2, _leaderStep # 3];
    };
    // Ruling 5 in one line: the second principal earns the *same* code. A dead
    // squad leader typed `wrong_side` is the asymmetry the ADR refuses, and it
    // is what a check placed after principal resolution would have produced.
    if ((_leaderStep # 2) isEqualTo "wrong_side") then {
        diag_log "CTI|FAIL class=assertion_failed dead_principal_probe_leader_typed_wrong_side code=wrong_side";
    };
    if (alive ([_target] call _matched)) then {
        diag_log "CTI|FAIL class=assertion_failed dead_principal_probe_leader_respawned_mid_step";
    };
    private _standingAfter = count units _squad;
    if (_standingAfter > _standingBefore) then {
        diag_log format ["CTI|FAIL class=assertion_failed dead_principal_probe_dead_leader_refilled squad=%1 before=%2 after=%3",
            _squadId, _standingBefore, _standingAfter];
    };
    diag_log format ["CTI|dead_principal_probe_leader squad=%1 code=%2 units=%3->%4",
        _squadId, _leaderStep # 2, _standingBefore, _standingAfter];
    ["leader"] call _ran;

    diag_log "CTI|dead_principal_probe_done";
};
