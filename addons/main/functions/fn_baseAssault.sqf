/*
 * Author: arma-cti
 * Presses home standing Assaults, and notices when an HQ has fallen. Server only.
 *
 * The engine's Destroy waypoint sends a Squad at the HQ structure and keeps it
 * there (cti_fnc_orderApply), but a rifle squad cannot demolish a building with
 * small arms: left to the engine, the group closes, fires, and waits forever for
 * something to fall down. So the closing is the engine's and the demolition is
 * this — a Squad under an Assault Order, standing at the enemy Base's HQ, brings
 * it down in a bounded time.
 *
 * **The means of destruction and the durability below are playtest-tuned
 * placeholders**, in exactly the sense the economy numbers are (ADR-0020,
 * docs/mvp-scope.md): what is being built here is the structure — Assault
 * ordered, Squad closes, HQ can die, telemetry says so — and they are the first
 * two things a playtest will move. Neither is a rule the daemon owns, because
 * neither is a rule: they are how long a thing takes in the world, which is the
 * world's half (ADR-0012).
 *
 * The alternatives, for whoever tunes this: charges in the Squad's loadout (a
 * purchase-side change, and a Squad that spent them has nothing left for the
 * next Base), or launcher damage (a composition-side change, and the AI's aim at
 * a building is its own subject). Both were passed over as more moving parts
 * than a placeholder needs, not as worse ideas.
 *
 * Destruction is noticed by polling `damage` rather than by a Killed event
 * handler, so an HQ that falls to anything at all — this, a player's satchel, a
 * stray shell — is the same event. Recorded exactly once per Base, because
 * `docs/mvp-scope.md` resolves a mutual Decapitation by which destruction came
 * first in telemetry, and a second row for the same Base would make that a
 * question of which report arrived rather than which HQ died.
 *
 * Arguments:
 * 0: seconds between sweeps <NUMBER> (optional, default 5)
 *
 * Return Value: <SCRIPT> the sweep thread
 */
#include "\cti\addons\main\script_component.hpp"

params [["_interval", 5, [0]]];

// The entry point of a supervised loop, which ADR-0041 keeps guarded: this is the
// one call site a future restart would re-enter, and the thread it starts is
// inventoried by name rather than by caller (#118).
SERVER_ONLY(scriptNull);

// What the world knows about each Base's HQ, for cti_fnc_hqSample to report and
// for this sweep to keep to one telling. Empty until something falls.
missionNamespace setVariable ["cti_hqDown", createHashMap, true];

// ---- playtest-tuned placeholder (ADR-0020) -------------------------------
// How long a Squad standing at the HQ needs to bring it down, in seconds. Head
// count does not scale it: a placeholder that rewarded stacking Squads would be
// a balance decision arriving by accident.
//
// How *close* is not a second number here. It is the Order's own ground, set
// once in cti_fnc_orderApply, because "still under this Order" and "still
// working on the HQ" are one question and two answers would drift.
private _durability = 90;
// --------------------------------------------------------------------------

diag_log format ["CTI|base_assault_started interval=%1 durability=%2",
    _interval, _durability];

private _bases = (missionNamespace getVariable ["cti_map", createHashMap])
    getOrDefault ["bases", []];
private _places = missionNamespace getVariable ["cti_placesById", createHashMap];

// Paced, heartbeated and watched by the one adapter every loop in the addon
// runs on (#85).
["base_assault", _interval, [_interval, _durability, _bases, _places], {
    params ["_interval", "_durability", "_bases", "_places"];

    private _down = missionNamespace getVariable ["cti_hqDown", createHashMap];

    // Who is working on which HQ this sweep. Read afterwards for the
    // attribution the telemetry event carries, so an HQ that falls to nobody's
    // Assault says so by carrying no attacker rather than by guessing at one.
    private _pressing = createHashMap;

    // Engine side→name through the vocabulary's one home (#149), fetched once
    // per sweep rather than respelled per Squad.
    private _nameBySide = (call cti_fnc_sideVocabulary) getOrDefault ["nameBySide", createHashMap];

    {
        private _squadId = _x;
        private _group = _y;
        if (!isNull _group) then {
            private _standing = _group getVariable ["cti_order", createHashMap];
            if ((_standing getOrDefault ["order", ""]) isEqualTo "assault") then {
                private _place = _standing getOrDefault ["place", ""];
                // A lookup rather than a scan over every Base inside a per-Squad
                // loop on a five-second sweep (#109).
                private _ground = _places getOrDefault [_place, createHashMap];
                private _hq = missionNamespace getVariable
                    [_ground getOrDefault ["hq", ""], objNull];
                if (!isNull _hq && { !(_place in _down) }) then {
                    private _at = getPosATL _hq;
                    // The Order's ground: at the HQ rather than merely inside
                    // the Base. Nothing to press with if the Order carried
                    // none, which is a bug in whoever wrote it rather than a
                    // licence to pick a distance here.
                    private _reach = _standing getOrDefault ["radius", 0];
                    private _working = {
                        alive _x && { (getPosATL _x) distance _at <= _reach }
                    } count units _group;
                    if (_working > 0) then {
                        private _by = _nameBySide getOrDefault [side _group, ""];
                        _pressing set [_place, _by];
                        private _was = damage _hq;
                        private _now = _was + (_interval / _durability);
                        _hq setDamage (_now min 1);
                        diag_log format ["CTI|hq_pressed base=%1 squad=%2 side=%3 men=%4 damage=%5",
                            _place, _squadId, _by, _working, damage _hq];
                    };
                };
            };
        };
    } forEach (missionNamespace getVariable ["cti_squads", createHashMap]);

    {
        private _baseId = _x getOrDefault ["id", ""];
        if !(_baseId in _down) then {
            private _hq = missionNamespace getVariable [_x getOrDefault ["hq", ""], objNull];
            // A wrecked structure is still an object, so `damage` is the
            // reading that holds; `alive` covers the rest. An HQ that is *no
            // object at all* is a world built without one, which
            // initServer.sqf has already refused in as many words — calling
            // that a Decapitation would announce a victory over a mission file.
            if (!isNull _hq && { !alive _hq || { damage _hq >= 1 } }) then {
                private _by = _pressing getOrDefault [_baseId, ""];
                _down set [_baseId, createHashMapFromArray [["by", _by]]];
                missionNamespace setVariable ["cti_hqDown", _down, true];
                // The one telling, in the world's log. The daemon writes the
                // matching row from the report cti_fnc_hqSample carries.
                diag_log format ["CTI|hq_destroyed base=%1 side=%2 by=%3 at=%4",
                    _baseId, _x getOrDefault ["side", ""], _by, time];
            };
        };
    } forEach _bases;
}] call cti_fnc_everyInterval
