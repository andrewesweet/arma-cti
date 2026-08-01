/*
 * Author: arma-cti
 * Brings the Commander's map UI up, once. Runs on the client.
 *
 * Crude on purpose (#18): this proves the path, not the presentation. Every
 * piece of it is a **playtest-tuned placeholder** in the sense ADR-0020 gives
 * the word — click a Place, press a number, read a hint — and Phase 4 replaces
 * the lot. What is not a placeholder is where the click ends up: a Command
 * built by cti_fnc_command and remoteExec'd to cti_fnc_portGateway, the one
 * door and the one wire format the AI planner uses (ADR-0012).
 *
 * No dialog, no config class, no resource: the whole surface is the map's own
 * click event, a key handler on the map display and a hint. That is what makes
 * it cheap to throw away, and it is also why nothing here can stall a frame —
 * a click builds a Command and hands it to remoteExec, which returns at once.
 * The judgement arrives later on its own, through cti_fnc_portReply.
 *
 * Idempotent: called on every Observation push, and does its work on the first.
 *
 * Arguments: none
 *
 * Return Value: none
 */
if (!hasInterface) exitWith {};
if !(isNil "cti_uiStarted") exitWith {};
cti_uiStarted = true;

cti_uiPlace = "";
cti_uiSquad = "";
cti_uiNote = "";

// Clicking the map picks the ground an Order will name. `placeOf` without the
// nearest-place fallback, so clicking open country selects nothing rather than
// silently naming a town two kilometres away — the open ground between places
// has no name (CONTEXT.md), and an Order that quietly acquired one would be an
// Order the Commander did not give.
addMissionEventHandler ["MapSingleClick", {
    params ["", "_pos"];
    private _map = missionNamespace getVariable ["cti_map", createHashMap];
    cti_uiPlace = [
        _pos,
        _map getOrDefault ["objectives", []],
        _map getOrDefault ["bases", []]
    ] call cti_fnc_placeOf;
    cti_uiNote = "";
    [] call cti_fnc_mapRender;
}];

// The key handler lives on the map display, which exists only while the map is
// open — so it is attached when the map opens rather than once at start-up.
addMissionEventHandler ["Map", {
    params ["_opened"];
    if (!_opened) exitWith {};

    // The event can arrive a frame before the display does, so it is waited for
    // rather than assumed — bounded, because a display that never turns up is a
    // bug to log and not a thread to leave spinning.
    [] spawn {
        private _by = diag_tickTime + 3;
        waitUntil { !isNull findDisplay 12 || { diag_tickTime > _by } };
        private _display = findDisplay 12;
        if (isNull _display) exitWith {
            diag_log "CTI|FAIL class=assertion_failed map_ui_no_display";
        };
        if !(_display getVariable ["cti_uiKeys", false]) then {
            _display setVariable ["cti_uiKeys", true];
            _display displayAddEventHandler ["KeyDown", {
                params ["", "_key"];
                [_key] call cti_fnc_mapIssue;
                // Never claim the key: the map's own controls keep working, and
                // a UI that ate them would be a worse map than the one it
                // replaced.
                false
            }];
        };
        [] call cti_fnc_mapRender;
    };
}];

diag_log format ["CTI|map_ui_started side=%1", cti_uiSide];
