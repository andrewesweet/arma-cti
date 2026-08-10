// probe: order-waypoint
// issues: 312, 14
// window: 240
//
// #312 in-world probe: an Order makes its own waypoint the group's *current*
// one, for all four Orders.
//
// `just regress order-waypoint`, or by hand
// `just probe spike/probes/order-waypoint.sqf 240`.
//
// ## The claim, and why it is worth a probe of its own
//
// `cti_fnc_orderApply` deletes the group's waypoints, lays new ones, and ends by
// making the first of them current. That last step is `setCurrentWaypoint`,
// which is `arg= local` (commands/setCurrentWaypoint.wiki), and ADR-0070 found
// before the squad-leader slot was built that a group leaves the server the
// moment a player leads it and does not come back (#189). So from #312 onwards
// the call has to be made where the group is, and the shape of the bug it
// guards against is a Squad whose Order records correctly (`cti_order`),
// displays correctly (`BIS_fnc_taskCreate`) and never becomes what the group is
// doing. Both of those are already asserted elsewhere — `base-assault` and
// `recall` read `cti_order` — and neither would move.
//
// So this asserts the third thing, which nothing did: `currentWaypoint _group`
// is a valid index into `waypoints _group`, and the waypoint at it is standing
// on the ground the Order named. A valid index is half the claim on its own —
// "if all waypoints are completed, then the index is 1 greater than the last
// valid index" (commands/currentWaypoint.wiki) is exactly the state a dropped
// `setCurrentWaypoint` leaves behind.
//
// **What this probe is not.** The corpus has no player, so every group here is
// the server's and the locality branch under test is the one that was always
// taken. What it pins is that the refactor did not break the path every Squad
// uses, and it is the assertion the player-led case will be judged by; the
// headed-client half is #313's, whose gate is different in kind.
//
// ## The window
//
// 20 s of runway (`cti_probe_fnc_worldReady`'s own deadline), up to 60 s for the
// Purchase to cross the outbox and stand the Squad up, and four Orders each
// crossing the outbox on the pump's 2 s poll with a 30 s deadline apiece. That
// is about 200 s of subject; 240 is that plus one report interval either side.
// If it ever wants more, the answer is that an Order is not arriving, and that
// is the bug.
//
// Nothing here waits on the Squad *reaching* anywhere: an Order becoming current
// is a decision `cti_fnc_orderApply` owns, and where the men get to afterwards
// is the world's (#38).
[] spawn {
    ["order_waypoint", ["capture", "defend", "assault", "reserve"]]
        call cti_probe_fnc_legsOwed;

    private _extension = call cti_fnc_shimName;
    if (_extension isEqualTo "") exitWith {
        diag_log "CTI|FAIL class=infra_unavailable order_waypoint_probe_no_shim";
        ["no_shim"] call cti_probe_fnc_done;
    };

    [20] call cti_probe_fnc_worldReady;

    // The ground each Order names, off the index cti_fnc_worldInit derives
    // beside the map (#109). An Objective for Capture and Defend, the enemy Base
    // for Assault; Reserve names none and falls back on the Squad's own Base,
    // which is why it is checked against that rather than against a place the
    // Order carried.
    private _town = ["agia_marina"] call cti_probe_fnc_placeNamed;
    private _enemy = ["csat_kamino"] call cti_probe_fnc_placeNamed;
    private _home = ["nato_airbase"] call cti_probe_fnc_placeNamed;
    if (count _town isEqualTo 0 || { count _enemy isEqualTo 0 } || { count _home isEqualTo 0 }) exitWith {
        diag_log "CTI|FAIL class=assertion_failed order_waypoint_probe_no_places";
        ["the_manifest_named_no_ground"] call cti_probe_fnc_done;
    };

    ["order-waypoint-buy"] call cti_probe_fnc_buySquad;

    // Judged on the call, carried out through the outbox: wait for the world to
    // hold the Squad rather than assuming the pump has run.
    private _deadline = diag_tickTime + 60;
    waitUntil {
        count (["WEST"] call cti_probe_fnc_squadsOf) > 0 || { diag_tickTime > _deadline }
    };
    private _squads = ["WEST"] call cti_probe_fnc_squadsOf;
    if (count _squads isEqualTo 0) exitWith {
        diag_log "CTI|FAIL class=timeout order_waypoint_probe_no_squad";
        ["the_squad_never_arrived"] call cti_probe_fnc_done;
    };
    private _squadId = (keys _squads) # 0;
    private _group = _squads get _squadId;
    diag_log format ["CTI|order_waypoint_probe_squad squad=%1 units=%2 local=%3",
        _squadId, count units _group, local _group];

    // One Order, and the three questions asked of the group afterwards. The
    // Order goes through the port because that is the only order path there is
    // (ADR-0012), and the wait is for `cti_order` to change — which is what says
    // the effect has been applied, and is the same signal `base-assault` waits
    // on.
    private _measure = {
        params ["_kind", "_place", "_ground"];

        private _reply = [createHashMapFromArray [
            // Unique per call, which ADR-0034 needs: each Order kind is issued
            // once, so its own name is the id.
            ["id", format ["order-waypoint-order-%1", _kind]],
            ["verb", "command"],
            ["payload", createHashMapFromArray [
                ["command", "order"],
                ["side", "WEST"],
                // Stamped by the probe because there is no gateway on this path
                // (ADR-0044): an unstamped line is refused `unknown_caller`.
                ["acting_side", "WEST"],
                ["args", createHashMapFromArray [
                    ["squad", _squadId], ["order", _kind], ["place", _place]
                ]]
            ]]
        ]] call cti_probe_fnc_rpc;
        if ((_reply getOrDefault ["status", ""]) isNotEqualTo "ok") exitWith {
            diag_log format ["CTI|FAIL class=assertion_failed order_waypoint_probe_refused order=%1 place=%2 reply=%3",
                _kind, _place, _reply];
            false
        };

        private _by = diag_tickTime + 30;
        waitUntil {
            ((_group getVariable ["cti_order", createHashMap]) getOrDefault ["order", ""])
                isEqualTo _kind
                || { diag_tickTime > _by }
        };
        private _standing = _group getVariable ["cti_order", createHashMap];
        if ((_standing getOrDefault ["order", ""]) isNotEqualTo _kind) exitWith {
            diag_log format ["CTI|FAIL class=timeout order_waypoint_probe_never_landed order=%1 standing=%2",
                _kind, _standing];
            false
        };

        private _laid = count waypoints _group;
        private _current = currentWaypoint _group;
        // The claim. A group with its waypoints replaced and nothing made
        // current reads as "all waypoints completed" — an index one past the
        // last valid one (commands/currentWaypoint.wiki) — which is precisely
        // what an Order that recorded and displayed but never took effect looks
        // like from here.
        if (_laid isEqualTo 0 || { _current < 0 } || { _current >= _laid }) exitWith {
            diag_log format ["CTI|FAIL class=assertion_failed order_waypoint_probe_not_current order=%1 current=%2 laid=%3 local=%4",
                _kind, _current, _laid, local _group];
            false
        };

        // And it is standing on the ground the Order named, rather than merely
        // being some waypoint. `distance2D` because the waypoint was laid with a
        // negative radius, which the engine reads as PositionASL
        // (commands/addWaypoint.wiki) while `waypointPosition` answers
        // PositionAGL — the two disagree by the terrain's height and agree
        // about the map.
        private _at = waypointPosition [_group, _current];
        private _wanted = _ground getOrDefault ["position", []];
        private _off = _at distance2D [_wanted # 0, _wanted # 1, 0];
        diag_log format ["CTI|order_waypoint_probe_measured order=%1 place=%2 current=%3 laid=%4 off=%5",
            _kind, _place, _current, _laid, round _off];
        // Ten metres of tolerance for the engine's own placement, and no more:
        // the Places on this map are kilometres apart, so this cannot pass by
        // finding the wrong one.
        if (_off > 10) exitWith {
            diag_log format ["CTI|FAIL class=assertion_failed order_waypoint_probe_wrong_ground order=%1 place=%2 off=%3",
                _kind, _place, round _off];
            false
        };

        [_kind] call cti_probe_fnc_legRan;
        true
    };

    // Assault is measured against the HQ structure rather than the Base's own
    // position, because that is where cti_fnc_orderApply aims it — the building
    // Decapitation destroys, whose position is authored data.
    private _hq = missionNamespace getVariable [_enemy getOrDefault ["hq", ""], objNull];
    if (isNull _hq) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed order_waypoint_probe_no_hq name=%1",
            _enemy getOrDefault ["hq", ""]];
        ["the_enemy_base_has_no_hq"] call cti_probe_fnc_done;
    };
    private _hqAt = getPosATL _hq;
    private _atHq = createHashMapFromArray [["position", [_hqAt # 0, _hqAt # 1]]];

    // In this order deliberately: Reserve last, because it is the Order the
    // Squad was already carrying when it spawned, and asking for it first would
    // be asking whether nothing changed.
    {
        _x params ["_kind", "_place", "_ground"];
        if !([_kind, _place, _ground] call _measure) exitWith {
            diag_log format ["CTI|order_waypoint_probe_stopped_at order=%1", _kind];
        };
    } forEach [
        ["capture", "agia_marina", _town],
        ["defend", "agia_marina", _town],
        ["assault", "csat_kamino", _atHq],
        ["reserve", "", _home]
    ];

    [] call cti_probe_fnc_done;
};
