// A Zeus-style observer for the human in a playtest session (#178, asked for
// verbatim in playtest 0001's response): fly about without triggering enemy
// AI, watch what the Squads are doing first-hand, and come back to the
// Commander's map — as a keybind rather than a typed incantation.
//
// Staged by spike/run.sh beside any fixture from spike/playtest/, because that
// directory is what marks a session as a human one (session-hold.sqf's own
// header). Deliberately **not** in spike/probes/ and never staged with a probe:
// the regression corpus must not boot a curator, both because #178 says so and
// because a Zeus standing beside a probe is a second author for every finding
// the probe makes. Runs on the server: initServer.sqf is what compiles the
// harness, and every curator command below is server-executed
// (docs/reference/arma-wiki/commands/assignCurator.wiki and kin).
//
// What the human gets, each engine fact from the vendored wiki:
//
//   - **Press Y to enter and leave observer mode**
//     (topics/Arma_3_Field_Manual_minus_Zeus.wiki: "Press Y to toggle the Zeus
//     interface"). Leaving puts him back in his own body, where the map key is
//     the Commander's map again — observing and commanding one keypress apart.
//   - **Entering spawns no unit and changes nothing the AI can perceive.** The
//     whole apparatus is one curator logic per human — a sideLogic entity,
//     outside every side `allUnits` covers (commands/allUnits.wiki) — and the
//     interface is a camera, local to its owner. The `units_alive` figures on
//     the log lines below are that claim read back out of the world rather
//     than remembered (#80's rule about staging the world can silently refuse).
//   - **A camera with no edit rights, which is #178's explicit default.** No
//     addon is unlocked (removeAllCuratorAddons, so the CREATE list is empty),
//     nothing in the world is made curator-editable, and all six curator
//     actions — place, edit, delete, destroy, group, synchronize — are set to
//     -1e10, below the -1e6 the engine documents as "considered as disabled
//     action" (commands/setCuratorCoef.wiki). The one power that remains is
//     map markers, which the engine keeps free for every curator
//     (topics/Arma_3_Curator.wiki: "Markers are always free") and which touch
//     nothing the AI can perceive; there is no curator surface that turns them
//     off, so the choice #178 asks be stated is: markers stay, everything else
//     is off.
//
// One logic per human, keyed by UID, because "Two players cannot act as one
// curator" (commands/assignCurator.wiki) — and kept assigned by sweep rather
// than latched once, because respawn hands the player a new unit and leaves
// the curator on the old body. The sweep also re-strips addons and re-pins
// coefficients every turn: a module created at runtime runs its own init on a
// later frame, and rather than trusting that ordering, drift is corrected and
// said out loud. The engine takes a frame or two to reflect an assignment
// (the wiki's note on getAssignedCuratorUnit), so `_assigning` and `_ready`
// are separate lines: the second is the read-back, and a session in which
// `playtest_observer_assigning` repeats without a `playtest_observer_ready` is
// a session whose observer never took.
//
// Says everything out loud and writes no FAIL line, deliberately: run.sh ends
// the hold window on the first FAIL it sees, and a session whose observer
// could not be staged is a degraded session for the human to play and report,
// not a void one. The exception is the sweep dying outright: it runs on
// cti_fnc_everyInterval, so cti_fnc_loopWatch reports that the way it reports
// any dead loop — typed, and loud.
if (isNil "cti_playtest_observer") then {
    cti_playtest_observer = true;

    if (isNil "cti_fnc_everyInterval") then {
        diag_log "CTI|playtest_observer_unavailable reason=addon_functions_unresolved";
    } else {
        private _disabled = ["place", "edit", "delete", "destroy", "group", "synchronize"];
        ["playtest_observer", 5, [createHashMap, createHashMap, _disabled], {
            params ["_logics", "_ready", "_disabled"];

            {
                private _unit = _x;
                private _uid = getPlayerUID _unit;
                if (alive _unit && { _uid isNotEqualTo "" }) then {
                    private _logic = _logics getOrDefault [_uid, objNull];
                    if (isNull _logic) then {
                        private _standing = count allUnits;
                        _logic = (createGroup sideLogic)
                            createUnit ["ModuleCurator_F", [0, 0, 0], [], 0, "NONE"];
                        if (isNull _logic) then {
                            diag_log format [
                                "CTI|playtest_observer_unavailable reason=logic_refused uid=%1",
                                _uid];
                        } else {
                            _logics set [_uid, _logic];
                            removeAllCuratorAddons _logic;
                            { _logic setCuratorCoef [_x, -1e10] } forEach _disabled;
                            diag_log format [
                                "CTI|playtest_observer_logic uid=%1 units_alive_before=%2 units_alive_after=%3",
                                _uid, _standing, count allUnits];
                        };
                    };
                    if (!isNull _logic) then {
                        if (count curatorAddons _logic > 0) then {
                            private _were = count curatorAddons _logic;
                            removeAllCuratorAddons _logic;
                            diag_log format [
                                "CTI|playtest_observer_restripped uid=%1 addons_were=%2",
                                _uid, _were];
                        };
                        {
                            if ((_logic curatorCoef _x) > -1e6) then {
                                _logic setCuratorCoef [_x, -1e10];
                                diag_log format [
                                    "CTI|playtest_observer_repinned uid=%1 action=%2",
                                    _uid, _x];
                            };
                        } forEach _disabled;

                        private _holder = getAssignedCuratorUnit _logic;
                        if (_holder isEqualTo _unit) then {
                            if !(_ready getOrDefault [_uid, false]) then {
                                _ready set [_uid, true];
                                diag_log format [
                                    "CTI|playtest_observer_ready uid=%1 name=%2 addons=%3 actions_disabled=%4 units_alive=%5",
                                    _uid, name _unit, count curatorAddons _logic,
                                    { (_logic curatorCoef _x) <= -1e6 } count _disabled,
                                    count allUnits];
                            };
                        } else {
                            unassignCurator _logic;
                            _unit assignCurator _logic;
                            _ready set [_uid, false];
                            diag_log format [
                                "CTI|playtest_observer_assigning uid=%1 name=%2",
                                _uid, name _unit];
                        };
                    };
                };
            } forEach (allPlayers - entities "HeadlessClient_F");
        }, true] call cti_fnc_everyInterval;

        diag_log "CTI|playtest_observer_watching interval=5";
    };
};
