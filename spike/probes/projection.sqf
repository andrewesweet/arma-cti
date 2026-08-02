// probe: projection
// issues: 24, 27, 46
// window: 300
//
// #27 in-world probe: the server takes the public picture and still repaints.
// #24 rides on it: the presence sampler sees both sides in one radius.
//
// `just regress projection`, or by hand
// `just probe spike/probes/projection.sqf 300`. Appended to the generated
// harness at bring-up, never packed into the mission — the mission is the thing
// under test, and a probe that ships in it is one that ships.
//
// ---- why #24 is here rather than in a probe of its own
//
// #24's property is that `cti_fnc_presenceSample` distinguishes WEST from EAST
// inside one Objective's radius. Every in-world run before this one put WEST
// units on the ground and nothing else, so `str (side group _x)` yielding
// exactly `"EAST"` was assumed rather than observed — and the failure would be
// silent and expensive: an Objective held by OPFOR would read as empty, never
// contest, never change hands, and keep paying its owner while every unit test
// stayed green, because the rules are right and the world was never reporting
// the enemy. (`contacts` plants EAST men, but that probe is about
// `targetsQuery` and the Contact sampler; it never asks who is standing in a
// capture radius.)
//
// This probe already does the whole of the setup that property needs: it plants
// a man inside `agia_marina`'s radius and waits for the daemon's judgement to
// come back and repaint the marker. Asserting the other two owner states off
// the same plant costs a minute of window and no bring-up at all; a probe of
// its own would cost a world. The subject is also the same one — the picture
// the server is allowed to hold — which is what makes them one file rather than
// two things sharing a lift.
//
// ---- the window
//
// 150 → 300, added up from the deadlines rather than guessed at: ~20 s of
// bring-up, 20 s for the world to be ready, up to 90 s for the first capture,
// up to 45 s for Contested to be read back (`capture_seconds` does not apply to
// it — Contested is decided on the first report that sees both sides, so this
// is a report interval and a margin), and up to 90 s for EAST's own capture,
// which does have to hold its 30 s. That is 265 s of worst case against a run
// that measured 48 s before this and should measure around 130 s after it: the
// deadlines are per-leg refusals, and the window only has to be wider than all
// of them together.
[] spawn {
    private _extension = call cti_fnc_shimName;
    if (_extension isEqualTo "") exitWith {
        diag_log "CTI|FAIL class=infra_unavailable projection_probe_no_shim";
    };

    // The world built and both server loops turned once. #46 replaced the fixed
    // 20 s settle this used to be with a wait on those three conditions, keeping
    // the 20 s as the deadline: a ready world is asked sooner, an unready one is
    // asked at the same moment and fails the same way.
    [20] call cti_probe_fnc_worldReady;

    // Ground a side holds is the thing the reply has to keep carrying. Spawned
    // here rather than bought and walked: what is under test is the marker path,
    // not the Order path, and agia_marina is 2 km from the NATO base.
    private _map = missionNamespace getVariable ["cti_map", createHashMap];
    private _objective = ((_map getOrDefault ["objectives", []]) select {
        (_x get "id") isEqualTo "agia_marina"
    }) # 0;
    (_objective get "position") params ["_easting", "_northing"];
    private _group = createGroup west;
    private _unit = _group createUnit ["B_Soldier_F", [_easting, _northing, 0], [], 0, "NONE"];
    // Told not to fight and not to wander, because an OPFOR man joins him in the
    // same radius below. Two riflemen at twenty metres in daylight settle it
    // between them in seconds, and a head count that a firefight can change is
    // not a head count the assertions can be made of — `contacts.sqf`'s rule,
    // applied where presence rather than knowledge is the subject. Nothing about
    // the capture is disabled: the sampler asks only whether a man is alive and
    // whose side his group is, and the daemon still has to read him standing
    // there.
    _unit disableAI "PATH";
    _group setCombatMode "BLUE";
    _unit allowDamage false;
    diag_log format ["CTI|projection_probe_planted at=%1 alive=%2",
        mapGridPosition _unit, alive _unit];

    // capture_seconds is 30 and reports run every 5, so a minute is generous.
    private _deadline = diag_tickTime + 90;
    waitUntil {
        private _owners = missionNamespace getVariable ["cti_objectiveOwner", createHashMap];
        (_owners getOrDefault ["agia_marina", ""]) isEqualTo "WEST"
            || { diag_tickTime > _deadline }
    };
    private _owner = (missionNamespace getVariable ["cti_objectiveOwner", createHashMap])
        getOrDefault ["agia_marina", ""];
    if !(_owner isEqualTo "WEST") exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed projection_probe_marker_stuck owner=%1", _owner];
    };
    diag_log "CTI|projection_probe_repainted objective=agia_marina owner=WEST";

    // And what the reply actually carried. Read here rather than inferred from
    // the marker: absence is the claim, and only the raw document can show it.
    private _envelope = createHashMapFromArray [
        ["id", "projection-probe"],
        ["verb", "observe"],
        ["payload", createHashMapFromArray [
            ["time", time],
            ["presence", call cti_fnc_presenceSample]
        ]]
    ];
    private _raw = (_extension callExtension ["rpc_keepalive", [toJSON _envelope]]) # 0;
    private _reply = fromJSON _raw;
    if !(_reply isEqualType createHashMap) exitWith {
        diag_log format ["CTI|FAIL class=oracle_disagreement projection_probe_unreadable=%1", _raw];
    };

    private _result = _reply getOrDefault ["result", createHashMap];
    private _keys = keys _result;
    diag_log format ["CTI|projection_probe_reply keys=%1 bytes=%2", _keys, count _raw];
    private _private = _keys select { _x in ["side", "funds", "squads", "paid", "lost"] };
    if (count _private > 0) then {
        diag_log format ["CTI|FAIL class=assertion_failed projection_probe_private_keys=%1", _private];
    };
    if !("owners" in _keys) then {
        diag_log "CTI|FAIL class=assertion_failed projection_probe_no_owners";
    };

    // ------------------------------------------------ both sides in one radius (#24)
    // An OPFOR rifleman twenty metres from the NATO one, well inside
    // agia_marina's 200 m radius. Spawned rather than bought for the reason
    // `contacts.sqf` gives: EAST's Base is 4.4 km away and the purchase path is
    // not what is under test here.
    private _opforGroup = createGroup [east, true];
    private _opfor = _opforGroup createUnit
        ["O_Soldier_F", [_easting + 20, _northing + 20, 0], [], 0, "NONE"];
    if (isNull _opfor) exitWith {
        diag_log "CTI|FAIL class=assertion_failed projection_probe_no_opfor";
    };
    _opfor disableAI "PATH";
    _opforGroup setCombatMode "BLUE";
    _opfor allowDamage false;
    diag_log format ["CTI|projection_probe_planted side=EAST at=%1 group_side=%2 alive=%3",
        mapGridPosition _opfor, str (side group _opfor), alive _opfor];

    // Contested is decided on the first report that sees both sides — there is
    // no hold to serve — so this is a report interval with a margin on it, not a
    // capture.
    private _owned = {
        params ["_want"];
        ((missionNamespace getVariable ["cti_objectiveOwner", createHashMap])
            getOrDefault ["agia_marina", ""]) isEqualTo _want
    };
    _deadline = diag_tickTime + 45;
    waitUntil { ["CONTESTED"] call _owned || { diag_tickTime > _deadline } };
    if !(["CONTESTED"] call _owned) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed projection_probe_not_contested owner=%1 sampled=%2",
            (missionNamespace getVariable ["cti_objectiveOwner", createHashMap])
                getOrDefault ["agia_marina", ""],
            (call cti_fnc_presenceSample) getOrDefault ["agia_marina", []]];
    };
    diag_log format ["CTI|projection_probe_contested objective=agia_marina sampled=%1 colour=%2",
        (call cti_fnc_presenceSample) getOrDefault ["agia_marina", []],
        getMarkerColor "cti_objective_agia_marina"];

    // Contested proves both sides were *seen* in one radius. That EAST is also
    // *classified* — that `str (side group _x)` yields exactly the string the
    // daemon's rules are written against — is only proven by EAST taking the
    // ground on its own: a side the sampler named anything else would leave the
    // radius reading as empty, and ground already taken stays taken, so the
    // marker would sit on WEST forever rather than change hands.
    deleteVehicle _unit;
    deleteGroup _group;
    _deadline = diag_tickTime + 90;
    waitUntil { ["EAST"] call _owned || { diag_tickTime > _deadline } };
    if !(["EAST"] call _owned) exitWith {
        diag_log format ["CTI|FAIL class=assertion_failed projection_probe_east_never_captured owner=%1 sampled=%2",
            (missionNamespace getVariable ["cti_objectiveOwner", createHashMap])
                getOrDefault ["agia_marina", ""],
            (call cti_fnc_presenceSample) getOrDefault ["agia_marina", []]];
    };
    diag_log format ["CTI|projection_probe_east_captured objective=agia_marina colour=%1 at=%2",
        getMarkerColor "cti_objective_agia_marina", time];

    diag_log "CTI|projection_probe_done";
};
