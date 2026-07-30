/*
 * Author: arma-cti
 * Records an Objective's owner and repaints it on the map. Runs on the server.
 *
 * The owner is the daemon's to decide; this only reflects it. Contested gets
 * its own colour rather than sharing Neutral's, because it is a real state a
 * Commander has to be able to see and react to (#13).
 *
 * Arguments:
 * 0: Objective id <STRING>
 * 1: owner <STRING> — "WEST", "EAST", "NEUTRAL" or "CONTESTED"
 *
 * Return Value: <BOOL> whether the owner changed
 */
params [["_id", "", [""]], ["_owner", "NEUTRAL", [""]]];

if (!isServer) exitWith { false };

private _owners = missionNamespace getVariable ["cti_objectiveOwner", createHashMap];
if ((_owners getOrDefault [_id, ""]) isEqualTo _owner) exitWith { false };

_owners set [_id, _owner];
missionNamespace setVariable ["cti_objectiveOwner", _owners, true];

private _colour = [_owner] call cti_fnc_sideMarkerColour;
// A global marker command publishes the marker's whole state, so both markers
// take one global call each rather than a local change plus a publish.
(format ["cti_objective_%1", _id]) setMarkerColor _colour;
(format ["cti_objective_%1_area", _id]) setMarkerColor _colour;

diag_log format ["CTI|objective_owner id=%1 owner=%2", _id, _owner];

true
