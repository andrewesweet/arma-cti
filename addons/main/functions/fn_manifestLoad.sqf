/*
 * Author: arma-cti
 * Finds the manifest for a world and checks it is whole enough to build on.
 *
 * The addon ships the authored JSON verbatim and parses it here (ADR-0017).
 * `loadFile` rather than `preprocessFile`, because preprocessing would treat a
 * `//` inside a string value as a comment; `fromJSON` because the engine has
 * had a JSON parser since 2.18 and the server runs 2.20. There is no second
 * rendering of this data, so there is nothing for it to drift from.
 *
 * The manifest is resolved from the running world's name: the file for world
 * `Stratis` is `stratis.json`. That rule is enforced in Python over the whole
 * directory (`manifest.load_all`), which is the only reader that can see it.
 *
 * The deep validation — adjacency symmetry, graph connectivity, ID shape —
 * runs in Python over the same authored JSON and gates `just unit`, so it
 * never reaches a Play Session. What is left for here is the failure Python
 * cannot see: the file missing, truncated or unparseable on the machine
 * actually running the mission. That has to be caught before a half-built
 * world boots, because an empty world looks like a working one until somebody
 * tries to capture something.
 *
 * Arguments:
 * 0: world name <STRING> (optional, default the running world)
 *
 * Return Value: the map <HASHMAP>, or an empty HASHMAP when there is none to
 * play on. Callers must treat empty as fatal.
 */
params [["_world", worldName, [""]]];

private _path = format ["cti\addons\main\manifests\%1.json", toLower _world];
private _raw = loadFile _path;
if (_raw isEqualTo "") exitWith {
    diag_log format ["CTI|FAIL class=assertion_failed no_manifest_for_world=%1 path=%2",
        _world, _path];
    createHashMap
};

private _found = fromJSON _raw;
if !(_found isEqualType createHashMap) exitWith {
    // A truncated or corrupted file parses to nil, or to something that is not
    // an object. Either way there is no map here.
    diag_log format ["CTI|FAIL class=assertion_failed manifest_unparseable world=%1 path=%2 bytes=%3",
        _world, _path, count _raw];
    createHashMap
};

if ((_found getOrDefault ["world", ""]) isNotEqualTo _world) exitWith {
    // The filename resolved but the document inside names a different world:
    // the naming rule Python enforces has been broken somewhere downstream.
    diag_log format ["CTI|FAIL class=assertion_failed manifest_wrong_world=%1 wanted=%2",
        _found getOrDefault ["world", ""], _world];
    createHashMap
};

// A manifest that parsed but carries nothing to play on is the half-built
// world this guard exists to refuse.
private _objectives = _found getOrDefault ["objectives", []];
private _bases = _found getOrDefault ["bases", []];
if (count _objectives isEqualTo 0 || {count _bases isEqualTo 0}) exitWith {
    diag_log format ["CTI|FAIL class=assertion_failed manifest_empty world=%1 objectives=%2 bases=%3",
        _world, count _objectives, count _bases];
    createHashMap
};

_found
