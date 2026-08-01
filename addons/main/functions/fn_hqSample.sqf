/*
 * Author: arma-cti
 * What the world alone knows about each Base's HQ structure. Runs on the server.
 *
 * One fact per Base: whether the HQ is destroyed, and which side brought it
 * down. Whether that ends the Campaign is the daemon's (ADR-0012); whether the
 * building is standing is nobody else's to say.
 *
 * Every Base every report, standing ones included: a report that only mentioned
 * rubble could not be told from one where nothing was mentioned because nothing
 * was looked at. cti_fnc_baseAssault decides once that an HQ has fallen and this
 * repeats it, so the daemon's row is written on the first report that carries it
 * and never again.
 *
 * Arguments: none
 *
 * Return Value: <HASHMAP> Base id -> HASHMAP of `destroyed` and `by`
 */
if (!isServer) exitWith { createHashMap };

private _map = missionNamespace getVariable ["cti_map", createHashMap];
private _down = missionNamespace getVariable ["cti_hqDown", createHashMap];
private _seen = createHashMap;

{
    private _baseId = _x getOrDefault ["id", ""];
    private _fell = _down getOrDefault [_baseId, createHashMap];
    _seen set [_baseId, createHashMapFromArray [
        ["destroyed", _baseId in _down],
        ["by", _fell getOrDefault ["by", ""]]
    ]];
} forEach (_map getOrDefault ["bases", []]);

_seen
