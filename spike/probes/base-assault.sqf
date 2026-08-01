// probe: base-assault
// issues: 33
// window: 480
//
// #33 in-world probe: the world acts on Assault(enemy Base) and Defend(own Base).
//
// `just regress base-assault`, or by hand `just probe spike/probes/base-assault.sqf 480`.
//
// The window is the subject's own length, added up rather than guessed at:
// ~40 s for the world to settle and the Purchase to arrive through the outbox,
// ~150 s for a Squad on foot to cover the 250 m approach at the tactical pace an
// AWARE waypoint moves at, 90 s of demolition once it is standing at the HQ
// (cti_fnc_baseAssault's durability placeholder), and a report interval or two
// on either side. That is about 330 s of subject; the rest is the engine's
// pathfinding around an airfield, which is the part nobody can predict to the
// second. If this probe ever needs *more* than 480 s the answer is not a bigger
// number: it is that the Squad is not arriving, and that is the bug.
//
// What is deliberately not in the window is the march from WEST's own Base.
// That is 4.4 km — forty minutes of engine walking speed — and it is the same
// walking `spike/probes/ai-commander.sqf` already declines to wait out. So the
// Squad is put on its approach at a position taken from the manifest's authored
// data: on the line between the EAST Base's HQ and the Objective the manifest
// says is adjacent to it, 250 m out. Authored ground, not a bearing off
// somebody's facing — #28's lesson, which cost two probes.
//
// Three claims, none of which a unit test can make:
//   1. An Assault ordered through the port sends the Squad at the enemy HQ and
//      the HQ ends destroyed. The daemon's half — the port accepting the Order,
//      the roster keeping it — is unit-tested; that a building falls is not.
//   2. The Assault outlives the leader carrying it. The leader is killed once
//      the Squad is demonstrably working on the HQ, and the HQ still falls.
//   3. Defend(own Base) garrisons the Base. Before #33 this Order found no
//      ground at all: an Order naming a Base was looked up in the Objectives
//      alone and logged `order_without_ground`, so the standing Order below is
//      exactly what was missing.
[] spawn {
    private _extension = call cti_fnc_shimName;
    if (_extension isEqualTo "") exitWith {
        diag_log "CTI|FAIL class=infra_unavailable assault_probe_no_shim";
    };

    private _rpc = {
        params ["_envelope"];
        private _raw = ((call cti_fnc_shimName) callExtension ["rpc_keepalive", [toJSON _envelope]]) # 0;
        fromJSON _raw
    };

    private _map = missionNamespace getVariable ["cti_map", createHashMap];
    private _placeNamed = {
        params ["_id"];
        private _found = createHashMap;
        {
            if ((_x getOrDefault ["id", ""]) isEqualTo _id) exitWith { _found = _x };
        } forEach ((_map getOrDefault ["objectives", []]) + (_map getOrDefault ["bases", []]));
        _found
    };

    private _target = ["csat_kamino"] call _placeNamed;
    private _home = ["nato_airbase"] call _placeNamed;
    if (count _target isEqualTo 0 || { count _home isEqualTo 0 }) exitWith {
        diag_log "CTI|FAIL class=assertion_failed assault_probe_no_bases";
    };
    private _hq = missionNamespace getVariable [_target getOrDefault ["hq", ""], objNull];
    if (isNull _hq) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed assault_probe_no_hq name=%1",
            _target getOrDefault ["hq", ""]];
    };

    // Let the world finish building and the report loop get a cycle in.
    private _next = diag_tickTime + 20;
    waitUntil { diag_tickTime >= _next };

    // Two Squads: one to assault the enemy Base, one to defend its own.
    private _wanted = 2;
    for "_i" from 1 to _wanted do {
        [createHashMapFromArray [
            ["id", format ["assault-probe-buy-%1", _i]],
            ["verb", "command"],
            ["payload", createHashMapFromArray [
                ["command", "purchase"],
                ["side", "WEST"],
                ["args", createHashMapFromArray [["squad_type", "rifle"]]]
            ]]
        ]] call _rpc;
    };

    // Judged on the call, carried out through the outbox: wait for the world to
    // hold them rather than assuming the pump has run.
    private _deadline = diag_tickTime + 60;
    waitUntil {
        count (missionNamespace getVariable ["cti_squads", createHashMap]) >= _wanted
            || { diag_tickTime > _deadline }
    };
    private _squads = missionNamespace getVariable ["cti_squads", createHashMap];
    if (count _squads < _wanted) exitWith {
        diag_log format ["CTI|FAIL class=timeout assault_probe_no_squads bought=%1 held=%2",
            _wanted, count _squads];
    };
    private _ids = keys _squads;
    private _attackerId = _ids # 0;
    private _garrisonId = _ids # 1;
    private _attacker = _squads get _attackerId;
    private _garrison = _squads get _garrisonId;

    // The approach, from authored data alone: the line from the enemy Base's HQ
    // to the Objective the manifest calls adjacent to that Base, 250 m out.
    private _adjacent = [(_target getOrDefault ["adjacent", [""]]) # 0] call _placeNamed;
    if (count _adjacent isEqualTo 0) exitWith {
        diag_log "CTI|FAIL class=assertion_failed assault_probe_no_adjacent_place";
    };
    private _hqAt = getPosATL _hq;
    (_adjacent get "position") params ["_fromEast", "_fromNorth"];
    private _runEast = _fromEast - (_hqAt # 0);
    private _runNorth = _fromNorth - (_hqAt # 1);
    private _span = sqrt ((_runEast * _runEast) + (_runNorth * _runNorth));
    private _approach = [
        (_hqAt # 0) + (_runEast / _span * 250),
        (_hqAt # 1) + (_runNorth / _span * 250),
        0
    ];
    {
        _x setPosATL [(_approach # 0) + (_forEachIndex * 4), _approach # 1, 0];
    } forEach units _attacker;
    diag_log format ["CTI|assault_probe_staged squad=%1 at=%2 from=%3 range=%4",
        _attackerId, mapGridPosition _approach, _adjacent get "id",
        (leader _attacker) distance2D _hqAt];

    // Both Orders through the port, which is the only order path there is
    // (ADR-0012): what is under test is an Order a Commander could issue.
    {
        _x params ["_squadId", "_order", "_place"];
        private _reply = [createHashMapFromArray [
            ["id", format ["assault-probe-order-%1", _squadId]],
            ["verb", "command"],
            ["payload", createHashMapFromArray [
                ["command", "order"],
                ["side", "WEST"],
                ["args", createHashMapFromArray [
                    ["squad", _squadId], ["order", _order], ["place", _place]
                ]]
            ]]
        ]] call _rpc;
        if ((_reply getOrDefault ["status", ""]) isNotEqualTo "ok") then {
            diag_log format ["CTI|FAIL class=assertion_failed assault_probe_order_refused squad=%1 order=%2 place=%3 reply=%4",
                _squadId, _order, _place, _reply];
        };
    } forEach [
        [_attackerId, "assault", "csat_kamino"],
        [_garrisonId, "defend", "nato_airbase"]
    ];

    // Each effect crosses the outbox on the pump's own turn, so the world holds
    // an Order some moments after the port accepted it — and the two Orders do
    // not land together. Waited on as a pair, because a first cut waited only
    // for the Assault and then read the garrison's Order in the same breath:
    // it passed three runs and caught the fourth still saying `reserve`.
    _deadline = diag_tickTime + 60;
    private _landed = {
        params ["_group", "_kind"];
        ((_group getVariable ["cti_order", createHashMap]) getOrDefault ["order", ""])
            isEqualTo _kind
    };
    waitUntil {
        ([_attacker, "assault"] call _landed && { [_garrison, "defend"] call _landed })
            || { diag_tickTime > _deadline }
    };
    if !([_garrison, "defend"] call _landed) exitWith {
        diag_log format ["CTI|FAIL class=timeout assault_probe_defend_never_landed standing=%1",
            _garrison getVariable ["cti_order", createHashMap]];
    };
    private _standing = _attacker getVariable ["cti_order", createHashMap];
    if ((_standing getOrDefault ["order", ""]) isNotEqualTo "assault") exitWith {
        diag_log format ["CTI|FAIL class=timeout assault_probe_order_never_landed standing=%1",
            _standing];
    };
    if ((_standing getOrDefault ["place", ""]) isNotEqualTo "csat_kamino") exitWith {
        // An Order that found no ground never records one, which is exactly the
        // `order_without_ground` #32 left behind.
        diag_log format ["CTI|FAIL class=assertion_failed assault_probe_assault_without_place standing=%1",
            _standing];
    };
    diag_log format ["CTI|assault_probe_ordered squad=%1 place=%2 waypoints=%3 range=%4",
        _attackerId, _standing get "place", count waypoints _attacker,
        (leader _attacker) distance2D _hqAt];

    // Defend(own Base): the same lookup, on the other side of the map and the
    // other side of the refusal matrix.
    private _garrisonOrder = _garrison getVariable ["cti_order", createHashMap];
    if ((_garrisonOrder getOrDefault ["place", ""]) isNotEqualTo "nato_airbase") then {
        diag_log format ["CTI|FAIL class=assertion_failed assault_probe_defend_without_place standing=%1",
            _garrisonOrder];
    } else {
        diag_log format ["CTI|assault_probe_garrisoned squad=%1 place=%2 waypoints=%3 at=%4",
            _garrisonId, _garrisonOrder get "place", count waypoints _garrison,
            [getPosATL leader _garrison, _map get "objectives", _map get "bases"]
                call cti_fnc_placeOf];
    };

    // The Squad closes and starts work. Waited on as damage rather than as
    // arrival: standing next to a building it is not working on would pass an
    // arrival check and is not an Assault.
    _deadline = diag_tickTime + 240;
    waitUntil { damage _hq > 0 || { diag_tickTime > _deadline } };
    if (damage _hq isEqualTo 0) exitWith {
        diag_log format ["CTI|FAIL class=timeout assault_probe_never_pressed range=%1 alive=%2 waypoint=%3",
            (leader _attacker) distance2D _hqAt, { alive _x } count units _attacker,
            currentWaypoint _attacker];
    };
    diag_log format ["CTI|assault_probe_pressing damage=%1 range=%2 men=%3",
        damage _hq, (leader _attacker) distance2D _hqAt, { alive _x } count units _attacker];

    // An Order survives its leader (#14, CONTEXT.md). Killed here rather than
    // asserted in the abstract: the engine promotes a replacement, the roster
    // still holds the Order, and the building still has to fall. Cheap, because
    // it costs the probe nothing it was not already waiting for.
    private _wasLeader = leader _attacker;
    _wasLeader setDamage 1;
    diag_log format ["CTI|assault_probe_leader_killed was=%1 damage=%2", name _wasLeader, damage _hq];

    _deadline = diag_tickTime + 180;
    waitUntil {
        ((missionNamespace getVariable ["cti_hqDown", createHashMap]) getOrDefault
            ["csat_kamino", createHashMap]) isNotEqualTo createHashMap
            || { diag_tickTime > _deadline }
    };

    private _fell = (missionNamespace getVariable ["cti_hqDown", createHashMap])
        getOrDefault ["csat_kamino", createHashMap];
    if (count _fell isEqualTo 0) exitWith {
        diag_log format ["CTI|FAIL class=timeout assault_probe_hq_survived damage=%1 range=%2 men=%3",
            damage _hq, (leader _attacker) distance2D _hqAt,
            { alive _x } count units _attacker];
    };
    if ((_fell getOrDefault ["by", ""]) isNotEqualTo "WEST") then {
        // Attribution is half of what the win-condition ticket reads: an HQ that
        // fell to nobody in particular cannot settle a mutual Decapitation.
        diag_log format ["CTI|FAIL class=assertion_failed assault_probe_hq_unattributed fell=%1", _fell];
    };
    if (_wasLeader isEqualTo (leader _attacker) && { count units _attacker > 0 }) then {
        diag_log "CTI|FAIL class=assertion_failed assault_probe_leader_never_replaced";
    };
    private _after = _attacker getVariable ["cti_order", createHashMap];
    if ((_after getOrDefault ["order", ""]) isNotEqualTo "assault") then {
        diag_log format ["CTI|FAIL class=assertion_failed assault_probe_order_lost_with_leader standing=%1",
            _after];
    };

    diag_log format ["CTI|assault_probe_decapitated base=csat_kamino by=%1 damage=%2 alive=%3 leader=%4 order=%5",
        _fell getOrDefault ["by", ""], damage _hq, { alive _x } count units _attacker,
        name leader _attacker, _after getOrDefault ["order", ""]];

    // The other half of the criterion: the daemon writes one row from this. Sent
    // here rather than waited for, because the report loop's next turn may fall
    // on the far side of the probe's last line — the first run of this probe
    // destroyed the HQ and ended four seconds before the world would have said
    // so, leaving the run's telemetry silent about the thing it had proved. The
    // daemon keeps the row to one per Base, so the loop repeating this after us
    // is exactly the case that must not write a second.
    private _sample = call cti_fnc_hqSample;
    private _told = [createHashMapFromArray [
        ["id", "assault-probe-observe"],
        ["verb", "observe"],
        ["payload", createHashMapFromArray [["time", time], ["hq", _sample]]]
    ]] call _rpc;
    if ((_told getOrDefault ["status", ""]) isNotEqualTo "ok") then {
        diag_log format ["CTI|FAIL class=assertion_failed assault_probe_report_refused hq=%1 reply=%2",
            _sample, _told];
    };
    diag_log format ["CTI|assault_probe_report hq=%1 status=%2",
        _sample, _told getOrDefault ["status", ""]];

    diag_log "CTI|assault_probe_done";
};
