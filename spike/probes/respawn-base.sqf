// probe: respawn-base
// issues: 189
// window: 480
// env: CTI_WINDOWS_CLIENT=1 CTI_PROBE_CLIENT=240
//
// #189 in-world probe: ADR-0052's rulings 1 and 6. A real person leading a Squad
// is killed in the field, and comes back at his own side's Base after the
// configured timer and nowhere else.
//
// A headless client cannot stand in for him. It holds no player unit, so there
// is nothing to kill and nothing to respawn — the same reason `client-port` and
// `reinforce` give. So this declares its headed client in its own `env:` header
// and reports its legs `unverified` when the run did not send one, rather than
// passing on a world where the subject was never present (#116).
//
// ## Ruling 4 is watched here, not asserted, and that is a finding
//
// This probe's first version asserted ruling 4's premise — that when a player
// squad leader dies "engine AI succession leads meanwhile" — and went red on the
// corpus run of 2026-08-05 (`~/.arma-cti/runs/20260805T011658Z-respawn-base`,
// sha 5926a6a). The engine does not do it. A 120 s observation across one death
// (57 rows, evidence quoted on #189) says leadership never moves at all: the
// dead player holds `leader` for the whole 30 s window, the group is 9 strong
// throughout, and at t=30 he respawns into a new unit that is *already* in that
// group and *already* leading it.
//
// So there is no interregnum to assert and nothing to reclaim, and this probe
// will not invent either. Ruling 4 is a human decision on a premise the world has
// falsified, which is the case ADR-0052's own "What would overturn this" reserves
// for the human — so the leadership timeline is logged here as evidence, in one
// line per observation, and asserted nowhere. A probe that quietly re-specified
// the ruling to match the engine would be this project's own "edit the spec to
// make it pass", one level down.
//
// ## What is staged and what is bet on
//
// Staged: the Squad, the person's place in it, where they are standing, and the
// death. Bet on: only what rulings 1 and 6 promise — that the timer is the
// configured one and that he arrives inside his own Base. Nothing here waits on
// a firefight or on AI pathing, which is #38's rule.
//
// He is killed 2.9 km from his Base (WEST) or 5.2 km from it (EAST), standing on
// the Objective furthest from it, chosen off the manifest so the arrangement does
// not care which Commander slot the client landed in. That distance is what makes
// "he came back at his Base" worth asserting: a man who died at his Base and
// respawned there would prove nothing.
//
// The Squad is teleported to that ground rather than marched to it, and is
// ordered to defend the ground it is standing on. The order matters:
// `cti_fnc_orderEnforce` re-asserts a standing Order once a Squad has run out of
// waypoints *and* drifted off the ground it was sent to, so a Squad ordered
// somewhere it is not would have its waypoints rewritten mid-window by a sweep
// that has nothing to do with this subject.
//
// ## The number is read back, never copied
//
// The delay is read from the mission config the engine itself is reading
// (`missionConfigFile >> "respawnDelay"`, which is description.ext), so this
// probe holds no second copy of 30 to drift from the one that is set. It is a
// playtest-tuned placeholder and a playtest may move it; the assertion is "not
// before the configured delay", which survives the move. The observed respawn on
// 2026-08-05 landed on t=30 exactly.
//
// ## Window
//
// 480 s, and every second of it is somebody's arithmetic:
//   240  the client's cold start on the Windows host, as `client-port` measured
//        it and `env:` above declares it
//    20  the world built and both server loops turned once (worldReady)
//    60  a Squad bought through the port and spawned into the world
//    30  the Order issued through the port, crossing the outbox, landing
//    30  the Squad staged on that ground, the person joined to it and leading
//    75  the death, plus the 30 s respawn timer, plus the new unit appearing
//    25  the leadership timeline watched past the respawn, for the record
//    20  slack
// The 30 s in there is the subject and cannot be shortened; the 240 dominates
// and is the client's, not this probe's. Nothing here was raised to make a
// flaky assertion pass — the one number that moved, 540 down to 480, moved down,
// because the legs that asserted ruling 4 are gone.
[] spawn {
    private _extension = call cti_fnc_shimName;
    if (_extension isEqualTo "") exitWith {
        diag_log "CTI|FAIL class=infra_unavailable respawn_probe_no_shim";
        diag_log "CTI|respawn_probe_done";
    };

    private _legs = ["respawn_timer", "respawn_succession"];
    private _lost = {
        params ["_why"];
        { diag_log format ["CTI|LEG name=%1 status=unverified reason=%2", _x, _why] } forEach _legs;
        diag_log "CTI|respawn_probe_done";
    };

    [20] call cti_probe_fnc_worldReady;

    // ---------------------------------------------------------------- the person
    private _waitFor = missionNamespace getVariable ["CTI_PROBE_CLIENT", 0];
    if (_waitFor <= 0) exitWith { ["run_sent_no_headed_client"] call _lost };

    ([_waitFor] call cti_probe_fnc_commanderSlot) params ["_side", "_uid", "_unit"];
    if (_side isEqualTo "") exitWith {
        diag_log format ["CTI|FAIL class=timeout respawn_probe_no_client_assigned waited=%1 players=%2",
            _waitFor, count allPlayers];
        ["no_person_in_a_commander_slot"] call _lost;
    };
    if (isNull _unit) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed respawn_probe_assigned_uid_absent uid=%1", _uid];
        ["assigned_uid_holds_no_unit"] call _lost;
    };

    // The engine's own copy of the setting, rather than a number written twice.
    private _delay = getNumber (missionConfigFile >> "respawnDelay");
    if (_delay <= 0) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed respawn_probe_no_configured_delay read=%1", _delay];
        ["the_mission_config_carries_no_respawn_delay"] call _lost;
    };

    private _base = (missionNamespace getVariable ["cti_basesBySide", createHashMap])
        getOrDefault [_side, createHashMap];
    if (count _base isEqualTo 0) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed respawn_probe_no_base side=%1", _side];
        ["the_world_holds_no_base_for_that_side"] call _lost;
    };
    (_base get "position") params ["_baseEast", "_baseNorth"];
    private _baseAt = [_baseEast, _baseNorth, 0];
    // One reading of how close counts as being at a Place, the addon's own.
    private _baseRadius = [_base] call cti_fnc_placeRadius;

    diag_log format ["CTI|respawn_probe_setting side=%1 delay=%2 base=%3 radius=%4",
        _side, _delay, _base get "id", _baseRadius];

    // --------------------------------------------------------------- the ground
    private _far = createHashMap;
    private _farBy = -1;
    {
        private _at = _x get "position";
        private _away = _baseAt distance2D [_at # 0, _at # 1, 0];
        if (_away > _farBy) then {
            _farBy = _away;
            _far = _x;
        };
    } forEach ((missionNamespace getVariable ["cti_map", createHashMap]) getOrDefault ["objectives", []]);
    if (count _far isEqualTo 0) exitWith {
        diag_log "CTI|FAIL class=assertion_failed respawn_probe_no_objectives";
        ["the_manifest_offered_no_ground_to_stand_on"] call _lost;
    };
    (_far get "position") params ["_farEast", "_farNorth"];
    diag_log format ["CTI|respawn_probe_ground place=%1 from_base=%2", _far get "id", round _farBy];

    // ---------------------------------------------------------------- his Squad
    [format ["respawn-probe-buy-%1", _side], _side, "rifle"] call cti_probe_fnc_buySquad;

    private _by = diag_tickTime + 60;
    private _squads = createHashMap;
    waitUntil {
        _squads = [_side] call cti_probe_fnc_squadsOf;
        count _squads > 0 || { diag_tickTime > _by }
    };
    if (count _squads isEqualTo 0) exitWith {
        diag_log "CTI|FAIL class=timeout respawn_probe_squad_never_spawned";
        ["the_world_never_spawned_a_squad"] call _lost;
    };
    private _squadId = (keys _squads) # 0;
    private _group = _squads get _squadId;

    // The Order, through the port, because that is the only way one is made.
    private _reply = [createHashMapFromArray [
        ["id", format ["respawn-probe-order-%1", _squadId]],
        ["verb", "command"],
        ["payload", createHashMapFromArray [
            ["command", "order"],
            ["side", _side],
            // Stamped by the probe because there is no gateway on this path
            // (ADR-0044): an unstamped line is refused `unknown_caller`.
            ["acting_side", _side],
            ["args", createHashMapFromArray [
                ["squad", _squadId], ["order", "defend"], ["place", _far get "id"]
            ]]
        ]]
    ]] call cti_probe_fnc_rpc;
    if ((_reply getOrDefault ["status", ""]) isNotEqualTo "ok") then {
        diag_log format ["CTI|FAIL class=assertion_failed respawn_probe_order_refused reply=%1", _reply];
    };

    // The standing Order as four values rather than as the HashMap holding them.
    // `isEqualTo` is documented for Arrays and says nothing about HashMaps
    // (commands/isEqualTo.wiki), and a comparison whose semantics the wiki does
    // not state is not one to build a red on.
    private _orderOf = {
        private _standing = _this getVariable ["cti_order", createHashMap];
        +[_standing getOrDefault ["order", ""], _standing getOrDefault ["place", ""],
            _standing getOrDefault ["position", []], _standing getOrDefault ["radius", -1]]
    };

    private _by = diag_tickTime + 30;
    waitUntil { (_group call _orderOf) # 0 isEqualTo "defend" || { diag_tickTime > _by } };
    if ((_group call _orderOf) # 0 isNotEqualTo "defend") exitWith {
        diag_log format ["CTI|FAIL class=timeout respawn_probe_order_never_landed standing=%1",
            _group getVariable ["cti_order", createHashMap]];
        ["the_squad_never_took_a_standing_order"] call _lost;
    };

    // Standing on the ground they are ordered to hold, so cti_fnc_orderEnforce
    // never finds them adrift and never rewrites their waypoints mid-window.
    {
        _x setPosATL [_farEast + (_forEachIndex * 4), _farNorth, 0];
    } forEach units _group;

    // ------------------------------------------------------- the person leads it
    // `joinSilent` is global in argument and effect; `selectLeader` takes a local
    // group, and the Squad is the server's until this line, which is what makes
    // it legal here (topics/Multiplayer_Scripting.wiki:219).
    [_unit] joinSilent _group;
    _unit setPosATL [_farEast - 6, _farNorth, 0];
    _group selectLeader _unit;

    private _by = diag_tickTime + 30;
    waitUntil { leader _group isEqualTo _unit || { diag_tickTime > _by } };
    if (leader _group isNotEqualTo _unit) exitWith {
        diag_log format ["CTI|FAIL class=timeout respawn_probe_leadership_never_passed squad=%1", _squadId];
        ["the_person_never_led_the_squad"] call _lost;
    };

    private _waypointsOf = {
        (waypoints _this) apply { [waypointPosition _x, waypointType _x] }
    };
    private _orderBefore = _group call _orderOf;
    private _waypointsBefore = _group call _waypointsOf;
    private _diedFrom = _unit distance2D _baseAt;
    diag_log format ["CTI|respawn_probe_before squad=%1 order=%2 place=%3 waypoints=%4 leader=%5 local=%6 from_base=%7",
        _squadId, _orderBefore # 0, _orderBefore # 1,
        count _waypointsBefore, name _unit, local _group, round _diedFrom];

    // -------------------------------------------------------------- the death
    private _diedAt = diag_tickTime;
    _unit setDamage 1;

    private _by = diag_tickTime + 20;
    waitUntil { !alive _unit || { diag_tickTime > _by } };
    if (alive _unit) exitWith {
        diag_log "CTI|FAIL class=timeout respawn_probe_the_person_would_not_die";
        ["the_staged_death_never_took_effect"] call _lost;
    };

    // ------------------------------------------------------------- coming back
    // `allPlayers` holds dead players too (ADR-0052 reads the same line), so the
    // new unit is the live one wearing his UID — never merely "not the old one".
    private _him = {
        private _found = objNull;
        { if (alive _x && { getPlayerUID _x isEqualTo _this }) exitWith { _found = _x } } forEach allPlayers;
        _found
    };

    // While waiting, the leadership timeline goes on the record — one line every
    // five seconds, asserting nothing. This is the evidence ruling 4 is now a
    // question about (see the header), kept where the corpus keeps evidence
    // rather than in a session that has ended.
    private _by = _diedAt + _delay + 45;
    private _new = objNull;
    private _nextAt = 0;
    waitUntil {
        if (diag_tickTime > _nextAt) then {
            _nextAt = diag_tickTime + 5;
            private _seat = leader _group;
            diag_log format ["CTI|respawn_probe_seat t=%1 leader=%2 alive=%3 is_player=%4 group_local=%5 units=%6",
                round (diag_tickTime - _diedAt), name _seat, alive _seat, isPlayer _seat,
                local _group, count units _group];
        };
        _new = _uid call _him;
        !isNull _new || { diag_tickTime > _by }
    };
    if (isNull _new) exitWith {
        diag_log format ["CTI|FAIL class=timeout respawn_probe_never_came_back uid=%1 waited=%2 delay=%3",
            _uid, round (diag_tickTime - _diedAt), _delay];
        diag_log "CTI|LEG name=respawn_timer status=unverified reason=the_person_never_respawned";
        diag_log "CTI|LEG name=respawn_succession status=unverified reason=the_person_never_respawned";
        diag_log "CTI|respawn_probe_done";
    };
    private _took = diag_tickTime - _diedAt;

    // Ruling 6: not before the configured delay. Polling can only make this
    // reading longer than the truth, never shorter, so an early respawn is a
    // real one — which is what a second copy of the number quietly winning
    // would look like.
    if (_took < _delay) then {
        diag_log format ["CTI|FAIL class=assertion_failed respawn_probe_came_back_early took=%1 delay=%2",
            _took, _delay];
    };

    // Ruling 1: at his own Base, which is what the respawn markers resolve to.
    private _cameBackAt = _new distance2D _baseAt;
    if (_cameBackAt > _baseRadius) then {
        diag_log format ["CTI|FAIL class=assertion_failed respawn_probe_came_back_elsewhere base=%1 away=%2 radius=%3 at=%4",
            _base get "id", round _cameBackAt, _baseRadius, mapGridPosition _new];
    };
    diag_log format ["CTI|respawn_probe_timer took=%1 delay=%2 died_from_base=%3 base=%4 away=%5 radius=%6 grid=%7",
        round _took, _delay, round _diedFrom, _base get "id",
        round _cameBackAt, _baseRadius, mapGridPosition _new];
    diag_log "CTI|LEG name=respawn_timer status=ran";

    // The standing Order is still the one he left, which ruling 4 promises and
    // which — unlike the succession it also promises — the world does deliver.
    private _orderAfter = _group call _orderOf;
    if !(_orderAfter isEqualTo _orderBefore) then {
        diag_log format ["CTI|FAIL class=assertion_failed respawn_probe_order_changed before=%1 after=%2",
            _orderBefore, _orderAfter];
    };
    private _waypointsAfter = _group call _waypointsOf;
    if !(_waypointsAfter isEqualTo _waypointsBefore) then {
        diag_log format ["CTI|FAIL class=assertion_failed respawn_probe_waypoints_changed before=%1 after=%2",
            _waypointsBefore, _waypointsAfter];
    };

    // ------------------------------------------------- what the seat did, recorded
    // Watched past the respawn and written down. No assertion: what the engine
    // does with leadership across a player-leader's death is the open question
    // #189 hands back to the human, and a probe that asserted today's answer
    // would be specifying it rather than reporting it.
    private _until = diag_tickTime + 20;
    private _nextAt = 0;
    waitUntil {
        if (diag_tickTime > _nextAt) then {
            _nextAt = diag_tickTime + 5;
            private _seat = leader _group;
            diag_log format ["CTI|respawn_probe_seat t=%1 leader=%2 alive=%3 is_player=%4 group_local=%5 units=%6",
                round (diag_tickTime - _diedAt), name _seat, alive _seat, isPlayer _seat,
                local _group, count units _group];
        };
        diag_tickTime > _until
    };
    private _seat = leader _group;
    diag_log format ["CTI|respawn_probe_succession squad=%1 leader=%2 is_him=%3 is_player=%4 in_his_squad=%5 group_local=%6 units=%7 order=%8 waypoints=%9",
        _squadId, name _seat, _seat isEqualTo _new, isPlayer _seat,
        (group _new) isEqualTo _group, local _group, count units _group,
        _orderAfter # 0, count _waypointsAfter];
    diag_log "CTI|LEG name=respawn_succession status=ran";

    diag_log "CTI|respawn_probe_done";
};
