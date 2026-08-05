// probe: human-commander
// issues: 18, 19, 46, 116, 174, 175, 176
// window: 420
// env: CTI_WINDOWS_CLIENT=1 CTI_PROBE_CLIENT=240 CTI_AI_SIDE=EAST CTI_AI_SEED=1
//
// #18 in-world probe: the human Commander's path, as far as a world with no
// human in it can be made to answer for it.
//
// #19's demo rides on it, and that is why EAST is under an AI Commander here.
// Every other probe in the corpus has a world with either Commanders or a
// client in it, never both: `two-commanders` and `campaign-end` play both sides
// with nobody watching, and this probe used to drive a real client around an
// empty Campaign. The demo Phase 1 exists to give is one world with both kinds
// of Commander in it at once, so this probe now is that world — a person in the
// NATO Commander slot, CSAT played by the seeded scorer, and both commanding
// through the one port.
//
// **The demo's wording does not survive contact with the daemon, and that is a
// finding rather than a defect.** #3 says "watch both AI sides fight over
// Objectives, then take over as Commander"; there is no handover, because
// `Daemon._command` refuses a Command for a side an AI is playing — one
// Commander per side, whichever kind, for ADR-0015's reason. So the demo is two
// acts against one build rather than one continuous session: both sides under
// AI is `two-commanders`/`campaign-end`, and taking a side is a bring-up that
// leaves that side free. That boundary is asserted below rather than left as
// prose, because it is the rule the demo's shape is a consequence of. Whether a
// handover is wanted at all is a gameplay decision and travels as #126.
//
// `just regress human-commander`, or by hand
// `just probe spike/probes/human-commander.sqf`.
//
// What this can and cannot settle, stated up front so nobody reads more out of
// a green run than is in it. The dedicated-server-plus-headless-client topology
// has no person in a Commander slot, and a headless client cannot stand in for
// one: `remoteExecutedOwner` returns 0 for a call arriving from a headless
// client by engine design (BIKI, vendored), and a headless client holds no
// player unit to carry a UID, so it can be neither attributed nor assigned. So
// this probe asserts everything up to and including the gateway's refusal of an
// unassigned caller, the view the daemon serves a Commander, and the identity
// between what the UI can say and what the port judges. What it cannot assert
// is a rendered map with a person clicking on it, and that is the human's play
// session rather than a longer window.
//
// The client leg is on in the corpus and declared in the `env:` header above,
// not left to a caller to remember (ADR-0037, #116). It used to default off:
// CTI_PROBE_CLIENT was 0 unless someone set it, so every corpus run of this
// probe finished green having never crossed the machine boundary that the
// second half of the ticket is entirely about. A leg that is optional in
// practice is a leg nobody runs.
//
// The window is 420 rather than the default 150 because the subject grew with
// it, not because a shorter one was flaky: the client has to launch on the
// Windows host, connect and be swept into the Commander slot (240 s allowed for
// a cold start, 24.7 s observed on #18's run), and the accepted Purchase is then
// polled to a 60 s ceiling with a 30 s wait on the client's own report after it.
// The #174 map-picture checks ride the same client without moving the window:
// they run on the client right after it publishes its first report, stage and
// read in one unscheduled block, and their 30 s server-side wait overlaps the
// 60 s Purchase poll that runs concurrently. The #176 notification checks ride
// the same way — staged pushes through the real Observation door, read in one
// unscheduled block — and their wait overlaps the same poll. The #175 checks
// are two halves and neither moves it either: the client half is a third staged
// block on the same client behind the same overlapping wait, and the server
// half's 30 s poll for a fielded position runs *before* the client leg begins,
// inside the stretch already spent waiting for EAST's Commander to field its
// first Squad — by which point WEST's has been reported some sixteen times.
//
// Run by hand without a client — `just probe spike/probes/human-commander.sqf` —
// this probe reports its client leg `unverified` and the run is
// infra_unavailable. That is the honest answer to "nothing was measured", and it
// is the same answer the tier gives for any other condition it could not read.
[] spawn {
    private _extension = call cti_fnc_shimName;
    if (_extension isEqualTo "") exitWith {
        diag_log "CTI|FAIL class=infra_unavailable human_commander_probe_no_shim";
    };

    // The world built and both server loops turned once (#46, replacing a fixed
    // 20 s settle and keeping its 20 s as the deadline).
    [20] call cti_probe_fnc_worldReady;

    // ---------------------------------------------------------------- whitelist
    // The mission's own config, read out of the running mission rather than out
    // of the file it was packed from. "No additional function is whitelisted to
    // make the UI work" is a claim about what shipped, and this is where what
    // shipped can be asked.
    private _remote = missionConfigFile >> "CfgRemoteExec";
    private _functionsMode = getNumber (_remote >> "Functions" >> "mode");
    private _commandsMode = getNumber (_remote >> "Commands" >> "mode");
    private _whitelisted = configProperties [_remote >> "Functions", "isClass _x", true]
        apply { configName _x };

    diag_log format ["CTI|human_commander_probe_whitelist functions=%1 commands=%2 classes=%3",
        _functionsMode, _commandsMode, _whitelisted];

    if (_functionsMode isNotEqualTo 1 || { _commandsMode isNotEqualTo 1 }) then {
        diag_log format ["CTI|FAIL class=assertion_failed human_commander_probe_remoteexec_open functions=%1 commands=%2",
            _functionsMode, _commandsMode];
    };
    if (_whitelisted isNotEqualTo ["cti_fnc_portGateway"]) then {
        diag_log format ["CTI|FAIL class=assertion_failed human_commander_probe_whitelist_grew classes=%1",
            _whitelisted];
    };

    // ---------------------------------------------------------------- vocabulary
    // The guarantee #18 exists for, asked mechanically: what the map UI can say
    // is read out of the same schema the port judges by, so an Order the human
    // can express and the AI cannot would be a fork of the wire format. Run on
    // the server because cti_fnc_mapVerbs reads the schema and nothing else —
    // the machine it runs on is not part of the answer.
    private _schema = call cti_fnc_commandSchema;
    private _verbs = call cti_fnc_mapVerbs;
    private _uiOrders = (_verbs select { (_x # 1) isEqualTo "order" }) apply { _x # 2 };
    private _uiBuys = (_verbs select { (_x # 1) isEqualTo "purchase" }) apply { _x # 2 };
    private _portOrders = _schema getOrDefault ["orders", []];
    private _portBuys = keys (_schema getOrDefault ["squads", createHashMap]);
    _portBuys sort true;

    diag_log format ["CTI|human_commander_probe_vocabulary ui_orders=%1 ui_buys=%2", _uiOrders, _uiBuys];

    if (_uiOrders isNotEqualTo _portOrders) then {
        diag_log format ["CTI|FAIL class=assertion_failed human_commander_probe_order_vocabulary ui=%1 port=%2",
            _uiOrders, _portOrders];
    };
    if (_uiBuys isNotEqualTo _portBuys) then {
        diag_log format ["CTI|FAIL class=assertion_failed human_commander_probe_buy_vocabulary ui=%1 port=%2",
            _uiBuys, _portBuys];
    };

    // ---------------------------------------------------------------- gateway
    // An unassigned caller is refused, and the refusal is the port's own word
    // rather than a dead click. Called here on the server, where
    // remoteExecutedOwner is 0 — which is the same answer the engine gives for a
    // headless client, and the reason the accepted case needs a person.
    private _before = ([createHashMapFromArray [
        ["id", "human-commander-probe-view-before"],
        ["verb", "view"],
        ["payload", createHashMapFromArray [["side", "WEST"]]]
    ]] call cti_probe_fnc_rpc) getOrDefault ["result", createHashMap];

    private _sent = [["purchase", [["squad_type", "rifle"]]] call cti_fnc_command]
        call cti_fnc_portGateway;
    if (_sent) then {
        diag_log "CTI|FAIL class=assertion_failed human_commander_probe_unassigned_accepted";
    } else {
        diag_log "CTI|human_commander_probe_unassigned_refused";
    };

    private _after = ([createHashMapFromArray [
        ["id", "human-commander-probe-view-after"],
        ["verb", "view"],
        ["payload", createHashMapFromArray [["side", "WEST"]]]
    ]] call cti_probe_fnc_rpc) getOrDefault ["result", createHashMap];
    if ((_after getOrDefault ["funds", -1]) isNotEqualTo (_before getOrDefault ["funds", -2])) then {
        diag_log format ["CTI|FAIL class=assertion_failed human_commander_probe_refused_command_spent before=%1 after=%2",
            _before getOrDefault ["funds", "?"], _after getOrDefault ["funds", "?"]];
    };

    // ------------------------------------------------------- one Commander per side
    // The rule the demo's two-act shape follows from (#19), asked of the daemon
    // rather than asserted in the header: EAST is under an AI Commander in this
    // world, so neither its view nor a Command for it is anyone else's to have.
    // A green run here is what makes "take over a side" mean "bring the world up
    // with that side free" rather than "join and displace the brain".
    private _taken = [createHashMapFromArray [
        ["id", "human-commander-probe-view-east"],
        ["verb", "view"],
        ["payload", createHashMapFromArray [["side", "EAST"]]]
    ]] call cti_probe_fnc_rpc;
    // `fromJSON` answers nil for a document it cannot read, so the reply is
    // rendered through a guard rather than straight into the format string.
    private _refusal = "unreadable_reply";
    private _shown = "nil";
    if (!isNil "_taken" && { _taken isEqualType createHashMap }) then {
        _shown = str _taken;
        if ((_taken getOrDefault ["status", ""]) isEqualTo "rejected") then {
            _refusal = (_taken getOrDefault ["reason", createHashMap]) getOrDefault ["code", ""];
        } else {
            _refusal = format ["status_%1", _taken getOrDefault ["status", ""]];
        };
    };
    if (_refusal isNotEqualTo "wrong_side") then {
        diag_log format ["CTI|FAIL class=assertion_failed human_commander_probe_ai_side_served got=%1 reply=%2",
            _refusal, _shown];
    } else {
        diag_log "CTI|human_commander_probe_ai_side_withheld code=wrong_side";
    };

    // ---------------------------------------------------------------- the view
    // WEST buys, so its own view has something in it. Sent as a Command on the
    // wire because that is how the world's own effects arrive, and the Squad has
    // to exist for the view to carry any.
    ["human-commander-probe-buy-WEST", "WEST"] call cti_probe_fnc_buySquad;

    // EAST's Squads are not bought here — they cannot be, and that is the point:
    // its Commander buys its own, off its own picture, in the same world. So the
    // enemy roster the leak assertion below is made against is a real one rather
    // than one this probe put there, and waiting for it is also the assertion
    // that the demo's other Commander is actually playing.
    private _fieldedBy = diag_tickTime + 90;
    waitUntil {
        count (["EAST"] call cti_probe_fnc_squadsOf) > 0 || { diag_tickTime > _fieldedBy }
    };
    private _enemy = ["EAST"] call cti_probe_fnc_squadsOf;
    if (count _enemy isEqualTo 0) exitWith {
        diag_log format ["CTI|FAIL class=timeout human_commander_probe_no_ai_opponent hint=%1",
            "is CTI_AI_SIDE=EAST set?"];
        diag_log "CTI|LEG name=human_commander_client status=unverified reason=no_ai_commander_on_the_other_side";
        diag_log "CTI|human_commander_probe_done";
    };
    diag_log format ["CTI|human_commander_probe_opponent side=EAST squads=%1 at=%2",
        count _enemy, time];

    private _reply = [createHashMapFromArray [
        ["id", "human-commander-probe-view"],
        ["verb", "view"],
        ["payload", createHashMapFromArray [["side", "WEST"]]]
    ]] call cti_probe_fnc_rpc;

    if !((_reply getOrDefault ["status", ""]) isEqualTo "ok") exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed human_commander_probe_view_refused reply=%1", _reply];
        diag_log "CTI|LEG name=human_commander_client status=unverified reason=view_refused_before_the_leg";
        diag_log "CTI|human_commander_probe_done";
    };

    private _view = _reply getOrDefault ["result", createHashMap];
    private _keys = keys _view;
    diag_log format ["CTI|human_commander_probe_view side=%1 funds=%2 squads=%3 keys=%4",
        _view getOrDefault ["side", "?"],
        _view getOrDefault ["funds", "?"],
        count (_view getOrDefault ["squads", []]),
        _keys];

    private _missing = ["side", "funds", "squads", "contacts", "owners", "hq"] select { !(_x in _keys) };
    if (_missing isNotEqualTo []) then {
        diag_log format ["CTI|FAIL class=assertion_failed human_commander_probe_view_incomplete missing=%1", _missing];
    };
    if ((_view getOrDefault ["side", ""]) isNotEqualTo "WEST") then {
        diag_log format ["CTI|FAIL class=assertion_failed human_commander_probe_view_wrong_side side=%1",
            _view getOrDefault ["side", "?"]];
    };

    // Per-side isolation, asked of the raw document rather than of a field:
    // EAST bought a Squad in the same breath WEST did, and nothing WEST is
    // handed may name it. The public halves are lifted out first — Objective
    // ownership and Base HQ status are public in every view on purpose (#27,
    // #35), so a town EAST holds says "EAST" in WEST's picture by design and
    // leaving it in would make this assertion a test of who holds what.
    private _private = +_view;
    _private deleteAt "owners";
    _private deleteAt "hq";
    private _raw = toJSON _private;
    if ((_raw find "EAST") > -1) then {
        diag_log format ["CTI|FAIL class=assertion_failed human_commander_probe_view_leaks_enemy raw=%1", _raw];
    };
    if (count (_view getOrDefault ["squads", []]) isNotEqualTo 1) then {
        diag_log format ["CTI|FAIL class=assertion_failed human_commander_probe_view_squads=%1",
            count (_view getOrDefault ["squads", []])];
    };

    // ---------------------------------------------------------------- #175: the position
    // The half of #175 no client can answer for: the served Observation carries
    // where a Commander's own Squad actually is, and it is that Squad's own
    // position rather than a plausible-looking pair of numbers. Judged against
    // the world's own reading of the same group, which is the only witness
    // there is — the sampler and this both ask the engine, and if they disagree
    // the wire is carrying something else.
    //
    // Polled rather than read once: the Squad was bought moments ago and is
    // spawned by the effect pump, so an empty `pos` can mean "not yet fielded"
    // as honestly as it can mean "the field is broken", and only the wait tells
    // them apart. This is waiting for the staging to take effect rather than
    // for a flaky assertion to pass. 30 s is six report intervals and does not
    // move the window: it runs inside the same stretch the client is being
    // waited for, and in practice the Squad has been reported many times over
    // by the time the ≤90 s wait for EAST's own first Squad above has returned.
    private _posBy = diag_tickTime + 30;
    private _wire = createHashMap;
    waitUntil {
        _wire = (((([createHashMapFromArray [
            ["id", format ["human-commander-probe-pos-%1", round diag_tickTime]],
            ["verb", "view"],
            ["payload", createHashMapFromArray [["side", "WEST"]]]
        ]] call cti_probe_fnc_rpc) getOrDefault ["result", createHashMap])
            getOrDefault ["squads", []]) param [0, createHashMap]);
        ((_wire getOrDefault ["pos", []]) isNotEqualTo []) || { diag_tickTime > _posBy }
    };

    private _wirePos = _wire getOrDefault ["pos", []];
    private _wireId = _wire getOrDefault ["id", ""];
    private _group = (["WEST"] call cti_probe_fnc_squadsOf) getOrDefault [_wireId, grpNull];

    if (_wirePos isEqualTo []) then {
        diag_log format ["CTI|FAIL class=assertion_failed human_commander_probe_view_no_position squad=%1 fielded=%2",
            _wireId, !isNull _group];
    } else {
        if (count _wirePos isNotEqualTo 2) then {
            // Two axes, which is the encoding ADR-0058 fixed: a strategic map
            // has no altitude to draw one at. Judged before anything reads the
            // pair, so a malformed position is named rather than crashing the
            // read that would have named it.
            diag_log format ["CTI|FAIL class=assertion_failed human_commander_probe_view_position_axes pos=%1",
                _wirePos];
        } else {
            // And whole metres: a marker on a strategic map cannot show a
            // fraction, so carrying one would be precision nothing can draw.
            _wirePos params ["_wireEast", "_wireNorth"];
            private _whole = _wireEast isEqualTo round _wireEast
                && { _wireNorth isEqualTo round _wireNorth };
            if !(_whole) then {
                diag_log format ["CTI|FAIL class=assertion_failed human_commander_probe_view_position_encoding pos=%1",
                    _wirePos];
            };

            if (isNull _group) then {
                diag_log format ["CTI|FAIL class=assertion_failed human_commander_probe_view_position_unwitnessed squad=%1",
                    _wireId];
            } else {
                // Agreement with the world, at the tolerance the ruling itself
                // set: the picture rides the 5 s push, so the wire is up to one
                // interval behind the men, which at infantry pace is tens of
                // metres. A hundred is that with room, and it is still orders of
                // magnitude tighter than the map origin or the wrong Place.
                private _truth = getPosATL leader _group;
                private _drift = [_wireEast, _wireNorth, 0] distance2D _truth;
                if (_drift > 100) then {
                    diag_log format ["CTI|FAIL class=assertion_failed human_commander_probe_view_position_disagrees squad=%1 wire=%2 world=%3 drift=%4",
                        _wireId, _wirePos, _truth, _drift];
                } else {
                    diag_log format ["CTI|human_commander_probe_view_position squad=%1 wire=%2 world=%3 drift=%4",
                        _wireId, _wirePos, _truth, round _drift];
                };
            };
        };
    };

    // ---------------------------------------------------------------- the client leg
    // The half only a person can answer for, and the half the corpus now runs.
    // The harness launches a headed client on the Windows host and stages
    // CTI_PROBE_CLIENT with the seconds this probe may wait for it to be swept
    // into a Commander slot; the probe then drives that client, which is as
    // close to a person as a machine gets.
    //
    // Every exit from here on names the leg and what became of it. `status=ran`
    // is claimed once, at the bottom, after the client has actually answered —
    // so nothing on the way out of this block can leave the verdict saying the
    // leg happened.
    private _waitFor = missionNamespace getVariable ["CTI_PROBE_CLIENT", 0];
    if (_waitFor <= 0) exitWith {
        diag_log "CTI|LEG name=human_commander_client status=unverified reason=run_sent_no_headed_client";
        diag_log "CTI|human_commander_probe_done";
    };

    // Which client the server swept into a slot, and the unit behind the UID it
    // latched. `client-port` had the same lookup (#86); the two refuse
    // differently, so the helper finds and this decides.
    ([_waitFor] call cti_probe_fnc_commanderSlot) params ["_commanded", "_uid", "_unit"];

    if (_commanded isEqualTo "") exitWith {
        diag_log "CTI|FAIL class=timeout human_commander_probe_no_client_assigned";
        diag_log "CTI|LEG name=human_commander_client status=unverified reason=no_person_in_a_commander_slot";
        diag_log "CTI|human_commander_probe_done";
    };

    if (isNull _unit) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed human_commander_probe_assigned_uid_absent uid=%1", _uid];
        diag_log "CTI|LEG name=human_commander_client status=unverified reason=assigned_uid_holds_no_unit";
        diag_log "CTI|human_commander_probe_done";
    };
    private _target = owner _unit;
    diag_log format ["CTI|human_commander_probe_commander side=%1 owner=%2 role=%3",
        _commanded, _target, roleDescription _unit];

    private _funded = (([createHashMapFromArray [
        ["id", "human-commander-probe-client-before"],
        ["verb", "view"],
        ["payload", createHashMapFromArray [["side", _commanded]]]
    ]] call cti_probe_fnc_rpc) getOrDefault ["result", createHashMap]) getOrDefault ["funds", -1];

    // Driving the client rather than standing in for it: the Command is built on
    // the client, by the client's own UI path, and crosses the network through
    // the mode=1 whitelist. Server-to-client remoteExec is unrestricted, which
    // is what lets the probe press the key nobody is there to press. The report
    // comes back on a public variable rather than a second remoteExec, because
    // the whitelist is the thing under test and a probe that widened it would be
    // testing a mission that does not ship.
    {
        [] spawn {
            // The push loop runs on its own cadence, so the view may be one
            // interval behind the assignment that triggered it.
            private _by = diag_tickTime + 30;
            waitUntil { !isNil "cti_uiSide" || { diag_tickTime > _by } };

            cti_probeReport = [
                missionNamespace getVariable ["cti_uiSide", ""],
                (missionNamespace getVariable ["cti_view", createHashMap]) getOrDefault ["funds", -1],
                count ((missionNamespace getVariable ["cti_view", createHashMap])
                    getOrDefault ["squads", []]),
                !isNil "cti_uiStarted"
            ];
            publicVariable "cti_probeReport";

            [["purchase", [["squad_type", "rifle"]]] call cti_fnc_command]
                remoteExec ["cti_fnc_portGateway", 2];

            // ---- #174: the map picture --------------------------------------
            // Playtest 0001's three presentation defects, asserted on the one
            // machine in the corpus that draws a Commander's map. Each entry is
            // [check, held, detail]; the server logs the verdicts, because the
            // harness reads the server's log. Staged and read inside one
            // unscheduled block (isNil) so the 5 s view push cannot repaint the
            // picture between a render and the read that judges it.
            private _results = [];
            isNil {
                private _real = missionNamespace getVariable ["cti_view", createHashMap];
                private _town = ((missionNamespace getVariable ["cti_map", createHashMap])
                    getOrDefault ["objectives", []]) param [0, createHashMap];
                private _townId = _town getOrDefault ["id", ""];
                (_town getOrDefault ["position", [0, 0]]) params ["_east", "_north"];
                private _townAt = [_east, _north, 0];

                // The real click path minus only the engine's event dispatch:
                // a click that resolves to a Place selects it.
                [[_east, _north]] call cti_fnc_mapSelect;
                _results pushBack ["selection_resolves", cti_uiPlace isEqualTo _townId,
                    format ["picked=%1 expected=%2", cti_uiPlace, _townId]];

                // The collision playtest 0001 photographed, restaged: a Squad
                // and a Contact at the selected Place, through the same
                // variable the push writes, rendered by the real renderer. The
                // first Squad is down three men so its strength text can only
                // read n over establishment if the denominator is real; the
                // second stands at the same Place so stacking is observable.
                private _staged = createHashMapFromArray [
                    // Through getVariable rather than bare, so a client whose
                    // UI never came up fails the checks below in words instead
                    // of killing this spawn on a nil access.
                    ["side", missionNamespace getVariable ["cti_uiSide", ""]],
                    ["funds", 0],
                    ["owners", createHashMap],
                    ["hq", createHashMap],
                    ["squads", [
                        createHashMapFromArray [["id", "probe-map-a"], ["type", "rifle"],
                            ["size", 5], ["order", "defend"], ["place", _townId], ["at", _townId]],
                        createHashMapFromArray [["id", "probe-map-b"], ["type", "rifle"],
                            ["size", 8], ["order", "reserve"], ["place", ""], ["at", _townId]]
                    ]],
                    ["contacts", [
                        createHashMapFromArray [["at", _townId], ["echelon", "team"],
                            ["posture", "foot"], ["assets", []], ["age", 30]]
                    ]]
                ];
                missionNamespace setVariable ["cti_view", _staged];
                [] call cti_fnc_mapRender;

                // The staging took effect (#80's sibling): every marker the
                // claims below are about exists, or the claims are vacuous.
                private _contactName = format ["cti_ui_contact_%1", _townId];
                private _squadKind = markerType "cti_ui_squad_probe-map-a";
                private _contactKind = markerType _contactName;
                private _selectionKind = markerType "cti_ui_place";
                _results pushBack ["staged_markers_drawn",
                    _squadKind isNotEqualTo "" && { _contactKind isNotEqualTo "" }
                        && { markerType "cti_ui_squad_probe-map-b" isNotEqualTo "" }
                        && { _selectionKind isNotEqualTo "" },
                    format ["squad=%1 contact=%2 selection=%3", _squadKind, _contactKind,
                        _selectionKind]];

                // 1. The selection marker sits at the Place the click named and
                // is its own kind of marker, not a Squad's or a Contact's.
                private _selectionAt = getMarkerPos "cti_ui_place";
                _results pushBack ["selection_at_the_place",
                    _selectionAt distance2D _townAt < 1,
                    format ["marker=%1 place=%2", _selectionAt, _townAt]];
                _results pushBack ["selection_distinct",
                    _selectionKind isNotEqualTo _squadKind
                        && { _selectionKind isNotEqualTo _contactKind },
                    format ["selection=%1 squad=%2 contact=%3", _selectionKind, _squadKind,
                        _contactKind]];

                // 2. Nothing with text draws at the town centre, which is where
                // the engine prints its own label, and the two kinds do not
                // draw at the same point as each other — or as each other's
                // stackmates.
                private _squadA = getMarkerPos "cti_ui_squad_probe-map-a";
                private _squadB = getMarkerPos "cti_ui_squad_probe-map-b";
                private _contactAt = getMarkerPos _contactName;
                _results pushBack ["text_off_the_engine_label",
                    _squadA distance2D _townAt > 25 && { _contactAt distance2D _townAt > 25 },
                    format ["squad=%1 contact=%2 label=%3", _squadA, _contactAt, _townAt]];
                _results pushBack ["kinds_separated",
                    _squadA distance2D _contactAt > 25,
                    format ["squad=%1 contact=%2", _squadA, _contactAt]];
                _results pushBack ["squads_stacked",
                    _squadA distance2D _squadB > 25,
                    format ["first=%1 second=%2", _squadA, _squadB]];

                // 3. Strength carries a denominator, and the denominator is the
                // establishment the catalogue sells — read from the same schema
                // the renderer reads, not written down here again (#159).
                private _establishment = (((call cti_fnc_commandSchema)
                    getOrDefault ["squads", createHashMap])
                    getOrDefault ["rifle", createHashMap]) getOrDefault ["size", -1];
                private _text = markerText "cti_ui_squad_probe-map-a";
                _results pushBack ["strength_has_a_denominator",
                    _text find (format ["%1/%2", 5, _establishment]) > -1,
                    format ["text=%1 establishment=%2", _text, _establishment]];

                // A click on open country selects nothing on purpose
                // (cti_fnc_placeOf without the fallback), and the marker goes
                // with the selection.
                [[10, 10]] call cti_fnc_mapSelect;
                _results pushBack ["selection_cleared",
                    cti_uiPlace isEqualTo "" && { markerType "cti_ui_place" isEqualTo "" },
                    format ["place=%1 marker=%2", cti_uiPlace, markerType "cti_ui_place"]];

                // The picture handed back to the session as it was found.
                missionNamespace setVariable ["cti_view", _real];
                [] call cti_fnc_mapRender;
            };
            cti_probeMap = _results;
            publicVariable "cti_probeMap";

            // ---- #175: a Squad on the march is on the map -------------------
            // Playtest 0001's other presentation defect, and the one it could
            // not tell from a death: a Squad standing in no Place was drawn
            // nowhere. Staged and read in one unscheduled block for the reason
            // the block above is, and each Squad is put somewhere no Place is,
            // so "drawn at the Squad" and "drawn at a Place" cannot be confused
            // for one another by a marker landing near both.
            private _march = [];
            isNil {
                private _real = missionNamespace getVariable ["cti_view", createHashMap];
                private _town = ((missionNamespace getVariable ["cti_map", createHashMap])
                    getOrDefault ["objectives", []]) param [0, createHashMap];
                private _townId = _town getOrDefault ["id", ""];
                (_town getOrDefault ["position", [0, 0]]) params ["_east", "_north"];
                private _townAt = [_east, _north, 0];

                // The field's name is the daemon's declaration rather than a
                // literal this probe and the renderer happen to agree on: a
                // rename that never reached the export would leave the map
                // reading nothing, silently, which is #163's whole finding. The
                // shipped PBO is what answers here.
                private _declared = (((call cti_fnc_commandSchema)
                    getOrDefault ["observation", createHashMap])
                    getOrDefault ["squad", []]);
                _march pushBack ["position_is_an_exported_field", "pos" in _declared,
                    format ["declared=%1", _declared]];

                // Far enough out that nothing can be mistaken for the town:
                // a marching Squad 1,500 m east of it, and a second Squad
                // standing *in* the town on the wire but 800 m away in fact.
                private _marching = [_east + 1500, _north, 0];
                private _misplaced = [_east + 800, _north, 0];
                missionNamespace setVariable ["cti_view", createHashMapFromArray [
                    ["side", missionNamespace getVariable ["cti_uiSide", ""]],
                    ["funds", 0],
                    ["owners", createHashMap],
                    ["hq", createHashMap],
                    ["contacts", []],
                    ["squads", [
                        // In no Place at all — the case that used to draw nothing.
                        createHashMapFromArray [["id", "probe-march-a"], ["type", "rifle"],
                            ["size", 8], ["order", "capture"], ["place", _townId], ["at", ""],
                            ["pos", [_east + 1500, _north]]],
                        // In a Place on the wire, and elsewhere in fact.
                        createHashMapFromArray [["id", "probe-march-b"], ["type", "rifle"],
                            ["size", 8], ["order", "defend"], ["place", _townId], ["at", _townId],
                            ["pos", [_east + 800, _north]]],
                        // Bought and not yet reported standing: no position at
                        // all, which is the one case that still falls back to
                        // the Place, exactly as the map drew before #175.
                        createHashMapFromArray [["id", "probe-march-c"], ["type", "rifle"],
                            ["size", 8], ["order", "defend"], ["place", _townId], ["at", _townId],
                            ["pos", []]]
                    ]]
                ]];
                [] call cti_fnc_mapRender;

                // The staging took effect (#80's sibling): the three markers the
                // claims below are about exist, or the claims are vacuous.
                private _kinds = ["probe-march-a", "probe-march-b", "probe-march-c"]
                    apply { markerType (format ["cti_ui_squad_%1", _x]) };
                _march pushBack ["staged_markers_drawn", !("" in _kinds),
                    format ["kinds=%1", _kinds]];

                // 1. The defect itself: a Squad in no Place is on the map, and
                // it is on the map where it actually is.
                private _drawnA = getMarkerPos "cti_ui_squad_probe-march-a";
                // 300 m of slack rather than nothing: the renderer pulls a
                // Squad's marker clear of the engine's town label, and a Squad
                // sharing a Place with another stacks a step further again
                // (#174) — both are placeholder distances of about a hundred
                // metres, and neither is what these checks are about. The gaps
                // being discriminated are 800 m and 1,500 m.
                _march pushBack ["marching_squad_is_drawn",
                    _drawnA distance2D _marching < 300,
                    format ["marker=%1 squad=%2", _drawnA, _marching]];
                _march pushBack ["marching_squad_is_not_at_a_place",
                    _drawnA distance2D _townAt > 1000,
                    format ["marker=%1 town=%2", _drawnA, _townAt]];

                // 2. Where the two answers disagree, the position wins: `at` is
                // what an Order names, `pos` is what a marker is drawn at.
                private _drawnB = getMarkerPos "cti_ui_squad_probe-march-b";
                _march pushBack ["position_beats_the_place",
                    _drawnB distance2D _misplaced < 300
                        && { _drawnB distance2D _townAt > 500 },
                    format ["marker=%1 squad=%2 town=%3", _drawnB, _misplaced, _townAt]];

                // 3. And a Squad the world has not reported yet is drawn at its
                // Place rather than at the map origin — an empty position is
                // silence, never a coordinate.
                private _drawnC = getMarkerPos "cti_ui_squad_probe-march-c";
                _march pushBack ["unreported_squad_falls_back_to_its_place",
                    _drawnC distance2D _townAt < 300,
                    format ["marker=%1 town=%2", _drawnC, _townAt]];

                missionNamespace setVariable ["cti_view", _real];
                [] call cti_fnc_mapRender;
            };
            cti_probeMarch = _march;
            publicVariable "cti_probeMarch";

            // ---- #176: the event channel ------------------------------------
            // Playtest 0001's summary judgement, asserted on the machine whose
            // silence it was about: ground changing hands and a Squad reaching
            // zero raise a notification on the Commander's client. Every push
            // below goes through cti_fnc_mapObservation — the real door, the
            // real diff, the real presenter — and the whole run is one
            // unscheduled block for #174's reason: the 5 s push cannot
            // interleave, so every count delta is this block's own doing. The
            // client-side facts asserted are cti_fnc_notify's own record: what
            // it told the Commander, and `queued` — BIS_fnc_showNotification's
            // return, the engine's notification system accepting the event —
            // which draws with or without the map open by construction.
            private _notices = [];
            isNil {
                private _real = missionNamespace getVariable ["cti_view", createHashMap];
                private _side = missionNamespace getVariable ["cti_uiSide", ""];
                private _townId = (((missionNamespace getVariable ["cti_map", createHashMap])
                    getOrDefault ["objectives", []]) param [0, createHashMap])
                    getOrDefault ["id", ""];

                // A served view in miniature: one town with an owner, and the
                // Squads the step stages. Fresh hashmaps per push, because the
                // door diffs the arriving picture against the object it kept.
                private _staged = {
                    params ["_owner", "_squads"];
                    createHashMapFromArray [
                        ["side", _side], ["funds", 0],
                        ["owners", createHashMapFromArray [[_townId, _owner]]],
                        ["hq", createHashMap],
                        ["squads", _squads], ["contacts", []]]
                };
                private _squadAt = {
                    params ["_size"];
                    [createHashMapFromArray [["id", "probe-n-1"], ["type", "rifle"],
                        ["size", _size], ["order", "reserve"], ["place", ""], ["at", ""]]]
                };
                private _countNow = { missionNamespace getVariable ["cti_notificationCount", 0] };
                private _lastOf = { missionNamespace getVariable ["cti_lastNotification", createHashMap] };

                // The baseline every delta below is measured from. Its own
                // arrival may notify — the real picture differs from it, and
                // the mechanism honestly says so — which is why the count is
                // read after it rather than assumed zero.
                [["WEST", [8] call _squadAt] call _staged] call cti_fnc_mapObservation;
                private _from = call _countNow;

                // Ground changing hands, named and with the new owner.
                [["EAST", [8] call _squadAt] call _staged] call cti_fnc_mapObservation;
                private _last = call _lastOf;
                _notices pushBack ["ground_lost_notifies",
                    (call _countNow) isEqualTo (_from + 1)
                        && { (_last getOrDefault ["event", ""]) isEqualTo "place_taken" }
                        && { (_last getOrDefault ["place", ""]) isEqualTo _townId }
                        && { (_last getOrDefault ["owner", ""]) isEqualTo "EAST" }
                        && { _last getOrDefault ["queued", false] },
                    format ["count=%1 from=%2 last=%3", call _countNow, _from, _last]];

                // Either way means both ways: the same town coming back.
                [["WEST", [8] call _squadAt] call _staged] call cti_fnc_mapObservation;
                _last = call _lastOf;
                _notices pushBack ["ground_taken_notifies",
                    (call _countNow) isEqualTo (_from + 2)
                        && { (_last getOrDefault ["event", ""]) isEqualTo "place_taken" }
                        && { (_last getOrDefault ["owner", ""]) isEqualTo "WEST" }
                        && { _last getOrDefault ["queued", false] },
                    format ["count=%1 from=%2 last=%3", call _countNow, _from, _last]];

                // A Squad reaching zero, in the issue's own words: still on the
                // wire at size 0, the shape the world can report for one cycle
                // before the roster drops it.
                [["WEST", [0] call _squadAt] call _staged] call cti_fnc_mapObservation;
                _last = call _lastOf;
                _notices pushBack ["squad_wipe_notifies",
                    (call _countNow) isEqualTo (_from + 3)
                        && { (_last getOrDefault ["event", ""]) isEqualTo "squad_wiped" }
                        && { (_last getOrDefault ["squad", ""]) isEqualTo "probe-n-1" }
                        && { _last getOrDefault ["queued", false] },
                    format ["count=%1 from=%2 last=%3", call _countNow, _from, _last]];

                // Gone from the wire the next push, as Roster.reconcile makes
                // it: the same wipe must not announce itself twice.
                [["WEST", []] call _staged] call cti_fnc_mapObservation;
                _notices pushBack ["wipe_notifies_once",
                    (call _countNow) isEqualTo (_from + 3),
                    format ["count=%1 from=%2", call _countNow, _from]];

                // An unchanged picture raises nothing: the push repeats every
                // 5 s, and events re-announced as state would be spam.
                [["WEST", []] call _staged] call cti_fnc_mapObservation;
                _notices pushBack ["steady_picture_is_silent",
                    (call _countNow) isEqualTo (_from + 3),
                    format ["count=%1 from=%2", call _countNow, _from]];

                // Handed back as found — directly, not through the door, so the
                // restore is not itself an event and the next real push diffs
                // the real picture against the real picture.
                missionNamespace setVariable ["cti_view", _real];
                [] call cti_fnc_mapRender;
            };
            cti_probeNotices = _notices;
            publicVariable "cti_probeNotices";
        };
    } remoteExec ["call", _target];

    // The judgement is what the daemon did with it, read where the daemon keeps
    // it rather than off a log line: the Command was accepted for the side the
    // *server* stamped, which is the whole of attribution.
    private _spentBy = diag_tickTime + 60;
    private _now = _funded;
    waitUntil {
        _now = (([createHashMapFromArray [
            ["id", format ["human-commander-probe-client-poll-%1", round diag_tickTime]],
            ["verb", "view"],
            ["payload", createHashMapFromArray [["side", _commanded]]]
        ]] call cti_probe_fnc_rpc) getOrDefault ["result", createHashMap]) getOrDefault ["funds", -1];
        _now isNotEqualTo _funded || { diag_tickTime > _spentBy }
    };

    if (_now isEqualTo _funded) then {
        diag_log format ["CTI|FAIL class=assertion_failed human_commander_probe_client_command_lost side=%1 funds=%2",
            _commanded, _funded];
    } else {
        diag_log format ["CTI|human_commander_probe_client_command side=%1 funds=%2->%3",
            _commanded, _funded, _now];
    };

    private _reportBy = diag_tickTime + 30;
    waitUntil { !isNil "cti_probeReport" || { diag_tickTime > _reportBy } };
    if (isNil "cti_probeReport") then {
        diag_log "CTI|FAIL class=assertion_failed human_commander_probe_client_silent";
    } else {
        cti_probeReport params ["_clientSide", "_clientFunds", "_clientSquads", "_clientUI"];
        diag_log format ["CTI|human_commander_probe_client_view side=%1 funds=%2 squads=%3 ui=%4",
            _clientSide, _clientFunds, _clientSquads, _clientUI];
        if (_clientSide isNotEqualTo _commanded) then {
            diag_log format ["CTI|FAIL class=assertion_failed human_commander_probe_client_no_view side=%1 expected=%2",
                _clientSide, _commanded];
        };
        if !(_clientUI) then {
            diag_log "CTI|FAIL class=assertion_failed human_commander_probe_client_ui_not_started";
        };
    };

    // The #174 map-picture verdicts, made on the client that draws the picture
    // and judged here because the harness reads the server's log. A client that
    // reported above but never sent these is a half-run leg, and silence would
    // otherwise read as green.
    private _mapBy = diag_tickTime + 30;
    waitUntil { !isNil "cti_probeMap" || { diag_tickTime > _mapBy } };
    if (isNil "cti_probeMap") then {
        diag_log "CTI|FAIL class=assertion_failed human_commander_probe_map_silent";
    } else {
        {
            _x params ["_check", "_held", "_detail"];
            if (_held) then {
                diag_log format ["CTI|human_commander_probe_map check=%1 %2", _check, _detail];
            } else {
                diag_log format ["CTI|FAIL class=assertion_failed human_commander_probe_map_%1 %2",
                    _check, _detail];
            };
        } forEach cti_probeMap;
    };

    // The #175 marching-Squad verdicts, made on the client that draws the
    // picture and judged here for the same reason the map's are.
    private _marchBy = diag_tickTime + 30;
    waitUntil { !isNil "cti_probeMarch" || { diag_tickTime > _marchBy } };
    if (isNil "cti_probeMarch") then {
        diag_log "CTI|FAIL class=assertion_failed human_commander_probe_march_silent";
    } else {
        {
            _x params ["_check", "_held", "_detail"];
            if (_held) then {
                diag_log format ["CTI|human_commander_probe_march check=%1 %2", _check, _detail];
            } else {
                diag_log format ["CTI|FAIL class=assertion_failed human_commander_probe_march_%1 %2",
                    _check, _detail];
            };
        } forEach cti_probeMarch;
    };

    // The #176 notification verdicts, made on the client the notifications
    // fired on and judged here for the same reason the map's are: the harness
    // reads the server's log, and a client that fell silent after the map
    // checks would otherwise read as green.
    private _noticeBy = diag_tickTime + 30;
    waitUntil { !isNil "cti_probeNotices" || { diag_tickTime > _noticeBy } };
    if (isNil "cti_probeNotices") then {
        diag_log "CTI|FAIL class=assertion_failed human_commander_probe_notices_silent";
    } else {
        {
            _x params ["_check", "_held", "_detail"];
            if (_held) then {
                diag_log format ["CTI|human_commander_probe_notify check=%1 %2", _check, _detail];
            } else {
                diag_log format ["CTI|FAIL class=assertion_failed human_commander_probe_notify_%1 %2",
                    _check, _detail];
            };
        } forEach cti_probeNotices;
    };

    diag_log "CTI|LEG name=human_commander_client status=ran";
    diag_log "CTI|human_commander_probe_done";
};
