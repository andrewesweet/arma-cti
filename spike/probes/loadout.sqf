// probe: loadout
// issues: 172
// window: 600
// env: CTI_HEADED_CLIENT=1 CTI_PROBE_CLIENT=240
//
// #172 in-world probe: the human's loadout ruling (ADR-0056), on a real player.
// A menu offered on his own body at his own Base, a pick granted and worn, the
// same kind of pick refused when he is not at his Base, and the kit still on him
// after he has died and come back.
//
// **A headless client cannot stand in for the subject**, and neither can an AI
// unit — which is the ruling's own "players only". An HC holds no player unit
// (ADR-0025, and `client-port.sqf`'s header for the engine's reason), so it has
// no UID to file a kit under, no body to hang a menu on and nothing to respawn.
// So this probe declares its headed client in its own `env:` header and reports
// every leg `unverified` when the run did not send one (ADR-0037, #116): a green
// pass with nobody in a player slot would be a pass about something smaller than
// the ticket.
//
// What it asserts and what it cannot, stated up front. The wish-to-kit path is
// exercised end to end from a real client: the server offers the menu, the
// client publishes a pick on its own body, and the server judges it and dresses
// the man. What no tier we have can exercise is the mouse landing on the action
// entry — the same boundary `human-commander.sqf` states about a rendered map
// with a person clicking on it. So the menu itself is asserted as *installed*:
// the client reads its own action list back and this checks there is one entry
// per catalogue kit, each carrying that kit's id and the Base rule in its
// condition. The pick is then driven through the installed statement where the
// engine hands one back that can be called, and through the wish that statement
// publishes where it does not — and which of the two ran is logged, so the
// evidence says what was exercised rather than implying more.
//
// **Vacuity is designed out of the kit assertions.** The player's slot spawns
// him as an ordinary rifleman, and the catalogue's `rifleman` kit is cut from
// that same class — so a probe that picked it would pass with the whole feature
// switched off. It picks `autorifleman` instead, and asserts *before* it picks
// that the weapon he is holding is not one that kit's class carries. Every later
// reading is against the class's own authored `weapons[]` array
// (`commands/setUnitLoadout.wiki` quotes that entry as standard for any unit
// class), never against a classname written out here.
//
// The staged moves are asserted to have taken effect before anything is read
// through them (#80): the teleport is checked with cti_fnc_loadoutAtBase — the
// rule's own function — and the kill is checked with `alive`.
//
// The window is 600 rather than the default 150 because the subject is that
// long, term by term: 20 s for the world to build, 240 s for a cold client to
// launch on the Windows host and be swept into a slot (the allowance
// `client-port` and `dead-principal` use; 24.7 s observed on #18's run), 30 s
// for the watch to offer a menu on his body and the client to read it back,
// 45 s for the pick to be granted and worn, 20 s to move him off his Base and
// confirm he is off it, 20 s of watching a second pick *not* be granted, 30 s to
// kill him and see the kill land, 90 s for the respawn (the configured delay is
// read back rather than copied — it is 5 s today and #189 makes it 30 s, and 90
// covers either with margin), 40 s for the watch to dress the new body, and 20 s
// for the report leg. That is 555 s of deadlines; 600 leaves the probe's own
// logging inside it. The only irreducible costs are the 20 s absence claim and
// the respawn timer, and neither is a wait for a flaky assertion to come good:
// the absence claim asserts the *grant* did not move, and the respawn leg
// asserts the kit came back rather than that it never left.
//
// `just regress loadout`, or by hand `just probe spike/probes/loadout.sqf 600`.
[] spawn {
    // Every leg this probe owes an answer for. A leg is struck off when it has
    // been measured; anything still standing at an early exit is reported
    // `unverified`, which the harness reads as infra_unavailable (ADR-0037,
    // #116).
    ["loadout", ["menu", "granted", "away", "respawn", "reported"]] call cti_probe_fnc_legsOwed;

    private _extension = call cti_fnc_shimName;
    if (_extension isEqualTo "") exitWith {
        diag_log "CTI|FAIL class=infra_unavailable loadout_probe_no_shim";
        ["the_world_had_no_shim"] call cti_probe_fnc_done;
    };

    [20] call cti_probe_fnc_worldReady;

    // --------------------------------------------------------------- the player
    private _waitFor = missionNamespace getVariable ["CTI_PROBE_CLIENT", 0];
    if (_waitFor <= 0) exitWith {
        ["run_sent_no_headed_client"] call cti_probe_fnc_done;
    };

    // The Commander slot is the only player slot this mission has today — the
    // squad-leader slot is #25 — and the sweep is what tells us a person is in
    // it. Nothing below is about commanding: it is about the body he stands in.
    ([_waitFor] call cti_probe_fnc_commanderSlot) params ["_side", "_uid", "_unit"];
    if (_side isEqualTo "") exitWith {
        diag_log format ["CTI|FAIL class=timeout loadout_probe_no_client_assigned waited=%1 players=%2",
            _waitFor, count allPlayers];
        ["no_person_in_a_player_slot"] call cti_probe_fnc_done;
    };
    if (isNull _unit) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed loadout_probe_assigned_uid_absent uid=%1", _uid];
        ["assigned_uid_holds_no_unit"] call cti_probe_fnc_done;
    };

    private _target = owner _unit;
    private _configured = getNumber (missionConfigFile >> "respawnDelay");
    diag_log format ["CTI|loadout_probe_player side=%1 owner=%2 uid=%3 respawn_delay=%4",
        _side, _target, _uid, _configured];

    // The body the server currently matches to that UID, re-read every time:
    // a respawn is a new object and the old one is a corpse.
    private _bodyOf = {
        private _found = objNull;
        { if (getPlayerUID _x isEqualTo _uid) exitWith { _found = _x } } forEach allPlayers;
        _found
    };

    // ------------------------------------------------------------- the catalogue
    private _kits = call cti_fnc_loadoutCatalogue;
    if (_kits isEqualTo []) exitWith {
        diag_log "CTI|FAIL class=assertion_failed loadout_probe_no_catalogue";
        ["the_world_shipped_no_menu"] call cti_probe_fnc_done;
    };
    private _kitIds = _kits apply { _x getOrDefault ["id", ""] };

    // What a soldier of a kit's class carries, read off that class's own
    // authored `weapons[]` entry rather than written out here.
    private _armsOf = {
        params ["_kitId"];
        private _index = _kits findIf { (_x getOrDefault ["id", ""]) isEqualTo _kitId };
        if (_index < 0) exitWith { [] };
        private _class = ((_kits # _index) getOrDefault ["units", createHashMap])
            getOrDefault [_side, ""];
        if (_class isEqualTo "") exitWith { [] };
        getArray (configFile >> "CfgVehicles" >> _class >> "weapons")
    };

    private _wanted = "autorifleman";
    private _second = "marksman";
    private _wantedArms = [_wanted] call _armsOf;
    private _secondArms = [_second] call _armsOf;
    if (_wantedArms isEqualTo [] || { _secondArms isEqualTo [] }) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed loadout_probe_kit_has_no_arms first=%1 second=%2 side=%3 menu=%4",
            _wantedArms, _secondArms, _side, _kitIds];
        ["a_menu_kit_named_no_weapon"] call cti_probe_fnc_done;
    };

    // The vacuity checks the header promises. If he already carries the kit's
    // weapon, or the two kits arm him the same way, every reading below would
    // pass with the feature switched off.
    private _before = primaryWeapon _unit;
    if (_before in _wantedArms || { (_secondArms # 0) in _wantedArms }) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed loadout_probe_kits_indistinguishable worn=%1 first=%2 second=%3",
            _before, _wantedArms, _secondArms];
        ["the_probe_could_not_tell_the_kits_apart"] call cti_probe_fnc_done;
    };
    diag_log format ["CTI|loadout_probe_before weapon=%1 first=%2 second=%3",
        _before, _wantedArms, _secondArms];

    // ------------------------------------------------------------------ the menu
    // Installed by the server's watch on the client's own body, so it is read
    // back from the client: an action list is local to the machine it was added
    // on. `actionParams`: title 0, statement 1, arguments 2, condition 7.
    private _readMenu = {
        cti_loadoutProbeMenu = nil;
        {
            private _seen = [];
            {
                private _params = player actionParams _x;
                private _arguments = _params # 2;
                if (isNil "_arguments") then { _arguments = [] };
                _seen pushBack [_x, _params # 0, _arguments, _params # 7];
            } forEach (actionIDs player);
            cti_loadoutProbeMenu = _seen;
            publicVariable "cti_loadoutProbeMenu";
        } remoteExec ["call", _target];

        private _until = diag_tickTime + 10;
        waitUntil { !isNil "cti_loadoutProbeMenu" || { diag_tickTime > _until } };
        if (isNil "cti_loadoutProbeMenu") exitWith { [] };
        +cti_loadoutProbeMenu
    };

    // A `while` around the read rather than a `waitUntil` on it: the read has a
    // `waitUntil` of its own, and one cannot be nested inside another's
    // condition.
    private _deadline = diag_tickTime + 30;
    private _menu = [];
    private _entries = [];
    while { count _entries < count _kits && { diag_tickTime < _deadline } } do {
        _menu = call _readMenu;
        // Ours are the entries whose arguments open with a catalogue kit id;
        // anything else on the body belongs to somebody else.
        _entries = _menu select { ((_x # 2) param [0, ""]) in _kitIds };
    };
    if (count _entries < count _kits) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed loadout_probe_menu_short have=%1 want=%2 actions=%3",
            count _entries, count _kits, _menu];
        ["the_client_was_offered_no_menu"] call cti_probe_fnc_done;
    };

    // One entry per authored kit, each gated on the rule the server grants
    // through. The ids are what the pick below is driven from, which is what
    // binds this probe to the real menu rather than to a list of its own.
    private _offeredIds = _entries apply { (_x # 2) param [0, ""] };
    private _missing = _kitIds select { !(_x in _offeredIds) };
    private _ungated = _entries select { ((_x # 3) find "cti_fnc_loadoutAtBase") < 0 };
    if (_missing isNotEqualTo [] || { _ungated isNotEqualTo [] }) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed loadout_probe_menu_wrong missing=%1 ungated=%2 offered=%3",
            _missing, count _ungated, _offeredIds];
        ["the_menu_was_not_the_authored_one"] call cti_probe_fnc_done;
    };
    diag_log format ["CTI|loadout_probe_menu entries=%1 ids=%2", count _entries, _offeredIds];
    ["menu"] call cti_probe_fnc_legRan;

    // --------------------------------------------------------------- he picks one
    // Installed on the client once; each pick is then a two-value call, sent as
    // a compiled block with its values inside it. `client-port`, `reinforce` and
    // `dead-principal` all drive their clients this way, and the vendored
    // `commands/remoteExec.wiki` is why: an argument array handed to a bare
    // `call` is the shape it tells you to avoid.
    {
        cti_loadoutProbePicker = {
            params ["_actionId", "_kitId"];
            private _how = "wish";
            if (_actionId >= 0) then {
                private _installed = player actionParams _actionId;
                private _statement = _installed # 1;
                if (_statement isEqualType {}) then {
                    _how = "action";
                    // The arguments the action was installed with rather than a
                    // copy of them: this is the click's own path as far as it
                    // can be walked without a mouse.
                    [player, player, _actionId, _installed # 2] call _statement;
                };
            };
            if (_how isEqualTo "wish") then {
                player setVariable ["cti_loadoutWish", _kitId, true];
            };
            cti_loadoutProbePicked = [_kitId, _how];
            publicVariable "cti_loadoutProbePicked";
        };
    } remoteExec ["call", _target];

    private _drivePick = {
        params ["_kitId"];
        cti_loadoutProbePicked = nil;
        private _found = _entries select { ((_x # 2) param [0, ""]) isEqualTo _kitId };
        private _actionId = if (_found isEqualTo []) then { -1 } else { (_found # 0) # 0 };
        (compile format ["[%1, '%2'] call cti_loadoutProbePicker", _actionId, _kitId])
            remoteExec ["call", _target];
        private _until = diag_tickTime + 30;
        waitUntil { !isNil "cti_loadoutProbePicked" || { diag_tickTime > _until } };
        if (isNil "cti_loadoutProbePicked") exitWith {
            diag_log format ["CTI|FAIL class=timeout loadout_probe_client_silent kit=%1", _kitId];
            false
        };
        diag_log format ["CTI|loadout_probe_picked kit=%1 how=%2",
            cti_loadoutProbePicked # 0, cti_loadoutProbePicked # 1];
        true
    };

    if !([_wanted] call _drivePick) exitWith {
        ["the_client_never_published_a_pick"] call cti_probe_fnc_done;
    };

    // Granted and worn. The grant is the server's own record and the kit is what
    // a person would see; both are read, because a record without a kit is a
    // feature that only pretends to work.
    private _deadline = diag_tickTime + 45;
    private _granted = "";
    waitUntil {
        _granted = (missionNamespace getVariable ["cti_loadoutChosen", createHashMap])
            getOrDefault [_uid, ""];
        (_granted isEqualTo _wanted && { (primaryWeapon (call _bodyOf)) in _wantedArms })
            || { diag_tickTime > _deadline }
    };
    private _worn = primaryWeapon (call _bodyOf);
    if (_granted isNotEqualTo _wanted || { !(_worn in _wantedArms) }) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed loadout_probe_not_dressed granted=%1 want=%2 weapon=%3 arms=%4",
            _granted, _wanted, _worn, _wantedArms];
        ["the_pick_at_base_was_never_worn"] call cti_probe_fnc_done;
    };
    diag_log format ["CTI|loadout_probe_granted kit=%1 weapon=%2", _granted, _worn];
    ["granted"] call cti_probe_fnc_legRan;

    // ------------------------------------------------ and cannot pick one away
    // Open ground: no Base, no Objective and not the sea, found by asking the
    // manifest's own reading rather than by writing a coordinate out here.
    private _home = (missionNamespace getVariable ["cti_basesBySide", createHashMap])
        getOrDefault [_side, createHashMap];
    (_home getOrDefault ["position", [0, 0]]) params ["_east", "_north"];
    private _from = [_east, _north, 0];
    private _map = missionNamespace getVariable ["cti_map", createHashMap];
    private _open = [];
    {
        private _try = _from getPos [600, _x];
        if (_open isEqualTo []
            && { !surfaceIsWater _try }
            && { ([_try, _map getOrDefault ["objectives", []], _map getOrDefault ["bases", []]]
                call cti_fnc_placeOf) isEqualTo "" }) then {
            _open = _try;
        };
    } forEach [0, 45, 90, 135, 180, 225, 270, 315];
    if (_open isEqualTo []) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed loadout_probe_no_open_ground base=%1", _from];
        ["the_map_offered_no_ground_off_a_place"] call cti_probe_fnc_done;
    };

    (call _bodyOf) setPosATL [_open # 0, _open # 1, 0];
    private _deadline = diag_tickTime + 20;
    waitUntil { !([call _bodyOf] call cti_fnc_loadoutAtBase) || { diag_tickTime > _deadline } };
    if ([call _bodyOf] call cti_fnc_loadoutAtBase) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed loadout_probe_move_refused at=%1 want=%2",
            mapGridPosition (getPosATL (call _bodyOf)), mapGridPosition _open];
        ["the_world_would_not_move_him_off_his_base"] call cti_probe_fnc_done;
    };
    diag_log format ["CTI|loadout_probe_away at=%1", mapGridPosition (getPosATL (call _bodyOf))];

    if !([_second] call _drivePick) exitWith {
        ["the_client_never_published_a_second_pick"] call cti_probe_fnc_done;
    };

    // An absence claim, so it is a length of time nothing happened for and has
    // no condition to wait on (docs/regression-tier.md, the honesty rule). What
    // it claims is that the *grant* did not move — a decision the code owns —
    // and never that a firefight went one way.
    private _until = diag_tickTime + 20;
    private _moved = "";
    private _took = false;
    waitUntil {
        _moved = (missionNamespace getVariable ["cti_loadoutChosen", createHashMap])
            getOrDefault [_uid, ""];
        _took = (primaryWeapon (call _bodyOf)) in _secondArms;
        _moved isNotEqualTo _wanted || _took || { diag_tickTime > _until }
    };
    if (_moved isNotEqualTo _wanted || _took) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed loadout_probe_granted_away_from_base granted=%1 want=%2 weapon=%3",
            _moved, _wanted, primaryWeapon (call _bodyOf)];
        ["a_pick_away_from_base_was_granted"] call cti_probe_fnc_done;
    };
    diag_log format ["CTI|loadout_probe_refused_away granted=%1 asked=%2 dwell=20", _moved, _second];
    ["away"] call cti_probe_fnc_legRan;

    // ------------------------------------------------------ he dies and returns
    // The wish is put back to what he is already wearing before the kill, so the
    // leg below reads the dressing rule and never a fresh grant: he respawns at
    // his own Base, where a standing wish for another kit would be honoured, and
    // that is correct behaviour rather than something to assert around.
    if !([_wanted] call _drivePick) exitWith {
        ["the_client_never_restored_its_pick"] call cti_probe_fnc_done;
    };

    private _corpse = call _bodyOf;
    _corpse setDamage 1;
    private _deadline = diag_tickTime + 30;
    waitUntil { !alive _corpse || { diag_tickTime > _deadline } };
    if (alive _corpse) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed loadout_probe_kill_refused damage=%1", damage _corpse];
        ["the_world_refused_the_kill"] call cti_probe_fnc_done;
    };
    diag_log format ["CTI|loadout_probe_killed configured_delay=%1", _configured];

    // 90 s covers the configured delay either side of #189's change, and it is a
    // deadline rather than a copy of the number: what this world was configured
    // with is on the record above.
    private _deadline = diag_tickTime + 90;
    waitUntil {
        ((call _bodyOf) isNotEqualTo _corpse && { alive (call _bodyOf) })
            || { diag_tickTime > _deadline }
    };
    private _reborn = call _bodyOf;
    if (_reborn isEqualTo _corpse || { !alive _reborn }) exitWith {
        diag_log format ["CTI|FAIL class=timeout loadout_probe_never_respawned new_body=%1 alive=%2 delay=%3",
            _reborn isNotEqualTo _corpse, alive _reborn, _configured];
        ["the_player_never_came_back"] call cti_probe_fnc_done;
    };
    diag_log format ["CTI|loadout_probe_respawned weapon=%1", primaryWeapon _reborn];

    private _deadline = diag_tickTime + 40;
    waitUntil { ((primaryWeapon (call _bodyOf)) in _wantedArms) || { diag_tickTime > _deadline } };
    private _after = primaryWeapon (call _bodyOf);
    if !(_after in _wantedArms) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed loadout_probe_kit_lost_on_respawn weapon=%1 want=%2 kit=%3",
            _after, _wantedArms, _wanted];
        ["the_kit_did_not_survive_the_respawn"] call cti_probe_fnc_done;
    };
    diag_log format ["CTI|loadout_probe_redressed kit=%1 weapon=%2", _wanted, _after];
    ["respawn"] call cti_probe_fnc_legRan;

    // ------------------------------------------------- and the wire carries it
    // What the daemon does with the field is a Python test's subject; what only
    // a world can answer is that the sampler puts the pick on the report and the
    // exported schema declares the field it travels in. A sampler the schema
    // does not declare is a `schema_stale` line in the server's own log, and
    // this is that drift caught before a session meets it.
    private _sampled = call cti_fnc_loadoutSample;
    private _declared = ((call cti_fnc_commandSchema) getOrDefault ["observe_report", createHashMap])
        getOrDefault ["payload", []];
    if ((_sampled getOrDefault [_uid, ""]) isNotEqualTo _wanted) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed loadout_probe_not_reported sampled=%1 want=%2",
            _sampled, _wanted];
        ["the_report_did_not_carry_the_pick"] call cti_probe_fnc_done;
    };
    if !("loadouts" in _declared) exitWith {
        diag_log format ["CTI|FAIL class=schema_stale loadout_probe_field_undeclared payload=%1", _declared];
        ["the_exported_schema_declared_no_such_field"] call cti_probe_fnc_done;
    };
    diag_log format ["CTI|loadout_probe_reported sampled=%1 payload=%2", _sampled, _declared];
    ["reported"] call cti_probe_fnc_legRan;

    [] call cti_probe_fnc_done;
};
