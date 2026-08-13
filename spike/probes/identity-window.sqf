// probe: identity-window
// issues: 194
// window: 480
// env: CTI_HEADED_CLIENT=1 CTI_PROBE_CLIENT=240
//
// #194 in-world probe: how wide the empty-UID frame after respawn actually is,
// and that the Command Port now says the right thing on either side of it.
//
// ## What was found, and what this measures
//
// #188's `dead-principal` run logged one line the issue was raised on
// (`~/.arma-cti/runs/20260805T003409Z-dead-principal`, sha `637d718f0c69`): at
// the first server frame on which the owner match answered with a *living* unit
// after respawn, `getPlayerUID` on that unit was `""`. So cti_fnc_commanderSide
// could not match the latch it is keyed on, and a latched Commander was typed
// `wrong_side` — "this machine commands no side and leads no Squad", which is
// false of him at one frame and at fifty (ADR-0025 ruling 2, ADR-0052 ruling 5).
//
// That was one sample from a picture taken once. The human's ruling of
// 2026-08-06 turns it into a number: **poll every frame from the death and
// report the window**, so a later reader knows whether a client-side retry is
// ever warranted. It is a measurement and it asserts nothing about the width. A
// window wide enough for a human to click through is a new issue, not a red
// here.
//
// Every frame means the `EachFrame` mission event handler
// (`topics/Arma_3_Mission_Event_Handlers.wiki:140`, Arma 3 since 1.58), added on
// the server and therefore running there. A scheduled `waitUntil` would have
// been the wrong instrument: `topics/Scheduler.wiki` puts scheduled code on a
// time-sliced budget, so a window a frame or two wide could pass entirely
// between two of its turns and be measured as zero.
//
// The handler reads the world exactly the way cti_fnc_portGateway reads it —
// the *first* `allPlayers` entry the machine id matches, not the first living
// one — because what is being measured is what the door sees. It records where
// the two disagree (`corpse_first_frames`) rather than quietly preferring the
// living unit: a frame on which the gateway's first match is still the corpse
// is a `caller_dead` frame, a different refusal with a different cause, and if
// there are many of them that is its own finding.
//
// ## What is asserted, and why it is not the width
//
// The width is the world's, so nothing bets on it (#38). What the code under
// test owns is which sentence a caller earns, and there are two of those to
// pin:
//
//   - `respawned` — a latched Commander's Command, issued as soon after respawn
//     as a cross-network round trip allows, is **never** `wrong_side`. `ok` and
//     `identity_pending` are both correct answers and which one arrives is the
//     world's business; `wrong_side` is the defect this issue exists to remove
//     and is the only red.
//   - `unlatched` — the same client, alive, with a UID the server *can* read,
//     whose latch has been taken away, still earns `wrong_side` and not
//     `identity_pending`. This is the half that keeps the new code honest: the
//     ruling's whole basis for minting it is that the two states are
//     distinguishable with certainty, and a machine that genuinely commands
//     nothing has a readable UID that is not in `cti_commanders`.
//
// The `identity_pending` branch firing is deliberately not asserted anywhere,
// and that is a limit rather than an oversight: it fires only while the server
// cannot read a real client's real UID, a condition nothing here can stage — a
// probe cannot stub `getPlayerUID` and cannot slow the engine's identity
// propagation. What the measurement can say, and does, is how many frames the
// gateway's own predicate held for (`refusable_frames`), evaluated in the
// gateway's own terms. That is the honest form of "is this branch reachable".
//
// cti_fnc_commanderView is untouched by this issue on the human's ruling, and
// `refusable_frames` is also the width of what it skips: the push resolves its
// target by UID the same way, so it misses him for those frames and the next
// cycle five seconds later carries the picture. Recorded here, asserted
// nowhere, because a view is not a refusal a player reads.
//
// ## The staging is asserted before it is read through (#80)
//
// The kill is asserted to have landed before the trace is trusted, the trace is
// asserted to have seen the death before its window is read, and the
// `unlatched` leg asserts both halves of its own arrangement — a readable UID
// and a caller leading no Squad — before it reads a refusal through them.
// Without those, a world that refused the staging would leave every line below
// measuring a living, latched Commander and reading as if it had measured
// something else.
//
// ## Window
//
// 480 s, term by term:
//   240  the client's cold start on the Windows host, as `env:` above declares
//        and `client-port` measured
//    20  the world built and both server loops turned once (worldReady)
//    20  the kill issued and seen to land
//    75  the configured 30 s respawn timer, plus the new unit appearing, plus
//        margin — `respawn-base`'s own budget for the same wait
//    45  the Command issued after respawn and its judgement crossing back
//    45  the same for the unlatched Command
//    35  slack, and the probe's own logging
// The 30 s in there is the subject and cannot be shortened. The 240 dominates
// and belongs to the client, not to this probe. Nothing here was raised to make
// an assertion come good.
//
// `just regress identity-window`, or by hand
// `just probe spike/probes/identity-window.sqf`.
[] spawn {
    // Every leg this probe owes an answer for (ADR-0037, #116), on the shared
    // ledger (#193): whatever is still owed at an exit is reported `unverified`
    // rather than left out of the evidence.
    ["identity", ["window", "respawned", "unlatched"]] call cti_probe_fnc_legsOwed;

    private _extension = call cti_fnc_shimName;
    if (_extension isEqualTo "") exitWith {
        diag_log "CTI|FAIL class=infra_unavailable identity_probe_no_shim";
        ["the_world_had_no_shim"] call cti_probe_fnc_done;
    };

    [20] call cti_probe_fnc_worldReady;

    // ---------------------------------------------------------------- the caller
    // A headless client cannot stand in for him, for ADR-0025's reason: it holds
    // no player unit, so there is nothing to kill, nothing to respawn and no UID
    // to fail to propagate.
    private _waitFor = missionNamespace getVariable ["CTI_PROBE_CLIENT", 0];
    if (_waitFor <= 0) exitWith {
        ["run_sent_no_headed_client"] call cti_probe_fnc_done;
    };

    ([_waitFor] call cti_probe_fnc_commanderSlot) params ["_side", "_uid", "_unit"];
    private _assigned = missionNamespace getVariable ["cti_commanders", createHashMap];
    if (_side isEqualTo "") exitWith {
        diag_log format ["CTI|FAIL class=timeout identity_probe_no_client_assigned waited=%1 players=%2",
            _waitFor, count allPlayers];
        ["no_person_in_a_commander_slot"] call cti_probe_fnc_done;
    };
    if (isNull _unit) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed identity_probe_assigned_uid_absent uid=%1", _uid];
        ["assigned_uid_holds_no_unit"] call cti_probe_fnc_done;
    };

    private _target = owner _unit;
    // The engine's own copy of the setting rather than a second authored 30 to
    // drift from it, as `respawn-base` reads it. The window below is sized on
    // this number, so a config that carries none is a run whose arithmetic is
    // not the one the header states.
    private _delay = getNumber (missionConfigFile >> "respawnDelay");
    if (_delay <= 0) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed identity_probe_no_configured_delay read=%1", _delay];
        ["the_mission_config_carries_no_respawn_delay"] call cti_probe_fnc_done;
    };
    diag_log format ["CTI|identity_probe_caller side=%1 owner=%2 uid=%3 delay=%4 role=%5",
        _side, _target, _uid, _delay, roleDescription _unit];

    // The judgement arrives on the client through cti_fnc_portReply and can only
    // be read there, so the client is armed to unpack it and publish an ack the
    // server reads (`cti_probe_fnc_armClient` / `cti_probe_fnc_drive`, prelude).
    // Armed before the kill so that neither Command leg waits on it.
    [_target] call cti_probe_fnc_armClient;

    // ------------------------------------------------------------- the trace
    // The machine id is published as a global rather than closed over, because
    // it cannot be closed over: `commands/onEachFrame.wiki` example 2 says in
    // as many words that private variables defined outside the scope are not
    // inherited, and a handler reading `any` for the machine would match nobody
    // and report a window of zero.
    cti_identityProbeOwner = _target;
    cti_identityProbeTrace = createHashMapFromArray [
        ["frames", 0],
        ["saw_dead", false],
        ["dead_frames", 0],
        ["corpse_first_frames", 0],
        ["blind_frames", 0],
        ["refusable_frames", 0],
        ["living_at", -1],
        ["living_frame", -1],
        ["identified_at", -1],
        ["identified_frame", -1],
        ["uid", ""],
        ["commands", ""]
    ];

    // Unscheduled, so nothing in here may suspend — `commands/onEachFrame.wiki`
    // example 4 says a `sleep` inside this scope throws. It reads the world,
    // updates the trace and returns inside the frame; the two addon functions it
    // calls are straight-line walks of `allPlayers` with no wait in either.
    cti_identityProbeEh = addMissionEventHandler ["EachFrame", {
        private _trace = missionNamespace getVariable ["cti_identityProbeTrace", createHashMap];
        private _machine = missionNamespace getVariable ["cti_identityProbeOwner", -1];
        _trace set ["frames", (_trace get "frames") + 1];

        // Both readings in one pass: `_first` is what cti_fnc_portGateway would
        // resolve as the caller, `_living` is whether a living unit exists on
        // that machine at all. They are the same object on almost every frame
        // and the frames where they are not are the ones worth counting.
        private _first = objNull;
        private _living = objNull;
        {
            if (owner _x isEqualTo _machine) then {
                if (isNull _first) then { _first = _x };
                if (isNull _living && { alive _x }) then { _living = _x };
            };
        } forEach allPlayers;

        // No player unit on that machine at all: nothing to say about it.
        if (isNull _first) exitWith {};

        // The gateway sees a corpse, so it would refuse `caller_dead` — a
        // different code for a different cause, and never the state this probe
        // is measuring.
        if !(alive _first) exitWith {
            _trace set ["saw_dead", true];
            _trace set ["dead_frames", (_trace get "dead_frames") + 1];
            if (!isNull _living) then {
                _trace set ["corpse_first_frames", (_trace get "corpse_first_frames") + 1];
            };
        };

        // Alive and matched, but before the staged death this is simply the old
        // unit going about its business.
        if !(_trace get "saw_dead") exitWith {};

        if ((_trace get "living_at") < 0) then {
            _trace set ["living_at", diag_tickTime];
            _trace set ["living_frame", _trace get "frames"];
        };

        private _readable = getPlayerUID _first;
        if (_readable isEqualTo "") exitWith {
            _trace set ["blind_frames", (_trace get "blind_frames") + 1];
            // The gateway's own predicate, in the gateway's own terms and in its
            // own order: the Commander's latch first, then the second
            // principal's slot. A frame on which both answer nothing is a frame
            // on which the new refusal would have fired.
            private _resolved = [_machine] call cti_fnc_commanderSide;
            if (_resolved isEqualTo "") then {
                _resolved = ([_machine] call cti_fnc_leaderSquad) # 0;
            };
            if (_resolved isEqualTo "") then {
                _trace set ["refusable_frames", (_trace get "refusable_frames") + 1];
            };
        };

        if ((_trace get "identified_at") < 0) then {
            _trace set ["identified_at", diag_tickTime];
            _trace set ["identified_frame", _trace get "frames"];
            _trace set ["uid", _readable];
            _trace set ["commands", [_machine] call cti_fnc_commanderSide];
        };
    }];

    // The instrument is asserted to be running before anything is measured
    // through it (#80), and asserted *here* rather than at the end: a handler
    // that never fires would otherwise be found only after the death and the
    // 30 s respawn had been spent finding it, and the evidence would say
    // "measured nothing" where the honest sentence is "never measured".
    private _by = diag_tickTime + 10;
    waitUntil { (cti_identityProbeTrace get "frames") > 0 || { diag_tickTime > _by } };
    if ((cti_identityProbeTrace get "frames") <= 0) exitWith {
        removeMissionEventHandler ["EachFrame", cti_identityProbeEh];
        diag_log "CTI|FAIL class=assertion_failed identity_probe_trace_never_started";
        ["the_every_frame_handler_never_turned"] call cti_probe_fnc_done;
    };
    diag_log format ["CTI|identity_probe_trace_armed frames=%1 owner=%2",
        cti_identityProbeTrace get "frames", _target];

    // -------------------------------------------------------------- the death
    // Armed above, so the death frame itself is inside the trace.
    private _diedAt = diag_tickTime;
    _unit setDamage 1;

    private _by = diag_tickTime + 20;
    waitUntil { !alive _unit || { diag_tickTime > _by } };
    if (alive _unit) exitWith {
        removeMissionEventHandler ["EachFrame", cti_identityProbeEh];
        diag_log format ["CTI|FAIL class=assertion_failed identity_probe_kill_refused damage=%1",
            damage _unit];
        ["the_staged_death_never_took_effect"] call cti_probe_fnc_done;
    };

    // ------------------------------------------------------------ coming back
    // The trace is what measures; this only waits for it to have something to
    // report. The deadline is the configured timer plus `respawn-base`'s own
    // margin for the new unit to appear.
    private _by = _diedAt + _delay + 75;
    waitUntil {
        ((cti_identityProbeTrace get "identified_at") >= 0) || { diag_tickTime > _by }
    };
    removeMissionEventHandler ["EachFrame", cti_identityProbeEh];
    private _trace = +cti_identityProbeTrace;

    // The measurement is read through its own staging, so the rest of the
    // staging is asserted before the window is (#80; the handler's own turning
    // was asserted before the kill). Each of these says the trace never covered
    // its subject, which is a different sentence from "the window was wide".
    if !(_trace get "saw_dead") exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed identity_probe_trace_missed_the_death frames=%1",
            _trace get "frames"];
        ["the_trace_never_saw_the_caller_dead"] call cti_probe_fnc_done;
    };
    // `corpse_first_frames` is in this line because it separates two very
    // different causes wearing one symptom: the caller genuinely never respawned
    // (zero), or he did and the gateway's first `allPlayers` match kept
    // answering with his corpse, which would type him `caller_dead` for as long
    // as it lasted. The second is a finding rather than a stalled world.
    if ((_trace get "living_at") < 0) exitWith {
        diag_log format ["CTI|FAIL class=timeout identity_probe_never_came_back delay=%1 waited=%2 frames=%3 dead_frames=%4 corpse_first_frames=%5",
            _delay, round (diag_tickTime - _diedAt), _trace get "frames",
            _trace get "dead_frames", _trace get "corpse_first_frames"];
        ["the_caller_never_came_back"] call cti_probe_fnc_done;
    };
    // The identity never arriving at all is the wiki's warning coming true
    // (`commands/getPlayerUID.wiki`: propagation can *fail*, not merely be
    // slow), and it is a different bug from the one this issue fixed — the
    // refusal would be permanent rather than retryable. Said out loud rather
    // than reported as a wide window.
    if ((_trace get "identified_at") < 0) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed identity_probe_identity_never_propagated blind_frames=%1 waited=%2",
            _trace get "blind_frames", round (diag_tickTime - (_trace get "living_at"))];
        ["the_servers_reading_of_his_identity_never_arrived"] call cti_probe_fnc_done;
    };

    // The number the ruling asked for. Asserted nowhere: a window wide enough
    // for a human to click through is a new issue about a client-side retry,
    // not a red on this one.
    private _windowFrames = (_trace get "identified_frame") - (_trace get "living_frame");
    private _windowSecs = (_trace get "identified_at") - (_trace get "living_at");
    // Two lines rather than one, and the reason is arithmetic rather than
    // taste: nothing in this repo's SQF has ever written a `%10` placeholder,
    // and a probe whose entire product is its evidence is the wrong place to be
    // the first to find out whether `format` reads it as the tenth argument or
    // as the first followed by a nought.
    diag_log format ["CTI|identity_probe_window frames=%1 living_frame=%2 identified_frame=%3 window_frames=%4 window_secs=%5",
        _trace get "frames", _trace get "living_frame", _trace get "identified_frame",
        _windowFrames, _windowSecs];
    diag_log format ["CTI|identity_probe_frames blind=%1 refusable=%2 dead=%3 corpse_first=%4 uid_readable=%5 commands=%6 latched_uid=%7",
        _trace get "blind_frames", _trace get "refusable_frames", _trace get "dead_frames",
        _trace get "corpse_first_frames", (_trace get "uid") isNotEqualTo "",
        _trace get "commands", _uid];
    ["window"] call cti_probe_fnc_legRan;

    // ------------------------------------------- what he is told after respawn
    // The defect, end to end. Both `ok` and `identity_pending` are correct
    // answers and which one arrives depends on whether the round trip beat the
    // propagation, which is the world's business rather than this code's.
    // `wrong_side` is the sentence ADR-0025 ruling 2 and ADR-0052 ruling 5 both
    // make false of a latched Commander, and it is the only red.
    private _respawned = ["respawned", {
        [] spawn {
            cti_lastJudgement = nil;
            private _cmd = ["purchase", [["squad_type", "rifle"]]] call cti_fnc_command;
            [_cmd] remoteExec ["cti_fnc_portGateway", 2];
            ["respawned", "purchase straight after respawn", "funds"] call cti_probeJudge;
        };
    }, 45] call cti_probe_fnc_drive;

    if (_respawned isEqualTo []) exitWith {
        ["client_never_acked_the_step"] call cti_probe_fnc_done;
    };
    if ((_respawned # 2) isEqualTo "wrong_side") then {
        diag_log format ["CTI|FAIL class=assertion_failed identity_probe_respawned_typed_wrong_side status=%1 detail=%2",
            _respawned # 1, _respawned # 3];
    };
    // And nothing else either: a latched Commander who has got up earns one of
    // exactly two answers, and a third would be a refusal nobody designed.
    if !((_respawned # 1) isEqualTo "ok"
        || { (_respawned # 1) isEqualTo "rejected" && { (_respawned # 2) isEqualTo "identity_pending" } }) then {
        diag_log format ["CTI|FAIL class=assertion_failed identity_probe_respawned_unexpected status=%1 code=%2 detail=%3",
            _respawned # 1, _respawned # 2, _respawned # 3];
    };
    diag_log format ["CTI|identity_probe_respawned status=%1 code=%2 funds=%3",
        _respawned # 1, _respawned # 2, _respawned # 4];
    ["respawned"] call cti_probe_fnc_legRan;

    // ------------------------------------ and what a caller who really commands
    // ------------------------------------ nothing is still told
    // The latch is taken away by overwriting the UID in the sweep's own HashMap,
    // which the sweep skips rather than re-latches (`fn_commanderAssign.sqf`:
    // a side already in the map is never revisited). `dead-principal` stages its
    // second principal the same way.
    _assigned set [_side, "cti-identity-probe-nobody"];

    // Both halves of the arrangement asserted before a refusal is read through
    // them. A readable UID is what makes this the *other* state rather than the
    // one above, and leading no Squad is what makes `wrong_side` the whole of
    // the answer — a caller who led one would be stamped from his slot and
    // judged, not refused.
    private _still = objNull;
    { if (owner _x isEqualTo _target) exitWith { _still = _x } } forEach allPlayers;
    if (isNull _still || { !alive _still } || { getPlayerUID _still isEqualTo "" }) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed identity_probe_unlatched_caller_unreadable matched=%1 alive=%2 uid_readable=%3",
            !isNull _still, alive _still, (getPlayerUID _still) isNotEqualTo ""];
        ["the_caller_was_not_readable_when_his_latch_was_taken"] call cti_probe_fnc_done;
    };
    ([_target] call cti_fnc_leaderSquad) params ["_ledSide", "_ledSquad"];
    if (_ledSquad isNotEqualTo "") exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed identity_probe_unlatched_leads_a_squad side=%1 squad=%2",
            _ledSide, _ledSquad];
        ["the_unlatched_caller_was_still_a_principal"] call cti_probe_fnc_done;
    };
    if (([_target] call cti_fnc_commanderSide) isNotEqualTo "") exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed identity_probe_unlatch_refused side=%1 commands=%2",
            _side, [_target] call cti_fnc_commanderSide];
        ["the_latch_could_not_be_taken_away"] call cti_probe_fnc_done;
    };
    diag_log format ["CTI|identity_probe_unlatched_staged side=%1 uid_readable=%2 leads=%3",
        _side, (getPlayerUID _still) isNotEqualTo "", _ledSquad];

    private _unlatched = ["unlatched", {
        [] spawn {
            cti_lastJudgement = nil;
            private _cmd = ["purchase", [["squad_type", "rifle"]]] call cti_fnc_command;
            [_cmd] remoteExec ["cti_fnc_portGateway", 2];
            ["unlatched", "purchase with the latch taken away"] call cti_probeJudge;
        };
    }, 45] call cti_probe_fnc_drive;

    if (_unlatched isEqualTo []) exitWith {
        ["client_never_acked_the_step"] call cti_probe_fnc_done;
    };
    if ((_unlatched # 1) isNotEqualTo "rejected" || { (_unlatched # 2) isNotEqualTo "wrong_side" }) then {
        diag_log format ["CTI|FAIL class=assertion_failed identity_probe_unlatched_not_wrong_side status=%1 code=%2 detail=%3",
            _unlatched # 1, _unlatched # 2, _unlatched # 3];
    };
    // The new code firing here would mean it does not fire only for the case it
    // names, which is the ruling's whole basis for minting it rather than
    // widening `wrong_side`.
    if ((_unlatched # 2) isEqualTo "identity_pending") then {
        diag_log "CTI|FAIL class=assertion_failed identity_probe_readable_caller_typed_identity_pending code=identity_pending";
    };
    diag_log format ["CTI|identity_probe_unlatched status=%1 code=%2",
        _unlatched # 1, _unlatched # 2];
    ["unlatched"] call cti_probe_fnc_legRan;

    [] call cti_probe_fnc_done;
};
