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
//   - **His body is out of the world while he flies, and back when he lands**
//     (#190). #178 left that flag open deliberately and the human ruled on it
//     on 2026-08-04: hide the body and stop simulating it for the duration of
//     the flight, restore both on the way out, where the body was left. Neither
//     of the two alternatives — a killable body is the cost of the
//     BIS_fnc_camera workaround this replaces, and an invulnerable visible one
//     is an unkillable target the AI can perceive and engage, a worse
//     divergence from the Campaign than an absent one.
//
// ## The body: two commands, two machines, and the engine chooses both
//
//   - `hideObjectGlobal` is `serverExec= server` with global effect
//     (commands/hideObjectGlobal.wiki), so hiding the body on every machine at
//     once is the server's to do and this sweep's half of the work.
//   - `enableSimulationGlobal` takes a **local argument on a client** since
//     Arma 3 2.06 (commands/enableSimulationGlobal.wiki), and a human's own
//     unit is local to that human's own machine. So the client stops
//     simulating it itself, on the turn it sees the camera, rather than a sweep
//     later. The direction that matters is the way out: a body unfrozen five
//     seconds after its player left the camera is five seconds of a Commander
//     who cannot move, and the sweep cannot be the thing that ends that.
//
// So the split has a visible seam, and it is the harmless one: for up to one
// sweep turn after the camera opens, a body that is already frozen and already
// out of the AI's reckoning is still drawn on any *other* human's screen. The
// asymmetry is deliberate. Nothing acts on what is drawn, and the half that
// something acts on — his own control of his own body — is never behind a
// sweep in either direction.
//
// Simulation off is the half the AI reads. A unit subjected to it "may stay
// unrecognised for a long time even after simulation was re-enabled, returning
// objNull as cursorTarget" (commands/enableSimulation.wiki), which is the
// engine saying it has left the reckoning; hiding is what takes it off the
// other Commander's screen, and disables its collision besides. What survives,
// stated because the ruling chose it: the body can still take damage
// (enableSimulation's own description), so a shell already in the air is not
// waved away. The ruling rejected invulnerability; this is its residue.
//
// ## Why a client-side watcher, and how it gets there
//
// There is no server-side signal that a curator camera is up. `curatorCamera`
// "is local to the curator owner" (topics/Arma_3_Curator.wiki) and every
// curator command the server can ask reports *assignment*, which is a fact
// about the whole session rather than about this moment. So the watcher runs on
// the human's own machine, pushed there by this sweep — the harness is compiled
// by initServer.sqf and runs nowhere else — and reports back by broadcasting
// one variable on the unit itself (`setVariable [..., true]`, global effect,
// commands/setVariable.wiki). The server hides on that and polls nothing.
//
// The push is `remoteExec ["spawn", _unit]`. The wiki cautions against
// remote-executing `spawn` "to prevent issues in cases where the remote
// execution of call or spawn is blocked by CfgRemoteExec"
// (commands/remoteExec.wiki) — it is not blocked here and cannot be, because
// those rules "only apply to clients. The server is not subject to any
// limitations" (topics/Arma_3_CfgRemoteExec.wiki), the same fact ADR-0041 leans
// on for cti_fnc_portReply. The alternative the wiki recommends, a named
// function to remote-execute, would be a function in the addon, and the addon
// is what every probe boots: #178's boundary is why this file exists at all.
// `_unit` as the target names the one machine where that unit is local, so the
// call site decides the machine and ADR-0041 asks for no locality guard on the
// far side. Whether the push landed is not assumed either — the watcher's first
// turn broadcasts its state unconditionally, and a curator whose read-back
// never arrives is said out loud as `body_watch_silent`.
//
// Detection is `findDisplay 312`, the Zeus display (commands/findDisplay.wiki's
// own list of common IDDs; `IDD_RSCDISPLAYCURATOR 312` in
// topics/Arma_3_IDD_List.wiki), polled once a second so that both edges are
// found the same way — the interface opens on a keypress and closes on one, and
// nothing the engine offers reports either to script. The two corroborating
// signals ride every transition line rather than the choice of detector being a
// matter of belief, and the first in-world flight has now answered them
// (`~/.arma-cti/runs/20260804T234450Z-issue-190-observer-body`):
//
//   - `curator_camera` tracks the display exactly — false on both grounded
//     lines, true on the flying one. Either would serve as the detector.
//   - `camera_on_it` never became true, in flight or out of it. So `cameraOn`
//     is *not* the curator camera even while the curator camera is what the
//     player is looking through, and the obvious-sounding test
//     `cameraOn isEqualTo curatorCamera` would have hidden nobody's body ever.
//     The field stays in the line as the record of that.
//
// The one thing the human has to know if the watcher ever dies mid-flight: his
// body stays frozen, and `player enableSimulationGlobal true` in the debug
// console (`enableDebugConsole = 1` in this mission) hands it back. Not
// automated, because the automation would be a heartbeat guarding a ten-line
// loop of engine calls, and a session's worth of network chatter to guard it.
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

        // Runs on the human's machine, not this one. Compiled here and carried
        // there by the push below, so it closes over nothing: SQF code is
        // source, and everything it names is either global or its own.
        private _bodyWatch = {
            if (isNil "cti_playtest_observer_body") then {
                cti_playtest_observer_body = true;

                if (isNil "cti_fnc_everyInterval") then {
                    diag_log "CTI|playtest_observer_unavailable reason=addon_functions_unresolved machine=client";
                } else {
                    // A second, rather than this sweep's five: this is the loop
                    // that decides how long a Commander stands still after he
                    // stops flying.
                    ["playtest_observer_body", 1, [createHashMap], {
                        params ["_seen"];

                        private _unit = player;
                        if (!isNull _unit) then {
                            private _flying = !isNull (findDisplay 312);
                            // "unset" rather than false, so the first turn is a
                            // transition too and the server hears from the
                            // watcher before it has anything to report.
                            if (_flying isNotEqualTo (_seen getOrDefault ["flying", "unset"])
                                || { _unit isNotEqualTo (_seen getOrDefault ["unit", objNull]) }) then {
                                _seen set ["flying", _flying];
                                _seen set ["unit", _unit];

                                _unit enableSimulationGlobal !_flying;
                                _unit setVariable ["cti_playtest_observerBody", _flying, true];

                                diag_log format [
                                    "CTI|playtest_observer_body_%1 uid=%2 simulation=%3 curator_camera=%4 camera_on_it=%5",
                                    ["grounded", "flying"] select _flying, getPlayerUID _unit,
                                    simulationEnabled _unit, !isNull curatorCamera,
                                    cameraOn isEqualTo curatorCamera];
                            };
                        };
                    }, true] call cti_fnc_everyInterval;

                    diag_log "CTI|playtest_observer_body_watching interval=1";
                };
            };
        };

        ["playtest_observer", 5, [createHashMap, createHashMap, _disabled, createHashMap, _bodyWatch], {
            params ["_logics", "_ready", "_disabled", "_bodies", "_bodyWatch"];

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

                        // The body, for as long as its player is flying (#190).
                        // Kept per UID beside the curator and not inside the
                        // ready branch: a player who can be assigned a camera is
                        // a player who can be in one, and the watcher is what
                        // decides which — this only hides what it is told has
                        // gone. Two fields: the unit the watcher was pushed onto,
                        // and the last thing said about it, so a state that has
                        // not changed is not said twice.
                        private _body = _bodies getOrDefault [_uid, []];
                        if (_body isEqualTo []) then {
                            _body = [objNull, ""];
                            _bodies set [_uid, _body];
                        };

                        if ((_body # 0) isNotEqualTo _unit) then {
                            // A respawn hands the player a new unit, and the
                            // watcher follows `player` rather than the body it
                            // started on — so this is the push and the re-push
                            // both, and the latch on the far side makes the
                            // second one inert.
                            _body set [0, _unit];
                            _body set [1, "pushed"];
                            [[], _bodyWatch] remoteExec ["spawn", _unit];
                            diag_log format [
                                "CTI|playtest_observer_body_pushed uid=%1 name=%2", _uid, name _unit];
                        } else {
                            // The sentinel rather than a nil, so "the watcher has
                            // not spoken" is a value this can compare instead of
                            // a question about scope.
                            private _flying = _unit getVariable
                                ["cti_playtest_observerBody", "unset"];
                            if (_flying isEqualTo "unset") then {
                                if ((_body # 1) isNotEqualTo "silent") then {
                                    _body set [1, "silent"];
                                    diag_log format [
                                        "CTI|playtest_observer_unavailable reason=body_watch_silent uid=%1",
                                        _uid];
                                };
                            } else {
                                private _word = ["grounded", "flying"] select _flying;
                                if ((_body # 1) isNotEqualTo _word) then {
                                    _body set [1, _word];
                                    _unit hideObjectGlobal _flying;
                                    // Read back out of the world rather than
                                    // reported from the intent (#80): both halves
                                    // are commands the engine may decline, and
                                    // the client's half was issued on another
                                    // machine entirely.
                                    diag_log format [
                                        "CTI|playtest_observer_body uid=%1 state=%2 hidden=%3 simulation=%4",
                                        _uid, _word, isObjectHidden _unit, simulationEnabled _unit];
                                };
                            };
                        };
                    };
                };
            } forEach (allPlayers - entities "HeadlessClient_F");
        }, true] call cti_fnc_everyInterval;

        diag_log "CTI|playtest_observer_watching interval=5";
    };
};
