// probe: transport
// issues: 170
// window: 480
//
// #170 in-world probe: the free ride (ADR-0059). A Squad bought at its own Base
// is issued the ladder's rung for its size without anybody asking, the vehicle
// lands in the group's own pool, a Squad whose vehicle has gone elsewhere is
// issued another and loses the first, a Squad that walks away from its vehicle
// stops owning it and gets it back on returning, and an AI-led Squad under a
// distant Order actually mounts.
//
// **What each leg bets on, because they are not the same kind of claim.** Five
// of the six are decisions this addon owns outright: the grant rule (a Squad at
// its own Base with no vehicle here gets one), the first-match read of the
// authored ladder, the replacement rule (one per Squad, and the old one goes),
// and the two halves of the locality rule (`disowned`, `repooled`). The sixth —
// `boarded` — is the engine's, and it is the one sentence ADR-0059's Ruling 4
// rests on: "Groups will automatically board any transport vehicles they own if
// the next waypoint is far enough away" (`topics/Waypoints.wiki`). A red there
// is that ruling overturned, not a bug in this addon, and the ADR says so under
// "What would overturn this" — the fix would be explicit GET IN waypoints in
// cti_fnc_orderApply. It is asserted here rather than left to a playtest because
// the whole of the ruling's second principal — "AI commander on behalf of squad
// leaders" — is carried by it.
//
// **The boarding leg tests more than the sentence it quotes.** That sentence
// lives under `=== Move ===`, and the Order this leg gives is a Capture, which
// `cti_fnc_orderApply` lays as a bare Seek-and-Destroy waypoint. Capture is by
// far the commonest Order in a Campaign, so the ride is worth nothing to the AI
// Commander if boarding is a Move-only behaviour. Deliberately not pre-empted by
// changing Capture to the MOVE→SAD pair Assault already uses: that would be a
// change to Order behaviour made on a guess, and this leg is the measurement
// that would justify it. A red here naming a SAD waypoint is what buys it.
//
// **The locality rule is here because a corpus run put it here.** At `0b4fa85`
// the vehicle stayed in the group's pool wherever the Squad went, and
// `campaign-end`'s assaulting Squad — staged 250 m from the enemy HQ with its
// truck 4.4 km behind it at its own Base — marched about 980 m the wrong way and
// never closed a metre on the HQ it was sent to destroy
// (`range=1227.91 closest=250`, `~/.arma-cti/runs/20260805T071859Z-campaign-end`).
// `disowned` and `repooled` are that fix's own assertions, so the next reader
// does not have to rediscover it through another probe's timeout.
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
// The window is 480 rather than the default 150 because the subject is that
// long, term by term: 20 s for the world to build, 60 s for a Purchase to cross
// the port, be pumped into the world on a 2 s poll and be swept by a 10 s watch,
// 60 s for the same watch to notice a vehicle that has left and replace it, 60 s
// each for the disowning and the re-pooling to be swept, 150 s for an Order to
// cross the port, be applied as waypoints and for the engine to decide to board,
// and 20 s for the probe's own logging. That is 430 s of deadlines. Every one is
// a deadline rather than a settle — each leg ends the moment its subject lands —
// and the widest of them is the boarding wait, sized for a bad draw for #28's
// reason rather than because a shorter one was ever seen to fail.
//
// `just regress transport`, or by hand `just probe spike/probes/transport.sqf 480`.
[] spawn {
    // Every leg this probe owes an answer for. A leg is struck off when it has
    // been measured; anything still standing at an early exit is reported
    // `unverified`, which the harness reads as infra_unavailable (ADR-0037,
    // #116).
    ["transport", ["issued", "pooled", "replaced", "disowned", "repooled", "boarded"]]
        call cti_probe_fnc_legsOwed;

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

    // Waited on as a **pair**, which is #33's lesson and cost this probe its
    // first corpus verdict. cti_fnc_transportIssue records the new vehicle and
    // deletes the old one in the same frame, and `commands/deleteVehicle.wiki`
    // says the deletion itself lands later: "The actual object deletion, when
    // the object becomes objNull, happens on the next frame after command
    // execution". So a probe that woke on the record alone read the old vehicle
    // exactly one frame too early and called a correct replacement wrong
    // (`old_gone=false`, `~/.arma-cti/runs/20260805T072304Z-transport`). The
    // window is unmoved at 60 s: what changed is what is being waited for, not
    // how long.
    private _second = objNull;
    _deadline = diag_tickTime + 60;
    waitUntil {
        _second = _group getVariable ["cti_transport", objNull];
        (_second isNotEqualTo _first && {!isNull _second} && {isNull _first})
            || diag_tickTime > _deadline
    };

    // The two halves are told apart, because they are different findings: a
    // record that never moved is a watch that did not fire, and a record that
    // moved with the old vehicle still standing is a delete that did not take —
    // or a release, which would have said so in the log.
    if (_second isEqualTo _first || {isNull _second}) exitWith {
        diag_log format ["CTI|FAIL class=timeout transport_probe_never_replaced squad=%1 away_at=%2 waited=%3",
            _squadId, _away, 60];
        ["the_stranded_vehicle_was_never_replaced"] call cti_probe_fnc_done;
    };
    if !(isNull _first) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed transport_probe_old_one_stayed squad=%1 alive=%2 crew=%3",
            _squadId, alive _first, count crew _first];
        ["the_replaced_vehicle_was_never_deleted"] call cti_probe_fnc_done;
    };

    private _newAt = [_second] call _placeOf;
    if (_newAt isNotEqualTo _baseId) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed transport_probe_replacement_elsewhere squad=%1 new_at=%2",
            _squadId, _newAt];
        ["the_replacement_was_not_at_the_base"] call cti_probe_fnc_done;
    };
    diag_log format ["CTI|transport_probe_replaced squad=%1 new_at=%2 pool=%3",
        _squadId, _newAt, count assignedVehicles _group];
    ["replaced"] call cti_probe_fnc_legRan;

    // ------------------------------------------------------------ disowned
    // A Squad away from its vehicle stops owning it, so the engine never walks
    // it back for one (ADR-0059's amendment, forced by `campaign-end` at
    // `0b4fa85`: an assaulting Squad staged 250 m from the enemy HQ, with its
    // truck 4.4 km behind at its own Base, marched about 980 m the wrong way
    // and never closed a metre). Staged by moving the Squad rather than the
    // truck, because moving the truck is the *replacement* rule above — the
    // disowning rule only bites where no replacement is issued, which is
    // anywhere that is not the Squad's own Base.
    private _stand = {
        params ["_where"];
        (_where getOrDefault ["position", [0, 0]]) params ["_x0", "_y0"];
        { _x setPosATL [_x0, _y0, 0] } forEach units _group;
        [getPosATL leader _group, _objectives, _bases] call cti_fnc_placeOf
    };

    private _standing = [_elsewhere] call _stand;
    if (_standing isEqualTo _baseId) exitWith {
        diag_log format ["CTI|FAIL class=infra_unavailable transport_probe_squad_move_refused squad=%1 at=%2",
            _squadId, _standing];
        ["the_squad_would_not_leave_its_base"] call cti_probe_fnc_done;
    };

    _deadline = diag_tickTime + 60;
    waitUntil { !(_second in assignedVehicles _group) || diag_tickTime > _deadline };
    if (_second in assignedVehicles _group) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed transport_probe_never_disowned squad=%1 at=%2 metres=%3 pool=%4",
            _squadId, _standing, round (_second distance leader _group),
            count assignedVehicles _group];
        ["the_squad_kept_a_vehicle_it_had_walked_away_from"] call cti_probe_fnc_done;
    };
    diag_log format ["CTI|transport_probe_disowned squad=%1 at=%2 metres=%3",
        _squadId, _standing, round (_second distance leader _group)];
    ["disowned"] call cti_probe_fnc_legRan;

    // ------------------------------------------------------------ repooled
    // And gets it back on returning, or the second march is on foot for good —
    // which is the half a disowning rule on its own would have broken.
    private _home = [(["nato_airbase"] call cti_probe_fnc_placeNamed)] call _stand;
    if (_home isNotEqualTo _baseId) exitWith {
        diag_log format ["CTI|FAIL class=infra_unavailable transport_probe_squad_return_refused squad=%1 at=%2",
            _squadId, _home];
        ["the_squad_would_not_return_to_its_base"] call cti_probe_fnc_done;
    };

    _deadline = diag_tickTime + 60;
    waitUntil { _second in assignedVehicles _group || diag_tickTime > _deadline };
    if !(_second in assignedVehicles _group) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed transport_probe_never_repooled squad=%1 metres=%2 held=%3",
            _squadId, round (_second distance leader _group),
            (_group getVariable ["cti_transport", objNull]) isEqualTo _second];
        ["the_returned_squad_never_got_its_vehicle_back"] call cti_probe_fnc_done;
    };
    diag_log format ["CTI|transport_probe_repooled squad=%1 metres=%2",
        _squadId, round (_second distance leader _group)];
    ["repooled"] call cti_probe_fnc_legRan;

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
