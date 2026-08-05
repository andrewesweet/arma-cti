/*
 * Author: arma-cti
 * The free transport ladder, as SQF sees it: which vehicle a Squad of a given
 * size is issued, weakest first. Runs anywhere; only the server asks today.
 *
 * The addon ships the authored JSON verbatim and parses it here (ADR-0017), the
 * same as the map manifests and the loadout menu, and for the same reason: a
 * second rendering would be a second ladder. The deep validation runs in Python
 * over this same file and gates `just unit` — a row with no vehicle class, a
 * fleet authored out of order, a menu that seats no Squad the economy sells
 * (`cti_daemon.motorpool`). What is left for here is the failure Python cannot
 * see: the file missing or unparseable on the machine actually running the
 * mission.
 *
 * `loadFile` rather than `preprocessFile`, because preprocessing would treat a
 * `//` inside a string value as a comment.
 *
 * Parsed once per machine and cached, like cti_fnc_loadoutCatalogue: the watch
 * reads it every sweep.
 *
 * Arguments: none
 *
 * Return Value: <ARRAY> of transport HASHMAPs, each carrying `id`,
 * `display_name`, `seats` and `vehicle`, in authored order — which is weakest
 * first, and which is the order cti_fnc_transportIssue reads it in. Empty when
 * there is no ladder to issue from, and callers must treat empty as fatal.
 */
private _cached = missionNamespace getVariable ["cti_transportCatalogueCache", []];
if (count _cached > 0) exitWith { _cached };

private _path = "cti\addons\main\catalogue\transport.json";
private _raw = loadFile _path;
if (_raw isEqualTo "") exitWith {
    diag_log format ["CTI|FAIL class=assertion_failed transport_catalogue_missing path=%1", _path];
    []
};

private _document = fromJSON _raw;
if !(_document isEqualType createHashMap) exitWith {
    diag_log format ["CTI|FAIL class=assertion_failed transport_catalogue_unparseable path=%1 bytes=%2",
        _path, count _raw];
    []
};

private _fleet = _document getOrDefault ["fleet", []];
if (count _fleet isEqualTo 0) exitWith {
    // A ladder with no rungs: every Squad would be offered a ride to nothing.
    diag_log format ["CTI|FAIL class=assertion_failed transport_catalogue_empty path=%1", _path];
    []
};

// Only a ladder that parsed is cached: an empty one would pin the failure for
// the rest of the session and hide a file that arrived late.
missionNamespace setVariable ["cti_transportCatalogueCache", _fleet];
_fleet
