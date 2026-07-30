/*
 * Author: arma-cti
 * Finds the manifest for a world and checks it is whole enough to build on.
 *
 * The deep validation — adjacency symmetry, graph connectivity, ID shape —
 * runs in Python over the authored JSON and gates `just unit`, so it never
 * reaches a Play Session. What is left for here is the failure Python cannot
 * see: the generated file missing, stale or truncated on the machine actually
 * running the mission. That has to be caught before a half-built world boots,
 * because an empty world looks like a working one until somebody tries to
 * capture something.
 *
 * Arguments:
 * 0: world name <STRING> (optional, default the running world)
 *
 * Return Value: the map <HASHMAP>, or an empty HASHMAP when there is none to
 * play on. Callers must treat empty as fatal.
 */
params [["_world", worldName, [""]]];

if (isNil "cti_fnc_manifestData") exitWith {
    diag_log "CTI|FAIL class=schema_stale manifest_data_missing";
    createHashMap
};

private _maps = call cti_fnc_manifestData;
if !(_maps isEqualType createHashMap) exitWith {
    diag_log "CTI|FAIL class=schema_stale manifest_data_not_a_hashmap";
    createHashMap
};

private _found = createHashMap;
{
    if ((_y getOrDefault ["world", ""]) isEqualTo _world) then { _found = _y };
} forEach _maps;

if (count _found isEqualTo 0) exitWith {
    diag_log format ["CTI|FAIL class=assertion_failed no_manifest_for_world=%1", _world];
    createHashMap
};

// A manifest that parsed but carries nothing to play on is the half-built
// world this guard exists to refuse.
private _objectives = _found getOrDefault ["objectives", []];
private _bases = _found getOrDefault ["bases", []];
if (count _objectives isEqualTo 0 || {count _bases isEqualTo 0}) exitWith {
    diag_log format ["CTI|FAIL class=schema_stale manifest_empty world=%1 objectives=%2 bases=%3",
        _world, count _objectives, count _bases];
    createHashMap
};

_found
