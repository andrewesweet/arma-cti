/*
 * Author: arma-cti
 * Resolves one map click to the Place the next Order will name. Runs on the
 * client.
 *
 * The MapSingleClick handler's whole body (#174), pulled out of
 * cti_fnc_mapCommander so the selection path — a position in, cti_uiPlace set,
 * the picture redrawn with the selection marker — is one function a probe can
 * call with a position. The engine's event dispatch is then the only part of
 * the click no probe can fire, and that part is the engine's own.
 *
 * Interior to the client's own call graph, so it carries no locality guard:
 * its callers are the MapSingleClick handler cti_fnc_mapCommander installs,
 * which no machine without a display can fire, and the probe that stands in
 * for it (#118, ADR-0041).
 *
 * cti_fnc_placeOf without the nearest-place fallback, so clicking open country
 * selects nothing rather than silently naming a town two kilometres away — the
 * open ground between places has no name (CONTEXT.md), and an Order that
 * quietly acquired one would be an Order the Commander did not give.
 *
 * Arguments:
 * 0: the clicked position <ARRAY> in [x, y]
 *
 * Return Value: none
 */
params [["_pos", [], [[]]]];

private _map = missionNamespace getVariable ["cti_map", createHashMap];
cti_uiPlace = [
    _pos,
    _map getOrDefault ["objectives", []],
    _map getOrDefault ["bases", []]
] call cti_fnc_placeOf;
cti_uiNote = "";
[] call cti_fnc_mapRender;
