/*
 * Author: arma-cti
 * Keeps every Squad standing at its own Base in a free ride. Runs on the server.
 *
 * The human's ruling of 2026-08-03 (#170, ADR-0059): the weakest motorised
 * transport that seats a Squad, free, at all times. "At all times" is a
 * standing condition rather than an event, so it is a watch and not a hook —
 * cti_fnc_loadoutWatch's reasoning and #189's before it. One rule, asked every
 * sweep: *this Squad is at its own Base and has no vehicle here, so give it
 * one.* That covers a Squad the moment it is bought, a Squad whose truck was
 * shot out from under it, a Squad that abandoned one across the island and
 * marched home, and a Campaign resumed when #4 lands — where a spawn hook would
 * cover the first of the four and need company for the other three.
 *
 * **Nobody asks.** There is no request, no Command, no Funds and no Judgement,
 * which is why the ruling's "or AI commander on behalf of squad leaders" needs
 * no planner change at all: an AI-led Squad and a player-led one are issued a
 * vehicle by the same sweep, because neither of them had to ask. A kit is not a
 * Command for the same reason (ADR-0056), and this adds no Command Port entry
 * and nothing to the CfgRemoteExec whitelist.
 *
 * **At the Base, and only there.** Consistent with restock and Reinforce being
 * free Base activities (ADR-0040's pinned line) and with the loadout menu
 * (ADR-0056): free things happen where a side's men are already going. The
 * reading is `cti_fnc_placeOf` off the leader's position — the same call
 * cti_fnc_squadSample reports a Squad's position with, so "at Base" means here
 * what it means on the Observation.
 *
 * Arguments:
 * 0: seconds between sweeps <NUMBER> (optional, default 10)
 *
 * Return Value: <SCRIPT> the watch thread
 */
#include "\cti\addons\main\script_component.hpp"

params [["_interval", 10, [0]]];

// The entry point of a supervised loop, which ADR-0041 keeps guarded: this is the
// one call site a future restart would re-enter, and the thread it starts is
// inventoried by name rather than by caller (#118).
SERVER_ONLY(scriptNull);

private _fleet = call cti_fnc_transportCatalogue;
if (_fleet isEqualTo []) exitWith {
    // cti_fnc_transportCatalogue has already logged which failure this is. Asked
    // before the thread is started rather than inside it (#102): a loop enters
    // the watchdog's register only once it is going to run.
    diag_log "CTI|FAIL class=assertion_failed transport_watch_no_catalogue";
    scriptNull
};

diag_log format ["CTI|transport_watch_started interval=%1 rungs=%2", _interval, count _fleet];

// Paced, heartbeated and watched by the one adapter every loop in the addon runs
// on (#85). First turn taken at once, so a Squad already standing at its Base
// when this starts is not made to wait a cadence for its ride.
["transport_watch", _interval, [_fleet], {
    params ["_fleet"];

    private _map = missionNamespace getVariable ["cti_map", createHashMap];
    private _objectives = _map getOrDefault ["objectives", []];
    private _bases = _map getOrDefault ["bases", []];
    private _basesBySide = missionNamespace getVariable ["cti_basesBySide", createHashMap];
    private _nameBySide = (call cti_fnc_sideVocabulary) getOrDefault ["nameBySide", createHashMap];

    {
        private _squadId = _x;
        private _group = _y;
        // A Squad the world has lost, or one wiped out: nothing to carry.
        if (!isNull _group && { (units _group findIf { alive _x }) > -1 }) then {
            private _base = _basesBySide getOrDefault [
                _nameBySide getOrDefault [side _group, ""], createHashMap];
            private _baseId = _base getOrDefault ["id", ""];
            if (_baseId isNotEqualTo "") then {
                private _at = [getPosATL leader _group, _objectives, _bases] call cti_fnc_placeOf;
                if (_at isEqualTo _baseId) then {
                    // Its own vehicle, and here rather than merely alive. A truck
                    // abandoned at an Objective is one this Squad would have to
                    // walk back to, which is the yomping the ruling ends — so it
                    // does not count as having one, and cti_fnc_transportIssue
                    // disowns it.
                    private _held = _group getVariable ["cti_transport", objNull];
                    private _here = !isNull _held && {alive _held}
                        && {([getPosATL _held, _objectives, _bases] call cti_fnc_placeOf)
                            isEqualTo _baseId};
                    if (!_here) then {
                        [_group, _squadId, _base, _fleet] call cti_fnc_transportIssue;
                    };
                };
                [_group, _squadId] call cti_fnc_transportPool;
            };
        };
    } forEach (missionNamespace getVariable ["cti_squads", createHashMap]);
}, true] call cti_fnc_everyInterval
