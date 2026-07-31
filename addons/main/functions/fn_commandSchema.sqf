/*
 * Author: arma-cti
 * The Command Port schema, as SQF sees it: which Commands exist and what each
 * needs, which sides command, which Orders a Squad can be given, the rejection
 * codes the daemon can return, and the Squad price table for display.
 *
 * The Command catalogue lives in Python (`cti_daemon.commands`,
 * `cti_daemon.port`), not in an authored file, so unlike the map manifests it
 * has to be exported — `tools/export_command_schema.py` writes it, and a stale
 * copy is a `schema_stale` failure in `just check`. What ADR-0017 changed is
 * that the export is JSON the engine parses rather than SQF literals the
 * exporter had to escape. Read through cti_fnc_command rather than called
 * directly.
 *
 * Parsed once per machine and cached: every Command built and every Command
 * judged asks for this, and re-reading a file off disk per Order is a cost
 * with nothing to buy.
 *
 * Arguments: none
 *
 * Return Value: schema <HASHMAP>, or an empty HASHMAP when the export is
 * missing or unreadable. Callers must treat empty as fatal.
 */
private _cached = missionNamespace getVariable ["cti_commandSchemaCache", createHashMap];
if (count _cached > 0) exitWith { _cached };

private _path = "cti\addons\main\generated\command-schema.json";
private _raw = loadFile _path;
if (_raw isEqualTo "") exitWith {
    diag_log format ["CTI|FAIL class=schema_stale command_schema_missing path=%1", _path];
    createHashMap
};

private _schema = fromJSON _raw;
if !(_schema isEqualType createHashMap) exitWith {
    diag_log format ["CTI|FAIL class=schema_stale command_schema_unparseable path=%1 bytes=%2",
        _path, count _raw];
    createHashMap
};

// Only a schema that parsed is cached: an empty one would pin the failure for
// the rest of the session and hide a file that arrived late.
missionNamespace setVariable ["cti_commandSchemaCache", _schema];
_schema
