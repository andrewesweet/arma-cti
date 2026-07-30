/*
 * Author: arma-cti
 * The Command Port's only door (ADR-0012). Runs on the server.
 *
 * A human Commander builds a Command client-side and remoteExecs this. The
 * mission whitelists this function alone at CfgRemoteExec mode=1, so it is the
 * only thing a client may call — which is what mechanically closes the
 * client-to-server side of "no order path outside the port". A client that
 * loaded the shim and spoke to the daemon directly would be an order path
 * outside the port, and that is what #19's audit exists to catch.
 *
 * The acting side is stamped here from the caller's own identity and the
 * client's `side` field is overwritten, never validated: a Commander's
 * authority is a fact about the server's state, not a claim in a payload.
 *
 * Arguments:
 * 0: the Command <HASHMAP> as built by cti_fnc_command
 *
 * Return Value: <BOOL> whether the Command was sent to the daemon. The
 * judgement itself comes back to the caller through cti_fnc_portReply.
 */
params [["_command", createHashMap, [createHashMap]]];

if (!isServer) exitWith { false };

private _owner = remoteExecutedOwner;

// remoteExecutedOwner is 0 when the call did not arrive over the network — the
// server calling itself, or the AI Commander, which reaches the port in-process
// on the Python side and should never be here.
private _unit = objNull;
{
    if (owner _x isEqualTo _owner) exitWith { _unit = _x };
} forEach allPlayers;

private _side = if (isNull _unit) then { "" } else { str (side group _unit) };
private _schema = call cti_fnc_commandSchema;

if !(_side in (_schema get "sides")) exitWith {
    // Identity is the gateway's business, so it answers this one itself rather
    // than asking the daemon about a caller the daemon cannot see.
    private _judgement = createHashMapFromArray [
        ["status", "rejected"],
        ["reason", createHashMapFromArray [
            ["code", "wrong_side"],
            ["detail", format ["no commanding side for owner %1", _owner]]
        ]]
    ];
    if (_owner > 0) then { [_judgement] remoteExec ["cti_fnc_portReply", _owner] };
    diag_log format ["CTI|port_rejected owner=%1 code=wrong_side", _owner];
    false
};

_command set ["side", _side];

private _id = format ["cmd-%1-%2", _owner, round (diag_tickTime * 1000)];
private _envelope = createHashMapFromArray [
    ["id", _id],
    ["verb", "command"],
    ["payload", _command]
];

// Synchronous by construction: ADR-0012 makes a Command's reply a judgement and
// never work, so it never waits on anything and stays far inside the engine's
// 1000 ms blocking-call stall cap (ADR-0005).
private _extension = call cti_fnc_shimName;
if (_extension isEqualTo "") exitWith {
    diag_log "CTI|FAIL class=infra_unavailable shim_not_loaded";
    false
};

private _reply = (_extension callExtension ["rpc_keepalive", [toJSON _envelope]]) # 0;
private _judgement = fromJSON _reply;

if !(_judgement isEqualType createHashMap) exitWith {
    diag_log format ["CTI|FAIL class=oracle_disagreement port_reply_unreadable=%1", _reply];
    false
};

diag_log format ["CTI|port_command id=%1 side=%2 command=%3 status=%4",
    _id, _side, _command get "command", _judgement getOrDefault ["status", "?"]];

// Server-to-client remoteExec is unrestricted; mode=1 binds clients only.
if (_owner > 0) then { [_judgement] remoteExec ["cti_fnc_portReply", _owner] };

true
