// probe: respawn-base
// issues: 189
// window: 540
// env: CTI_WINDOWS_CLIENT=1 CTI_PROBE_CLIENT=240
//
// #189 in-world probe: ADR-0052's rulings 1, 6 and the reclaim half of 4, which
// are one event seen end to end. A real person leading a Squad is killed in the
// field; the engine hands the Squad to an AI and it goes on doing what it was
// told; he comes back at his own Base after the configured timer and nowhere
// else; and he is a rifleman in his own Squad until he walks back to it, at
// which point the server gives it to him again.
//
// A headless client cannot stand in for him. It holds no player unit, so there
// is nothing to kill and nothing to respawn — the same reason `client-port` and
// `reinforce` give. So this declares its headed client in its own `env:` header
// and reports every leg `unverified` when the run did not send one, rather than
// passing on a world where the subject was never present (#116).
//
// ## What is staged and what is bet on
//
// Staged: the Squad, the person's place in it, where they are standing, and the
// death. Bet on: only decisions this repository's code owns — that the timer is
// the configured one, that the respawn lands inside the Base, that the standing
// Order survives the interregnum untouched, that leadership does *not* come back
// while he is at Base, and that it does once he is with his men. Nothing here
// waits on a firefight or on AI pathing, which is #38's rule.
//
// The Squad is teleported to the Place it is ordered to defend rather than
// marched there. Two reasons, and the second is the one that matters: a march is
// world-owned timing, and — more sharply — `cti_fnc_orderEnforce` re-asserts a
// standing Order when the Squad has run out of waypoints *and* drifted off the
// ground it was sent to, which rewrites the waypoints this probe is asserting
// are unchanged. Ordering them to defend the ground they are standing on leaves
// them un-adrift for the whole window, so the only thing that could touch those
// waypoints is the death, which is the subject.
//
// The ground is chosen as the Objective furthest from that side's own Base, off
// the manifest, so the arrangement does not care which Commander slot the client
// landed in: for WEST that is 2.9 km and for EAST 5.2 km, and either is far
// enough that respawning at Base is unambiguously *not* being with the Squad.
//
// ## The number is read back, never copied
//
// The delay is read from the mission config the engine itself is reading
// (`missionConfigFile >> "respawnDelay"`, which is description.ext), so this
// probe holds no second copy of 30 to drift from the one that is set. It is a
// playtest-tuned placeholder and a playtest may move it; the assertion is
// "not before the configured delay", which survives the move.
//
// The reclaim distance is not read back — it is a default inside
// `cti_fnc_leaderReclaim` with no reading command to ask. So this probe never
// stands the person at the boundary: it puts him well inside (a few metres) and
// well outside (kilometres), which are the two answers any sane value of that
// placeholder agrees on. Betting on the boundary would be betting on a number
// the probe would then have to copy.
//
// ## Window
//
// 540 s, and every second of it is somebody's arithmetic:
//   240  the client's cold start on the Windows host, as `client-port` measured
//        it and `env:` above declares it
//    20  the world built and both server loops turned once (worldReady)
//    60  a Squad bought through the port and spawned into the world
//    30  the Order issued through the port, crossing the outbox, landing
//    30  the Squad staged on that ground, the person joined to it and leading
//    75  the death, plus the 30 s respawn timer, plus the new unit appearing
//    20  the far-window watch — four turns of the 5 s reclaim sweep, spent
//        proving that nothing happens
//    45  the staged rejoin, one reclaim sweep, the group's locality moving back
//        to his machine, and the settle
//    20  slack
// The 30 s in there is the subject and cannot be shortened; the 240 dominates
// and is the client's, not this probe's. Nothing here was raised to make a
// flaky assertion pass.
[] spawn {
    private _extension = call cti_fnc_shimName;
    if (_extension isEqualTo "") exitWith {
        diag_log "CTI|FAIL class=infra_unavailable respawn_probe_no_shim";
        diag_log "CTI|respawn_probe_done";
    };

    private _legs = ["respawn_timer", "respawn_interregnum", "respawn_reclaim"];
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
    // The Objective furthest from his own Base, so respawning at Base is
    // unambiguously away from his Squad whichever side the client landed in.
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
    private _farAt = [_farEast, _farNorth, 0];
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
    // not state is not one to build a red on — the failure would read as "the
    // Order changed" when it meant "the engine compares by reference".
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
    // never finds them adrift and never rewrites the waypoints below.
    {
        _x setPosATL [_farEast + (_forEachIndex * 4), _farNorth, 0];
    } forEach units _group;

    // ------------------------------------------------------- the person leads it
    // `joinSilent` is global in argument and effect; `selectLeader` takes a local
    // group, and the Squad is the server's until this line, which is what makes
    // it legal here (topics/Multiplayer_Scripting.wiki:219). It stops being the
    // server's by this line, which is the locality the reclaim later depends on
    // coming back.
    [_unit] joinSilent _group;
    _unit setPosATL [_farEast - 6, _farNorth, 0];
    _group selectLeader _unit;

    private _by = diag_tickTime + 30;
    waitUntil { leader _group isEqualTo _unit || { diag_tickTime > _by } };
    if (leader _group isNotEqualTo _unit) exitWith {
        diag_log format ["CTI|FAIL class=timeout respawn_probe_leadership_never_passed squad=%1", _squadId];
        ["the_person_never_led_the_squad"] call _lost;
    };

    // What has to be true when he dies, recorded while it still is. The waypoint
    // list rather than `currentWaypoint`: the engine advances the second as the
    // Squad works, and it is the Order's ground that must not move.
    private _waypointsOf = {
        (waypoints _this) apply { [waypointPosition _x, waypointType _x] }
    };
    private _orderBefore = _group call _orderOf;
    private _waypointsBefore = _group call _waypointsOf;
    diag_log format ["CTI|respawn_probe_before squad=%1 order=%2 place=%3 waypoints=%4 leader=%5 local=%6 at=%7",
        _squadId, _orderBefore # 0, _orderBefore # 1,
        count _waypointsBefore, name _unit, local _group, mapGridPosition _unit];

    // -------------------------------------------------------------- the death
    private _diedAt = diag_tickTime;
    _unit setDamage 1;

    private _by = diag_tickTime + 20;
    waitUntil { !alive _unit || { diag_tickTime > _by } };
    if (alive _unit) exitWith {
        diag_log "CTI|FAIL class=timeout respawn_probe_the_person_would_not_die";
        ["the_staged_death_never_took_effect"] call _lost;
    };

    // ------------------------------------------------- the Squad without him
    // The engine promotes; ADR-0052 ruling 4 relies on it rather than building
    // it, so this reads it rather than asserting it into being. What is asserted
    // is what the ruling promises: an AI is leading, and the Order it was given
    // is untouched.
    private _by = diag_tickTime + 20;
    waitUntil {
        (leader _group isNotEqualTo _unit && { alive leader _group }) || { diag_tickTime > _by }
    };
    private _standIn = leader _group;
    if (_standIn isEqualTo _unit || { !alive _standIn }) then {
        diag_log format ["CTI|FAIL class=assertion_failed respawn_probe_no_successor leader=%1 alive=%2",
            name _standIn, alive _standIn];
    };
    if (isPlayer _standIn) then {
        diag_log format ["CTI|FAIL class=assertion_failed respawn_probe_successor_is_not_ai leader=%1",
            name _standIn];
    };

    private _orderDuring = _group call _orderOf;
    if !(_orderDuring isEqualTo _orderBefore) then {
        diag_log format ["CTI|FAIL class=assertion_failed respawn_probe_order_changed_on_death before=%1 after=%2",
            _orderBefore, _orderDuring];
    };
    private _waypointsDuring = _group call _waypointsOf;
    if !(_waypointsDuring isEqualTo _waypointsBefore) then {
        diag_log format ["CTI|FAIL class=assertion_failed respawn_probe_waypoints_changed_on_death before=%1 after=%2",
            _waypointsBefore, _waypointsDuring];
    };
    diag_log format ["CTI|respawn_probe_interregnum squad=%1 leader=%2 is_ai=%3 order=%4 waypoints=%5 local=%6",
        _squadId, name _standIn, !isPlayer _standIn,
        _orderDuring # 0, count _waypointsDuring, local _group];
    diag_log "CTI|LEG name=respawn_interregnum status=ran";

    // ------------------------------------------------------------- coming back
    // `allPlayers` holds dead players too (ADR-0052 reads the same line), so the
    // new unit is the live one wearing his UID — never merely "not the old one".
    private _him = {
        private _found = objNull;
        { if (alive _x && { getPlayerUID _x isEqualTo _this }) exitWith { _found = _x } } forEach allPlayers;
        _found
    };

    private _by = _diedAt + _delay + 45;
    private _new = objNull;
    waitUntil {
        _new = _uid call _him;
        !isNull _new || { diag_tickTime > _by }
    };
    if (isNull _new) exitWith {
        diag_log format ["CTI|FAIL class=timeout respawn_probe_never_came_back uid=%1 waited=%2 delay=%3",
            _uid, round (diag_tickTime - _diedAt), _delay];
        diag_log "CTI|LEG name=respawn_timer status=unverified reason=the_person_never_respawned";
        diag_log "CTI|LEG name=respawn_reclaim status=unverified reason=the_person_never_respawned";
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
    diag_log format ["CTI|respawn_probe_timer took=%1 delay=%2 base=%3 away=%4 radius=%5 grid=%6",
        round _took, _delay, _base get "id", round _cameBackAt, _baseRadius, mapGridPosition _new];
    diag_log "CTI|LEG name=respawn_timer status=ran";

    // ------------------------------------------- a rifleman until he walks back
    // The ordering ruling 4 turns on, and the reason it says "on rejoining"
    // rather than "on respawn": at Base he is kilometres from his men, and
    // handing him the Squad there would pull it off the Order it is still
    // holding. Watched for four turns of the 5 s sweep rather than sampled once
    // at the end (#46), so this is a claim about every moment in the window.
    private _away = _new distance2D (leader _group);
    private _snatched = objNull;
    private _by = diag_tickTime + 20;
    waitUntil {
        if (leader _group isEqualTo _new) then { _snatched = _new };
        !isNull _snatched || { diag_tickTime > _by }
    };
    if (!isNull _snatched) then {
        diag_log format ["CTI|FAIL class=assertion_failed respawn_probe_reclaimed_from_base squad=%1 away=%2",
            _squadId, round _away];
    };
    diag_log format ["CTI|respawn_probe_apart squad=%1 away=%2 leader=%3 is_ai=%4 in_his_squad=%5",
        _squadId, round _away, name leader _group, !isPlayer leader _group,
        (group _new) isEqualTo _group];

    // ----------------------------------------------------------- and rejoining
    // Group membership across respawn is the engine's business and this probe
    // does not bet on it either way: whichever way the world does it, the state
    // ruling 4 describes is a live player standing in his own Squad, and that is
    // staged here and asserted to have taken effect before anything is expected
    // of it.
    private _kept = (group _new) isEqualTo _group;
    if (!_kept) then {
        [_new] joinSilent _group;
    };
    private _standAt = leader _group;
    _new setPosATL [(getPosATL _standAt) # 0, ((getPosATL _standAt) # 1) - 5, 0];

    private _by = diag_tickTime + 15;
    waitUntil {
        ((group _new) isEqualTo _group && { _new distance2D (leader _group) < 20 })
            || { diag_tickTime > _by }
    };
    if !((group _new) isEqualTo _group) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed respawn_probe_rejoin_not_staged squad=%1 kept=%2",
            _squadId, _kept];
        diag_log "CTI|LEG name=respawn_reclaim status=unverified reason=the_staged_rejoin_never_took_effect";
        diag_log "CTI|respawn_probe_done";
    };
    private _closed = _new distance2D (leader _group);
    if (_closed >= 20) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed respawn_probe_rejoin_not_close squad=%1 away=%2",
            _squadId, round _closed];
        diag_log "CTI|LEG name=respawn_reclaim status=unverified reason=the_staged_rejoin_left_him_apart";
        diag_log "CTI|respawn_probe_done";
    };
    diag_log format ["CTI|respawn_probe_rejoined squad=%1 kept_membership=%2 away=%3 local=%4",
        _squadId, _kept, round _closed, local _group];

    // The decision the addon owns: within reclaim distance, standing in his own
    // Squad, alive — the sweep hands it back. One turn of the 5 s loop, plus the
    // group's locality moving to his machine.
    private _by = diag_tickTime + 40;
    waitUntil { leader _group isEqualTo _new || { diag_tickTime > _by } };
    if (leader _group isNotEqualTo _new) then {
        diag_log format ["CTI|FAIL class=assertion_failed respawn_probe_never_reclaimed squad=%1 leader=%2 away=%3 local=%4",
            _squadId, name leader _group, round (_new distance2D (leader _group)), local _group];
    };

    // And the Order he comes back to is still the one he left.
    private _orderAfter = _group call _orderOf;
    if !(_orderAfter isEqualTo _orderBefore) then {
        diag_log format ["CTI|FAIL class=assertion_failed respawn_probe_order_changed_on_reclaim before=%1 after=%2",
            _orderBefore, _orderAfter];
    };

    diag_log format ["CTI|respawn_probe_reclaim squad=%1 leader=%2 is_him=%3 order=%4 waypoints=%5",
        _squadId, name leader _group, leader _group isEqualTo _new,
        _orderAfter # 0, count (_group call _waypointsOf)];
    diag_log "CTI|LEG name=respawn_reclaim status=ran";

    diag_log "CTI|respawn_probe_done";
};
