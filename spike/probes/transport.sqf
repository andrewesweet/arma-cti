// probe: transport
// issues: 170
// window: 360
//
// #170 in-world probe: the free ride (ADR-0059). A Squad bought at its own Base
// is issued the ladder's rung for its size without anybody asking, the vehicle
// lands in the group's own pool, a Squad whose vehicle has gone elsewhere is
// issued another and loses the first, and an AI-led Squad under a distant Order
// actually mounts.
//
// **What each leg bets on, because they are not the same kind of claim.** Three
// of the four are decisions this addon owns outright: the grant rule (a Squad at
// its own Base with no vehicle here gets one), the first-match read of the
// authored ladder, and the replacement rule (one per Squad, and the old one
// goes). The fourth — `boarded` — is the engine's, and it is the one sentence
// ADR-0059's Ruling 4 rests on: "Groups will automatically board any transport
// vehicles they own if the next waypoint is far enough away"
// (`topics/Waypoints.wiki`). A red there is that ruling overturned, not a bug in
// this addon, and the ADR says so under "What would overturn this" — the fix
// would be explicit GET IN waypoints in cti_fnc_orderApply. It is asserted here
// rather than left to a playtest because the whole of the ruling's second
// principal — "AI commander on behalf of squad leaders" — is carried by it.
//
// It needs no headed client and declares none. Every principal here is the
// world's own: nobody asks for a transport, which is the ruling's shape (a
// player-led Squad's leader is served by the truck standing at his Base, and
// `local _group` is what the server checks before touching a group it may not
// own — a claim about a client-local group that no server-side probe can make).
//
// **Vacuity is designed out of each leg.** `issued` reads the expected class off
// `cti_fnc_transportCatalogue` rather than writing a classname here, so a probe
// that passed against an empty ladder is impossible — and it asserts the
// vehicle's own back-reference (`cti_transportOf`) names this Squad, which
// cannot come true by a truck happening to be parked at the Base. `replaced`
// asserts the staged move took effect before it waits on anything (#80): the
// first vehicle is read as being away from the Base through the same
// `cti_fnc_placeOf` call the watch uses, and the new one is asserted to be a
// different object. `boarded` asserts nobody is in a vehicle *before* the Order
// goes in.
//
// The window is 360 rather than the default 150 because the subject is that
// long, term by term: 20 s for the world to build, 60 s for a Purchase to cross
// the port, be pumped into the world on a 2 s poll and be swept by a 10 s watch,
// 60 s for the same watch to notice a vehicle that has left and replace it, 150 s
// for an Order to cross the port, be applied as waypoints and for the engine to
// decide to board, and 20 s for the probe's own logging. That is 310 s of
// deadlines. The only irreducible cost is the boarding wait, and it is a
// deadline rather than a settle — the leg ends the moment somebody is aboard.
//
// `just regress transport`, or by hand `just probe spike/probes/transport.sqf 360`.
[] spawn {
    // Every leg this probe owes an answer for. A leg is struck off when it has
    // been measured; anything still standing at an early exit is reported
    // `unverified`, which the harness reads as infra_unavailable (ADR-0037,
    // #116).
    ["transport", ["issued", "pooled", "replaced", "boarded"]] call cti_probe_fnc_legsOwed;

    private _extension = call cti_fnc_shimName;
    if (_extension isEqualTo "") exitWith {
        diag_log "CTI|FAIL class=infra_unavailable transport_probe_no_shim";
        ["the_world_had_no_shim"] call cti_probe_fnc_done;
    };

    [20] call cti_probe_fnc_worldReady;

    // ---------------------------------------------------------- the ladder
    private _fleet = call cti_fnc_transportCatalogue;
    if (_fleet isEqualTo []) exitWith {
        diag_log "CTI|FAIL class=assertion_failed transport_probe_no_catalogue";
        ["the_world_shipped_no_ladder"] call cti_probe_fnc_done;
    };

    private _map = missionNamespace getVariable ["cti_map", createHashMap];
    private _objectives = _map getOrDefault ["objectives", []];
    private _bases = _map getOrDefault ["bases", []];
    private _placeOf = {
        params ["_thing"];
        [getPosATL _thing, _objectives, _bases] call cti_fnc_placeOf
    };
    private _baseId = (["nato_airbase"] call cti_probe_fnc_placeNamed) getOrDefault ["id", ""];
    if (_baseId isEqualTo "") exitWith {
        diag_log "CTI|FAIL class=assertion_failed transport_probe_no_base";
        ["the_map_named_no_west_base"] call cti_probe_fnc_done;
    };

    // ------------------------------------------------------------ the Squad
    private _bought = ["transport-probe-buy", "WEST", "rifle"] call cti_probe_fnc_buySquad;
    if ((_bought getOrDefault ["status", ""]) isNotEqualTo "ok") exitWith {
        // cti_probe_fnc_buySquad has already written the FAIL line.
        ["the_purchase_was_refused"] call cti_probe_fnc_done;
    };

    private _squadId = "";
    private _group = grpNull;
    private _deadline = diag_tickTime + 60;
    waitUntil {
        private _mine = ["WEST"] call cti_probe_fnc_squadsOf;
        {
            if (!isNull _y && { (_y getVariable ["cti_transport", objNull]) isNotEqualTo objNull }) then {
                _squadId = _x;
                _group = _y;
            };
        } forEach _mine;
        !isNull _group || diag_tickTime > _deadline
    };

    if (isNull _group) exitWith {
        diag_log format ["CTI|FAIL class=timeout transport_probe_never_issued waited=%1 squads=%2",
            60, count (["WEST"] call cti_probe_fnc_squadsOf)];
        ["no_squad_was_issued_a_vehicle"] call cti_probe_fnc_done;
    };

    // ------------------------------------------------------------- issued
    private _first = _group getVariable ["cti_transport", objNull];
    private _men = _group getVariable ["cti_squadSize", 0];

    // The rung the ladder says, read off the ladder rather than written here:
    // a classname in this file would pass against a catalogue nobody shipped.
    private _rung = createHashMap;
    { if ((_x getOrDefault ["seats", 0]) >= _men) exitWith { _rung = _x } } forEach _fleet;
    private _wanted = _rung getOrDefault ["vehicle", ""];

    private _at = [_first] call _placeOf;
    private _of = _first getVariable ["cti_transportOf", ""];
    private _faults = [];
    if (!alive _first) then { _faults pushBack "vehicle_not_alive" };
    if (_men <= 0) then { _faults pushBack "squad_size_unrecorded" };
    if (_at isNotEqualTo _baseId) then { _faults pushBack format ["vehicle_at_%1", _at] };
    if (typeOf _first isNotEqualTo _wanted) then {
        _faults pushBack format ["class_%1_not_%2", typeOf _first, _wanted];
    };
    if (_of isNotEqualTo _squadId) then { _faults pushBack format ["owned_by_%1", _of] };

    if (_faults isNotEqualTo []) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed transport_probe_issued_wrong squad=%1 men=%2 rung=%3 class=%4 at=%5 faults=%6",
            _squadId, _men, _rung getOrDefault ["id", "?"], typeOf _first, _at, _faults];
        ["the_vehicle_issued_was_not_the_ladders"] call cti_probe_fnc_done;
    };

    diag_log format ["CTI|transport_probe_issued squad=%1 men=%2 rung=%3 class=%4 at=%5",
        _squadId, _men, _rung getOrDefault ["id", "?"], typeOf _first, _at];
    ["issued"] call cti_probe_fnc_legRan;

    // ------------------------------------------------------------- pooled
    // `assignedVehicles` returns "all vehicles added to the given Group with
    // addVehicle" (commands/assignedVehicles.wiki), which is the pool the engine
    // boards from — so this is the leg that says the truck is the Squad's to use
    // and not merely parked beside it.
    private _pool = assignedVehicles _group;
    if !(_first in _pool) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed transport_probe_not_pooled squad=%1 pool=%2 local=%3",
            _squadId, count _pool, local _group];
        ["the_vehicle_was_not_in_the_groups_pool"] call cti_probe_fnc_done;
    };
    diag_log format ["CTI|transport_probe_pooled squad=%1 pool=%2", _squadId, count _pool];
    ["pooled"] call cti_probe_fnc_legRan;

    // ------------------------------------------------------------ replaced
    // The staged move: the vehicle is put on an Objective, which is the state a
    // Squad that abandoned its truck and marched home arrives in. Staged rather
    // than played out, because what is under test is the watch's rule and not a
    // Squad's ability to drive somewhere and walk back.
    private _elsewhere = ["agia_marina"] call cti_probe_fnc_placeNamed;
    (_elsewhere getOrDefault ["position", [0, 0]]) params ["_east", "_north"];
    _first setPosATL [_east, _north, 0];

    // The staging is asserted to have taken effect before anything is read
    // through it (#80), and through the watch's own reading of where a thing is.
    private _away = [_first] call _placeOf;
    if (_away isEqualTo _baseId) exitWith {
        diag_log format ["CTI|FAIL class=infra_unavailable transport_probe_move_refused squad=%1 at=%2",
            _squadId, _away];
        ["the_staged_move_did_not_take"] call cti_probe_fnc_done;
    };

    private _second = objNull;
    _deadline = diag_tickTime + 60;
    waitUntil {
        _second = _group getVariable ["cti_transport", objNull];
        (_second isNotEqualTo _first && {!isNull _second}) || diag_tickTime > _deadline
    };

    if (_second isEqualTo _first || {isNull _second}) exitWith {
        diag_log format ["CTI|FAIL class=timeout transport_probe_never_replaced squad=%1 away_at=%2 waited=%3",
            _squadId, _away, 60];
        ["the_stranded_vehicle_was_never_replaced"] call cti_probe_fnc_done;
    };

    private _newAt = [_second] call _placeOf;
    // The old one is gone rather than merely superseded: nobody was in it, so
    // cti_fnc_transportIssue deletes it. `isNull` is what a deleted object reads
    // as; a released one would still be alive and is a different sentence.
    private _oldGone = isNull _first || {!alive _first};
    if (_newAt isNotEqualTo _baseId || {!_oldGone}) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed transport_probe_replacement_wrong squad=%1 new_at=%2 old_gone=%3",
            _squadId, _newAt, _oldGone];
        ["the_replacement_was_not_at_the_base_or_the_old_one_stayed"] call cti_probe_fnc_done;
    };
    diag_log format ["CTI|transport_probe_replaced squad=%1 new_at=%2 old_gone=%3 pool=%4",
        _squadId, _newAt, _oldGone, count assignedVehicles _group];
    ["replaced"] call cti_probe_fnc_legRan;

    // ------------------------------------------------------------- boarded
    // Nobody aboard before the Order, so the leg cannot pass on a Squad that was
    // already sitting in it.
    private _aboard = { units _group findIf { vehicle _x isNotEqualTo _x } };
    if (call _aboard > -1) exitWith {
        diag_log format ["CTI|FAIL class=infra_unavailable transport_probe_already_aboard squad=%1", _squadId];
        ["the_squad_was_already_mounted"] call cti_probe_fnc_done;
    };

    // A Capture on the Objective the manifest calls adjacent to the Base — about
    // a kilometre, which is the shortest march this Campaign ever asks for. If
    // the engine will board for anything, it will board for the trip it is least
    // likely to bother with.
    private _reply = [createHashMapFromArray [
        ["id", ["transport-probe-order", _squadId] call cti_fnc_requestId],
        ["verb", "command"],
        ["payload", createHashMapFromArray [
            ["command", "order"],
            ["side", "WEST"],
            // Stamped by the probe because there is no gateway on this path
            // (ADR-0044): an unstamped line is refused `unknown_caller`.
            ["acting_side", "WEST"],
            ["args", createHashMapFromArray [
                ["squad", _squadId], ["order", "capture"], ["place", "agia_marina"]
            ]]
        ]]
    ]] call cti_probe_fnc_rpc;
    if ((_reply getOrDefault ["status", ""]) isNotEqualTo "ok") exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed transport_probe_order_refused squad=%1 reply=%2",
            _squadId, _reply];
        ["the_order_was_refused"] call cti_probe_fnc_done;
    };

    private _mounted = -1;
    _deadline = diag_tickTime + 150;
    waitUntil {
        _mounted = call _aboard;
        _mounted > -1 || diag_tickTime > _deadline
    };

    if (_mounted < 0) exitWith {
        // ADR-0059 Ruling 4 overturned rather than a defect here: the group owns
        // the vehicle (`pooled` passed) and has a waypoint a kilometre away, and
        // the engine did not use it.
        diag_log format ["CTI|FAIL class=assertion_failed transport_probe_never_boarded squad=%1 pool=%2 waypoints=%3 waited=%4",
            _squadId, count assignedVehicles _group, count waypoints _group, 150];
        ["the_ai_squad_never_mounted"] call cti_probe_fnc_done;
    };

    private _rider = (units _group) select (units _group findIf { vehicle _x isNotEqualTo _x });
    diag_log format ["CTI|transport_probe_boarded squad=%1 riders=%2 vehicle=%3 is_issued=%4",
        _squadId,
        { vehicle _x isNotEqualTo _x } count units _group,
        typeOf vehicle _rider,
        vehicle _rider isEqualTo _second];
    ["boarded"] call cti_probe_fnc_legRan;

    [] call cti_probe_fnc_done;
};
