/*
 * Author: arma-cti
 * Which side a machine commands, if any. Runs on the server.
 *
 * Interior to the server's own call graph, so it carries no locality guard: its
 * callers are cti_fnc_portGateway and cti_fnc_commanderView, both of which have
 * already decided the machine (#118, ADR-0041).
 *
 * The gateway's whole question, asked in one place so the answer cannot differ
 * between the door a Command comes through and the channel an Observation goes
 * out on. A machine that commands nothing gets "", which is a refusal at the
 * gateway and no Observation at all — a client the server has not assigned is
 * a client with no Commander's view to be sent.
 *
 * Resolved every time rather than cached against the machine id: a player who
 * reconnects is the same Commander on a new machine id, and a cache keyed by
 * the old one would silently disenfranchise them.
 *
 * Arguments:
 * 0: the machine network id <NUMBER>, as remoteExecutedOwner gives it
 *
 * Return Value: <STRING> the side that machine commands, or "" for none
 */
params [["_owner", 0, [0]]];

// Zero is not a machine. It is what remoteExecutedOwner returns for a call that
// did not arrive over the network — the server calling itself — and also, by
// engine design, for one that arrived from a headless client. Neither is a
// Commander, and treating zero as one would make "the server" a player.
if (_owner <= 0) exitWith { "" };

private _assigned = missionNamespace getVariable ["cti_commanders", createHashMap];
if (count _assigned isEqualTo 0) exitWith { "" };

private _side = "";
{
    if (owner _x isEqualTo _owner) exitWith {
        private _uid = getPlayerUID _x;
        {
            if (_y isEqualTo _uid) exitWith { _side = _x };
        } forEach _assigned;
    };
} forEach allPlayers;

_side
