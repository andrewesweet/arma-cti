/*
 * Author: arma-cti
 * Receives this Commander's own Observation. Runs on the client.
 *
 * Pushed by the server (cti_fnc_commanderView) rather than asked for from here:
 * a client never loads the shim and never speaks to the daemon (ADR-0018), so
 * the only picture that exists on this machine is the one the server sent it.
 *
 * Receiving one at all is how a client learns it is a Commander. The server
 * sends a view to the machine it has assigned and to no other, so there is
 * nothing to ask and nothing to claim: the UI comes up when a picture arrives
 * for it to draw.
 *
 * Arguments:
 * 0: the Observation <HASHMAP>, in the shape cti_daemon.observation.serialise
 *    writes — `owners`, `hq`, `side`, `funds`, `squads`, `contacts`
 *
 * Return Value: none
 */
#include "\cti\addons\main\script_component.hpp"

params [["_view", createHashMap, [createHashMap]]];

// One of the two doors the server pushes through, and server-to-client
// remoteExec is unrestricted (topics/Arma_3_CfgRemoteExec.wiki), so
// `description.ext` offers no protection here and this guard is the only thing
// there is (#118, ADR-0041).
INTERFACE_ONLY(nil);

private _side = _view getOrDefault ["side", ""];
if (_side isEqualTo "") exitWith {
    // The public picture belongs to nobody (#27) and is not a Commander's view.
    // Arriving here it would be a projection bug on the server, not a UI state.
    diag_log "CTI|FAIL class=assertion_failed map_view_without_side";
};

cti_view = _view;
cti_uiSide = _side;

[] call cti_fnc_mapCommander;
[] call cti_fnc_mapRender;
