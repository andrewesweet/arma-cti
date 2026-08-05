/*
 * Author: arma-cti
 * The curated loadout menu, as SQF sees it: which kits a player may take and
 * which unit class each is cut from, per side. Runs anywhere.
 *
 * The addon ships the authored JSON verbatim and parses it here (ADR-0017), the
 * same as the map manifests and for the same reason: the daemon reads this file
 * too — it records which kit each player chose, because that is what the
 * snapshot persists (ADR-0056, ADR-0008) — and a second rendering would be a
 * second menu. `loadFile` rather than `preprocessFile`, because preprocessing
 * would treat a `//` inside a string value as a comment.
 *
 * The deep validation runs in Python over this same file and gates `just unit`:
 * a kit with no id, a side with no unit class, a duplicate id. What is left for
 * here is the failure Python cannot see — the file missing or unparseable on
 * the machine actually running the mission — because a menu that silently came
 * up empty would look exactly like a menu nobody had opened yet.
 *
 * Parsed once per machine and cached, like cti_fnc_commandSchema: the server's
 * watch reads it every sweep and a client reads it to draw its actions.
 *
 * Arguments: none
 *
 * Return Value: <ARRAY> of kit HASHMAPs, each carrying `id`, `display_name` and
 * `units`, in authored order — which is the order the menu shows. Empty when
 * there is no menu to offer, and callers must treat empty as fatal.
 */
private _cached = missionNamespace getVariable ["cti_loadoutCatalogueCache", []];
if (count _cached > 0) exitWith { _cached };

private _path = "cti\addons\main\catalogue\loadouts.json";
private _raw = loadFile _path;
if (_raw isEqualTo "") exitWith {
    diag_log format ["CTI|FAIL class=assertion_failed loadout_catalogue_missing path=%1", _path];
    []
};

private _document = fromJSON _raw;
if !(_document isEqualType createHashMap) exitWith {
    diag_log format ["CTI|FAIL class=assertion_failed loadout_catalogue_unparseable path=%1 bytes=%2",
        _path, count _raw];
    []
};

private _kits = _document getOrDefault ["kits", []];
if (count _kits isEqualTo 0) exitWith {
    // A menu with nothing on it is the half-built world this guard refuses:
    // every player would be offered an action that does nothing.
    diag_log format ["CTI|FAIL class=assertion_failed loadout_catalogue_empty path=%1", _path];
    []
};

// Only a menu that parsed is cached: an empty one would pin the failure for the
// rest of the session and hide a file that arrived late.
missionNamespace setVariable ["cti_loadoutCatalogueCache", _kits];
_kits
